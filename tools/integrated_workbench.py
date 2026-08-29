"""One-window wardrobe, hair, eye, and pixel workbench for Daily Dress."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageTk

from eye_designer import (
    DEFAULT_IRIS,
    DEFAULT_LASH,
    DEFAULT_SKIN,
    DEFAULT_WHITE,
    classify_reference_eye_features,
    edit_eye_feature,
    mirrored_eye_coordinate,
    preset_eye_features,
    retarget_eye_pixel,
    write_eye_reference,
)
from minecraft_theme import COLORS
from pixel_category_editor import CATEGORY_COLORS
from skin_styler_core import (
    EYE_FEATURE_BOX,
    classify_skin_categories,
    detect_skin_model,
    is_eye_feature_coordinate,
    make_face_template,
    normalize_skin,
    render_front_face,
    render_player_view,
    representative_hair_color,
)
from wardrobe_picker import STATUSES, TAGS

if TYPE_CHECKING:
    from skin_styler_gui import SkinStylerApp


LIBRARY_FILTERS = (
    "Current working set",
    "All skins",
    "Unsorted",
    "Favorites",
    "Maybe",
    "Removed",
    "Dresses",
    "Casual",
    "Seasonal",
)


class IntegratedWorkbench(ttk.Frame):
    """The full lower workbench, embedded in the main Styler window."""

    def __init__(self, parent: tk.Misc, app: "SkinStylerApp") -> None:
        super().__init__(parent)
        self.app = app
        self.mode = "wardrobe"
        self.subview = "gallery"
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="Current working set")
        self.count_var = tk.StringVar(value="Wardrobe library")
        self._refresh_job: str | None = None
        self._signature: object = None
        self._photos: list[ImageTk.PhotoImage] = []
        self._thumbnail_cache: dict[tuple[str, str], ImageTk.PhotoImage] = {}
        self._hair_color_cache: dict[tuple[str, int], tuple[int, int, int] | None] = {}
        self._mode_buttons: dict[str, tk.Button] = {}
        self._scroll_fraction = 0.0

        self.pixel_tool_var = tk.StringVar(value="hair")
        self._pixel_skin: Image.Image | None = None
        self._pixel_classification = None
        self._pixel_corrections: dict[tuple[int, int], str] = {}
        self._pixel_history: list[dict[tuple[int, int], str]] = []
        self._pixel_photo: ImageTk.PhotoImage | None = None

        self.eye_tool_var = tk.StringVar(value="liner")
        self.eye_mirror_var = tk.BooleanVar(value=True)
        self._eye_features: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self._eye_iris: set[tuple[int, int]] = set()
        self._eye_liner: set[tuple[int, int]] = set()
        self._eye_white: set[tuple[int, int]] = set()
        self._eye_representatives: dict[str, tuple[int, int, int]] = {}
        self._eye_skin_color = DEFAULT_SKIN
        self._eye_photo: ImageTk.PhotoImage | None = None

        self._build()
        self.search_var.trace_add("write", lambda *_args: self.invalidate())
        self.filter_var.trace_add("write", lambda *_args: self.invalidate())

    def _build(self) -> None:
        modes = ttk.Frame(self)
        modes.pack(fill="x", pady=(1, 5))
        for mode, label in (
            ("wardrobe", "WARDROBE"),
            ("hair", "REFERENCE"),
            ("eyes", "EYES"),
            ("pixels", "RE-DESIGNATE"),
        ):
            button = tk.Button(
                modes,
                text=label,
                command=lambda chosen=mode: self.set_mode(chosen),
                background=COLORS["stone"],
                activebackground=COLORS["grass"],
                foreground="#151515",
                relief="raised",
                borderwidth=2,
                cursor="hand2",
                font=("TkDefaultFont", 8, "bold"),
            )
            button.pack(side="left", fill="x", expand=True, padx=(0 if not self._mode_buttons else 3, 0))
            self._mode_buttons[mode] = button

        self.search_row = ttk.Frame(self)
        self.search_row.pack(fill="x", pady=(0, 5))
        ttk.Label(self.search_row, text="Find").pack(side="left")
        self.search_entry = ttk.Entry(self.search_row, textvariable=self.search_var, width=14)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.filter_box = ttk.Combobox(
            self.search_row,
            textvariable=self.filter_var,
            values=LIBRARY_FILTERS,
            state="readonly",
            width=18,
        )
        self.filter_box.pack(side="right")
        self.count_label = ttk.Label(self, textvariable=self.count_var, style="Muted.TLabel")
        self.count_label.pack(fill="x", pady=(0, 3))

        self.stage = tk.Frame(self, background=COLORS["slot"], height=210)
        self.stage.pack(fill="both", expand=True)
        self.stage.pack_propagate(False)
        self._paint_mode_buttons()

    def set_mode(self, mode: str, *, subview: str = "gallery") -> None:
        if mode not in self._mode_buttons:
            return
        self.mode = mode
        self.subview = subview
        self.app._set_re_designate_focus(mode == "pixels")
        self._paint_mode_buttons()
        gallery_controls = mode != "pixels" and subview == "gallery"
        if gallery_controls:
            if not self.search_row.winfo_manager():
                self.search_row.pack(fill="x", pady=(0, 5), before=self.count_label)
            self.search_entry.configure(state="normal")
            self.filter_box.configure(state="readonly")
            self.stage.configure(height=210)
        else:
            self.search_row.pack_forget()
            self.stage.configure(height=620 if mode == "pixels" else 245)
        self.invalidate()

    def _paint_mode_buttons(self) -> None:
        for mode, button in self._mode_buttons.items():
            selected = mode == self.mode
            button.configure(
                background=COLORS["grass"] if selected else COLORS["stone"],
                activebackground=COLORS["grass_dark"] if selected else COLORS["grass"],
                foreground=COLORS["cream"] if selected else "#151515",
                relief="sunken" if selected else "raised",
            )

    def invalidate(self) -> None:
        self._signature = None
        self.refresh()

    def refresh(self) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        self._refresh_job = self.after(80, self._finish_refresh)

    def _finish_refresh(self) -> None:
        self._refresh_job = None
        metadata: tuple[object, ...] = ()
        if self.app._picker_state is not None:
            metadata = tuple(
                (
                    self.app._relative_sample(path),
                    tuple(sorted(self.app._picker_state.get(self.app._relative_sample(path) or "").items())),
                    tuple(sorted(self.app._picker_state.get_corrections(self.app._relative_sample(path) or "").items())),
                )
                for path in self.app._sample_paths
            )
        signature = (
            self.mode,
            self.subview,
            self.search_var.get(),
            self.filter_var.get(),
            self.app.preview_batch_var.get(),
            round(float(self.app.tolerance_var.get())),
            round(float(self.app.skin_tolerance_var.get())),
            self.app.body_hair_var.get(),
            tuple(str(path) for path in self.app._sample_paths),
            str(self.app._hair_sample_path),
            self.app.reference_var.get(),
            metadata,
        )
        if signature == self._signature:
            return
        self._signature = signature
        if self.mode == "pixels":
            self._build_pixel_editor()
        elif self.mode == "hair" and self.subview == "sampler":
            self._build_hair_sampler()
        elif self.mode == "eyes" and self.subview == "designer":
            self._build_eye_designer()
        else:
            self._build_gallery()

    def _clear_stage(self) -> None:
        existing_canvas = getattr(self, "gallery_canvas", None)
        if existing_canvas is not None and existing_canvas.winfo_exists():
            self._scroll_fraction = existing_canvas.yview()[0]
        for child in self.stage.winfo_children():
            child.destroy()
        self._photos.clear()

    def _visible_paths(self) -> list[Path]:
        search = self.search_var.get().strip().casefold()
        selected_filter = self.filter_var.get()
        if selected_filter == "Current working set":
            candidates = self.app._working_paths()
        else:
            candidates = list(self.app._sample_paths)
        visible: list[Path] = []
        for path in candidates:
            relative = self.app._relative_sample(path) or path.name
            if search and search not in relative.casefold():
                continue
            state = self.app._picker_state.get(relative) if self.app._picker_state is not None else {"status": "unsorted", "tag": "other"}
            status = state["status"]
            tag = state["tag"]
            if selected_filter == "Unsorted" and status != "unsorted":
                continue
            if selected_filter == "Favorites" and status != "favorite":
                continue
            if selected_filter == "Maybe" and status != "maybe":
                continue
            if selected_filter == "Removed" and status != "remove":
                continue
            if selected_filter in ("Dresses", "Casual", "Seasonal") and tag != selected_filter.casefold():
                continue
            visible.append(path)
        return visible

    def _build_gallery(self) -> None:
        self._clear_stage()
        visible = self._visible_paths()
        instructions = {
            "wardrobe": "Every skin is here · click one to preview, then sort it above",
            "hair": "Pick ONE skin · it sets the preview, starting hair color, and eyes together",
            "eyes": "Click any face to use its eyes as the reference",
        }[self.mode]
        header = ttk.Frame(self.stage, padding=(5, 4, 5, 2))
        header.pack(fill="x")
        ttk.Label(header, text=instructions, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        if self.mode == "hair":
            ttk.Button(
                header,
                text="Adjust exact hair color",
                command=lambda: self.set_mode("hair", subview="sampler"),
                style="Accent.TButton",
            ).pack(side="right")
        elif self.mode == "eyes":
            ttk.Button(
                header,
                text="Design custom",
                command=lambda: self.set_mode("eyes", subview="designer"),
                style="Rose.TButton",
            ).pack(side="right")

        holder = tk.Frame(self.stage, background=COLORS["slot"])
        holder.pack(fill="both", expand=True)
        self.gallery_canvas = tk.Canvas(holder, background=COLORS["slot"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=scrollbar.set)
        self.gallery_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        gallery = tk.Frame(self.gallery_canvas, background=COLORS["slot"])
        gallery_window = self.gallery_canvas.create_window((0, 0), window=gallery, anchor="nw")
        gallery.bind("<Configure>", lambda _event: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")))
        self.gallery_canvas.bind("<Configure>", lambda event: self.gallery_canvas.itemconfigure(gallery_window, width=event.width))
        self.gallery_canvas.bind("<MouseWheel>", self._scroll_gallery)

        for index, path in enumerate(visible):
            relative = self.app._relative_sample(path) or path.name
            state = self.app._picker_state.get(relative) if self.app._picker_state is not None else {"status": "unsorted", "tag": "other"}
            selected = path == self.app._hair_sample_path
            eye_selected = self.mode == "eyes" and self.app.reference_var.get() and Path(self.app.reference_var.get()) == path
            background = STATUSES[state["status"]][1]
            card = tk.Frame(
                gallery,
                width=96,
                height=113,
                background=background,
                highlightthickness=3 if selected or eye_selected else 1,
                highlightbackground=COLORS["water"] if eye_selected else (COLORS["gold"] if selected else COLORS["stone_dark"]),
            )
            card.grid(row=index // 5, column=index % 5, padx=4, pady=4, sticky="n")
            card.grid_propagate(False)
            photo = self._thumbnail(path, self.mode)
            button = tk.Button(
                card,
                image=photo,
                command=lambda chosen=path: self._choose_gallery_item(chosen),
                background=background,
                activebackground=COLORS["grass_dark"],
                relief="flat",
                borderwidth=0,
                cursor="hand2",
            )
            button.pack(pady=(4, 1))
            label = tk.Label(
                card,
                text=self._friendly_name(path.stem),
                background=background,
                foreground=COLORS["cream"],
                wraplength=88,
                font=("TkDefaultFont", 7),
            )
            label.pack(fill="x", padx=2)
            footer_text = f"{STATUSES[state['status']][0]} · {TAGS[state['tag']]}"
            if self.mode == "hair":
                color = self._hair_color(path)
                footer_text = "no visible hair" if color is None else f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
            footer = tk.Label(
                card,
                text=footer_text,
                background=background,
                foreground="#F7E7D1",
                font=("TkDefaultFont", 6),
            )
            footer.pack(side="bottom", fill="x", pady=(1, 3))
            for widget in (card, label, footer):
                widget.bind("<Button-1>", lambda _event, chosen=path: self._choose_gallery_item(chosen))
                widget.bind("<MouseWheel>", self._scroll_gallery)
        for column in range(5):
            gallery.columnconfigure(column, weight=1)
        self.count_var.set(f"{len(visible)} of {len(self.app._sample_paths)} skins shown · scroll for the full library")
        self.after_idle(lambda: self.gallery_canvas.yview_moveto(self._scroll_fraction))

    def _scroll_gallery(self, event: tk.Event) -> str:
        self.gallery_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    @staticmethod
    def _friendly_name(stem: str) -> str:
        friendly = stem.replace("_", " ").replace("-", " ")
        return friendly if len(friendly) <= 19 else friendly[:18].rstrip() + "…"

    def _thumbnail(self, path: Path, mode: str) -> ImageTk.PhotoImage:
        cache_mode = "eyes" if mode == "eyes" else "player"
        key = (str(path), cache_mode)
        cached = self._thumbnail_cache.get(key)
        if cached is not None:
            self._photos.append(cached)
            return cached
        try:
            with Image.open(path) as image:
                normalized, _ = normalize_skin(image)
            if mode == "eyes":
                preview = render_front_face(normalized, 5)
            else:
                preview = render_player_view(normalized, scale=2, slim=detect_skin_model(normalized) == "slim")
        except Exception:
            preview = Image.new("RGBA", (40, 55), (95, 42, 49, 255))
            draw = ImageDraw.Draw(preview)
            draw.line((5, 7, 35, 48), fill=(255, 180, 190, 255), width=4)
            draw.line((35, 7, 5, 48), fill=(255, 180, 190, 255), width=4)
        photo = ImageTk.PhotoImage(preview)
        self._thumbnail_cache[key] = photo
        self._photos.append(photo)
        return photo

    def _hair_color(self, path: Path) -> tuple[int, int, int] | None:
        key = (str(path), round(float(self.app.tolerance_var.get())))
        if key in self._hair_color_cache:
            return self._hair_color_cache[key]
        try:
            with Image.open(path) as image:
                normalized, _ = normalize_skin(image)
            color = representative_hair_color(normalized, float(self.app.tolerance_var.get()))
        except Exception:
            color = None
        self._hair_color_cache[key] = color
        return color

    def _choose_gallery_item(self, path: Path) -> None:
        if self.mode == "hair":
            self.app._use_complete_reference(path)
        else:
            self.app._load_hair_sample(path)
            if self.mode == "eyes":
                self.app._use_face_reference(path)
            self.app._refresh_hair_preview()
        self.invalidate()

    def _build_hair_sampler(self) -> None:
        self._clear_stage()
        self.count_var.set("Exact hair-color eyedropper · the source skin stays untouched")
        header = ttk.Frame(self.stage, padding=(5, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Click one exact, opaque hair pixel on the texture.", style="Muted.TLabel").pack(side="left")
        ttk.Button(header, text="Back to hair library", command=lambda: self.set_mode("hair")).pack(side="right")
        if self.app._hair_sample_path is None or self.app._hair_sample_image is None:
            ttk.Label(self.stage, text="Choose a skin in the Hair library first.").pack(pady=50)
            return
        scale = 3
        photo = ImageTk.PhotoImage(self.app._hair_sample_image.resize((64 * scale, 64 * scale), Image.Resampling.NEAREST))
        self._photos.append(photo)
        canvas = tk.Canvas(
            self.stage,
            width=64 * scale,
            height=64 * scale,
            background=COLORS["slot"],
            highlightthickness=2,
            highlightbackground=COLORS["gold"],
            cursor="crosshair",
        )
        canvas.pack(pady=3)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.bind("<Button-1>", lambda event: self._pick_hair_pixel(event, scale))

    def _pick_hair_pixel(self, event: tk.Event, scale: int) -> None:
        if self.app._hair_sample_image is None:
            return
        coordinate = (min(63, max(0, int(event.x) // scale)), min(63, max(0, int(event.y) // scale)))
        red, green, blue, alpha = self.app._hair_sample_image.getpixel(coordinate)
        if alpha < 48:
            self.app.status_var.set("That pixel is transparent; choose a visible hair pixel.")
            return
        self.app._set_target_hair_rgb((red, green, blue))
        self.app.status_var.set(f"Exact hair color sampled at {coordinate}: #{red:02X}{green:02X}{blue:02X}")
        self.set_mode("hair")

    def _build_pixel_editor(self) -> None:
        self._clear_stage()
        self.count_var.set("RE-DESIGNATE MATERIALS · paint only what automatic detection got wrong")
        if self.app._hair_sample_path is None or self.app._hair_sample_image is None or self.app._picker_state is None:
            ttk.Label(self.stage, text="Choose a wardrobe skin before correcting pixels.").pack(pady=60)
            return
        relative = self.app._relative_sample()
        if relative is None:
            ttk.Label(self.stage, text="Pixel corrections are saved only for skins in this wardrobe.").pack(pady=60)
            return
        self._pixel_skin = self.app._hair_sample_image.copy()
        self._pixel_classification = classify_skin_categories(
            self._pixel_skin,
            float(round(self.app.tolerance_var.get())),
            float(round(self.app.skin_tolerance_var.get())),
            self.app.body_hair_var.get(),
        )
        self._pixel_corrections = self.app._picker_state.get_corrections(relative)
        self._pixel_history = []

        body = ttk.Frame(self.stage, padding=4)
        body.pack(fill="both", expand=True)
        scale = 6
        self.pixel_canvas = tk.Canvas(
            body,
            width=64 * scale,
            height=64 * scale,
            background=COLORS["slot"],
            highlightthickness=2,
            highlightbackground=COLORS["stone_dark"],
            cursor="crosshair",
        )
        self.pixel_canvas.bind("<ButtonPress-1>", lambda event: self._pixel_paint(event, scale))
        self.pixel_canvas.bind("<B1-Motion>", lambda event: self._pixel_paint(event, scale))
        self.pixel_canvas.bind("<ButtonRelease-1>", lambda _event: self._save_pixels())
        self.pixel_canvas.bind("<ButtonPress-3>", lambda event: self._pixel_erase(event, scale))
        self.pixel_canvas.bind("<B3-Motion>", lambda event: self._pixel_erase(event, scale))
        self.pixel_canvas.bind("<ButtonRelease-3>", lambda _event: self._save_pixels())

        tools = ttk.Frame(body, padding=(4, 0, 4, 0))
        tools.pack(side="top", fill="x")
        for index, (category, label) in enumerate((
            ("hair", "Hair"),
            ("skin", "Skin"),
            ("outfit", "Outfit"),
            ("accessory", "Accessory"),
            ("eyes", "Eyes"),
            ("ignore", "Ignore"),
        )):
            ttk.Radiobutton(tools, text=label, value=category, variable=self.pixel_tool_var).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 4)
            )
        buttons = ttk.Frame(tools)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(buttons, text="Undo", command=self._undo_pixels).pack(side="left")
        ttk.Button(buttons, text="Clear", command=self._clear_pixels, style="Danger.TButton").pack(side="left", padx=(4, 0))
        ttk.Label(tools, text="Left paints · right restores auto\nSaved automatically", style="Muted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(3, 0)
        )
        self.pixel_canvas.pack(side="top", pady=(8, 0))
        self._redraw_pixels(scale)

    def _pixel_map(self) -> dict[tuple[int, int], str]:
        result: dict[tuple[int, int], str] = {}
        if self._pixel_classification is not None:
            for category in ("outfit", "skin", "hair", "accessory", "eyes"):
                for coordinate in getattr(self._pixel_classification, category):
                    result[coordinate] = category
        result.update(self._pixel_corrections)
        return result

    def _redraw_pixels(self, scale: int = 6) -> None:
        if self._pixel_skin is None or not hasattr(self, "pixel_canvas"):
            return
        overlay = Image.new("RGBA", self._pixel_skin.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for coordinate, category in self._pixel_map().items():
            color = CATEGORY_COLORS.get(category)
            if color is not None:
                draw.point(coordinate, fill=color)
        preview = Image.alpha_composite(self._pixel_skin, overlay).resize((64 * scale, 64 * scale), Image.Resampling.NEAREST)
        self._pixel_photo = ImageTk.PhotoImage(preview)
        self.pixel_canvas.delete("all")
        self.pixel_canvas.create_image(0, 0, image=self._pixel_photo, anchor="nw")
        for grid in range(0, 65, 8):
            position = grid * scale
            self.pixel_canvas.create_line(position, 0, position, 64 * scale, fill="#61584D")
            self.pixel_canvas.create_line(0, position, 64 * scale, position, fill="#61584D")

    def _pixel_coordinate(self, event: tk.Event, scale: int) -> tuple[int, int]:
        return min(63, max(0, int(event.x) // scale)), min(63, max(0, int(event.y) // scale))

    def _remember_pixels(self, event: tk.Event) -> None:
        if str(event.type) in ("4", "ButtonPress"):
            self._pixel_history.append(dict(self._pixel_corrections))
            self._pixel_history = self._pixel_history[-100:]

    def _pixel_paint(self, event: tk.Event, scale: int) -> None:
        if self._pixel_skin is None:
            return
        coordinate = self._pixel_coordinate(event, scale)
        if self._pixel_skin.getpixel(coordinate)[3] < 48:
            return
        self._remember_pixels(event)
        self._pixel_corrections[coordinate] = self.pixel_tool_var.get()
        self._redraw_pixels(scale)

    def _pixel_erase(self, event: tk.Event, scale: int) -> None:
        coordinate = self._pixel_coordinate(event, scale)
        self._remember_pixels(event)
        if coordinate in self._pixel_corrections:
            self._pixel_corrections.pop(coordinate)
            self._redraw_pixels(scale)

    def _save_pixels(self) -> None:
        relative = self.app._relative_sample()
        if relative is not None:
            self.app._save_category_corrections(relative, dict(self._pixel_corrections))

    def _undo_pixels(self) -> None:
        if not self._pixel_history:
            return
        self._pixel_corrections = self._pixel_history.pop()
        self._redraw_pixels()
        self._save_pixels()

    def _clear_pixels(self) -> None:
        if not self._pixel_corrections:
            return
        if not messagebox.askyesno("Clear corrections?", "Restore automatic categories for this skin?", parent=self.app):
            return
        self._pixel_history.append(dict(self._pixel_corrections))
        self._pixel_corrections.clear()
        self._redraw_pixels()
        self._save_pixels()

    def _load_eye_design(self) -> None:
        reference_text = self.app.reference_var.get().strip()
        reference = Path(reference_text) if reference_text else None
        if reference is not None and reference.is_file():
            try:
                with Image.open(reference) as image:
                    template = make_face_template(image)
                self._eye_skin_color = template.skin_color
                self._eye_features = {
                    coordinate: color
                    for coordinate, color in template.features.items()
                    if is_eye_feature_coordinate(*coordinate)
                }
            except Exception:
                self._eye_features = {}
        else:
            self._eye_features = {}
        if not self._eye_features:
            self._eye_skin_color = DEFAULT_SKIN
            self._eye_features = preset_eye_features(
                "Soft lashes",
                self._hex_rgb(DEFAULT_IRIS),
                self._hex_rgb(DEFAULT_LASH),
                self._hex_rgb(DEFAULT_WHITE),
            )
        (
            self._eye_iris,
            self._eye_liner,
            self._eye_white,
            iris,
            liner,
            white,
        ) = classify_reference_eye_features(self._eye_features)
        self._eye_representatives = {"iris": iris, "liner": liner, "white": white}

    @staticmethod
    def _hex_rgb(value: str) -> tuple[int, int, int]:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]

    def _build_eye_designer(self) -> None:
        self._clear_stage()
        self._load_eye_design()
        self.count_var.set("Custom eye designer · edit here, preview in the 3D view above")
        body = ttk.Frame(self.stage, padding=4)
        body.pack(fill="both", expand=True)
        scale = 23
        self.eye_canvas = tk.Canvas(
            body,
            width=8 * scale,
            height=8 * scale,
            background=COLORS["slot"],
            highlightthickness=2,
            highlightbackground=COLORS["rose"],
            cursor="pencil",
        )
        self.eye_canvas.pack(side="left")
        self.eye_canvas.bind("<Button-1>", lambda event: self._paint_eye(event, scale, False))
        self.eye_canvas.bind("<B1-Motion>", lambda event: self._paint_eye(event, scale, False))
        self.eye_canvas.bind("<Button-3>", lambda event: self._paint_eye(event, scale, True))
        self.eye_canvas.bind("<B3-Motion>", lambda event: self._paint_eye(event, scale, True))

        tools = ttk.Frame(body, padding=(8, 0, 0, 0), width=270)
        tools.pack(side="left", fill="both", expand=True)
        tools.grid_propagate(False)
        for index, (material, label) in enumerate((("iris", "Iris"), ("liner", "Liner / lashes"), ("white", "Eye white"), ("eraser", "Eraser"))):
            ttk.Radiobutton(tools, text=label, value=material, variable=self.eye_tool_var).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 3)
            )
        ttk.Checkbutton(tools, text="Mirror both eyes", variable=self.eye_mirror_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(1, 2)
        )
        colors = ttk.Frame(tools)
        colors.grid(row=3, column=0, columnspan=2, sticky="ew")
        for material, label in (("iris", "Iris"), ("liner", "Liner"), ("white", "White")):
            ttk.Button(
                colors,
                text=label,
                width=5,
                command=lambda chosen=material: self._choose_eye_color(chosen),
            ).pack(side="left", fill="x", expand=True, padx=(0, 2))
        action = ttk.Frame(tools)
        action.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        ttk.Button(action, text="Eye library", command=lambda: self.set_mode("eyes")).pack(side="left")
        ttk.Button(action, text="Use eyes", command=self._save_eye_design, style="Rose.TButton").pack(side="right")
        self._redraw_eyes(scale)

    def _redraw_eyes(self, scale: int = 23) -> None:
        if not hasattr(self, "eye_canvas"):
            return
        self.eye_canvas.delete("all")
        _left, top, _right, bottom = EYE_FEATURE_BOX
        for local_y in range(8):
            for local_x in range(8):
                coordinate = (8 + local_x, 8 + local_y)
                color = self._eye_features.get(coordinate, self._eye_skin_color + (255,))
                fill = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
                editable = is_eye_feature_coordinate(*coordinate)
                self.eye_canvas.create_rectangle(
                    local_x * scale,
                    local_y * scale,
                    (local_x + 1) * scale,
                    (local_y + 1) * scale,
                    fill=fill,
                    outline="#F3C6DC" if editable else "#A98472",
                    width=2 if editable else 1,
                )
        for left, right in ((8, 11), (13, 16)):
            self.eye_canvas.create_rectangle(
                (left - 8) * scale,
                (top - 8) * scale,
                (right - 8) * scale,
                (bottom - 8) * scale,
                outline=COLORS["gold"],
                width=3,
            )

    def _paint_eye(self, event: tk.Event, scale: int, erase: bool) -> None:
        coordinate = (8 + min(7, max(0, int(event.x) // scale)), 8 + min(7, max(0, int(event.y) // scale)))
        material = "eraser" if erase else self.eye_tool_var.get()
        sets = {"iris": self._eye_iris, "liner": self._eye_liner, "white": self._eye_white}
        changed = edit_eye_feature(
            self._eye_features,
            self._eye_iris,
            self._eye_liner,
            self._eye_white,
            coordinate,
            material,
            self._eye_representatives,
        )
        if self.eye_mirror_var.get():
            mirrored = mirrored_eye_coordinate(coordinate)
            if mirrored != coordinate:
                changed = edit_eye_feature(
                    self._eye_features,
                    sets["iris"],
                    sets["liner"],
                    sets["white"],
                    mirrored,
                    material,
                    self._eye_representatives,
                ) or changed
        if changed:
            self._redraw_eyes(scale)

    def _choose_eye_color(self, material: str) -> None:
        old = self._eye_representatives[material]
        chosen = colorchooser.askcolor(
            color=f"#{old[0]:02X}{old[1]:02X}{old[2]:02X}",
            title=f"Choose {material} color",
            parent=self.app,
        )[1]
        if not chosen:
            return
        target = self._hex_rgb(chosen)
        coordinates = {"iris": self._eye_iris, "liner": self._eye_liner, "white": self._eye_white}[material]
        for coordinate in coordinates:
            if coordinate in self._eye_features:
                self._eye_features[coordinate] = retarget_eye_pixel(self._eye_features[coordinate], old, target)
        self._eye_representatives[material] = target
        self._redraw_eyes()

    def _save_eye_design(self) -> None:
        if not self._eye_features:
            return
        try:
            write_eye_reference(self.app.custom_eye_reference, self._eye_features, self._eye_skin_color)
            materials = {
                f"{x},{y}": material
                for material, coordinates in (("iris", self._eye_iris), ("liner", self._eye_liner), ("white", self._eye_white))
                for x, y in sorted(coordinates)
                if (x, y) in self._eye_features
            }
            self.app.custom_eye_reference.with_suffix(".json").write_text(
                json.dumps({"materials": materials}, indent=2), encoding="utf-8"
            )
        except Exception as exception:
            messagebox.showerror("Could not save eye design", str(exception), parent=self.app)
            return
        self.app._use_face_reference(self.app.custom_eye_reference)
        self.app.status_var.set("Custom eyes saved and applied. The live 3D preview is already updated.")
        self.invalidate()
