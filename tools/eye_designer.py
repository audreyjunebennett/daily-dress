"""Small pixel editor for building reusable Daily Dress eye templates."""

from __future__ import annotations

import colorsys
import json
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import Callable

from PIL import Image, ImageTk

from skin_styler_core import (
    EYE_FEATURE_BOX,
    STANDARD_EYE_ANCHOR,
    FaceTemplate,
    RGBA,
    apply_face_template,
    detect_hair_mask,
    is_eye_feature_coordinate,
    make_face_template,
    normalize_skin,
    parse_hex_color,
    render_player_3d,
)

FACE_LEFT = 8
FACE_TOP = 8
FACE_SIZE = 8
CELL_SIZE = 42
DEFAULT_SKIN = (205, 145, 115)
DEFAULT_IRIS = "#2F9588"
DEFAULT_LASH = "#33242A"
DEFAULT_WHITE = "#F4F7F6"
_DEFAULT_IRIS_RGB = tuple(int(DEFAULT_IRIS[index : index + 2], 16) for index in (1, 3, 5))
_DEFAULT_IRIS_HUE, IRIS_LIGHTNESS, IRIS_SATURATION = colorsys.rgb_to_hls(
    *(_channel / 255 for _channel in _DEFAULT_IRIS_RGB)
)


def iris_color_from_targets(
    degrees: float,
    saturation_percent: float = IRIS_SATURATION * 100,
    lightness_percent: float = IRIS_LIGHTNESS * 100,
) -> tuple[int, int, int]:
    channels = colorsys.hls_to_rgb(
        (degrees % 360) / 360,
        min(1.0, max(0.0, lightness_percent / 100)),
        min(1.0, max(0.0, saturation_percent / 100)),
    )
    return tuple(round(channel * 255) for channel in channels)  # type: ignore[return-value]


def iris_color_from_hue(degrees: float) -> tuple[int, int, int]:
    """Backward-compatible hue-only helper used by older saved settings/tests."""

    return iris_color_from_targets(degrees)


def hue_from_hex(value: str) -> float:
    red, green, blue = parse_hex_color(value)
    hue, _saturation, _value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    return hue * 360


def targets_from_hex(value: str) -> tuple[float, float, float]:
    red, green, blue = parse_hex_color(value)
    hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
    return hue * 360, saturation * 100, lightness * 100


def _shade(color: tuple[int, int, int], factor: float) -> RGBA:
    return tuple(round(channel * factor) for channel in color) + (255,)  # type: ignore[return-value]


def _hex(color: tuple[int, int, int]) -> str:
    return f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"


def classify_reference_eye_features(
    features: dict[tuple[int, int], RGBA],
) -> tuple[
    set[tuple[int, int]],
    set[tuple[int, int]],
    set[tuple[int, int]],
    tuple[int, int, int],
    tuple[int, int, int],
    tuple[int, int, int],
]:
    """Separate a picked skin's exact eye pixels into iris, liner, and white."""

    iris_coordinates: set[tuple[int, int]] = set()
    liner_coordinates: set[tuple[int, int]] = set()
    white_coordinates: set[tuple[int, int]] = set()
    records: dict[tuple[int, int], tuple[float, float, float]] = {}
    for coordinate, color in features.items():
        hue, saturation, brightness = colorsys.rgb_to_hsv(*(channel / 255 for channel in color[:3]))
        records[coordinate] = (hue, saturation, brightness)
        x, _y = coordinate
        if x in (EYE_FEATURE_BOX[0], EYE_FEATURE_BOX[2] - 1) or brightness <= 0.24:
            liner_coordinates.add(coordinate)
        elif saturation <= 0.20 and brightness >= 0.55:
            white_coordinates.add(coordinate)
        else:
            iris_coordinates.add(coordinate)

    if not iris_coordinates:
        iris_coordinates = set(features) - liner_coordinates - white_coordinates
    if not iris_coordinates and white_coordinates:
        # Monochrome eyes still need something for the iris sliders to control.
        darkest_white = min(white_coordinates, key=lambda coordinate: records[coordinate][2])
        white_coordinates.remove(darkest_white)
        iris_coordinates.add(darkest_white)

    def representative(
        coordinates: set[tuple[int, int]],
        fallback: tuple[int, int, int],
        brightest: bool,
    ) -> tuple[int, int, int]:
        if not coordinates:
            return fallback
        coordinate = (max if brightest else min)(coordinates, key=lambda item: records[item][2])
        return features[coordinate][:3]

    iris = representative(iris_coordinates, _DEFAULT_IRIS_RGB, True)
    liner = representative(liner_coordinates, parse_hex_color(DEFAULT_LASH), False)
    white = representative(white_coordinates, parse_hex_color(DEFAULT_WHITE), True)
    return iris_coordinates, liner_coordinates, white_coordinates, iris, liner, white


def retarget_eye_pixel(
    color: RGBA,
    source_representative: tuple[int, int, int],
    target: tuple[int, int, int],
) -> RGBA:
    """Move one eye pixel with its palette while retaining its local shading."""

    old_hue, old_saturation, old_brightness = colorsys.rgb_to_hsv(*(channel / 255 for channel in color[:3]))
    source_hue, source_saturation, source_brightness = colorsys.rgb_to_hsv(
        *(channel / 255 for channel in source_representative)
    )
    target_hue, target_saturation, target_brightness = colorsys.rgb_to_hsv(
        *(channel / 255 for channel in target)
    )
    hue_shift = (target_hue - source_hue + 0.5) % 1.0 - 0.5
    new_hue = (old_hue + hue_shift) % 1.0 if target_saturation >= 0.02 else old_hue
    if source_saturation >= 0.03:
        new_saturation = min(1.0, old_saturation * target_saturation / source_saturation)
    else:
        new_saturation = target_saturation
    new_brightness = min(1.0, old_brightness * target_brightness / max(0.03, source_brightness))
    changed = colorsys.hsv_to_rgb(new_hue, new_saturation, new_brightness)
    return tuple(round(channel * 255) for channel in changed) + (color[3],)  # type: ignore[return-value]


def mirrored_eye_coordinate(coordinate: tuple[int, int]) -> tuple[int, int]:
    """Return the matching pixel on the other eye canvas."""

    return EYE_FEATURE_BOX[0] + EYE_FEATURE_BOX[2] - 1 - coordinate[0], coordinate[1]


def edit_eye_feature(
    features: dict[tuple[int, int], RGBA],
    iris_coordinates: set[tuple[int, int]],
    liner_coordinates: set[tuple[int, int]],
    white_coordinates: set[tuple[int, int]],
    coordinate: tuple[int, int],
    material: str,
    representatives: dict[str, tuple[int, int, int]],
) -> bool:
    """Assign or erase one editable eye pixel while retaining its material."""

    if not is_eye_feature_coordinate(*coordinate):
        return False
    material_sets = {
        "iris": iris_coordinates,
        "liner": liner_coordinates,
        "white": white_coordinates,
    }
    if material not in (*material_sets, "eraser"):
        return False
    for coordinates in material_sets.values():
        coordinates.discard(coordinate)
    if material == "eraser":
        features.pop(coordinate, None)
    else:
        material_sets[material].add(coordinate)
        features[coordinate] = representatives[material] + (255,)
    return True


def preset_eye_features(
    style: str,
    iris: tuple[int, int, int],
    lash: tuple[int, int, int],
    white: tuple[int, int, int],
) -> dict[tuple[int, int], RGBA]:
    """Build a preset on one stable baseline, with an optional lash row above."""

    iris_color = iris + (255,)
    lash_color = lash + (255,)
    white_color = white + (255,)
    iris_shadow = _shade(iris, 0.58)
    white_shadow = _shade(white, 0.82)

    if style == "Simple":
        return {(10, 14): iris_color, (13, 14): iris_color}
    if style == "Tall":
        return {
            (10, 13): lash_color,
            (13, 13): lash_color,
            (10, 14): iris_color,
            (13, 14): iris_color,
        }

    # Both shaded styles use the same two-row eyes as the user's reference:
    # darker white/iris above, full white/iris below, mirrored horizontally.
    features = {
        (9, 13): white_shadow,
        (10, 13): iris_shadow,
        (13, 13): iris_shadow,
        (14, 13): white_shadow,
        (9, 14): white_color,
        (10, 14): iris_color,
        (13, 14): iris_color,
        (14, 14): white_color,
    }
    if style == "Soft lashes":
        features.update({(8, 13): lash_color, (15, 13): lash_color})
    elif style == "Wide sparkle":
        features.update({(10, 12): white_color, (13, 12): white_color})
    return features


def write_eye_reference(path: Path, features: dict[tuple[int, int], RGBA], skin_color: tuple[int, int, int]) -> None:
    """Write a minimal skin PNG whose only non-skin face pixels are the designed eyes."""

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(FACE_TOP, FACE_TOP + FACE_SIZE):
        for x in range(FACE_LEFT, FACE_LEFT + FACE_SIZE):
            pixels[x, y] = skin_color + (255,)
    for coordinate, color in features.items():
        pixels[coordinate[0], coordinate[1]] = color
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False)


class EyeDesigner(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        initial_reference: Path | None,
        output_path: Path,
        choose: Callable[[Path], None],
        preview_skin: Path | None = None,
        eyes_over_bangs: bool = True,
        preserve_hat_layer_lashes: bool = True,
    ) -> None:
        super().__init__(parent)
        self.output_path = output_path
        self.choose = choose
        self.skin_color = DEFAULT_SKIN
        self.features: dict[tuple[int, int], RGBA] = {}
        self.reference_anchor_y = STANDARD_EYE_ANCHOR
        self._load_reference(initial_reference)
        self.preview_source = self._load_preview_skin(preview_skin or initial_reference)
        self.preview_eyes_over_bangs = eyes_over_bangs
        self.preview_preserve_hat_lashes = preserve_hat_layer_lashes
        self.preview_yaw = 25.0
        self.preview_drag_x: int | None = None
        self.preview_photo = None
        self.preview_resize_job: str | None = None
        is_saved_custom = bool(
            initial_reference
            and initial_reference.is_file()
            and initial_reference.resolve() == output_path.resolve()
        )
        settings = self._load_settings() if is_saved_custom else {}
        self.reference_source_features = dict(self.features)
        (
            self.reference_iris_coordinates,
            self.reference_liner_coordinates,
            self.reference_white_coordinates,
            inferred_iris,
            inferred_liner,
            inferred_white,
        ) = classify_reference_eye_features(self.reference_source_features)
        self.reference_shape = bool(self.reference_source_features)

        self.title("Design Daily Dress Eyes ✿")
        self.geometry("1060x700")
        self.minsize(930, 610)
        self.resizable(True, True)
        self.configure(background="#25272B")
        iris_value = str(settings.get("iris", _hex(inferred_iris) if self.reference_shape else DEFAULT_IRIS))
        self.iris_var = tk.StringVar(value=iris_value)
        self.lash_var = tk.StringVar(
            value=str(settings.get("lash", _hex(inferred_liner) if self.reference_shape else DEFAULT_LASH))
        )
        self.white_var = tk.StringVar(
            value=str(settings.get("white", _hex(inferred_white) if self.reference_shape else DEFAULT_WHITE))
        )
        self.reference_iris_color = inferred_iris
        self.reference_liner_color = inferred_liner
        self.reference_white_color = inferred_white
        default_hue, default_saturation, default_lightness = targets_from_hex(iris_value)
        hsl_settings = settings if settings.get("color_model") == "hsl" else {}
        self.hue_var = tk.DoubleVar(value=float(hsl_settings.get("hue", default_hue)))
        self.saturation_var = tk.DoubleVar(value=float(hsl_settings.get("saturation", default_saturation)))
        self.lightness_var = tk.DoubleVar(value=float(hsl_settings.get("lightness", default_lightness)))
        self.hue_text_var = tk.StringVar(value=f"{round(self.hue_var.get())}°")
        self.saturation_text_var = tk.StringVar(value=f"{round(self.saturation_var.get())}%")
        self.lightness_text_var = tk.StringVar(value=f"{round(self.lightness_var.get())}%")
        self.preset_var = tk.StringVar(value="Soft lashes")
        self.paint_material_var = tk.StringVar(value="liner")
        self.mirror_paint_var = tk.BooleanVar(value=True)
        self.show_outer_layers_var = tk.BooleanVar(value=True)
        self.preview_layer_text_var = tk.StringVar(value="base + outer layers")
        self.paint_help_var = tk.StringVar(value="Left-click paints · right-click erases")
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []
        self.active_stroke_snapshot: dict[str, object] | None = None
        self.active_stroke_changed = False

        self._restore_saved_materials(settings)

        self._build()
        self._apply_preset()
        self.bind("<Control-z>", self._undo)
        self.bind("<Control-y>", self._redo)
        self.bind("<Control-Shift-Z>", self._redo)
        self.transient(parent)
        self.grab_set()
        self.after(50, self.focus_force)

    def _load_reference(self, reference: Path | None) -> None:
        if reference is None or not reference.is_file():
            return
        try:
            with Image.open(reference) as image:
                template = make_face_template(image)
            self.skin_color = template.skin_color
            self.reference_anchor_y = template.anchor_y
            self.features = {
                coordinate: color
                for coordinate, color in template.features.items()
                if is_eye_feature_coordinate(*coordinate)
            }
        except Exception:
            self.skin_color = DEFAULT_SKIN
            self.features = {}

    @staticmethod
    def _load_preview_skin(path: Path | None) -> Image.Image | None:
        if path is None or not path.is_file():
            return None
        try:
            with Image.open(path) as image:
                normalized, _ = normalize_skin(image)
            return normalized
        except Exception:
            return None

    def _load_settings(self) -> dict[str, object]:
        settings_path = self.output_path.with_suffix(".json")
        if not settings_path.is_file():
            return {}
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _restore_saved_materials(self, settings: dict[str, object]) -> None:
        saved = settings.get("materials")
        if not isinstance(saved, dict):
            return
        restored = {"iris": set(), "liner": set(), "white": set()}
        for raw_coordinate, raw_material in saved.items():
            if not isinstance(raw_coordinate, str) or raw_material not in restored:
                continue
            try:
                x_text, y_text = raw_coordinate.split(",", 1)
                coordinate = (int(x_text), int(y_text))
            except (ValueError, TypeError):
                continue
            if coordinate in self.reference_source_features and is_eye_feature_coordinate(*coordinate):
                restored[str(raw_material)].add(coordinate)
        restored_coordinates = set().union(*restored.values())
        if restored_coordinates:
            self.reference_iris_coordinates = restored["iris"]
            self.reference_liner_coordinates = restored["liner"]
            self.reference_white_coordinates = restored["white"]

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, padding=(18, 15, 18, 10))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Design your eyes", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="The chosen gallery eyes load here with their exact shape. Adjust their reusable iris and eyeliner colors; the outlined boxes include side eyelashes.",
            wraplength=700,
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(self, padding=(18, 5, 18, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            body,
            width=FACE_SIZE * CELL_SIZE,
            height=FACE_SIZE * CELL_SIZE,
            background="#303238",
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, rowspan=20, sticky="n")
        self.canvas.configure(cursor="pencil")
        self.canvas.bind("<ButtonPress-1>", self._begin_paint_stroke)
        self.canvas.bind("<B1-Motion>", self._continue_paint_stroke)
        self.canvas.bind("<ButtonRelease-1>", self._finish_paint_stroke)
        self.canvas.bind("<ButtonPress-3>", lambda event: self._begin_paint_stroke(event, erase=True))
        self.canvas.bind("<B3-Motion>", lambda event: self._continue_paint_stroke(event, erase=True))
        self.canvas.bind("<ButtonRelease-3>", self._finish_paint_stroke)

        controls = ttk.Frame(body, padding=(18, 0, 0, 0))
        controls.grid(row=0, column=1, sticky="nsew")
        ttk.Label(
            controls,
            text="Selected eye shape" if self.reference_shape else "Shaded eyes + soft lashes",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            controls,
            text=(
                "Geometry and asymmetry come from the selected skin; its iris shading moves together."
                if self.reference_shape
                else "The darker upper iris suggests the pupil; the brighter lower iris catches the light."
            ),
            foreground="#777777",
            wraplength=260,
        ).pack(anchor="w", pady=(4, 8))

        ttk.Label(controls, text="Iris color", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 0))
        hue_header = ttk.Frame(controls)
        hue_header.pack(fill="x", pady=(5, 1))
        self.iris_swatch = tk.Label(hue_header, width=4, height=1, relief="solid", borderwidth=1)
        self.iris_swatch.pack(side="left", ipady=3)
        ttk.Label(hue_header, textvariable=self.hue_text_var).pack(side="right")
        self._history_slider(
            controls,
            from_=0,
            to=359,
            variable=self.hue_var,
            orient="horizontal",
            command=self._on_hue_change,
        ).pack(fill="x", pady=(2, 4))
        self._target_slider(controls, "Saturation", self.saturation_var, self.saturation_text_var, 0, 100)
        self._target_slider(controls, "Lightness", self.lightness_var, self.lightness_text_var, 5, 95)

        ttk.Label(controls, text="Separate liner color", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 0))
        self.lash_swatch = self._color_row(controls, "Eyeliner / lashes", self.lash_var)
        self.white_swatch = self._color_row(controls, "Eye white", self.white_var)
        ttk.Label(controls, text="Pixel editor", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(12, 2))
        paint_tools = ttk.Frame(controls)
        paint_tools.pack(fill="x")
        for label, value in (
            ("Iris", "iris"),
            ("Liner / lashes", "liner"),
            ("Eye white", "white"),
            ("Eraser", "eraser"),
        ):
            ttk.Radiobutton(
                paint_tools,
                text=label,
                value=value,
                variable=self.paint_material_var,
            ).pack(anchor="w")
        ttk.Checkbutton(
            paint_tools,
            text="Mirror edits to the other eye",
            variable=self.mirror_paint_var,
        ).pack(anchor="w", pady=(3, 0))
        history_buttons = ttk.Frame(paint_tools)
        history_buttons.pack(anchor="w", pady=(5, 1))
        ttk.Button(history_buttons, text="Undo (Ctrl+Z)", command=self._undo).pack(side="left")
        ttk.Button(history_buttons, text="Redo (Ctrl+Y)", command=self._redo).pack(side="left", padx=(5, 0))
        paint_status = ttk.Frame(paint_tools, width=270, height=38)
        paint_status.pack(fill="x", pady=(2, 0))
        paint_status.pack_propagate(False)
        ttk.Label(
            paint_status,
            textvariable=self.paint_help_var,
            foreground="#777777",
            wraplength=260,
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True)
        ttk.Label(
            controls,
            text="Pixel edits can mirror automatically. In the main window you can reveal the result over base-layer bangs and independently preserve lashes already painted on a skin’s hat layer.",
            foreground="#777777",
            wraplength=260,
        ).pack(anchor="w", pady=(12, 0))

        self._set_swatch(self.iris_swatch, self.iris_var.get())

        preview_frame = ttk.Frame(body, padding=(22, 0, 0, 0))
        preview_frame.grid(row=0, column=2, sticky="nsew")
        ttk.Label(preview_frame, text="Live layered preview", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            preview_frame,
            text="Drag the model left/right to inspect every angle.",
            foreground="#777777",
            wraplength=245,
        ).pack(anchor="w", pady=(3, 7))
        ttk.Checkbutton(
            preview_frame,
            text="Show outer layers (hat, jacket, sleeves, trousers)",
            variable=self.show_outer_layers_var,
            command=self._refresh_model_preview,
        ).pack(anchor="w", pady=(0, 7))
        self.model_canvas = tk.Canvas(
            preview_frame,
            width=250,
            height=350,
            background="#202124",
            highlightthickness=1,
            highlightbackground="#55575D",
            cursor="fleur",
        )
        self.model_canvas.pack(fill="both", expand=True)
        self.model_canvas.bind("<ButtonPress-1>", self._begin_preview_drag)
        self.model_canvas.bind("<B1-Motion>", self._drag_preview)
        self.model_canvas.bind("<Configure>", self._schedule_preview_refresh)

        footer = ttk.Frame(self, padding=(18, 0, 18, 16))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Use these eyes", command=self._save).pack(side="right", padx=(0, 8))

    def _target_slider(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.DoubleVar,
        text_variable: tk.StringVar,
        minimum: float,
        maximum: float,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=10).pack(side="left")
        self._history_slider(
            row,
            from_=minimum,
            to=maximum,
            variable=variable,
            orient="horizontal",
            command=self._on_iris_target_change,
        ).pack(side="left", fill="x", expand=True, padx=(4, 5))
        ttk.Label(row, textvariable=text_variable, width=5).pack(side="right")

    def _history_slider(self, parent: tk.Misc, **options) -> ttk.Scale:
        """Create a scale whose complete drag is one eye-design history step."""

        scale = ttk.Scale(parent, **options)
        scale.bind("<ButtonPress-1>", self._begin_slider_gesture)
        scale.bind("<ButtonRelease-1>", self._finish_paint_stroke)
        for key in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            scale.bind(f"<KeyPress-{key}>", self._begin_slider_gesture)
            scale.bind(f"<KeyRelease-{key}>", self._finish_paint_stroke)
        return scale

    def _color_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> tk.Label:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label).pack(side="left")
        swatch = tk.Label(row, width=3, height=1, relief="solid", borderwidth=1, cursor="hand2")
        swatch.pack(side="right", padx=(6, 0), ipady=2)
        swatch.bind("<Button-1>", lambda _event: self._choose_color(variable, swatch, label))
        ttk.Button(row, text="Choose…", command=lambda: self._choose_color(variable, swatch, label)).pack(side="right")
        self._set_swatch(swatch, variable.get())
        return swatch

    @staticmethod
    def _set_swatch(swatch: tk.Label, value: str) -> None:
        try:
            parse_hex_color(value)
            swatch.configure(background=value)
        except ValueError:
            swatch.configure(background="#777777")

    def _choose_color(self, variable: tk.StringVar, swatch: tk.Label, label: str) -> None:
        chosen = colorchooser.askcolor(color=variable.get(), title=f"Choose {label.casefold()} color", parent=self)[1]
        if chosen:
            variable.set(chosen.upper())
            self._set_swatch(swatch, chosen)
            self._apply_preset()

    def _on_hue_change(self, value: str) -> None:
        self.hue_var.set(float(value))
        self._on_iris_target_change()

    def _on_iris_target_change(self, _value: str | None = None) -> None:
        degrees = float(self.hue_var.get())
        saturation = float(self.saturation_var.get())
        lightness = float(self.lightness_var.get())
        red, green, blue = iris_color_from_targets(degrees, saturation, lightness)
        color = f"#{red:02X}{green:02X}{blue:02X}"
        self.iris_var.set(color)
        self.hue_text_var.set(f"{round(degrees)}°")
        self.saturation_text_var.set(f"{round(saturation)}%")
        self.lightness_text_var.set(f"{round(lightness)}%")
        if hasattr(self, "iris_swatch"):
            self._set_swatch(self.iris_swatch, color)
            self._apply_preset()
        if self.active_stroke_snapshot is not None:
            self.active_stroke_changed = True

    @staticmethod
    def _editable(x: int, y: int) -> bool:
        return is_eye_feature_coordinate(x, y)

    def _apply_preset(self) -> None:
        try:
            iris = parse_hex_color(self.iris_var.get()) + (255,)
            lash = parse_hex_color(self.lash_var.get()) + (255,)
            white = parse_hex_color(self.white_var.get()) + (255,)
        except ValueError as exception:
            messagebox.showerror("Invalid eye color", str(exception), parent=self)
            return
        if self.reference_shape:
            self.features = dict(self.reference_source_features)
            for coordinate in self.reference_iris_coordinates:
                self.features[coordinate] = retarget_eye_pixel(
                    self.reference_source_features[coordinate],
                    self.reference_iris_color,
                    iris[:3],
                )
            for coordinate in self.reference_liner_coordinates:
                self.features[coordinate] = retarget_eye_pixel(
                    self.reference_source_features[coordinate],
                    self.reference_liner_color,
                    lash[:3],
                )
            for coordinate in self.reference_white_coordinates:
                self.features[coordinate] = retarget_eye_pixel(
                    self.reference_source_features[coordinate],
                    self.reference_white_color,
                    white[:3],
                )
            self._redraw()
            return
        left, top, right, bottom = EYE_FEATURE_BOX
        for y in range(top, bottom):
            for x in range(left, right):
                self.features.pop((x, y), None)

        self.features.update(
            preset_eye_features(
                self.preset_var.get(),
                iris[:3],
                lash[:3],
                white[:3],
            )
        )
        self._redraw()

    def _freeze_current_design(self) -> None:
        """Turn the generated default into an editable reference palette."""

        if self.reference_shape:
            return
        self.reference_source_features = dict(self.features)
        (
            self.reference_iris_coordinates,
            self.reference_liner_coordinates,
            self.reference_white_coordinates,
            self.reference_iris_color,
            self.reference_liner_color,
            self.reference_white_color,
        ) = classify_reference_eye_features(self.reference_source_features)
        self.reference_shape = True

    def _capture_edit_state(self) -> dict[str, object]:
        return {
            "features": dict(self.features),
            "source": dict(self.reference_source_features),
            "iris": set(self.reference_iris_coordinates),
            "liner": set(self.reference_liner_coordinates),
            "white": set(self.reference_white_coordinates),
            "reference_shape": self.reference_shape,
            "iris_color": self.reference_iris_color,
            "liner_color": self.reference_liner_color,
            "white_color": self.reference_white_color,
            "hue_target": float(self.hue_var.get()),
            "saturation_target": float(self.saturation_var.get()),
            "lightness_target": float(self.lightness_var.get()),
            "iris_target": self.iris_var.get(),
            "lash_target": self.lash_var.get(),
            "white_target": self.white_var.get(),
        }

    def _restore_edit_state(self, state: dict[str, object]) -> None:
        self.features = dict(state["features"])  # type: ignore[arg-type]
        self.reference_source_features = dict(state["source"])  # type: ignore[arg-type]
        self.reference_iris_coordinates = set(state["iris"])  # type: ignore[arg-type]
        self.reference_liner_coordinates = set(state["liner"])  # type: ignore[arg-type]
        self.reference_white_coordinates = set(state["white"])  # type: ignore[arg-type]
        self.reference_shape = bool(state["reference_shape"])
        self.reference_iris_color = state["iris_color"]  # type: ignore[assignment]
        self.reference_liner_color = state["liner_color"]  # type: ignore[assignment]
        self.reference_white_color = state["white_color"]  # type: ignore[assignment]
        self.hue_var.set(float(state["hue_target"]))
        self.saturation_var.set(float(state["saturation_target"]))
        self.lightness_var.set(float(state["lightness_target"]))
        self.iris_var.set(str(state["iris_target"]))
        self.lash_var.set(str(state["lash_target"]))
        self.white_var.set(str(state["white_target"]))
        self.hue_text_var.set(f"{round(self.hue_var.get())}°")
        self.saturation_text_var.set(f"{round(self.saturation_var.get())}%")
        self.lightness_text_var.set(f"{round(self.lightness_var.get())}%")
        if hasattr(self, "iris_swatch"):
            self._set_swatch(self.iris_swatch, self.iris_var.get())
            self._set_swatch(self.lash_swatch, self.lash_var.get())
            self._set_swatch(self.white_swatch, self.white_var.get())
        self._redraw()

    def _begin_slider_gesture(self, _event: tk.Event | None = None) -> None:
        if self.active_stroke_snapshot is not None:
            self._finish_paint_stroke()
        self.active_stroke_snapshot = self._capture_edit_state()
        self.active_stroke_changed = False

    def _begin_paint_stroke(self, event: tk.Event, erase: bool = False) -> None:
        if self.active_stroke_snapshot is not None:
            self._finish_paint_stroke()
        self.active_stroke_snapshot = self._capture_edit_state()
        self.active_stroke_changed = False
        self._paint_canvas(event, erase)

    def _continue_paint_stroke(self, event: tk.Event, erase: bool = False) -> None:
        if self.active_stroke_snapshot is None:
            self._begin_paint_stroke(event, erase)
            return
        self._paint_canvas(event, erase)

    def _finish_paint_stroke(self, _event: tk.Event | None = None) -> None:
        if self.active_stroke_snapshot is None:
            return
        if self.active_stroke_changed:
            self.undo_stack.append(self.active_stroke_snapshot)
            if len(self.undo_stack) > 100:
                del self.undo_stack[0]
            self.redo_stack.clear()
        self.active_stroke_snapshot = None
        self.active_stroke_changed = False

    def _undo(self, _event: tk.Event | None = None) -> str:
        self._finish_paint_stroke()
        if not self.undo_stack:
            self.paint_help_var.set("Nothing to undo yet")
            return "break"
        self.redo_stack.append(self._capture_edit_state())
        state = self.undo_stack.pop()
        self._restore_edit_state(state)
        self.paint_help_var.set("Undid the last eye edit · Ctrl+Z again for the previous one")
        return "break"

    def _redo(self, _event: tk.Event | None = None) -> str:
        self._finish_paint_stroke()
        if not self.redo_stack:
            self.paint_help_var.set("Nothing to redo yet")
            return "break"
        self.undo_stack.append(self._capture_edit_state())
        if len(self.undo_stack) > 100:
            del self.undo_stack[0]
        state = self.redo_stack.pop()
        self._restore_edit_state(state)
        self.paint_help_var.set("Redid the eye edit · Ctrl+Y again for the next one")
        return "break"

    def _paint_canvas(self, event: tk.Event, erase: bool = False) -> None:
        local_x = int(event.x) // CELL_SIZE
        local_y = int(event.y) // CELL_SIZE
        if not (0 <= local_x < FACE_SIZE and 0 <= local_y < FACE_SIZE):
            return
        coordinate = (FACE_LEFT + local_x, FACE_TOP + local_y)
        if not self._editable(*coordinate):
            self.paint_help_var.set("Only the two outlined eye boxes are editable")
            return
        self._freeze_current_design()
        material = "eraser" if erase else self.paint_material_var.get()
        representatives = {
            "iris": self.reference_iris_color,
            "liner": self.reference_liner_color,
            "white": self.reference_white_color,
        }
        targets = [coordinate]
        if self.mirror_paint_var.get():
            mirrored = mirrored_eye_coordinate(coordinate)
            if mirrored != coordinate:
                targets.append(mirrored)
        changed = False
        for target in targets:
            before = (
                self.reference_source_features.get(target),
                target in self.reference_iris_coordinates,
                target in self.reference_liner_coordinates,
                target in self.reference_white_coordinates,
            )
            edit_eye_feature(
                self.reference_source_features,
                self.reference_iris_coordinates,
                self.reference_liner_coordinates,
                self.reference_white_coordinates,
                target,
                material,
                representatives,
            )
            after = (
                self.reference_source_features.get(target),
                target in self.reference_iris_coordinates,
                target in self.reference_liner_coordinates,
                target in self.reference_white_coordinates,
            )
            changed = changed or before != after
        if changed:
            self.active_stroke_changed = True
            action = "Erased" if material == "eraser" else f"Painted {material.replace('liner', 'liner / lashes')}"
            mirror_note = " on both eyes" if self.mirror_paint_var.get() else ""
            self.paint_help_var.set(f"{action}{mirror_note} · right-click erases")
            self._apply_preset()

    def _redraw(self) -> None:
        self.canvas.delete("all")
        _left, top, _right, bottom = EYE_FEATURE_BOX
        for local_y in range(FACE_SIZE):
            for local_x in range(FACE_SIZE):
                x = FACE_LEFT + local_x
                y = FACE_TOP + local_y
                color = self.features.get((x, y), self.skin_color + (255,))
                fill = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
                x1 = local_x * CELL_SIZE
                y1 = local_y * CELL_SIZE
                editable = self._editable(x, y)
                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + CELL_SIZE,
                    y1 + CELL_SIZE,
                    fill=fill,
                    outline="#73546A" if editable else "#A98472",
                    width=2 if editable else 1,
                )
        for left, right in ((8, 11), (13, 16)):
            self.canvas.create_rectangle(
                (left - FACE_LEFT) * CELL_SIZE,
                (top - FACE_TOP) * CELL_SIZE,
                (right - FACE_LEFT) * CELL_SIZE,
                (bottom - FACE_TOP) * CELL_SIZE,
                outline="#F3C6DC",
                width=4,
            )
        self._refresh_model_preview()

    def _preview_with_designed_eyes(self) -> Image.Image | None:
        if self.preview_source is None:
            return None
        hair_mask = detect_hair_mask(self.preview_source, 42)
        template = FaceTemplate(
            features=dict(self.features),
            skin_color=self.skin_color,
            anchor_y=self.reference_anchor_y,
        )
        return apply_face_template(
            self.preview_source,
            self.preview_source,
            template,
            hair_mask,
            eyes_over_bangs=self.preview_eyes_over_bangs,
            preserve_hat_layer_lashes=self.preview_preserve_hat_lashes,
        )

    def _refresh_model_preview(self) -> None:
        if not hasattr(self, "model_canvas"):
            return
        self.model_canvas.delete("all")
        canvas_width = max(200, self.model_canvas.winfo_width())
        canvas_height = max(260, self.model_canvas.winfo_height())
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        preview_skin = self._preview_with_designed_eyes()
        if preview_skin is None:
            self.model_canvas.create_text(
                center_x,
                center_y,
                text="Choose gallery eyes to load\na full layered skin preview.",
                fill="#B9BBC2",
                justify="center",
                font=("Segoe UI", 10),
            )
            return
        render_scale = max(4, min(16, round(min(canvas_width / 19, (canvas_height - 48) / 34))))
        show_outer_layers = self.show_outer_layers_var.get()
        self.preview_layer_text_var.set("base + outer layers" if show_outer_layers else "base layer only")
        model = render_player_3d(
            preview_skin,
            render_scale,
            yaw_degrees=self.preview_yaw,
            show_outer_layers=show_outer_layers,
        )
        self.preview_photo = ImageTk.PhotoImage(model)
        self.model_canvas.create_image(center_x, center_y - 8, image=self.preview_photo, anchor="center")
        self.model_canvas.create_text(
            center_x,
            canvas_height - 18,
            text=f"{round(self.preview_yaw) % 360}° · {self.preview_layer_text_var.get()}",
            fill="#B9BBC2",
            font=("Segoe UI", 9),
        )

    def _schedule_preview_refresh(self, _event: tk.Event | None = None) -> None:
        if self.preview_resize_job is not None:
            self.after_cancel(self.preview_resize_job)
        self.preview_resize_job = self.after(80, self._finish_preview_resize)

    def _finish_preview_resize(self) -> None:
        self.preview_resize_job = None
        self._refresh_model_preview()

    def _begin_preview_drag(self, event: tk.Event) -> None:
        self.preview_drag_x = int(event.x)

    def _drag_preview(self, event: tk.Event) -> None:
        current_x = int(event.x)
        if self.preview_drag_x is None:
            self.preview_drag_x = current_x
            return
        delta = current_x - self.preview_drag_x
        if abs(delta) < 4:
            return
        self.preview_yaw = (self.preview_yaw + delta * 1.8) % 360
        self.preview_drag_x = current_x
        self._refresh_model_preview()

    def _save(self) -> None:
        if not self.features:
            messagebox.showerror("No eyes designed", "Paint at least one eye pixel first.", parent=self)
            return
        try:
            materials = {
                f"{x},{y}": material
                for material, coordinates in (
                    ("iris", self.reference_iris_coordinates),
                    ("liner", self.reference_liner_coordinates),
                    ("white", self.reference_white_coordinates),
                )
                for x, y in sorted(coordinates)
                if (x, y) in self.features
            }
            write_eye_reference(self.output_path, self.features, self.skin_color)
            self.output_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "preset": "Soft lashes",
                        "color_model": "hsl",
                        "hue": round(self.hue_var.get(), 2),
                        "saturation": round(self.saturation_var.get(), 2),
                        "lightness": round(self.lightness_var.get(), 2),
                        "iris": self.iris_var.get(),
                        "lash": self.lash_var.get(),
                        "white": self.white_var.get(),
                        "materials": materials,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exception:
            messagebox.showerror("Could not save eye design", str(exception), parent=self)
            return
        self.choose(self.output_path)
        self.destroy()
