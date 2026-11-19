"""Local studio prototype: QML interaction, existing Python skin rendering.

Metadata lives in dev-workspace/styler. This shell never stages or uploads skins.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import colorsys
import hashlib
from datetime import datetime, timezone
import json
import os
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw
from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Property, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider, QQuickWindow
from PySide6.QtWidgets import QApplication, QColorDialog, QFileDialog

from skin_styler_core import (
    apply_category_overrides, classify_skin_categories,
    is_eye_feature_coordinate, make_face_template, normalize_skin, parse_hex_color, recommended_hair_tolerance,
    cuboid_face_boxes, player_uv_parts, render_front_face, render_player_3d, representative_hair_color, resolve_skin_model,
)
from eye_designer import mirrored_eye_coordinate
from pixel_category_editor import CATEGORY_COLORS
from studio_eyes import (
    EYE_MATERIALS, EYE_TOOLS, design_eyes, eye_canvas, eye_coordinates, eye_template, freeze_eye_template,
)
from studio_preview import (
    DEFAULT_STYLE, PreviewJob, PreviewRenderer, PreviewRequest, ViewportFrames, clean_style, pil_to_qimage, reference_skin_tone,
)
from wardrobe_picker import PickerState, STATUSES


@lru_cache(maxsize=2)
def mirrored_skin_pixels(slim):
    parts = player_uv_parts(slim)
    mirrored = {}
    for part, opposite in zip(parts, (0, 1, 3, 2, 5, 4)):
        _, base, outer, width, depth, height = part
        for origin, destination in zip((base, outer), parts[opposite][1:3]):
            target = cuboid_face_boxes(destination, width, depth, height)
            for face, (left, top, right, bottom) in cuboid_face_boxes(origin, width, depth, height).items():
                other = {"left": "right", "right": "left"}.get(face, face)
                _, target_top, target_right, _ = target[other]
                for y in range(top, bottom):
                    for x in range(left, right):
                        mirrored[x, y] = (target_right - 1 - (x - left), target_top + y - top)
    return mirrored


@dataclass(frozen=True)
class Skin:
    path: Path
    relative: str
    look_name: str = ""

    @property
    def name(self):
        return self.look_name or self.path.stem.replace("_", " ")


class WardrobeModel(QAbstractListModel):
    """Filters add/remove rows in place; only a source change resets the list."""
    names = ("skinName", "skinStatus", "category", "thumbnail", "isReference", "skinFilename")

    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.indexes = []

    def roleNames(self):
        return {int(Qt.UserRole) + i: name.encode() for i, name in enumerate(self.names)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.indexes)

    def data(self, index, role):
        if not index.isValid() or not 0 <= index.row() < len(self.indexes):
            return None
        entry = self.indexes[index.row()]
        skin = self.studio.all_skins[entry]
        details = self.studio.picker.get(skin.relative)
        values = (skin.name, details["status"], details["tag"],
                  self.studio.thumbnail_source(entry),
                  skin.relative == self.studio.reference_relative, skin.path.name)
        offset = role - int(Qt.UserRole)
        return values[offset] if 0 <= offset < len(values) else None

    def replace(self, indexes, force=False, refresh=True):
        if force:
            self.beginResetModel()
            self.indexes = list(indexes)
            self.endResetModel()
            return
        wanted = set(indexes)
        for row in range(len(self.indexes) - 1, -1, -1):
            if self.indexes[row] not in wanted:
                self.beginRemoveRows(QModelIndex(), row, row)
                self.indexes.pop(row)
                self.endRemoveRows()
        for row, entry in enumerate(indexes):
            if row >= len(self.indexes) or self.indexes[row] != entry:
                self.beginInsertRows(QModelIndex(), row, row)
                self.indexes.insert(row, entry)
                self.endInsertRows()
        if refresh and self.indexes:
            self.dataChanged.emit(self.index(0), self.index(len(self.indexes) - 1), [])

    def refresh_entry(self, entry, roles=("skinStatus", "category")):
        if entry in self.indexes:
            index = self.index(self.indexes.index(entry))
            self.dataChanged.emit(index, index, [int(Qt.UserRole) + self.names.index(role) for role in roles])


class SkinImages(QQuickImageProvider):
    def __init__(self, studio):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.studio = studio
        self.cache = {}

    def requestImage(self, identifier, size, requested_size):
        parts = identifier.split("/")
        try:
            if parts[0] in ("stage", "original"):
                image = self.studio.stage_image(original=parts[0] == "original")
            elif parts[0] == "styled-face":
                image = self.studio._frames[2] if self.studio._frames and len(self.studio._frames) > 2 else QImage()
            elif parts[0] == "editor":
                image = self.studio._editor_image
            elif parts[0] == "face":
                with Image.open(self.studio.all_skins[int(parts[-1])].path) as source:
                    image = pil_to_qimage(render_front_face(source, scale=8))
            else:
                entry = int(parts[-1])
                model = parts[-2]
                key = (self.studio.source_revision, entry, model)
                if key not in self.cache:
                    if len(self.cache) > 400:
                        self.cache.clear()
                    with Image.open(self.studio.all_skins[entry].path) as source:
                        self.cache[key] = pil_to_qimage(render_player_3d(
                            source, scale=4, slim=resolve_skin_model(source, model) == "slim"))
                image = self.cache[key]
        except (OSError, ValueError, IndexError, AttributeError):
            image = QImage()
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class StudioBridge(QObject):
    selectionChanged = Signal()
    armModelChanged = Signal()
    statusChanged = Signal()
    filtersChanged = Signal()
    categoriesChanged = Signal()
    shadingBasesChanged = Signal()
    previewChanged = Signal()
    historyChanged = Signal()
    styleChanged = Signal()
    renderStateChanged = Signal()
    reviewChanged = Signal()
    viewportPacketChanged = Signal()
    previewYawChanged = Signal()
    editorChanged = Signal()
    materialsChanged = Signal()

    def __init__(self, source=None, state_directory=None, viewport_path=None):
        super().__init__()
        self.selectionChanged.connect(self.armModelChanged.emit)
        self.state_directory = state_directory or Path(__file__).resolve().parents[1] / "dev-workspace" / "styler"
        self.settings_path = self.state_directory / "studio-state.json"
        try:
            settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.settings = settings if isinstance(settings, dict) else {}
        except (OSError, ValueError):
            self.settings = {}
        for key in ("references", "styles", "eyeDesigns"):
            if not isinstance(self.settings.get(key), dict):
                self.settings[key] = {}
        saved_source = self.settings.get("source")
        self.source = source or Path(saved_source if isinstance(saved_source, str) and saved_source else Path.home() / "Pictures" / "Skins")
        self.all_skins = []
        self.visible_indexes = []
        self.current_visible_index = -1
        self.source_revision = 0
        self.reference_relative = ""
        self._search = self._status_filter = self._tag_filter = ""
        self._review_mode = False
        self._review_origin = None
        self._review_remaining = 0
        self._held_relative = None
        self._stage_version = 0
        self._yaw = 25.0
        self._viewport_path = viewport_path
        self._viewport_packet = ""
        self._viewport_edit_session = 0
        self._viewport_preview_active = False
        self._status = "Local studio"
        self._undo, self._redo = [], []
        self._updating_model = False
        self.options = clean_style({})
        self._hair_hsl = (0, 0, 0)
        self._reference_hair = ""
        self._reference_skin = ""
        self._style_edit_before = None
        self._editor_mode = ""
        self._editor_version = 0
        self._editor_image = QImage()
        self._editor_error = ""
        self._editor_texture = self._editor_auto = None
        self._editor_relative = None
        self._style_relative = None
        self._skin_style_dirty = False
        self._editor_filter = "all"
        self._editor_corrections = {}
        self._texture_drafts = {}
        self._texture_history = {}
        self._texture_stroke = None
        self._texture_painting = False
        self._texture_color = "#E9A7C8"
        self._stroke_before = self._stroke_last = None
        self._material_cache = None
        self._eye_cache = None
        self._sampling_color = ""
        self._material_counts = {}
        self._inspect_materials = False
        self._extra_hsl = {}
        self._frames = None
        self._render_revision = 0
        self._render_busy = False
        self._render_error = ""
        self._pending_preview = None
        self._closed = False
        self._renderer = PreviewRenderer()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._active_job = None
        self.model = WardrobeModel(self)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(24)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._materials_timer = QTimer(self)
        self._materials_timer.setSingleShot(True)
        self._materials_timer.setInterval(100)
        self._materials_timer.timeout.connect(self._refresh_material_counts)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_settings)
        self.load_source(self.source)

    @Property(QObject, constant=True)
    def wardrobe(self):
        return self.model

    @Property(int, notify=selectionChanged)
    def selectedIndex(self):
        return self.current_visible_index

    @Property(bool, notify=selectionChanged)
    def hasSkins(self):
        return bool(self.visible_indexes)

    @Property(str, notify=selectionChanged)
    def selectedName(self):
        skin = self.current_skin()
        if not skin and self._review_mode:
            return "All caught up!" if self.all_skins else "No skins to review yet"
        return skin.name if skin else "Your wardrobe awaits"

    def thumbnail_source(self, entry):
        model = self.picker.model(self.all_skins[entry].relative)
        return f"image://skins/thumb/{self.source_revision}/{model}/{entry}"

    @Property("QVariantMap", notify=selectionChanged)
    def pixelNeighbors(self):
        if self.current_visible_index < 0:
            return {}
        neighbors = {}
        for name, offset in (("previous", -1), ("next", 1)):
            index = self.current_visible_index + offset
            if 0 <= index < len(self.visible_indexes):
                entry = self.visible_indexes[index]
                neighbors[name] = {"name": self.all_skins[entry].name, "thumbnail": self.thumbnail_source(entry)}
        return neighbors

    @Property(str, notify=selectionChanged)
    def styleSkinKey(self):
        return f"{self.source_revision}:{self._style_relative}" if self._style_relative else ""

    @Property(str, notify=selectionChanged)
    def selectedSkinKey(self):
        skin = self.current_skin()
        return skin.relative if skin else ""

    @Property(str, notify=armModelChanged)
    def selectedArmModel(self):
        skin = self.current_skin()
        return self.picker.model(skin.relative) if skin else "auto"

    @Property(str, notify=armModelChanged)
    def selectedMeta(self):
        skin = self.current_skin()
        if not skin:
            if self._review_mode and self.all_skins:
                return "Every skin has a decision. Your wardrobe is all sorted!"
            return "No skins match" if self.all_skins else "Choose a wardrobe folder to begin"
        try:
            with Image.open(skin.path) as image:
                model = "Slim" if resolve_skin_model(image, self.selectedArmModel) == "slim" else "Regular"
        except (OSError, ValueError):
            model = "Unavailable"
        return f"{model} · {self.current_visible_index + 1} of {len(self.visible_indexes)}"

    @Property(str, notify=selectionChanged)
    def selectedStatus(self):
        skin = self.current_skin()
        return self.picker.get(skin.relative)["status"] if skin else ""

    @Property(str, notify=selectionChanged)
    def selectedTag(self):
        skin = self.current_skin()
        return self.picker.get(skin.relative)["tag"] if skin else "other"

    @Property(str, notify=previewChanged)
    def stageSource(self):
        return f"image://skins/stage/{self._stage_version}" if self._frames else ""

    @Property(str, notify=previewChanged)
    def originalSource(self):
        return f"image://skins/original/{self._stage_version}" if self._frames else ""

    @Property(str, notify=previewChanged)
    def styledFaceSource(self):
        return f"image://skins/styled-face/{self._stage_version}" if self._frames and len(self._frames) > 2 else ""

    @Property(bool, notify=renderStateChanged)
    def previewBusy(self):
        return self._render_busy

    @Property(str, notify=renderStateChanged)
    def previewError(self):
        return self._render_error

    @Property(bool, constant=True)
    def viewportAvailable(self):
        return self._viewport_path is not None

    @Property(QUrl, constant=True)
    def viewportUrl(self):
        return QUrl.fromLocalFile(str(self._viewport_path)) if self.viewportAvailable else QUrl()

    @Property(str, notify=viewportPacketChanged)
    def viewportPacket(self):
        return self._viewport_packet

    @Property(float, notify=previewYawChanged)
    def previewYaw(self):
        return self._yaw

    def _viewport_token(self):
        if not self.viewportAvailable or not self.current_skin():
            return ""
        return f"{self.source_revision}:{self.visible_indexes[self.current_visible_index]}:{self._viewport_edit_session}"

    def _set_viewport_packet(self, packet):
        if self._viewport_packet != packet:
            self._viewport_packet = packet
            self.viewportPacketChanged.emit()

    @Slot(bool)
    def useViewportPreview(self, active):
        previous = self._viewport_preview_active
        self._viewport_preview_active = active
        if previous and not active:
            self._refresh_preview()

    @Slot(str, result=bool)
    def acceptsViewportEdits(self, token):
        return bool(token and token == self._viewport_token() and self._editor_mode == "pixels"
                    and self._editor_texture is not None and not self.samplingColor and not self._closed)

    @Slot(str, "QVariantList", str, bool)
    def paintViewportCells(self, token, cells, material, restore):
        if not self.acceptsViewportEdits(token) or material not in CATEGORY_COLORS:
            return
        # Hit-testing samples a stroke on the model's surface. Joining two
        # UVs with a straight line could cross into an unrelated atlas tile.
        indexes = [int(cell) for cell in cells[:128]
                   if type(cell) in (int, float) and 0 <= cell < 4096 and cell == int(cell)]
        points = [(cell % 64, cell // 64) for cell in indexes]
        self._stroke_last = None
        self._paint_pixels(points, material, restore)

    @Slot(str)
    def endViewportStroke(self, token):
        if self.acceptsViewportEdits(token):
            self.endPixelStroke()

    @Property("QVariantMap", notify=styleChanged)
    def styleOptions(self):
        hue, saturation, lightness = self._hair_hsl
        skin_color = self._reference_skin if self.options["skinMode"] == "reference" else self.options["skinColor"]
        return {**self.options, "hairColor": self._effective_hair_color(), "skinColor": skin_color or self.options["skinColor"],
                "hairTargetAvailable": self.options["hairMode"] == "custom" or bool(self._reference_hair),
                "skinTargetAvailable": bool(skin_color),
                "hairHue": hue, "hairSaturation": saturation, "hairLightness": lightness}

    @Property("QVariantMap", notify=styleChanged)
    def colorChannels(self):
        result = {}
        for name in ("skinColor", "outfitColor", "accessoryColor", *EYE_MATERIALS.values()):
            value = self.eyeColors.get(name, "") if name in EYE_MATERIALS.values() else self.styleOptions[name]
            hsl = self._extra_hsl.get(name)
            if hsl is None:
                hsl = self._hex_hsl(value) if value else (0, 0, 0)
            result[name] = dict(zip(("hue", "saturation", "lightness"), hsl))
        return result

    @Property(bool, notify=styleChanged)
    def hasReference(self):
        return self.reference_skin() is not None

    @Property(str, notify=styleChanged)
    def referenceHairColor(self):
        return self._reference_hair

    @Property(str, notify=styleChanged)
    def referenceSkinColor(self):
        return self._reference_skin

    @Property(str, notify=styleChanged)
    def referenceFaceSource(self):
        skin = self.reference_skin()
        return f"image://skins/face/{self.source_revision}/{self.all_skins.index(skin)}" if skin else ""

    @Property(str, notify=statusChanged)
    def statusText(self):
        return self._status

    @Property(str, notify=statusChanged)
    def wardrobeName(self):
        return self.source.name or "Wardrobe"

    @Property(str, notify=statusChanged)
    def wardrobeInfo(self):
        return f"{len(self.all_skins)} skins · local studio"

    @Property(str, notify=statusChanged)
    def referenceName(self):
        skin = self.reference_skin()
        return skin.name if skin else "No reference yet"

    @Property(str, notify=styleChanged)
    def referenceFilename(self):
        skin = self.reference_skin()
        return skin.path.name if skin else ""

    @Property(str, notify=statusChanged)
    def referenceSource(self):
        skin = self.reference_skin()
        return self.thumbnail_source(self.all_skins.index(skin)) if skin else ""

    @Property(str, notify=filtersChanged)
    def statusFilter(self):
        return self._status_filter

    @Property(str, notify=filtersChanged)
    def tagFilter(self):
        return self._tag_filter

    @Property(bool, notify=reviewChanged)
    def reviewMode(self):
        return self._review_mode

    @Property(int, notify=reviewChanged)
    def reviewRemaining(self):
        return self._review_remaining

    @Property(int, notify=reviewChanged)
    def reviewReviewed(self):
        return len(self.all_skins) - self._review_remaining

    @Property(bool, notify=selectionChanged)
    def selectionHeld(self):
        return self._held_relative is not None

    @Property(bool, notify=historyChanged)
    def canUndo(self):
        if self.texturePainting:
            return bool(self._texture_history.get((self.source, self._editor_relative), ([], []))[0])
        return bool(self._undo)

    @Property(bool, notify=historyChanged)
    def canRedo(self):
        if self.texturePainting:
            return bool(self._texture_history.get((self.source, self._editor_relative), ([], []))[1])
        return bool(self._redo)

    def current_skin(self):
        return self.all_skins[self.visible_indexes[self.current_visible_index]] if 0 <= self.current_visible_index < len(self.visible_indexes) else None

    def reference_skin(self):
        return next((skin for skin in self.all_skins if skin.relative == self.reference_relative), None)

    def load_source(self, source):
        self.closeEditor()
        self.endStyleEdit()
        if hasattr(self, "picker"):
            self.flush()
        self.source = source.resolve()
        self.source_revision += 1
        self._review_mode = False
        self._review_origin = self._held_relative = None
        self.all_skins = []
        if self.source.is_dir():
            for path in sorted(self.source.rglob("*"), key=lambda p: (p.name.casefold(), str(p))):
                if path.suffix.lower() != ".png":
                    continue
                try:
                    with Image.open(path) as image:
                        normalize_skin(image)
                    self.all_skins.append(Skin(path, path.relative_to(self.source).as_posix()))
                except (OSError, ValueError):
                    continue
        self.picker = PickerState(self.source, state_directory=self.state_directory)
        self.categoriesChanged.emit()
        originals = {skin.relative: skin.path for skin in self.all_skins}
        self.all_skins.extend(Skin(originals[look["source"]], relative, look["name"])
                              for relative, look in self.picker.looks() if look["source"] in originals)
        self.shadingBasesChanged.emit()
        references = self.settings.get("references", {})
        self.reference_relative = references.get(str(self.source), "") if isinstance(references, dict) else ""
        if not isinstance(self.reference_relative, str):
            self.reference_relative = ""
        self._style_relative = None
        self._skin_style_dirty = False
        self.options = clean_style({})
        self._read_reference()
        self._migrate_wardrobe_styles()
        self._undo.clear()
        self._redo.clear()
        self.current_visible_index = -1
        self._updating_model = True
        self.model.replace([], force=True)
        self._updating_model = False
        self.apply_filters()
        self.historyChanged.emit()
        self.statusChanged.emit()
        self.styleChanged.emit()

    def _migrate_wardrobe_styles(self):
        if self.settings.get("styleScopeVersion") == 1:
            return
        recent = []
        wardrobe = str(self.source)
        for source, legacy in sorted(self.settings["styles"].items(), key=lambda item: item[0] != wardrobe):
            old = clean_style(legacy)
            for material in ("outfit", "accessory", "hair", "skin"):
                key = material + "Color"
                if old[material + "Enabled"] or old[key] != DEFAULT_STYLE[key]:
                    reference_tone = self._reference_skin if source == wardrobe and material == "skin" else ""
                    recent.append(reference_tone if old["skinMode"] == "reference" and reference_tone else old[key])
            recent.extend(old[key] for key in EYE_MATERIALS.values() if old[key])
        self.settings["recentColors"] = list(dict.fromkeys(recent + self.recentColors))[:6]
        self.settings["styleScopeVersion"] = 1
        if self.settings["styles"]:
            self._schedule_save()

    def _matches_browsing(self, skin, details):
        status = details["status"]
        if self._status_filter == "kept":
            if status not in ("keep", "favorite"):
                return False
        elif self._status_filter:
            if status != self._status_filter:
                return False
        elif status == "remove":
            return False
        query = self._search.casefold()
        return (any(query in label.casefold() for label in (skin.relative, skin.name, skin.path.name))
                and (not self._tag_filter or details["tag"] == self._tag_filter))

    def apply_filters(self, *, preferred=None, fallback=None, advance_after=None, changed_relative=None, keep_pixels=False):
        self.endPixelStroke()
        selected = self.current_skin()
        previous = self.current_visible_index if fallback is None else fallback
        self.visible_indexes = []
        remaining = 0
        changed_entry = None
        for index, skin in enumerate(self.all_skins):
            details = self.picker.get(skin.relative)
            is_unsorted = details["status"] == "unsorted"
            remaining += is_unsorted
            if skin.relative == changed_relative:
                changed_entry = index
            show = is_unsorted if self._review_mode else (
                self._matches_browsing(skin, details) or skin.relative == self._held_relative)
            if show:
                self.visible_indexes.append(index)
        self._review_remaining = remaining
        if advance_after is not None and self.visible_indexes:
            self.current_visible_index = bisect_right(self.visible_indexes, advance_after) % len(self.visible_indexes)
        else:
            target = preferred if preferred is not None else selected.relative if selected else None
            self.current_visible_index = next((
                position for position, entry in enumerate(self.visible_indexes) if self.all_skins[entry].relative == target
            ), min(max(previous, 0), len(self.visible_indexes) - 1))
        self._updating_model = True
        self.model.replace(self.visible_indexes, refresh=False)
        self.model.refresh_entry(changed_entry)
        self._updating_model = False
        self._selection_for_editor(keep_pixels=keep_pixels)
        self.selectionChanged.emit()
        self.reviewChanged.emit()
        if changed_relative is None or self.current_skin() != selected:
            self._refresh_preview()

    @Slot()
    def toggleReview(self):
        if self._editor_mode:
            return
        skin = self.current_skin()
        self._held_relative = None
        if self._review_mode:
            relative, index = self._review_origin
            self._review_mode = False
            self._review_origin = None
            self.apply_filters(preferred=relative, fallback=index)
        else:
            self._review_origin = (skin.relative if skin else None, self.current_visible_index)
            self._review_mode = True
            self.apply_filters(fallback=0)

    def stage_image(self, original=False):
        return self._frames[0 if original else 1] if self._frames else QImage()

    def _refresh_preview(self):
        if self._closed:
            return
        self._render_revision += 1
        skin = self.current_skin()
        if not skin:
            self._pending_preview = self._frames = None
            self._set_viewport_packet("")
            self.previewChanged.emit()
            return
        reference = self.reference_skin()
        details = self.picker.details(skin.relative)
        base_key = self.options.get("shadingBase")
        if base_key and self.picker.is_shading_base(base_key):
            base = next((entry for entry in self.all_skins if entry.relative == base_key and entry != skin), None)
            if base and base.path.is_file():
                details["shadingPath"] = str(base.path)
                details["shadingModel"] = self.picker.model(base.relative)
        if self.texturePainting:
            draft = self._texture_drafts.get((self.source, skin.relative))
            details["textureDraft"] = (draft if draft is not None else self._editor_texture).tobytes().hex()
        self._pending_preview = PreviewRequest(
            self._render_revision, skin.path, reference.path if reference else None,
            {**self.options, "hairColor": self._effective_hair_color(),
             "hairEnabled": self.options["hairEnabled"] and self.styleOptions["hairTargetAvailable"]},
            details,
            self._active_corrections(skin), self._yaw,
            self._eye_source_path() if self.options["eyeReference"] else None,
            self._editor_mode == "eyes", self._viewport_token())
        if not self._render_busy:
            self._start_preview()

    def _start_preview(self):
        request, self._pending_preview = self._pending_preview, None
        if request is None or self._closed:
            return
        self._render_busy = True
        self._render_error = ""
        job = PreviewJob(self._renderer, request)
        job.signals.finished.connect(self._preview_finished)
        self._active_job = job
        self.renderStateChanged.emit()
        self._pool.start(job)

    @Slot(int, object, str)
    def _preview_finished(self, revision, frames, error):
        self._active_job = None
        self._render_busy = False
        if self._closed:
            return
        if revision == self._render_revision:
            self._render_error = "Preview unavailable — " + error if error else ""
            if frames is not None:
                if isinstance(frames, ViewportFrames):
                    self._set_viewport_packet(frames.packet)
                    frames = frames.fallback
                self._frames = frames
                self._stage_version += 1
                self.previewChanged.emit()
        if self._pending_preview:
            self._start_preview()
        else:
            self.renderStateChanged.emit()

    @Slot()
    def shutdown(self):
        self._closed = True
        self._pending_preview = None
        self._preview_timer.stop()
        self._materials_timer.stop()
        self._pool.waitForDone()

    def _schedule_save(self):
        self._status = "Saving…"
        self.statusChanged.emit()
        self._save_timer.start()

    @Slot()
    def flush(self):
        self.endPixelStroke()
        self.endStyleEdit()
        if self._save_timer.isActive() or self._skin_style_dirty:
            self._save_timer.stop()
            self._save_settings()

    def _save_settings(self):
        self.settings["source"] = str(self.source)
        self.settings.setdefault("references", {})[str(self.source)] = self.reference_relative
        try:
            if self._skin_style_dirty:
                self.picker.save()
                self._skin_style_dirty = False
            self.state_directory.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
            temporary.replace(self.settings_path)
            self._status = "Saved ✓"
        except OSError:
            self._status = "Couldn’t save — check folder access"
        self.statusChanged.emit()

    @Slot(int)
    def selectVisible(self, index):
        self._select_visible(index)

    @Slot(int)
    def navigatePixels(self, step):
        if self._editor_mode == "pixels" and not self.samplingColor and step in (-1, 1):
            self._select_visible(self.current_visible_index + step, keep_pixels=True)

    def _select_visible(self, index, *, keep_pixels=False):
        if not self._updating_model and 0 <= index < len(self.visible_indexes) and index != self.current_visible_index:
            self.endPixelStroke()
            if self._held_relative is not None:
                target = self.all_skins[self.visible_indexes[index]].relative
                self._held_relative = None
                self.apply_filters(preferred=target, keep_pixels=keep_pixels)
                return
            self.current_visible_index = index
            self._selection_for_editor(keep_pixels=keep_pixels)
            self.selectionChanged.emit()
            self._refresh_preview()

    @Slot(float)
    def rotate(self, degrees):
        self._yaw = (self._yaw + degrees) % 360
        self.previewYawChanged.emit()
        if not self._viewport_preview_active and not self._preview_timer.isActive():
            self._preview_timer.start()

    @Slot()
    def resetView(self):
        self._yaw = 25.0
        self.previewYawChanged.emit()
        if not self._viewport_preview_active:
            self._refresh_preview()

    @Slot(str)
    def setSearch(self, text):
        if self._review_mode:
            return
        self._held_relative = None
        self._search = text
        self.apply_filters()

    @Slot(str)
    def setFilter(self, name):
        if self._review_mode:
            return
        self._held_relative = None
        status = {"Favorites": "favorite", "Kept": "kept", "Maybe": "maybe",
                  "Unsorted": "unsorted", "Removed": "remove"}.get(name)
        categories = self.picker.categories()
        tag = name[4:] if name.startswith("tag:") and name[4:] in categories else next(
            (key for key, label in categories.items() if label == name), None)
        if name == "All":
            self._status_filter = self._tag_filter = ""
        elif status:
            self._status_filter = "" if self._status_filter == status else status
        elif tag:
            self._tag_filter = "" if self._tag_filter == tag else tag
        self.apply_filters()
        self.filtersChanged.emit()

    def _edit_metadata(self, **change):
        skin = self.current_skin()
        if not skin:
            return
        before = self.picker.get(skin.relative)
        after = {**before, **change}
        if before == after:
            return
        try:
            self.picker.set(skin.relative, **after)
        except OSError:
            self._status = "Couldn’t save — check folder access"
            self.statusChanged.emit()
            return
        self.endStyleEdit()
        self._undo.append(("metadata", skin.relative, before, after))
        self._redo.clear()
        decided = self._review_mode and "status" in change and after["status"] != "unsorted"
        advance_after = self.visible_indexes[self.current_visible_index] if decided else None
        self._hold_if_filtered(skin, after)
        self.apply_filters(preferred=skin.relative, advance_after=advance_after, changed_relative=skin.relative)
        self.historyChanged.emit()
        self._metadata_saved()

    def _hold_if_filtered(self, skin, details):
        self._held_relative = skin.relative if not self._review_mode and not self._matches_browsing(skin, details) else None

    def _metadata_saved(self):
        if not self._save_timer.isActive():
            self._status = "Saved ✓"
            self.statusChanged.emit()

    @Slot(str)
    def setStatus(self, status):
        if status in STATUSES:
            self._edit_metadata(status=status)

    @Slot(str)
    def setTag(self, tag):
        if tag in self.picker.categories():
            self._edit_metadata(tag=tag)

    @Property("QVariantList", notify=shadingBasesChanged)
    def shadingBases(self):
        if not hasattr(self, "picker"):
            return []
        return [{"key": skin.relative, "name": skin.name} for skin in self.all_skins
                if self.picker.is_shading_base(skin.relative)]

    @Slot()
    def toggleShadingBase(self):
        skin = self.current_skin()
        if skin is None:
            return
        try:
            self.picker.set_shading_base(skin.relative, not self.picker.is_shading_base(skin.relative))
        except OSError:
            self._status = "Couldn’t save shading base"
            self.statusChanged.emit()
            return
        self.shadingBasesChanged.emit()
        self._refresh_preview()
        self._metadata_saved()

    @Slot(str)
    def useShadingBase(self, key):
        if not key or self.picker.is_shading_base(key):
            self._change_style(shadingBase=key)

    @Property("QVariantList", notify=categoriesChanged)
    def categories(self):
        return [{"key": key, "name": name} for key, name in self.picker.categories().items()] if hasattr(self, "picker") else []

    @Slot(str, str, result=str)
    def saveCategory(self, key, name):
        name = " ".join(name.split())
        if not name:
            return "Enter a category name."
        categories = self.picker.categories()
        reserved = {"all", "kept", "favorites", "maybe", "unsorted", "removed"}
        if name.casefold() in reserved or any(
                existing.casefold() == name.casefold() for k, existing in categories.items() if k != key):
            return "That name is already in use."
        if key and (key not in categories or key == "other"):
            return "Choose an editable category."
        try:
            self.picker.save_category(key or uuid4().hex, name)
        except OSError:
            return "Couldn’t save the category."
        self.categoriesChanged.emit()
        return ""

    @Slot()
    def duplicateLook(self):
        skin = self.current_skin()
        if not skin or self._editor_mode not in ("", "pixels") or self.samplingColor:
            return
        self.endPixelStroke()
        self.endStyleEdit()
        stem = skin.path.stem.replace("_", " ")
        names = {entry.name.casefold() for entry in self.all_skins}
        number = 2
        while f"Look {number} · {stem}".casefold() in names:
            number += 1
        name = f"Look {number} · {stem}"
        relative = f"@look:{uuid4().hex}"
        try:
            self.picker.duplicate_look(skin.relative, relative, skin.path.relative_to(self.source).as_posix(), name, self.options)
        except OSError:
            self._status = "Couldn’t duplicate look — check folder access"
            self.statusChanged.emit()
            return
        duplicate = Skin(skin.path, relative, name)
        self.all_skins.append(duplicate)
        self._hold_if_filtered(duplicate, self.picker.get(relative))
        self.apply_filters(preferred=relative, keep_pixels=self._editor_mode == "pixels")
        self._metadata_saved()

    @Slot(str)
    def setArmModel(self, model):
        skin = self.current_skin()
        before = self.selectedArmModel
        if not skin or model not in ("auto", "slim", "classic") or model == before:
            return
        self.endPixelStroke()
        self.endStyleEdit()
        if self._save_arm_model(skin.relative, model):
            self._undo.append(("armModel", skin.relative, before, model))
            self._redo.clear()
            self.historyChanged.emit()

    def _save_arm_model(self, relative, model):
        try:
            self.picker.set_model(relative, model)
        except OSError:
            self._status = "Couldn’t save arm model — check folder access"
            self.statusChanged.emit()
            self.armModelChanged.emit()
            return False
        for entry in self.visible_indexes:
            if self.all_skins[entry].relative == relative:
                self.model.refresh_entry(entry, ("thumbnail",))
                break
        skin = self.current_skin()
        if skin and skin.relative == relative:
            if self._editor_mode == "pixels":
                self._viewport_edit_session += 1
            self.armModelChanged.emit()
            self._refresh_preview()
        self._metadata_saved()
        return True

    def _history(self, undo):
        self.endPixelStroke()
        if self.texturePainting:
            key = (self.source, self._editor_relative)
            undo_stack, redo_stack = self._texture_history.get(key, ([], []))
            stack, other = (undo_stack, redo_stack) if undo else (redo_stack, undo_stack)
            if stack:
                other.append(self._texture_drafts.get(key))
                restored = stack.pop()
                if restored is None:
                    self._texture_drafts.pop(key, None)
                else:
                    self._texture_drafts[key] = restored
                self._redraw_pixels()
                self._refresh_preview()
                self.historyChanged.emit()
            return
        self.endStyleEdit()
        stack, other = (self._undo, self._redo) if undo else (self._redo, self._undo)
        if not stack:
            return
        action = stack[-1]
        kind, relative, before, after = action
        if kind == "style":
            self._restore_style(relative, before if undo else after)
        elif kind == "reference":
            self._set_style_reference(before if undo else after)
        elif kind == "pixels":
            restored = before if undo else after
            if not self._save_corrections(relative, restored):
                return
            skin = self.current_skin()
            if self._editor_mode == "pixels" and skin and self._editor_relative == skin.relative == relative:
                # The preview reads the open editor's copy when it queues a frame.
                self._editor_corrections = dict(restored)
                self._redraw_pixels()
        elif kind == "armModel":
            if not self._save_arm_model(relative, before if undo else after):
                return
        else:
            try:
                self.picker.set(relative, **(before if undo else after))
            except OSError:
                self._status = "Couldn’t save — check folder access"
                self.statusChanged.emit()
                return
        stack.pop()
        other.append(action)
        if kind == "armModel":
            self.historyChanged.emit()
            return
        preferred = relative if relative and not self._editor_mode else None
        advance_after = None
        if kind == "metadata" and not self._editor_mode:
            skin = next((skin for skin in self.all_skins if skin.relative == relative), None)
            if skin is not None:
                self._hold_if_filtered(skin, before if undo else after)
            if self._review_mode and not undo and self.current_skin() == skin and after["status"] != "unsorted":
                advance_after = self.visible_indexes[self.current_visible_index]
        self.apply_filters(preferred=preferred, advance_after=advance_after,
                           changed_relative=relative if kind == "metadata" else None)
        self.historyChanged.emit()
        if kind == "metadata":
            self._metadata_saved()
        else:
            self._schedule_save()

    @Slot()
    def undo(self):
        self._history(True)

    @Slot()
    def redo(self):
        self._history(False)

    @Property(str, notify=editorChanged)
    def editorMode(self):
        return self._editor_mode

    @Property(str, notify=editorChanged)
    def editorSource(self):
        return f"image://skins/editor/{self._editor_version}" if not self._editor_image.isNull() else ""

    @Property(str, notify=editorChanged)
    def editorError(self):
        return self._editor_error

    @Property(int, notify=editorChanged)
    def correctionCount(self):
        return len(self._editor_corrections)

    @Property("QVariantList", notify=armModelChanged)
    def atlasGuides(self):
        if self._editor_texture is None:
            return []
        slim = resolve_skin_model(self._editor_texture, self.selectedArmModel) == "slim"
        return [
            {"label": name, "outer": outer, "x": x, "y": y,
             "width": 2 * (width + depth), "height": depth + height}
            for name, base, overlay, width, depth, height in player_uv_parts(slim)
            for outer, (x, y) in ((False, base), (True, overlay))
        ]

    def _selection_for_editor(self, *, keep_pixels=False):
        skin = self.current_skin()
        relative = skin.relative if skin else None
        if self._editor_mode and self._editor_relative != relative:
            if keep_pixels and skin:
                self._load_pixel_skin(skin)
            else:
                self.closeEditor()
        if self._style_relative != relative:
            self.endStyleEdit()
            self._style_relative = relative
            saved = self.picker.style(relative)
            default_matching = {"hairEnabled": True, "skinEnabled": True} if skin else {}
            self.options = clean_style({**default_matching, **(saved if isinstance(saved, dict) else {})})
            self._sync_hsl()
            self.styleChanged.emit()
        self._material_counts = {}
        self.materialsChanged.emit()
        if self._inspect_materials:
            self._materials_timer.start()

    @Property("QVariantMap", notify=materialsChanged)
    def materialCounts(self):
        return dict(self._material_counts)

    @Slot(bool)
    def setMaterialInspection(self, enabled):
        self._inspect_materials = enabled
        if enabled:
            self._materials_timer.start()
        else:
            self._materials_timer.stop()

    def _refresh_material_counts(self):
        skin = self.current_skin()
        try:
            if skin:
                _texture, detected = self._get_materials(skin)
                corrected = apply_category_overrides(detected, self._active_corrections(skin))
                self._material_counts = {material: len(getattr(corrected, material))
                                         for material in ("hair", "skin", "eyes", "outfit", "accessory")}
        except (ValueError, OSError):
            self._material_counts = {}
        self.materialsChanged.emit()

    def _get_materials(self, skin):
        key = (skin.path, skin.path.stat().st_mtime_ns)
        if self._material_cache is None or self._material_cache[0] != key:
            with Image.open(skin.path) as source:
                texture, _ = normalize_skin(source)
            auto = classify_skin_categories(texture, recommended_hair_tolerance(texture))
            self._material_cache = key, texture, auto
        return self._material_cache[1:]

    @Slot()
    def openPixels(self):
        skin = self.current_skin()
        if not skin:
            return
        self.closeEditor()
        self._editor_mode = "pixels"
        self._mirror_pixels = False
        self._editor_filter = "all"
        self._load_pixel_skin(skin)
        if self.viewportAvailable:
            self._refresh_preview()

    def _load_pixel_skin(self, skin):
        self._viewport_edit_session += 1
        self._editor_relative = skin.relative
        self._editor_error = ""
        self._editor_texture = self._editor_auto = None
        self._editor_image = QImage()
        self._editor_corrections = {}
        try:
            self._editor_texture, self._editor_auto = self._get_materials(skin)
            self._editor_corrections = self.picker.get_corrections(skin.relative)
            self._redraw_pixels()
        except (OSError, ValueError) as error:
            self._editor_error = "Couldn’t open texture — " + str(error)
            self.editorChanged.emit()
        self.historyChanged.emit()

    @Property(bool, notify=editorChanged)
    def texturePainting(self):
        return self._texture_painting and self._editor_mode == "pixels" and self._editor_texture is not None

    @Property(bool, notify=editorChanged)
    def hasTextureDraft(self):
        return (self.source, self._editor_relative) in self._texture_drafts

    @Property(str, notify=editorChanged)
    def textureColor(self):
        return self._texture_color

    @Slot(bool)
    def setTexturePainting(self, enabled):
        self.endPixelStroke()
        self._viewport_edit_session += 1
        self._texture_painting = enabled and self._editor_texture is not None and not self.samplingColor
        self._editor_error = ""
        self._redraw_pixels()
        self._refresh_preview()
        self.historyChanged.emit()

    @Slot()
    def chooseTextureColor(self):
        color = QColorDialog.getColor(QColor(self._texture_color), None, "Choose paint color")
        if color.isValid():
            self._texture_color = color.name()
            self.editorChanged.emit()

    @Slot()
    def revertTextureDraft(self):
        self.endPixelStroke()
        key = (self.source, self._editor_relative)
        before = self._texture_drafts.pop(key, None)
        if before is not None:
            self._record_texture_edit(key, before)
        self._redraw_pixels()
        self._refresh_preview()

    @Slot()
    def saveTextureAs(self):
        self.endPixelStroke()
        skin = self.current_skin()
        if not self.texturePainting or not skin or skin.relative != self._editor_relative:
            return
        draft = self._texture_drafts.get((self.source, skin.relative))
        if draft is None:
            return
        number = 1
        while True:
            suffix = " painted" if number == 1 else f" painted {number}"
            path = skin.path.with_stem(skin.path.stem + suffix).with_suffix(".png")
            try:
                stream = path.open("xb")
                break
            except FileExistsError:
                number += 1
            except OSError as error:
                self._editor_error = f"Couldn’t save painted skin — {error}"
                self.editorChanged.emit()
                return
        relative = path.relative_to(self.source).as_posix()
        try:
            with stream:
                draft.save(stream, format="PNG")
            self.picker.copy_painted_skin(skin.relative, relative, self.options)
        except OSError as error:
            path.unlink(missing_ok=True)
            self._editor_error = f"Couldn’t save painted skin — {error}"
            self.editorChanged.emit()
            return
        self._texture_drafts.pop((self.source, skin.relative), None)
        self._texture_history.pop((self.source, skin.relative), None)
        saved_skin = Skin(path, relative)
        self.all_skins.append(saved_skin)
        self._texture_painting = False
        self._hold_if_filtered(saved_skin, self.picker.get(relative))
        self.apply_filters(preferred=relative, keep_pixels=True)
        self._metadata_saved()
        self.historyChanged.emit()

    @Slot()
    def closeEditor(self):
        self.endPixelStroke()
        self.endStyleEdit()
        if self._editor_mode:
            self._texture_painting = False
            self._viewport_edit_session += 1
            self._editor_mode = self._editor_error = ""
            self._editor_relative = self._editor_texture = self._editor_auto = None
            self._editor_corrections = {}
            self._sampling_color = ""
            self._editor_image = QImage()
            self.editorChanged.emit()
            self.historyChanged.emit()

    @Slot(str)
    def setMaskFilter(self, material):
        if self._editor_mode == "pixels":
            self._editor_filter = material
            self._redraw_pixels()

    def _set_editor_image(self, image):
        self._editor_image = pil_to_qimage(image)
        self._editor_version += 1
        self.editorChanged.emit()

    def _redraw_pixels(self):
        if self._editor_texture is None:
            return
        if self.texturePainting:
            draft = self._texture_drafts.get((self.source, self._editor_relative), self._editor_texture)
            self._set_editor_image(draft.resize((256, 256), Image.Resampling.NEAREST))
            return
        show_auto = self._editor_filter == "auto"
        corrected = self._editor_auto if show_auto else apply_category_overrides(self._editor_auto, self._editor_corrections)
        overlay = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(overlay)
        for material, color in CATEGORY_COLORS.items():
            if self._editor_filter in ("all", "auto", material):
                mask = getattr(corrected, "ignored" if material == "ignore" else material)
                draw.point(sorted(mask), fill=(*color[:3], 115))
        image = Image.alpha_composite(self._editor_texture, overlay).resize((256, 256), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(image)
        for (x, y), material in self._editor_corrections.items():
            if self._editor_filter in ("all", material):
                # A white corner mark distinguishes manual edits from the tint.
                draw.line((x * 4, y * 4, x * 4 + 2, y * 4), fill="white")
                draw.point((x * 4, y * 4 + 1), fill="white")
        self._set_editor_image(image)

    @Property(bool, notify=editorChanged)
    def samplingColor(self):
        return bool(self._sampling_color)

    @Property(str, notify=editorChanged)
    def samplingTarget(self):
        return {
            "hairColor": "hair color",
            "skinColor": "skin tone",
            "outfitColor": "outfit color",
            "accessoryColor": "accessory color",
        }.get(self._sampling_color, "")

    @Slot(str)
    def openColorSampler(self, name):
        if name in ("hairColor", "skinColor", "outfitColor", "accessoryColor"):
            self.openPixels()
            if self._editor_texture is not None:
                self._sampling_color = name
                self.setMaskFilter("none")

    @Slot(int, int, str, bool)
    def paintPixel(self, x, y, material, restore):
        if self._editor_mode != "pixels" or self._editor_texture is None or not (0 <= x < 64 and 0 <= y < 64):
            self._stroke_last = None
            return
        if material not in CATEGORY_COLORS:
            return
        if self._sampling_color:
            color = self._editor_texture.getpixel((x, y))
            if not restore and color[3] >= 48:
                self.setColor(self._sampling_color, "#%02X%02X%02X" % color[:3])
                self.closeEditor()
            return
        self._paint_pixels(self._stroke_points(x, y), material, restore)

    @Slot(int, int, str, result=int)
    def matchPixelColor(self, x, y, material):
        """Assign the picked source RGB across both layers as one undoable edit."""
        texture = self._editor_texture
        if (self._editor_mode != "pixels" or texture is None or self.samplingColor
                or material not in CATEGORY_COLORS or not (0 <= x < 64 and 0 <= y < 64)):
            return -1
        pixels = texture.load()
        color = pixels[x, y]
        if color[3] < 48:
            return -1

        return self._assign_skin_pixels(material, color[:3], (x, y))

    @Slot(str, result=int)
    def setAllPixels(self, material):
        if (self._editor_mode != "pixels" or self._editor_texture is None
                or self.samplingColor or material not in CATEGORY_COLORS):
            return -1
        return self._assign_skin_pixels(material)

    def _assign_skin_pixels(self, material, rgb=None, picked=None):
        texture = self._editor_texture
        pixels = texture.load()
        slim = resolve_skin_model(texture, self.selectedArmModel) == "slim"
        matches = set()
        for _name, base, overlay, width, depth, height in player_uv_parts(slim):
            for origin in (base, overlay):
                for left, top, right, bottom in cuboid_face_boxes(origin, width, depth, height).values():
                    matches.update((px, py) for py in range(top, bottom) for px in range(left, right)
                                   if pixels[px, py][3] >= 48
                                   and (rgb is None or pixels[px, py][:3] == rgb))
        if picked is not None and picked not in matches:
            return -1

        self.endPixelStroke()
        before = dict(self._editor_corrections)
        self._editor_corrections.update(dict.fromkeys(matches, material))
        if self._editor_corrections != before:
            self._redraw_pixels()
            if not self._commit_pixels(before):
                return -1
        return len(matches)

    @Slot(bool)
    def setMirrorPixels(self, enabled):
        self.endPixelStroke()
        self._mirror_pixels = enabled

    def _paint_pixels(self, points, material, restore):
        if not points:
            return
        if self._mirror_pixels:
            slim = resolve_skin_model(self._editor_texture, self.selectedArmModel) == "slim"
            mirror = mirrored_skin_pixels(slim)
            points = [*points, *(mirror[point] for point in points if point in mirror)]
        if self.texturePainting:
            key = (self.source, self._editor_relative)
            previous = self._texture_drafts.get(key)
            draft = (previous if previous is not None else self._editor_texture).copy()
            paint = QColor(self._texture_color).getRgb()
            changed = False
            for point in points:
                original = self._editor_texture.getpixel(point)
                if original[3] < 48:
                    continue
                color = original if restore else (*paint[:3], original[3])
                if draft.getpixel(point) != color:
                    draft.putpixel(point, color)
                    changed = True
            if changed:
                if self._texture_stroke is None:
                    self._texture_stroke = (key, previous)
                self._texture_drafts[key] = draft
                self._redraw_pixels()
                if not self._preview_timer.isActive():
                    self._preview_timer.start()
            return
        if self._stroke_before is None:
            self._stroke_before = dict(self._editor_corrections)
        changed = False
        for px, py in points:
            coordinate = (px, py)
            if restore:
                changed |= self._editor_corrections.pop(coordinate, None) is not None
            elif self._editor_texture.getpixel(coordinate)[3] >= 48 and self._editor_corrections.get(coordinate) != material:
                self._editor_corrections[coordinate] = material
                changed = True
        if changed:
            self._redraw_pixels()
            if not self._preview_timer.isActive():
                self._preview_timer.start()

    def _stroke_points(self, x, y):
        ox, oy = self._stroke_last or (x, y)
        self._stroke_last = (x, y)
        steps = max(abs(x - ox), abs(y - oy), 1)
        return [(round(ox + (x - ox) * i / steps), round(oy + (y - oy) * i / steps))
                for i in range(1, steps + 1)]

    def _active_corrections(self, skin):
        if self._editor_mode == "pixels" and self._editor_relative == skin.relative:
            return dict(self._editor_corrections)
        return self.picker.get_corrections(skin.relative)

    def _approval_context(self):
        skin = self.current_skin()
        if self._editor_mode != "pixels" or not skin or skin.relative != self._editor_relative:
            raise ValueError("Open Edit Color Areas first")
        raw = skin.path.read_bytes()
        with Image.open(skin.path) as source:
            current, _ = normalize_skin(source)
        if current.tobytes() != self._editor_texture.tobytes():
            raise ValueError("The source skin changed; reopen the editor")
        detector = Path(__file__).with_name("skin_styler_core.py")
        identity = {"source": str(skin.path.resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "detector_sha256": hashlib.sha256(detector.read_bytes()).hexdigest(),
                    "model": resolve_skin_model(current, self.selectedArmModel), "schema": 1}
        classification = apply_category_overrides(self._editor_auto, self._editor_corrections)
        labels = {f"{x},{y}": category for category in ("hair", "skin", "eyes", "outfit", "accessory", "ignore")
                  for x, y in getattr(classification, {"ignore": "ignored"}.get(category, category))}
        return skin, identity, labels

    @Slot(str, "QVariantList", str, bool, result=int)
    def reviewViewportCells(self, token, cells, material, approve):
        if not self.acceptsViewportEdits(token) or material not in ("hair", "skin", "eyes", "outfit", "accessory", "ignore"):
            return -1
        try:
            self.endPixelStroke()
            skin, identity, labels = self._approval_context()
            saved = self.picker.approvals(skin.relative, identity)
            saved = {k: v for k, v in saved.items() if isinstance(v, dict) and labels.get(k) == v.get("label")}
            targets = {f"{int(cell) % 64},{int(cell) // 64}" for cell in cells
                       if type(cell) in (int, float) and 0 <= cell < 4096 and cell == int(cell)}
            targets = {key for key in targets if labels.get(key) == material}
            stamp = datetime.now(timezone.utc).isoformat()
            for key in targets:
                if approve:
                    saved[key] = {"label": material, "approved_at": stamp}
                else:
                    saved.pop(key, None)
            self.picker.set_approvals(skin.relative, identity, saved)
            self._status = "Saved ✓"
            self.statusChanged.emit()
            return len(targets)
        except (OSError, ValueError) as error:
            self._status = "Couldn’t save approval — " + str(error)
            self.statusChanged.emit()
            return -1
    def _save_corrections(self, relative, corrections):
        previous = self.picker.source_data.get(relative)
        try:
            self.picker.set_corrections(relative, corrections)
        except OSError:
            if previous is None:
                self.picker.source_data.pop(relative, None)
            else:
                self.picker.source_data[relative] = previous
            self._status = "Couldn’t save pixel corrections — check folder access"
            self.statusChanged.emit()
            return False
        self._status = "Saved ✓"
        self.statusChanged.emit()
        if self._inspect_materials:
            self._materials_timer.start()
        return True

    def _commit_pixels(self, before):
        after = dict(self._editor_corrections)
        if before == after:
            return True
        skin = self.current_skin()
        if not skin or skin.relative != self._editor_relative:
            return False
        saved = self._save_corrections(skin.relative, after)
        if saved:
            self._undo.append(("pixels", skin.relative, before, after))
            self._redo.clear()
            self.historyChanged.emit()
        else:
            self._editor_corrections = before
            self._redraw_pixels()
        self._refresh_preview()
        return saved

    def _record_texture_edit(self, key, before):
        undo, redo = self._texture_history.setdefault(key, ([], []))
        undo.append(before)
        del undo[:-100]
        redo.clear()
        self.historyChanged.emit()

    @Slot()
    def endPixelStroke(self):
        self._stroke_last = None
        if self._texture_stroke is not None:
            key, before = self._texture_stroke
            self._texture_stroke = None
            self._record_texture_edit(key, before)
        if self._stroke_before is not None:
            before, self._stroke_before = self._stroke_before, None
            self._commit_pixels(before)

    @Slot(int, int, int, int)
    def resetPixels(self, x1, y1, x2, y2):
        if self._editor_mode != "pixels":
            return
        self.endPixelStroke()
        before = dict(self._editor_corrections)
        self._editor_corrections = {
            (x, y): material for (x, y), material in before.items()
            if not (min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2))
        }
        if before != self._editor_corrections:
            self._redraw_pixels()
            self._commit_pixels(before)

    def _eye_source_path(self):
        if self.options["eyeBase"]:
            return None
        source = self.options["eyeReference"]
        if source == "@legacy":
            path = Path(__file__).with_name("custom-eye-reference.png")
            return path if path.is_file() else None
        if not source:
            skin = self.reference_skin() or self.current_skin()
        else:
            skin = next((skin for skin in self.all_skins if skin.relative == source), None)
        return skin.path if skin else None

    @Property(bool, notify=styleChanged)
    def hasEyeReference(self):
        return bool(self.options["eyeBase"]) or self.options["eyeReference"] == "@preset" or self._eye_source_path() is not None

    @Property(bool, constant=True)
    def hasLegacyEyes(self):
        return Path(__file__).with_name("custom-eye-reference.png").is_file()

    @Property(str, notify=styleChanged)
    def eyeReferenceName(self):
        source = self.options["eyeReference"]
        if self.options["eyeBase"]:
            return source.removeprefix("@saved:")
        if source == "@preset":
            return "Soft lashes preset"
        if source == "@legacy":
            return "Legacy saved eyes"
        path = self._eye_source_path()
        if path:
            return path.stem.replace("_", " ") if source else (
                "Follows style reference" if self.reference_skin() else "This skin’s eyes")
        return "Eye source unavailable" if source else "No eye reference yet"

    def _base_eyes(self):
        path = self._eye_source_path()
        try:
            key = (path, path.stat().st_mtime_ns if path else self.options["eyeReference"], self.options["eyeBase"])
            if self._eye_cache is None or self._eye_cache[0] != key:
                if path:
                    with Image.open(path) as source:
                        base = eye_template(source, self.options)
                else:
                    base = eye_template(None, self.options)
                self._eye_cache = key, base
            return self._eye_cache[1]
        except (OSError, ValueError):
            return None

    @Property("QVariantMap", notify=editorChanged)
    def eyeColors(self):
        base = self._base_eyes()
        if base is None:
            return {}
        _template, targets = design_eyes(base, self.options)
        return {EYE_MATERIALS[material]: "#%02X%02X%02X" % color for material, color in targets.items()}

    @Slot(str)
    def setEyeSource(self, choice):
        skin = self.current_skin()
        if choice == "selected" and skin:
            source = skin.relative
        elif choice == "reference":
            source = ""
        elif choice == "preset":
            source = "@preset"
        elif choice == "legacy" and self.hasLegacyEyes:
            source = "@legacy"
        else:
            return
        self.endStyleEdit()
        self._change_style(eyeReference=source, eyeBase={}, eyesEnabled=bool(source or self.reference_skin()),
                           **{key: "" for key in EYE_MATERIALS.values()}, eyePixels={})

    @Slot()
    def openEyes(self):
        skin = self.current_skin()
        if not skin:
            return
        self.closeEditor()
        self._editor_mode, self._editor_relative = "eyes", skin.relative
        self._redraw_eyes()
        self._refresh_preview()

    def _redraw_eyes(self):
        base = self._base_eyes()
        if base:
            self._editor_error = ""
            template, _ = design_eyes(base, self.options)
            self._set_editor_image(eye_canvas(template))
        else:
            self._editor_error = "Choose a valid eye reference or the preset"
            self._editor_image = QImage()
            self.editorChanged.emit()

    @Slot(int, int, str, bool)
    def paintEye(self, x, y, material, restore):
        if self._editor_mode != "eyes" or material not in EYE_TOOLS:
            return
        if not (0 <= x < 8 and 0 <= y < 8):
            self._stroke_last = None
            return
        current = eye_coordinates(self.options["eyePixels"])
        painted = dict(current)
        for px, py in self._stroke_points(x + 8, y + 8):
            coordinate = (px, py)
            if not is_eye_feature_coordinate(*coordinate):
                continue
            for target in (coordinate, mirrored_eye_coordinate(coordinate)) if self.options["eyeMirror"] else (coordinate,):
                if restore:
                    painted.pop(target, None)
                else:
                    painted[target] = material
        if painted != current:
            self.beginStyleEdit()
            # Editing a design freezes which reference supplies its shape.
            self._change_style(eyePixels={f"{x},{y}": m for (x, y), m in painted.items()},
                               eyesEnabled=True, **self._pin_eye_reference())

    def _pin_eye_reference(self):
        reference = self.reference_skin() or self.current_skin()
        return {"eyeReference": reference.relative} if not self.options["eyeReference"] and reference else {}

    @Slot()
    def endEyeStroke(self):
        self._stroke_last = None
        self.endStyleEdit()

    @Slot(str)
    def resetEyeColor(self, name):
        if name in EYE_MATERIALS.values():
            self._change_style(**{name: ""})

    def _eye_designs(self):
        designs = self.settings["eyeDesigns"].get(str(self.source))
        if not isinstance(designs, dict):
            designs = {}
            self.settings["eyeDesigns"][str(self.source)] = designs
        return designs

    @Property("QStringList", notify=styleChanged)
    def eyeDesignNames(self):
        return sorted(self._eye_designs())

    @Slot(str)
    def saveEyeDesign(self, name):
        name = name.strip()[:60]
        if not name:
            return
        self.endEyeStroke()
        if name in self._eye_designs():
            self._status = "That eye design name is already used"
            self.statusChanged.emit()
            return
        base = self._base_eyes()
        if base is None or not design_eyes(base, self.options)[0].features:
            self._status = "Paint at least one eye pixel before saving"
            self.statusChanged.emit()
            return
        keys = ("eyeMirror", "eyePixels", *EYE_MATERIALS.values())
        self._eye_designs()[name] = {
            **{key: self.options[key] for key in keys},
            "eyeBase": freeze_eye_template(base),
            "eyeReference": "@saved:" + name,
        }
        self.styleChanged.emit()
        self._schedule_save()

    @Slot(str)
    def loadEyeDesign(self, name):
        saved = self._eye_designs().get(name)
        if isinstance(saved, dict):
            self.endStyleEdit()
            design = clean_style(saved)
            keys = ("eyeReference", "eyeBase", "eyeMirror", "eyePixels", *EYE_MATERIALS.values())
            self._change_style(eyesEnabled=True, **{key: design[key] for key in keys})

    @Slot(result=bool)
    def setReference(self):
        skin = self.current_skin()
        if skin:
            self.endStyleEdit()
            before = self.reference_relative
            previous_palette = self._reference_hair, self._reference_skin
            self.reference_relative = skin.relative
            self._read_reference()
            if not self._reference_skin:
                self.reference_relative = before
                self._reference_hair, self._reference_skin = previous_palette
                self._status = "Choose a reference with a visible face"
                self.statusChanged.emit()
                return False
            if before != self.reference_relative:
                self._undo.append(("reference", "", before, self.reference_relative))
                self._redo.clear()
                self.historyChanged.emit()
            self._reference_changed()
            self._refresh_preview()
            self._schedule_save()
            return True
        return False

    def _set_style_reference(self, relative):
        self.reference_relative = relative
        self._read_reference()
        self._reference_changed()

    def _reference_changed(self):
        if self.options["hairMode"] == "reference":
            self._hair_hsl = self._hex_hsl(self._effective_hair_color())
        if self.options["skinMode"] == "reference":
            self._extra_hsl.pop("skinColor", None)
        self.model.replace(self.visible_indexes)
        self.styleChanged.emit()
        self.statusChanged.emit()

    def _effective_hair_color(self):
        if self.options["hairMode"] == "reference" and self._reference_hair:
            return self._reference_hair
        return self.options["hairColor"]

    def _sync_hsl(self):
        self._hair_hsl = self._hex_hsl(self._effective_hair_color())
        self._extra_hsl.clear()

    @staticmethod
    def _hex_hsl(value):
        hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255 for c in parse_hex_color(value)))
        return hue * 360, saturation * 100, lightness * 100

    def _read_reference(self):
        self._reference_hair = ""
        self._reference_skin = ""
        skin = self.reference_skin()
        if skin:
            try:
                texture, _ = self._get_materials(skin)
                tone = reference_skin_tone(texture)
                self._reference_skin = "#%02X%02X%02X" % tone if tone is not None else ""
                self._reference_hair = self._sample_detected_hair(skin)
            except (OSError, ValueError):
                pass

    def _sample_detected_hair(self, skin):
        if self.picker.details(skin.relative)["hair_mode"] == "none":
            return ""
        texture, auto = self._get_materials(skin)
        # Use the same final categories as the color area editor and the recolorer. A
        # bow, scalp highlight, or corrected false positive isn't a hair swatch.
        corrected = apply_category_overrides(auto, self.picker.get_corrections(skin.relative))
        try:
            return "#%02X%02X%02X" % representative_hair_color(texture, hair_mask=corrected.hair)
        except ValueError:
            return ""

    def _style_snapshot(self):
        return {"options": dict(self.options),
                "hsl": self._hair_hsl, "extra_hsl": dict(self._extra_hsl)}

    def _stage_style(self, relative, options):
        self.picker.stage_style(relative, options)
        self._skin_style_dirty = True

    def _restore_style(self, relative, snapshot):
        self._stage_style(relative, snapshot["options"])
        if self._style_relative != relative:
            return
        self.options = dict(snapshot["options"])
        self._hair_hsl = (self._hex_hsl(self._effective_hair_color()) if self.options["hairMode"] == "reference"
                          else snapshot["hsl"])
        self._extra_hsl = dict(snapshot["extra_hsl"])
        self.styleChanged.emit()
        if self._editor_mode == "eyes":
            self._redraw_eyes()

    def _record_style(self, before):
        after = self._style_snapshot()
        if before != after and self._style_relative is not None:
            self._stage_style(self._style_relative, after["options"])
            self._undo.append(("style", self._style_relative, before, after))
            self._redo.clear()
            self.historyChanged.emit()
            self._schedule_save()

    @Slot()
    def beginStyleEdit(self):
        if self._style_edit_before is None:
            self._style_edit_before = self._style_snapshot()

    @Slot()
    def endStyleEdit(self):
        if self._style_edit_before is not None:
            before, self._style_edit_before = self._style_edit_before, None
            self._record_style(before)
            for name in ("hairColor", "skinColor", "outfitColor", "accessoryColor", *EYE_MATERIALS.values()):
                color = self.options[name]
                if color and before["options"][name] != color:
                    self._remember_color(color)

    def _change_style(self, **change):
        if self._style_relative is None or all(self.options.get(k) == v for k, v in change.items()):
            return
        before = self._style_snapshot()
        self.options.update(change)
        if "hairColor" in change or "hairMode" in change:
            self._hair_hsl = self._hex_hsl(self._effective_hair_color())
        for name in change:
            self._extra_hsl.pop(name, None)
        if "eyeReference" in change:
            for name in EYE_MATERIALS.values():
                self._extra_hsl.pop(name, None)
        if "skinMode" in change:
            self._extra_hsl.pop("skinColor", None)
        if self._style_edit_before is None:
            self._record_style(before)
        self.styleChanged.emit()
        if self._editor_mode == "eyes":
            self._redraw_eyes()
        if not self._preview_timer.isActive():
            self._preview_timer.start()

    @Slot(str, bool)
    def setStyleToggle(self, name, enabled):
        if isinstance(DEFAULT_STYLE.get(name), bool):
            if name == "eyesEnabled" and enabled and not self.hasEyeReference:
                return
            if name == "hairEnabled" and enabled and not self.styleOptions["hairTargetAvailable"]:
                return
            if name == "skinEnabled" and enabled and not self.styleOptions["skinTargetAvailable"]:
                return
            self._change_style(**{name: enabled})

    @Slot(str)
    def setSkinMode(self, mode):
        if mode in ("reference", "custom"):
            self._change_style(skinMode=mode)

    @Slot(str, str)
    def setColor(self, name, value):
        if name not in ("hairColor", "skinColor", "outfitColor", "accessoryColor", *EYE_MATERIALS.values()):
            return
        try:
            color = "#%02X%02X%02X" % parse_hex_color(value)
        except ValueError:
            self._status = "Use a hex color like #A26EBB"
            self.statusChanged.emit()
            self.styleChanged.emit()
            return
        if name in EYE_MATERIALS.values():
            self._change_style(**{name: color, "eyesEnabled": True}, **self._pin_eye_reference())
            self._remember_color(color)
            return
        change = {name: color, name.removesuffix("Color") + "Enabled": True}
        if name == "skinColor":
            change["skinMode"] = "custom"
        elif name == "hairColor":
            change["hairMode"] = "custom"
        self._change_style(**change)
        self._remember_color(color)

    @Property("QStringList", notify=styleChanged)
    def recentColors(self):
        items = self.settings.get("recentColors")
        if not isinstance(items, list):
            return []
        result = []
        for item in items[:6]:
            if isinstance(item, str):
                try:
                    result.append("#%02X%02X%02X" % parse_hex_color(item))
                except ValueError:
                    pass
        return result

    def _remember_color(self, color):
        recent = [color, *(stored for stored in self.recentColors if stored != color)][:6]
        if recent != self.recentColors:
            self.settings["recentColors"] = recent
            self.styleChanged.emit()
            self._schedule_save()

    @Slot(str)
    def chooseColor(self, name):
        if name in ("hairColor", "skinColor", "outfitColor", "accessoryColor", *EYE_MATERIALS.values()):
            current = self.eyeColors.get(name, "") if name in EYE_MATERIALS.values() else self.styleOptions[name]
            color = QColorDialog.getColor(QColor(current), None, "Choose a color")
            if color.isValid():
                self.setColor(name, color.name())

    @Slot(str, float)
    def setHairChannel(self, channel, value):
        if self._style_relative is None or channel not in ("hue", "saturation", "lightness"):
            return
        before = self._style_snapshot()
        hsl = list(self._hair_hsl)
        index = ("hue", "saturation", "lightness").index(channel)
        hsl[index] = min(360 if index == 0 else 100, max(0, value))
        color = "#%02X%02X%02X" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hsl[0] / 360, hsl[2] / 100, hsl[1] / 100))
        self.options.update(hairColor=color, hairEnabled=True, hairMode="custom")
        self._hair_hsl = tuple(hsl)
        if self._style_edit_before is None:
            self._record_style(before)
        self.styleChanged.emit()
        if not self._preview_timer.isActive():
            self._preview_timer.start()

    @Slot(str, str, float)
    def setColorChannel(self, name, channel, value):
        if name == "hairColor":
            self.setHairChannel(channel, value)
            return
        channels = self.colorChannels.get(name)
        order = ("hue", "saturation", "lightness")
        if channels is None or channel not in order:
            return
        hsl = [channels[key] for key in order]
        hsl[order.index(channel)] = min(360 if channel == "hue" else 100, max(0, value))
        color = "#%02X%02X%02X" % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hsl[0] / 360, hsl[2] / 100, hsl[1] / 100))
        # While a slider is held, retain sub-RGB precision and latent hue on
        # gray colors so the next saturation change works as expected.
        own_edit = self._style_edit_before is None
        if own_edit:
            self.beginStyleEdit()
        if name in EYE_MATERIALS.values():
            self._change_style(**{name: color, "eyesEnabled": True}, **self._pin_eye_reference())
        else:
            extras = {"skinMode": "custom"} if name == "skinColor" else {}
            self._change_style(**{name: color, name.removesuffix("Color") + "Enabled": True}, **extras)
        self._extra_hsl[name] = tuple(hsl)
        self.styleChanged.emit()
        if own_edit:
            self.endStyleEdit()

    @Slot(str)
    def resetMaterialColor(self, material):
        if material == "hair":
            if self._reference_hair:
                self.useReferenceHair()
            else:
                self._change_style(hairColor=DEFAULT_STYLE["hairColor"], hairEnabled=False)
        elif material == "skin":
            self._change_style(skinMode="reference", skinEnabled=bool(self._reference_skin))
        elif material in ("outfit", "accessory"):
            self._change_style(**{material + "Enabled": False})

    @Slot()
    def useReferenceHair(self):
        if self._reference_hair:
            self._change_style(hairMode="reference", hairEnabled=True)

    @Slot(result=bool)
    def sampleHair(self):
        skin = self.current_skin()
        if skin:
            try:
                color = self._sample_detected_hair(skin)
            except (OSError, ValueError):
                color = ""
            if color:
                self.setColor("hairColor", color)
                return True
            else:
                self._status = "No visible hair to sample in this skin"
                self.statusChanged.emit()
        return False

    @Slot(result=bool)
    def sampleSkinTone(self):
        skin = self.current_skin()
        if skin:
            try:
                with Image.open(skin.path) as image:
                    self.setColor("skinColor", "#%02X%02X%02X" % make_face_template(image).skin_color)
                    return True
            except (OSError, ValueError):
                self._status = "Couldn’t sample this skin"
                self.statusChanged.emit()
        return False

    @Slot()
    def chooseSource(self):
        path = QFileDialog.getExistingDirectory(None, "Choose your skin wardrobe", str(self.source.parent))
        if path:
            self.flush()
            self.load_source(Path(path))
            self._schedule_save()


def initialize_viewport():
    directory = Path(__file__).resolve().with_name("viewport")
    if not (directory / "dist" / "viewport.js").is_file():
        return None
    try:
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
    except (ImportError, RuntimeError):
        return None
    return directory / "index.html"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--state-directory", type=Path)
    parser.add_argument("--check-launch", action="store_true", help="Exit after rendering one frame on an Offstage test desktop")
    parser.add_argument("--software-preview", action="store_true", help="Use the original preview renderer")
    parser.add_argument("--require-webgl", action="store_true", help="Require a rendered WebGL frame during --check-launch")
    args = parser.parse_args()
    if args.check_launch and (not os.environ.get("OFFSTAGE_DESKTOP") or args.state_directory is None):
        parser.error("--check-launch requires Offstage and an isolated --state-directory")
    if args.require_webgl and not args.check_launch:
        parser.error("--require-webgl is only for --check-launch")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    viewport_path = None if args.software_preview else initialize_viewport()
    if args.require_webgl and viewport_path is None:
        parser.error("Build the local viewport and install Qt WebEngine first")
    app = QApplication(sys.argv)
    bridge = StudioBridge(source=args.source, state_directory=args.state_directory, viewport_path=viewport_path)
    app.aboutToQuit.connect(bridge.flush)
    app.aboutToQuit.connect(bridge.shutdown)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("skins", SkinImages(bridge))
    engine.rootContext().setContextProperty("studio", bridge)
    errors = []
    engine.warnings.connect(lambda messages: errors.extend(message.toString() for message in messages))
    engine.load(str(Path(__file__).with_name("qml") / "DailyDressStudio.qml"))
    if not engine.rootObjects():
        bridge.shutdown()
        return 1
    if args.check_launch:
        window = engine.rootObjects()[0]
        def check():
            webgl_ready = bridge._viewport_preview_active
            if (not bridge.previewBusy and not bridge.stage_image().isNull()
                    and (webgl_ready or not args.require_webgl)):
                rendered = isinstance(window, QQuickWindow) and not window.grabWindow().isNull()
                success = rendered and not errors and not bridge.previewError
                print(f"Daily Dress native launch: {'OK' if success else 'FAILED'} | {app.platformName()} | "
                      f"{os.environ['OFFSTAGE_DESKTOP']} | {bridge.reviewReviewed} reviewed / "
                      f"{bridge.reviewRemaining} left | {'WebGL' if webgl_ready else 'software'}", flush=True)
                app.exit(0 if success else 1)
            else:
                QTimer.singleShot(50, check)
        QTimer.singleShot(400, check)
        QTimer.singleShot(10000, lambda: app.exit(1))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
