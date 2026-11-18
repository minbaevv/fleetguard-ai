"""Оценка качества фото кузова: резкость, яркость и разрешение.

Модуль не зависит от БД и S3: на вход подаётся PIL-изображение с уже исправленной
EXIF-ориентацией. Пороги приходят снаружи, чтобы их можно было настроить под камеры парка.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from PIL import Image

# Резкость меряем на уменьшенной копии: дисперсия Лапласа зависит от разрешения камеры.
ANALYSIS_MAX_SIDE: Final = 640

# Резкость важнее всего: по размытому фото повреждения не распознать.
_SHARPNESS_WEIGHT: Final = 0.5
_BRIGHTNESS_WEIGHT: Final = 0.3
_RESOLUTION_WEIGHT: Final = 0.2

FLAG_LOW_RESOLUTION: Final = "low_resolution"
FLAG_BLURRY: Final = "blurry"
FLAG_TOO_DARK: Final = "too_dark"
FLAG_TOO_BRIGHT: Final = "too_bright"


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    """Границы брака. Значения по умолчанию задаются в `core/config.py`."""

    min_width: int
    min_height: int
    blur_threshold: float
    min_brightness: float
    max_brightness: float


@dataclass(frozen=True, slots=True)
class QualityResult:
    score: float
    flags: tuple[str, ...]
    width: int
    height: int
    # Измеренные значения: нужны для отладки порогов и тестов.
    sharpness: float
    brightness: float

    @property
    def ok(self) -> bool:
        return not self.flags


@dataclass(frozen=True, slots=True)
class _Measurements:
    sharpness: float
    brightness: float


def _measure(image: Image.Image) -> _Measurements:
    # Один проход по уменьшенной серой копии: 50 МП в float64 заняли бы сотни мегабайт.
    grayscale = image.convert("L")
    grayscale.thumbnail((ANALYSIS_MAX_SIDE, ANALYSIS_MAX_SIDE), Image.Resampling.BILINEAR)
    pixels = np.asarray(grayscale, dtype=np.float64)
    if pixels.size == 0:
        return _Measurements(sharpness=0.0, brightness=0.0)

    brightness = float(pixels.mean())
    if min(pixels.shape) < 3:
        # Для картинки меньше 3 пикселей ядро 3×3 не помещается.
        return _Measurements(sharpness=0.0, brightness=brightness)

    laplacian = (
        pixels[:-2, 1:-1]
        + pixels[2:, 1:-1]
        + pixels[1:-1, :-2]
        + pixels[1:-1, 2:]
        - 4.0 * pixels[1:-1, 1:-1]
    )
    return _Measurements(sharpness=float(laplacian.var()), brightness=brightness)


def _sharpness_score(sharpness: float, threshold: float) -> float:
    if threshold <= 0:
        return 1.0
    # Порог — граница брака, а не идеал: вдвое резче порога считаем за максимум.
    return min(1.0, sharpness / (2.0 * threshold))


def _brightness_score(brightness: float, low: float, high: float) -> float:
    if brightness < low:
        return 0.0 if low <= 0 else brightness / low
    if brightness > high:
        return 0.0 if high >= 255 else (255.0 - brightness) / (255.0 - high)
    return 1.0


def _resolution_score(width: int, height: int, min_width: int, min_height: int) -> float:
    return min(1.0, width / min_width, height / min_height)


def analyze_quality(image: Image.Image, thresholds: QualityThresholds) -> QualityResult:
    """Считает оценку 0..1 и список флагов брака для фото."""
    width, height = image.size
    measured = _measure(image)

    flags: list[str] = []
    if width < thresholds.min_width or height < thresholds.min_height:
        flags.append(FLAG_LOW_RESOLUTION)
    if measured.sharpness < thresholds.blur_threshold:
        flags.append(FLAG_BLURRY)
    if measured.brightness < thresholds.min_brightness:
        flags.append(FLAG_TOO_DARK)
    elif measured.brightness > thresholds.max_brightness:
        flags.append(FLAG_TOO_BRIGHT)

    score = (
        _SHARPNESS_WEIGHT * _sharpness_score(measured.sharpness, thresholds.blur_threshold)
        + _BRIGHTNESS_WEIGHT
        * _brightness_score(
            measured.brightness, thresholds.min_brightness, thresholds.max_brightness
        )
        + _RESOLUTION_WEIGHT
        * _resolution_score(width, height, thresholds.min_width, thresholds.min_height)
    )
    return QualityResult(
        score=round(score, 3),
        flags=tuple(flags),
        width=width,
        height=height,
        sharpness=round(measured.sharpness, 2),
        brightness=round(measured.brightness, 2),
    )
