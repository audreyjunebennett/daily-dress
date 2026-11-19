"""Regressions for the QML adapter's unchanged pixel-processing behavior."""
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from skin_styler_core import make_face_template, style_skin
from studio_preview import DEFAULT_STYLE, PreviewRenderer, PreviewRequest, clean_style, styled_texture
from test_skin_styler import synthetic_skin


class PreviewTests(unittest.TestCase):
    def test_all_disabled_preserves_original_pixels(self):
        original = synthetic_skin()
        result = styled_texture(original, None, dict(DEFAULT_STYLE), {}, {})
        self.assertEqual(original.tobytes(), result.tobytes())
        self.assertIsNot(original, result)

    def test_hair_uses_existing_backend_exactly(self):
        original = synthetic_skin()
        options = {**DEFAULT_STYLE, "hairEnabled": True, "hairColor": "#7D42B4"}
        actual = styled_texture(original, None, options, {}, {})
        expected, _, _ = style_skin(original, (125, 66, 180), adaptive_detection=True)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertNotEqual(actual.getpixel((9, 1)), original.getpixel((9, 1)))

    def test_eyes_can_transfer_without_recoloring_hair(self):
        original = synthetic_skin(eye=(10, 180, 50, 255))
        reference = synthetic_skin(eye=(80, 30, 220, 255))
        options = {**DEFAULT_STYLE, "eyesEnabled": True}
        result = styled_texture(original, reference, options, {}, {})
        expected, mask, _ = style_skin(original, None, face_template=make_face_template(reference), adaptive_detection=True)
        self.assertTrue(mask)  # hair protection survives disabling recoloring
        self.assertEqual(result.tobytes(), expected.tobytes())
        self.assertEqual(result.getpixel((9, 1)), original.getpixel((9, 1)))
        self.assertNotEqual(result.getpixel((10, 11)), original.getpixel((10, 11)))

    def test_skin_tone_does_not_enable_hair_or_change_outfit(self):
        original = synthetic_skin()
        options = {**DEFAULT_STYLE, "skinEnabled": True, "skinMode": "custom", "skinColor": "#B07862"}
        result = styled_texture(original, None, options, {}, {})
        self.assertEqual(result.getpixel((9, 1)), original.getpixel((9, 1)))
        self.assertEqual(result.getpixel((20, 25)), original.getpixel((20, 25)))
        self.assertNotEqual(result.getpixel((11, 15)), original.getpixel((11, 15)))

    def test_corrections_and_no_visible_hair_override_are_respected(self):
        original = synthetic_skin()
        options = {**DEFAULT_STYLE, "hairEnabled": True, "hairColor": "#7D42B4"}
        result = styled_texture(original, None, options, {}, {(20, 25): "hair"})
        self.assertNotEqual(result.getpixel((20, 25)), original.getpixel((20, 25)))
        result = styled_texture(original, None, options, {"hair_mode": "none"}, {})
        self.assertEqual(result.tobytes(), original.tobytes())

    def test_rotating_reuses_texture_but_source_changes_invalidate_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "skin.png"
            synthetic_skin().save(path)
            renderer = PreviewRenderer()
            def request(yaw):
                return PreviewRequest(1, path, None, dict(DEFAULT_STYLE), {}, {}, yaw)
            with patch("studio_preview.styled_texture", wraps=styled_texture) as style:
                renderer.textures(request(25))
                renderer.textures(request(90))
                self.assertEqual(style.call_count, 1)
                stamp = path.stat().st_mtime_ns
                Image.new("RGBA", (64, 64), "blue").save(path)
                os.utime(path, ns=(stamp, stamp + 2_000_000_000))
                renderer.textures(request(90))
                self.assertEqual(style.call_count, 2)

    def test_outfit_and_accessory_use_independent_corrected_masks(self):
        original = synthetic_skin()
        outfit = [(20, 23), (21, 23)]
        accessory = (22, 23)
        original.putpixel(outfit[1], (20, 90, 40, 180))
        original.putpixel(accessory, (160, 60, 180, 255))
        options = {**DEFAULT_STYLE, "outfitEnabled": True, "outfitColor": "#CB68B4"}
        corrections = {**dict.fromkeys(outfit, "outfit"), accessory: "accessory"}
        outfit_only = styled_texture(original, None, options, {}, corrections)
        both = styled_texture(original, None, {**options, "accessoryEnabled": True, "accessoryColor": "#D4B32B"}, {}, corrections)
        self.assertNotEqual(outfit_only.getpixel(outfit[0]), original.getpixel(outfit[0]))
        self.assertNotEqual(outfit_only.getpixel(outfit[0])[:3], outfit_only.getpixel(outfit[1])[:3])
        self.assertEqual(both.getpixel(outfit[1])[3], 180)
        self.assertEqual(both.getpixel(outfit[0]), outfit_only.getpixel(outfit[0]))
        self.assertEqual(outfit_only.getpixel(accessory), original.getpixel(accessory))
        self.assertNotEqual(both.getpixel(accessory), original.getpixel(accessory))
        self.assertEqual(both.getpixel((9, 1)), original.getpixel((9, 1)))
        self.assertEqual(both.getpixel((8, 15)), original.getpixel((8, 15)))

    def test_invalid_saved_options_have_safe_defaults(self):
        result = clean_style({"hairEnabled": "false", "hairColor": "invalid", "skinColor": "#abc"})
        self.assertFalse(result["hairEnabled"])
        self.assertEqual(result["hairColor"], DEFAULT_STYLE["hairColor"])
        self.assertEqual(result["skinColor"], "#AABBCC")

    def test_disabled_eyes_do_not_require_missing_reference_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "skin.png"
            synthetic_skin().save(source)
            request = PreviewRequest(1, source, source.with_name("missing.png"), dict(DEFAULT_STYLE), {}, {}, 25)
            original, styled, _ = PreviewRenderer().textures(request)
            self.assertEqual(original.tobytes(), styled.tobytes())

    def test_reference_matching_samples_face_not_hair_or_default_preset(self):
        original = synthetic_skin()
        reference = synthetic_skin(hair=(217, 178, 176, 255))
        for y in range(8, 16):
            for x in range(8, 16):
                reference.putpixel((x, y), (255, 246, 238, 255))
        options = {**DEFAULT_STYLE, "skinEnabled": True}
        with patch("studio_preview.style_skin", wraps=style_skin) as style:
            result = styled_texture(original, reference, options, {}, {})
            self.assertEqual(style.call_args.kwargs["target_skin_color"], (255, 246, 238))
        self.assertNotEqual(result.getpixel((11, 15)), original.getpixel((11, 15)))
        self.assertEqual(result.getpixel((20, 25)), original.getpixel((20, 25)))
        self.assertEqual(result.getpixel((9, 1)), original.getpixel((9, 1)))

    def test_matching_reference_to_itself_preserves_all_original_shading(self):
        reference = synthetic_skin()
        reference.putpixel((9, 15), (195, 130, 100, 255))
        reference.putpixel((14, 15), (218, 165, 140, 255))
        result = styled_texture(reference, reference.copy(), {**DEFAULT_STYLE, "skinEnabled": True}, {}, {})
        self.assertEqual(reference.tobytes(), result.tobytes())

    def test_skin_only_reference_mode_loads_reference_without_eye_transfer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "skin.png"
            reference = Path(temporary) / "reference.png"
            original = synthetic_skin()
            original.save(path)
            other = synthetic_skin()
            for x in range(9, 15):
                other.putpixel((x, 15), (240, 210, 195, 255))
            other.save(reference)
            options = {**DEFAULT_STYLE, "skinEnabled": True}
            request = PreviewRequest(1, path, reference, options, {}, {}, 25)
            before, after, _ = PreviewRenderer().textures(request)
            self.assertNotEqual(before.getpixel((11, 15)), after.getpixel((11, 15)))

    def test_old_custom_color_is_preserved_but_preset_migrates_to_reference(self):
        self.assertEqual(clean_style({"skinColor": "#B07862"})["skinMode"], "custom")
        self.assertEqual(clean_style({"skinColor": "#E8BAA2"})["skinMode"], "reference")


if __name__ == "__main__":
    unittest.main()
