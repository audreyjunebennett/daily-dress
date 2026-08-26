from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import colorsys
import json

from PIL import Image

from skin_styler_core import (
    detect_skin_model,
    FaceTemplate,
    _fill_small_torso_hair_gaps,
    _hair_core_palette,
    _trace_surface_hair_paths,
    apply_face_template,
    detect_body_hair_mask,
    generate_folder,
    install_generated_wardrobe,
    make_face_template,
    normalize_skin,
    render_player_3d,
    render_player_view,
    style_skin,
)


def synthetic_skin(hair=(40, 20, 10, 255), eye=(20, 30, 80, 255), size=64):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    pixels = image.load()
    skin = (205, 145, 115, 255)
    for y in range(16):
        for x in range(32):
            pixels[x, y] = hair
    for y in range(8, 16):
        for x in range(8, 16):
            pixels[x, y] = skin
    pixels[10, 11] = eye
    pixels[13, 11] = eye
    pixels[11, 14] = (120, 40, 45, 255)
    pixels[12, 14] = (120, 40, 45, 255)
    for y in range(20, 32):
        for x in range(16, 40):
            pixels[x, y] = (10, 180, 40, 255)
    if size != 64:
        image = image.resize((size, size), Image.Resampling.NEAREST)
    return image


class SkinStylerTests(unittest.TestCase):
    def test_black_hair_receives_target_color_without_flattening_dark_shading(self):
        original = synthetic_skin(hair=(2, 2, 2, 255))
        original.putpixel((9, 1), (14, 14, 14, 255))

        styled, mask, _ = style_skin(original, (155, 70, 205), 42)

        self.assertIn((9, 1), mask)
        self.assertNotEqual(styled.getpixel((9, 1)), original.getpixel((9, 1)))
        self.assertGreater(styled.getpixel((9, 1))[2], styled.getpixel((9, 1))[0])
        self.assertLess(sum(styled.getpixel((8, 1))[:3]), sum(styled.getpixel((9, 1))[:3]))

    def test_manual_category_overrides_can_reclaim_and_ignore_individual_pixels(self):
        original = synthetic_skin(hair=(80, 40, 20, 255))
        outfit = (20, 25)
        hair = (9, 1)
        outfit_before = original.getpixel(outfit)
        hair_before = original.getpixel(hair)

        styled, mask, _ = style_skin(
            original,
            (75, 180, 210),
            42,
            category_overrides={outfit: "hair", hair: "ignore"},
        )

        self.assertIn(outfit, mask)
        self.assertNotIn(hair, mask)
        self.assertNotEqual(styled.getpixel(outfit), outfit_before)
        self.assertEqual(styled.getpixel(hair), hair_before)

    def test_hood_override_can_disable_hair_recolor_for_one_skin(self):
        hooded = synthetic_skin(hair=(65, 35, 80, 255))
        before = hooded.getpixel((9, 1))

        styled, mask, _ = style_skin(hooded, (220, 75, 90), suppress_hair=True)

        self.assertFalse(mask)
        self.assertEqual(styled.getpixel((9, 1)), before)

    def test_skin_model_detection_handles_classic_and_slim_discriminator_strips(self):
        classic = synthetic_skin()
        for left, top, right, bottom in ((54, 20, 55, 31), (46, 52, 47, 63), (50, 16, 51, 19), (42, 48, 43, 51)):
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    classic.putpixel((x, y), (50, 80, 120, 255))
        slim = classic.copy()
        for left, top, right, bottom in ((54, 20, 55, 31), (46, 52, 47, 63), (50, 16, 51, 19), (42, 48, 43, 51)):
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    slim.putpixel((x, y), (0, 0, 0, 0))

        self.assertEqual(detect_skin_model(classic), "classic")
        self.assertEqual(detect_skin_model(slim), "slim")

    def test_recolor_is_confined_to_head_uv(self):
        original = synthetic_skin()
        styled, mask, _ = style_skin(original, (180, 40, 200), 55)
        self.assertTrue(mask)
        self.assertEqual(original.getpixel((20, 25)), styled.getpixel((20, 25)))
        self.assertNotEqual(original.getpixel((9, 1)), styled.getpixel((9, 1)))

    def test_long_front_hair_continues_down_torso_without_touching_outfit_center(self):
        original = synthetic_skin(hair=(200, 56, 40, 255))
        for y in range(20, 28):
            for x in (20, 21, 26, 27):
                original.putpixel((x, y), (216, 88, 40, 255))
        center_before = original.getpixel((23, 25))
        strand_before = original.getpixel((20, 25))

        styled, hair_mask, _ = style_skin(original, (175, 155, 105), 42, include_body_hair=True)

        self.assertIn((20, 25), hair_mask)
        self.assertNotEqual(styled.getpixel((20, 25)), strand_before)
        self.assertEqual(styled.getpixel((23, 25)), center_before)

    def test_front_hair_can_fill_all_three_safe_edge_columns(self):
        original = synthetic_skin(hair=(122, 70, 34, 255))
        strand = (185, 102, 26, 255)
        for y in range(20, 30):
            for x in (20, 21, 22, 25, 26, 27):
                original.putpixel((x, y), strand)

        styled, hair_mask, _ = style_skin(original, (80, 170, 120), 42, include_body_hair=True)

        for coordinate in ((20, 27), (22, 27), (25, 27), (27, 27)):
            self.assertIn(coordinate, hair_mask)
            self.assertNotEqual(styled.getpixel(coordinate), original.getpixel(coordinate))

    def test_noisy_same_hue_shading_survives_the_head_to_torso_handoff(self):
        original = synthetic_skin(hair=(88, 152, 200, 255))
        shades = ((20, 54, 89, 255), (34, 79, 126, 255), (59, 122, 184, 255))
        for y in range(20, 30):
            shade = shades[y % len(shades)]
            for x in (20, 21, 22, 25, 26, 27):
                original.putpixel((x, y), shade)

        styled, hair_mask, _ = style_skin(original, (115, 65, 180), 42, include_body_hair=True)

        for coordinate in ((20, 20), (21, 24), (22, 28), (25, 28), (27, 20)):
            self.assertIn(coordinate, hair_mask)
            self.assertNotEqual(styled.getpixel(coordinate), original.getpixel(coordinate))

    def test_matching_sleeves_prevent_broad_clothing_from_becoming_hair(self):
        original = synthetic_skin(hair=(145, 75, 50, 255))
        clothing = (150, 80, 55, 255)
        for y in range(20, 32):
            for x in range(20, 28):
                original.putpixel((x, y), clothing)
            for x in range(44, 47):
                original.putpixel((x, y), clothing)
        for y in range(52, 64):
            for x in range(36, 39):
                original.putpixel((x, y), clothing)

        styled, hair_mask, _ = style_skin(original, (175, 155, 105), 42, include_body_hair=True)

        self.assertNotIn((20, 25), hair_mask)
        self.assertEqual(styled.getpixel((20, 25)), clothing)

    def test_accessory_color_is_removed_from_long_hair_core_palette(self):
        palette = ((184, 88, 56), (216, 104, 72), (200, 184, 232), (200, 104, 72))

        core = _hair_core_palette(palette)

        self.assertIn((184, 88, 56), core)
        self.assertIn((216, 104, 72), core)
        self.assertNotIn((200, 184, 232), core)

    def test_torso_handoff_rejects_a_similarly_colored_bikini(self):
        original = synthetic_skin(hair=(88, 56, 56, 255))
        hair = (98, 72, 75, 255)
        bikini = (164, 67, 67, 255)
        for y in range(13, 16):
            original.putpixel((40, y), hair)
            original.putpixel((47, y), hair)
        for y in range(20, 23):
            original.putpixel((20, y), hair)
            original.putpixel((27, y), hair)
        for y in range(20, 27):
            original.putpixel((22, y), bikini)
            original.putpixel((25, y), bikini)

        mask = detect_body_hair_mask(original, 42)

        self.assertIn((20, 21), mask)
        self.assertIn((27, 21), mask)
        self.assertNotIn((22, 21), mask)
        self.assertNotIn((25, 21), mask)

    def test_confirmed_long_hair_recovers_matching_shoulder_cap_pixels(self):
        original = synthetic_skin(hair=(174, 86, 56, 255))
        hair = (185, 93, 61, 255)
        for y in range(20, 28):
            original.putpixel((20, y), hair)
            original.putpixel((27, y), hair)
        original.putpixel((44, 16), hair)
        original.putpixel((45, 16), hair)

        mask = detect_body_hair_mask(original, 42)

        self.assertIn((20, 25), mask)
        self.assertIn((44, 16), mask)
        self.assertIn((45, 16), mask)

    def test_exact_skin_shade_reclaims_a_false_positive_shoulder(self):
        hair = (170, 110, 80, 255)
        skin = (205, 145, 115, 255)
        original = synthetic_skin(hair=hair)
        for y in range(20, 29):
            original.putpixel((20, y), hair)
            original.putpixel((27, y), hair)
        for y in range(20, 23):
            for x in range(47, 51):
                original.putpixel((x, y), skin)

        styled, hair_mask, _ = style_skin(original, (70, 175, 120), 42, include_body_hair=True)

        self.assertIn((20, 25), hair_mask)
        self.assertNotIn((48, 21), hair_mask)
        self.assertEqual(styled.getpixel((48, 21)), skin)

    def test_pale_long_hair_does_not_claim_exposed_neck_skin(self):
        hair = (248, 184, 200, 255)
        skin = (255, 223, 204, 255)
        original = synthetic_skin(hair=hair)
        for y in range(8, 16):
            for x in range(8, 16):
                original.putpixel((x, y), skin)
        for y in range(20, 23):
            for x in range(22, 26):
                original.putpixel((x, y), skin)
        for y in range(20, 29):
            original.putpixel((20, y), hair)
            original.putpixel((27, y), hair)

        mask = detect_body_hair_mask(original, 42)

        self.assertIn((20, 25), mask)
        self.assertIn((27, 25), mask)
        self.assertNotIn((22, 20), mask)
        self.assertNotIn((25, 22), mask)

    def test_confirmed_long_hair_links_aligned_base_and_outer_torso_layers(self):
        original = synthetic_skin(hair=(200, 56, 88, 255))
        hair = (204, 72, 104, 255)
        clothing = (20, 150, 80, 255)
        # Continuous base-layer strands establish hair on both the front and
        # back. Their matching outer-layer pixels are intentionally isolated,
        # reproducing a skin where only one of the two torso layers was caught.
        for y in range(20, 30):
            original.putpixel((20, y), hair)
            original.putpixel((32, y), hair)
        for y in range(36, 48):
            original.putpixel((20, y), clothing)
            original.putpixel((32, y), clothing)
        original.putpixel((20, 44), hair)
        original.putpixel((32, 44), hair)

        mask = detect_body_hair_mask(original, 42)

        self.assertIn((20, 28), mask)
        self.assertIn((20, 44), mask)
        self.assertIn((32, 28), mask)
        self.assertIn((32, 44), mask)
        self.assertNotIn((20, 43), mask)
        self.assertNotIn((32, 43), mask)

    def test_tiny_palette_matched_holes_are_filled_without_absorbing_clothing(self):
        original = synthetic_skin(hair=(200, 56, 88, 255))
        hair = (204, 72, 104, 255)
        for coordinate in ((20, 23), (20, 24), (20, 25), (26, 23), (26, 24), (26, 25), (26, 26)):
            original.putpixel(coordinate, hair)
        established = {(20, 23), (20, 25), (26, 23)}

        filled = _fill_small_torso_hair_gaps(
            original,
            established,
            ((200, 56, 88), (204, 72, 104)),
            42,
        )

        self.assertIn((20, 24), filled)
        # This four-pixel block could be a garment detail, so it stays out.
        self.assertNotIn((26, 24), filled)
        self.assertNotIn((26, 25), filled)
        self.assertNotIn((26, 26), filled)

    def test_edge_tracer_stops_when_a_new_palette_region_crosses_a_strong_border(self):
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for y in range(3):
            image.putpixel((1, y), (210, 70, 40, 255))
        for y in range(3, 8):
            image.putpixel((1, y), (105, 35, 30, 255))

        traced = _trace_surface_hair_paths(
            image,
            (0, 0, 3, 8),
            ((210, 70, 40), (105, 35, 30)),
            {1},
            42,
            2,
            2,
        )

        self.assertIn((1, 2), traced)
        self.assertNotIn((1, 3), traced)

    def test_recolor_rotates_hues_without_flattening_palette(self):
        original = synthetic_skin(hair=(210, 70, 100, 255))
        # A same-hue highlight on the outer head layer remains part of the hair
        # palette; genuinely contrasting headbands are now independent controls.
        original.putpixel((40, 8), (235, 95, 130, 255))
        styled, mask, _ = style_skin(original, (100, 70, 220), 85)
        self.assertIn((40, 8), mask)

        def hsv(pixel):
            return colorsys.rgb_to_hsv(*(channel / 255 for channel in pixel[:3]))

        hair_before = hsv(original.getpixel((9, 1)))
        hair_after = hsv(styled.getpixel((9, 1)))
        accent_before = hsv(original.getpixel((40, 8)))
        accent_after = hsv(styled.getpixel((40, 8)))
        before_gap = (accent_before[0] - hair_before[0]) % 1.0
        after_gap = (accent_after[0] - hair_after[0]) % 1.0
        target_hsv = hsv((100, 70, 220, 255))
        self.assertAlmostEqual(before_gap, after_gap, places=2)
        self.assertAlmostEqual(hair_after[1], target_hsv[1], delta=0.03)
        self.assertAlmostEqual(hair_after[2], target_hsv[2], delta=0.03)
        self.assertAlmostEqual(
            accent_before[1] / hair_before[1],
            accent_after[1] / hair_after[1],
            delta=0.04,
        )
        self.assertAlmostEqual(
            accent_before[2] / hair_before[2],
            accent_after[2] / hair_after[2],
            delta=0.04,
        )

    def test_isolated_eye_color_is_not_mistaken_for_hair(self):
        original = synthetic_skin(hair=(40, 20, 10, 255), eye=(40, 20, 10, 255))
        original.putpixel((42, 11), (40, 20, 10, 255))
        _styled, mask, _ = style_skin(original, (100, 70, 220), 55)
        self.assertNotIn((10, 11), mask)
        self.assertNotIn((42, 11), mask)

        # Once connected to hair above, the same pixel is correctly a bang.
        original.putpixel((10, 10), (40, 20, 10, 255))
        original.putpixel((42, 10), (40, 20, 10, 255))
        _styled, mask, _ = style_skin(original, (100, 70, 220), 55)
        self.assertIn((10, 11), mask)
        self.assertIn((42, 11), mask)

    def test_reference_eyes_are_applied(self):
        reference = synthetic_skin(eye=(10, 220, 240, 255))
        target = synthetic_skin(hair=(20, 20, 20, 255), eye=(220, 20, 20, 255))
        template = make_face_template(reference, 55)
        styled, _mask, _ = style_skin(target, (80, 120, 220), 55, template)
        self.assertEqual(styled.getpixel((10, 14)), reference.getpixel((10, 11)))

    def test_reference_eyes_leave_exactly_one_face_row_below(self):
        reference = synthetic_skin(eye=(10, 220, 240, 255))
        target = synthetic_skin(hair=(80, 55, 30, 255), eye=(205, 145, 115, 255))
        for x in (10, 13):
            target.putpixel((x, 13), (30, 40, 90, 255))
            target.putpixel((x, 14), (70, 120, 210, 255))
        template = make_face_template(reference, 55)

        styled, hair_mask, _ = style_skin(target, (180, 150, 100), 55, template)

        self.assertEqual(styled.getpixel((10, 14)), reference.getpixel((10, 11)))
        self.assertEqual(styled.getpixel((10, 15)), target.getpixel((10, 15)))
        self.assertNotIn((10, 14), hair_mask)

    def test_bright_center_bang_is_not_mistaken_for_skin(self):
        original = synthetic_skin(hair=(200, 56, 40, 255))
        original.putpixel((11, 11), (241, 134, 70, 255))
        before = original.getpixel((11, 11))

        styled, hair_mask, _ = style_skin(
            original,
            (190, 170, 105),
            42,
            target_skin_color=(225, 185, 180),
            skin_tolerance=24,
        )

        self.assertIn((11, 11), hair_mask)
        self.assertNotEqual(styled.getpixel((11, 11)), before)

    def test_eye_matching_preserves_mouth_and_hair_over_eyes(self):
        reference = synthetic_skin(eye=(10, 220, 240, 255))
        # A reference bang crossing the eye band must not become part of the eye template.
        for y in range(10, 13):
            reference.putpixel((9, y), (40, 20, 10, 255))
        target = synthetic_skin(hair=(20, 20, 20, 255), eye=(220, 20, 20, 255))
        target_mouth = target.getpixel((11, 14))
        # This destination bang should remain in front of the incoming eye.
        target.putpixel((10, 10), (20, 20, 20, 255))
        target.putpixel((10, 11), (20, 20, 20, 255))
        target.putpixel((42, 10), (20, 20, 20, 255))
        target.putpixel((42, 11), (20, 20, 20, 255))
        target.putpixel((45, 12), (250, 250, 250, 255))

        template = make_face_template(reference, 55)
        styled, hair_mask, _ = style_skin(
            target,
            (80, 120, 220),
            55,
            template,
            eyes_over_bangs=False,
        )

        self.assertNotIn((9, 12), template.features)
        self.assertIn((10, 11), hair_mask)
        self.assertNotEqual(styled.getpixel((10, 11)), reference.getpixel((10, 11)))
        self.assertNotEqual(styled.getpixel((42, 11))[3], 0)
        self.assertEqual(styled.getpixel((45, 12))[3], 0)
        self.assertEqual(styled.getpixel((11, 14)), target_mouth)

    def test_eyes_over_bangs_use_only_the_base_face_layer(self):
        reference = synthetic_skin(eye=(10, 220, 240, 255))
        target = synthetic_skin(hair=(20, 20, 20, 255), eye=(220, 20, 20, 255))
        # The same eye pixel is hidden by hair on both the base face and hat layer.
        target.putpixel((10, 10), (20, 20, 20, 255))
        target.putpixel((10, 11), (20, 20, 20, 255))
        target.putpixel((42, 10), (20, 20, 20, 255))
        target.putpixel((42, 11), (20, 20, 20, 255))
        # Keep one bilateral pair visible so this test isolates layer behavior
        # from the separate per-skin eye-height detector.
        target.putpixel((9, 11), (220, 20, 20, 255))
        target.putpixel((14, 11), (220, 20, 20, 255))
        template = make_face_template(reference, 55)

        styled, _hair_mask, _ = style_skin(
            target,
            (80, 120, 220),
            55,
            template,
            preserve_hat_layer_lashes=False,
        )

        self.assertEqual(styled.getpixel((10, 14)), reference.getpixel((10, 11)))
        self.assertEqual(styled.getpixel((42, 14)), (0, 0, 0, 0))

    def test_hat_layer_lash_shape_uses_the_designed_liner_color(self):
        original = synthetic_skin()
        original.putpixel((40, 12), (25, 20, 22, 255))
        liner = (88, 35, 66, 255)
        template = FaceTemplate(
            features={(8, 12): liner, (10, 12): (30, 130, 180, 255)},
            skin_color=(205, 145, 115),
            anchor_y=14,
        )

        preserved = apply_face_template(
            original,
            original,
            template,
            set(),
            preserve_hat_layer_lashes=True,
        )
        replaced = apply_face_template(
            original,
            original,
            template,
            set(),
            preserve_hat_layer_lashes=False,
        )

        self.assertEqual(preserved.getpixel((40, 12)), liner)
        self.assertEqual(replaced.getpixel((40, 12)), (0, 0, 0, 0))

    def test_thin_player_preview_has_front_and_back_views(self):
        skin = synthetic_skin()
        front = render_player_view(skin, scale=4, back=False, slim=True)
        back = render_player_view(skin, scale=4, back=True, slim=True)

        self.assertEqual(front.size, (56, 128))
        self.assertEqual(back.size, (56, 128))
        self.assertIsNotNone(front.getbbox())
        self.assertIsNotNone(back.getbbox())

    def test_three_quarter_player_preview_renders_a_textured_model(self):
        preview = render_player_3d(synthetic_skin(), scale=4, slim=True)

        self.assertGreater(preview.width, 50)
        self.assertGreater(preview.height, 85)
        self.assertIsNotNone(preview.getbbox())

    def test_three_quarter_player_preview_uses_continuous_yaw(self):
        skin = synthetic_skin()
        at_25 = render_player_3d(skin, scale=5, slim=True, yaw_degrees=25)
        at_35 = render_player_3d(skin, scale=5, slim=True, yaw_degrees=35)

        self.assertNotEqual(at_25.tobytes(), at_35.tobytes())

    def test_three_quarter_preview_projects_outer_layer_as_a_larger_cuboid(self):
        base = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        overlay = base.copy()
        base.putpixel((8, 8), (240, 80, 140, 255))
        overlay.putpixel((40, 8), (240, 80, 140, 255))

        base_preview = render_player_3d(base, scale=8, slim=True, yaw_degrees=25)
        overlay_preview = render_player_3d(overlay, scale=8, slim=True, yaw_degrees=25)
        base_area = sum(pixel[3] > 0 for pixel in base_preview.get_flattened_data())
        overlay_area = sum(pixel[3] > 0 for pixel in overlay_preview.get_flattened_data())

        self.assertGreater(overlay_area, base_area)

    def test_three_quarter_preview_can_hide_every_outer_layer(self):
        base = synthetic_skin()
        with_overlay = base.copy()
        with_overlay.putpixel((40, 8), (250, 30, 160, 255))
        with_overlay.putpixel((20, 36), (30, 220, 180, 255))

        expected = render_player_3d(base, scale=6, slim=True, yaw_degrees=25, show_outer_layers=False)
        hidden = render_player_3d(with_overlay, scale=6, slim=True, yaw_degrees=25, show_outer_layers=False)
        visible = render_player_3d(with_overlay, scale=6, slim=True, yaw_degrees=25, show_outer_layers=True)

        self.assertEqual(hidden.tobytes(), expected.tobytes())
        self.assertNotEqual(visible.tobytes(), hidden.tobytes())

    def test_three_quarter_player_preview_rotates_to_the_back(self):
        skin = synthetic_skin()
        skin.putpixel((25, 10), (245, 30, 120, 255))

        front = render_player_3d(skin, scale=4, slim=True, yaw_degrees=25)
        back = render_player_3d(skin, scale=4, slim=True, yaw_degrees=205)

        self.assertNotEqual(front.tobytes(), back.tobytes())

    def test_hd_input_is_normalized_without_touching_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            hd_path = source / "hd.png"
            synthetic_skin(size=128).save(hd_path)
            before = hd_path.read_bytes()
            result = generate_folder(source, output, (100, 80, 180), standardize_face=False)
            self.assertEqual(result.written, 1)
            self.assertEqual(result.normalized, 1)
            with Image.open(output / "hd.png") as image:
                self.assertEqual(image.size, (64, 64))
            self.assertEqual(hd_path.read_bytes(), before)

    def test_regeneration_removes_skins_deleted_from_the_master_folder(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            keep = source / "keep.png"
            removed = source / "removed.png"
            synthetic_skin().save(keep)
            synthetic_skin(hair=(80, 20, 40, 255)).save(removed)
            generate_folder(source, output, (100, 80, 180), standardize_face=False)
            removed.unlink()

            generate_folder(source, output, (100, 80, 180), standardize_face=False)

            self.assertTrue((output / "keep.png").is_file())
            self.assertFalse((output / "removed.png").exists())

    def test_generation_uses_saved_working_set_and_writes_flat_sync_metadata(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            (source / "nested").mkdir(parents=True)
            synthetic_skin().save(source / "nested" / "favorite.png")
            synthetic_skin(hair=(90, 30, 90, 255)).save(source / "removed.png")
            metadata = {
                "nested/favorite.png": {"status": "favorite", "tag": "casual", "model": "classic"},
                "removed.png": {"status": "remove", "tag": "seasonal"},
            }

            result = generate_folder(
                source,
                output,
                (100, 80, 180),
                standardize_face=False,
                wardrobe_metadata=metadata,
                batch_filter="favorites+casual",
                flatten_output=True,
            )

            self.assertEqual(result.written, 1)
            self.assertTrue((output / "favorite.png").is_file())
            self.assertFalse((output / "nested").exists())
            manifest = json.loads((output / "daily-dress-wardrobe.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["skins"]["favorite.png"]["favorite"])
            self.assertEqual(manifest["skins"]["favorite.png"]["tags"], ["casual"])

    def test_skin_tone_changes_matching_exposed_pixels_only(self):
        original = synthetic_skin()
        # Add a continuous exposed arm matching the face and a green outfit.
        for y in range(20, 32):
            original.putpixel((42, y), (205, 145, 115, 255))
        outfit_before = original.getpixel((20, 25))
        styled, _mask, _ = style_skin(
            original,
            (80, 40, 120),
            55,
            target_skin_color=(120, 75, 55),
            skin_tolerance=28,
        )
        self.assertNotEqual(styled.getpixel((42, 20)), original.getpixel((42, 20)))
        self.assertEqual(styled.getpixel((20, 25)), outfit_before)

    def test_skin_tone_stops_at_a_pale_swimsuit_edge(self):
        original = synthetic_skin()
        face_skin = (255, 227, 209, 255)
        pale_swimsuit = (246, 246, 246, 255)
        for y in range(8, 16):
            for x in range(8, 16):
                original.putpixel((x, y), face_skin)
        original.putpixel((10, 11), (20, 40, 80, 255))
        original.putpixel((13, 11), (20, 40, 80, 255))
        for y in range(20, 32):
            for x in range(20, 28):
                original.putpixel((x, y), pale_swimsuit)
        for y in range(20, 22):
            for x in range(22, 26):
                original.putpixel((x, y), face_skin)
        for y in range(20, 32):
            for x in range(4, 8):
                original.putpixel((x, y), face_skin)
        original.putpixel((20, 36), face_skin)

        styled, _mask, _ = style_skin(
            original,
            (80, 40, 120),
            42,
            target_skin_color=(185, 115, 125),
            skin_tolerance=24,
        )

        self.assertNotEqual(styled.getpixel((23, 20)), original.getpixel((23, 20)))
        self.assertEqual(styled.getpixel((23, 25)), pale_swimsuit)
        self.assertNotEqual(styled.getpixel((5, 25)), original.getpixel((5, 25)))
        self.assertEqual(styled.getpixel((20, 36)), face_skin)

    def test_outfit_palette_colorizes_neutral_fabric_without_touching_skin(self):
        original = synthetic_skin()
        neutral = (238, 238, 238, 255)
        for y in range(22, 32):
            for x in range(20, 28):
                original.putpixel((x, y), neutral)
        face_before = original.getpixel((11, 13))

        styled, _mask, _ = style_skin(
            original,
            (175, 155, 105),
            42,
            target_outfit_color=(65, 105, 210),
        )

        self.assertNotEqual(styled.getpixel((23, 25)), neutral)
        _hue, saturation, _value = colorsys.rgb_to_hsv(
            *(channel / 255 for channel in styled.getpixel((23, 25))[:3])
        )
        self.assertGreater(saturation, 0.35)
        self.assertEqual(styled.getpixel((11, 13)), face_before)

    def test_hair_accessory_palette_is_independent_from_hair(self):
        original = synthetic_skin(hair=(105, 55, 30, 255))
        accessory = (35, 95, 220, 255)
        for y in range(2, 5):
            for x in range(40, 43):
                original.putpixel((x, y), accessory)

        preserved, _mask, _ = style_skin(original, (205, 170, 95), 42)
        styled, _mask, _ = style_skin(
            original,
            (205, 170, 95),
            42,
            target_accessory_color=(80, 190, 95),
        )

        self.assertEqual(preserved.getpixel((41, 3)), accessory)
        self.assertNotEqual(styled.getpixel((41, 3)), accessory)
        self.assertNotEqual(styled.getpixel((9, 1)), original.getpixel((9, 1)))

    def test_long_hair_flower_is_traced_beside_body_hair(self):
        original = synthetic_skin(hair=(145, 70, 35, 255))
        for y in range(20, 29):
            for x in (20, 21):
                original.putpixel((x, y), (150, 75, 38, 255))
        flower = (50, 105, 225, 255)
        original.putpixel((22, 23), flower)
        original.putpixel((22, 24), flower)

        styled, _mask, _ = style_skin(
            original,
            (190, 155, 95),
            42,
            include_body_hair=True,
            target_accessory_color=(190, 70, 155),
        )

        self.assertNotEqual(styled.getpixel((22, 23)), flower)
        self.assertNotEqual(styled.getpixel((20, 23)), original.getpixel((20, 23)))

    def test_large_floral_clothing_panel_beside_long_hair_is_not_an_accessory(self):
        original = synthetic_skin(hair=(145, 70, 35, 255))
        for y in range(20, 30):
            for x in (20, 21):
                original.putpixel((x, y), (150, 75, 38, 255))
        floral_clothing = (50, 105, 225, 255)
        for y in range(22, 28):
            for x in (22, 23, 24):
                original.putpixel((x, y), floral_clothing)

        styled, _mask, _ = style_skin(
            original,
            (190, 155, 95),
            42,
            include_body_hair=True,
            target_accessory_color=(190, 70, 155),
        )

        self.assertEqual(styled.getpixel((23, 24)), floral_clothing)

    def test_pastel_back_hair_does_not_absorb_cross_hue_pastel_clothing(self):
        hair = (248, 200, 205, 255)
        clothing = (190, 225, 218, 255)
        original = synthetic_skin(hair=hair)
        for y in range(20, 30):
            original.putpixel((32, y), (235, 180, 198, 255))
            original.putpixel((33, y), (235, 180, 198, 255))
            for x in range(34, 40):
                original.putpixel((x, y), clothing)

        styled, hair_mask, _ = style_skin(original, (135, 75, 185), 42, include_body_hair=True)

        self.assertIn((32, 25), hair_mask)
        self.assertNotEqual(styled.getpixel((32, 25)), original.getpixel((32, 25)))
        self.assertNotIn((36, 25), hair_mask)
        self.assertEqual(styled.getpixel((36, 25)), clothing)

    def test_skin_tone_reaches_forehead_pixels_between_bangs(self):
        original = synthetic_skin(hair=(190, 120, 100, 255))
        forehead_before = original.getpixel((11, 9))
        styled, hair_mask, _ = style_skin(
            original,
            (100, 70, 220),
            85,
            target_skin_color=(225, 185, 180),
            skin_tolerance=28,
        )
        self.assertNotEqual(styled.getpixel((11, 9)), forehead_before)
        self.assertNotIn((11, 9), hair_mask)

    def test_install_replaces_live_wardrobe_and_backs_up_previous_skins(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "styled"
            target = root / "config" / "daily-dress" / "wardrobe" / "shared"
            generated.mkdir()
            target.mkdir(parents=True)
            synthetic_skin(hair=(90, 30, 120, 255)).save(generated / "new.png")
            synthetic_skin(hair=(20, 20, 20, 255)).save(target / "old.png")

            result = install_generated_wardrobe(generated, target)

            self.assertEqual(result.installed, 1)
            self.assertTrue((target / "new.png").is_file())
            self.assertFalse((target / "old.png").exists())
            self.assertIsNotNone(result.backup)
            self.assertTrue((result.backup / "old.png").is_file())
            self.assertTrue((target / "DAILY DRESS SYNC OUTBOX.txt").is_file())


if __name__ == "__main__":
    unittest.main()
