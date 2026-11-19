"""Local studio safety/state tests; no Minecraft or real wardrobe writes."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

if os.environ.get("DAILY_DRESS_REQUIRE_OFFSTAGE") and not os.environ.get("OFFSTAGE_DESKTOP"):
    raise RuntimeError("Refusing to run graphical tests outside an Offstage desktop")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PIL import Image
from PySide6.QtCore import QMetaObject, QObject, QPoint, QUrl, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage, QPalette

from daily_dress_qml import SkinImages, StudioBridge
from skin_styler_core import detect_skin_model
from studio_eyes import design_eyes, eye_template
from test_skin_styler import synthetic_skin


APP = QApplication.instance() or QApplication([])


class StudioTests(unittest.TestCase):
    def test_reviewed_pixels_persist_and_corrections_invalidate_them(self):
        bridge = self.bridge
        original = (self.source / "a_dress.png").read_bytes()
        bridge._viewport_path = self.root / "index.html"
        bridge.openPixels()
        bridge.paintPixel(44, 20, "hair", False)
        bridge.endPixelStroke()
        token = bridge._viewport_token()
        self.assertEqual(bridge.reviewViewportCells(token, [20 * 64 + 44], "hair", True), 1)
        skin, identity, _ = bridge._approval_context()
        self.assertEqual(bridge.picker.approvals(skin.relative, identity)["44,20"]["label"], "hair")
        bridge.paintPixel(45, 20, "hair", False)
        bridge.endPixelStroke()
        self.assertEqual(bridge.reviewViewportCells(token, [20 * 64 + 45], "hair", True), 1)
        self.assertEqual(set(bridge.picker.approvals(skin.relative, identity)), {"44,20", "45,20"})
        bridge.reviewViewportCells(token, [20 * 64 + 45], "hair", False)
        self.assertEqual(set(bridge.picker.approvals(skin.relative, identity)), {"44,20"})
        restored = type(bridge.picker)(self.source, state_directory=self.state)
        self.assertIn("44,20", restored.approvals(skin.relative, identity))
        bridge.paintPixel(44, 20, "skin", False)
        bridge.endPixelStroke()
        self.assertNotIn("44,20", bridge.picker.approvals(skin.relative, identity))
        self.assertEqual(original, (self.source / "a_dress.png").read_bytes())

    def test_mirror_edits_follow_the_model_and_undo_together(self):
        bridge = self.bridge
        bridge.openPixels()
        bridge.setArmModel("slim")
        bridge.setMirrorPixels(True)
        bridge.paintPixel(44, 20, "skin", False)
        bridge.endPixelStroke()
        self.assertEqual(bridge.picker.get_corrections("a_dress.png"), {(44, 20): "skin", (38, 52): "skin"})
        bridge.undo()
        self.assertEqual(bridge.correctionCount, 0)
        bridge.closeEditor()
        bridge.openPixels()
        bridge.paintPixel(44, 20, "skin", False)
        bridge.endPixelStroke()
        self.assertEqual(bridge.correctionCount, 1)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "skins"
        self.source.mkdir()
        for name, color in (("a_dress", "red"), ("b_casual", "blue"), ("c_cozy", "green")):
            Image.new("RGBA", (64, 64), color).save(self.source / (name + ".png"))
        (self.source / "broken.png").write_bytes(b"not an image")
        self.state = self.root / "state"
        self.bridge = StudioBridge(self.source, self.state)

    def wait_preview(self, bridge=None):
        bridge = self.bridge if bridge is None else bridge
        for _ in range(150):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        self.assertFalse(bridge.previewBusy)
        self.assertEqual(bridge.previewError, "")

    def tearDown(self):
        self.bridge.flush()
        self.bridge.shutdown()
        self.bridge.deleteLater()
        APP.processEvents()
        self.temporary.cleanup()

    def test_sort_reference_and_history_do_not_touch_originals(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
        self.assertEqual(len(self.bridge.all_skins), 3)
        self.bridge.setStatus("favorite")
        self.bridge.setTag("dresses")
        self.bridge.setReference()
        self.bridge.flush()
        self.assertEqual(self.bridge.referenceName, "a dress")
        self.assertTrue(self.bridge.canUndo)
        self.bridge.undo()
        self.assertEqual(self.bridge.referenceName, "No reference yet")
        self.bridge.undo()
        self.assertEqual(self.bridge.selectedTag, "other")
        self.bridge.redo()
        self.bridge.redo()
        self.bridge.flush()
        self.assertEqual(self.bridge.selectedTag, "dresses")
        restored = StudioBridge(self.source, self.state)
        self.assertEqual(restored.referenceName, "a dress")
        self.assertEqual(restored.selectedStatus, "favorite")
        self.assertEqual(restored.selectedTag, "dresses")
        restored.shutdown()
        restored.deleteLater()
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()})
        self.assertFalse((self.source / "wardrobe-picker-state.json").exists())

    def test_composable_filters_remove_and_undo(self):
        self.bridge.setStatus("favorite")
        self.bridge.setTag("dresses")
        self.bridge.setFilter("Favorites")
        self.bridge.setFilter("Dresses")
        self.assertEqual(self.bridge.model.rowCount(), 1)
        self.assertEqual(self.bridge.selectedName, "a dress")
        self.bridge.setStatus("remove")
        self.assertTrue(self.bridge.selectionHeld)
        self.assertEqual(self.bridge.selectedName, "a dress")
        self.assertEqual(self.bridge.selectedStatus, "remove")
        self.bridge.undo()
        self.assertEqual(self.bridge.selectedName, "a dress")
        self.assertFalse(self.bridge.selectionHeld)
        self.bridge.setFilter("All")
        self.bridge.setSearch("cozy")
        self.assertEqual(self.bridge.selectedName, "c cozy")
        self.bridge.setStatus("remove")
        self.assertEqual(self.bridge.selectedName, "c cozy")
        self.assertTrue(self.bridge.selectionHeld)
        self.bridge.setFilter("Removed")
        self.assertEqual(self.bridge.selectedName, "c cozy")
        self.assertFalse(self.bridge.selectionHeld)

    def test_review_progress_wrap_undo_and_saved_filters(self):
        bridge = self.bridge
        before = {path: path.read_bytes() for path in self.source.glob("*.png")}
        bridge.setFilter("Unsorted")
        bridge.setSearch("casual")
        bridge.setTag("dresses")
        bridge.toggleReview()
        self.assertEqual(bridge.selectedName, "b casual")
        self.assertEqual((bridge.reviewReviewed, bridge.reviewRemaining), (0, 3))
        bridge.setStatus("keep")
        self.assertEqual(bridge.selectedName, "c cozy")
        bridge.setStatus("maybe")
        self.assertEqual(bridge.selectedName, "a dress")
        bridge.setStatus("remove")
        self.assertEqual((bridge.reviewReviewed, bridge.reviewRemaining), (3, 0))
        self.assertEqual(bridge.selectedName, "All caught up!")
        bridge.undo()
        self.assertEqual(bridge.selectedName, "a dress")
        self.assertEqual(bridge.selectedStatus, "unsorted")
        self.assertEqual((bridge.reviewReviewed, bridge.reviewRemaining), (2, 1))
        bridge.redo()
        self.assertEqual(bridge.reviewRemaining, 0)
        bridge.toggleReview()
        self.assertEqual(bridge.statusFilter, "unsorted")
        self.assertFalse(bridge.hasSkins)
        bridge.setFilter("All")
        self.assertEqual(bridge.selectedName, "b casual")  # search restored
        self.assertEqual(bridge.selectedTag, "dresses")

        restored = StudioBridge(self.source, self.state)
        try:
            for name, expected in (("Removed", "a dress"), ("Maybe", "c cozy"), ("Kept", "b casual")):
                restored.setFilter(name)
                self.assertEqual(restored.model.rowCount(), 1)
                self.assertEqual(restored.selectedName, expected)
            restored.toggleReview()
            self.assertEqual(restored.reviewRemaining, 0)
        finally:
            restored.shutdown()
            restored.deleteLater()
        self.assertEqual(before, {path: path.read_bytes() for path in self.source.glob("*.png")})

    def test_ordinary_sorting_holds_selected_then_resumes_normal_filter(self):
        bridge = self.bridge
        bridge.selectVisible(1)
        bridge.setStatus("favorite")
        self.assertEqual(bridge.selectedName, "b casual")
        bridge.setStatus("remove")
        self.assertEqual(bridge.selectedName, "b casual")
        self.assertTrue(bridge.selectionHeld)
        bridge.selectVisible(2)
        self.assertEqual(bridge.selectedName, "c cozy")
        self.assertEqual(bridge.model.rowCount(), 2)
        bridge.undo()
        self.assertEqual(bridge.selectedName, "b casual")
        self.assertEqual(bridge.selectedStatus, "favorite")
        bridge.setFilter("Kept")
        self.assertEqual(bridge.model.rowCount(), 1)

    def test_failed_review_save_does_not_advance_or_change_progress(self):
        bridge = self.bridge
        bridge.toggleReview()
        with patch.object(bridge.picker, "save", side_effect=OSError("disk full")):
            bridge.setStatus("keep")
        self.assertEqual(bridge.selectedName, "a dress")
        self.assertEqual(bridge.selectedStatus, "unsorted")
        self.assertEqual(bridge.reviewRemaining, 3)
        self.assertFalse(bridge.canUndo)
        self.assertIn("Couldn’t save", bridge.statusText)

    def test_qml_review_numbers_are_fast_and_protect_text_entry(self):
        bridge = self.bridge
        for i in range(12):
            Image.new("RGBA", (64, 64), (i, 90, 180)).save(self.source / f"extra_{i:02}.png")
        bridge.load_source(self.source)
        ordered = [skin.relative for skin in bridge.all_skins]
        warnings = []
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
        engine.addImageProvider("skins", SkinImages(bridge))
        engine.rootContext().setContextProperty("studio", bridge)
        engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "DailyDressStudio.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.resize(980, 680)
        QTest.qWait(300)
        search = window.findChild(QObject, "wardrobeSearch")
        search.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_1)
        self.assertEqual(search.property("text"), "1")
        self.assertEqual(bridge.reviewRemaining, len(ordered))
        QTest.keyClick(window, Qt.Key_Backspace)
        hair = window.findChild(QObject, "hairHex")
        hair.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_2)
        self.assertEqual(bridge.reviewRemaining, len(ordered))

        origin = bridge.current_skin().relative
        cursor = ordered.index(origin)
        ordered = ordered[cursor:] + ordered[:cursor]
        review = window.findChild(QObject, "reviewUnsorted")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, review.mapToScene(QPoint(20, 15)).toPoint())
        self.assertTrue(bridge.reviewMode)
        bridge.openPixels()
        QTest.keyClick(window, Qt.Key_4)
        self.assertEqual(bridge.reviewRemaining, len(ordered))
        QTest.keyClick(window, Qt.Key_Escape)
        self.assertEqual(bridge.editorMode, "")
        QTest.qWait(0)

        keys = [Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4]
        decisions = ["favorite", "keep", "maybe", "remove"]
        # Returning from a nonempty queue must restore the browse skin, not
        # whatever card the filtered ListView happens to snap to.
        QTest.keyClick(window, Qt.Key_1)
        self.assertEqual(bridge.picker.get(origin)["status"], "favorite")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, review.mapToScene(QPoint(20, 15)).toPoint())
        QTest.qWait(300)
        self.assertEqual(bridge.current_skin().relative, origin)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, review.mapToScene(QPoint(20, 15)).toPoint())
        pending = sorted(set(ordered) - {origin})
        cursor = pending.index(bridge.current_skin().relative)
        pending = pending[cursor:] + pending[:cursor]
        # No waits for rendering or carousel animations between decisions.
        for i, relative in enumerate(pending, start=1):
            self.assertEqual(bridge.current_skin().relative, relative)
            QTest.keyClick(window, keys[i % 4])
            self.assertEqual(bridge.picker.get(relative)["status"], decisions[i % 4])
        self.assertFalse(bridge.hasSkins)
        progress = window.findChild(QObject, "reviewProgress")
        self.assertEqual(progress.property("text"), f"{len(ordered)} reviewed · 0 left")
        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(bridge.current_skin().relative, pending[-1])
        self.assertEqual(bridge.selectedStatus, "unsorted")
        self.assertEqual(bridge.reviewRemaining, 1)
        QTest.keyClick(window, keys[(len(ordered) - 1) % 4])
        self.assertEqual(bridge.reviewRemaining, 0)
        QTest.qWait(250)
        self.assertEqual(window.findChild(QObject, "carousel").property("currentIndex"), -1)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, review.mapToScene(QPoint(20, 15)).toPoint())
        QTest.qWait(200)
        self.assertFalse(bridge.reviewMode)
        self.assertEqual(bridge.current_skin().relative, origin)
        self.assertEqual(warnings, [])
        window.close()
        engine.deleteLater()
        APP.processEvents()

        if os.environ.get("OFFSTAGE_DESKTOP"):
            # Restart the application in a separate process, reusing the
            # scratch files written by the real keyboard decisions above.
            output = subprocess.check_output([
                sys.executable, str(Path(__file__).with_name("daily_dress_qml.py")),
                "--source", str(self.source), "--state-directory", str(self.state), "--check-launch",
            ], text=True, timeout=15)
            self.assertIn(f"{len(ordered)} reviewed / 0 left", output)

    def test_metadata_does_not_reset_delegates(self):
        resets = []
        self.bridge.model.modelReset.connect(lambda: resets.append(True))
        self.bridge.selectVisible(2)
        self.bridge.setStatus("favorite")
        self.assertEqual(self.bridge.selectedIndex, 2)
        self.assertEqual(resets, [])
        self.bridge.setSearch("cozy")
        self.assertEqual(self.bridge.model.rowCount(), 1)
        self.assertEqual(resets, [])

    def test_preview_rotation_and_reset(self):
        self.wait_preview()
        original = self.bridge.stage_image()
        self.bridge.rotate(90)
        self.wait_preview()
        self.assertNotEqual(original, self.bridge.stage_image())
        self.bridge.resetView()
        self.wait_preview()
        self.assertEqual(original, self.bridge.stage_image())

    def test_source_change_invalidates_thumbnails(self):
        provider = SkinImages(self.bridge)
        first = provider.requestImage("thumb/1/auto/0", None, None)
        other = self.root / "other"
        other.mkdir()
        Image.new("RGBA", (64, 64), "yellow").save(other / "z.png")
        self.bridge.load_source(other)
        second = provider.requestImage("thumb/2/auto/0", None, None)
        self.assertNotEqual(first, second)
        self.assertEqual(self.bridge.selectedName, "z")

    def test_arm_model_updates_thumbnail_and_preview_and_persists_per_skin(self):
        relative = "a_dress.png"
        original_bytes = (self.source / relative).read_bytes()
        model = self.bridge.model
        row = model.index(0)
        role = int(Qt.UserRole) + model.names.index("thumbnail")
        provider = SkinImages(self.bridge)
        auto_uri = model.data(row, role)
        auto_thumb = provider.requestImage(auto_uri.removeprefix("image://skins/"), None, None)
        self.wait_preview()
        auto_preview = self.bridge.stage_image(original=True)

        self.bridge.setArmModel("slim")
        self.wait_preview()
        slim_uri = model.data(row, role)
        self.assertNotEqual(slim_uri, auto_uri)
        self.assertNotEqual(provider.requestImage(slim_uri.removeprefix("image://skins/"), None, None), auto_thumb)
        self.assertNotEqual(self.bridge.stage_image(original=True), auto_preview)

        self.bridge.selectVisible(1)
        self.assertEqual(self.bridge.selectedArmModel, "auto")
        self.bridge.undo()
        self.assertEqual(self.bridge.selectedIndex, 1)
        self.assertEqual(self.bridge.picker.model(relative), "auto")
        self.bridge.redo()
        self.assertEqual(self.bridge.picker.model(relative), "slim")
        reopened = StudioBridge(self.source, self.state)
        try:
            self.assertEqual(reopened.selectedArmModel, "slim")
            reopened.setArmModel("auto")
            self.assertEqual(reopened.selectedArmModel, "auto")
            self.assertEqual((self.source / relative).read_bytes(), original_bytes)
        finally:
            reopened.shutdown()
            reopened.deleteLater()

    def test_arm_model_save_failure_restores_previous_preference(self):
        self.bridge.setArmModel("classic")
        with patch.object(self.bridge.picker, "save", side_effect=OSError("locked")):
            self.bridge.setArmModel("slim")
        self.assertEqual(self.bridge.selectedArmModel, "classic")
        self.assertIn("Couldn’t save arm model", self.bridge.statusText)

    def test_match_source_color_across_layers_is_one_undoable_saved_edit(self):
        path = self.source / "a_dress.png"
        source = synthetic_skin()
        shade = (183, 132, 104)
        matches = {(22, 25), (22, 40), (4, 24)}
        for point in matches:
            source.putpixel(point, (*shade, 184 if point == (22, 40) else 255))
        source.putpixel((23, 25), (184, 132, 104, 255))
        source.putpixel((0, 0), (*shade, 255))  # unused head padding
        source.putpixel((24, 40), (*shade, 0))
        source.save(path)
        original = path.read_bytes()
        bridge = self.bridge
        bridge.openPixels()
        bridge.paintPixel(22, 40, "outfit", False)
        bridge.endPixelStroke()
        history = len(bridge._undo)
        self.assertEqual(bridge.matchPixelColor(0, 0, "skin"), -1)
        self.assertEqual(bridge.matchPixelColor(22, 25, "skin"), len(matches))
        self.assertEqual(bridge.picker.get_corrections(path.name), dict.fromkeys(matches, "skin"))
        self.assertEqual(len(bridge._undo), history + 1)
        bridge.undo()
        self.assertEqual(bridge.picker.get_corrections(path.name), {(22, 40): "outfit"})
        bridge.redo()
        bridge.paintPixel(22, 40, "skin", True)
        bridge.endPixelStroke()
        reopened = StudioBridge(self.source, self.state)
        try:
            self.assertEqual(reopened.picker.get_corrections(path.name), {(22, 25): "skin", (4, 24): "skin"})
            self.assertEqual(path.read_bytes(), original)
        finally:
            reopened.shutdown()
            reopened.deleteLater()

    def test_style_persists_per_skin_and_hair_keeps_eyes_independent(self):
        self.bridge.setReference()
        self.assertFalse(self.bridge.options["eyesEnabled"])
        self.bridge.setStyleToggle("eyesEnabled", True)
        reference = self.bridge.reference_relative
        self.bridge.setStyleToggle("eyesOverBangs", False)
        self.bridge.setStyleToggle("keep3DLashes", False)
        self.bridge.setColor("hairColor", "#7D42B4")
        self.assertEqual(self.bridge.reference_relative, reference)
        self.assertTrue(self.bridge.options["eyesEnabled"])
        self.assertFalse(self.bridge.options["eyesOverBangs"])
        self.assertFalse(self.bridge.options["keep3DLashes"])
        self.bridge.setColor("skinColor", "#B07862")
        selected = dict(self.bridge.options)
        self.bridge.selectVisible(1)
        self.assertTrue(self.bridge.options["hairEnabled"])
        self.assertFalse(self.bridge.options["eyesEnabled"])
        self.bridge.setColor("hairColor", "#AD79EC")
        self.bridge.setStyleToggle("hairEnabled", False)
        self.bridge.selectVisible(0)
        self.assertEqual(self.bridge.options, selected)
        self.bridge.flush()
        restored = StudioBridge(self.source, self.state)
        self.assertEqual(restored.options, self.bridge.options)
        restored.selectVisible(1)
        self.assertFalse(restored.options["hairEnabled"])
        self.assertEqual(restored.options["hairColor"], "#AD79EC")
        restored.shutdown()
        other = self.root / "empty"
        other.mkdir()
        self.bridge.load_source(other)
        self.assertFalse(self.bridge.options["hairEnabled"])
        self.assertFalse(self.bridge.options["skinEnabled"])
        self.bridge.load_source(self.source)
        self.assertEqual(self.bridge.options["hairColor"], "#7D42B4")
        self.assertTrue(self.bridge.options["skinEnabled"])

    def test_saved_opt_outs_take_precedence_and_legacy_colors_remain_available(self):
        self.state.mkdir(exist_ok=True)
        self.bridge.settings_path.write_text(json.dumps({"styles": {str(self.source): {
            "hairEnabled": True, "hairColor": "#AABBCC", "eyesEnabled": True,
            "outfitEnabled": True, "outfitColor": "#487E8F", "accessoryColor": "#BADACE",
        }}, "references": {str(self.source): "a_dress.png"}}), encoding="utf-8")
        self.bridge.picker.stage_style("a_dress.png", {"hairEnabled": False, "skinEnabled": False})
        self.bridge.picker.save()
        restored = StudioBridge(self.source, self.state)
        try:
            self.assertEqual(restored.referenceName, "a dress")
            self.assertTrue({"#AABBCC", "#487E8F", "#BADACE"} <= set(restored.recentColors))
            for key in ("hairEnabled", "skinEnabled", "outfitEnabled", "accessoryEnabled", "eyesEnabled"):
                self.assertFalse(restored.options[key])
            self.wait_preview(restored)
            self.assertEqual(restored.stage_image(), restored.stage_image(original=True))
            restored.selectVisible(1)
            self.assertTrue(restored.options["hairEnabled"])
            self.assertTrue(restored.options["skinEnabled"])
            for key in ("outfitEnabled", "accessoryEnabled", "eyesEnabled"):
                self.assertFalse(restored.options[key])
            restored.flush()
            self.assertEqual(json.loads(restored.settings_path.read_text(encoding="utf-8"))["styleScopeVersion"], 1)
        finally:
            restored.shutdown()
            restored.deleteLater()

    def test_duplicate_look_shares_png_but_saves_independent_choices(self):
        bridge = self.bridge
        path = bridge.current_skin().path
        original = path.read_bytes()
        bridge.setStatus("keep")
        bridge.setTag("dresses")
        bridge.setArmModel("slim")
        bridge.setColor("outfitColor", "#487E8F")
        bridge.setColor("accessoryColor", "#CC704D")
        bridge.openPixels()
        bridge.paintPixel(20, 25, "outfit", False)
        bridge.closeEditor()
        bridge.duplicateLook()
        look = bridge.current_skin()
        self.assertNotEqual(look.relative, "a_dress.png")
        self.assertEqual(look.path, path)
        self.assertEqual(bridge.selectedName, "Look 2 · a dress")
        self.assertEqual(bridge.selectedStatus, "unsorted")
        self.assertEqual(bridge.selectedTag, "dresses")
        self.assertEqual(bridge.selectedArmModel, "slim")
        self.assertEqual(bridge.picker.get_corrections(look.relative), {(20, 25): "outfit"})
        self.assertEqual(bridge.options["outfitColor"], "#487E8F")
        bridge.setColor("outfitColor", "#AB639C")
        bridge.setStyleToggle("accessoryEnabled", False)
        bridge.selectVisible(0)
        self.assertTrue(bridge.options["accessoryEnabled"])
        self.assertEqual(bridge.options["outfitColor"], "#487E8F")
        bridge.undo()
        self.assertEqual(bridge.current_skin(), look)
        self.assertTrue(bridge.options["accessoryEnabled"])
        bridge.redo()
        self.assertFalse(bridge.options["accessoryEnabled"])
        bridge.setStyleToggle("outfitEnabled", False)
        self.wait_preview()
        self.assertEqual(bridge.stage_image(), bridge.stage_image(original=True))
        self.assertEqual(bridge.options["outfitColor"], "#AB639C")
        bridge.setStyleToggle("outfitEnabled", True)
        bridge.flush()
        reopened = StudioBridge(self.source, self.state)
        try:
            reopened.setSearch("look 2")
            self.assertEqual(reopened.current_skin(), look)
            self.assertEqual(reopened.options["outfitColor"], "#AB639C")
            self.assertFalse(reopened.options["accessoryEnabled"])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(list(self.source.glob("*.png"))), 4)
        finally:
            reopened.shutdown()
            reopened.deleteLater()

    def test_slider_gesture_is_one_undo_and_color_validation_is_non_destructive(self):
        before = dict(self.bridge.options)
        self.bridge.beginStyleEdit()
        for hue in (60, 90, 150, 210, 270):
            self.bridge.setHairChannel("hue", hue)
        self.bridge.endStyleEdit()
        self.assertEqual(len(self.bridge._undo), 1)
        self.bridge.undo()
        self.assertEqual(before, self.bridge.options)
        self.bridge.redo()
        after = dict(self.bridge.options)
        self.bridge.setColor("hairColor", "nope")
        self.assertEqual(after, self.bridge.options)

    def test_reference_skin_target_tracks_reference_not_hair_and_custom_mode_undoes(self):
        from test_skin_styler import synthetic_skin
        from skin_styler_core import make_face_template
        skin = synthetic_skin()
        skin.save(self.source / "a_dress.png")
        self.bridge.setReference()
        self.assertTrue(self.bridge.options["skinEnabled"])
        expected = "#%02X%02X%02X" % make_face_template(skin).skin_color
        self.assertEqual(self.bridge.styleOptions["skinColor"], expected)
        self.bridge.setStyleToggle("skinEnabled", True)
        self.bridge.setColor("hairColor", "#6FB88E")
        self.assertEqual(self.bridge.styleOptions["skinColor"], expected)
        self.bridge.setColor("skinColor", "#B07862")
        self.assertEqual(self.bridge.options["skinMode"], "custom")
        self.assertEqual(self.bridge.styleOptions["skinColor"], "#B07862")
        self.bridge.undo()
        self.assertEqual(self.bridge.options["skinMode"], "reference")
        self.assertEqual(self.bridge.styleOptions["skinColor"], expected)

    def test_reference_defaults_to_matching_hair_and_skin_and_samples_final_material_mask(self):
        bridge = self.bridge
        wanted_hair = (100, 45, 25, 255)
        reference = synthetic_skin(hair=(130, 50, 210, 255))
        reference.putpixel((10, 2), wanted_hair)
        reference.save(self.source / "a_dress.png")
        bridge.picker.set_corrections("a_dress.png", {
            **{(x, y): "ignore" for x in range(32) for y in range(16)},
            (10, 2): "hair",
        })
        bridge.setEyeSource("preset")
        bridge.setStyleToggle("eyesEnabled", False)
        self.wait_preview()
        self.assertEqual(bridge.stage_image(), bridge.stage_image(original=True))
        self.assertFalse(bridge.styleOptions["hairTargetAvailable"])
        self.assertFalse(bridge.styleOptions["skinTargetAvailable"])
        before = bridge._style_snapshot()
        history = len(bridge._undo)
        self.assertTrue(bridge.setReference())
        self.assertEqual(bridge.referenceHairColor, "#642D19")
        self.assertTrue(bridge.options["hairEnabled"])
        self.assertTrue(bridge.options["skinEnabled"])
        self.assertEqual(bridge.options["skinMode"], "reference")
        self.assertEqual(bridge.options["eyeReference"], "@preset")
        self.assertFalse(bridge.options["eyesEnabled"])
        self.assertEqual(len(bridge._undo), history + 1)
        bridge.undo()
        self.assertEqual(bridge._style_snapshot(), before)
        bridge.redo()
        bridge.selectVisible(1)
        self.assertTrue(bridge.options["hairEnabled"])
        self.assertTrue(bridge.options["skinEnabled"])
        self.assertFalse(bridge.options["outfitEnabled"])
        from studio_preview import styled_texture
        next_skin = synthetic_skin(hair=(60, 85, 145, 255))
        for y in range(11, 16):
            for x in range(9, 15):
                next_skin.putpixel((x, y), (244, 201, 178, 255))
        result = styled_texture(next_skin, reference, bridge.styleOptions, {}, {})
        self.assertNotEqual(result.getpixel((10, 2)), next_skin.getpixel((10, 2)))
        self.assertNotEqual(result.getpixel((11, 15)), next_skin.getpixel((11, 15)))
        self.assertEqual(result.getpixel((23, 23)), next_skin.getpixel((23, 23)))
        bridge.flush()
        reopened = StudioBridge(self.source, self.state)
        try:
            reopened.selectVisible(1)
            self.assertEqual(reopened.options, bridge.options)
            self.assertEqual(reopened.referenceName, "a dress")
        finally:
            reopened.shutdown()
            reopened.deleteLater()

    def test_reference_without_a_visible_face_does_not_replace_the_style(self):
        bridge = self.bridge
        bridge.setReference()
        before = bridge._style_snapshot()
        bridge.selectVisible(1)
        texture = Image.new("RGBA", (64, 64))
        texture.putpixel((10, 2), (100, 60, 20, 255))
        texture.save(self.source / "b_casual.png")
        self.assertFalse(bridge.setReference())
        self.assertEqual(bridge._style_snapshot(), before)
        self.assertIn("visible face", bridge.statusText)

    def test_background_preview_keeps_last_frame_and_coalesces_latest_edit(self):
        self.wait_preview()
        previous = self.bridge.stage_image()
        gate = threading.Event()
        started = threading.Event()
        calls = []
        class DelayedRenderer:
            def render(inner, request):
                calls.append(request)
                started.set()
                gate.wait(3)
                return (previous, previous)
        self.bridge._renderer = DelayedRenderer()
        try:
            self.bridge.selectVisible(1)
            self.assertTrue(started.wait(1))
            self.bridge.selectVisible(2)
            self.bridge.selectVisible(0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.bridge.stage_image(), previous)
            from PySide6.QtCore import QTimer
            responsive = []
            QTimer.singleShot(10, lambda: responsive.append(True))
            QTest.qWait(30)
            self.assertTrue(responsive)
            gate.set()
            self.wait_preview()
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1].path.name, "a_dress.png")
        finally:
            gate.set()

    def test_preview_error_keeps_last_frame_then_recovers(self):
        self.wait_preview()
        previous = self.bridge.stage_image()
        missing = self.bridge.all_skins[1].path
        data = missing.read_bytes()
        missing.unlink()
        self.bridge.selectVisible(1)
        for _ in range(100):
            QTest.qWait(20)
            if not self.bridge.previewBusy:
                break
        self.assertTrue(self.bridge.previewError)
        self.assertEqual(previous, self.bridge.stage_image())
        missing.write_bytes(data)
        self.bridge._refresh_preview()
        self.wait_preview()

    def test_pixel_stroke_restore_reset_and_reopen_by_skin(self):
        bridge = self.bridge
        path = bridge.current_skin().path
        synthetic_skin().save(path)
        original = path.read_bytes()
        bridge.setColor("hairColor", "#2FE7B3")
        self.wait_preview()
        uncorrected = bridge.stage_image()
        bridge.openPixels()
        bridge.paintPixel(21, 25, "hair", False)
        bridge.paintPixel(24, 25, "hair", False)
        bridge.endPixelStroke()
        self.assertEqual(bridge.correctionCount, 4)
        self.wait_preview()
        self.assertNotEqual(uncorrected, bridge.stage_image())
        bridge.undo()
        self.assertEqual(bridge.correctionCount, 0)
        bridge.redo()
        self.assertEqual(bridge.correctionCount, 4)
        bridge.paintPixel(22, 25, "hair", True)
        bridge.endPixelStroke()
        bridge.resetPixels(23, 24, 24, 26)
        self.assertEqual(bridge.correctionCount, 1)
        bridge.closeEditor()
        self.assertEqual(bridge.selectedIndex, 0)
        bridge.selectVisible(1)
        bridge.openPixels()
        self.assertEqual(bridge.correctionCount, 0)
        bridge.flush()
        restored = StudioBridge(self.source, self.state)
        try:
            restored.openPixels()
            self.assertEqual(restored.correctionCount, 1)
            self.assertEqual(restored.picker.get_corrections(path.name), {(21, 25): "hair"})
            self.assertEqual(path.read_bytes(), original)
        finally:
            restored.shutdown()
            restored.deleteLater()

    def test_viewport_hits_do_not_bridge_atlas_tiles_and_stale_tokens_are_ignored(self):
        bridge = self.bridge
        bridge._viewport_path = self.root / "index.html"
        bridge.openPixels()
        token = bridge._viewport_token()
        bridge.paintViewportCells(token, [65, 102.0, 105.5, -1], "hair", False)
        bridge.endViewportStroke(token)
        self.assertEqual(bridge.picker.get_corrections("a_dress.png"), {(1, 1): "hair", (38, 1): "hair"})
        bridge.undo()
        self.assertEqual(bridge.correctionCount, 0)
        bridge.closeEditor()
        bridge.openPixels()
        bridge.paintViewportCells(token, [65], "hair", False)
        self.assertEqual(bridge.correctionCount, 0)

    def test_eye_design_and_material_colors_persist_independently(self):
        bridge = self.bridge
        bridge.setReference()
        bridge.setColor("hairColor", "#FF80AA")
        bridge.selectVisible(1)
        bridge.setEyeSource("selected")
        self.assertEqual(bridge.eyeReferenceName, "b casual")
        bridge.setEyeSource("preset")
        bridge.openEyes()
        bridge.setColor("irisColor", "#39B299")
        bridge.setColor("linerColor", "#361222")
        bridge.setColor("whiteColor", "#F0CDFE")
        bridge.paintEye(2, 6, "iris", False)
        bridge.endEyeStroke()
        self.assertEqual(bridge.options["eyePixels"], {"10,14": "iris", "13,14": "iris"})
        rendered, _ = design_eyes(eye_template(None, bridge.options), bridge.options)
        self.assertEqual(rendered.features[10, 14], (57, 178, 153, 255))
        self.assertEqual(rendered.features[8, 13], (54, 18, 34, 255))
        self.assertEqual(rendered.features[9, 14], (240, 205, 254, 255))
        bridge.undo()
        self.assertEqual(bridge.options["eyePixels"], {})
        bridge.redo()
        bridge.saveEyeDesign("Seafoam")
        bridge.closeEditor()
        bridge.setColor("outfitColor", "#3D61ED")
        bridge.setColor("accessoryColor", "#FDCA57")
        bridge.setEyeSource("reference")
        bridge.loadEyeDesign("Seafoam")
        bridge.flush()
        restored = StudioBridge(self.source, self.state)
        try:
            self.assertEqual(restored.options["hairColor"], "#FF80AA")
            self.assertFalse(restored.options["eyesEnabled"])
            restored.selectVisible(1)
            self.assertEqual(restored.options, bridge.options)
            self.assertEqual(restored.eyeDesignNames, ["Seafoam"])
            self.assertEqual(restored.referenceName, "a dress")
            self.assertEqual(restored.options["hairMode"], "reference")
            self.assertEqual(restored.eyeReferenceName, "Seafoam")
            self.assertEqual(restored.options["outfitColor"], "#3D61ED")
            self.assertEqual(restored.options["accessoryColor"], "#FDCA57")
        finally:
            restored.shutdown()
            restored.deleteLater()

    def test_saved_eye_design_survives_reference_skin_moving(self):
        bridge = self.bridge
        reference = bridge.current_skin().path
        synthetic_skin(eye=(85, 160, 210, 255)).save(reference)
        synthetic_skin(eye=(100, 90, 160, 255)).save(self.source / "b_casual.png")
        bridge.setEyeSource("selected")
        bridge.openEyes()
        bridge.setColor("irisColor", "#FB87DB")
        bridge.paintEye(2, 6, "iris", False)
        bridge.endEyeStroke()
        expected, _ = design_eyes(bridge._base_eyes(), bridge.options)
        bridge.saveEyeDesign("Pink glitter")
        bridge.closeEditor()
        bridge.selectVisible(1)
        bridge.loadEyeDesign("Pink glitter")
        self.wait_preview()
        expected_frame = bridge.stage_image()
        bridge.setEyeSource("preset")
        bridge.flush()
        reference.rename(self.root / "moved-reference.png")
        restored = StudioBridge(self.source, self.state)
        try:
            restored.loadEyeDesign("Pink glitter")
            self.assertTrue(restored.hasEyeReference)
            self.assertIsNone(restored._eye_source_path())
            self.assertEqual(restored.eyeReferenceName, "Pink glitter")
            actual, _ = design_eyes(restored._base_eyes(), restored.options)
            self.assertEqual(actual, expected)
            self.wait_preview(restored)
            self.assertEqual(restored.stage_image(), expected_frame)
            restored.openEyes()
            restored.setColor("irisColor", "#CC4EAA")
            self.assertIsNotNone(restored._base_eyes())
            self.assertTrue(restored.editorSource)
        finally:
            restored.shutdown()
            restored.deleteLater()

    def test_exact_color_sampling_writes_no_correction_and_hsl_resets(self):
        bridge = self.bridge
        path = bridge.current_skin().path
        skin = synthetic_skin()
        skin.putpixel((40, 9), (130, 90, 145, 255))
        skin.save(path)
        bridge.openColorSampler("accessoryColor")
        bridge.paintPixel(62, 62, "hair", False)
        self.assertTrue(bridge.samplingColor)
        bridge.paintPixel(40, 9, "hair", False)
        self.assertEqual(bridge.options["accessoryColor"], "#825A91")
        self.assertEqual(bridge.editorMode, "")
        self.assertFalse(bridge.picker.get_corrections(path.name))
        self.assertFalse(bridge.styleOptions["hairTargetAvailable"])
        undo_depth = len(bridge._undo)
        bridge.beginStyleEdit()
        bridge.setColorChannel("accessoryColor", "hue", 120)
        bridge.setColorChannel("accessoryColor", "lightness", 60)
        bridge.endStyleEdit()
        self.assertEqual(len(bridge._undo), undo_depth + 1)
        bridge.resetMaterialColor("accessory")
        self.assertFalse(bridge.options["accessoryEnabled"])
        self.assertIn("#825A91", bridge.recentColors)

    def test_qml_editors_keep_comparison_camera_and_selection(self):
        bridge = self.bridge
        slim = synthetic_skin()
        slim.putpixel((40, 9), (90, 60, 120, 255))
        slim.save(self.source / "a_dress.png")
        self.assertEqual(detect_skin_model(slim), "slim")
        self.assertEqual(detect_skin_model(Image.new("RGBA", (64, 64), "blue")), "classic")
        source_hashes = {p: p.read_bytes() for p in self.source.glob("*.png")}
        bridge.load_source(self.source)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
        engine.addImageProvider("skins", SkinImages(bridge))
        engine.rootContext().setContextProperty("studio", bridge)
        engine.load(str(Path(__file__).parent / "qml" / "DailyDressStudio.qml"))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.resize(980, 680)
        QTest.qWait(300)
        window.setProperty("viewMode", "Compare")
        window.setProperty("comparePosition", .68)
        stage = window.findChild(QObject, "stage")
        preview_frame = window.findChild(QObject, "stageImage").parentItem()
        preview_frame.setProperty("zoom", 1.15)
        from_point = stage.mapToScene(QPoint(150, 150)).toPoint()
        initial_yaw = bridge._yaw
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, from_point)
        QTest.mouseMove(window, from_point + QPoint(76, 0), 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, from_point + QPoint(76, 0))
        camera = bridge._yaw
        self.assertNotEqual(camera, initial_yaw)
        self.assertAlmostEqual(window.property("comparePosition"), .68)
        carousel = window.findChild(QObject, "carousel")
        carousel_offset = carousel.property("contentX")

        def click(item, x, y, button=Qt.LeftButton):
            QTest.mouseClick(window, button, Qt.NoModifier, item.mapToScene(QPoint(x, y)).toPoint())

        def cell(x, y, size, button=Qt.LeftButton):
            texture = window.findChild(QObject, "pixelTexture")
            width = texture.property("width")
            click(texture, int((x + .5) * width / size), int((y + .5) * width / size), button)

        def snapshot(name):
            target = os.environ.get("DAILY_DRESS_QA_SHOTS")
            if target:
                self.assertTrue(window.grabWindow().save(str(Path(target) / name)))

        click(window.findChild(QObject, "fixPixels"), 15, 12)
        QTest.qWait(100)
        self.assertEqual(bridge.editorMode, "pixels")
        self.assertFalse(window.findChild(QObject, "inspector").property("visible"))
        self.assertFalse(window.findChild(QObject, "wardrobeTray").property("visible"))
        canvas = window.findChild(QObject, "pixelCanvas")
        click(window.findChild(QObject, "pixelZoomIn"), 8, 12)
        self.assertGreater(canvas.property("zoom"), 1)
        cell(22, 25, 64)
        self.assertEqual(bridge.correctionCount, 1)
        bridge.setMaskFilter("auto")
        self.assertNotEqual(bridge._editor_image, QImage())
        bridge.setMaskFilter("all")
        cell(22, 25, 64, Qt.RightButton)
        self.assertEqual(bridge.correctionCount, 0)
        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(bridge.correctionCount, 1)
        snapshot("fix-pixels.png")
        reset = window.findChild(QObject, "resetAllPixels")
        dialog = window.findChild(QObject, "resetPixelDialog")
        click(reset, 24, 12)
        QTest.qWait(150)
        self.assertTrue(dialog.property("visible"))
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(150)
        self.assertFalse(dialog.property("visible"))
        self.assertEqual(bridge.correctionCount, 1)
        self.assertEqual(bridge.editorMode, "pixels")
        click(reset, 24, 12)
        self.assertTrue(QMetaObject.invokeMethod(dialog, "accept"))
        self.assertEqual(bridge.correctionCount, 0)
        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(bridge.correctionCount, 1)
        previous_skin = window.findChild(QObject, "previousPixelSkin")
        next_skin = window.findChild(QObject, "nextPixelSkin")
        self.assertFalse(previous_skin.property("visible"))
        for index in (1, 2):
            click(next_skin, 24, 45)
            self.assertEqual(bridge.selectedIndex, index)
            self.assertEqual(bridge.editorMode, "pixels")
            self.assertEqual(window.findChild(QObject, "pixelCanvas"), canvas)
            self.assertGreater(canvas.property("zoom"), 1)
            self.assertEqual(bridge.correctionCount, 0)
        self.assertFalse(next_skin.property("visible"))
        click(previous_skin, 24, 45)
        click(previous_skin, 24, 45)
        self.assertEqual(bridge.selectedIndex, 0)
        self.assertEqual(bridge.correctionCount, 1)
        QTest.keyClick(window, Qt.Key_Escape)
        self.assertEqual(bridge.editorMode, "")

        bridge.setEyeSource("preset")
        bridge.openEyes()
        self.wait_preview()
        QTest.qWait(200)
        snapshot("design-eyes.png")
        cell(2, 6, 8)
        self.assertEqual(bridge.options["eyePixels"], {"10,14": "iris", "13,14": "iris"})
        # Repeater delegates have visual parents but not necessarily QObject
        # parents under the window.
        pending = [window.contentItem()]
        while pending:
            field = pending.pop()
            if field.objectName() == "irisColorHex":
                break
            pending.extend(field.childItems())
        self.assertEqual(field.objectName(), "irisColorHex")
        click(field, 22, 9)
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for character in "#D84F77":
            QTest.keyClick(window, Qt.Key(ord(character)))
        QTest.keyClick(window, Qt.Key_Return)
        self.assertEqual(bridge.options["irisColor"], "#D84F77")
        self.wait_preview()
        self.assertTrue(bridge.styledFaceSource)
        snapshot("design-eyes.png")
        QTest.keyClick(window, Qt.Key_Escape)
        self.assertEqual(bridge.editorMode, "")
        self.assertEqual(bridge._yaw, camera)
        self.assertAlmostEqual(preview_frame.property("zoom"), 1.15)
        self.assertEqual(bridge.selectedIndex, 0)
        self.assertAlmostEqual(carousel.property("contentX"), carousel_offset, delta=1)
        self.assertEqual(window.property("viewMode"), "Compare")
        self.assertAlmostEqual(window.property("comparePosition"), .68)
        window.setProperty("activeMaterial", "outfit")
        QTest.qWait(50)
        self.assertTrue(window.findChild(QObject, "inspector").property("visible"))
        self.assertTrue(window.findChild(QObject, "wardrobeTray").property("visible"))
        pick = window.findChild(QObject, "pickMaterialColor")
        self.assertEqual(pick.property("text"), "Pick outfit color…")
        self.assertIsNone(window.findChild(QObject, "hairHex"))
        click(pick, 18, 10)
        QTest.qWait(80)
        self.assertEqual(window.findChild(QObject, "pixelWorkspaceTitle").property("text"), "Pick outfit color")
        self.assertFalse(window.findChild(QObject, "wardrobeTray").property("visible"))
        hair_before = bridge.options["hairColor"]
        cell(21, 25, 64)
        self.assertEqual(bridge.options["outfitColor"], "#%02X%02X%02X" % slim.getpixel((21, 25))[:3])
        self.assertEqual(bridge.options["hairColor"], hair_before)
        self.assertEqual(window.property("activeMaterial"), "outfit")
        self.assertEqual(bridge.editorMode, "")
        self.assertEqual(bridge._yaw, camera)
        self.assertAlmostEqual(preview_frame.property("zoom"), 1.15)
        self.assertEqual(window.findChild(QObject, "categoryLabel").property("text"), "OUTFIT CATEGORY")
        window.setProperty("activeMaterial", "accessory")
        bridge.selectVisible(1)
        self.wait_preview()
        for mode, expected in (("Original", bridge.originalSource), ("Compare", bridge.stageSource), ("Styled", bridge.stageSource)):
            window.setProperty("viewMode", mode)
            self.assertEqual(window.findChild(QObject, "stageImage").property("source").toString(), expected)
        window.setProperty("viewMode", "Compare")
        snapshot("compare-after-editors.png")
        self.assertEqual(source_hashes, {p: p.read_bytes() for p in self.source.glob("*.png")})
        self.assertEqual(warnings, [])
        window.close()
        engine.deleteLater()
        APP.processEvents()

    def test_qml_selection_and_responsive_shell(self):
        saved_palette = APP.palette()
        self.addCleanup(APP.setPalette, saved_palette)
        dark = QPalette(saved_palette)
        dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        dark.setColor(QPalette.ColorRole.Base, QColor("#202020"))
        dark.setColor(QPalette.ColorRole.Window, QColor("#171419"))
        dark.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        dark.setColor(QPalette.ColorRole.ToolTipBase, QColor("#09080a"))
        dark.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
        APP.setPalette(dark)
        warnings = []
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
        engine.addImageProvider("skins", SkinImages(self.bridge))
        engine.rootContext().setContextProperty("studio", self.bridge)
        engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "DailyDressStudio.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        QTest.qWait(350)
        # QObject avoids depending on the private Python wrapper for QQuickListView.
        from PySide6.QtCore import QObject
        carousel = window.findChild(QObject, "carousel")
        tray = window.findChild(QObject, "wardrobeTray")
        self.assertAlmostEqual(tray.property("width"), window.width() - 40, delta=1)
        self.assertAlmostEqual(carousel.property("preferredHighlightBegin"), (carousel.property("width") - 124) / 2)
        self.bridge.selectVisible(2)
        QTest.qWait(300)
        self.assertEqual(carousel.property("currentIndex"), 2)
        self.bridge.setSearch("casual")
        QTest.qWait(300)
        self.assertEqual(self.bridge.selectedName, "b casual")
        self.assertEqual(carousel.property("currentIndex"), 0)
        window.resize(980, 680)
        QTest.qWait(250)
        self.assertAlmostEqual(tray.property("width"), 940, delta=1)
        self.assertGreater(window.findChild(QObject, "stage").property("width"), 600)
        self.bridge.setSearch("")
        self.bridge.selectVisible(0)
        QTest.qWait(350)
        carousel.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Right)
        QTest.qWait(300)
        self.assertEqual(self.bridge.selectedIndex, 1)
        self.bridge.selectVisible(0)
        QTest.qWait(350)
        origin = carousel.mapToScene(QPoint(490, 70)).toPoint()
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, origin)
        for step in range(1, 11):
            QTest.mouseMove(window, origin - QPoint(step * 18, 0), 12)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, origin - QPoint(180, 0))
        QTest.qWait(900)
        self.assertGreater(self.bridge.selectedIndex, 0)
        self.assertEqual(carousel.property("currentIndex"), self.bridge.selectedIndex)
        # The before/after wipe is a real interactive control, not a placeholder.
        window.setProperty("viewMode", "Compare")
        QTest.qWait(200)
        wipe = window.findChild(QObject, "compareHandle")
        center = wipe.mapToScene(QPoint(12, 40)).toPoint()
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, center)
        QTest.mouseMove(window, center + QPoint(70, 0), 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, center + QPoint(70, 0))
        self.assertGreater(window.property("comparePosition"), .55)
        window.resize(1440, 900)
        QTest.qWait(250)
        hair_hex = window.findChild(QObject, "hairHex")
        self.assertEqual(hair_hex.property("color").name(), "#42394b")
        self.assertEqual(hair_hex.property("selectedTextColor").name(), "#ffffff")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, hair_hex.mapToScene(QPoint(20, 10)).toPoint())
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(150, 200))
        self.assertFalse(self.bridge.styleOptions["hairTargetAvailable"])
        def visible_item(name):
            pending = [window.contentItem()]
            while pending:
                item = pending.pop()
                if item.objectName() == name and item.isVisible():
                    return item
                pending.extend(item.childItems())
            self.fail(f"No visible item named {name}")

        skin_tab = visible_item("skinMaterialTab")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, skin_tab.mapToScene(QPoint(18, 12)).toPoint())
        self.assertEqual(window.property("activeMaterial"), "skin")
        self.assertIsNone(window.findChild(QObject, "hairHex"))
        self.assertEqual(window.findChild(QObject, "skinHex").property("color").name(), "#42394b")
        hair_tab = visible_item("hairMaterialTab")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, hair_tab.mapToScene(QPoint(18, 12)).toPoint())
        QTest.qWait(100)
        wheel = visible_item("materialColorWheel")
        self.assertIsNotNone(wheel)
        self.assertIsNone(window.findChild(QObject, "materialColorOptions"))
        undo_count = len(self.bridge._undo)
        with patch("daily_dress_qml.QColorDialog.getColor", return_value=QColor("#6BA0D1")) as choose:
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, wheel.mapToScene(QPoint(17, 15)).toPoint())
            choose.assert_called_once()
        self.assertEqual(self.bridge.options["hairColor"], "#6BA0D1")
        self.assertEqual(len(self.bridge._undo), undo_count + 1)
        window.setProperty("viewMode", "Original")
        reference_button = visible_item("useStyleReference")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, reference_button.mapToScene(QPoint(45, 12)).toPoint())
        self.assertTrue(self.bridge.hasReference)
        self.assertTrue(self.bridge.options["skinEnabled"])
        self.assertFalse(self.bridge.options["eyesEnabled"])
        self.assertEqual(window.property("viewMode"), "Original")
        self.assertEqual(len(self.bridge._undo), undo_count + 2)
        portrait = visible_item("referencePortrait")
        self.assertIsNotNone(portrait)
        self.assertTrue(portrait.property("source").toString().startswith("image://skins/thumb/"))
        QTest.mouseMove(window, portrait.mapToScene(QPoint(15, 18)).toPoint())
        QTest.qWait(600)
        self.assertTrue(any(tip.property("visible") and tip.property("text") == self.bridge.current_skin().path.name
                            for tip in window.findChildren(QObject, "studioHelpTip")))
        category = visible_item("outfitCategory")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, category.mapToScene(QPoint(20, 14)).toPoint())
        QTest.qWait(150)
        popup = next(popup for popup in window.findChildren(QObject, "studioDropdownList") if popup.property("visible"))
        self.assertTrue(popup.property("visible"))
        self.assertEqual(popup.property("background").property("color").name(), "#fffafd")
        casual = visible_item("studioDropdownChoice2")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, casual.mapToScene(QPoint(20, 14)).toPoint())
        self.assertEqual(self.bridge.selectedTag, "casual")
        self.assertFalse(popup.property("visible"))
        category.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        self.assertTrue(popup.property("visible"))
        QTest.keyClick(window, Qt.Key_Up)
        QTest.keyClick(window, Qt.Key_Return)
        self.assertEqual(self.bridge.selectedTag, "dresses")
        self.assertFalse(popup.property("visible"))
        pick = visible_item("pickMaterialColor")
        QTest.mouseMove(window, pick.mapToScene(QPoint(20, 12)).toPoint())
        QTest.qWait(600)
        tips = [tip for tip in window.findChildren(QObject, "studioHelpTip")
                if tip.property("visible") and tip.property("text") == "Set hair color from a pixel on this skin"]
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0].property("background").property("color").name(), "#faf3ff")
        self.assertEqual(warnings, [])
        window.close()
        engine.deleteLater()
        APP.processEvents()


if __name__ == "__main__":
    unittest.main()
