"""Reuse the legacy eye designer's eye materials in the Qt studio."""
from dataclasses import replace

from PIL import Image

from eye_designer import (
    DEFAULT_IRIS, DEFAULT_LASH, DEFAULT_SKIN, DEFAULT_WHITE,
    classify_reference_eye_features, preset_eye_features, retarget_eye_pixel,
)
from skin_styler_core import FaceTemplate, is_eye_feature_coordinate, make_face_template, parse_hex_color

EYE_MATERIALS = {"iris": "irisColor", "liner": "linerColor", "white": "whiteColor"}
EYE_DEFAULTS = {"iris": DEFAULT_IRIS, "liner": DEFAULT_LASH, "white": DEFAULT_WHITE}
EYE_TOOLS = (*EYE_MATERIALS, "eraser")


def _eye_coordinate(key):
    try:
        x, y = map(int, key.split(","))
    except (ValueError, AttributeError):
        return None
    return (x, y) if is_eye_feature_coordinate(x, y) else None


def eye_coordinates(saved):
    """Read a sparse, JSON-safe map in the legacy normalized eye coordinates."""
    result = {}
    if isinstance(saved, dict):
        for key, material in saved.items():
            coordinate = _eye_coordinate(key)
            if coordinate is not None and material in EYE_TOOLS:
                result[coordinate] = material
    return result


def freeze_eye_template(template):
    """Store just the editable eye band, not the source skin image."""
    return {
        "skin": list(template.skin_color),
        "features": {f"{x},{y}": list(color) for (x, y), color in template.features.items()},
    }


def thaw_eye_template(saved):
    def valid_color(color, length):
        return (isinstance(color, list) and len(color) == length
                and all(type(channel) is int and 0 <= channel <= 255 for channel in color))

    if not isinstance(saved, dict) or not valid_color(saved.get("skin"), 3):
        return None
    colors = saved.get("features")
    if not isinstance(colors, dict):
        return None
    features = {}
    for key, color in colors.items():
        coordinate = _eye_coordinate(key)
        if coordinate is not None and valid_color(color, 4):
            features[coordinate] = tuple(color)
    return FaceTemplate(features, tuple(saved["skin"]))


def eye_template(reference, options):
    if options.get("eyeBase"):
        return thaw_eye_template(options["eyeBase"])
    if reference is not None:
        return make_face_template(reference)
    if options.get("eyeReference") == "@preset":
        return FaceTemplate(
            preset_eye_features("Soft lashes", *(parse_hex_color(color) for color in EYE_DEFAULTS.values())),
            DEFAULT_SKIN,
        )
    return None


def design_eyes(base, options):
    """Tint the original shades, then layer explicit material/eraser strokes."""
    features = dict(base.features)
    classified = classify_reference_eye_features(features)
    targets = {}
    for (material, color_key), coords, source in zip(EYE_MATERIALS.items(), classified[:3], classified[3:]):
        value = options.get(color_key)
        targets[material] = parse_hex_color(value) if value else source
        if targets[material] != source:
            for coordinate in coords:
                features[coordinate] = retarget_eye_pixel(features[coordinate], source, targets[material])
    for coordinate, material in eye_coordinates(options.get("eyePixels")).items():
        if material == "eraser":
            features.pop(coordinate, None)
        else:
            features[coordinate] = (*targets[material], 255)
    return replace(base, features=features), targets


def eye_canvas(template):
    """A face-sized editor; the surrounding pixels show the fixed eye band."""
    canvas = Image.new("RGBA", (8, 8), (*template.skin_color, 255))
    for y in range(8, 16):
        for x in range(8, 16):
            if is_eye_feature_coordinate(x, y):
                canvas.putpixel((x - 8, y - 8), (246, 235, 252, 255))
    for (x, y), color in template.features.items():
        if 8 <= x < 16 and 8 <= y < 16:
            canvas.putpixel((x - 8, y - 8), color)
    return canvas
