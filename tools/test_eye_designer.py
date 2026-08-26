from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import colorsys

from PIL import Image

from eye_designer import (
    EyeDesigner,
    classify_reference_eye_features,
    edit_eye_feature,
    iris_color_from_targets,
    mirrored_eye_coordinate,
    preset_eye_features,
    retarget_eye_pixel,
    write_eye_reference,
)
from skin_styler_core import make_face_template


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class EyeDesignerTests(unittest.TestCase):
    def test_pixel_editor_redefines_and_erases_eye_materials(self):
        features = {(8, 13): (30, 20, 25, 255), (10, 14): (40, 180, 160, 255)}
        iris = {(10, 14)}
        liner = {(8, 13)}
        white: set[tuple[int, int]] = set()
        representatives = {
            "iris": (40, 180, 160),
            "liner": (30, 20, 25),
            "white": (244, 247, 246),
        }

        self.assertTrue(edit_eye_feature(features, iris, liner, white, (10, 14), "white", representatives))
        self.assertNotIn((10, 14), iris)
        self.assertIn((10, 14), white)
        self.assertEqual(features[(10, 14)], (244, 247, 246, 255))

        self.assertTrue(edit_eye_feature(features, iris, liner, white, (8, 13), "eraser", representatives))
        self.assertNotIn((8, 13), features)
        self.assertNotIn((8, 13), liner)

    def test_pixel_editor_mirror_maps_between_eye_canvases(self):
        self.assertEqual(mirrored_eye_coordinate((8, 13)), (15, 13))
        self.assertEqual(mirrored_eye_coordinate((10, 14)), (13, 14))

    def test_eye_editor_undo_restores_a_deep_pixel_state(self):
        designer = object.__new__(EyeDesigner)
        designer.features = {(10, 14): (40, 180, 160, 255)}
        designer.reference_source_features = dict(designer.features)
        designer.reference_iris_coordinates = {(10, 14)}
        designer.reference_liner_coordinates = set()
        designer.reference_white_coordinates = set()
        designer.reference_shape = True
        designer.reference_iris_color = (40, 180, 160)
        designer.reference_liner_color = (30, 20, 25)
        designer.reference_white_color = (244, 247, 246)
        designer.hue_var = DummyVar(193.0)
        designer.saturation_var = DummyVar(68.0)
        designer.lightness_var = DummyVar(58.0)
        designer.iris_var = DummyVar("#289FB3")
        designer.lash_var = DummyVar("#1E1419")
        designer.white_var = DummyVar("#F4F7F6")
        designer.hue_text_var = DummyVar("193°")
        designer.saturation_text_var = DummyVar("68%")
        designer.lightness_text_var = DummyVar("58%")
        designer.active_stroke_snapshot = None
        designer.active_stroke_changed = False
        designer.redo_stack = []
        designer.paint_help_var = SimpleNamespace(set=lambda _message: None)
        designer._redraw = lambda: None
        original = designer._capture_edit_state()
        designer.undo_stack = [original]
        designer.features.clear()
        designer.reference_source_features.clear()
        designer.reference_iris_coordinates.clear()
        designer.hue_var.set(315.0)

        self.assertEqual(designer._undo(), "break")
        self.assertEqual(designer.features, {(10, 14): (40, 180, 160, 255)})
        self.assertEqual(designer.reference_iris_coordinates, {(10, 14)})
        self.assertEqual(designer.hue_var.get(), 193.0)
        self.assertFalse(designer.undo_stack)
        self.assertEqual(len(designer.redo_stack), 1)

        self.assertEqual(designer._redo(), "break")
        self.assertFalse(designer.features)
        self.assertFalse(designer.reference_iris_coordinates)
        self.assertEqual(designer.hue_var.get(), 315.0)
        self.assertFalse(designer.redo_stack)
        self.assertEqual(len(designer.undo_stack), 1)

    def test_reference_eye_shape_is_classified_without_changing_its_coordinates(self):
        features = {
            (8, 12): (35, 20, 30, 255),
            (9, 12): (220, 225, 225, 255),
            (10, 12): (28, 90, 120, 255),
            (10, 13): (55, 175, 205, 255),
        }
        iris, liner, white, _iris_color, _liner_color, _white_color = classify_reference_eye_features(features)

        self.assertEqual(iris | liner | white, set(features))
        self.assertEqual(liner, {(8, 12)})
        self.assertEqual(white, {(9, 12)})
        self.assertEqual(iris, {(10, 12), (10, 13)})

    def test_reference_iris_retarget_preserves_shadow_difference(self):
        source = (55, 175, 205)
        upper = retarget_eye_pixel((28, 90, 120, 255), source, (180, 90, 205))
        lower = retarget_eye_pixel((55, 175, 205, 255), source, (180, 90, 205))
        _upper_hue, _upper_sat, upper_value = colorsys.rgb_to_hsv(*(channel / 255 for channel in upper[:3]))
        _lower_hue, _lower_sat, lower_value = colorsys.rgb_to_hsv(*(channel / 255 for channel in lower[:3]))

        self.assertLess(upper_value, lower_value)

    def test_iris_targets_control_hue_saturation_and_lightness(self):
        red, green, blue = iris_color_from_targets(210, 42, 73)
        hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)

        self.assertAlmostEqual(hue * 360, 210, delta=1)
        self.assertAlmostEqual(saturation * 100, 42, delta=1)
        self.assertAlmostEqual(lightness * 100, 73, delta=1)

    def test_desaturating_an_iris_moves_it_toward_gray_at_fixed_lightness(self):
        colorful = iris_color_from_targets(210, 100, 50)
        neutral = iris_color_from_targets(210, 0, 50)

        self.assertNotEqual(colorful[0], colorful[2])
        self.assertEqual(neutral[0], neutral[1])
        self.assertEqual(neutral[1], neutral[2])

    def test_shaded_default_uses_stable_lower_rows_and_two_tones_per_material(self):
        features = preset_eye_features("Shaded eyes", (40, 180, 160), (30, 20, 25), (244, 247, 246))

        self.assertEqual(set(features), {
            (9, 13), (10, 13), (13, 13), (14, 13),
            (9, 14), (10, 14), (13, 14), (14, 14),
        })
        self.assertNotEqual(features[(9, 13)], features[(9, 14)])
        self.assertNotEqual(features[(10, 13)], features[(10, 14)])
        self.assertEqual(features[(9, 13)], features[(14, 13)])
        self.assertEqual(features[(10, 14)], features[(13, 14)])
        upper_hue, _upper_saturation, upper_value = colorsys.rgb_to_hsv(
            *(channel / 255 for channel in features[(10, 13)][:3])
        )
        lower_hue, _lower_saturation, lower_value = colorsys.rgb_to_hsv(
            *(channel / 255 for channel in features[(10, 14)][:3])
        )
        self.assertAlmostEqual(upper_hue, lower_hue, places=2)
        self.assertLess(upper_value, lower_value)

    def test_outer_lash_columns_are_editable_but_nose_gap_is_not(self):
        self.assertTrue(EyeDesigner._editable(8, 13))
        self.assertTrue(EyeDesigner._editable(15, 13))
        self.assertFalse(EyeDesigner._editable(11, 13))
        self.assertFalse(EyeDesigner._editable(12, 13))
        lashes = preset_eye_features("Soft lashes", (40, 180, 160), (30, 20, 25), (244, 247, 246))
        self.assertIn((8, 13), lashes)
        self.assertIn((15, 13), lashes)

    def test_saved_design_round_trips_as_an_eye_template(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "custom-eye-reference.png"
            features = {
                (10, 11): (30, 40, 50, 255),
                (13, 11): (30, 40, 50, 255),
                (10, 12): (40, 180, 160, 255),
                (13, 12): (40, 180, 160, 255),
            }
            write_eye_reference(output, features, (205, 145, 115))

            with Image.open(output) as image:
                template = make_face_template(image)

            expected = {
                (10, 13): (30, 40, 50, 255),
                (13, 13): (30, 40, 50, 255),
                (10, 14): (40, 180, 160, 255),
                (13, 14): (40, 180, 160, 255),
            }
            self.assertEqual(template.features, expected)
            self.assertNotIn((11, 14), template.features)


if __name__ == "__main__":
    unittest.main()
