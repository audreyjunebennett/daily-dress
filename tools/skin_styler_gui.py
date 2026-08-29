"""Friendly Tk GUI for the Daily Dress skin styling engine."""

from __future__ import annotations

import colorsys
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from integrated_workbench import IntegratedWorkbench
from minecraft_theme import COLORS, apply_minecraft_theme
from skin_styler_core import (
    detect_skin_model,
    generate_folder,
    install_generated_wardrobe,
    make_face_template,
    normalize_skin,
    parse_hex_color,
    render_front_face,
    render_player_3d,
    style_skin,
)
from wardrobe_picker import PickerState, TAGS


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
        apply_minecraft_theme(self)
        self.title("Daily Dress Skin Styler ✿")
        self.geometry("1460x1000")
        self.minsize(1180, 900)

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
        self.adaptive_detection_var = tk.BooleanVar(value=True)
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
        self.source_count_var = tk.StringVar(value="Choose a source wardrobe to begin")
        self.sample_position_var = tk.StringVar(value="No skin selected")
        self.current_status_var = tk.StringVar(value="Unsorted · Other")
        self.current_tag_var = tk.StringVar(value="other")
        self.preview_batch_var = tk.StringVar(value="All kept skins")
        self.model_var = tk.StringVar(value="Auto-detect per skin")
        self.no_visible_hair_var = tk.BooleanVar(value=False)
        self._reference_preview_image: ImageTk.PhotoImage | None = None
        self._hair_preview_image: ImageTk.PhotoImage | None = None
        self._hair_sample_path: Path | None = None
        self._hair_sample_image: Image.Image | None = None
        self._sample_paths: list[Path] = []
        self._sample_index = -1
        self._picker_state: PickerState | None = None
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
        self.adaptive_detection_var.trace_add("write", self._refresh_hair_preview)
        self.outfit_enabled_var.trace_add("write", self._refresh_hair_preview)
        self.accessory_enabled_var.trace_add("write", self._refresh_hair_preview)
        self.preview_batch_var.trace_add("write", self._working_set_changed)
        self._refresh_color_swatches()
        self._refresh_tolerance_labels()
        self._refresh_reference_preview()
        self._source_wardrobe_changed()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18, style="Root.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="DAILY DRESS ✿ SKIN STYLER", style="Title.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            frame,
            text="A cozy Minecraft workbench for sorting outfits, choosing hair + eyes, correcting tricky pixels, and preparing one safe personal sync set. Originals are never changed.",
            wraplength=1120,
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 18))

        self._path_row(frame, 2, "Source wardrobe", self.input_var, self._choose_input, folder=True)
        ttk.Label(frame, text="Reference eyes").grid(row=3, column=0, sticky="w", pady=5)
        reference_frame = ttk.Frame(frame)
        reference_frame.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Entry(reference_frame, textvariable=self.reference_var).grid(row=0, column=0, sticky="ew", padx=(8, 8))
        ttk.Button(reference_frame, text="Eyes below", command=lambda: self._show_workbench("eyes")).grid(row=0, column=1, sticky="ew", padx=(0, 7))
        ttk.Button(reference_frame, text="Browse…", command=self._choose_reference).grid(row=0, column=2, sticky="ew", padx=(0, 10))
        ttk.Label(reference_frame, text="Full face is context; only eye pixels are copied.", foreground="#777777").grid(row=1, column=0, sticky="w", padx=(8, 8), pady=(3, 0))
        ttk.Button(reference_frame, text="Design below", command=lambda: self._show_workbench("eyes", "designer")).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=(3, 0))
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

        ttk.Label(frame, text="3. TARGET HAIR COLOR", style="Step.TLabel").grid(row=5, column=0, sticky="nw", pady=(18, 4))
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

        hair_reference_buttons = ttk.Frame(color_frame)
        hair_reference_buttons.grid(row=3, column=1, columnspan=4, sticky="ew", pady=(6, 0))
        ttk.Button(hair_reference_buttons, text="Hair library", command=lambda: self._show_workbench("hair"), style="Rose.TButton").pack(side="left")
        ttk.Button(hair_reference_buttons, text="Choose sample file…", command=self._choose_hair_sample).pack(side="left", padx=(7, 0))
        ttk.Button(hair_reference_buttons, text="Exact pixel below", command=lambda: self._show_workbench("hair", "sampler")).pack(side="left", padx=(7, 0))
        ttk.Label(
            color_frame,
            text="Gallery/sample sets both the visible reference and the starting color; sliders are for refinement.",
            style="Muted.TLabel",
        ).grid(row=4, column=1, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            color_frame,
            text="Continue long hair down the torso/shoulders",
            variable=self.body_hair_var,
        ).grid(row=5, column=1, columnspan=4, sticky="w", pady=(4, 0))
        color_frame.columnconfigure(2, weight=1)

        detection_label = ttk.Frame(frame)
        detection_label.grid(row=6, column=0, sticky="w", pady=8)
        ttk.Label(detection_label, text="Advanced hair detection").pack(anchor="w")
        ttk.Checkbutton(detection_label, text="Auto-tune per skin", variable=self.adaptive_detection_var).pack(anchor="w")
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
        ttk.Button(skin_frame, text="Sample selected skin", command=self._sample_current_skin_tone).pack(side="left")

        ttk.Label(frame, text="Advanced skin detection").grid(row=9, column=0, sticky="w", pady=8)
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
        ttk.Button(button_frame, text="Wardrobe workspace", command=lambda: self._show_workbench("wardrobe")).pack(side="left")
        self.install_button = ttk.Button(button_frame, text="Generate + prepare sync", command=lambda: self._generate(True))
        self.install_button.pack(side="left", padx=10)
        self.generate_button = ttk.Button(button_frame, text="Generate only", command=lambda: self._generate(False))
        self.generate_button.pack(side="left")
        ttk.Button(button_frame, text="Undo slider (Ctrl+Z)", command=self._undo_sliders).pack(side="right")
        ttk.Button(button_frame, text="Redo slider (Ctrl+Y)", command=self._redo_sliders).pack(side="right", padx=(0, 7))

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=13, column=0, columnspan=3, sticky="ew")
        ttk.Label(frame, textvariable=self.status_var, wraplength=850).grid(row=14, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._build_workspace(frame)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, minsize=455)

    def _build_workspace(self, frame: ttk.Frame) -> None:
        workspace = ttk.LabelFrame(frame, text="2. ORGANIZE + LIVE PREVIEW", padding=10)
        workspace.grid(row=2, column=3, rowspan=13, sticky="nsew", padx=(18, 0))
        ttk.Label(workspace, textvariable=self.source_count_var, style="Count.TLabel", wraplength=420).pack(fill="x")

        filter_row = ttk.Frame(workspace)
        filter_row.pack(fill="x", pady=(7, 5))
        ttk.Label(filter_row, text="Working set").pack(side="left")
        ttk.Combobox(
            filter_row,
            textvariable=self.preview_batch_var,
            values=(
                "All kept skins",
                "Favorites only",
                "Dresses",
                "Casual",
                "Seasonal",
                "Favorite dresses",
                "Favorite casual",
                "Favorite seasonal",
            ),
            state="readonly",
            width=20,
        ).pack(side="right", fill="x", expand=True, padx=(8, 0))

        preview_box = tk.Frame(
            workspace,
            width=425,
            height=310,
            background=COLORS["slot"],
            highlightthickness=3,
            highlightbackground=COLORS["stone_dark"],
        )
        preview_box.pack(fill="x", pady=(4, 5))
        preview_box.pack_propagate(False)
        self.hair_preview = tk.Label(
            preview_box,
            text="choose a wardrobe\nto light the workbench",
            background=COLORS["slot"],
            foreground=COLORS["muted"],
            cursor="fleur",
        )
        self.hair_preview.pack(fill="both", expand=True)
        self.hair_preview.bind("<ButtonPress-1>", self._begin_live_preview_drag)
        self.hair_preview.bind("<B1-Motion>", self._drag_live_preview)

        ttk.Label(workspace, textvariable=self.sample_position_var, anchor="center").pack(fill="x")
        ttk.Label(workspace, textvariable=self.current_status_var, style="Muted.TLabel", anchor="center").pack(fill="x")
        nav = ttk.Frame(workspace)
        nav.pack(fill="x", pady=(5, 7))
        ttk.Button(nav, text="◀ Previous", command=lambda: self._cycle_sample(-1)).pack(side="left")
        ttk.Button(nav, text="Next ▶", command=lambda: self._cycle_sample(1)).pack(side="right")
        ttk.Button(nav, text="Browse hair below", command=lambda: self._show_workbench("hair"), style="Rose.TButton").pack(expand=True)

        model_row = ttk.Frame(workspace)
        model_row.pack(fill="x", pady=(0, 7))
        ttk.Label(model_row, text="Arm model").pack(side="left")
        model_box = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=("Auto-detect per skin", "Slim / thin arms", "Classic / default arms"),
            state="readonly",
            width=22,
        )
        model_box.pack(side="right")
        model_box.bind("<<ComboboxSelected>>", lambda _event: self._set_current_model())
        ttk.Checkbutton(
            workspace,
            text="Hood / helmet: no visible hair on this skin",
            variable=self.no_visible_hair_var,
            command=self._set_current_hair_mode,
        ).pack(anchor="w", pady=(0, 7))

        decisions = ttk.Frame(workspace)
        decisions.pack(fill="x", pady=(0, 6))
        ttk.Button(decisions, text="♥ Favorite", command=lambda: self._set_current_status("favorite"), style="Rose.TButton").pack(side="left", fill="x", expand=True)
        ttk.Button(decisions, text="? Maybe", command=lambda: self._set_current_status("maybe")).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(decisions, text="Unsorted", command=lambda: self._set_current_status("unsorted")).pack(side="left", fill="x", expand=True)
        ttk.Button(decisions, text="Remove", command=lambda: self._set_current_status("remove"), style="Danger.TButton").pack(side="left", fill="x", expand=True, padx=(4, 0))

        categories = ttk.Frame(workspace)
        categories.pack(fill="x", pady=(0, 7))
        ttk.Label(categories, text="Category").pack(side="left")
        tag_box = ttk.Combobox(
            categories,
            textvariable=self.current_tag_var,
            values=("dresses", "casual", "seasonal", "other"),
            state="readonly",
            width=12,
        )
        tag_box.pack(side="left", padx=(7, 5))
        tag_box.bind("<<ComboboxSelected>>", lambda _event: self._set_current_tag())
        ttk.Button(categories, text="Fix pixels below", command=lambda: self._show_workbench("pixels"), style="Accent.TButton").pack(side="right")

        ttk.Label(
            workspace,
            text="ALL-IN-ONE WORKBENCH · switch tools without opening another window",
            style="Step.TLabel",
        ).pack(fill="x", pady=(2, 3))
        self.workbench = IntegratedWorkbench(workspace, self)
        self.workbench.pack(fill="both", expand=True)

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

    def _use_face_reference(self, path: Path) -> None:
        self.reference_var.set(str(path))
        label = "Custom eyes designed" if path.resolve() == self.custom_eye_reference.resolve() else "Reference eyes selected"
        self.status_var.set(f"{label}: {path.name}")

    def _show_workbench(self, mode: str, subview: str = "gallery") -> None:
        """Bring one of the embedded tools into view without opening a window."""

        if not hasattr(self, "workbench"):
            return
        self.workbench.set_mode(mode, subview=subview)
        self.workbench.stage.focus_set()
        labels = {
            "wardrobe": "Wardrobe library",
            "hair": "Hair library",
            "eyes": "Eye library",
            "pixels": "Pixel-category editor",
        }
        self.status_var.set(f"{labels.get(mode, 'Workbench')} is open below the live 3D preview.")

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
        self._sample_paths = []
        self._sample_index = -1
        self._picker_state = None
        self.hair_sample_var.set("finding a sample…")
        source = Path(self.input_var.get()).expanduser()
        if source.is_dir():
            self._sample_paths = sorted(source.rglob("*.png"), key=lambda item: (item.name.casefold(), str(item).casefold()))
            self._picker_state = PickerState(source)
            self.source_count_var.set(
                f"Found {len(self._sample_paths)} skin{'s' if len(self._sample_paths) != 1 else ''} · originals stay untouched"
            )
            if self._sample_paths:
                self._load_hair_sample(self._sample_paths[0])
        else:
            self.source_count_var.set("Source folder not found yet")
        self.after_idle(self._refresh_hair_preview)
        self._schedule_strip_refresh()

    def _reload_wardrobe_state(self) -> None:
        source = Path(self.input_var.get()).expanduser()
        if source.is_dir():
            self._picker_state = PickerState(source)
            if self._hair_sample_path is not None:
                self._refresh_current_metadata()
            self._schedule_strip_refresh()

    def _relative_sample(self, path: Path | None = None) -> str | None:
        selected = path or self._hair_sample_path
        if selected is None:
            return None
        source = Path(self.input_var.get()).expanduser()
        try:
            return selected.resolve().relative_to(source.resolve()).as_posix()
        except (OSError, ValueError):
            return None

    def _batch_key(self) -> str:
        return {
            "All kept skins": "all",
            "Favorites only": "favorites",
            "Dresses": "dresses",
            "Casual": "casual",
            "Seasonal": "seasonal",
            "Favorite dresses": "favorites+dresses",
            "Favorite casual": "favorites+casual",
            "Favorite seasonal": "favorites+seasonal",
        }.get(self.preview_batch_var.get(), "all")

    def _path_in_working_set(self, path: Path) -> bool:
        if self._picker_state is None:
            return True
        relative = self._relative_sample(path)
        if relative is None:
            return True
        saved = self._picker_state.get(relative)
        if saved["status"] == "remove":
            return False
        requested = self._batch_key().split("+")
        if "favorites" in requested and saved["status"] != "favorite":
            return False
        tags = [piece for piece in requested if piece not in ("all", "favorites")]
        return not tags or saved["tag"] in tags

    def _working_paths(self) -> list[Path]:
        return [path for path in self._sample_paths if self._path_in_working_set(path)]

    def _working_set_changed(self, *_args) -> None:
        working = self._working_paths()
        self.source_count_var.set(
            f"Found {len(self._sample_paths)} skins · {len(working)} in “{self.preview_batch_var.get()}”"
        )
        if working and self._hair_sample_path not in working:
            self._load_hair_sample(working[0])
        self._schedule_strip_refresh()

    def _load_hair_sample(self, path: Path) -> bool:
        try:
            with Image.open(path) as image:
                normalized, _was_normalized = normalize_skin(image)
            self._hair_sample_path = path
            self._hair_sample_image = normalized.copy()
            self.hair_sample_var.set(path.stem[:18] + ("…" if len(path.stem) > 18 else ""))
            try:
                self._sample_index = self._sample_paths.index(path)
            except ValueError:
                self._sample_index = -1
            self._refresh_current_metadata()
            return True
        except Exception:
            return False

    def _ensure_hair_sample(self) -> bool:
        if self._hair_sample_image is not None:
            return True
        source = Path(self.input_var.get()).expanduser()
        if not source.is_dir():
            return False
        candidates = self._working_paths() or sorted(source.rglob("*.png"), key=lambda item: item.name.casefold())
        for path in candidates:
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
            self._sample_reference_color(self._hair_sample_image)
            self._refresh_hair_preview()
            self._schedule_strip_refresh()

    def _use_hair_reference(self, path: Path, color: tuple[int, int, int]) -> None:
        if not self._load_hair_sample(path):
            return
        self._set_target_hair_rgb(color)
        self.status_var.set(f"Hair reference + starting color selected from {path.name}.")
        self._refresh_hair_preview()
        self._schedule_strip_refresh()

    def _set_target_hair_rgb(self, color: tuple[int, int, int]) -> None:
        before = self._capture_slider_state()
        value = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
        degrees, saturation, lightness = hair_targets_from_color(value)
        self.hair_hue_var.set(degrees)
        self.hair_saturation_var.set(saturation)
        self.hair_lightness_var.set(max(12.0, lightness))
        self._on_hair_target_change()
        self._record_slider_action(before)

    def _sample_reference_color(self, image: Image.Image | None) -> None:
        if image is None:
            return
        from skin_styler_core import representative_hair_color

        try:
            self._set_target_hair_rgb(representative_hair_color(image, float(self.tolerance_var.get())))
        except ValueError:
            self.status_var.set("That skin has little or no visible hair; it remains the preview sample without changing the target color.")

    def _cycle_sample(self, change: int) -> None:
        working = self._working_paths()
        if not working:
            return
        try:
            index = working.index(self._hair_sample_path) if self._hair_sample_path is not None else -1
        except ValueError:
            index = -1
        self._load_hair_sample(working[(index + change) % len(working)])
        self._refresh_hair_preview()
        self._schedule_strip_refresh()

    def _refresh_current_metadata(self) -> None:
        if self._hair_sample_path is None:
            self.sample_position_var.set("No skin selected")
            return
        working = self._working_paths()
        try:
            position = working.index(self._hair_sample_path) + 1
        except ValueError:
            position = 0
        suffix = f" · {position}/{len(working)} in working set" if position else ""
        self.sample_position_var.set(f"{self._hair_sample_path.stem}{suffix}")
        relative = self._relative_sample()
        if relative is None or self._picker_state is None:
            self.current_status_var.set("External preview sample")
            self.current_tag_var.set("other")
            return
        saved = self._picker_state.details(relative)
        self.current_status_var.set(
            f"{str(saved['status']).title()} · {TAGS.get(str(saved['tag']), str(saved['tag']).title())} · "
            f"{len(saved['corrections'])} pixel correction(s)"
        )
        self.current_tag_var.set(str(saved["tag"]))
        model = str(saved["model"])
        self.model_var.set({"auto": "Auto-detect per skin", "slim": "Slim / thin arms", "classic": "Classic / default arms"}[model])
        self.no_visible_hair_var.set(str(saved["hair_mode"]) == "none")

    def _set_current_status(self, status: str) -> None:
        relative = self._relative_sample()
        if relative is None or self._picker_state is None:
            return
        self._picker_state.set(relative, status=status)
        self.status_var.set(f"Marked {self._hair_sample_path.stem} as {status.title()}; moved to the next skin.")
        self._refresh_current_metadata()
        self._cycle_sample(1)

    def _set_current_tag(self) -> None:
        relative = self._relative_sample()
        if relative is None or self._picker_state is None:
            return
        tag = self.current_tag_var.get()
        self._picker_state.set(relative, tag=tag)
        self.status_var.set(f"Categorized {self._hair_sample_path.stem} as {TAGS.get(tag, tag.title())}; moved to the next skin.")
        self._refresh_current_metadata()
        self._cycle_sample(1)

    def _set_current_model(self) -> None:
        relative = self._relative_sample()
        if relative is None or self._picker_state is None:
            return
        model = {
            "Auto-detect per skin": "auto",
            "Slim / thin arms": "slim",
            "Classic / default arms": "classic",
        }.get(self.model_var.get(), "auto")
        self._picker_state.set_model(relative, model)
        self._refresh_current_metadata()
        self._refresh_hair_preview()
        self._schedule_strip_refresh()

    def _set_current_hair_mode(self) -> None:
        relative = self._relative_sample()
        if relative is None or self._picker_state is None:
            return
        self._picker_state.set_hair_mode(relative, "none" if self.no_visible_hair_var.get() else "auto")
        self._refresh_current_metadata()
        self._refresh_hair_preview()
        self._schedule_strip_refresh()

    def _current_model_is_slim(self, image: Image.Image, path: Path | None = None) -> bool:
        relative = self._relative_sample(path)
        if relative is not None and self._picker_state is not None:
            model = str(self._picker_state.details(relative)["model"])
            if model != "auto":
                return model == "slim"
        return detect_skin_model(image) == "slim"

    def _save_category_corrections(self, relative: str, corrections: dict[tuple[int, int], str]) -> None:
        if self._picker_state is None:
            return
        self._picker_state.set_corrections(relative, corrections)
        self._refresh_current_metadata()
        self._refresh_hair_preview()
        self._schedule_strip_refresh()
        self.status_var.set(f"Saved {len(corrections)} pixel correction(s); the original PNG is unchanged.")

    def _corrections_for(self, path: Path | None) -> dict[tuple[int, int], str]:
        relative = self._relative_sample(path)
        if relative is None or self._picker_state is None:
            return {}
        return self._picker_state.get_corrections(relative)

    def _suppress_hair_for(self, path: Path | None) -> bool:
        relative = self._relative_sample(path)
        if relative is None or self._picker_state is None:
            return False
        return str(self._picker_state.details(relative)["hair_mode"]) == "none"

    def _schedule_strip_refresh(self) -> None:
        if hasattr(self, "workbench"):
            self.workbench.refresh()

    def _style_preview_image(self, image: Image.Image, path: Path | None = None) -> Image.Image:
        target = parse_hex_color(self.hair_var.get())
        tolerance = float(round(self.tolerance_var.get()))
        skin_target = parse_hex_color(self.skin_var.get()) if self.skin_enabled_var.get() else None
        outfit_target = parse_hex_color(self.outfit_var.get()) if self.outfit_enabled_var.get() else None
        accessory_target = parse_hex_color(self.accessory_var.get()) if self.accessory_enabled_var.get() else None
        template = None
        reference_text = self.reference_var.get().strip()
        if self.face_var.get() and reference_text:
            reference_path = Path(reference_text)
            if reference_path.is_file():
                with Image.open(reference_path) as reference:
                    template = make_face_template(reference, tolerance)
        styled, _mask, _was_normalized = style_skin(
            image,
            target,
            tolerance,
            template,
            False,
            skin_target,
            float(round(self.skin_tolerance_var.get())),
            self.body_hair_var.get(),
            self.eyes_over_bangs_var.get(),
            outfit_target,
            accessory_target,
            self.preserve_hat_lashes_var.get(),
            self._corrections_for(path),
            self.adaptive_detection_var.get(),
            self._suppress_hair_for(path),
        )
        return styled

    def _refresh_hair_preview(self, *_args) -> None:
        if not hasattr(self, "hair_preview"):
            return
        if not self._ensure_hair_sample() or self._hair_sample_image is None:
            self._hair_preview_image = None
            self.hair_preview.configure(image="", text="no sample skin")
            self.hair_sample_var.set("choose Sample…")
            return
        try:
            styled = self._style_preview_image(self._hair_sample_image, self._hair_sample_path)
            slim = self._current_model_is_slim(self._hair_sample_image, self._hair_sample_path)
            before = render_player_3d(self._hair_sample_image, 7, slim=slim, yaw_degrees=self._preview_yaw)
            after = render_player_3d(styled, 7, slim=slim, yaw_degrees=self._preview_yaw)
            comparison = Image.new("RGBA", (420, 300), (30, 37, 41, 255))
            before_x = 110 - before.width // 2
            after_x = 310 - after.width // 2
            model_y = max(34, (300 - before.height) // 2 + 11)
            comparison.alpha_composite(before, (before_x, model_y))
            comparison.alpha_composite(after, (after_x, model_y))
            draw = ImageDraw.Draw(comparison)
            draw.text((110, 16), "ORIGINAL", fill=(200, 191, 167, 255), anchor="mm")
            draw.text((310, 16), "STYLED", fill=(244, 201, 93, 255), anchor="mm")
            draw.line((195, 150, 217, 150), fill=(217, 122, 174, 255), width=4)
            draw.polygon(((217, 141), (232, 150), (217, 159)), fill=(217, 122, 174, 255))
            draw.text((210, 284), f"drag to rotate · {round(self._preview_yaw) % 360}° · {'slim' if slim else 'classic'} arms", fill=(200, 191, 167, 255), anchor="mm")
            self._hair_preview_image = ImageTk.PhotoImage(comparison)
            self.hair_preview.configure(image=self._hair_preview_image, text="")
            self._refresh_current_metadata()
            self._schedule_strip_refresh()
        except Exception as exception:
            self._hair_preview_image = None
            self.hair_preview.configure(image="", text=f"preview unavailable\n{str(exception)[:80]}")

    def _refresh_workspace_strip(self) -> None:
        if hasattr(self, "workbench"):
            self.workbench.invalidate()

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

    def _sample_current_skin_tone(self) -> None:
        if not self._ensure_hair_sample() or self._hair_sample_image is None:
            messagebox.showerror("No skin selected", "Choose a skin to sample first.")
            return
        sampled = make_face_template(self._hair_sample_image, float(round(self.tolerance_var.get()))).skin_color
        self.skin_var.set(f"#{sampled[0]:02X}{sampled[1]:02X}{sampled[2]:02X}")
        self.skin_enabled_var.set(True)
        self.status_var.set(f"Sampled the base skin tone from {self._hair_sample_path.name}.")

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
                    wardrobe_metadata=self._picker_state.generation_metadata() if self._picker_state is not None else None,
                    batch_filter=self._batch_key(),
                    flatten_output=True,
                    adaptive_detection=self.adaptive_detection_var.get(),
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
