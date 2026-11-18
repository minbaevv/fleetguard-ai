from collections.abc import Callable

import numpy as np
import pytest
from PIL import Image

from app.services.quality import (
    FLAG_BLURRY,
    FLAG_LOW_RESOLUTION,
    FLAG_TOO_BRIGHT,
    FLAG_TOO_DARK,
    QualityThresholds,
    analyze_quality,
)

THRESHOLDS = QualityThresholds(
    min_width=640,
    min_height=480,
    blur_threshold=60.0,
    min_brightness=40.0,
    max_brightness=215.0,
)


def noise_image(width: int = 800, height: int = 600) -> Image.Image:
    # Случайный шум даёт максимальную дисперсию Лапласа — эталон «резкого» фото.
    rng = np.random.default_rng(42)
    pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    return Image.fromarray(pixels, mode="RGB")


def solid_image(color: tuple[int, int, int], width: int = 800, height: int = 600) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def test_sharp_photo_passes_all_checks() -> None:
    result = analyze_quality(noise_image(), THRESHOLDS)

    assert result.ok is True
    assert result.flags == ()
    assert result.score >= 0.9
    assert result.sharpness >= THRESHOLDS.blur_threshold
    assert result.width == 800
    assert result.height == 600


def test_featureless_photo_is_blurry() -> None:
    result = analyze_quality(solid_image((128, 128, 128)), THRESHOLDS)

    assert result.ok is False
    assert result.flags == (FLAG_BLURRY,)
    assert result.score < 0.6


def test_dark_photo_is_flagged() -> None:
    result = analyze_quality(solid_image((5, 5, 5)), THRESHOLDS)

    assert FLAG_TOO_DARK in result.flags
    assert FLAG_TOO_BRIGHT not in result.flags
    assert result.brightness < THRESHOLDS.min_brightness


def test_overexposed_photo_is_flagged() -> None:
    result = analyze_quality(solid_image((250, 250, 250)), THRESHOLDS)

    assert FLAG_TOO_BRIGHT in result.flags
    assert FLAG_TOO_DARK not in result.flags
    assert result.brightness > THRESHOLDS.max_brightness


def test_small_photo_is_flagged() -> None:
    result = analyze_quality(solid_image((128, 128, 128), width=320, height=240), THRESHOLDS)

    assert FLAG_LOW_RESOLUTION in result.flags
    assert result.width == 320
    assert result.height == 240


def test_blur_lowers_score_of_identical_scene() -> None:
    sharp = analyze_quality(noise_image(), THRESHOLDS)
    blurred = analyze_quality(solid_image((128, 128, 128)), THRESHOLDS)

    assert blurred.score < sharp.score


@pytest.mark.parametrize(
    "factory",
    [
        lambda: noise_image(),
        lambda: solid_image((0, 0, 0)),
        lambda: solid_image((255, 255, 255)),
        lambda: solid_image((128, 128, 128), width=64, height=64),
    ],
    ids=["sharp", "black", "white", "tiny"],
)
def test_score_is_always_within_unit_range(factory: Callable[[], Image.Image]) -> None:
    result = analyze_quality(factory(), THRESHOLDS)

    assert 0.0 <= result.score <= 1.0


def test_zero_blur_threshold_disables_blur_flag() -> None:
    thresholds = QualityThresholds(
        min_width=640,
        min_height=480,
        blur_threshold=0.0,
        min_brightness=40.0,
        max_brightness=215.0,
    )

    result = analyze_quality(solid_image((128, 128, 128)), thresholds)

    assert FLAG_BLURRY not in result.flags


def test_analysis_does_not_mutate_source_image() -> None:
    image = noise_image()
    before = np.asarray(image).copy()

    analyze_quality(image, THRESHOLDS)

    assert np.array_equal(np.asarray(image), before)
