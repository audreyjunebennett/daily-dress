"""Visual, non-destructive wardrobe organizer for Daily Dress skins."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

from skin_styler_core import detect_skin_model, normalize_skin, render_player_view


STATUSES = {
    "unsorted": ("Unsorted", "#454A52"),
    "favorite": ("Favorite", "#A83F70"),
    "maybe": ("Maybe", "#9A7435"),
    "remove": ("Remove", "#77434A"),
}

TAGS = {
    "other": "Other",
    "dresses": "Dresses",
    "casual": "Casual",
    "seasonal": "Seasonal",
}

FILTERS = {
    "All skins": None,
    "Unsorted": "unsorted",
    "Favorites": "favorite",
    "Favorite dresses": "favorite+dresses",
    "Favorite casual": "favorite+casual",
    "Favorite seasonal": "favorite+seasonal",
    "Dresses": "tag:dresses",
    "Casual": "tag:casual",
    "Seasonal": "tag:seasonal",
    "Maybe": "maybe",
    "Remove": "remove",
    "Visual duplicates": "duplicates",
}


@dataclass(frozen=True)
class SkinEntry:
    path: Path
    relative: str


def find_visual_duplicates(entries: list[SkinEntry]) -> dict[str, int]:
    """Return duplicate-group sizes for skins whose normalized pixels match."""

    groups: dict[str, list[str]] = {}
    for entry in entries:
        try:
            with Image.open(entry.path) as image:
                normalized, _ = normalize_skin(image)
            digest = hashlib.sha256(normalized.tobytes()).hexdigest()
        except Exception:
            continue
        groups.setdefault(digest, []).append(entry.relative)
    return {
        relative: len(group)
        for group in groups.values()
        if len(group) > 1
        for relative in group
    }


class PickerState:
    def __init__(self, source: Path) -> None:
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / ".config"
        self.path = root / "Daily Dress Skin Styler" / "wardrobe-picker-state.json"
        self.source_key = str(source.resolve()).casefold()
        self.data: dict = {"version": 2, "sources": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("sources"), dict):
                self.data = loaded
        except (OSError, ValueError, TypeError):
            pass
        self.source_data: dict[str, dict[str, str]] = self.data.setdefault("sources", {}).setdefault(
            self.source_key,
            {},
        )

    def get(self, relative: str) -> dict[str, str]:
        saved = self.source_data.get(relative, {})
        status = saved.get("status", "unsorted")
        tag = saved.get("tag", "other")
        if status not in STATUSES:
            status = "unsorted"
        if tag not in TAGS:
            tag = "other"
        return {"status": status, "tag": tag}

    def set(self, relative: str, *, status: str | None = None, tag: str | None = None) -> None:
        current = dict(self.source_data.get(relative, {}))
        current.update(self.get(relative))
        if status is not None:
            current["status"] = status
        if tag is not None:
            current["tag"] = tag
        self.source_data[relative] = current
        self.save()

    def details(self, relative: str) -> dict[str, object]:
        """Return styling metadata while keeping ``get`` backward-compatible."""

        basic = self.get(relative)
        saved = self.source_data.get(relative, {})
        model = str(saved.get("model", "auto"))
        if model not in ("auto", "slim", "classic"):
            model = "auto"
        corrections = saved.get("corrections", {})
        if not isinstance(corrections, dict):
            corrections = {}
        hair_mode = str(saved.get("hair_mode", "auto"))
        if hair_mode not in ("auto", "none"):
            hair_mode = "auto"
        return {**basic, "model": model, "hair_mode": hair_mode, "corrections": dict(corrections)}

    def set_model(self, relative: str, model: str) -> None:
        if model not in ("auto", "slim", "classic"):
            raise ValueError(f"Unsupported skin model: {model}")
        saved = dict(self.source_data.get(relative, {}))
        saved.update(self.get(relative))
        saved["model"] = model
        self.source_data[relative] = saved
        self.save()

    def set_hair_mode(self, relative: str, mode: str) -> None:
        if mode not in ("auto", "none"):
            raise ValueError(f"Unsupported hair mode: {mode}")
        saved = dict(self.source_data.get(relative, {}))
        saved.update(self.get(relative))
        saved["hair_mode"] = mode
        self.source_data[relative] = saved
        self.save()

    def get_corrections(self, relative: str) -> dict[tuple[int, int], str]:
        raw = self.details(relative)["corrections"]
        parsed: dict[tuple[int, int], str] = {}
        for key, category in raw.items():
            try:
                x_text, y_text = str(key).split(",", 1)
                parsed[(int(x_text), int(y_text))] = str(category)
            except (TypeError, ValueError):
                continue
        return parsed

    def set_corrections(self, relative: str, corrections: dict[tuple[int, int], str]) -> None:
        saved = dict(self.source_data.get(relative, {}))
        saved.update(self.get(relative))
        saved["corrections"] = {
            f"{x},{y}": category for (x, y), category in sorted(corrections.items())
        }
        self.source_data[relative] = saved
        self.save()

    def generation_metadata(self) -> dict[str, dict[str, object]]:
        return {relative: self.details(relative) for relative in self.source_data}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class WardrobePicker(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        source: Path,
        use_as_source: Callable[[Path], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.source = source.expanduser().resolve()
        self.use_as_source = use_as_source
        self.state_store = PickerState(self.source)
        self.entries = [
            SkinEntry(path, path.relative_to(self.source).as_posix())
            for path in sorted(self.source.rglob("*.png"), key=lambda item: item.name.casefold())
        ]
        self.entry_by_relative = {entry.relative: entry for entry in self.entries}
        self.duplicate_counts = find_visual_duplicates(self.entries)
        self.visible_entries: list[SkinEntry] = []
        self.thumbnail_cache: dict[str, ImageTk.PhotoImage] = {}
        self.detail_images: list[ImageTk.PhotoImage] = []
        self.card_widgets: dict[str, tuple[tk.Frame, tk.Button, tk.Label, tk.Label]] = {}
        self.selected_relative: str | None = None
        self.status_history: list[tuple[str, str]] = []

        self.title("Daily Dress Wardrobe Picker ✿")
        self.geometry("1180x880")
        self.minsize(980, 740)
        self.configure(background="#25272B")

        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All skins")
        self.counts_var = tk.StringVar()
        self.selected_name_var = tk.StringVar(value="Choose a skin")
        self.selected_path_var = tk.StringVar(value="")
        self.selected_status_var = tk.StringVar(value="")
        self.tag_var = tk.StringVar(value="other")
        self.message_var = tk.StringVar(value="Your choices save automatically; original skins are never changed.")

        self._build()
        self.search_var.trace_add("write", lambda *_args: self._refresh_grid())
        self.filter_var.trace_add("write", lambda *_args: self._refresh_grid())
        self.bind("<KeyPress>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._refresh_grid()
        self.after(50, self.focus_force)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(16, 13, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Wardrobe Picker", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="See the real thin-model outfit, sort safely, then create a small Favorites master folder.",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
        ttk.Label(header, text="Search").grid(row=2, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.search_var, width=34).grid(row=2, column=1, sticky="ew", padx=(7, 16))
        ttk.Label(header, text="Show").grid(row=2, column=2, sticky="w")
        ttk.Combobox(
            header,
            textvariable=self.filter_var,
            values=list(FILTERS),
            state="readonly",
            width=18,
        ).grid(row=2, column=3, sticky="w", padx=(7, 0))
        ttk.Label(header, textvariable=self.counts_var).grid(row=2, column=4, sticky="e", padx=(18, 0))
        header.columnconfigure(1, weight=1)
        header.columnconfigure(4, weight=1)

        content = ttk.Panedwindow(self, orient="horizontal")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        gallery_holder = ttk.Frame(content)
        content.add(gallery_holder, weight=4)
        self.gallery_canvas = tk.Canvas(
            gallery_holder,
            background="#202226",
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(gallery_holder, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=scrollbar.set)
        self.gallery_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.gallery = tk.Frame(self.gallery_canvas, background="#202226")
        self.gallery_window = self.gallery_canvas.create_window((0, 0), window=self.gallery, anchor="nw")
        self.gallery.bind(
            "<Configure>",
            lambda _event: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")),
        )
        self.gallery_canvas.bind(
            "<Configure>",
            lambda event: self.gallery_canvas.itemconfigure(self.gallery_window, width=event.width),
        )
        self.bind("<MouseWheel>", self._on_mousewheel)

        detail = ttk.Frame(content, padding=(16, 10))
        content.add(detail, weight=1)
        ttk.Label(detail, textvariable=self.selected_name_var, font=("Segoe UI", 12, "bold"), wraplength=380).pack(fill="x")
        ttk.Label(detail, textvariable=self.selected_path_var, foreground="#777777", wraplength=380).pack(fill="x", pady=(2, 10))

        preview = tk.Frame(detail, background="#303238", relief="solid", borderwidth=1)
        preview.pack(fill="x")
        self.front_preview = tk.Label(preview, text="front", background="#303238", foreground="#CCCCCC")
        self.front_preview.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        self.back_preview = tk.Label(preview, text="back", background="#303238", foreground="#CCCCCC")
        self.back_preview.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        ttk.Label(detail, textvariable=self.selected_status_var, font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(10, 5))

        status_frame = ttk.LabelFrame(detail, text="Decision — automatically moves to next", padding=8)
        status_frame.pack(fill="x", pady=(3, 8))
        ttk.Button(status_frame, text="♥ Favorite  [F]", command=lambda: self._set_status("favorite")).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(status_frame, text="? Maybe  [M]", command=lambda: self._set_status("maybe")).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)
        ttk.Button(status_frame, text="× Remove  [X]", command=lambda: self._set_status("remove")).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(status_frame, text="↶ Unsorted  [U]", command=lambda: self._set_status("unsorted")).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=1)

        tag_frame = ttk.LabelFrame(detail, text="Optional outfit type", padding=8)
        tag_frame.pack(fill="x", pady=(0, 8))
        tag_options = (("Dresses [1]", "dresses"), ("Casual [2]", "casual"), ("Seasonal [3]", "seasonal"), ("Other [0]", "other"))
        for index, (label, value) in enumerate(tag_options):
            ttk.Radiobutton(
                tag_frame,
                text=label,
                value=value,
                variable=self.tag_var,
                command=self._set_tag,
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=4, pady=2)

        nav = ttk.Frame(detail)
        nav.pack(fill="x", pady=(2, 10))
        ttk.Button(nav, text="← Previous", command=lambda: self._move_selection(-1)).pack(side="left")
        ttk.Button(nav, text="Next →", command=lambda: self._move_selection(1)).pack(side="right")
        ttk.Button(nav, text="Undo last  [Ctrl+Z]", command=self._undo_status).pack(expand=True)

        export_frame = ttk.LabelFrame(detail, text="Ready for styling", padding=8)
        export_frame.pack(fill="x", pady=(2, 8))
        ttk.Label(
            export_frame,
            text=(
                "No folder copies are needed. Close this view when you are done: the main Styler reads these saved choices, "
                "skips Remove, and carries favorites/categories into the sync wardrobe."
            ),
            foreground="#777777",
            wraplength=260,
        ).pack(fill="x", pady=(6, 0))

        footer = ttk.Frame(self, padding=(16, 4, 16, 12))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.message_var, wraplength=1120).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right", padx=(12, 0))

    def _on_mousewheel(self, event) -> None:
        if self.winfo_exists():
            self.gallery_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _filtered_entries(self) -> list[SkinEntry]:
        search = self.search_var.get().strip().casefold()
        status_filter = FILTERS.get(self.filter_var.get())
        return [
            entry
            for entry in self.entries
            if (not search or search in entry.relative.casefold())
            and (
                status_filter is None
                or (status_filter == "duplicates" and entry.relative in self.duplicate_counts)
                or (
                    status_filter.startswith("tag:")
                    and self.state_store.get(entry.relative)["tag"] == status_filter.split(":", 1)[1]
                )
                or (
                    status_filter.startswith("favorite+")
                    and self.state_store.get(entry.relative)["status"] == "favorite"
                    and self.state_store.get(entry.relative)["tag"] == status_filter.split("+", 1)[1]
                )
                or self.state_store.get(entry.relative)["status"] == status_filter
            )
        ]

    def _refresh_grid(self, preferred: str | None = None) -> None:
        for child in self.gallery.winfo_children():
            child.destroy()
        self.card_widgets.clear()
        self.visible_entries = self._filtered_entries()
        columns = 7
        for index, entry in enumerate(self.visible_entries):
            state = self.state_store.get(entry.relative)
            color = STATUSES[state["status"]][1]
            card = tk.Frame(
                self.gallery,
                background=color,
                width=104,
                height=174,
                highlightthickness=2,
                highlightbackground="#202226",
            )
            card.grid(row=index // columns, column=index % columns, padx=5, pady=5, sticky="n")
            card.grid_propagate(False)
            image = self._thumbnail(entry)
            button = tk.Button(
                card,
                image=image,
                command=lambda relative=entry.relative: self._select(relative),
                background=color,
                activebackground=color,
                relief="flat",
                borderwidth=0,
                cursor="hand2",
            )
            button.pack(pady=(5, 1))
            name = tk.Label(
                card,
                text=self._card_name(entry.path.stem),
                background=color,
                foreground="white",
                wraplength=94,
                font=("Segoe UI", 8),
            )
            name.pack(fill="x", padx=2)
            status_label = tk.Label(
                card,
                text=self._card_status_text(entry.relative, state),
                background=color,
                foreground="#F2E9EF",
                font=("Segoe UI", 7),
            )
            status_label.pack(side="bottom", pady=(1, 4))
            for widget in (card, name, status_label):
                widget.bind("<Button-1>", lambda _event, relative=entry.relative: self._select(relative))
            self.card_widgets[entry.relative] = (card, button, name, status_label)

        for column in range(columns):
            self.gallery.columnconfigure(column, weight=1)
        self._refresh_counts()
        if not self.visible_entries:
            self.selected_relative = None
            self._clear_detail("No skins match this search/filter.")
            return
        target = preferred if preferred in self.card_widgets else None
        if target is None and self.selected_relative in self.card_widgets:
            target = self.selected_relative
        if target is None:
            target = self.visible_entries[0].relative
        self._select(target)

    @staticmethod
    def _card_name(stem: str) -> str:
        friendly = stem.replace("_", " ").replace("-", " ")
        return friendly if len(friendly) <= 24 else friendly[:23].rstrip() + "…"

    def _card_status_text(self, relative: str, state: dict[str, str]) -> str:
        duplicates = self.duplicate_counts.get(relative)
        if duplicates:
            return f"SAME×{duplicates} · {STATUSES[state['status']][0]}"
        return f"{STATUSES[state['status']][0]} · {TAGS[state['tag']]}"

    def _thumbnail(self, entry: SkinEntry) -> ImageTk.PhotoImage:
        cached = self.thumbnail_cache.get(entry.relative)
        if cached is not None:
            return cached
        try:
            with Image.open(entry.path) as image:
                saved_model = str(self.state_store.details(entry.relative)["model"])
                slim = saved_model == "slim" or (saved_model == "auto" and detect_skin_model(image) == "slim")
                preview = render_player_view(image, scale=4, slim=slim)
        except Exception:
            preview = Image.new("RGBA", (56, 128), (65, 30, 38, 255))
            draw = ImageDraw.Draw(preview)
            draw.line((8, 32, 48, 96), fill=(255, 150, 160, 255), width=5)
            draw.line((48, 32, 8, 96), fill=(255, 150, 160, 255), width=5)
        photo = ImageTk.PhotoImage(preview)
        self.thumbnail_cache[entry.relative] = photo
        return photo

    def _select(self, relative: str) -> None:
        entry = self.entry_by_relative.get(relative)
        if entry is None:
            return
        previous = self.card_widgets.get(self.selected_relative or "")
        if previous is not None:
            previous[0].configure(highlightbackground="#202226")
        self.selected_relative = relative
        current = self.card_widgets.get(relative)
        if current is not None:
            current[0].configure(highlightbackground="#F3C6DC")

        state = self.state_store.get(relative)
        self.selected_name_var.set(entry.path.stem)
        self.selected_path_var.set(relative)
        duplicate_note = ""
        if relative in self.duplicate_counts:
            duplicate_note = f" · Same pixels as {self.duplicate_counts[relative] - 1} other skin(s)"
        self.selected_status_var.set(f"{STATUSES[state['status']][0]} · {TAGS[state['tag']]}{duplicate_note}")
        self.tag_var.set(state["tag"])
        try:
            with Image.open(entry.path) as image:
                saved_model = str(self.state_store.details(entry.relative)["model"])
                slim = saved_model == "slim" or (saved_model == "auto" and detect_skin_model(image) == "slim")
                front = ImageTk.PhotoImage(render_player_view(image, scale=6, slim=slim))
                back = ImageTk.PhotoImage(render_player_view(image, scale=6, back=True, slim=slim))
            self.detail_images = [front, back]
            self.front_preview.configure(image=front, text="")
            self.back_preview.configure(image=back, text="")
        except Exception as exception:
            self.detail_images.clear()
            self.front_preview.configure(image="", text="could not\npreview")
            self.back_preview.configure(image="", text=str(exception)[:60])

    def _clear_detail(self, message: str) -> None:
        self.selected_name_var.set(message)
        self.selected_path_var.set("")
        self.selected_status_var.set("")
        self.detail_images.clear()
        self.front_preview.configure(image="", text="front")
        self.back_preview.configure(image="", text="back")

    def _set_status(self, status: str) -> None:
        if self.selected_relative is None:
            return
        relative = self.selected_relative
        try:
            index = next(i for i, entry in enumerate(self.visible_entries) if entry.relative == relative)
        except StopIteration:
            index = 0
        next_relative = None
        if len(self.visible_entries) > 1:
            next_relative = self.visible_entries[(index + 1) % len(self.visible_entries)].relative
        try:
            previous_status = self.state_store.get(relative)["status"]
            self.state_store.set(relative, status=status)
            if previous_status != status:
                self.status_history.append((relative, previous_status))
                self.status_history = self.status_history[-1000:]
        except OSError as exception:
            messagebox.showerror("Could not save choice", str(exception), parent=self)
            return

        if FILTERS.get(self.filter_var.get()) is not None:
            self._refresh_grid(preferred=next_relative)
        else:
            self._refresh_card(relative)
            self._refresh_counts()
            if next_relative is not None:
                self._select(next_relative)
            else:
                self._select(relative)
        self.message_var.set(f"Marked {self.entry_by_relative[relative].path.stem} as {STATUSES[status][0]}. Ctrl+Z undoes it.")

    def _undo_status(self) -> None:
        if not self.status_history:
            self.message_var.set("Nothing to undo yet.")
            return
        relative, previous_status = self.status_history.pop()
        try:
            self.state_store.set(relative, status=previous_status)
        except OSError as exception:
            messagebox.showerror("Could not undo choice", str(exception), parent=self)
            return
        self._refresh_grid(preferred=relative)
        self.message_var.set(f"Restored {self.entry_by_relative[relative].path.stem} to {STATUSES[previous_status][0]}.")

    def _set_tag(self) -> None:
        if self.selected_relative is None:
            return
        try:
            relative = self.selected_relative
            selected_tag = self.tag_var.get()
            try:
                index = next(i for i, entry in enumerate(self.visible_entries) if entry.relative == relative)
            except StopIteration:
                index = 0
            next_relative = self.visible_entries[(index + 1) % len(self.visible_entries)].relative if len(self.visible_entries) > 1 else relative
            self.state_store.set(relative, tag=selected_tag)
            self._refresh_card(relative)
            self._select(next_relative)
            self.message_var.set(
                f"Categorized {self.entry_by_relative[relative].path.stem} as {TAGS[selected_tag]}; moved to the next skin."
            )
        except OSError as exception:
            messagebox.showerror("Could not save category", str(exception), parent=self)

    def _refresh_card(self, relative: str) -> None:
        widgets = self.card_widgets.get(relative)
        if widgets is None:
            return
        state = self.state_store.get(relative)
        color = STATUSES[state["status"]][1]
        frame, button, name, status_label = widgets
        for widget in (frame, button, name, status_label):
            widget.configure(background=color)
        button.configure(activebackground=color)
        status_label.configure(text=self._card_status_text(relative, state))

    def _refresh_counts(self) -> None:
        counts = {status: 0 for status in STATUSES}
        for entry in self.entries:
            counts[self.state_store.get(entry.relative)["status"]] += 1
        self.counts_var.set(
            f"♥ {counts['favorite']}   ? {counts['maybe']}   × {counts['remove']}   "
            f"Unsorted {counts['unsorted']}   Same-pixel skins {len(self.duplicate_counts)}"
        )

    def _move_selection(self, change: int) -> None:
        if not self.visible_entries:
            return
        if self.selected_relative is None:
            self._select(self.visible_entries[0].relative)
            return
        try:
            index = next(i for i, entry in enumerate(self.visible_entries) if entry.relative == self.selected_relative)
        except StopIteration:
            index = 0
        self._select(self.visible_entries[(index + change) % len(self.visible_entries)].relative)

    def _on_key(self, event) -> str | None:
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return None
        key = event.keysym.casefold()
        if key == "z" and event.state & 0x4:
            self._undo_status()
            return "break"
        if key == "backspace":
            self._undo_status()
            return "break"
        actions = {
            "f": lambda: self._set_status("favorite"),
            "m": lambda: self._set_status("maybe"),
            "x": lambda: self._set_status("remove"),
            "u": lambda: self._set_status("unsorted"),
            "left": lambda: self._move_selection(-1),
            "right": lambda: self._move_selection(1),
            "1": lambda: self._set_tag_value("dresses"),
            "2": lambda: self._set_tag_value("casual"),
            "3": lambda: self._set_tag_value("seasonal"),
            "0": lambda: self._set_tag_value("other"),
        }
        action = actions.get(key)
        if action is None:
            return None
        action()
        return "break"

    def _set_tag_value(self, tag: str) -> None:
        self.tag_var.set(tag)
        self._set_tag()

    def _choose_export_parent(self, title: str) -> Path | None:
        selected = filedialog.askdirectory(
            title=title,
            initialdir=str(Path.home() / "Pictures"),
            parent=self,
        )
        return Path(selected) if selected else None

    @staticmethod
    def _new_export_folder(parent: Path, base: str) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d %H%M")
        candidate = parent / f"{base} - {timestamp}"
        suffix = 2
        while candidate.exists():
            candidate = parent / f"{base} - {timestamp} ({suffix})"
            suffix += 1
        return candidate

    def _export_favorites(self) -> None:
        favorites = [
            entry for entry in self.entries if self.state_store.get(entry.relative)["status"] == "favorite"
        ]
        if not favorites:
            messagebox.showinfo("No favorites yet", "Mark some skins as Favorite first.", parent=self)
            return
        parent = self._choose_export_parent("Choose where to create the Favorites master folder")
        if parent is None:
            return
        target = self._new_export_folder(parent, "Daily Dress Favorites")
        try:
            self._copy_entries(favorites, target, include_status=False)
        except Exception as exception:
            messagebox.showerror("Could not create Favorites folder", str(exception), parent=self)
            return
        self.message_var.set(f"Created a new {len(favorites)}-skin Favorites master folder: {target}")
        use_now = messagebox.askyesno(
            "Favorites master folder created ✿",
            f"Created {len(favorites)} favorite skins in:\n\n{target}\n\nUse this as the Skin Styler's new Source wardrobe?",
            parent=self,
        )
        if use_now and self.use_as_source is not None:
            self.use_as_source(target)
            self.destroy()

    def _export_organized(self) -> None:
        parent = self._choose_export_parent("Choose where to create the organized wardrobe copy")
        if parent is None:
            return
        target = self._new_export_folder(parent, "Daily Dress Organized")
        try:
            self._copy_entries(self.entries, target, include_status=True)
        except Exception as exception:
            messagebox.showerror("Could not create organized copy", str(exception), parent=self)
            return
        self.message_var.set(f"Created a complete organized copy: {target}")
        messagebox.showinfo(
            "Organized copy created ✿",
            f"Copied {len(self.entries)} skins into safe Favorite, Maybe, Remove, and Unsorted folders:\n\n{target}",
            parent=self,
        )

    def _copy_entries(self, entries: list[SkinEntry], target: Path, include_status: bool) -> None:
        target.mkdir(parents=True)
        for entry in entries:
            saved = self.state_store.get(entry.relative)
            pieces = []
            if include_status:
                pieces.append(STATUSES[saved["status"]][0])
            pieces.append(TAGS[saved["tag"]])
            destination = target.joinpath(*pieces, Path(entry.relative))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry.path, destination)
        (target / "DAILY DRESS ORGANIZER.txt").write_text(
            "Daily Dress Wardrobe Picker export\n"
            f"Source: {self.source}\n"
            f"Created: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Skins copied: {len(entries)}\n"
            "Original skins were not moved, renamed, changed, or deleted.\n",
            encoding="utf-8",
        )
