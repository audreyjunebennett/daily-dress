import unittest

from skin_styler_gui import (
    hair_color_from_hue,
    hair_color_from_targets,
    hair_targets_from_color,
    hue_from_color,
)


class GuiHelperTests(unittest.TestCase):
    def test_hair_slider_color_round_trips_its_hue(self):
        for expected in (0, 42, 172, 245, 319):
            red, green, blue = hair_color_from_hue(expected)
            actual = hue_from_color(f"#{red:02X}{green:02X}{blue:02X}")
            distance = abs((actual - expected + 180) % 360 - 180)
            self.assertLess(distance, 1.0)

    def test_hair_target_color_keeps_requested_saturation_and_lightness(self):
        red, green, blue = hair_color_from_targets(37, 28, 91)
        hue, saturation, lightness = hair_targets_from_color(f"#{red:02X}{green:02X}{blue:02X}")
        self.assertLess(abs((hue - 37 + 180) % 360 - 180), 1.0)
        self.assertAlmostEqual(saturation, 28, delta=1.0)
        self.assertAlmostEqual(lightness, 91, delta=1.0)


if __name__ == "__main__":
    unittest.main()
