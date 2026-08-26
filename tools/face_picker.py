"""Wardrobe gallery for choosing Daily Dress reference eyes."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

from skin_styler_core import render_front_face


@dataclass(frozen=True)
class FaceEntry:
    path: Path
    relative: str


def discover_faces(source: Path) -> list[FaceEntry]:
    source = source.expanduser().resolve()
    return [
        FaceEntry(path, path.relative_to(source).as_posix())
        for path in sorted(source.rglob("*.png"), key=lambda item: item.name.casefold())
    ]


class FacePicker(tk.Toplevel):
    def __init__(self, parent: tk.Misc, source: Path, choose: Callable[[Path], None]) -> None:
        super().__init__(parent)
        self.source = source.expanduser().resolve()
        self.choose = choose
        self.entries = discover_faces(self.source)
        self.entry_by_relative = {entry.relative: entry for entry in self.entries}
        self.visible_entries: list[FaceEntry] = []
        self.photo_cache: dict[str, ImageTk.PhotoImage] = {}
        self.card_widgets: dict[str, tk.Frame] = {}
        self.detail_image: ImageTk.PhotoImage | None = None
        self.selected_relative: str | None = None

        self.title("Choose Daily Dress Eyes ✿")
        self.geometry("1040x790")
        self.minsize(850, 650)
        self.configure(background="#25272B")

        self.search_var = tk.StringVar()
        self.count_var = tk.StringVar()
        self.name_var = tk.StringVar(value="Choose some eyes")
        self.path_var = tk.StringVar()

        self._build()
        self.search_var.trace_add("write", lambda *_args: self._refresh_grid())
        self.bind("<KeyPress>", self._on_key)
        self._refresh_grid()
        self.after(50, self.focus_force)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(16, 13, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Choose the reference eyes", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            header,
            text="The full face is shown for context, but only its eye-area pixels are used. Double-click one to choose it.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 9))
        ttk.Label(header, text="Search").grid(row=2, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.search_var).grid(row=2, column=1, sticky="ew", padx=(8, 12))
        ttk.Label(header, textvariable=self.count_var).grid(row=2, column=2, sticky="e")
        header.columnconfigure(1, weight=1)

        content = ttk.Panedwindow(self, orient="horizontal")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        gallery_holder = ttk.Frame(content)
        content.add(gallery_holder, weight=4)
        self.canvas = tk.Canvas(gallery_holder, background="#202226", highlightthickness=0)
        scrollbar = ttk.Scrollbar(gallery_holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.gallery = tk.Frame(self.canvas, background="#202226")
        self.gallery_window = self.canvas.create_window((0, 0), window=self.gallery, anchor="nw")
        self.gallery.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.gallery_window, width=event.width),
        )
        self.bind("<MouseWheel>", self._on_mousewheel)

        detail = ttk.Frame(content, padding=(16, 10))
        content.add(detail, weight=1)
        ttk.Label(detail, text="Selected eyes", font=("Segoe UI", 11, "bold")).pack(fill="x")
        ttk.Label(detail, textvariable=self.name_var, font=("Segoe UI", 12, "bold"), wraplength=360).pack(fill="x", pady=(7, 1))
        ttk.Label(detail, textvariable=self.path_var, foreground="#777777", wraplength=360).pack(fill="x", pady=(0, 12))

        preview_box = tk.Frame(detail, width=214, height=214, background="#303238", relief="solid", borderwidth=1)
        preview_box.pack(pady=(4, 14))
        preview_box.pack_propagate(False)
        self.detail_preview = tk.Label(preview_box, text="face context", background="#303238", foreground="#CCCCCC")
        self.detail_preview.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(detail, text="Use these reference eyes", command=self._use_selected).pack(fill="x", pady=(4, 7))
        ttk.Label(
            detail,
            text="Only eyes are copied. Each destination keeps its own bangs, hairbands, forehead details, nose, and mouth—even when hair crosses an eye.",
            foreground="#777777",
            wraplength=280,
        ).pack(fill="x")

        nav = ttk.Frame(detail)
        nav.pack(fill="x", pady=(18, 0))
        ttk.Button(nav, text="← Previous", command=lambda: self._move_selection(-1)).pack(side="left")
        ttk.Button(nav, text="Next →", command=lambda: self._move_selection(1)).pack(side="right")

        footer = ttk.Frame(self, padding=(16, 3, 16, 12))
        footer.pack(fill="x")
        ttk.Label(footer, text="Enter uses the selected eyes · Arrow keys move · Nothing is changed in the wardrobe").pack(side="left")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _filtered_entries(self) -> list[FaceEntry]:
        search = self.search_var.get().strip().casefold()
        return [entry for entry in self.entries if not search or search in entry.relative.casefold()]

    def _refresh_grid(self) -> None:
        for child in self.gallery.winfo_children():
            child.destroy()
        self.card_widgets.clear()
        self.visible_entries = self._filtered_entries()
        columns = 7
        for index, entry in enumerate(self.visible_entries):
            card = tk.Frame(
                self.gallery,
                background="#464A52",
                width=100,
                height=116,
                highlightthickness=2,
                highlightbackground="#202226",
            )
            card.grid(row=index // columns, column=index % columns, padx=5, pady=5, sticky="n")
            card.grid_propagate(False)
            photo = self._face_photo(entry, 8)
            button = tk.Button(
                card,
                image=photo,
                command=lambda relative=entry.relative: self._select(relative),
                background="#464A52",
                activebackground="#464A52",
                relief="flat",
                borderwidth=0,
                cursor="hand2",
            )
            button.pack(pady=(5, 2))
            label = tk.Label(
                card,
                text=self._card_name(entry.path.stem),
                background="#464A52",
                foreground="white",
                wraplength=92,
                font=("Segoe UI", 8),
            )
            label.pack(fill="x", padx=2)
            for widget in (card, button, label):
                widget.bind("<Double-Button-1>", lambda _event, relative=entry.relative: self._use_relative(relative))
                if widget is not button:
                    widget.bind("<Button-1>", lambda _event, relative=entry.relative: self._select(relative))
            self.card_widgets[entry.relative] = card

        for column in range(columns):
            self.gallery.columnconfigure(column, weight=1)
        self.count_var.set(f"Showing {len(self.visible_entries)} of {len(self.entries)} eye choices")
        if not self.visible_entries:
            self.selected_relative = None
            self.name_var.set("No eye choices match this search")
            self.path_var.set("")
            self.detail_image = None
            self.detail_preview.configure(image="", text="no matches")
            return
        target = self.selected_relative if self.selected_relative in self.card_widgets else self.visible_entries[0].relative
        self._select(target)

    @staticmethod
    def _card_name(stem: str) -> str:
        friendly = stem.replace("_", " ").replace("-", " ")
        return friendly if len(friendly) <= 22 else friendly[:21].rstrip() + "…"

    def _face_photo(self, entry: FaceEntry, scale: int) -> ImageTk.PhotoImage:
        key = f"{entry.relative}:{scale}"
        cached = self.photo_cache.get(key)
        if cached is not None:
            return cached
        try:
            with Image.open(entry.path) as image:
                face = render_front_face(image, scale)
        except Exception:
            face = Image.new("RGBA", (8 * scale, 8 * scale), (70, 30, 38, 255))
            draw = ImageDraw.Draw(face)
            draw.line((8, 8, face.width - 8, face.height - 8), fill=(255, 150, 160, 255), width=max(2, scale // 2))
            draw.line((face.width - 8, 8, 8, face.height - 8), fill=(255, 150, 160, 255), width=max(2, scale // 2))
        photo = ImageTk.PhotoImage(face)
        self.photo_cache[key] = photo
        return photo

    def _select(self, relative: str) -> None:
        entry = self.entry_by_relative.get(relative)
        if entry is None:
            return
        previous = self.card_widgets.get(self.selected_relative or "")
        if previous is not None:
            previous.configure(highlightbackground="#202226")
        self.selected_relative = relative
        current = self.card_widgets.get(relative)
        if current is not None:
            current.configure(highlightbackground="#F3C6DC")
        self.name_var.set(entry.path.stem)
        self.path_var.set(entry.relative)
        self.detail_image = self._face_photo(entry, 24)
        self.detail_preview.configure(image=self.detail_image, text="")

    def _move_selection(self, change: int) -> None:
        if not self.visible_entries:
            return
        try:
            index = next(i for i, entry in enumerate(self.visible_entries) if entry.relative == self.selected_relative)
        except StopIteration:
            index = 0
        self._select(self.visible_entries[(index + change) % len(self.visible_entries)].relative)

    def _use_relative(self, relative: str) -> None:
        self._select(relative)
        self._use_selected()

    def _use_selected(self) -> None:
        if self.selected_relative is None:
            return
        entry = self.entry_by_relative[self.selected_relative]
        self.choose(entry.path)
        self.destroy()

    def _on_key(self, event) -> str | None:
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry)):
            return None
        key = event.keysym.casefold()
        if key in {"return", "kp_enter"}:
            self._use_selected()
            return "break"
        movements = {"left": -1, "right": 1, "up": -7, "down": 7}
        if key in movements:
            self._move_selection(movements[key])
            return "break"
        if key == "escape":
            self.destroy()
            return "break"
        return None
