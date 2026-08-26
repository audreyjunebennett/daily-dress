"""Manual material-category correction for difficult Minecraft skins."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

from minecraft_theme import COLORS
from skin_styler_core import SkinClassification, classify_skin_categories, normalize_skin


CATEGORY_COLORS = {
    "hair": (218, 93, 170, 170),
    "skin": (247, 181, 128, 170),
    "outfit": (89, 161, 235, 170),
    "accessory": (246, 204, 82, 170),
    "eyes": (91, 226, 211, 185),
    "ignore": (80, 80, 80, 205),
}


class PixelCategoryEditor(tk.Toplevel):
    """Paint sparse corrections over an automatic full-skin classification."""

    def __init__(
        self,
        parent: tk.Misc,
        path: Path,
        corrections: dict[tuple[int, int], str],
        save: Callable[[dict[tuple[int, int], str]], None],
        *,
        tolerance: float = 42.0,
        skin_tolerance: float = 24.0,
        include_body_hair: bool = True,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.save_callback = save
        with Image.open(path) as image:
            self.skin, _ = normalize_skin(image)
        self.classification = classify_skin_categories(self.skin, tolerance, skin_tolerance, include_body_hair)
        self.corrections = dict(corrections)
        self.history: list[dict[tuple[int, int], str]] = []
        self.tool_var = tk.StringVar(value="hair")
        self.message_var = tk.StringVar(value="Paint only the pixels auto-detection got wrong. Right-click erases a correction.")
        self.scale = 9
        self.photo: ImageTk.PhotoImage | None = None
        self.title(f"Pixel categories — {path.stem}")
        self.geometry("920x720")
        self.minsize(760, 640)
        self.configure(background=COLORS["void"])
        self._build()
        self._redraw()
        self.bind("<Control-z>", self._undo)
        self.transient(parent.winfo_toplevel())

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill="x")
        ttk.Label(header, text="PIXEL CATEGORY WORKBENCH", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Automatic categories are already filled in. Touch up only the odd hair, skin, outfit, eye, or accessory pixel.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(self, padding=(14, 4, 14, 8))
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body,
            width=64 * self.scale,
            height=64 * self.scale,
            background=COLORS["slot"],
            highlightthickness=2,
            highlightbackground=COLORS["stone_dark"],
            cursor="crosshair",
        )
        self.canvas.pack(side="left", fill="none", expand=False)
        self.canvas.bind("<Button-1>", self._paint)
        self.canvas.bind("<B1-Motion>", self._paint)
        self.canvas.bind("<Button-3>", self._erase)
        self.canvas.bind("<B3-Motion>", self._erase)

        tools = ttk.LabelFrame(body, text="Paint material", padding=10)
        tools.pack(side="left", fill="y", padx=(14, 0))
        for category, label in (
            ("hair", "Hair"),
            ("skin", "Skin"),
            ("outfit", "Outfit"),
            ("accessory", "Accessory"),
            ("eyes", "Eyes"),
            ("ignore", "Ignore / other"),
        ):
            row = ttk.Radiobutton(tools, text=label, value=category, variable=self.tool_var)
            row.pack(anchor="w", fill="x", pady=3)
            color = CATEGORY_COLORS[category]
            tk.Frame(tools, width=22, height=5, background=f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}").pack(fill="x")
        ttk.Separator(tools).pack(fill="x", pady=10)
        ttk.Button(tools, text="Undo (Ctrl+Z)", command=self._undo).pack(fill="x", pady=3)
        ttk.Button(tools, text="Clear my corrections", command=self._clear, style="Danger.TButton").pack(fill="x", pady=3)
        ttk.Label(
            tools,
            text="Left-drag paints.\nRight-drag restores auto-detection.\n\nThe original PNG is never edited.",
            style="Muted.TLabel",
            wraplength=190,
        ).pack(fill="x", pady=(12, 0))

        footer = ttk.Frame(self, padding=(14, 4, 14, 14))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.message_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Save corrections", command=self._save, style="Accent.TButton").pack(side="right")

    def _automatic_map(self) -> dict[tuple[int, int], str]:
        result: dict[tuple[int, int], str] = {}
        for category in ("outfit", "skin", "hair", "accessory", "eyes"):
            for coordinate in getattr(self.classification, category):
                result[coordinate] = category
        return result

    def _redraw(self) -> None:
        preview = self.skin.copy()
        overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        categories = self._automatic_map()
        categories.update(self.corrections)
        for (x, y), category in categories.items():
            color = CATEGORY_COLORS.get(category)
            if color is not None:
                draw.point((x, y), fill=color)
        preview = Image.alpha_composite(preview, overlay)
        preview = preview.resize((64 * self.scale, 64 * self.scale), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for grid in range(0, 65, 8):
            position = grid * self.scale
            self.canvas.create_line(position, 0, position, 64 * self.scale, fill="#61584D")
            self.canvas.create_line(0, position, 64 * self.scale, position, fill="#61584D")
        self.message_var.set(f"{len(self.corrections)} manual pixel correction(s) · {self.path.name}")

    def _coordinate(self, event: tk.Event) -> tuple[int, int]:
        return min(63, max(0, int(event.x) // self.scale)), min(63, max(0, int(event.y) // self.scale))

    def _remember(self) -> None:
        if not self.history or self.history[-1] != self.corrections:
            self.history.append(dict(self.corrections))
            self.history = self.history[-200:]

    def _paint(self, event: tk.Event) -> None:
        coordinate = self._coordinate(event)
        if self.skin.getpixel(coordinate)[3] < 48:
            return
        if str(event.type) in ("4", "ButtonPress"):
            self._remember()
        self.corrections[coordinate] = self.tool_var.get()
        self._redraw()

    def _erase(self, event: tk.Event) -> None:
        coordinate = self._coordinate(event)
        if str(event.type) in ("4", "ButtonPress"):
            self._remember()
        if coordinate in self.corrections:
            self.corrections.pop(coordinate)
            self._redraw()

    def _undo(self, _event: tk.Event | None = None) -> str:
        if self.history:
            self.corrections = self.history.pop()
            self._redraw()
        return "break"

    def _clear(self) -> None:
        if not self.corrections:
            return
        if messagebox.askyesno("Clear corrections?", "Restore automatic categories for every pixel on this skin?", parent=self):
            self._remember()
            self.corrections.clear()
            self._redraw()

    def _save(self) -> None:
        try:
            self.save_callback(dict(self.corrections))
        except OSError as exception:
            messagebox.showerror("Could not save corrections", str(exception), parent=self)
            return
        self.destroy()
