"""Background preview adapter; all image processing stays in the existing core."""
from __future__ import annotations

import json
from statistics import median
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from skin_styler_core import (
    apply_category_overrides, classify_skin_categories, cuboid_face_boxes, player_uv_parts,
    recommended_hair_tolerance,
    make_face_template, normalize_skin, parse_hex_color, resolve_skin_model,
    render_front_face, render_player_3d, style_skin,
)
from studio_eyes import design_eyes, eye_coordinates, eye_template, freeze_eye_template, thaw_eye_template


DEFAULT_STYLE = {
    "hairEnabled": False, "hairColor": "#A26EBB", "hairMode": "reference",
    "eyesEnabled": False, "eyesOverBangs": True, "keep3DLashes": True,
    "skinEnabled": False, "skinColor": "#E8BAA2", "skinMode": "reference",
    "outfitEnabled": False, "outfitColor": "#B587D1",
    "accessoryEnabled": False, "accessoryColor": "#C994BA",
    "eyeReference": "", "eyeMirror": True, "eyePixels": {}, "eyeBase": {},
    "irisColor": "", "linerColor": "", "whiteColor": "",
    "shadingBase": "",
}


def clean_style(saved):
    result = dict(DEFAULT_STYLE)
    if not isinstance(saved, dict):
        return result
    for key, default in DEFAULT_STYLE.items():
        value = saved.get(key, default)
        if isinstance(default, bool):
            result[key] = value if isinstance(value, bool) else default
        elif key in ("eyeReference", "shadingBase"):
            result[key] = value if isinstance(value, str) else default
        elif key == "eyePixels":
            result[key] = {f"{x},{y}": material for (x, y), material in eye_coordinates(value).items()}
        elif key == "eyeBase":
            base = thaw_eye_template(value)
            if base is not None:
                result[key] = freeze_eye_template(base)
        elif key in ("hairMode", "skinMode"):
            result[key] = value if value in ("reference", "custom") else default
        else:
            try:
                rgb = parse_hex_color(value)
                result[key] = "#%02X%02X%02X" % rgb
            except (ValueError, TypeError, AttributeError):
                pass
    # Preserve colors explicitly customized in an older studio state. The old
    # untouched peach preset must not masquerade as a sampled reference tone.
    if "skinMode" not in saved and result["skinColor"] != DEFAULT_STYLE["skinColor"]:
        result["skinMode"] = "custom"
    return result


def pil_to_qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    return QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format_RGBA8888).copy()


def reference_skin_tone(reference, template=None):
    """Don't advertise the face-template fallback as a sampled skin tone."""
    texture, _ = normalize_skin(reference)
    face = texture.crop((9, 11, 15, 16))
    if sum(alpha >= 128 for alpha in face.getchannel("A").tobytes()) < 2:
        return None
    return (template or make_face_template(texture)).skin_color


@dataclass(frozen=True)
class PreviewRequest:
    revision: int
    path: Path
    reference: Path | None
    options: dict
    details: dict
    corrections: dict
    yaw: float
    eye_reference: Path | None = None
    eye_workspace: bool = False
    viewport_token: str = ""


@dataclass(frozen=True)
class ViewportFrames:
    fallback: tuple
    packet: str


def styled_texture(original, reference, options, details, corrections, eye_reference=None):
    eyes_enabled = options["eyesEnabled"]
    eye_source = eye_reference if options.get("eyeReference") else reference or original
    if not (options["hairEnabled"] or options["skinEnabled"] or eyes_enabled
            or options.get("outfitEnabled") or options.get("accessoryEnabled")):
        return normalize_skin(original)[0].copy()
    base_eyes = eye_template(eye_source, options) if eyes_enabled else None
    template = design_eyes(base_eyes, options)[0] if base_eyes is not None else None
    skin_target = None
    if options["skinEnabled"]:
        if options.get("skinMode", "reference") == "custom":
            skin_target = parse_hex_color(options["skinColor"])
        elif reference is not None:
            skin_target = reference_skin_tone(reference, base_eyes if eye_source is reference else None)
        # Matching an already-matching sample is an identity operation. The
        # legacy tint function rebalances whole-mask brightness/saturation even
        # for the same face color; don't darken the reference's own shading.
        if skin_target is not None and skin_target == make_face_template(original).skin_color:
            skin_target = None
    styled, _mask, _normalized = style_skin(
        original,
        parse_hex_color(options["hairColor"]) if options["hairEnabled"] else None,
        face_template=template,
        target_skin_color=skin_target,
        target_outfit_color=parse_hex_color(options["outfitColor"]) if options.get("outfitEnabled") else None,
        target_accessory_color=parse_hex_color(options["accessoryColor"]) if options.get("accessoryEnabled") else None,
        eyes_over_bangs=options["eyesOverBangs"],
        preserve_hat_layer_lashes=options["keep3DLashes"],
        category_overrides=corrections,
        adaptive_detection=True,
        suppress_hair=details.get("hair_mode") == "none",
    )
    return styled


def apply_body_shading(styled, base, skin_mask, slim, base_slim):
    """Replace body shading using corresponding faces of a bare base texture."""
    def brightness(pixel):
        return .2126 * pixel[0] + .7152 * pixel[1] + .0722 * pixel[2]

    target_pixels = styled.load()
    source_pixels = base.load()
    samples = []
    changes = []
    for target_part, base_part in zip(player_uv_parts(slim)[1:], player_uv_parts(base_slim)[1:]):
        _, target_origin, target_outer, *target_size = target_part
        _, base_origin, _, *base_size = base_part
        base_faces = cuboid_face_boxes(base_origin, *base_size)
        for origin in (target_origin, target_outer):
            for face, (left, top, right, bottom) in cuboid_face_boxes(origin, *target_size).items():
                bx, by, br, bb = base_faces[face]
                for y in range(top, bottom):
                    for x in range(left, right):
                        sx = bx + int((x - left + .5) * (br - bx) / (right - left))
                        sy = by + int((y - top + .5) * (bb - by) / (bottom - top))
                        pixel = source_pixels[sx, sy]
                        if pixel[3] < 128:
                            continue
                        shade = brightness(pixel)
                        if origin == target_origin:
                            samples.append(shade)
                        point = (x, y)
                        if point in skin_mask and target_pixels[point][3] >= 48:
                            changes.append((point, shade))
    if not changes:
        return
    center = median(samples)
    tone = tuple(median(target_pixels[point][channel] for point, _ in changes) for channel in range(3))
    for point, shade in changes:
        alpha = target_pixels[point][3]
        target_pixels[point] = tuple(round(max(0, min(255, channel + shade - center)))
                                     for channel in tone) + (alpha,)


class PreviewRenderer:
    """Used serially by one worker at a time; rotation reuses styled textures."""
    def __init__(self):
        self.cache = {}

    def textures(self, request):
        needs_reference = ((request.options["eyesEnabled"] and not request.options.get("eyeReference"))
                           or (request.options["skinEnabled"] and request.options.get("skinMode", "reference") == "reference"))
        reference_path = request.reference if needs_reference else None
        eye_path = request.eye_reference if request.options["eyesEnabled"] and request.options.get("eyeReference") else None
        shading_path = Path(request.details["shadingPath"]) if request.details.get("shadingPath") else None
        def stamp(path):
            if path is None:
                return None
            stat = path.stat()
            return path, stat.st_mtime_ns, stat.st_size
        key = (stamp(request.path), stamp(reference_path), stamp(eye_path), stamp(shading_path),
               json.dumps(request.options, sort_keys=True), json.dumps(request.details, sort_keys=True),
               tuple(sorted(request.corrections.items())))
        if key not in self.cache:
            with Image.open(request.path) as source:
                original, _ = normalize_skin(source)
            if "textureDraft" in request.details:
                draft = Image.frombytes("RGBA", original.size, bytes.fromhex(request.details["textureDraft"]))
                return original, draft, resolve_skin_model(original, request.details.get("model", "auto")) == "slim"
            reference = None
            if reference_path:
                with Image.open(reference_path) as source:
                    reference, _ = normalize_skin(source)
            eye_reference = None
            if eye_path:
                with Image.open(eye_path) as source:
                    eye_reference, _ = normalize_skin(source)
            styled = styled_texture(original, reference, request.options, request.details, request.corrections, eye_reference)
            slim = resolve_skin_model(original, request.details.get("model", "auto")) == "slim"
            if shading_path:
                with Image.open(shading_path) as source:
                    shading, _ = normalize_skin(source)
                base_slim = resolve_skin_model(shading, request.details.get("shadingModel", "auto")) == "slim"
                mask = apply_category_overrides(
                    classify_skin_categories(original, recommended_hair_tolerance(original)),
                    request.corrections).skin
                apply_body_shading(styled, shading, mask, slim, base_slim)
            if len(self.cache) >= 12:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = original, styled, slim
        return self.cache[key]

    def render(self, request):
        original, styled, slim = self.textures(request)
        # Both views use identical geometry/yaw, enabling a true before/after wipe.
        frames = tuple(pil_to_qimage(render_player_3d(image, scale=12, slim=slim,
                       yaw_degrees=request.yaw)) for image in (original, styled))
        if request.eye_workspace:
            frames += (pil_to_qimage(render_front_face(styled, scale=12)),)
        if not request.viewport_token:
            return frames
        return ViewportFrames(frames, json.dumps({
            "token": request.viewport_token,
            "slim": slim,
            "original": b64encode(original.tobytes()).decode("ascii"),
            "styled": b64encode(styled.tobytes()).decode("ascii"),
        }, separators=(",", ":")))


class PreviewSignals(QObject):
    finished = Signal(int, object, str)


class PreviewJob(QRunnable):
    def __init__(self, renderer, request):
        super().__init__()
        self.renderer, self.request = renderer, request
        self.signals = PreviewSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.request.revision, self.renderer.render(self.request), "")
        except Exception as error:
            # Report rather than clearing the stage or letting a worker exception
            # terminate the application. The bridge rejects obsolete results.
            self.signals.finished.emit(self.request.revision, None, str(error))
