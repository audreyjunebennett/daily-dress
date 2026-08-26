"""Pixel-exact Minecraft skin styling for Daily Dress.

The source wardrobe is never modified. Every output is normalized to a 64x64
RGBA PNG. Hair color detection is deliberately constrained to the two head UV
regions, so outfit pixels elsewhere on the skin cannot be recolored.
"""

from __future__ import annotations

import argparse
import colorsys
import math
import shutil
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

from PIL import Image, ImageDraw

RGBA = tuple[int, int, int, int]
RGB = tuple[int, int, int]

BASE_HEAD = (0, 0, 32, 16)
HAT_HEAD = (32, 0, 64, 16)
FACE_FRONT = (8, 8, 16, 16)
HAT_FRONT = (40, 8, 48, 16)
STANDARD_EYE_ANCHOR = 14
EYE_FEATURE_BOX = (8, 12, 16, 15)
EYE_FEATURE_COLUMNS = (8, 9, 10, 13, 14, 15)
EYE_SEARCH_BOX = (8, 10, 16, 15)
TORSO_FRONT = (20, 20, 28, 32)
TORSO_RIGHT = (16, 20, 20, 32)
TORSO_LEFT = (28, 20, 32, 32)
TORSO_BACK = (32, 20, 40, 32)
TORSO_OVERLAY_FRONT = (20, 36, 28, 48)
TORSO_OVERLAY_RIGHT = (16, 36, 20, 48)
TORSO_OVERLAY_LEFT = (28, 36, 32, 48)
TORSO_OVERLAY_BACK = (32, 36, 40, 48)


def is_eye_feature_coordinate(x: int, y: int) -> bool:
    """Return whether a base-face pixel belongs to one of the two eye canvases."""

    _left, top, _right, bottom = EYE_FEATURE_BOX
    return x in EYE_FEATURE_COLUMNS and top <= y < bottom


@dataclass(frozen=True)
class FaceTemplate:
    """Eye-area pixels copied from one chosen reference skin."""

    features: dict[tuple[int, int], RGBA]
    skin_color: RGB
    anchor_y: int = STANDARD_EYE_ANCHOR


@dataclass(frozen=True)
class GenerationResult:
    written: int
    normalized: int
    skipped: tuple[str, ...]


@dataclass(frozen=True)
class InstallationResult:
    target: Path
    backup: Path | None
    installed: int


def parse_hex_color(value: str) -> RGB:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError("Color must look like #A45C8A")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exception:
        raise ValueError("Color must contain only hexadecimal digits") from exception


def normalize_skin(image: Image.Image) -> tuple[Image.Image, bool]:
    """Return a 64x64 RGBA skin, using nearest-neighbor for HD multiples."""

    converted = image.convert("RGBA")
    if converted.size == (64, 64):
        return converted, False
    width, height = converted.size
    if width == height and width >= 64 and width % 64 == 0:
        return converted.resize((64, 64), Image.Resampling.NEAREST), True
    raise ValueError(f"unsupported dimensions {width}x{height}; expected 64x64 or an integer HD multiple")


def _quantize(color: RGB, step: int = 16) -> RGB:
    return tuple(min(255, (channel // step) * step + step // 2) for channel in color)  # type: ignore[return-value]


def _distance(first: RGB, second: RGB) -> float:
    # Red-mean-ish weighted RGB distance, divided into a friendly ~0-255 scale.
    red_mean = (first[0] + second[0]) / 2
    red_weight = 2 + red_mean / 256
    blue_weight = 2 + (255 - red_mean) / 256
    total = red_weight * (first[0] - second[0]) ** 2
    total += 4 * (first[1] - second[1]) ** 2
    total += blue_weight * (first[2] - second[2]) ** 2
    return math.sqrt(total) / 2.8


def _likely_skin_tone(color: RGB) -> bool:
    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))
    degrees = hue * 360
    return (degrees <= 55 or degrees >= 345) and 0.06 <= saturation <= 0.78 and value >= 0.22


def _hair_seed_coordinates() -> Iterable[tuple[int, int]]:
    # The top/back of the base head are overwhelmingly hair on humanoid skins.
    for y in range(0, 8):
        for x in range(8, 16):
            yield x, y
    for y in range(8, 16):
        for x in range(24, 32):
            yield x, y
    for y in range(8, 12):
        for x in (*range(0, 8), *range(16, 24)):
            yield x, y
    # Opaque pixels on the hat layer are useful fringe/highlight seeds.
    for y in range(0, 16):
        for x in range(32, 64):
            yield x, y


def hair_palette(skin: Image.Image, max_colors: int = 10) -> tuple[RGB, ...]:
    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    counts: Counter[RGB] = Counter()
    for x, y in _hair_seed_coordinates():
        red, green, blue, alpha = pixels[x, y]
        if alpha >= 48:
            counts[_quantize((red, green, blue))] += 1

    if not counts:
        return ()

    # Keep the colors that explain most seed pixels, including several shades.
    selected: list[RGB] = []
    covered = 0
    target = max(1, int(sum(counts.values()) * 0.86))
    for color, count in counts.most_common(max_colors):
        selected.append(color)
        covered += count
        if covered >= target and len(selected) >= 3:
            break
    return tuple(selected)


def _matches_hair_palette(color: RGB, palette: tuple[RGB, ...], tolerance: float) -> bool:
    if min(_distance(color, seed) for seed in palette) <= tolerance:
        return True

    # RGB distance alone drops bright tips of a dark hairstyle. A restrained
    # HSV comparison recovers those shade extremes while the later skin mask
    # still removes genuinely exposed face pixels of a similar warm hue.
    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))
    if saturation < 0.09 or value < 0.04:
        return False
    for seed in palette[:6]:
        seed_hue, seed_saturation, seed_value = colorsys.rgb_to_hsv(*(channel / 255 for channel in seed))
        if seed_saturation < 0.09 or seed_value < 0.04:
            continue
        hue_gap = abs(hue - seed_hue)
        hue_gap = min(hue_gap, 1.0 - hue_gap)
        if hue_gap <= 24 / 360 and abs(saturation - seed_saturation) <= 0.48:
            return True
    return False


def _same_hue_shading_family(
    color: RGB,
    palette: tuple[RGB, ...],
    hue_limit: float = 24.0,
    saturation_limit: float = 0.28,
) -> bool:
    """Match noisy light/dark shades without accepting a new garment palette."""

    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))
    if saturation < 0.06 or value < 0.035:
        return False
    for seed in palette:
        seed_hue, seed_saturation, seed_value = colorsys.rgb_to_hsv(
            *(channel / 255 for channel in seed)
        )
        if seed_saturation < 0.06 or seed_value < 0.035:
            continue
        hue_gap = min(abs(hue - seed_hue), 1.0 - abs(hue - seed_hue))
        if hue_gap <= hue_limit / 360 and abs(saturation - seed_saturation) <= saturation_limit:
            return True
    return False


def _body_hair_match(color: RGB, palette: tuple[RGB, ...], tolerance: float) -> bool:
    """Use hue-aware matching on body UVs where pastel clothes are common."""

    if not palette:
        return False
    nearest = min(_distance(color, seed) for seed in palette)
    if nearest <= min(25.0, tolerance * 0.58):
        return True
    palette_has_hue = any(
        colorsys.rgb_to_hsv(*(channel / 255 for channel in seed))[1] >= 0.08
        for seed in palette
    )
    if palette_has_hue:
        return _same_hue_shading_family(color, palette, 32.0, 0.40)
    return nearest <= tolerance


def detect_hair_mask(skin: Image.Image, tolerance: float = 42.0) -> set[tuple[int, int]]:
    """Detect hair pixels without touching torso/arms/legs."""

    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    palette = hair_palette(normalized)
    if not palette:
        return set()

    mask: set[tuple[int, int]] = set()
    for y in range(16):
        for x in range(64):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 48:
                continue
            color = (red, green, blue)
            if _matches_hair_palette(color, palette, tolerance):
                mask.add((x, y))

    # Eye heights vary between skin artists. Locate this face's own eye anchor,
    # then protect symmetric eye pixels while retaining bangs connected from
    # above. This prevents a lower iris row from being recolored as hair.
    skin_color = _median_skin_color(normalized, mask)
    eye_anchor = detect_eye_anchor(normalized, skin_color)
    left, _search_top, right, search_bottom = EYE_SEARCH_BOX
    top = max(EYE_SEARCH_BOX[1], eye_anchor - 2)
    bottom = min(search_bottom, eye_anchor + 1)
    eye_pixels = _bilateral_eye_features(normalized, skin_color, eye_anchor)
    vertical_tolerance = min(38.0, max(22.0, tolerance * 0.68))
    for x, y in eye_pixels:
        above = (x, y - 1)
        if above not in mask or _distance(pixels[x, y][:3], pixels[x, y - 1][:3]) > vertical_tolerance:
            mask.discard((x, y))

    face_candidates = {
        coordinate
        for coordinate in mask
        if FACE_FRONT[0] <= coordinate[0] < FACE_FRONT[2]
        and FACE_FRONT[1] <= coordinate[1] < FACE_FRONT[3]
    }
    connected = {coordinate for coordinate in face_candidates if coordinate[1] <= top}
    pending = list(connected)
    connection_tolerance = min(48.0, max(24.0, tolerance * 0.86))
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (
                neighbor in face_candidates
                and neighbor not in connected
                and _distance(pixels[x, y][:3], pixels[neighbor[0], neighbor[1]][:3]) <= connection_tolerance
            ):
                connected.add(neighbor)
                pending.append(neighbor)
    for y in range(top, bottom):
        for x in EYE_FEATURE_COLUMNS:
            if (x, y) not in connected:
                mask.discard((x, y))

    # The center below the eyes is reserved for nose/mouth details. Central
    # bangs above it remain eligible, including the bright tips at row 11.
    for y in range(13, FACE_FRONT[3]):
        mask.discard((11, y))
        mask.discard((12, y))

    # The outer head layer can contain either a hair strand or an eye accent.
    # Apply the same connectivity rule there, using the front-overlay UV offset.
    overlay_candidates = {
        coordinate
        for coordinate in mask
        if HAT_FRONT[0] <= coordinate[0] < HAT_FRONT[2]
        and HAT_FRONT[1] <= coordinate[1] < HAT_FRONT[3]
    }
    overlay_connected = {coordinate for coordinate in overlay_candidates if coordinate[1] <= top}
    pending = list(overlay_connected)
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (
                neighbor in overlay_candidates
                and neighbor not in overlay_connected
                and _distance(pixels[x, y][:3], pixels[neighbor[0], neighbor[1]][:3]) <= connection_tolerance
            ):
                overlay_connected.add(neighbor)
                pending.append(neighbor)
    overlay_offset = HAT_FRONT[0] - FACE_FRONT[0]
    for y in range(top, bottom):
        for x in EYE_FEATURE_COLUMNS:
            overlay = (x + overlay_offset, y)
            if overlay not in overlay_connected:
                mask.discard(overlay)
    return mask


def _strict_hair_match(color: RGB, palette: tuple[RGB, ...], tolerance: float) -> bool:
    return bool(palette) and min(_distance(color, seed) for seed in palette) <= tolerance


def _hair_core_palette(palette: tuple[RGB, ...]) -> tuple[RGB, ...]:
    """Keep genuine shades of the dominant hair family, excluding accessories.

    Outer-layer flowers, goggles, and headbands are valid palette samples but
    must not become long-hair anchors merely because they occupy the hat UV.
    Very dark shadows and same-hue highlights remain eligible.
    """

    if not palette:
        return ()
    anchor = palette[0]
    anchor_hue, anchor_saturation, _anchor_value = colorsys.rgb_to_hsv(
        *(channel / 255 for channel in anchor)
    )
    selected: list[RGB] = []
    for color in palette:
        hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))
        hue_gap = abs(hue - anchor_hue)
        hue_gap = min(hue_gap, 1.0 - hue_gap)
        if (
            value <= 0.12
            or (
                anchor_saturation < 0.08
                and _distance(color, anchor) <= 68
            )
            or (
                saturation < 0.05
                and _distance(color, anchor) <= 52
            )
            or (
                anchor_saturation >= 0.08
                and saturation >= 0.05
                and hue_gap <= 32 / 360
            )
        ):
            selected.append(color)
    return tuple(selected or palette[:1])


def _head_to_body_seed_columns(
    hair_mask: set[tuple[int, int]],
    head_box: tuple[int, int, int, int],
    head_overlay_box: tuple[int, int, int, int],
    body_width: int,
) -> set[int]:
    """Project bottom-edge head hair onto columns of one torso surface."""

    head_width = head_box[2] - head_box[0]
    seeds: set[int] = set()
    for body_x in range(body_width):
        start = math.floor(body_x * head_width / body_width)
        end = max(start + 1, math.ceil((body_x + 1) * head_width / body_width))
        for local_x in range(start, min(head_width, end)):
            base_x = head_box[0] + local_x
            overlay_x = head_overlay_box[0] + local_x
            if any(
                (base_x, y) in hair_mask or (overlay_x, y) in hair_mask
                for y in range(head_box[3] - 3, head_box[3])
            ):
                seeds.add(body_x)
                break
    return seeds


def _head_to_body_seed_colors(
    skin: Image.Image,
    hair_mask: set[tuple[int, int]],
    head_box: tuple[int, int, int, int],
    head_overlay_box: tuple[int, int, int, int],
    body_width: int,
) -> dict[int, tuple[RGB, ...]]:
    """Project the actual bottom-edge head colors onto each torso column."""

    pixels = skin.load()
    head_width = head_box[2] - head_box[0]
    projected: dict[int, tuple[RGB, ...]] = {}
    for body_x in range(body_width):
        start = math.floor(body_x * head_width / body_width)
        end = max(start + 1, math.ceil((body_x + 1) * head_width / body_width))
        colors: list[RGB] = []
        for local_x in range(start, min(head_width, end)):
            for source_x in (head_box[0] + local_x, head_overlay_box[0] + local_x):
                for y in range(head_box[3] - 3, head_box[3]):
                    if (source_x, y) in hair_mask:
                        color = pixels[source_x, y][:3]
                        if color not in colors:
                            colors.append(color)
        if colors:
            projected[body_x] = tuple(colors)
    return projected


def _trace_surface_hair_paths(
    skin: Image.Image,
    box: tuple[int, int, int, int],
    palette: tuple[RGB, ...],
    seed_columns: set[int],
    tolerance: float,
    start_depth: int,
    max_per_half: int | None,
    seed_colors: dict[int, tuple[RGB, ...]] | None = None,
) -> set[tuple[int, int]]:
    """Trace downward, edge-aware paths from a mapped head/torso seam."""

    if not palette or not seed_columns:
        return set()
    pixels = skin.load()
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    edge_limit = min(82.0, max(52.0, tolerance * 1.42))
    palette_limit = min(62.0, max(40.0, tolerance * 1.18))
    seed_edge_limit = min(32.0, max(22.0, tolerance * 0.66))
    seed_skin_center = _median_skin_color(skin, set()) if skin.size == (64, 64) else None

    candidate_distance: dict[tuple[int, int], float] = {}
    nearest_seed: dict[tuple[int, int], int] = {}
    for local_y in range(height):
        for local_x in range(width):
            color = pixels[left + local_x, top + local_y]
            if color[3] < 48:
                continue
            distances = [_distance(color[:3], seed) for seed in palette]
            nearest = min(range(len(distances)), key=distances.__getitem__)
            if _body_hair_match(color[:3], palette, palette_limit):
                coordinate = (local_x, local_y)
                candidate_distance[coordinate] = min(distances[nearest], palette_limit * 0.92)
                nearest_seed[coordinate] = nearest

    accepted: set[tuple[int, int]] = set()
    scores: dict[tuple[int, int], float] = {}
    for local_y in range(height):
        row_candidates = [coordinate for coordinate in candidate_distance if coordinate[1] == local_y]
        proposed: list[tuple[float, tuple[int, int]]] = []
        for local_x, _y in row_candidates:
            coordinate = (local_x, local_y)
            palette_quality = 1.0 - candidate_distance[coordinate] / max(1.0, palette_limit)
            best: float | None = None
            nearby_seed_colors = (
                tuple(
                    color
                    for _seed_column, colors in (seed_colors or {}).items()
                    for color in colors
                    if not (
                        seed_skin_center is not None
                        and
                        _likely_skin_tone(color)
                        and _distance(color, seed_skin_center) <= 24.0
                    )
                    and (
                        _strict_hair_match(color, palette, seed_edge_limit)
                        or _same_hue_shading_family(color, palette, 24.0, 0.22)
                    )
                )
                if seed_colors is not None
                else ()
            )
            handoff_is_valid = (
                seed_colors is None
                or not nearby_seed_colors
                or min(
                    _distance(pixels[left + local_x, top + local_y][:3], color)
                    for color in nearby_seed_colors
                )
                <= seed_edge_limit
                or _same_hue_shading_family(
                    pixels[left + local_x, top + local_y][:3],
                    nearby_seed_colors,
                )
            )
            # The first half of a torso surface must remain compatible with
            # the real hair shade above it. This prevents a nearby bikini or
            # collar from joining a strand diagonally one row after the seam.
            if local_y < max(6, start_depth) and not handoff_is_valid:
                continue
            if local_y < start_depth and min(abs(local_x - seed) for seed in seed_columns) <= 1:
                if handoff_is_valid:
                    best = 2.0 + palette_quality - local_y * 0.18

            for previous_y in (local_y - 1, local_y - 2):
                if previous_y < 0:
                    continue
                for previous_x in range(max(0, local_x - 1), min(width, local_x + 2)):
                    previous = (previous_x, previous_y)
                    if previous not in scores:
                        continue
                    previous_color = pixels[left + previous_x, top + previous_y][:3]
                    current_color = pixels[left + local_x, top + local_y][:3]
                    border = _distance(previous_color, current_color)
                    same_palette_track = nearest_seed.get(previous) == nearest_seed[coordinate]
                    if border > edge_limit and not (same_palette_track and border <= edge_limit * 1.25):
                        continue
                    gap_penalty = 0.34 if previous_y == local_y - 2 else 0.0
                    drift_penalty = abs(previous_x - local_x) * 0.16
                    continuation = (
                        scores[previous]
                        + 0.82
                        + palette_quality * 0.55
                        - border / max(1.0, edge_limit) * 0.48
                        - gap_penalty
                        - drift_penalty
                    )
                    if best is None or continuation > best:
                        best = continuation
            if best is not None and best >= 1.35:
                proposed.append((best, coordinate))

        if max_per_half is not None:
            kept: list[tuple[float, tuple[int, int]]] = []
            midpoint = width / 2
            for right_half in (False, True):
                half = [item for item in proposed if (item[1][0] >= midpoint) == right_half]
                half.sort(reverse=True)
                kept.extend(half[:max_per_half])
            proposed = kept
        for score, coordinate in proposed:
            scores[coordinate] = score
            accepted.add((left + coordinate[0], top + coordinate[1]))
    return accepted


def _link_aligned_torso_hair_layers(
    skin: Image.Image,
    mask: set[tuple[int, int]],
    palette: tuple[RGB, ...],
    tolerance: float,
) -> set[tuple[int, int]]:
    """Mirror confirmed strands between aligned base and outer torso UVs.

    Skin artists often paint one continuous lock partly on the torso and partly
    on its jacket layer. Independent edge tracing can accept only one copy even
    when the aligned pixels are the same shade. A counterpart is linked only
    when it is opaque, belongs to the head-hair palette, and remains close to
    the already-confirmed pixel, which protects unrelated clothing underneath.
    """

    if not mask or not palette:
        return set(mask)
    pixels = skin.load()
    linked = set(mask)
    palette_limit = min(58.0, max(36.0, tolerance * 1.10))
    counterpart_limit = min(48.0, max(28.0, tolerance))
    layer_pairs = (
        (TORSO_FRONT, TORSO_OVERLAY_FRONT),
        (TORSO_RIGHT, TORSO_OVERLAY_RIGHT),
        (TORSO_LEFT, TORSO_OVERLAY_LEFT),
        (TORSO_BACK, TORSO_OVERLAY_BACK),
    )
    for base_box, overlay_box in layer_pairs:
        width = base_box[2] - base_box[0]
        height = base_box[3] - base_box[1]
        for local_y in range(height):
            for local_x in range(width):
                base = (base_box[0] + local_x, base_box[1] + local_y)
                overlay = (overlay_box[0] + local_x, overlay_box[1] + local_y)
                for confirmed, counterpart in ((base, overlay), (overlay, base)):
                    if confirmed not in mask or counterpart in linked:
                        continue
                    confirmed_color = pixels[confirmed[0], confirmed[1]]
                    counterpart_color = pixels[counterpart[0], counterpart[1]]
                    if counterpart_color[3] < 48:
                        continue
                    if not _body_hair_match(counterpart_color[:3], palette, palette_limit):
                        continue
                    if _distance(confirmed_color[:3], counterpart_color[:3]) > counterpart_limit:
                        continue
                    linked.add(counterpart)
    return linked


def _fill_small_torso_hair_gaps(
    skin: Image.Image,
    mask: set[tuple[int, int]],
    palette: tuple[RGB, ...],
    tolerance: float,
) -> set[tuple[int, int]]:
    """Fill tiny palette-matched holes touching an established torso strand."""

    if not mask or not palette:
        return set(mask)
    pixels = skin.load()
    filled = set(mask)
    palette_limit = min(50.0, max(34.0, tolerance * 1.12))
    boxes = (
        TORSO_FRONT,
        TORSO_RIGHT,
        TORSO_LEFT,
        TORSO_BACK,
        TORSO_OVERLAY_FRONT,
        TORSO_OVERLAY_RIGHT,
        TORSO_OVERLAY_LEFT,
        TORSO_OVERLAY_BACK,
    )
    for box in boxes:
        left, top, right, bottom = box
        width = right - left
        candidates = {
            (x, y)
            for y in range(top, bottom)
            for x in range(left, right)
            if (x, y) not in filled
            and pixels[x, y][3] >= 48
            and _body_hair_match(pixels[x, y][:3], palette, palette_limit)
            and (
                box not in (TORSO_FRONT, TORSO_OVERLAY_FRONT)
                or x - left <= 2
                or x - left >= width - 3
            )
        }
        seen: set[tuple[int, int]] = set()
        for seed in candidates:
            if seed in seen:
                continue
            component = {seed}
            pending = [seed]
            seen.add(seed)
            while pending:
                x, y = pending.pop()
                for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if neighbor in candidates and neighbor not in seen:
                        seen.add(neighbor)
                        component.add(neighbor)
                        pending.append(neighbor)
            if len(component) > 3:
                continue
            touching = sum(
                any(
                    (x + offset_x, y + offset_y) in filled
                    for offset_x in (-1, 0, 1)
                    for offset_y in (-1, 0, 1)
                    if offset_x or offset_y
                )
                for x, y in component
            )
            if touching == len(component):
                filled.update(component)
    return filled


def _detect_shoulder_hair(
    skin: Image.Image,
    head_mask: set[tuple[int, int]],
    torso_mask: set[tuple[int, int]],
    palette: tuple[RGB, ...],
    tolerance: float,
) -> set[tuple[int, int]]:
    """Recover hair painted across shoulder caps and upper arm surfaces."""

    if not torso_mask or not palette:
        return set()
    pixels = skin.load()
    reference_colors = [pixels[x, y][:3] for x, y in torso_mask]
    reference_colors.extend(
        pixels[x, y][:3]
        for x, y in head_mask
        if y >= 12 and (x < 8 or 16 <= x < 24 or 32 <= x < 40 or 48 <= x < 56)
    )
    if not reference_colors:
        return set()
    color_limit = min(42.0, max(28.0, tolerance * 0.86))

    # Each tuple is an arm's base/outer top cap followed by the upper rows of
    # its four vertical faces. Hair draped over a shoulder rarely reaches any
    # farther; stopping there keeps matching sleeves and cuffs protected.
    regions = (
        ((44, 16, 48, 20), (40, 20, 56, 23)),
        ((44, 32, 48, 36), (40, 36, 56, 39)),
        ((36, 48, 40, 52), (32, 52, 48, 55)),
        ((52, 48, 56, 52), (48, 52, 64, 55)),
    )
    recovered: set[tuple[int, int]] = set()
    for cap, upper_faces in regions:
        candidates = {
            (x, y)
            for box in (cap, upper_faces)
            for y in range(box[1], box[3])
            for x in range(box[0], box[2])
            if pixels[x, y][3] >= 48
            and _body_hair_match(pixels[x, y][:3], palette, color_limit)
            and min(_distance(pixels[x, y][:3], reference) for reference in reference_colors) <= color_limit
        }
        for component in _pixel_components(candidates, pixels, color_limit):
            # A broad, flesh-hued rectangle on an upper arm is an exposed
            # shoulder, not a lock. Genuine shoulder wisps are normally narrow
            # components; retain those (including warm brown hair) while
            # rejecting the 3x4 skin patches common on swimsuits/base skins.
            if len(component) >= 6 and all(
                _likely_skin_tone(pixels[x, y][:3]) for x, y in component
            ):
                continue
            if len(component) <= 24:
                recovered.update(component)
    return recovered


def _prune_torso_hair_handoffs(
    skin: Image.Image,
    mask: set[tuple[int, int]],
    head_mask: set[tuple[int, int]],
    palette: tuple[RGB, ...],
    tolerance: float,
) -> set[tuple[int, int]]:
    """Keep cleanup passes from crossing a rejected head-to-clothing seam."""

    if not mask or not palette:
        return set(mask)
    pixels = skin.load()
    seed_limit = min(32.0, max(22.0, tolerance * 0.66))
    seed_skin_center = _median_skin_color(skin, head_mask)
    surface_specs = (
        (TORSO_FRONT, (8, 8, 16, 16), (40, 8, 48, 16)),
        (TORSO_OVERLAY_FRONT, (8, 8, 16, 16), (40, 8, 48, 16)),
        (TORSO_RIGHT, (0, 8, 8, 16), (32, 8, 40, 16)),
        (TORSO_OVERLAY_RIGHT, (0, 8, 8, 16), (32, 8, 40, 16)),
        (TORSO_LEFT, (16, 8, 24, 16), (48, 8, 56, 16)),
        (TORSO_OVERLAY_LEFT, (16, 8, 24, 16), (48, 8, 56, 16)),
        (TORSO_BACK, (24, 8, 32, 16), (56, 8, 64, 16)),
        (TORSO_OVERLAY_BACK, (24, 8, 32, 16), (56, 8, 64, 16)),
    )
    torso_coordinates: set[tuple[int, int]] = set()
    retained: set[tuple[int, int]] = set()
    for box, head_box, overlay_box in surface_specs:
        left, top, right, bottom = box
        region = {(x, y) for y in range(top, bottom) for x in range(left, right)}
        torso_coordinates.update(region)
        surface_mask = mask & region
        if not surface_mask:
            continue
        projected = _head_to_body_seed_colors(
            skin,
            head_mask,
            head_box,
            overlay_box,
            right - left,
        )
        trusted_colors = tuple(
            color
            for colors in projected.values()
            for color in colors
            if not (
                _likely_skin_tone(color)
                and _distance(color, seed_skin_center) <= 24.0
            )
            and (
                _strict_hair_match(color, palette, seed_limit)
                or _same_hue_shading_family(color, palette, 24.0, 0.22)
            )
        )
        if not trusted_colors:
            retained.update(surface_mask)
            continue
        eligible = {
            coordinate
            for coordinate in surface_mask
            if coordinate[1] - top >= 6
            or min(
                _distance(pixels[coordinate[0], coordinate[1]][:3], color)
                for color in trusted_colors
            )
            <= seed_limit
            or _same_hue_shading_family(
                pixels[coordinate[0], coordinate[1]][:3],
                trusted_colors,
            )
        }
        connected = {coordinate for coordinate in eligible if coordinate[1] - top < 6}
        pending = list(connected)
        while pending:
            x, y = pending.pop()
            for offset_y in (-2, -1, 0, 1, 2):
                for offset_x in (-1, 0, 1):
                    if not offset_x and not offset_y:
                        continue
                    neighbor = (x + offset_x, y + offset_y)
                    if neighbor in eligible and neighbor not in connected:
                        connected.add(neighbor)
                        pending.append(neighbor)
        retained.update(connected)
    return (mask - torso_coordinates) | retained


def detect_body_hair_mask(skin: Image.Image, tolerance: float = 42.0) -> set[tuple[int, int]]:
    """Conservatively find long hair painted down torso UVs.

    Front strands must descend from the shoulder area and stay near the sides;
    broad central clothing is deliberately excluded even when it shares a hue.
    A matching back curtain is accepted only when front shoulder strands prove
    that the skin actually uses body-length hair.
    """

    normalized, _ = normalize_skin(skin)
    palette = hair_palette(normalized)
    if not palette:
        return set()
    core = _hair_core_palette(palette)
    strict_tolerance = min(58.0, max(38.0, tolerance * 1.12))
    mask: set[tuple[int, int]] = set()
    pixels = normalized.load()
    head_mask = detect_hair_mask(normalized, tolerance)
    # Establish anatomical skin before any torso pixels can be labeled hair.
    # Passing only the head mask avoids the circular failure where a pale hair
    # palette claims neck skin first and the later skin detector is forbidden
    # from taking it back.
    protected_skin = detect_skin_mask(normalized, head_mask, 24.0)

    arm_samples = [
        (x, y)
        for left, top, right, bottom in ((44, 20, 47, 32), (36, 52, 39, 64))
        for y in range(top, bottom)
        for x in range(left, right)
        if pixels[x, y][3] >= 48
    ]
    skin_center = _median_skin_color(normalized, head_mask)
    non_skin_arm_samples = [
        (x, y)
        for x, y in arm_samples
        if _distance(pixels[x, y][:3], skin_center) > max(28.0, tolerance * 0.72)
    ]
    core_has_hue = any(
        colorsys.rgb_to_hsv(*(channel / 255 for channel in color))[1] >= 0.08
        for color in core
    )
    matching_arm_samples = sum(
        1
        for x, y in non_skin_arm_samples
        if _strict_hair_match(pixels[x, y][:3], core, strict_tolerance)
        and (
            not core_has_hue
            or _same_hue_shading_family(pixels[x, y][:3], core, 32.0, 0.34)
        )
    )
    arm_match_ratio = matching_arm_samples / max(1, len(non_skin_arm_samples))
    # A few true locks may lie on the upper arm. Treat the palette as clothing
    # only when it covers a substantial arm area like a sleeve or jacket.
    clothing_conflict = (
        len(non_skin_arm_samples) >= 16
        and matching_arm_samples >= 12
        and arm_match_ratio >= 0.45
    )

    surface_specs = (
        (TORSO_FRONT, (8, 8, 16, 16), (40, 8, 48, 16), 3, 2),
        (TORSO_OVERLAY_FRONT, (8, 8, 16, 16), (40, 8, 48, 16), 5, 2),
        (TORSO_RIGHT, (0, 8, 8, 16), (32, 8, 40, 16), 3, 2),
        (TORSO_OVERLAY_RIGHT, (0, 8, 8, 16), (32, 8, 40, 16), 5, 2),
        (TORSO_LEFT, (16, 8, 24, 16), (48, 8, 56, 16), 3, 2),
        (TORSO_OVERLAY_LEFT, (16, 8, 24, 16), (48, 8, 56, 16), 5, 2),
        (TORSO_BACK, (24, 8, 32, 16), (56, 8, 64, 16), 3, None),
        (TORSO_OVERLAY_BACK, (24, 8, 32, 16), (56, 8, 64, 16), 5, None),
    )
    for box, head_box, overlay_box, start_depth, max_per_half in surface_specs:
        width = box[2] - box[0]
        seeds = _head_to_body_seed_columns(head_mask, head_box, overlay_box, width)
        seed_colors = _head_to_body_seed_colors(normalized, head_mask, head_box, overlay_box, width)
        if box in (TORSO_FRONT, TORSO_OVERLAY_FRONT) and not seeds:
            seeds = {0, width - 1}
        if clothing_conflict and box not in (TORSO_OVERLAY_FRONT,):
            continue
        traced = _trace_surface_hair_paths(
            normalized,
            box,
            core,
            seeds,
            tolerance,
            start_depth,
            max_per_half,
            seed_colors,
        )
        if box in (TORSO_FRONT, TORSO_OVERLAY_FRONT):
            # Even a traced front strand should remain in the side lanes; this
            # keeps center-front collars and dress panels out of the mask.
            traced = {
                coordinate
                for coordinate in traced
                if coordinate[0] - box[0] <= 2 or coordinate[0] - box[0] >= width - 3
            }
            # Below the chest, a proven strand may widen from two to all three
            # safe edge columns. Upper torso rows deliberately stay narrower
            # so bikini tops and collars cannot become a third hair lane.
            lower_edge_candidates = {
                (x, y)
                for y in range(box[1] + 7, box[3])
                for x in range(box[0], box[2])
                if (x - box[0] <= 2 or x - box[0] >= width - 3)
                and pixels[x, y][3] >= 48
                and _body_hair_match(pixels[x, y][:3], core, strict_tolerance)
            }
            changed = True
            while changed:
                changed = False
                for coordinate in lower_edge_candidates - traced:
                    x, y = coordinate
                    if any(
                        neighbor in traced
                        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                    ):
                        traced.add(coordinate)
                        changed = True
        mask.update(traced)
    linked = _link_aligned_torso_hair_layers(normalized, mask, core, tolerance)
    filled = _fill_small_torso_hair_gaps(normalized, linked, core, tolerance)
    torso = _link_aligned_torso_hair_layers(normalized, filled, core, tolerance)
    torso = _prune_torso_hair_handoffs(normalized, torso, head_mask, core, tolerance)
    # Restore a genuinely aligned isolated outer-layer pixel only after both
    # surfaces have passed the seam gate; rejected clothing has no retained
    # counterpart from which it can grow back.
    torso = _link_aligned_torso_hair_layers(normalized, torso, core, tolerance)
    shoulder = _detect_shoulder_hair(normalized, head_mask, torso, core, tolerance)
    return (torso | shoulder) - protected_skin


def recolor_hair(
    skin: Image.Image,
    target: RGB,
    tolerance: float = 42.0,
    hair_mask: set[tuple[int, int]] | None = None,
    color_reference_mask: set[tuple[int, int]] | None = None,
    colorize_neutrals: bool = False,
    neutral_saturation_floor: float = 0.0,
) -> tuple[Image.Image, set[tuple[int, int]]]:
    normalized, _ = normalize_skin(skin)
    result = normalized.copy()
    source = normalized.load()
    destination = result.load()
    mask = set(hair_mask) if hair_mask is not None else detect_hair_mask(normalized, tolerance)
    if not mask:
        return result, mask
    reference_mask = set(color_reference_mask) if color_reference_mask else mask

    hue_x = 0.0
    hue_y = 0.0
    hue_weight = 0.0
    source_saturations: list[float] = []
    source_values: list[float] = []
    for x, y in reference_mask:
        red, green, blue, _alpha = source[x, y]
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if value < 0.02:
            continue
        source_values.append(value)
        if saturation < 0.04:
            continue
        weight = saturation * max(value, 0.15)
        angle = hue * math.tau
        hue_x += math.cos(angle) * weight
        hue_y += math.sin(angle) * weight
        hue_weight += weight
        source_saturations.append(saturation)

    target_hue, target_saturation, target_value = colorsys.rgb_to_hsv(*(channel / 255 for channel in target))
    if hue_weight == 0:
        if not colorize_neutrals or not source_values:
            return result, mask
        source_hue = target_hue
    else:
        source_hue = (math.atan2(hue_y, hue_x) / math.tau) % 1.0
    hue_shift = 0.0 if target_saturation < 0.02 else (target_hue - source_hue + 0.5) % 1.0 - 0.5
    source_saturation = max(0.03, statistics.median(source_saturations) if source_saturations else 0.03)
    source_value = max(0.03, statistics.median(source_values))
    saturation_scale = min(4.0, max(0.05, target_saturation / source_saturation))
    value_scale = min(3.0, max(0.15, target_value / source_value))

    for x, y in mask:
        red, green, blue, alpha = source[x, y]
        old_hue, old_saturation, old_value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if old_value < 0.02:
            continue
        if old_saturation < 0.04:
            if not colorize_neutrals:
                continue
            new_hue = target_hue
            neutral_weight = min(1.0, max(0.14, (1.0 - old_value) * 1.45 + 0.16))
            new_saturation = target_saturation * max(neutral_weight, neutral_saturation_floor)
        else:
            new_hue = (old_hue + hue_shift) % 1.0
            new_saturation = min(1.0, old_saturation * saturation_scale)
        new_value = min(1.0, old_value * value_scale)
        changed = colorsys.hsv_to_rgb(new_hue, new_saturation, new_value)
        destination[x, y] = tuple(round(channel * 255) for channel in changed) + (alpha,)
    return result, mask


def _median_skin_color(skin: Image.Image, hair_mask: set[tuple[int, int]]) -> RGB:
    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    # The bottom-center face is the most stable skin sample across wardrobes;
    # bangs and eyes commonly occupy the rows above it. Prefer it before the
    # broader fallback so red/orange hair cannot become the skin-tone anchor.
    safe_samples: list[RGB] = []
    for x, y in (*((x, 15) for x in range(9, 15)), (11, 14), (12, 14)):
        red, green, blue, alpha = pixels[x, y]
        color = (red, green, blue)
        if alpha >= 128 and _likely_skin_tone(color):
            safe_samples.append(color)
    if len(safe_samples) >= 2:
        return tuple(round(statistics.median(channel)) for channel in zip(*safe_samples))  # type: ignore[return-value]

    samples: list[RGB] = []
    for y in range(11, 16):
        for x in range(9, 15):
            if (x, y) in hair_mask:
                continue
            red, green, blue, alpha = pixels[x, y]
            color = (red, green, blue)
            if alpha >= 128 and _likely_skin_tone(color):
                samples.append(color)
    # Hair detection is intentionally conservative around bangs, so recover
    # face-colored pixels from the whole inner face when that mask hid every
    # lower-face sample.
    if not samples:
        for y in range(8, 16):
            for x in range(9, 15):
                red, green, blue, alpha = pixels[x, y]
                color = (red, green, blue)
                if alpha >= 128 and _likely_skin_tone(color):
                    samples.append(color)
    if not samples:
        for y in range(11, 16):
            for x in range(9, 15):
                red, green, blue, alpha = pixels[x, y]
                if alpha >= 128:
                    samples.append((red, green, blue))
    if not samples:
        return 0xC6, 0x8D, 0x71
    return tuple(round(statistics.median(channel)) for channel in zip(*samples))  # type: ignore[return-value]


def detect_eye_anchor(skin: Image.Image, skin_color: RGB | None = None) -> int:
    """Return the bottom row of the face's bilaterally matched eye features."""

    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    if skin_color is None:
        skin_color = _median_skin_color(normalized, set())
    candidates: list[tuple[int, int]] = []
    for y in range(EYE_SEARCH_BOX[1], EYE_SEARCH_BOX[3]):
        score = 0
        for left_x, right_x in ((9, 14), (10, 13)):
            left = pixels[left_x, y]
            right = pixels[right_x, y]
            if left[3] < 48 or right[3] < 48:
                continue
            if _distance(left[:3], skin_color) < 27 or _distance(right[:3], skin_color) < 27:
                continue
            if _distance(left[:3], right[:3]) <= 76:
                score += 1
        if score:
            candidates.append((score, y))
    if not candidates:
        return 13
    strongest = max(score for score, _y in candidates)
    allowed = max(1, strongest - 1)
    return max(y for score, y in candidates if score >= allowed)


def _bilateral_eye_features(skin: Image.Image, skin_color: RGB, anchor_y: int) -> set[tuple[int, int]]:
    """Find paired eye pixels near a previously detected per-skin anchor."""

    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    features: set[tuple[int, int]] = set()
    for y in range(max(EYE_SEARCH_BOX[1], anchor_y - 2), min(EYE_SEARCH_BOX[3], anchor_y + 1)):
        for left_x, right_x in ((9, 14), (10, 13)):
            left = pixels[left_x, y]
            right = pixels[right_x, y]
            if left[3] < 48 or right[3] < 48:
                continue
            if _distance(left[:3], skin_color) < 27 or _distance(right[:3], skin_color) < 27:
                continue
            if _distance(left[:3], right[:3]) <= 76:
                features.update(((left_x, y), (right_x, y)))
    return features


def _box_coordinates(box: tuple[int, int, int, int]) -> set[tuple[int, int]]:
    return {(x, y) for y in range(box[1], box[3]) for x in range(box[0], box[2])}


def _trace_skin_region(
    candidates: set[tuple[int, int]],
    region: set[tuple[int, int]],
    seeds: set[tuple[int, int]],
    pixels,
    edge_limit: float,
) -> set[tuple[int, int]]:
    """Flood skin-like pixels without crossing a sharp local garment edge."""

    available = candidates & region
    connected = available & seeds
    pending = list(connected)
    while pending:
        x, y = pending.pop()
        color = pixels[x, y][:3]
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor not in available or neighbor in connected:
                continue
            if _distance(color, pixels[neighbor[0], neighbor[1]][:3]) > edge_limit:
                continue
            connected.add(neighbor)
            pending.append(neighbor)
    return connected


def detect_skin_mask(
    skin: Image.Image,
    hair_mask: set[tuple[int, int]] | None = None,
    tolerance: float = 24.0,
) -> set[tuple[int, int]]:
    """Find exposed-skin shades by matching the skin's own central face palette."""

    normalized, _ = normalize_skin(skin)
    if hair_mask is None:
        hair_mask = detect_hair_mask(normalized)
    center = _median_skin_color(normalized, hair_mask)
    pixels = normalized.load()
    candidates: set[tuple[int, int]] = set()
    for y in range(64):
        for x in range(64):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 48:
                continue
            color = (red, green, blue)
            if _distance(color, center) > tolerance:
                continue
            candidates.add((x, y))

    # Forehead skin must connect back to the reliable lower face. This reaches
    # skin between bangs without reclaiming a similarly colored isolated bang.
    face_candidates = {
        coordinate for coordinate in candidates if 8 <= coordinate[0] < 16 and 8 <= coordinate[1] < 16
    }
    # Pale bangs can be nearly identical to the face palette. Preserve hair
    # pixels that form a continuous crown-to-face path; isolated false-positive
    # skin pixels remain available to the face flood below.
    crown_palette = _hair_core_palette(hair_palette(normalized))
    crown_hair_candidates = {
        coordinate
        for coordinate in face_candidates & hair_mask
        if crown_palette
        and min(
            _distance(pixels[coordinate[0], coordinate[1]][:3], hair_color)
            for hair_color in crown_palette
        )
        < _distance(pixels[coordinate[0], coordinate[1]][:3], center)
    }
    crown_hair = {coordinate for coordinate in crown_hair_candidates if coordinate[1] == 8}
    pending = list(crown_hair)
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor not in crown_hair_candidates or neighbor in crown_hair:
                continue
            if _distance(pixels[x, y][:3], pixels[neighbor[0], neighbor[1]][:3]) > 28.0:
                continue
            crown_hair.add(neighbor)
            pending.append(neighbor)
    face_candidates -= crown_hair
    connected_face = {
        coordinate for coordinate in face_candidates if coordinate[1] == 15 and 9 <= coordinate[0] <= 14
    }
    connected_face.update(
        coordinate for coordinate in face_candidates if coordinate[1] == 14 and coordinate[0] in (11, 12)
    )
    pending = list(connected_face)
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in face_candidates and neighbor not in connected_face:
                connected_face.add(neighbor)
                pending.append(neighbor)

    # Skin is painted on the base model. The second-layer UVs overwhelmingly
    # contain clothes, hair, and accessories, so never recolor those merely
    # because their palette resembles the face.
    head_region = _box_coordinates(BASE_HEAD)
    torso_region = _box_coordinates((16, 16, 40, 32))
    right_arm_region = _box_coordinates((40, 16, 56, 32))
    left_arm_region = _box_coordinates((32, 48, 48, 64))
    right_leg_region = _box_coordinates((0, 16, 16, 32))
    left_leg_region = _box_coordinates((16, 48, 32, 64))
    body_candidates = candidates - hair_mask

    # A seed must be substantially closer to the face palette than the broader
    # shading tolerance. This prevents pale swimsuits and shirts from becoming
    # anatomical anchors while still allowing their neighboring skin shades.
    core_limit = max(7.0, min(18.0, tolerance * 0.52))
    edge_limit = max(9.0, min(27.0, tolerance * 0.88))

    def core(coordinate: tuple[int, int]) -> bool:
        return (
            coordinate in body_candidates
            and _distance(pixels[coordinate[0], coordinate[1]][:3], center) <= core_limit
        )

    # Head base pixels are already protected by the hair mask; retain the
    # connected-face exception so forehead skin between bangs is still reached.
    mask = {coordinate for coordinate in body_candidates & head_region}
    mask.update(connected_face)

    # Reclaim exact face-palette shades anywhere on the anatomical base model,
    # even when a hand or shoulder is not connected to a conventional UV-edge
    # seed. This is intentionally narrower than the normal shading tolerance:
    # it protects bare/base skins and exposed shoulders without turning a pale
    # swimsuit or similarly colored sleeve into skin.
    anatomical_region = (
        torso_region
        | right_arm_region
        | left_arm_region
        | right_leg_region
        | left_leg_region
    )
    mask.update(
        coordinate
        for coordinate in body_candidates & anatomical_region
        if _distance(pixels[coordinate[0], coordinate[1]][:3], center) <= core_limit
    )

    # Torso skin begins at the neckline. A genuinely bare midriff can also begin
    # at the waist, but only from a close face-palette match; the flood then stops
    # at straps, collars, swimsuit panels, and other sharp local edges.
    torso_seed_candidates = {
        *((x, 20) for x in range(22, 26)),
        *((x, 20) for x in range(34, 38)),
        *((x, 31) for x in range(16, 40)),
    }
    torso_seeds = {coordinate for coordinate in torso_seed_candidates if core(coordinate)}
    mask.update(_trace_skin_region(body_candidates, torso_region, torso_seeds, pixels, edge_limit))

    # Arms normally expose hands at their lower edge; legs expose either thighs
    # at the upper edge or feet at the lower edge. Seed each UV face separately
    # so a sleeve, cuff, short, shoe, or sock boundary breaks the path cleanly.
    right_arm_seeds = {(x, 31) for x in range(40, 56) if core((x, 31))}
    left_arm_seeds = {(x, 63) for x in range(32, 48) if core((x, 63))}
    right_leg_seeds = {
        (x, y)
        for y in (20, 31)
        for x in range(0, 16)
        if core((x, y))
    }
    left_leg_seeds = {
        (x, y)
        for y in (52, 63)
        for x in range(16, 32)
        if core((x, y))
    }
    mask.update(_trace_skin_region(body_candidates, right_arm_region, right_arm_seeds, pixels, edge_limit))
    mask.update(_trace_skin_region(body_candidates, left_arm_region, left_arm_seeds, pixels, edge_limit))
    mask.update(_trace_skin_region(body_candidates, right_leg_region, right_leg_seeds, pixels, edge_limit))
    mask.update(_trace_skin_region(body_candidates, left_leg_region, left_leg_seeds, pixels, edge_limit))
    return mask


def recolor_skin_tone(
    skin: Image.Image,
    target: RGB,
    hair_mask: set[tuple[int, int]] | None = None,
    tolerance: float = 24.0,
    skin_mask: set[tuple[int, int]] | None = None,
) -> tuple[Image.Image, set[tuple[int, int]]]:
    normalized, _ = normalize_skin(skin)
    if hair_mask is None:
        hair_mask = detect_hair_mask(normalized)
    mask = set(skin_mask) if skin_mask is not None else detect_skin_mask(normalized, hair_mask, tolerance)
    result = normalized.copy()
    source = normalized.load()
    destination = result.load()
    if not mask:
        return result, mask

    values = []
    for x, y in mask:
        red, green, blue, _alpha = source[x, y]
        _hue, _saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        values.append(value)
    median_value = max(0.08, statistics.median(values))
    target_hue, target_saturation, target_value = colorsys.rgb_to_hsv(*(channel / 255 for channel in target))
    value_scale = min(2.5, max(0.35, target_value / median_value))

    for x, y in mask:
        red, green, blue, alpha = source[x, y]
        _old_hue, old_saturation, old_value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        new_saturation = min(1.0, target_saturation * 0.88 + old_saturation * 0.12)
        new_value = min(1.0, max(0.03, old_value * value_scale))
        changed = colorsys.hsv_to_rgb(target_hue, new_saturation, new_value)
        destination[x, y] = tuple(round(channel * 255) for channel in changed) + (alpha,)
    return result, mask


def _hair_hsv_center(skin: Image.Image, hair_mask: set[tuple[int, int]]) -> tuple[float, float, float]:
    pixels = skin.load()
    hue_x = 0.0
    hue_y = 0.0
    weights = 0.0
    saturations: list[float] = []
    values: list[float] = []
    base_samples = [coordinate for coordinate in hair_mask if coordinate[1] < 16 and coordinate[0] < 32]
    samples = base_samples or [coordinate for coordinate in hair_mask if coordinate[1] < 16]
    for x, y in samples:
        red, green, blue, alpha = pixels[x, y]
        if alpha < 48:
            continue
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        values.append(value)
        if saturation < 0.06:
            continue
        weight = saturation * max(0.15, value)
        hue_x += math.cos(hue * math.tau) * weight
        hue_y += math.sin(hue * math.tau) * weight
        weights += weight
        saturations.append(saturation)
    hue = (math.atan2(hue_y, hue_x) / math.tau) % 1.0 if weights else 0.0
    return (
        hue,
        statistics.median(saturations) if saturations else 0.0,
        statistics.median(values) if values else 0.5,
    )


def _accessory_like(color: RGB, hair_center: tuple[float, float, float]) -> bool:
    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))
    hair_hue, hair_saturation, hair_value = hair_center
    hue_gap = abs(hue - hair_hue)
    hue_gap = min(hue_gap, 1.0 - hue_gap)
    if saturation >= 0.11 and (hair_saturation < 0.08 or hue_gap >= 34 / 360):
        return True
    if saturation < 0.08 and hair_saturation >= 0.24 and abs(value - hair_value) >= 0.16:
        return True
    return False


def _pixel_components(
    coordinates: set[tuple[int, int]],
    pixels=None,
    edge_limit: float | None = None,
) -> list[set[tuple[int, int]]]:
    remaining = set(coordinates)
    components: list[set[tuple[int, int]]] = []
    while remaining:
        component = {remaining.pop()}
        pending = list(component)
        while pending:
            x, y = pending.pop()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    if (
                        pixels is not None
                        and edge_limit is not None
                        and _distance(pixels[x, y][:3], pixels[neighbor[0], neighbor[1]][:3]) > edge_limit
                    ):
                        continue
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        components.append(component)
    return components


def detect_hair_accessory_mask(
    skin: Image.Image,
    head_hair_mask: set[tuple[int, int]],
    body_hair_mask: set[tuple[int, int]] | None = None,
    skin_mask: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """Find color-bounded head accessories and ornaments embedded in long hair."""

    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    body_hair_mask = set(body_hair_mask or ())
    skin_mask = set(skin_mask or ())
    hair_center = _hair_hsv_center(normalized, head_hair_mask)

    protected_face = {
        (x, y)
        for y in range(10, 16)
        for x in (*range(8, 16), *range(40, 48))
    }
    head_candidates = {
        (x, y)
        for y in range(16)
        for x in range(32, 64)
        if pixels[x, y][3] >= 48
        and (x, y) in head_hair_mask
        and (x, y) not in skin_mask
        and (x, y) not in protected_face
        and _accessory_like(pixels[x, y][:3], hair_center)
    }
    head_mask: set[tuple[int, int]] = set()
    for component in _pixel_components(head_candidates, pixels, 46.0):
        if len(component) <= 32:
            head_mask.update(component)

    # A torso ornament should continue an accessory palette already established
    # on the outer head layer. Without this link, colorful jacket trim beside a
    # false-positive long-hair edge is far too easy to misclassify.
    head_accessory_colors = [pixels[x, y][:3] for x, y in head_mask]

    # Flowers and ribbons may be painted into the torso UV beside a braid or
    # long-hair curtain. Stay immediately beside confirmed hair, and require
    # most ornament pixels to touch it. This keeps a nearby floral blouse from
    # being mistaken for flowers pinned into a braid.
    corridor: set[tuple[int, int]] = set()
    for hair_x, hair_y in body_hair_mask:
        for offset_y in range(-1, 2):
            for offset_x in range(-1, 2):
                x = hair_x + offset_x
                y = hair_y + offset_y
                if 0 <= x < 64 and 16 <= y < 64:
                    corridor.add((x, y))
    body_candidates = {
        coordinate
        for coordinate in corridor
        if coordinate not in body_hair_mask
        and coordinate not in skin_mask
        and pixels[coordinate[0], coordinate[1]][3] >= 48
        and _accessory_like(pixels[coordinate[0], coordinate[1]][:3], hair_center)
    }
    body_mask: set[tuple[int, int]] = set()
    for component in _pixel_components(body_candidates, pixels, 46.0):
        contacts = 0
        touching_pixels = 0
        for x, y in component:
            local_contacts = sum(
                (x + offset_x, y + offset_y) in body_hair_mask
                for offset_y in (-1, 0, 1)
                for offset_x in (-1, 0, 1)
                if offset_x or offset_y
            )
            contacts += local_contacts
            touching_pixels += int(local_contacts > 0)
        minimum_touching = max(1, math.ceil(len(component) * 0.65))
        palette_match = bool(head_accessory_colors) and any(
            _distance(pixels[x, y][:3], head_color) <= 58
            for x, y in component
            for head_color in head_accessory_colors
        )
        tiny_embedded_ornament = (
            len(component) <= 6
            and touching_pixels == len(component)
            and contacts >= len(component) * 3
        )
        if (
            1 <= len(component) <= 24
            and touching_pixels >= minimum_touching
            and contacts >= max(2, len(component) * 2)
            and (palette_match or tiny_embedded_ornament)
        ):
            body_mask.update(component)
    return head_mask | body_mask


def detect_outfit_mask(
    skin: Image.Image,
    hair_mask: set[tuple[int, int]],
    skin_mask: set[tuple[int, int]],
    accessory_mask: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """Return opaque body pixels that are neither anatomical skin nor hair."""

    normalized, _ = normalize_skin(skin)
    pixels = normalized.load()
    excluded = set(hair_mask) | set(skin_mask) | set(accessory_mask or ())
    return {
        (x, y)
        for y in range(16, 64)
        for x in range(64)
        if pixels[x, y][3] >= 48 and (x, y) not in excluded
    }


def make_face_template(reference: Image.Image, hair_tolerance: float = 42.0) -> FaceTemplate:
    normalized, _ = normalize_skin(reference)
    hair_mask = detect_hair_mask(normalized, hair_tolerance)
    skin_color = _median_skin_color(normalized, hair_mask)
    source_anchor_y = detect_eye_anchor(normalized, skin_color)
    pixels = normalized.load()
    features: dict[tuple[int, int], RGBA] = {}

    # Copy only the eye band. Reference hair/bangs are explicitly excluded, and
    # the destination hair mask protects any strands that cross its own eyes.
    left, _top, right, _bottom = EYE_FEATURE_BOX
    top = max(EYE_SEARCH_BOX[1], source_anchor_y - 2)
    bottom = min(EYE_SEARCH_BOX[3], source_anchor_y + 1)
    vertical_shift = STANDARD_EYE_ANCHOR - source_anchor_y
    for y in range(top, bottom):
        for x in range(left, right):
            if x not in EYE_FEATURE_COLUMNS:
                continue
            if (x, y) in hair_mask:
                continue
            color = pixels[x, y]
            if color[3] >= 48 and _distance(color[:3], skin_color) >= 24:
                normalized_y = y + vertical_shift
                if EYE_FEATURE_BOX[1] <= normalized_y < EYE_FEATURE_BOX[3]:
                    features[(x, normalized_y)] = color
    return FaceTemplate(
        features=features,
        skin_color=skin_color,
        anchor_y=STANDARD_EYE_ANCHOR,
    )


def apply_face_template(
    styled: Image.Image,
    original: Image.Image,
    template: FaceTemplate,
    original_hair_mask: set[tuple[int, int]],
    match_reference_skin_tone: bool = False,
    face_fill_color: RGB | None = None,
    eyes_over_bangs: bool = True,
    preserve_hat_layer_lashes: bool = True,
) -> Image.Image:
    styled, _ = normalize_skin(styled)
    original, _ = normalize_skin(original)
    result = styled.copy()
    original_pixels = original.load()
    pixels = result.load()
    destination_skin = _median_skin_color(original, original_hair_mask)
    fill = face_fill_color or (template.skin_color if match_reference_skin_tone else destination_skin)
    original_anchor = detect_eye_anchor(original, destination_skin)
    destination_anchor = STANDARD_EYE_ANCHOR
    vertical_shift = destination_anchor - template.anchor_y
    liner_candidates = [
        color
        for (x, _y), color in template.features.items()
        if x in (EYE_FEATURE_BOX[0], EYE_FEATURE_BOX[2] - 1)
    ]
    liner_color = liner_candidates[0] if liner_candidates else None

    def probable_hat_lash(color: RGBA) -> bool:
        """Recognize the dark little overlay pixels some artists use as 3D liner."""

        if color[3] < 48:
            return False
        _hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in color[:3]))
        return value <= 0.40 and (saturation <= 0.72 or value <= 0.25)

    # Remove only the old eye-area pixels while keeping detected bangs intact.
    # Nose, mouth, forehead details, and both head-layer hairstyles stay local.
    left, _top, right, _bottom = EYE_FEATURE_BOX
    top = max(EYE_SEARCH_BOX[1], original_anchor - 2)
    bottom = min(EYE_SEARCH_BOX[3], original_anchor + 1)
    for y in range(top, bottom):
        for x in range(left, right):
            if x not in EYE_FEATURE_COLUMNS:
                continue
            if (x, y) in original_hair_mask:
                continue
            old = original_pixels[x, y]
            if old[3] >= 48:
                pixels[x, y] = fill + (old[3],)

    for (x, y), color in template.features.items():
        coordinate = (x, y + vertical_shift)
        if (
            EYE_SEARCH_BOX[1] <= coordinate[1] < EYE_SEARCH_BOX[3]
            and (eyes_over_bangs or coordinate not in original_hair_mask)
        ):
            pixels[coordinate[0], coordinate[1]] = color

    # Remove the destination's old outer-layer eye accents so they cannot mix
    # with the designed style. Eye colors are never written to this hat layer.
    # When requested, only the overlay pixels directly covering incoming eye or
    # liner features become transparent so the base-layer feature shows through.
    overlay_offset = HAT_FRONT[0] - FACE_FRONT[0]
    for y in range(top, bottom):
        for x in range(left, right):
            if x not in EYE_FEATURE_COLUMNS:
                continue
            overlay = (x + overlay_offset, y)
            keep_lash = preserve_hat_layer_lashes and probable_hat_lash(original_pixels[overlay[0], overlay[1]])
            if overlay not in original_hair_mask and not keep_lash:
                pixels[overlay[0], overlay[1]] = (0, 0, 0, 0)
            elif keep_lash and liner_color is not None:
                pixels[overlay[0], overlay[1]] = liner_color
    if eyes_over_bangs:
        for x, y in template.features:
            coordinate = (x, y + vertical_shift)
            if EYE_SEARCH_BOX[1] <= coordinate[1] < EYE_SEARCH_BOX[3]:
                overlay = (coordinate[0] + overlay_offset, coordinate[1])
                keep_lash = preserve_hat_layer_lashes and probable_hat_lash(original_pixels[overlay[0], overlay[1]])
                if not keep_lash:
                    pixels[overlay[0], overlay[1]] = (0, 0, 0, 0)
                elif liner_color is not None:
                    pixels[overlay[0], overlay[1]] = liner_color
    return result


def style_skin(
    image: Image.Image,
    target_hair_color: RGB,
    tolerance: float = 42.0,
    face_template: FaceTemplate | None = None,
    match_reference_skin_tone: bool = False,
    target_skin_color: RGB | None = None,
    skin_tolerance: float = 24.0,
    include_body_hair: bool = True,
    eyes_over_bangs: bool = True,
    target_outfit_color: RGB | None = None,
    target_accessory_color: RGB | None = None,
    preserve_hat_layer_lashes: bool = True,
) -> tuple[Image.Image, set[tuple[int, int]], bool]:
    normalized, was_normalized = normalize_skin(image)
    original_hair_mask = detect_hair_mask(normalized, tolerance)
    # Establish skin from the head-only hair guess before torso/shoulder
    # tracing. If the body tracer makes a mistake, this independent mask can
    # still reclaim the anatomical pixel instead of inheriting the mistake.
    anatomical_skin_mask = detect_skin_mask(normalized, original_hair_mask, skin_tolerance)
    body_hair_mask = detect_body_hair_mask(normalized, tolerance) if include_body_hair else set()
    combined_hair_mask = original_hair_mask | body_hair_mask
    skin_mask = detect_skin_mask(normalized, combined_hair_mask, skin_tolerance) | anatomical_skin_mask
    accessory_mask = detect_hair_accessory_mask(
        normalized,
        original_hair_mask,
        body_hair_mask,
        skin_mask,
    )
    effective_head_hair_mask = original_hair_mask - skin_mask - accessory_mask
    effective_hair_mask = combined_hair_mask - skin_mask - accessory_mask
    outfit_mask = detect_outfit_mask(normalized, effective_hair_mask, skin_mask, accessory_mask)
    if target_skin_color is not None:
        base, _skin_mask = recolor_skin_tone(
            normalized,
            target_skin_color,
            effective_hair_mask,
            skin_tolerance,
            skin_mask,
        )
    else:
        base = normalized
    styled, _mask = recolor_hair(
        base,
        target_hair_color,
        tolerance,
        effective_hair_mask,
        effective_head_hair_mask,
    )
    if target_outfit_color is not None:
        styled, _outfit_mask = recolor_hair(
            styled,
            target_outfit_color,
            tolerance,
            outfit_mask,
            outfit_mask,
            colorize_neutrals=True,
            neutral_saturation_floor=0.68,
        )
    if target_accessory_color is not None:
        styled, _accessory_mask = recolor_hair(
            styled,
            target_accessory_color,
            tolerance,
            accessory_mask,
            accessory_mask,
            colorize_neutrals=True,
        )
    if face_template is not None:
        styled = apply_face_template(
            styled,
            normalized,
            face_template,
            effective_head_hair_mask,
            match_reference_skin_tone,
            target_skin_color,
            eyes_over_bangs,
            preserve_hat_layer_lashes,
        )
    return styled, effective_hair_mask, was_normalized


def render_front_face(image: Image.Image, scale: int = 16) -> Image.Image:
    """Render the front head with its overlay for a crisp GUI preview."""

    normalized, _ = normalize_skin(image)
    face = normalized.crop(FACE_FRONT)
    overlay = normalized.crop(HAT_FRONT)
    face.alpha_composite(overlay)
    return face.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST)


def render_player_view(
    image: Image.Image,
    scale: int = 4,
    back: bool = False,
    slim: bool = True,
) -> Image.Image:
    """Render a crisp standing Minecraft player from a 64x64 skin texture."""

    normalized, _ = normalize_skin(image)
    arm_width = 3 if slim else 4
    body_width = arm_width * 2 + 8
    body = Image.new("RGBA", (body_width, 32), (0, 0, 0, 0))
    body_x = arm_width

    def composite(box: tuple[int, int, int, int], position: tuple[int, int]) -> None:
        layer = normalized.crop(box)
        body.alpha_composite(layer, position)

    if back:
        head = (24, 8, 32, 16)
        head_overlay = (56, 8, 64, 16)
        torso = (32, 20, 40, 32)
        torso_overlay = (32, 36, 40, 48)
        right_leg = (12, 20, 16, 32)
        right_leg_overlay = (12, 36, 16, 48)
        left_leg = (28, 52, 32, 64)
        left_leg_overlay = (12, 52, 16, 64)
        if slim:
            right_arm = (51, 20, 54, 32)
            right_arm_overlay = (51, 36, 54, 48)
            left_arm = (43, 52, 46, 64)
            left_arm_overlay = (59, 52, 62, 64)
        else:
            right_arm = (52, 20, 56, 32)
            right_arm_overlay = (52, 36, 56, 48)
            left_arm = (44, 52, 48, 64)
            left_arm_overlay = (60, 52, 64, 64)

        composite(head, (body_x, 0))
        composite(torso, (body_x, 8))
        composite(left_arm, (0, 8))
        composite(right_arm, (body_x + 8, 8))
        composite(left_leg, (body_x, 20))
        composite(right_leg, (body_x + 4, 20))
        composite(head_overlay, (body_x, 0))
        composite(torso_overlay, (body_x, 8))
        composite(left_arm_overlay, (0, 8))
        composite(right_arm_overlay, (body_x + 8, 8))
        composite(left_leg_overlay, (body_x, 20))
        composite(right_leg_overlay, (body_x + 4, 20))
    else:
        head = (8, 8, 16, 16)
        head_overlay = (40, 8, 48, 16)
        torso = (20, 20, 28, 32)
        torso_overlay = (20, 36, 28, 48)
        right_leg = (4, 20, 8, 32)
        right_leg_overlay = (4, 36, 8, 48)
        left_leg = (20, 52, 24, 64)
        left_leg_overlay = (4, 52, 8, 64)
        if slim:
            right_arm = (44, 20, 47, 32)
            right_arm_overlay = (44, 36, 47, 48)
            left_arm = (36, 52, 39, 64)
            left_arm_overlay = (52, 52, 55, 64)
        else:
            right_arm = (44, 20, 48, 32)
            right_arm_overlay = (44, 36, 48, 48)
            left_arm = (36, 52, 40, 64)
            left_arm_overlay = (52, 52, 56, 64)

        composite(head, (body_x, 0))
        composite(torso, (body_x, 8))
        composite(right_arm, (0, 8))
        composite(left_arm, (body_x + 8, 8))
        composite(right_leg, (body_x, 20))
        composite(left_leg, (body_x + 4, 20))
        composite(head_overlay, (body_x, 0))
        composite(torso_overlay, (body_x, 8))
        composite(right_arm_overlay, (0, 8))
        composite(left_arm_overlay, (body_x + 8, 8))
        composite(right_leg_overlay, (body_x, 20))
        composite(left_leg_overlay, (body_x + 4, 20))

    return body.resize((body.width * scale, body.height * scale), Image.Resampling.NEAREST)


def _layered_texture(
    skin: Image.Image,
    base_box: tuple[int, int, int, int],
    overlay_box: tuple[int, int, int, int],
) -> Image.Image:
    texture = skin.crop(base_box)
    overlay = skin.crop(overlay_box)
    texture.alpha_composite(overlay)
    return texture


def _draw_texture_plane(
    canvas: Image.Image,
    texture: Image.Image,
    origin: tuple[int, int],
    across: tuple[int, int],
    down: tuple[int, int],
    brightness: float = 1.0,
) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    pixels = texture.load()
    for y in range(texture.height):
        for x in range(texture.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            color = (
                min(255, round(red * brightness)),
                min(255, round(green * brightness)),
                min(255, round(blue * brightness)),
                alpha,
            )
            x0 = origin[0] + x * across[0] + y * down[0]
            y0 = origin[1] + x * across[1] + y * down[1]
            polygon = (
                (x0, y0),
                (x0 + across[0], y0 + across[1]),
                (x0 + across[0] + down[0], y0 + across[1] + down[1]),
                (x0 + down[0], y0 + down[1]),
            )
            draw.polygon(polygon, fill=color)
    canvas.alpha_composite(layer)


def _cuboid_face_layers(
    skin: Image.Image,
    base_uv: tuple[int, int],
    overlay_uv: tuple[int, int],
    width: int,
    depth: int,
    height: int,
) -> dict[str, tuple[Image.Image, Image.Image]]:
    """Return separate base/outer faces from a standard Minecraft UV net."""

    def boxes(origin: tuple[int, int]) -> dict[str, tuple[int, int, int, int]]:
        u, v = origin
        return {
            "right": (u, v + depth, u + depth, v + depth + height),
            "front": (u + depth, v + depth, u + depth + width, v + depth + height),
            "left": (u + depth + width, v + depth, u + depth + width + depth, v + depth + height),
            "back": (
                u + depth + width + depth,
                v + depth,
                u + depth + width + depth + width,
                v + depth + height,
            ),
            "top": (u + depth, v, u + depth + width, v + depth),
            "bottom": (u + depth + width, v, u + depth + width + width, v + depth),
        }

    base_boxes = boxes(base_uv)
    overlay_boxes = boxes(overlay_uv)
    return {
        name: (skin.crop(base_boxes[name]), skin.crop(overlay_boxes[name]))
        for name in ("front", "right", "back", "left", "top", "bottom")
    }


def render_player_3d(
    image: Image.Image,
    scale: int = 4,
    slim: bool = True,
    yaw_degrees: float = 25.0,
    show_outer_layers: bool = True,
) -> Image.Image:
    """Render a continuously rotatable, layered Minecraft player in software 3D."""

    normalized, _ = normalize_skin(image)
    scale = max(2, int(scale))
    yaw = math.radians(float(yaw_degrees) % 360.0)
    pitch = math.radians(11.0)
    yaw_cos, yaw_sin = math.cos(yaw), math.sin(yaw)
    pitch_cos, pitch_sin = math.cos(pitch), math.sin(pitch)
    canvas = Image.new("RGBA", (30 * scale, 38 * scale), (0, 0, 0, 0))
    center_x = canvas.width / 2
    floor_y = 35 * scale
    quads: list[tuple[float, tuple[tuple[int, int], ...], RGBA]] = []

    normals = {
        "front": (0.0, 0.0, 1.0),
        "back": (0.0, 0.0, -1.0),
        "right": (1.0, 0.0, 0.0),
        "left": (-1.0, 0.0, 0.0),
        "top": (0.0, 1.0, 0.0),
        "bottom": (0.0, -1.0, 0.0),
    }
    lighting = {"front": 1.00, "back": 0.94, "right": 0.88, "left": 0.90, "top": 1.06, "bottom": 0.78}

    def camera_point(point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        rotated_x = x * yaw_cos + z * yaw_sin
        rotated_z = -x * yaw_sin + z * yaw_cos
        camera_y = y * pitch_cos - rotated_z * pitch_sin
        depth = y * pitch_sin + rotated_z * pitch_cos
        return center_x + rotated_x * scale, floor_y - camera_y * scale, depth

    def normal_depth(normal: tuple[float, float, float]) -> float:
        x, y, z = normal
        rotated_z = -x * yaw_sin + z * yaw_cos
        return y * pitch_sin + rotated_z * pitch_cos

    def surface_point(
        face: str,
        u: float,
        v: float,
        center: tuple[float, float, float],
        dimensions: tuple[float, float, float],
        expansion: float,
    ) -> tuple[float, float, float]:
        center_part_x, center_part_y, center_part_z = center
        width, height, depth = dimensions
        half_width = width / 2 + expansion
        half_height = height / 2 + expansion
        half_depth = depth / 2 + expansion
        horizontal = -half_width + u * half_width * 2
        vertical = half_height - v * half_height * 2
        receding = half_depth - u * half_depth * 2
        if face == "front":
            return center_part_x + horizontal, center_part_y + vertical, center_part_z + half_depth
        if face == "back":
            return center_part_x - horizontal, center_part_y + vertical, center_part_z - half_depth
        if face == "right":
            return center_part_x + half_width, center_part_y + vertical, center_part_z + receding
        if face == "left":
            return center_part_x - half_width, center_part_y + vertical, center_part_z - receding
        if face == "top":
            return center_part_x + horizontal, center_part_y + half_height, center_part_z + (half_depth - v * half_depth * 2)
        return center_part_x + horizontal, center_part_y - half_height, center_part_z - (half_depth - v * half_depth * 2)

    def add_face(
        face: str,
        texture: Image.Image,
        center: tuple[float, float, float],
        dimensions: tuple[float, float, float],
        expansion: float,
    ) -> None:
        if normal_depth(normals[face]) <= 0.001:
            return
        pixels = texture.load()
        for pixel_y in range(texture.height):
            for pixel_x in range(texture.width):
                red, green, blue, alpha = pixels[pixel_x, pixel_y]
                if alpha == 0:
                    continue
                u0 = pixel_x / texture.width
                u1 = (pixel_x + 1) / texture.width
                v0 = pixel_y / texture.height
                v1 = (pixel_y + 1) / texture.height
                vertices = (
                    surface_point(face, u0, v0, center, dimensions, expansion),
                    surface_point(face, u1, v0, center, dimensions, expansion),
                    surface_point(face, u1, v1, center, dimensions, expansion),
                    surface_point(face, u0, v1, center, dimensions, expansion),
                )
                projected = tuple(camera_point(vertex) for vertex in vertices)
                polygon = tuple((round(x), round(y)) for x, y, _depth in projected)
                average_depth = sum(depth_value for _x, _y, depth_value in projected) / 4
                brightness = lighting[face]
                color = (
                    min(255, round(red * brightness)),
                    min(255, round(green * brightness)),
                    min(255, round(blue * brightness)),
                    alpha,
                )
                quads.append((average_depth, polygon, color))

    arm_width = 3 if slim else 4
    parts = (
        (_cuboid_face_layers(normalized, (0, 0), (32, 0), 8, 8, 8), (0.0, 28.0, 0.0), (8.0, 8.0, 8.0), 0.50),
        (_cuboid_face_layers(normalized, (16, 16), (16, 32), 8, 4, 12), (0.0, 18.0, 0.0), (8.0, 12.0, 4.0), 0.25),
        (
            _cuboid_face_layers(normalized, (40, 16), (40, 32), arm_width, 4, 12),
            (-(4.0 + arm_width / 2), 18.0, 0.0),
            (float(arm_width), 12.0, 4.0),
            0.25,
        ),
        (
            _cuboid_face_layers(normalized, (32, 48), (48, 48), arm_width, 4, 12),
            (4.0 + arm_width / 2, 18.0, 0.0),
            (float(arm_width), 12.0, 4.0),
            0.25,
        ),
        (_cuboid_face_layers(normalized, (0, 16), (0, 32), 4, 4, 12), (-2.0, 6.0, 0.0), (4.0, 12.0, 4.0), 0.25),
        (_cuboid_face_layers(normalized, (16, 48), (0, 48), 4, 4, 12), (2.0, 6.0, 0.0), (4.0, 12.0, 4.0), 0.25),
    )
    for faces, center, dimensions, outer_expansion in parts:
        for face, (base_texture, outer_texture) in faces.items():
            add_face(face, base_texture, center, dimensions, 0.0)
            if show_outer_layers:
                add_face(face, outer_texture, center, dimensions, outer_expansion)

    draw = ImageDraw.Draw(canvas, "RGBA")
    for _depth, polygon, color in sorted(quads, key=lambda item: item[0]):
        draw.polygon(polygon, fill=color)

    bounds = canvas.getbbox()
    if bounds is None:
        return canvas
    margin = max(2, scale)
    left = max(0, bounds[0] - margin)
    top = max(0, bounds[1] - margin)
    right = min(canvas.width, bounds[2] + margin)
    bottom = min(canvas.height, bounds[3] + margin)
    return canvas.crop((left, top, right, bottom))


def generate_folder(
    input_folder: Path,
    output_folder: Path,
    target_hair_color: RGB,
    tolerance: float = 42.0,
    reference_skin: Path | None = None,
    standardize_face: bool = True,
    match_reference_skin_tone: bool = False,
    target_skin_color: RGB | None = None,
    skin_tolerance: float = 24.0,
    include_body_hair: bool = True,
    eyes_over_bangs: bool = True,
    target_outfit_color: RGB | None = None,
    target_accessory_color: RGB | None = None,
    preserve_hat_layer_lashes: bool = True,
    progress: Callable[[int, int, Path], None] | None = None,
) -> GenerationResult:
    input_folder = input_folder.expanduser().resolve()
    output_folder = output_folder.expanduser().resolve()
    if input_folder == output_folder:
        raise ValueError("Choose a different output folder so the originals stay untouched")
    if output_folder.is_relative_to(input_folder):
        raise ValueError("Choose an output folder outside the source wardrobe")
    if not input_folder.is_dir():
        raise ValueError(f"Source folder does not exist: {input_folder}")

    template = None
    if standardize_face:
        if reference_skin is None:
            raise ValueError("Choose a reference skin when eye matching is enabled")
        with Image.open(reference_skin) as reference:
            template = make_face_template(reference, tolerance)

    files = sorted(input_folder.rglob("*.png"), key=lambda path: path.name.casefold())
    if not files:
        raise ValueError("No PNG skins were found")

    output_folder.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    staging = output_folder.parent / f".{output_folder.name}-styler-staging-{token}"
    previous = output_folder.parent / f".{output_folder.name}-styler-previous-{token}"
    staging.mkdir(parents=True)
    written = 0
    normalized_count = 0
    skipped: list[str] = []
    total = len(files)
    try:
        for index, source_path in enumerate(files, 1):
            try:
                with Image.open(source_path) as source_image:
                    styled, _mask, was_normalized = style_skin(
                        source_image,
                        target_hair_color,
                        tolerance,
                        template,
                        match_reference_skin_tone,
                        target_skin_color,
                        skin_tolerance,
                        include_body_hair,
                        eyes_over_bangs,
                        target_outfit_color,
                        target_accessory_color,
                        preserve_hat_layer_lashes,
                    )
                relative = source_path.relative_to(input_folder)
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                styled.save(destination, format="PNG", optimize=False)
                written += 1
                normalized_count += int(was_normalized)
            except Exception as exception:  # keep a large batch moving
                skipped.append(f"{source_path.name}: {exception}")
            if progress is not None:
                progress(index, total, source_path)

        manifest = staging / "DAILY-DRESS-STYLING.txt"
        manifest.write_text(
            "Daily Dress styled wardrobe\n"
            f"Source: {input_folder}\n"
            f"Target hair hue: #{target_hair_color[0]:02X}{target_hair_color[1]:02X}{target_hair_color[2]:02X}\n"
            f"Hair tolerance: {tolerance:g}\n"
            f"Skin tone: {('#%02X%02X%02X' % target_skin_color) if target_skin_color else 'unchanged'}\n"
            f"Skin tolerance: {skin_tolerance:g}\n"
            f"Outfit palette: {('#%02X%02X%02X' % target_outfit_color) if target_outfit_color else 'unchanged'}\n"
            f"Hair-accessory palette: {('#%02X%02X%02X' % target_accessory_color) if target_accessory_color else 'unchanged'}\n"
            f"Eye reference: {reference_skin if standardize_face else 'disabled'}\n"
            f"Eyes and liner over bangs: {eyes_over_bangs if standardize_face else 'disabled'}\n"
            f"Preserve existing hat-layer lashes: {preserve_hat_layer_lashes if standardize_face else 'disabled'}\n"
            f"Match reference skin tone: {match_reference_skin_tone}\n"
            f"Written: {written}; normalized from HD: {normalized_count}; skipped: {len(skipped)}\n",
            encoding="utf-8",
        )

        if output_folder.exists():
            output_folder.rename(previous)
        try:
            staging.rename(output_folder)
        except Exception:
            if previous.exists() and not output_folder.exists():
                previous.rename(output_folder)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return GenerationResult(written, normalized_count, tuple(skipped))


def install_generated_wardrobe(generated_folder: Path, target_folder: Path) -> InstallationResult:
    """Atomically replace a Daily Dress sync outbox after making a backup."""

    generated_folder = generated_folder.expanduser().resolve()
    target_folder = target_folder.expanduser().resolve()
    if not generated_folder.is_dir():
        raise ValueError(f"Styled wardrobe does not exist: {generated_folder}")
    if generated_folder == target_folder:
        raise ValueError("The styled output and live wardrobe must be different folders")

    png_files = sorted(generated_folder.rglob("*.png"), key=lambda path: str(path).casefold())
    if not png_files:
        raise ValueError("The styled output does not contain any PNG skins")
    for path in png_files:
        with Image.open(path) as image:
            if image.size != (64, 64):
                raise ValueError(f"{path.name} is {image.width}x{image.height}; live skins must be 64x64")

    target_folder.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    staging = target_folder.parent / f".{target_folder.name}-styler-staging-{token}"
    previous = target_folder.parent / f".{target_folder.name}-styler-previous-{token}"
    backup: Path | None = None

    try:
        staging.mkdir(parents=True)
        for source_path in png_files:
            relative = source_path.relative_to(generated_folder)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)

        manifest = generated_folder / "DAILY-DRESS-STYLING.txt"
        if manifest.is_file():
            shutil.copy2(manifest, staging / manifest.name)
        (staging / "DAILY DRESS SYNC OUTBOX.txt").write_text(
            "DAILY DRESS - PERSONAL SYNC OUTBOX\n"
            "===================================\n\n"
            "This local outbox was prepared by Daily Dress Skin Styler.\n"
            "The master collection is whichever folder is selected as Source wardrobe\n"
            "in the Styler. Its name and location can be different for every person.\n\n"
            "Use Generate + prepare sync after changing that master folder.\n"
            "When this client joins Roses, Daily Dress securely uploads the outbox to\n"
            "the separate server wardrobe belonging to the signed-in Minecraft account.\n",
            encoding="utf-8",
        )

        if target_folder.exists():
            config_root = next(
                (parent for parent in target_folder.parents if parent.name.casefold() == "daily-dress"),
                target_folder.parent,
            )
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup = config_root / "styler-backups" / timestamp / target_folder.name
            if backup.exists():
                backup = backup.with_name(f"{backup.name}-{token[:8]}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target_folder, backup)
            target_folder.rename(previous)

        try:
            staging.rename(target_folder)
        except Exception:
            if previous.exists() and not target_folder.exists():
                previous.rename(target_folder)
            raise

        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return InstallationResult(target_folder, backup, len(png_files))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructively style a Minecraft skin wardrobe")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hair", required=True, help="Target hair color, for example #9C5FA8")
    parser.add_argument("--tolerance", type=float, default=42.0)
    parser.add_argument("--skin-tone", help="Optional exposed-skin target, for example #C58C70")
    parser.add_argument("--outfit", help="Optional outfit palette target, for example #6F86C9")
    parser.add_argument("--hair-accessory", help="Optional hair-accessory palette target, for example #D86AA5")
    parser.add_argument("--skin-tolerance", type=float, default=24.0)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--no-face", action="store_true", help="Do not standardize eye features")
    parser.add_argument(
        "--eyes-under-bangs",
        action="store_true",
        help="Keep destination bangs in front of matched eyes and eyeliner",
    )
    parser.add_argument(
        "--replace-hat-lashes",
        action="store_true",
        help="Clear existing dark hat-layer lash pixels where the designed eyes are applied",
    )
    parser.add_argument("--match-skin-tone", action="store_true")
    args = parser.parse_args()
    result = generate_folder(
        args.input,
        args.output,
        parse_hex_color(args.hair),
        tolerance=args.tolerance,
        reference_skin=args.reference,
        standardize_face=not args.no_face,
        match_reference_skin_tone=args.match_skin_tone,
        target_skin_color=parse_hex_color(args.skin_tone) if args.skin_tone else None,
        skin_tolerance=args.skin_tolerance,
        eyes_over_bangs=not args.eyes_under_bangs,
        target_outfit_color=parse_hex_color(args.outfit) if args.outfit else None,
        target_accessory_color=parse_hex_color(args.hair_accessory) if args.hair_accessory else None,
        preserve_hat_layer_lashes=not args.replace_hat_lashes,
        progress=lambda current, total, path: print(f"[{current}/{total}] {path.name}"),
    )
    print(f"Wrote {result.written} skins; normalized {result.normalized}; skipped {len(result.skipped)}")
    for skipped in result.skipped:
        print("SKIPPED", skipped)
    return 0 if not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(_main())
