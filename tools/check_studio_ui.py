"""Render real-data studio QA frames without touching the user's studio state."""
import os
if os.environ.get("DAILY_DRESS_REQUIRE_OFFSTAGE") and not os.environ.get("OFFSTAGE_DESKTOP"):
    raise RuntimeError("Refusing to run graphical QA outside an Offstage desktop")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import argparse
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from daily_dress_qml import SkinImages, StudioBridge, initialize_viewport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path.home() / "Pictures" / "Skins")
    parser.add_argument("--webgl", action="store_true", help="Capture the local WebGL renderer on Offstage")
    args = parser.parse_args()
    if args.webgl and not os.environ.get("OFFSTAGE_DESKTOP"):
        parser.error("--webgl requires Offstage")
    viewport_path = initialize_viewport() if args.webgl else None
    if args.webgl and viewport_path is None:
        parser.error("Build the local viewport first")
    app = QApplication([])
    for font in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf", "seguisym.ttf"):
        path = Path("C:/Windows/Fonts") / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    out = Path(__file__).resolve().parents[1] / "dev-workspace" / "styler-qa"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        bridge = StudioBridge(args.source, Path(temporary), viewport_path)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
        engine.addImageProvider("skins", SkinImages(bridge))
        engine.rootContext().setContextProperty("studio", bridge)
        engine.load(str(Path(__file__).with_name("qml") / "DailyDressStudio.qml"))
        if not engine.rootObjects():
            raise RuntimeError(warnings)
        window = engine.rootObjects()[0]
        if args.webgl:
            wait_viewport(window, "gpuPreview")
        bridge.selectVisible(min(20, len(bridge.visible_indexes) - 1))
        window.resize(980, 680)
        QTest.qWait(250)
        window.grabWindow().save(str(out / "studio-choose-reference.png"))
        reference_button = window.findChild(QObject, "useStyleReference")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                         reference_button.mapToScene(QPoint(45, 11)).toPoint())
        if not (bridge.hasReference and bridge.options["hairEnabled"] and bridge.options["skinEnabled"]):
            raise RuntimeError("The default hair and skin modes did not follow the reference")
        if bridge.options["outfitEnabled"]:
            raise RuntimeError("Choosing a reference enabled outfit recoloring")
        QTest.mouseMove(window, QPoint(125, 400))
        for _ in range(100):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        window.grabWindow().save(str(out / "studio-reference-applied.png"))
        pick = window.findChild(QObject, "pickMaterialColor")
        QTest.mouseMove(window, pick.mapToScene(QPoint(20, 10)).toPoint())
        QTest.qWait(600)
        window.grabWindow().save(str(out / "studio-soft-tooltip.png"))
        category = window.findChild(QObject, "outfitCategory")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, category.mapToScene(QPoint(18, 12)).toPoint())
        QTest.qWait(200)
        window.grabWindow().save(str(out / "studio-soft-dropdown.png"))
        QTest.keyClick(window, Qt.Key_Escape)
        window.resize(1440, 900)
        bridge.selectVisible(min(21, len(bridge.visible_indexes) - 1))
        bridge.setColor("hairColor", "#995AC1")
        for _ in range(250):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        if bridge.previewError or bridge.previewBusy:
            raise RuntimeError(bridge.previewError or "Preview timed out")
        QTest.qWait(300)
        window.grabWindow().save(str(out / "studio-hair.png"))
        window.setProperty("viewMode", "Compare")
        window.setProperty("activeMaterial", "eyes")
        QTest.qWait(250)
        window.grabWindow().save(str(out / "studio-compare.png"))
        window.resize(980, 680)
        QTest.qWait(250)
        window.grabWindow().save(str(out / "studio-styling-small.png"))
        window.resize(1440, 900)
        window.setProperty("viewMode", "Styled")
        window.setProperty("activeMaterial", "hair")
        QTest.qWait(250)
        QTest.qWait(250)
        window.grabWindow().save(str(out / "studio-hair-controls.png"))
        beach = next((i for i, entry in enumerate(bridge.visible_indexes)
                      if bridge.all_skins[entry].relative == "beach-babe-on-planetminecraft-com.png"), None)
        if beach is not None:
            bridge.selectVisible(beach)
            bridge.setReference()
            bridge.setStyleToggle("skinEnabled", True)
            window.setProperty("viewMode", "Compare")
            window.setProperty("activeMaterial", "skin")
            for _ in range(250):
                QTest.qWait(20)
                if not bridge.previewBusy and not bridge._preview_timer.isActive():
                    break
            QTest.qWait(250)
            QTest.qWait(100)
            window.grabWindow().save(str(out / "studio-skin-reference.png"))
        braid = next((i for i, entry in enumerate(bridge.visible_indexes)
                      if "aphrodite--goddess-of-beauty" in bridge.all_skins[entry].relative), None)
        if braid is not None:
            bridge.selectVisible(braid)
            bridge.setStyleToggle("skinEnabled", False)
            bridge.setColor("hairColor", "#C69EB4")
            bridge.rotate(155)
            if args.webgl:
                for _ in range(120):
                    QTest.qWait(25)
                    if not bridge.previewBusy and not bridge._preview_timer.isActive():
                        break
                window.setProperty("viewMode", "Compare")
                QTest.qWait(150)
                window.grabWindow().save(str(out / "aphrodite-compare-webgl.png"))
            bridge.openPixels()
            bridge.paintPixel(12, 23, "hair", False)
            bridge.endPixelStroke()
            QTest.qWait(450)
            if args.webgl:
                wait_viewport(window, "fixViewport")
                web = window.findChild(QObject, "editWebViewport")
                QTest.mouseMove(window, web.mapToScene(QPoint(int(web.width() * .5), int(web.height() * .64))).toPoint())
                QTest.qWait(150)
                window.grabWindow().save(str(out / "aphrodite-fix-3d.png"))
                button = window.findChild(QObject, "fixPixels3D")
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                                 button.mapToScene(QPoint(30, 12)).toPoint())
                QTest.qWait(150)
            window.grabWindow().save(str(out / "aphrodite-fix-pixels.png"))
            bridge.closeEditor()
            bridge.setEyeSource("selected")
            bridge.openEyes()
            bridge.setColor("irisColor", "#A589BA")
            QTest.qWait(450)
            window.grabWindow().save(str(out / "aphrodite-design-eyes.png"))
            bridge.closeEditor()
        window.setProperty("activeMaterial", "outfit")
        bridge.openColorSampler("outfitColor")
        QTest.qWait(250)
        window.grabWindow().save(str(out / "studio-pick-outfit-color.png"))
        bridge.closeEditor()
        window.resize(980, 680)
        browse_skin = bridge.current_skin()
        bridge.toggleReview()
        for decision in ("favorite", "keep", "maybe", "remove"):
            bridge.setStatus(decision)
        for _ in range(100):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        window.grabWindow().save(str(out / "studio-review-unsorted.png"))
        bridge.toggleReview()
        for _ in range(100):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        if bridge.current_skin() != browse_skin:
            raise RuntimeError("Review did not restore the prior browse selection")
        window.grabWindow().save(str(out / "studio-browse-sorting.png"))
        bridge.setColor("outfitColor", "#487E8F")
        bridge.setColor("accessoryColor", "#D68EAA")
        duplicate = window.findChild(QObject, "duplicateLook")
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                         duplicate.mapToScene(QPoint(28, 12)).toPoint())
        assert bridge.current_skin().path == browse_skin.path and bridge.current_skin() != browse_skin
        assert bridge.options["outfitColor"] == "#487E8F"
        bridge.setStyleToggle("accessoryEnabled", False)
        bridge.setColor("outfitColor", "#BA786A")
        window.setProperty("activeMaterial", "outfit")
        window.setProperty("viewMode", "Compare")
        window.resize(1440, 900)
        for _ in range(100):
            QTest.qWait(20)
            if not bridge.previewBusy and not bridge._preview_timer.isActive():
                break
        QTest.qWait(300)
        window.grabWindow().save(str(out / "studio-duplicate-look.png"))
        bridge.flush()
        bridge.shutdown()
        window.close()
        if warnings:
            raise RuntimeError("\n".join(warnings))
        print(f"Rendered {len(bridge.all_skins)} wardrobe entries including the test look; QA frames: {out}")


def wait_viewport(window, name):
    view = window.findChild(QObject, name)
    for _ in range(160):
        QTest.qWait(25)
        if view.property("ready"):
            return
    raise RuntimeError(f"{name} did not render")


if __name__ == "__main__":
    main()
