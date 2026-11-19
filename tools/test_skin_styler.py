from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import colorsys
import json

from PIL import Image, ImageDraw

from skin_styler_core import (
    apply_category_overrides,
    detect_skin_model,
    FaceTemplate,
    _fill_small_torso_hair_gaps,
    _hair_core_palette,
    _trace_surface_hair_paths,
    apply_face_template,
    classify_skin_categories,
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
    def test_hair_recolor_preserves_brown_to_blue_highlight_gradient(self):
        source = synthetic_skin()
        for x in range(32):
            for y in range(16):
                # Smooth brown gradient, with two-tone head layers alike.
                value = 38 + round(170 * (y / 15))
                source.putpixel((x, y), (value, round(value * .68), round(value * .48), 255))
                source.putpixel((x + 32, y), (value, round(value * .68), round(value * .48), 255))
        mask = {(x, y) for x in range(64) for y in range(16)
                if not (8 <= x % 32 < 16 and 8 <= y < 16)}
        styled, _, _ = style_skin(source, (95, 165, 235), category_overrides=dict.fromkeys(mask, "hair"))
        levels = [max(styled.getpixel((x, y))[:3]) for x, y in ((2, 1), (2, 4), (2, 8), (2, 12), (2, 15))]
        self.assertEqual(levels, sorted(levels), levels)
        self.assertGreater(levels[-1] - levels[0], 65)

    def test_black_hair_receives_target_color_without_flattening_dark_shading(self):
        original = synthetic_skin(hair=(2, 2, 2, 255))
        original.putpixel((9, 1), (14, 14, 14, 255))

        styled, mask, _ = style_skin(original, (155, 70, 205), 42)

        self.assertIn((9, 1), mask)
        self.assertNotEqual(styled.getpixel((9, 1)), original.getpixel((9, 1)))
        self.assertGreater(styled.getpixel((9, 1))[2], styled.getpixel((9, 1))[0])
        self.assertLess(sum(styled.getpixel((8, 1))[:3]), sum(styled.getpixel((9, 1))[:3]))

    def test_pale_side_decoration_does_not_disable_dark_hair_recolor(self):
        dark = (24, 24, 24, 255)
        source = synthetic_skin(hair=dark)
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 8, 7, 15), fill=(236, 192, 201, 255))
        draw.rectangle((8, 0, 15, 7), fill=(236, 192, 201, 255))
        styled, mask, _ = style_skin(source, (180, 120, 220))
        self.assertIn((27, 11), mask)
        self.assertNotEqual(styled.getpixel((27, 11)), dark)

    def test_split_dye_keeps_dark_bangs_and_long_strands_with_eye_styling(self):
        dark = (24, 24, 24, 255)
        light = (236, 192, 201, 255)
        source = synthetic_skin(hair=dark)
        draw = ImageDraw.Draw(source)
        for box in ((12, 0, 23, 7), (16, 8, 23, 15), (28, 8, 31, 15)):
            draw.rectangle(box, fill=light)
        draw.rectangle((8, 11, 10, 13), fill=dark)
        draw.rectangle((40, 11, 41, 13), fill=dark)
        draw.line((20, 20, 20, 30), fill=dark)
        draw.line((27, 20, 27, 30), fill=light)

        liner = (129, 78, 99, 255)
        iris = (103, 134, 171, 255)
        eyes = FaceTemplate({(8, 12): liner, (9, 12): iris, (14, 12): iris}, (205, 145, 115))
        dark_points = {(8, 1), (8, 12), (9, 12), (40, 12), (41, 13), (20, 25)}
        light_points = {(18, 2), (27, 25)}
        corrections = dict.fromkeys(dark_points | light_points, "hair")
        for hair_color in (None, (233, 216, 198)):
            with self.subTest(hair_color=hair_color):
                styled, mask, _ = style_skin(source, hair_color, face_template=eyes,
                                             category_overrides=corrections)
                for point in dark_points:
                    self.assertIn(point, mask)
                    self.assertEqual(styled.getpixel(point), dark)
                for point in light_points:
                    self.assertEqual(styled.getpixel(point) != light, hair_color is not None)
                self.assertEqual(styled.getpixel((14, 12)), iris)

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

    def test_skin_model_detection_recognizes_black_padding_with_painted_arm_boundaries(self):
        skin = Image.new("RGBA", (64, 64), (212, 162, 118, 255))
        draw = ImageDraw.Draw(skin)
        strips = ((54, 20, 55, 31), (46, 52, 47, 63), (50, 16, 51, 19), (42, 48, 43, 51))
        for box in strips:
            draw.rectangle(box, fill=(0, 0, 0, 255))
        self.assertEqual(detect_skin_model(skin), "slim")
        # A painted fourth column or an entirely black sleeve is real geometry.
        draw.line((54, 20, 54, 31), fill=(27, 55, 100, 255))
        self.assertEqual(detect_skin_model(skin), "classic")
        self.assertEqual(detect_skin_model(Image.new("RGBA", (64, 64), "black")), "classic")

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

    def test_back_braid_crosses_both_leg_uvs_and_preserves_flowers_and_shoes(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        flower = (240, 240, 239, 255)
        shoe = (246, 203, 1, 255)
        for y in range(20, 32):
            for x in range(34, 38):
                original.putpixel((x, y), hair)
        braid = set()
        for row in range(11):
            # Back view: left leg comes before right leg, unlike front view.
            for column in (3, 4 if row % 2 else 2):
                coordinate = ((28 + column, 52 + row) if column < 4
                              else (12 + column - 4, 20 + row))
                original.putpixel(coordinate, hair)
                braid.add(coordinate)
        original.putpixel((31, 56), flower)
        braid.remove((31, 56))
        leaf = (101, 129, 44, 255)
        original.putpixel((12, 25), leaf)
        braid.remove((12, 25))
        # Isolated matching outer pixels must share the base strand's path.
        original.putpixel((14, 53), hair)
        braid.add((14, 53))
        for x in range(12, 16):
            original.putpixel((x, 31), shoe)

        styled, mask, _ = style_skin(original, (180, 90, 160), include_body_hair=True)

        self.assertTrue(braid <= mask, braid - mask)
        for coordinate in braid:
            self.assertNotEqual(styled.getpixel(coordinate), original.getpixel(coordinate))
        self.assertEqual(styled.getpixel((31, 56)), flower)
        self.assertEqual(styled.getpixel((12, 25)), leaf)
        for x in range(12, 16):
            self.assertEqual(styled.getpixel((x, 31)), shoe)

    def test_front_hair_continues_across_waist_to_aligned_leg(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        for y in range(20, 32):
            original.putpixel((20, y), hair)
            original.putpixel((4, y), hair)
        mask = detect_body_hair_mask(original)
        self.assertIn((4, 20), mask)
        self.assertIn((4, 31), mask)

    def test_matching_leg_pixels_need_hair_reaching_the_waist(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        for y in range(20, 28):
            original.putpixel((20, y), hair)
        for y in range(20, 32):
            original.putpixel((4, y), hair)
        mask = detect_body_hair_mask(original)
        self.assertIn((20, 25), mask)
        self.assertNotIn((4, 20), mask)
        self.assertNotIn((4, 31), mask)

    def test_waist_hair_does_not_recolor_broad_matching_trousers(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        for y in range(20, 32):
            original.putpixel((20, y), hair)
            for x in range(4, 8):
                original.putpixel((x, y), hair)
        mask = detect_body_hair_mask(original)
        self.assertIn((20, 31), mask)
        self.assertFalse(mask & {(x, y) for x in range(4, 8) for y in range(20, 32)})

    def test_leg_hair_does_not_jump_to_disconnected_matching_boots(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        for y in range(20, 32):
            original.putpixel((20, y), hair)
        for y in (*range(20, 28), *range(30, 32)):
            original.putpixel((4, y), hair)
        mask = detect_body_hair_mask(original)
        self.assertIn((4, 23), mask)
        self.assertNotIn((4, 30), mask)
        self.assertNotIn((4, 31), mask)

    def test_short_matching_hems_are_not_leg_hair(self):
        original = synthetic_skin(hair=(88, 40, 24, 255))
        hair = (90, 57, 25, 255)
        for y in range(20, 32):
            original.putpixel((20, y), hair)
        for y in range(20, 23):
            original.putpixel((4, y), hair)
        mask = detect_body_hair_mask(original)
        self.assertIn((20, 31), mask)
        self.assertNotIn((4, 20), mask)

    def test_flesh_like_head_palette_cannot_claim_shaded_legs(self):
        original = synthetic_skin(hair=(210, 150, 120, 255))
        shade = (212, 151, 118, 255)
        for y in range(20, 32):
            original.putpixel((20, y), shade)
            original.putpixel((4, y), shade)
        mask = detect_body_hair_mask(original)
        self.assertNotIn((4, 20), mask)
        self.assertNotIn((4, 31), mask)

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

    def test_generation_excludes_deferred_skins_and_kept_batch_requires_a_decision(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            statuses = ("favorite", "keep", "maybe", "remove", "unsorted")
            metadata = {f"{status}.png": {"status": status, "tag": "dresses"} for status in statuses}
            for filename in metadata:
                synthetic_skin().save(source / filename)
            originals = {path.name: path.read_bytes() for path in source.glob("*.png")}
            for batch, expected in (("all", {"keep", "favorite", "unsorted"}),
                                    ("dresses", {"keep", "favorite", "unsorted"}),
                                    ("kept", {"keep", "favorite"})):
                output = root / batch
                result = generate_folder(source, output, (100, 80, 180), standardize_face=False,
                                         wardrobe_metadata=metadata, batch_filter=batch)
                self.assertEqual(result.written, len(expected))
                self.assertEqual({path.stem for path in output.glob("*.png")}, expected)
            self.assertEqual(originals, {path.name: path.read_bytes() for path in source.glob("*.png")})

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

    def test_skin_tone_preserves_highlight_detail_near_white(self):
        from skin_styler_core import recolor_skin_tone
        original = synthetic_skin()
        points = [(44, 20), (45, 20), (46, 20), (47, 20)]
        for point, value in zip(points, (170, 205, 235, 252)):
            original.putpixel(point, (value, round(value * .8), round(value * .7), 173))
        styled, _ = recolor_skin_tone(original, (255, 220, 205), skin_mask=set(points))
        values = [sum(styled.getpixel(point)[:3]) for point in points]
        self.assertEqual(values, sorted(set(values)))
        self.assertTrue(all(styled.getpixel(point)[3] == 173 for point in points))

    def test_skin_tone_preserves_pale_shading_with_constant_red(self):
        from skin_styler_core import recolor_skin_tone

        original = synthetic_skin()
        points = [(44, 20), (45, 20), (46, 20)]
        for point, color in zip(points, ((255, 216, 192), (255, 223, 204), (255, 232, 219))):
            original.putpixel(point, color + (255,))
        target = (235, 189, 161)
        styled, _ = recolor_skin_tone(original, target, skin_mask=set(points))
        shades = [styled.getpixel(point)[:3] for point in points]
        self.assertEqual(shades[1], target)
        self.assertGreater(shades[2][1] - shades[0][1], 8)

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

    def test_skin_shade_confirmed_on_face_and_limbs_reaches_exposed_torso(self):
        for chin, exposed in (((162, 104, 69), (187, 126, 90)),
                              ((65, 39, 26), (108, 67, 45))):
            with self.subTest(chin=chin, exposed=exposed):
                original = synthetic_skin()
                draw = ImageDraw.Draw(original)
                draw.rectangle((8, 10, 15, 15), fill=(*chin, 255))
                draw.rectangle((11, 14, 12, 15), fill=(*exposed, 255))
                for box in ((44, 20, 47, 31), (36, 52, 39, 63), (4, 21, 7, 31), (20, 20, 27, 30)):
                    draw.rectangle(box, fill=(*exposed, 255))
                draw.rectangle((22, 23, 25, 24), fill=(255, 255, 255, 255))
                draw.point((22, 40), fill=(*exposed, 255))

                materials = classify_skin_categories(original)
                self.assertTrue({(23, 28), (45, 24), (5, 26)} <= materials.skin)
                self.assertIn((23, 23), materials.outfit)
                self.assertNotIn((22, 40), materials.skin)
                styled, _, _ = style_skin(original, None, target_skin_color=(238, 184, 158))
                self.assertNotEqual(styled.getpixel((23, 28)), original.getpixel((23, 28)))
                self.assertEqual(styled.getpixel((23, 23)), original.getpixel((23, 23)))
                self.assertEqual(styled.getpixel((22, 40)), original.getpixel((22, 40)))

    def test_back_hair_continues_on_both_layers_beside_similar_sleeves(self):
        hair = (100, 63, 23, 255)
        lit_hair = (143, 89, 33, 255)
        sleeve = (59, 39, 13, 255)
        original = synthetic_skin(hair=hair)
        draw = ImageDraw.Draw(original)
        for box in ((44, 20, 47, 31), (36, 52, 39, 63), (32, 20, 39, 31)):
            draw.rectangle(box, fill=sleeve)
        draw.rectangle((27, 8, 28, 15), fill=lit_hair)
        draw.rectangle((34, 20, 37, 29), fill=hair)
        draw.rectangle((35, 20, 36, 28), fill=lit_hair)
        draw.rectangle((35, 36, 36, 44), fill=lit_hair)

        materials = classify_skin_categories(original)
        self.assertTrue({(35, 28), (35, 44)} <= materials.hair)
        self.assertTrue({(45, 26), (32, 25), (35, 30)} <= materials.outfit)

    def test_deep_cheek_shades_along_both_arms_are_skin(self):
        original = synthetic_skin(hair=(18, 18, 18, 255))
        base = (159, 122, 119, 255)
        shadow = (126, 95, 93, 255)
        dark_shadow = (109, 74, 71, 255)
        dress = (222, 208, 200, 255)
        eye = (67, 106, 144, 255)
        draw = ImageDraw.Draw(original)
        draw.rectangle((8, 8, 15, 15), fill=base)
        draw.point([(9, 12), (14, 12)], fill=eye)
        draw.point([(9, 13), (14, 13)], fill=dark_shadow)
        draw.point([(9, 14), (14, 14)], fill=shadow)
        for x, y in ((44, 20), (36, 52)):
            draw.rectangle((x, y, x + 2, y + 11), fill=base)
            draw.rectangle((x, y + 2, x + 2, y + 3), fill=dress)
            draw.line((x, y + 4, x, y + 7), fill=dark_shadow)
            draw.line((x, y + 8, x, y + 11), fill=shadow)
        draw.point((4, 23), fill=dark_shadow)

        materials = classify_skin_categories(original)
        self.assertTrue({(9, 13), (14, 14), (44, 25), (36, 61), (4, 23)} <= materials.skin)
        self.assertTrue({(9, 12), (14, 12)} <= materials.eyes)
        self.assertIn((44, 22), materials.outfit)

        styled, _, _ = style_skin(original, None, target_skin_color=(241, 190, 172))
        self.assertNotEqual(styled.getpixel((44, 25)), dark_shadow)
        self.assertEqual(styled.getpixel((44, 22)), dress)
        self.assertLess(styled.getpixel((44, 25))[0], styled.getpixel((45, 25))[0])

        draw.rectangle((36, 56, 38, 63), fill=base)
        self.assertNotIn((4, 23), classify_skin_categories(original).skin)

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

    def test_outfit_recolor_respects_muted_swatch_on_mixed_fabric(self):
        target = (72, 126, 143)
        for fabric in ((26, 26, 26), (144, 62, 62)):
            with self.subTest(fabric=fabric):
                original = Image.new("RGBA", (64, 64))
                points = [(20 + x, 20 + y) for y in range(2) for x in range(8)]
                colors = [(0, 0, 0)] * 8 + [fabric] * 4 + [(246, 246, 246)] * 4
                for point, color in zip(points, colors):
                    original.putpixel(point, (*color, 172))
                styled, _, _ = style_skin(original, None, target_outfit_color=target,
                                          category_overrides=dict.fromkeys(points, "outfit"))
                shadow, midtone, highlight = [styled.getpixel(points[i]) for i in (0, 8, 12)]
                self.assertLess(sum(shadow[:3]), sum(midtone[:3]))
                self.assertLess(sum(midtone[:3]), sum(highlight[:3]))
                self.assertLessEqual(max(highlight[:3]), 183)
                target_saturation = 1 - min(target) / max(target)
                for red, green, blue, alpha in (shadow, midtone, highlight):
                    self.assertLess(red, green)
                    self.assertLess(green, blue)
                    self.assertEqual(alpha, 172)
                    self.assertLessEqual(1 - red / blue, target_saturation + .03)

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
