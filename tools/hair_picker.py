"""Hair-reference gallery and pixel eyedropper for the Daily Dress Styler."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageTk

from minecraft_theme import COLORS
from skin_styler_core import detect_skin_model, normalize_skin, render_player_view, representative_hair_color


@dataclass(frozen=True)
class HairEntry:
    path: Path
    relative: str


class PixelEyedropper(tk.Toplevel):
    """Choose an exact source-skin pixel as a target color."""

    def __init__(self, parent: tk.Misc, path: Path, choose: Callable[[tuple[int, int, int]], None]) -> None:
        super().__init__(parent)
        self.path = path
        self.choose = choose
        with Image.open(path) as image:
            self.skin, _ = normalize_skin(image)
        self.scale = 9
        self.photo = ImageTk.PhotoImage(self.skin.resize((64 * self.scale, 64 * self.scale), Image.Resampling.NEAREST))
        self.title(f"Hair-color eyedropper — {path.stem}")
        self.configure(background=COLORS["void"])
        ttk.Label(self, text="EYEDROPPER", style="Step.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            self,
            text="Click a hair pixel on the skin texture. Transparent pixels are ignored.",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        self.canvas = tk.Canvas(
            self,
            width=64 * self.scale,
            height=64 * self.scale,
            background=COLORS["slot"],
            highlightthickness=2,
            highlightbackground=COLORS["stone_dark"],
            cursor="crosshair",
        )
        self.canvas.pack(padx=12, pady=(0, 12))
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.bind("<Button-1>", self._pick)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _pick(self, event: tk.Event) -> None:
        x = min(63, max(0, int(event.x) // self.scale))
        y = min(63, max(0, int(event.y) // self.scale))
        red, green, blue, alpha = self.skin.getpixel((x, y))
        if alpha < 48:
            return
        self.choose((red, green, blue))
        self.destroy()


class HairPicker(tk.Toplevel):
    """A gallery parallel to Eye Gallery, focused on hairstyle + base color."""

    def __init__(
        self,
        parent: tk.Misc,
        source: Path,
        choose: Callable[[Path, tuple[int, int, int]], None],
    ) -> None:
        super().__init__(parent)
        self.source = source.expanduser().resolve()
        self.choose = choose
        self.entries = [
            HairEntry(path, path.relative_to(self.source).as_posix())
            for path in sorted(self.source.rglob("*.png"), key=lambda item: item.name.casefold())
        ]
        self.search_var = tk.StringVar()
        self.photos: list[ImageTk.PhotoImage] = []
        self.title("Daily Dress Hair Gallery ✿")
        self.geometry("1080x780")
        self.minsize(760, 520)
        self.configure(background=COLORS["void"])
        self._build()
        self.search_var.trace_add("write", lambda *_args: self._refresh())
        self._refresh()

    def _build(self) -> None:
        header = ttk.Frame(self, padding=14)
        header.pack(fill="x")
        ttk.Label(header, text="HAIR GALLERY", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Choose a reference hairstyle. Its detected hair becomes the preview sample and starting Target Hair Color.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))
        ttk.Label(header, text="Search").grid(row=2, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.search_var).grid(row=2, column=1, sticky="ew", padx=(8, 0))
        header.columnconfigure(1, weight=1)

        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.canvas = tk.Canvas(holder, background=COLORS["slot"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.gallery = tk.Frame(self.canvas, background=COLORS["slot"])
        self.window = self.canvas.create_window((0, 0), window=self.gallery, anchor="nw")
        self.gallery.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window, width=event.width))
        self.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-event.delta / 120), "units"))

    def _refresh(self) -> None:
        for child in self.gallery.winfo_children():
            child.destroy()
        self.photos.clear()
        search = self.search_var.get().strip().casefold()
        visible = [entry for entry in self.entries if not search or search in entry.relative.casefold()]
        columns = 6
        for index, entry in enumerate(visible):
            try:
                with Image.open(entry.path) as image:
                    preview = render_player_view(image, scale=4, slim=detect_skin_model(image) == "slim")
                    color = representative_hair_color(image)
            except Exception:
                continue
            photo = ImageTk.PhotoImage(preview)
            self.photos.append(photo)
            card = tk.Frame(
                self.gallery,
                background=COLORS["panel_alt"],
                highlightthickness=2,
                highlightbackground=COLORS["stone_dark"],
            )
            card.grid(row=index // columns, column=index % columns, padx=6, pady=6, sticky="n")
            button = tk.Button(
                card,
                image=photo,
                command=lambda item=entry, sampled=color: self._use(item, sampled),
                background=COLORS["panel_alt"],
                activebackground=COLORS["grass_dark"],
                relief="flat",
                borderwidth=0,
                cursor="hand2",
            )
            button.pack(padx=8, pady=(8, 3))
            tk.Label(
                card,
                text=entry.path.stem[:20],
                background=COLORS["panel_alt"],
                foreground=COLORS["cream"],
                wraplength=125,
            ).pack(fill="x", padx=4)
            swatch = tk.Label(
                card,
                text="  sampled hair  ",
                background=f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}",
                foreground="white" if sum(color) < 330 else "black",
            )
            swatch.pack(fill="x", padx=6, pady=(3, 3))
            ttk.Button(
                card,
                text="Eyedropper…",
                command=lambda item=entry: PixelEyedropper(self, item.path, lambda rgb, chosen=item: self._use(chosen, rgb)),
            ).pack(fill="x", padx=6, pady=(0, 7))
        for column in range(columns):
            self.gallery.columnconfigure(column, weight=1)

    def _use(self, entry: HairEntry, color: tuple[int, int, int]) -> None:
        self.choose(entry.path, color)
        self.destroy()
