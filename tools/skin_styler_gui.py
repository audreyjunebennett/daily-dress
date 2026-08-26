"""Friendly Tk GUI for the Daily Dress skin styling engine."""

from __future__ import annotations

import colorsys
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from face_picker import FacePicker
from eye_designer import EyeDesigner
from skin_styler_core import (
    generate_folder,
    install_generated_wardrobe,
    make_face_template,
    normalize_skin,
    parse_hex_color,
    render_front_face,
    render_player_3d,
    render_player_view,
    style_skin,
)
from wardrobe_picker import WardrobePicker


DEFAULT_HAIR_HUE_COLOR = "#9C5FA8"
DEFAULT_OUTFIT_COLOR = "#6F86C9"
DEFAULT_ACCESSORY_COLOR = "#D86AA5"
_DEFAULT_HAIR_RGB = tuple(int(DEFAULT_HAIR_HUE_COLOR[index : index + 2], 16) for index in (1, 3, 5))
_DEFAULT_HAIR_HUE, HAIR_SWATCH_SATURATION, HAIR_SWATCH_VALUE = colorsys.rgb_to_hsv(
    *(_channel / 255 for _channel in _DEFAULT_HAIR_RGB)
)


def hair_color_from_targets(
    degrees: float,
    saturation_percent: float,
    lightness_percent: float,
) -> tuple[int, int, int]:
    channels = colorsys.hsv_to_rgb(
        (degrees % 360) / 360,
        min(1.0, max(0.0, saturation_percent / 100)),
        min(1.0, max(0.0, lightness_percent / 100)),
    )
    return tuple(round(channel * 255) for channel in channels)  # type: ignore[return-value]


def hair_color_from_hue(degrees: float) -> tuple[int, int, int]:
    return hair_color_from_targets(degrees, HAIR_SWATCH_SATURATION * 100, HAIR_SWATCH_VALUE * 100)


def hue_from_color(value: str) -> float:
    red, green, blue = parse_hex_color(value)
    hue, _saturation, _brightness = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    return hue * 360


def hair_targets_from_color(value: str) -> tuple[float, float, float]:
    red, green, blue = parse_hex_color(value)
    hue, saturation, lightness = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    return hue * 360, saturation * 100, lightness * 100


def _find_modrinth_profile() -> Path | None:
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / "mods").is_dir() and (parent / "config" / "daily-dress").is_dir():
            return parent

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    profiles = Path(appdata) / "ModrinthApp" / "profiles"
    preferred = profiles / "Taylors Version"
    candidates = [preferred] if preferred.is_dir() else []
    if profiles.is_dir():
        candidates.extend(path for path in profiles.iterdir() if path.is_dir() and path != preferred)
    for candidate in candidates:
        if (candidate / "config" / "daily-dress").is_dir() and list((candidate / "mods").glob("daily-dress*.jar")):
            return candidate
    return None


class SkinStylerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Daily Dress Skin Styler ✿")
        self.geometry("1040x950")
        self.minsize(940, 860)

        pictures = Path.home() / "Pictures"
        profile = _find_modrinth_profile()
        self.sync_outbox = profile / "config" / "daily-dress" / "sync-outbox" if profile else None
        self.input_var = tk.StringVar(value=str(pictures / "Skins"))
        self.output_var = tk.StringVar(value=str(pictures / "Skins - Daily Dress Styled"))
        self.custom_eye_reference = Path(__file__).resolve().with_name("custom-eye-reference.png")
        self.reference_var = tk.StringVar(
            value=str(self.custom_eye_reference) if self.custom_eye_reference.is_file() else ""
        )
        self.hair_var = tk.StringVar(value=DEFAULT_HAIR_HUE_COLOR)
        self.hair_hue_var = tk.DoubleVar(value=hue_from_color(DEFAULT_HAIR_HUE_COLOR))
        self.hair_hue_text_var = tk.StringVar(value=f"{round(self.hair_hue_var.get())}°")
        self.hair_saturation_var = tk.DoubleVar(value=HAIR_SWATCH_SATURATION * 100)
        self.hair_saturation_text_var = tk.StringVar(value=f"{round(self.hair_saturation_var.get())}%")
        self.hair_lightness_var = tk.DoubleVar(value=HAIR_SWATCH_VALUE * 100)
        self.hair_lightness_text_var = tk.StringVar(value=f"{round(self.hair_lightness_var.get())}%")
        self.hair_sample_var = tk.StringVar(value="finding a sample…")
        self.tolerance_var = tk.DoubleVar(value=42)
        self.tolerance_text_var = tk.StringVar(value="42")
        self.body_hair_var = tk.BooleanVar(value=True)
        self.skin_enabled_var = tk.BooleanVar(value=False)
        self.skin_var = tk.StringVar(value="#C58C70")
        self.skin_tolerance_var = tk.DoubleVar(value=24)
        self.skin_tolerance_text_var = tk.StringVar(value="24")
        outfit_hue, outfit_saturation, outfit_brightness = hair_targets_from_color(DEFAULT_OUTFIT_COLOR)
        self.outfit_enabled_var = tk.BooleanVar(value=False)
        self.outfit_var = tk.StringVar(value=DEFAULT_OUTFIT_COLOR)
        self.outfit_hue_var = tk.DoubleVar(value=outfit_hue)
        self.outfit_saturation_var = tk.DoubleVar(value=outfit_saturation)
        self.outfit_brightness_var = tk.DoubleVar(value=outfit_brightness)
        self.outfit_hue_text_var = tk.StringVar(value=f"{round(outfit_hue)}°")
        self.outfit_saturation_text_var = tk.StringVar(value=f"{round(outfit_saturation)}%")
        self.outfit_brightness_text_var = tk.StringVar(value=f"{round(outfit_brightness)}%")
        accessory_hue, accessory_saturation, accessory_brightness = hair_targets_from_color(DEFAULT_ACCESSORY_COLOR)
        self.accessory_enabled_var = tk.BooleanVar(value=False)
        self.accessory_var = tk.StringVar(value=DEFAULT_ACCESSORY_COLOR)
        self.accessory_hue_var = tk.DoubleVar(value=accessory_hue)
        self.accessory_saturation_var = tk.DoubleVar(value=accessory_saturation)
        self.accessory_brightness_var = tk.DoubleVar(value=accessory_brightness)
        self.accessory_hue_text_var = tk.StringVar(value=f"{round(accessory_hue)}°")
        self.accessory_saturation_text_var = tk.StringVar(value=f"{round(accessory_saturation)}%")
        self.accessory_brightness_text_var = tk.StringVar(value=f"{round(accessory_brightness)}%")
        self.face_var = tk.BooleanVar(value=True)
        self.eyes_over_bangs_var = tk.BooleanVar(value=True)
        self.preserve_hat_lashes_var = tk.BooleanVar(value=True)
        self.sync_var = tk.BooleanVar(value=self.sync_outbox is not None)
        self.status_var = tk.StringVar(value="Choose reference eyes and the target hair color you want.")
        self._reference_preview_image: ImageTk.PhotoImage | None = None
        self._hair_preview_image: ImageTk.PhotoImage | None = None
        self._hair_sample_path: Path | None = None
        self._hair_sample_image: Image.Image | None = None
        self._preview_yaw = 25.0
        self._preview_drag_x: int | None = None
        self._slider_undo_stack: list[dict[str, float]] = []
        self._slider_redo_stack: list[dict[str, float]] = []
        self._active_slider_snapshot: dict[str, float] | None = None

        self._build()
        self.bind("<Control-z>", self._undo_sliders)
        self.bind("<Control-y>", self._redo_sliders)
        self.bind("<Control-Shift-Z>", self._redo_sliders)
        self.hair_var.trace_add("write", self._refresh_color_swatches)
        self.skin_var.trace_add("write", self._refresh_color_swatches)
        self.skin_var.trace_add("write", self._refresh_hair_preview)
        self.tolerance_var.trace_add("write", self._refresh_tolerance_labels)
        self.skin_tolerance_var.trace_add("write", self._refresh_tolerance_labels)
        self.reference_var.trace_add("write", self._refresh_reference_preview)
        self.input_var.trace_add("write", self._source_wardrobe_changed)
        self.face_var.trace_add("write", self._refresh_hair_preview)
        self.eyes_over_bangs_var.trace_add("write", self._refresh_hair_preview)
        self.preserve_hat_lashes_var.trace_add("write", self._refresh_hair_preview)
        self.skin_enabled_var.trace_add("write", self._refresh_hair_preview)
        self.body_hair_var.trace_add("write", self._refresh_hair_preview)
        self.outfit_enabled_var.trace_add("write", self._refresh_hair_preview)
        self.accessory_enabled_var.trace_add("write", self._refresh_hair_preview)
        self._refresh_color_swatches()
        self._refresh_tolerance_labels()
        self._refresh_reference_preview()
        self._refresh_hair_preview()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Daily Dress Skin Styler", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            frame,
            text="Moves each hairstyle toward one chosen hue, saturation, and lightness while preserving its shading and accent relationships. Designed eyes can be reused across the wardrobe, with a choice to reveal them over bangs. Originals are never changed.",
            wraplength=750,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        self._path_row(frame, 2, "Source wardrobe", self.input_var, self._choose_input, folder=True)
        ttk.Label(frame, text="Reference eyes").grid(row=3, column=0, sticky="w", pady=5)
        reference_frame = ttk.Frame(frame)
        reference_frame.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Entry(reference_frame, textvariable=self.reference_var).grid(row=0, column=0, sticky="ew", padx=(8, 8))
        ttk.Button(reference_frame, text="Eye gallery…", command=self._open_face_picker).grid(row=0, column=1, sticky="ew", padx=(0, 7))
        ttk.Button(reference_frame, text="Browse…", command=self._choose_reference).grid(row=0, column=2, sticky="ew", padx=(0, 10))
        ttk.Label(reference_frame, text="Full face is context; only eye pixels are copied.", foreground="#777777").grid(row=1, column=0, sticky="w", padx=(8, 8), pady=(3, 0))
        ttk.Button(reference_frame, text="Design eyes…", command=self._open_eye_designer).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=(3, 0))
        preview_box = tk.Frame(reference_frame, width=66, height=66, background="#2B2B2B", relief="solid", borderwidth=1)
        preview_box.grid(row=0, column=3, rowspan=2, sticky="e")
        preview_box.grid_propagate(False)
        self.reference_preview = tk.Label(
            preview_box,
            text="eye\npreview",
            compound="center",
            background="#2B2B2B",
            foreground="#DDDDDD",
        )
        self.reference_preview.pack(fill="both", expand=True)
        reference_frame.columnconfigure(0, weight=1)
        self._path_row(frame, 4, "New output folder", self.output_var, self._choose_output, folder=True)

        ttk.Label(frame, text="Target hair color").grid(row=5, column=0, sticky="nw", pady=(18, 4))
        color_frame = ttk.Frame(frame)
        color_frame.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(14, 4))
        self.hair_swatch = tk.Label(color_frame, width=4, height=1, relief="solid", borderwidth=1, cursor="hand2")
        self.hair_swatch.grid(row=0, column=0, rowspan=3, padx=(0, 10), ipady=9)
        self.hair_swatch.bind("<Button-1>", lambda _event: self._choose_color())
        ttk.Label(color_frame, text="Hue", width=10).grid(row=0, column=1, sticky="w")
        self._history_scale(
            color_frame,
            from_=0,
            to=359,
            variable=self.hair_hue_var,
            orient="horizontal",
            command=self._on_hair_target_change,
        ).grid(row=0, column=2, sticky="ew")
        ttk.Label(color_frame, textvariable=self.hair_hue_text_var, width=5).grid(row=0, column=3, padx=(6, 2))
        ttk.Button(color_frame, text="Choose…", command=self._choose_color).grid(row=0, column=4, padx=(3, 9))

        ttk.Label(color_frame, text="Saturation", width=10).grid(row=1, column=1, sticky="w")
        self._history_scale(
            color_frame,
            from_=0,
            to=100,
            variable=self.hair_saturation_var,
            orient="horizontal",
            command=self._on_hair_target_change,
        ).grid(row=1, column=2, sticky="ew")
        ttk.Label(color_frame, textvariable=self.hair_saturation_text_var, width=5).grid(row=1, column=3, padx=(6, 2))

        ttk.Label(color_frame, text="Lightness", width=10).grid(row=2, column=1, sticky="w")
        self._history_scale(
            color_frame,
            from_=12,
            to=100,
            variable=self.hair_lightness_var,
            orient="horizontal",
            command=self._on_hair_target_change,
        ).grid(row=2, column=2, sticky="ew")
        ttk.Label(color_frame, textvariable=self.hair_lightness_text_var, width=5).grid(row=2, column=3, padx=(6, 2))

        hair_preview_box = tk.Frame(color_frame, width=158, height=118, background="#2B2B2B", relief="solid", borderwidth=1)
        hair_preview_box.grid(row=0, column=5, rowspan=5, sticky="e")
        hair_preview_box.grid_propagate(False)
        self.hair_preview = tk.Label(
            hair_preview_box,
            text="hair preview",
            background="#2B2B2B",
            foreground="#DDDDDD",
            cursor="fleur",
        )
        self.hair_preview.pack(fill="both", expand=True)
        self.hair_preview.bind("<ButtonPress-1>", self._begin_live_preview_drag)
        self.hair_preview.bind("<B1-Motion>", self._drag_live_preview)
        ttk.Button(color_frame, text="Sample…", command=self._choose_hair_sample).grid(row=0, column=6, padx=(7, 0))
        ttk.Label(
            color_frame,
            text="live whole-skin original → styled · drag the models left/right to rotate",
            foreground="#777777",
        ).grid(row=3, column=1, columnspan=4, sticky="w", pady=(3, 0))
        ttk.Checkbutton(
            color_frame,
            text="Continue long hair down the torso/shoulders",
            variable=self.body_hair_var,
        ).grid(row=4, column=1, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(color_frame, textvariable=self.hair_sample_var, foreground="#777777", width=16).grid(
            row=1, column=6, rowspan=2, sticky="w", padx=(7, 0)
        )
        color_frame.columnconfigure(2, weight=1)

        ttk.Label(frame, text="Hair detection tolerance").grid(row=6, column=0, sticky="w", pady=8)
        self._history_scale(frame, from_=18, to=85, variable=self.tolerance_var, orient="horizontal").grid(row=6, column=1, sticky="ew", pady=8)
        hair_tolerance_controls = ttk.Frame(frame)
        hair_tolerance_controls.grid(row=6, column=2, sticky="w")
        ttk.Label(hair_tolerance_controls, textvariable=self.tolerance_text_var, width=3).pack(side="left")
        ttk.Button(hair_tolerance_controls, text="Reset to 42", command=self._reset_hair_tolerance).pack(side="left", padx=(4, 0))

        eye_options = ttk.Frame(frame)
        eye_options.grid(row=7, column=1, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Checkbutton(eye_options, text="Match eyes from the reference skin", variable=self.face_var).pack(side="left")
        ttk.Checkbutton(
            eye_options,
            text="Show eyes / eyeliner over bangs (base face layer only)",
            variable=self.eyes_over_bangs_var,
        ).pack(side="left", padx=(18, 0))
        ttk.Checkbutton(
            eye_options,
            text="Keep existing 3D hat-layer lashes",
            variable=self.preserve_hat_lashes_var,
        ).pack(side="left", padx=(18, 0))

        ttk.Checkbutton(frame, text="Adjust exposed skin tone too", variable=self.skin_enabled_var).grid(row=8, column=0, sticky="w", pady=(8, 2))
        skin_frame = ttk.Frame(frame)
        skin_frame.grid(row=8, column=1, columnspan=2, sticky="ew", pady=(8, 2))
        self.skin_swatch = tk.Label(skin_frame, width=4, height=1, relief="solid", borderwidth=1, cursor="hand2")
        self.skin_swatch.pack(side="left", padx=(0, 8), ipady=3)
        self.skin_swatch.bind("<Button-1>", lambda _event: self._choose_skin_color())
        ttk.Entry(skin_frame, textvariable=self.skin_var, width=14).pack(side="left")
        ttk.Button(skin_frame, text="Choose skin tone…", command=self._choose_skin_color).pack(side="left", padx=8)

        ttk.Label(frame, text="Skin detection tolerance").grid(row=9, column=0, sticky="w", pady=8)
        self._history_scale(frame, from_=10, to=46, variable=self.skin_tolerance_var, orient="horizontal").grid(row=9, column=1, sticky="ew", pady=8)
        skin_tolerance_controls = ttk.Frame(frame)
        skin_tolerance_controls.grid(row=9, column=2, sticky="w")
        ttk.Label(skin_tolerance_controls, textvariable=self.skin_tolerance_text_var, width=3).pack(side="left")
        ttk.Button(skin_tolerance_controls, text="Reset to 24", command=self._reset_skin_tolerance).pack(side="left", padx=(4, 0))

        palette_frame = ttk.LabelFrame(frame, text="Optional outfit + hair-accessory palettes", padding=8)
        palette_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(12, 2))

        def palette_row(
            row: int,
            title: str,
            enabled_var: tk.BooleanVar,
            hue_var: tk.DoubleVar,
            saturation_var: tk.DoubleVar,
            brightness_var: tk.DoubleVar,
            hue_text_var: tk.StringVar,
            saturation_text_var: tk.StringVar,
            brightness_text_var: tk.StringVar,
            group: str,
        ) -> tk.Label:
            ttk.Checkbutton(palette_frame, text=title, variable=enabled_var).grid(row=row, column=0, sticky="w", padx=(0, 8))
            swatch = tk.Label(palette_frame, width=3, height=1, relief="solid", borderwidth=1)
            swatch.grid(row=row, column=1, padx=(0, 10), ipady=3)
            controls = (
                ("Hue", hue_var, 0, 359, hue_text_var),
                ("Sat", saturation_var, 0, 100, saturation_text_var),
                ("Brightness", brightness_var, 12, 100, brightness_text_var),
            )
            for index, (label, variable, start, end, text_var) in enumerate(controls):
                control = ttk.Frame(palette_frame)
                control.grid(row=row, column=index + 2, sticky="ew", padx=(0, 8))
                ttk.Label(control, text=label).pack(side="left")
                self._history_scale(
                    control,
                    from_=start,
                    to=end,
                    variable=variable,
                    orient="horizontal",
                    length=105,
                    command=lambda _value, name=group: self._on_palette_target_change(name),
                ).pack(side="left", padx=(5, 3))
                ttk.Label(control, textvariable=text_var, width=5).pack(side="left")
            return swatch

        self.outfit_swatch = palette_row(
            0,
            "Adjust outfit",
            self.outfit_enabled_var,
            self.outfit_hue_var,
            self.outfit_saturation_var,
            self.outfit_brightness_var,
            self.outfit_hue_text_var,
            self.outfit_saturation_text_var,
            self.outfit_brightness_text_var,
            "outfit",
        )
        self.accessory_swatch = palette_row(
            1,
            "Adjust hair accessories",
            self.accessory_enabled_var,
            self.accessory_hue_var,
            self.accessory_saturation_var,
            self.accessory_brightness_var,
            self.accessory_hue_text_var,
            self.accessory_saturation_text_var,
            self.accessory_brightness_text_var,
            "accessory",
        )
        for column in range(2, 5):
            palette_frame.columnconfigure(column, weight=1)

        install_frame = ttk.LabelFrame(frame, text="Automatic personal wardrobe sync — no copying needed", padding=10)
        install_frame.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(14, 2))
        self.sync_check = ttk.Checkbutton(
            install_frame,
            text="Prepare this wardrobe for my Minecraft account",
            variable=self.sync_var,
            state="normal" if self.sync_outbox is not None else "disabled",
        )
        self.sync_check.grid(row=0, column=0, sticky="w")
        ttk.Label(
            install_frame,
            text=str(self.sync_outbox) if self.sync_outbox else "A Daily Dress Modrinth instance was not found",
            foreground="#777777",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(
            install_frame,
            text=(
                "The Styler prepares a local outbox. When you join Roses, Daily Dress securely sends it as the personal wardrobe "
                "for the Minecraft account you joined with. Audrey and Lynn therefore stay completely separate, and the server host does not need to be available."
            ),
            wraplength=820,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(9, 0))

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(18, 12))
        ttk.Button(button_frame, text="Organize wardrobe…", command=self._open_picker).pack(side="left")
        ttk.Button(button_frame, text="Preview styling", command=self._preview).pack(side="left", padx=(10, 0))
        self.install_button = ttk.Button(button_frame, text="Generate + prepare sync", command=lambda: self._generate(True))
        self.install_button.pack(side="left", padx=10)
        self.generate_button = ttk.Button(button_frame, text="Generate only", command=lambda: self._generate(False))
        self.generate_button.pack(side="left")
        ttk.Button(button_frame, text="Undo slider (Ctrl+Z)", command=self._undo_sliders).pack(side="right")
        ttk.Button(button_frame, text="Redo slider (Ctrl+Y)", command=self._redo_sliders).pack(side="right", padx=(0, 7))

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=13, column=0, columnspan=3, sticky="ew")
        ttk.Label(frame, textvariable=self.status_var, wraplength=850).grid(row=14, column=0, columnspan=3, sticky="w", pady=(8, 0))

        frame.columnconfigure(1, weight=1)

    def _history_scale(self, parent: tk.Misc, **options) -> ttk.Scale:
        """Create a scale whose entire mouse drag is one undoable action."""

        scale = ttk.Scale(parent, **options)
        scale.bind("<ButtonPress-1>", self._begin_slider_gesture)
        scale.bind("<ButtonRelease-1>", self._finish_slider_gesture)
        for key in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"):
            scale.bind(f"<KeyPress-{key}>", self._begin_slider_gesture)
            scale.bind(f"<KeyRelease-{key}>", self._finish_slider_gesture)
        return scale

    def _slider_variables(self) -> dict[str, tk.DoubleVar]:
        return {
            "hair_hue": self.hair_hue_var,
            "hair_saturation": self.hair_saturation_var,
            "hair_lightness": self.hair_lightness_var,
            "hair_tolerance": self.tolerance_var,
            "skin_tolerance": self.skin_tolerance_var,
            "outfit_hue": self.outfit_hue_var,
            "outfit_saturation": self.outfit_saturation_var,
            "outfit_brightness": self.outfit_brightness_var,
            "accessory_hue": self.accessory_hue_var,
            "accessory_saturation": self.accessory_saturation_var,
            "accessory_brightness": self.accessory_brightness_var,
        }

    def _capture_slider_state(self) -> dict[str, float]:
        return {name: float(variable.get()) for name, variable in self._slider_variables().items()}

    def _begin_slider_gesture(self, _event: tk.Event | None = None) -> None:
        self._finish_slider_gesture()
        self._active_slider_snapshot = self._capture_slider_state()

    def _finish_slider_gesture(self, _event: tk.Event | None = None) -> None:
        if self._active_slider_snapshot is None:
            return
        before = self._active_slider_snapshot
        self._active_slider_snapshot = None
        if before == self._capture_slider_state():
            return
        self._slider_undo_stack.append(before)
        if len(self._slider_undo_stack) > 100:
            del self._slider_undo_stack[0]
        self._slider_redo_stack.clear()

    def _restore_slider_state(self, state: dict[str, float]) -> None:
        for name, variable in self._slider_variables().items():
            variable.set(state[name])
        self._on_hair_target_change()
        self._on_palette_target_change("outfit")
        self._on_palette_target_change("accessory")
        self._refresh_tolerance_labels()

    def _undo_sliders(self, _event: tk.Event | None = None) -> str:
        self._finish_slider_gesture()
        if not self._slider_undo_stack:
            self.status_var.set("Nothing to undo yet — move any color or detection slider first.")
            return "break"
        self._slider_redo_stack.append(self._capture_slider_state())
        self._restore_slider_state(self._slider_undo_stack.pop())
        self.status_var.set("Undid the last slider adjustment. Ctrl+Z goes back again.")
        return "break"

    def _redo_sliders(self, _event: tk.Event | None = None) -> str:
        self._finish_slider_gesture()
        if not self._slider_redo_stack:
            self.status_var.set("Nothing to redo yet.")
            return "break"
        self._slider_undo_stack.append(self._capture_slider_state())
        self._restore_slider_state(self._slider_redo_stack.pop())
        self.status_var.set("Redid the slider adjustment. Ctrl+Y goes forward again.")
        return "break"

    def _record_slider_action(self, before: dict[str, float]) -> None:
        if before == self._capture_slider_state():
            return
        self._slider_undo_stack.append(before)
        if len(self._slider_undo_stack) > 100:
            del self._slider_undo_stack[0]
        self._slider_redo_stack.clear()

    def _path_row(self, parent, row, label, variable, command, folder: bool) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=5)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, sticky="ew", pady=5)

    def _choose_input(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.input_var.get())
        if selected:
            self.input_var.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(Path(self.output_var.get()).parent), mustexist=False)
        if selected:
            self.output_var.set(selected)

    def _choose_reference(self) -> None:
        selected = filedialog.askopenfilename(
            initialdir=self.input_var.get(),
            filetypes=(("Minecraft skin PNG", "*.png"), ("All files", "*.*")),
        )
        if selected:
            self.reference_var.set(selected)

    def _open_face_picker(self) -> None:
        source = Path(self.input_var.get()).expanduser()
        if not source.is_dir():
            messagebox.showerror("Cannot open eye gallery", f"Source folder does not exist:\n{source}")
            return
        if not any(source.rglob("*.png")):
            messagebox.showerror("Cannot open eye gallery", "No PNG skins were found in the Source wardrobe.")
            return
        FacePicker(self, source, self._use_face_reference_and_design)

    def _open_eye_designer(self, initial: Path | None = None) -> None:
        if initial is None:
            selected = Path(self.reference_var.get()).expanduser() if self.reference_var.get().strip() else None
            initial = selected if selected is not None and selected.is_file() else None
        if initial is None and self.custom_eye_reference.is_file():
            initial = self.custom_eye_reference
        self._ensure_hair_sample()
        preview_skin = initial
        if preview_skin == self.custom_eye_reference or preview_skin is None:
            preview_skin = self._hair_sample_path
        EyeDesigner(
            self,
            initial,
            self.custom_eye_reference,
            self._use_face_reference,
            preview_skin=preview_skin,
            eyes_over_bangs=self.eyes_over_bangs_var.get(),
            preserve_hat_layer_lashes=self.preserve_hat_lashes_var.get(),
        )

    def _use_face_reference_and_design(self, path: Path) -> None:
        self._use_face_reference(path)
        # Let the gallery release its modal grab and close before the designer
        # opens with the chosen skin as its exact starting point.
        self.after_idle(lambda chosen=path: self._open_eye_designer(chosen))

    def _use_face_reference(self, path: Path) -> None:
        self.reference_var.set(str(path))
        label = "Custom eyes designed" if path.resolve() == self.custom_eye_reference.resolve() else "Reference eyes selected"
        self.status_var.set(f"{label}: {path.name}")

    def _open_picker(self) -> None:
        source = Path(self.input_var.get()).expanduser()
        if not source.is_dir():
            messagebox.showerror("Cannot open wardrobe", f"Source folder does not exist:\n{source}")
            return
        if not any(source.rglob("*.png")):
            messagebox.showerror("Cannot open wardrobe", "No PNG skins were found in the source folder.")
            return
        WardrobePicker(self, source, self._use_picker_source)

    def _use_picker_source(self, source: Path) -> None:
        self.input_var.set(str(source))
        self.status_var.set(f"Favorites master folder is now the Source wardrobe: {source}")

    def _refresh_reference_preview(self, *_args) -> None:
        value = self.reference_var.get().strip()
        if not value:
            self._reference_preview_image = None
            self.reference_preview.configure(image="", text="eye\npreview")
            self.after_idle(self._refresh_hair_preview)
            return
        try:
            with Image.open(value) as image:
                face = render_front_face(image, 8)
            self._reference_preview_image = ImageTk.PhotoImage(face)
            self.reference_preview.configure(image=self._reference_preview_image, text="")
        except Exception:
            self._reference_preview_image = None
            self.reference_preview.configure(image="", text="not a valid\nskin")
        self.after_idle(self._refresh_hair_preview)

    def _source_wardrobe_changed(self, *_args) -> None:
        self._hair_sample_path = None
        self._hair_sample_image = None
        self.hair_sample_var.set("finding a sample…")
        self.after_idle(self._refresh_hair_preview)

    def _load_hair_sample(self, path: Path) -> bool:
        try:
            with Image.open(path) as image:
                normalized, _was_normalized = normalize_skin(image)
            self._hair_sample_path = path
            self._hair_sample_image = normalized.copy()
            self.hair_sample_var.set(path.stem[:18] + ("…" if len(path.stem) > 18 else ""))
            return True
        except Exception:
            return False

    def _ensure_hair_sample(self) -> bool:
        if self._hair_sample_image is not None:
            return True
        source = Path(self.input_var.get()).expanduser()
        if not source.is_dir():
            return False
        for path in sorted(source.rglob("*.png"), key=lambda item: item.name.casefold()):
            if not self._load_hair_sample(path):
                continue
            try:
                _styled, mask, _was_normalized = style_skin(
                    self._hair_sample_image,
                    parse_hex_color(self.hair_var.get()),
                    float(round(self.tolerance_var.get())),
                )
                if mask:
                    return True
            except Exception:
                pass
            self._hair_sample_path = None
            self._hair_sample_image = None
        return False

    def _choose_hair_sample(self) -> None:
        selected = filedialog.askopenfilename(
            initialdir=self.input_var.get(),
            filetypes=(("Minecraft skin PNG", "*.png"), ("All files", "*.*")),
            title="Choose the live hair-preview skin",
        )
        if selected and self._load_hair_sample(Path(selected)):
            self._refresh_hair_preview()

    def _refresh_hair_preview(self, *_args) -> None:
        if not hasattr(self, "hair_preview"):
            return
        if not self._ensure_hair_sample() or self._hair_sample_image is None:
            self._hair_preview_image = None
            self.hair_preview.configure(image="", text="no sample skin")
            self.hair_sample_var.set("choose Sample…")
            return
        try:
            target = parse_hex_color(self.hair_var.get())
            tolerance = float(round(self.tolerance_var.get()))
            skin_target = parse_hex_color(self.skin_var.get()) if self.skin_enabled_var.get() else None
            outfit_target = parse_hex_color(self.outfit_var.get()) if self.outfit_enabled_var.get() else None
            accessory_target = parse_hex_color(self.accessory_var.get()) if self.accessory_enabled_var.get() else None
            skin_tolerance = float(round(self.skin_tolerance_var.get()))
            template = None
            reference_text = self.reference_var.get().strip()
            if self.face_var.get() and reference_text:
                reference_path = Path(reference_text)
                if reference_path.is_file():
                    with Image.open(reference_path) as reference:
                        template = make_face_template(reference, tolerance)
            styled, _mask, _was_normalized = style_skin(
                self._hair_sample_image,
                target,
                tolerance,
                template,
                False,
                skin_target,
                skin_tolerance,
                self.body_hair_var.get(),
                self.eyes_over_bangs_var.get(),
                outfit_target,
                accessory_target,
                self.preserve_hat_lashes_var.get(),
            )
            before = render_player_3d(self._hair_sample_image, 3, yaw_degrees=self._preview_yaw)
            after = render_player_3d(styled, 3, yaw_degrees=self._preview_yaw)
            comparison = Image.new("RGBA", (150, 110), (43, 43, 43, 255))
            before_x = max(2, 57 - before.width)
            after_x = 90
            comparison.alpha_composite(before, (before_x, max(2, (110 - before.height) // 2)))
            comparison.alpha_composite(after, (after_x, max(2, (110 - after.height) // 2)))
            draw = ImageDraw.Draw(comparison)
            draw.line((67, 54, 78, 54), fill=(235, 190, 219, 255), width=2)
            draw.polygon(((78, 50), (84, 54), (78, 58)), fill=(235, 190, 219, 255))
            self._hair_preview_image = ImageTk.PhotoImage(comparison)
            self.hair_preview.configure(image=self._hair_preview_image, text="")
        except Exception:
            self._hair_preview_image = None
            self.hair_preview.configure(image="", text="preview unavailable")

    def _begin_live_preview_drag(self, event: tk.Event) -> None:
        self._preview_drag_x = int(event.x)

    def _drag_live_preview(self, event: tk.Event) -> None:
        current_x = int(event.x)
        if self._preview_drag_x is None:
            self._preview_drag_x = current_x
            return
        delta = current_x - self._preview_drag_x
        if abs(delta) < 8:
            return
        self._preview_yaw = (self._preview_yaw + delta * 2.2) % 360.0
        self._preview_drag_x = current_x
        self._refresh_hair_preview()

    def _refresh_color_swatches(self, *_args) -> None:
        self._set_swatch(self.hair_swatch, self.hair_var.get())
        self._set_swatch(self.skin_swatch, self.skin_var.get())
        if hasattr(self, "outfit_swatch"):
            self._set_swatch(self.outfit_swatch, self.outfit_var.get())
        if hasattr(self, "accessory_swatch"):
            self._set_swatch(self.accessory_swatch, self.accessory_var.get())

    @staticmethod
    def _set_swatch(widget: tk.Label, value: str) -> None:
        try:
            red, green, blue = parse_hex_color(value)
            widget.configure(background=f"#{red:02X}{green:02X}{blue:02X}", text="")
        except ValueError:
            widget.configure(background="#555555", foreground="white", text="?")

    def _refresh_tolerance_labels(self, *_args) -> None:
        self.tolerance_text_var.set(str(round(float(self.tolerance_var.get()))))
        self.skin_tolerance_text_var.set(str(round(float(self.skin_tolerance_var.get()))))
        self.after_idle(self._refresh_hair_preview)

    def _reset_hair_tolerance(self) -> None:
        before = self._capture_slider_state()
        self.tolerance_var.set(42)
        self._record_slider_action(before)

    def _reset_skin_tolerance(self) -> None:
        before = self._capture_slider_state()
        self.skin_tolerance_var.set(24)
        self._record_slider_action(before)

    def _choose_color(self) -> None:
        before = self._capture_slider_state()
        try:
            initial = self.hair_var.get()
            selected = colorchooser.askcolor(color=initial, title="Choose the target hair color")[1]
            if selected:
                degrees, saturation, lightness = hair_targets_from_color(selected)
                self.hair_hue_var.set(degrees)
                self.hair_saturation_var.set(saturation)
                self.hair_lightness_var.set(lightness)
                self._on_hair_target_change()
                self._record_slider_action(before)
        except tk.TclError:
            degrees, saturation, lightness = hair_targets_from_color(DEFAULT_HAIR_HUE_COLOR)
            self.hair_hue_var.set(degrees)
            self.hair_saturation_var.set(saturation)
            self.hair_lightness_var.set(lightness)
            self._on_hair_target_change()
            self._record_slider_action(before)

    def _on_hair_hue_change(self, value: str) -> None:
        self.hair_hue_var.set(float(value))
        self._on_hair_target_change()

    def _on_hair_target_change(self, _value: str | None = None) -> None:
        degrees = float(self.hair_hue_var.get())
        saturation = float(self.hair_saturation_var.get())
        lightness = float(self.hair_lightness_var.get())
        red, green, blue = hair_color_from_targets(degrees, saturation, lightness)
        self.hair_var.set(f"#{red:02X}{green:02X}{blue:02X}")
        self.hair_hue_text_var.set(f"{round(degrees)}°")
        self.hair_saturation_text_var.set(f"{round(saturation)}%")
        self.hair_lightness_text_var.set(f"{round(lightness)}%")
        if hasattr(self, "hair_preview"):
            self._refresh_hair_preview()

    def _on_palette_target_change(self, group: str) -> None:
        if group == "outfit":
            hue_var = self.outfit_hue_var
            saturation_var = self.outfit_saturation_var
            brightness_var = self.outfit_brightness_var
            color_var = self.outfit_var
            hue_text = self.outfit_hue_text_var
            saturation_text = self.outfit_saturation_text_var
            brightness_text = self.outfit_brightness_text_var
        else:
            hue_var = self.accessory_hue_var
            saturation_var = self.accessory_saturation_var
            brightness_var = self.accessory_brightness_var
            color_var = self.accessory_var
            hue_text = self.accessory_hue_text_var
            saturation_text = self.accessory_saturation_text_var
            brightness_text = self.accessory_brightness_text_var
        hue = float(hue_var.get())
        saturation = float(saturation_var.get())
        brightness = float(brightness_var.get())
        red, green, blue = hair_color_from_targets(hue, saturation, brightness)
        color_var.set(f"#{red:02X}{green:02X}{blue:02X}")
        hue_text.set(f"{round(hue)}°")
        saturation_text.set(f"{round(saturation)}%")
        brightness_text.set(f"{round(brightness)}%")
        self._refresh_color_swatches()
        if hasattr(self, "hair_preview"):
            self._refresh_hair_preview()

    def _choose_skin_color(self) -> None:
        try:
            selected = colorchooser.askcolor(color=self.skin_var.get(), title="Choose the exposed skin tone")[1]
            if selected:
                self.skin_var.set(selected.upper())
                self.skin_enabled_var.set(True)
        except tk.TclError:
            self.skin_var.set("#C58C70")

    def _settings(self):
        input_folder = Path(self.input_var.get())
        output_folder = Path(self.output_var.get())
        reference = Path(self.reference_var.get()) if self.reference_var.get().strip() else None
        target = parse_hex_color(self.hair_var.get())
        skin_target = parse_hex_color(self.skin_var.get()) if self.skin_enabled_var.get() else None
        outfit_target = parse_hex_color(self.outfit_var.get()) if self.outfit_enabled_var.get() else None
        accessory_target = parse_hex_color(self.accessory_var.get()) if self.accessory_enabled_var.get() else None
        tolerance = float(round(self.tolerance_var.get()))
        skin_tolerance = float(round(self.skin_tolerance_var.get()))
        include_body_hair = self.body_hair_var.get()
        if self.face_var.get() and reference is None:
            raise ValueError("Choose one reference skin for the eyes you want to keep")
        return (
            input_folder,
            output_folder,
            reference,
            target,
            tolerance,
            skin_target,
            skin_tolerance,
            include_body_hair,
            self.eyes_over_bangs_var.get(),
            outfit_target,
            accessory_target,
            self.preserve_hat_lashes_var.get(),
        )

    def _preview(self) -> None:
        try:
            (
                input_folder,
                _output,
                reference,
                target,
                tolerance,
                skin_target,
                skin_tolerance,
                include_body_hair,
                eyes_over_bangs,
                outfit_target,
                accessory_target,
                preserve_hat_lashes,
            ) = self._settings()
            files = sorted(input_folder.rglob("*.png"), key=lambda path: path.name.casefold())
            if not files:
                raise ValueError("No PNG skins were found in the source folder")
            template = None
            if self.face_var.get() and reference is not None:
                with Image.open(reference) as reference_image:
                    template = make_face_template(reference_image, tolerance)

            rows: list[tuple[str, Image.Image, Image.Image]] = []
            self.status_var.set(f"Preparing {len(files)} lightweight preview thumbnails…")
            self.update_idletasks()
            for path in files:
                with Image.open(path) as image:
                    normalized, _ = normalize_skin(image)
                    styled, _mask, _was_hd = style_skin(
                        normalized,
                        target,
                        tolerance,
                        template,
                        False,
                        skin_target,
                        skin_tolerance,
                        include_body_hair,
                        eyes_over_bangs,
                        outfit_target,
                        accessory_target,
                        preserve_hat_lashes,
                    )
                rows.append((path.stem, normalized, styled))
            self._show_preview(rows)
            self.status_var.set(f"Previewing all {len(rows)} skins · click any card for full 360°")
        except Exception as exception:
            messagebox.showerror("Could not preview", str(exception))

    def _show_preview(self, rows: list[tuple[str, Image.Image, Image.Image]]) -> None:
        window = tk.Toplevel(self)
        window.title("Daily Dress — all original → styled previews")
        window.geometry("1120x820")
        window.minsize(720, 480)
        canvas = tk.Canvas(window, width=1080, height=780, background="#202124")
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        preview_images: list[ImageTk.PhotoImage] = []
        # Keep each gallery's thumbnails alive independently if two preview
        # windows are opened at once.
        window._daily_dress_preview_images = preview_images  # type: ignore[attr-defined]

        canvas.create_text(
            18,
            22,
            text=f"All {len(rows)} skins · lightweight thumbnails · click one for a large resizable 360° comparison",
            fill="white",
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )

        columns = 4
        tile_width = 265
        tile_height = 195
        for index, (name, before, after) in enumerate(rows):
            column = index % columns
            row = index // columns
            x = 10 + column * tile_width
            y = 48 + row * tile_height
            tag = f"preview-card-{index}"
            canvas.create_rectangle(
                x,
                y,
                x + tile_width - 10,
                y + tile_height - 10,
                fill="#2B2D32",
                outline="#464950",
                width=2,
                tags=(tag,),
            )
            before_tk = ImageTk.PhotoImage(render_player_view(before, scale=4, slim=True))
            after_tk = ImageTk.PhotoImage(render_player_view(after, scale=4, slim=True))
            preview_images.extend((before_tk, after_tk))
            canvas.create_text(x + 16, y + 12, text="original", fill="#B9BBC2", anchor="nw", tags=(tag,))
            canvas.create_text(x + 150, y + 12, text="styled", fill="#B9BBC2", anchor="nw", tags=(tag,))
            canvas.create_image(x + 62, y + 88, image=before_tk, anchor="center", tags=(tag,))
            canvas.create_text(x + 128, y + 88, text="→", fill="#D7A9E3", font=("Segoe UI", 18, "bold"), tags=(tag,))
            canvas.create_image(x + 195, y + 88, image=after_tk, anchor="center", tags=(tag,))
            canvas.create_text(x + 12, y + 160, text=name[:36], fill="white", anchor="w", font=("Segoe UI", 9), tags=(tag,))
            canvas.tag_bind(
                tag,
                "<Button-1>",
                lambda _event, selected_name=name, original=before, styled=after: self._show_preview_detail(
                    selected_name, original, styled
                ),
            )
            canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
            canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))
        gallery_height = 58 + ((len(rows) + columns - 1) // columns) * tile_height
        canvas.configure(scrollregion=(0, 0, columns * tile_width + 10, gallery_height))
        canvas.bind(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(-1 * int(event.delta / 120), "units"),
        )

    def _show_preview_detail(self, name: str, before: Image.Image, after: Image.Image) -> None:
        window = tk.Toplevel(self)
        window.title(f"360° original → styled — {name}")
        window.geometry("900x720")
        window.minsize(620, 480)
        canvas = tk.Canvas(window, background="#202124", highlightthickness=0, cursor="fleur")
        canvas.pack(fill="both", expand=True)
        state = {"yaw": self._preview_yaw, "drag_x": None, "resize_job": None, "photos": []}

        def redraw() -> None:
            state["resize_job"] = None
            width = max(600, canvas.winfo_width())
            height = max(440, canvas.winfo_height())
            model_scale = max(4, min(18, round(min(width / 38, (height - 90) / 34))))
            before_model = render_player_3d(before, model_scale, yaw_degrees=float(state["yaw"]))
            after_model = render_player_3d(after, model_scale, yaw_degrees=float(state["yaw"]))
            before_tk = ImageTk.PhotoImage(before_model)
            after_tk = ImageTk.PhotoImage(after_model)
            state["photos"] = [before_tk, after_tk]
            canvas.delete("all")
            canvas.create_text(width // 2, 24, text=name, fill="white", font=("Segoe UI", 13, "bold"))
            canvas.create_text(
                width // 2,
                49,
                text=f"drag anywhere for continuous 360° · {round(float(state['yaw'])) % 360}° · both Minecraft layers",
                fill="#B9BBC2",
                font=("Segoe UI", 10),
            )
            canvas.create_text(width // 4, 78, text="original", fill="white", font=("Segoe UI", 11, "bold"))
            canvas.create_text(3 * width // 4, 78, text="styled", fill="white", font=("Segoe UI", 11, "bold"))
            center_y = 90 + (height - 90) // 2
            canvas.create_image(width // 4, center_y, image=before_tk, anchor="center")
            canvas.create_text(width // 2, center_y, text="→", fill="#D7A9E3", font=("Segoe UI", 24, "bold"))
            canvas.create_image(3 * width // 4, center_y, image=after_tk, anchor="center")

        def schedule_redraw(_event=None) -> None:
            job = state.get("resize_job")
            if job is not None:
                window.after_cancel(job)
            state["resize_job"] = window.after(70, redraw)

        def begin_drag(event: tk.Event) -> None:
            state["drag_x"] = int(event.x)

        def drag(event: tk.Event) -> None:
            current_x = int(event.x)
            previous = state.get("drag_x")
            if previous is None:
                state["drag_x"] = current_x
                return
            delta = current_x - int(previous)
            if abs(delta) < 3:
                return
            state["yaw"] = (float(state["yaw"]) + delta * 1.3) % 360.0
            self._preview_yaw = float(state["yaw"])
            state["drag_x"] = current_x
            redraw()

        canvas.bind("<Configure>", schedule_redraw)
        canvas.bind("<ButtonPress-1>", begin_drag)
        canvas.bind("<B1-Motion>", drag)
        window.after(50, redraw)

    def _selected_install_targets(self) -> list[tuple[str, Path]]:
        if self.sync_var.get() and self.sync_outbox is not None:
            return [("your Minecraft sync outbox", self.sync_outbox)]
        return []

    def _generate(self, install: bool) -> None:
        try:
            settings = self._settings()
            install_targets = self._selected_install_targets() if install else []
            if install and not install_targets:
                raise ValueError("Enable automatic personal wardrobe sync")
        except Exception as exception:
            messagebox.showerror("Cannot generate", str(exception))
            return

        if install:
            destinations = "\n".join(f"• {label}" for label, _path in install_targets)
            confirmed = messagebox.askokcancel(
                "Generate and prepare sync?",
                "The Styler will generate the whole wardrobe, back up the previous outbox, then prepare the new skins in:\n\n"
                f"{destinations}\n\nYour original source skins will not be changed.",
            )
            if not confirmed:
                return

        self.generate_button.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("Starting…")

        def progress(current: int, total: int, path: Path) -> None:
            self.after(0, lambda: self._set_progress(current, total, path.name))

        def worker() -> None:
            try:
                (
                    input_folder,
                    output_folder,
                    reference,
                    target,
                    tolerance,
                    skin_target,
                    skin_tolerance,
                    include_body_hair,
                    eyes_over_bangs,
                    outfit_target,
                    accessory_target,
                    preserve_hat_lashes,
                ) = settings
                result = generate_folder(
                    input_folder,
                    output_folder,
                    target,
                    tolerance=tolerance,
                    reference_skin=reference,
                    standardize_face=self.face_var.get(),
                    target_skin_color=skin_target,
                    skin_tolerance=skin_tolerance,
                    include_body_hair=include_body_hair,
                    eyes_over_bangs=eyes_over_bangs,
                    target_outfit_color=outfit_target,
                    target_accessory_color=accessory_target,
                    preserve_hat_layer_lashes=preserve_hat_lashes,
                    progress=progress,
                )
                installations = []
                for label, target_folder in install_targets:
                    self.after(0, lambda label=label: self.status_var.set(f"Preparing {label}…"))
                    installations.append((label, install_generated_wardrobe(output_folder, target_folder)))
                self.after(0, lambda: self._finished(result, output_folder, installations))
            except Exception as exception:
                self.after(0, lambda: self._failed(exception))

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, current: int, total: int, name: str) -> None:
        self.progress["maximum"] = total
        self.progress["value"] = current
        self.status_var.set(f"{current}/{total}: {name}")

    def _finished(self, result, output_folder: Path, installations) -> None:
        self.generate_button.configure(state="normal")
        self.install_button.configure(state="normal")
        summary = f"Created {result.written} styled skins in:\n{output_folder}\n\nNormalized {result.normalized} HD skin(s)."
        if result.skipped:
            summary += f"\nSkipped {len(result.skipped)} file(s); see the styling manifest."
        if installations:
            summary += "\n\nPrepared automatically in:"
            for label, installation in installations:
                summary += f"\n• {label} ({installation.installed} skins)"
            summary += (
                "\n\nThe previous outbox was backed up first. Join Roses with the account this wardrobe belongs to; "
                "Daily Dress will sync it automatically, usually within a few seconds, and keep that player separate from everyone else."
            )
        self.status_var.set(summary.replace("\n", " "))
        messagebox.showinfo("Styled wardrobe ready ✿", summary)

    def _failed(self, exception: Exception) -> None:
        self.generate_button.configure(state="normal")
        self.install_button.configure(state="normal")
        self.status_var.set("Generation stopped.")
        messagebox.showerror("Could not generate wardrobe", str(exception))


if __name__ == "__main__":
    SkinStylerApp().mainloop()
