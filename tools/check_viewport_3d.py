"""Exercise the WebEngine viewport with scratch skins on the hidden desktop."""
import json
import os
import tempfile
from pathlib import Path

if not os.environ.get("OFFSTAGE_DESKTOP"):
    raise SystemExit("Run this graphical check through offstage-windows.")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PIL import ImageDraw
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from daily_dress_qml import SkinImages, StudioBridge, initialize_viewport
from test_skin_styler import synthetic_skin


def wait_for(predicate, description):
    for _ in range(240):
        if predicate():
            return
        QTest.qWait(25)
    raise AssertionError(description)


def main():
    viewport = initialize_viewport()
    assert viewport is not None, "Build the local viewport before running the check"
    app = QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "skins"
        source.mkdir()
        slim = synthetic_skin(hair=(108, 64, 36, 255))
        draw = ImageDraw.Draw(slim)
        draw.rectangle((28, 16, 35, 19), fill=(10, 180, 40, 255))
        draw.rectangle((0, 20, 15, 31), fill=(215, 149, 117, 255))
        draw.rectangle((16, 52, 31, 63), fill=(215, 149, 117, 255))
        slim.save(source / "a_clear_outer.png")
        classic = slim.copy()
        draw = ImageDraw.Draw(classic)
        draw.rectangle((32, 0, 63, 15), fill=(52, 171, 110, 255))
        draw.rectangle((54, 20, 55, 31), fill=(52, 171, 110, 255))
        draw.rectangle((46, 52, 47, 63), fill=(52, 171, 110, 255))
        classic.save(source / "b_opaque_outer.png")
        original_bytes = {p: p.read_bytes() for p in source.glob("*.png")}
        bridge = StudioBridge(source, root / "state", viewport)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda notices: warnings.extend(n.toString() for n in notices))
        engine.addImageProvider("skins", SkinImages(bridge))
        engine.rootContext().setContextProperty("studio", bridge)
        engine.load(str(Path(__file__).with_name("qml") / "DailyDressStudio.qml"))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1100, 760)
        look_up = lambda name: window.findChild(QObject, name)
        try:
            live = look_up("gpuPreview")
            wait_for(lambda: live.property("ready"), f"3D preview never rendered: {warnings}")
            assert window.property("viewMode") == "Compare", "Studio should start in Compare"
            assert not look_up("stageImage").property("visible"), "Software fallback is still showing"
            bridge.setColor("hairColor", "#A962D5")
            bridge.setColor("outfitColor", "#487E8F")
            bridge.rotate(-25)
            wait_for(lambda: not bridge.previewBusy and not bridge._preview_timer.isActive(), "Preview job did not finish")
            QTest.qWait(250)
            shot = window.grabWindow()
            dpr = shot.devicePixelRatio()
            def shade_at(x, y):
                point = live.mapToScene(QPoint(x, y))
                return shot.pixelColor(round(point.x() * dpr), round(point.y() * dpr))
            halves = [(shade_at(int(live.width() / 2) - 10, y),
                       shade_at(int(live.width() / 2) + 10, y))
                      for y in range(int(live.height() * .06), int(live.height() * .17))]
            assert any(left.red() > left.blue() + 20 and right.blue() > right.red() + 20
                       for left, right in halves), "Compare did not show original brown and tinted purple on opposite halves"
            snapshot(window, "viewport-compare.png")
            wipe = look_up("compareHandle")
            start = wipe.mapToScene(QPoint(12, 30)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPoint(55, 0), 25)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPoint(55, 0))
            split = window.property("comparePosition")
            assert split > .53, "Compare divider did not drag over WebEngine"

            editor_button = look_up("fixPixels")
            assert editor_button.property("text") == "Edit Color Areas"
            click(window, editor_button)
            QTest.qWait(50)
            assert look_up("pixelWorkspaceTitle").property("text") == "Edit Color Areas"
            fix = look_up("fixViewport")
            wait_for(lambda: fix.property("ready"), f"Default 3D editor never rendered: {warnings}")
            rect = look_up("editWebViewport")
            texture = look_up("pixelCanvas")
            assert not texture.property("visible"), "Texture should be hidden by default"
            assert look_up("editorCompareHandle").property("visible"), "Editor should start in Compare"
            assert not look_up("mirrorPixels").property("checked")
            click(window, look_up("approveVisiblePixels"))
            wait_for(lambda: bool(bridge.picker.data.get("approvals", {}).get(bridge.picker.source_key, {}).get("a_clear_outer.png", {}).get("pixels")),
                     "Visible hair approval did not save")
            approved = bridge.picker.data["approvals"][bridge.picker.source_key]["a_clear_outer.png"]["pixels"]
            assert all(item["label"] == "hair" for item in approved.values())
            front = set(approved)
            bridge.rotate(180)
            QTest.qWait(500)
            click(window, look_up("approveVisiblePixels"))
            wait_for(lambda: len(bridge.picker.data["approvals"][bridge.picker.source_key]["a_clear_outer.png"]["pixels"]) > len(front),
                     "Approvals from the back did not accumulate with the front")
            combined = set(bridge.picker.data["approvals"][bridge.picker.source_key]["a_clear_outer.png"]["pixels"])
            assert front < combined
            click(window, look_up("unapproveVisiblePixels"))
            wait_for(lambda: set(bridge.picker.data["approvals"][bridge.picker.source_key]["a_clear_outer.png"]["pixels"]) < combined,
                     "Undo approval did not remove the visible approval")
            bridge.rotate(-180)
            QTest.qWait(500)
            click(window, look_up("editorCompare"))
            before_correction = json.loads(bridge.viewportPacket)["styled"]
            match = look_up("matchPixelColor")
            click(window, match)
            torso_pixel = rect.mapToScene(QPoint(int(rect.width() / 2) - 8, int(rect.height() * .46))).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, torso_pixel)
            wait_for(lambda: bridge.correctionCount > 1 and json.loads(bridge.viewportPacket)["styled"] != before_correction,
                     "The match-color edit must change the styled texture")
            after_correction = json.loads(bridge.viewportPacket)["styled"]
            QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
            wait_for(lambda: bridge.correctionCount == 0 and json.loads(bridge.viewportPacket)["styled"] == before_correction,
                     "Ctrl+Z must undo the pixel correction and refresh the 3D texture")
            assert bridge.options["outfitColor"] == "#487E8F"
            QTest.keyClick(window, Qt.Key_Y, Qt.ControlModifier)
            wait_for(lambda: bridge.correctionCount > 1 and json.loads(bridge.viewportPacket)["styled"] == after_correction,
                     "Ctrl+Y must redo the correction and refresh the 3D texture")
            click(window, look_up("studioUndo"))
            wait_for(lambda: bridge.correctionCount == 0 and json.loads(bridge.viewportPacket)["styled"] == before_correction,
                     "The Undo button must also refresh the 3D texture")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, torso_pixel)
            QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
            QTest.qWait(250)
            assert bridge.correctionCount == 0 and bridge.options["outfitColor"] == "#487E8F", (
                "An immediate Undo must wait for the last 3D click before changing history"
            )
            click(window, match)
            click(window, look_up("editorCompare"))
            editor_wipe = look_up("editorCompareHandle")
            assert editor_wipe.property("visible")
            start = editor_wipe.mapToScene(QPoint(12, 30)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start - QPoint(45, 0), 25)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start - QPoint(45, 0))
            assert editor_wipe.property("fraction") < split - .03, "Editor Compare divider did not drag"
            assert window.property("comparePosition") == split
            QTest.qWait(100)
            shot = window.grabWindow()
            dpr = shot.devicePixelRatio()
            cut = int(rect.width() * editor_wipe.property("fraction"))
            halves = [(shade_at_editor(shot, rect, cut - 12, y, dpr), shade_at_editor(shot, rect, cut + 12, y, dpr))
                      for y in range(int(rect.height() * .07), int(rect.height() * .19))]
            assert any(left.red() > left.blue() + 20 and right.blue() > right.red() + 20
                       for left, right in halves), "Editor Compare must show both versions"
            snapshot(window, "viewport-editor-compare.png")
            click(window, look_up("editorCompare"))
            click(window, look_up("pixelZoomIn"))
            wait_for(lambda: fix.property("viewZoom") > 1, "Plus did not zoom the model")
            click(window, look_up("fixPixels3D"))
            assert texture.property("visible") and not rect.property("visible")
            wait_for(lambda: visible_item(window, "atlasPartGuide") is not None, "Texture guide boxes did not appear")
            snapshot(window, "viewport-atlas-part-guides.png")
            atlas = look_up("pixelTexture")
            match = look_up("matchPixelColor")
            wand = look_up("matchWandIcon")
            wait_for(lambda: wand.property("sourceSize").width() > 0, "Match color wand did not load")
            assert match.mapToScene(QPoint(0, 0)).y() < atlas.mapToScene(QPoint(0, 0)).y()
            click(window, match)
            assert match.property("checked")
            QTest.qWait(100)
            point = atlas.mapToScene(QPoint(int(22.5 * atlas.width() / 64), int(25.5 * atlas.height() / 64))).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            first_count = bridge.correctionCount
            assert first_count > 1 and match.property("checked"), (first_count, match.property("checked"), point)
            second = atlas.mapToScene(QPoint(int(5.5 * atlas.width() / 64), int(23.5 * atlas.height() / 64))).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, second)
            assert bridge.correctionCount > first_count and match.property("checked")
            bridge.undo()
            bridge.undo()
            assert bridge.correctionCount == 0
            click(window, look_up("atlasGuideToggle"))
            assert visible_item(window, "atlasPartGuide") is None
            click(window, look_up("pixelZoomIn"))
            assert texture.property("zoom") > 1 and fix.property("viewZoom") == 1.5
            click(window, look_up("fixPixels3D"))
            assert rect.property("visible") and not texture.property("visible")
            assert match.property("checked"), "Switching views turned off Match color"
            click(window, match)
            assert not match.property("checked")
            click(window, look_up("pixelZoomOut"))
            wait_for(lambda: fix.property("viewZoom") == 1, "Minus did not zoom the model")
            click(window, look_up("pixelZoomOut"))
            wait_for(lambda: fix.property("viewZoom") < 1, "Minus did not zoom past the fitted size")
            click(window, look_up("pixelFit"))
            wait_for(lambda: fix.property("viewZoom") == 1, "Fit did not reset 3D zoom")
            legs = rect.mapToScene(QPoint(int(rect.width() / 2) - 10, int(rect.height() * .8))).toPoint()
            QTest.mouseMove(window, legs)
            wait_for(lambda: fix.property("hit").x() >= 0, "Leg should be pickable before hiding it")
            assert look_up("editorBodyParts").property("visible")
            for name in ("Right leg", "Left leg"):
                wait_for(lambda: visible_item(window, "bodyPart" + name) is not None, "Body part controls did not open")
                item = visible_item(window, "bodyPart" + name)
                click(window, item)
                assert not item.property("checked")
            QTest.qWait(150)
            snapshot(window, "viewport-parts-panel.png")
            QTest.mouseMove(window, legs + QPoint(1, 0))
            wait_for(lambda: fix.property("hit").x() < 0, "Hidden legs must be excluded from picking")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, legs)
            assert bridge.correctionCount == 0
            torso = rect.mapToScene(QPoint(int(rect.width() / 2), int(rect.height() / 2))).toPoint()
            middle_drag(window, torso, QPoint(0, -90))
            underside = rect.mapToScene(QPoint(int(rect.width() / 2) - 10, int(rect.height() * .56))).toPoint()
            QTest.mouseMove(window, underside)
            wait_for(lambda: 28 <= fix.property("hit").x() < 36 and 16 <= fix.property("hit").y() < 20,
                     "Could not pick the underside of the torso with the legs hidden")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, underside)
            wait_for(lambda: len(bridge.picker.get_corrections("a_clear_outer.png")) == 1,
                     "Could not save an edit under the torso")
            bridge.undo()
            middle_drag(window, torso, QPoint(0, 90))
            QTest.qWait(100)
            snapshot(window, "viewport-fix-before-hover.png")
            before_hover = window.grabWindow()
            target = rect.mapToScene(QPoint(int(rect.width() / 2), int(rect.height() * .20))).toPoint()
            QTest.qWait(150)
            QTest.mouseMove(window, target - QPoint(1, 0))
            QTest.mouseMove(window, target)
            wait_for(lambda: fix.property("hit").x() >= 0, f"No hover hit at {target} through transparent overlay")
            hit = fix.property("hit")
            assert hit.x() < 32 and hit.y() < 16, f"Expected base head under transparent hat, got {hit}"
            QTest.qWait(100)
            highlighted = window.grabWindow()
            center = target * highlighted.devicePixelRatio()
            assert any(highlighted.pixelColor(center + QPoint(dx, dy)).name() == "#ffffff"
                       and before_hover.pixelColor(center + QPoint(dx, dy)).name() != "#ffffff"
                       for dx in range(-18, 19) for dy in range(-18, 19)), "No visible white pixel outline"
            snapshot(window, "viewport-fix-pixels.png")
            click(window, match)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target)
            wait_for(lambda: len(bridge.picker.get_corrections("a_clear_outer.png")) > 1,
                     "Picking one color in 3D did not save its other matching pixels")
            assert match.property("checked"), "3D color match turned itself off"
            snapshot(window, "viewport-match-wand-active.png")
            window.resize(window.minimumWidth(), 760)
            QTest.qWait(100)
            parts = look_up("editorBodyParts")
            card = look_up("stageCard")
            assert parts.mapToScene(QPoint(int(parts.width()), 0)).x() <= card.mapToScene(QPoint(int(card.width()), 0)).x()
            window.resize(1100, 760)
            QTest.qWait(100)
            bridge.undo()
            assert bridge.correctionCount == 0
            click(window, match)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target)
            wait_for(lambda: len(bridge.picker.get_corrections("a_clear_outer.png")) == 1,
                     "Individual 3D correction wasn't committed")
            hit = fix.property("hit")
            assert bridge.picker.get_corrections("a_clear_outer.png") == {(int(hit.x()), int(hit.y())): "hair"}
            QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, target)
            wait_for(lambda: not bridge.picker.get_corrections("a_clear_outer.png"),
                     "Right-click did not restore automatic classification")
            bridge.undo()
            assert bridge.correctionCount == 1
            start = rect.mapToScene(QPoint(int(rect.width() / 2), int(rect.height() / 2))).toPoint()
            QTest.mouseMove(window, start)
            wait_for(lambda: fix.property("hit").x() >= 0, "No model hit before turning")
            facing = fix.property("hit")
            QTest.mousePress(window, Qt.MiddleButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPoint(140, 0), 30)
            QTest.mouseRelease(window, Qt.MiddleButton, Qt.NoModifier, start + QPoint(140, 0))
            QTest.mouseMove(window, start)
            wait_for(lambda: fix.property("hit").x() >= 0 and fix.property("hit") != facing,
                     "Middle-drag did not rotate the model")
            assert bridge.correctionCount == 1
            assert not look_up("previousPixelSkin").property("visible")
            click(window, look_up("editorCompare"))
            editor_split = look_up("editorCompareHandle").property("fraction")
            click(window, look_up("pixelZoomIn"))
            wait_for(lambda: fix.property("viewZoom") > 1, "Zoom did not finish before navigating")
            # Stay off the divider's drag strip while painting the torso.
            brush = start + QPoint(-22 if editor_split >= .5 else 22, 0)
            QTest.mouseMove(window, brush)
            QTest.qWait(75)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, brush)
            click(window, look_up("nextPixelSkin"))
            wait_for(lambda: bridge.selectedIndex == 1, "Next skin did not open in Edit Color Areas")
            assert len(bridge.picker.get_corrections("a_clear_outer.png")) == 2, "Navigation lost a pending 3D edit"
            assert bridge.editorMode == "pixels" and look_up("fixViewport") == fix
            assert fix.property("viewZoom") > 1 and look_up("editorCompareHandle").property("fraction") == editor_split
            assert not look_up("nextPixelSkin").property("visible")
            snapshot(window, "viewport-pixel-neighbors.png")
            click(window, look_up("previousPixelSkin"))
            wait_for(lambda: bridge.selectedIndex == 0, "Previous skin did not reopen in Edit Color Areas")
            assert bridge.correctionCount == 2
            close_pixels = look_up("leavePixels")
            card = look_up("stageCard")
            assert close_pixels.property("text") == "×" and close_pixels.y() < card.y()
            assert close_pixels.x() + close_pixels.width() > card.x() + card.width()
            outside = close_pixels.mapToScene(QPoint(int(close_pixels.width()) - 4, 16)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, outside)
            assert bridge.editorMode == ""
            assert window.property("viewMode") == "Compare" and window.property("comparePosition") == split

            bridge.selectVisible(1)
            wait_for(lambda: not bridge.previewBusy, "Classic skin did not load")
            assert '"slim":false' in bridge.viewportPacket
            arm_model = look_up("stageArmModel")
            assert arm_model.property("displayText") == "Arms: Auto"
            choose_option(window, arm_model, 1)
            wait_for(lambda: '"slim":true' in bridge.viewportPacket, "Slim override did not update 3D geometry")
            bridge.openPixels()
            QTest.qWait(50)
            fix = look_up("fixViewport")
            wait_for(lambda: fix.property("ready"), "Classic editor did not render")
            arm_model = look_up("pixelArmModel")
            assert arm_model.property("displayText") == "Arms: Slim"
            choose_option(window, arm_model, 2)
            wait_for(lambda: '"slim":false' in bridge.viewportPacket, "Regular override did not update 3D geometry")
            rect = look_up("editWebViewport")
            target = rect.mapToScene(QPoint(int(rect.width() / 2) - 10, int(rect.height() * .20))).toPoint()
            QTest.qWait(100)
            QTest.mouseMove(window, target)
            wait_for(lambda: fix.property("hit").x() >= 32, "Opaque outer head did not win the hit")
            outer_hit = fix.property("hit").toPoint()
            read_corrections = lambda: bridge.picker.get_corrections("b_opaque_outer.png")
            click(window, look_up("outerLayerVisible"))
            QTest.qWait(100)
            QTest.mouseMove(window, target)
            wait_for(lambda: 0 <= fix.property("hit").x() < 32, "Base layer was blocked by opaque outer pixels")
            snapshot(window, "viewport-base-layer.png")
            base_hit = fix.property("hit").toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target)
            wait_for(lambda: len(read_corrections()) == 1, "Could not save the base-layer edit")
            click(window, look_up("baseLayerVisible"))
            click(window, look_up("outerLayerVisible"))
            QTest.qWait(100)
            QTest.mouseMove(window, target)
            wait_for(lambda: fix.property("hit").toPoint() == outer_hit, "Outer-only mode picked the wrong layer")
            snapshot(window, "viewport-outer-layer.png")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target)
            wait_for(lambda: len(read_corrections()) == 2, "Could not save the outer-layer edit")
            corrections = set(read_corrections())
            expected = {
                (base_hit.x(), base_hit.y()), (outer_hit.x(), outer_hit.y()),
            }
            assert corrections == expected, (corrections, expected)
            bridge.closeEditor()
            bridge.openColorSampler("hairColor")
            QTest.qWait(50)
            assert look_up("pixelCanvas").property("visible"), "Color sampler should open the texture"
            click(window, look_up("leavePixels"))
            assert bridge.editorMode == "" and not bridge.samplingColor
            selected = bridge.selectedIndex
            bridge.openEyes()
            QTest.qWait(50)
            click(window, look_up("leaveEyes"))
            assert bridge.editorMode == "" and bridge.selectedIndex == selected
            assert window.property("viewMode") == "Compare" and window.property("comparePosition") == split
            assert original_bytes == {p: p.read_bytes() for p in source.glob("*.png")}
            assert not warnings, warnings
            print("3D Undo and Redo, immediate Undo, Editor Compare, color matching, and viewport controls passed.")
        finally:
            bridge.flush()
            bridge.shutdown()
            window.close()
            engine.deleteLater()
            app.processEvents()


def click(window, item):
    position = item.mapToScene(QPoint(int(item.width() / 2), int(item.height() / 2))).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)


def middle_drag(window, start, offset):
    QTest.mousePress(window, Qt.MiddleButton, Qt.NoModifier, start)
    QTest.mouseMove(window, start + offset, 30)
    QTest.mouseRelease(window, Qt.MiddleButton, Qt.NoModifier, start + offset)


def shade_at_editor(shot, rect, x, y, dpr):
    point = rect.mapToScene(QPoint(x, y))
    return shot.pixelColor(round(point.x() * dpr), round(point.y() * dpr))


def visible_item(window, name):
    items = [window.contentItem()]
    while items:
        item = items.pop()
        if item.objectName() == name and item.isVisible():
            return item
        items.extend(item.childItems())
    return None


def choose_option(window, combo, index):
    steps = index - combo.property("currentIndex")
    click(window, combo)
    popups = window.findChildren(QObject, "studioDropdownList")
    wait_for(lambda: any(p.property("visible") for p in popups), "Dropdown did not open")
    popup = next(p for p in popups if p.property("visible"))
    for _ in range(abs(steps)):
        QTest.keyClick(window, Qt.Key_Down if steps > 0 else Qt.Key_Up)
    QTest.keyClick(window, Qt.Key_Return)
    wait_for(lambda: combo.property("currentIndex") == index and not popup.property("visible"),
             "Dropdown did not select the requested item")


def snapshot(window, name):
    if folder := os.environ.get("DAILY_DRESS_QA_SHOTS"):
        assert window.grabWindow().save(str(Path(folder) / name))


if __name__ == "__main__":
    main()
