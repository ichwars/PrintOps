"""Obico frame smoothing with a background baseline per printer.

A running print has its own exponential and short rolling means. The
long rolling mean follows the camera across jobs. Notifying uses the
alert threshold. Pausing or cutting power requires the escalation level.
"""

import math
from collections import deque
from dataclasses import dataclass, field

EWM_SPAN = 12
EWM_ALPHA = 2.0 / (EWM_SPAN + 1)
ROLLING_SHORT = 310
ROLLING_LONG = 7200
WARMUP_FRAMES = 30
ESCALATING_FACTOR = 1.75
_SHORT_RISE_MULTIPLIER = 3.8

# Base thresholds; sensitivity multipliers adjust them
BASE_LOW = 0.38
BASE_HIGH = 0.78

SENSITIVITY_MULT = {
    "low": 1.25,  # harder to trigger — higher thresholds
    "medium": 1.0,
    "high": 0.75,  # easier to trigger — lower thresholds
}


def thresholds(sensitivity: str) -> tuple[float, float]:
    mult = SENSITIVITY_MULT.get(sensitivity, 1.0)
    return BASE_LOW * mult, BASE_HIGH * mult


class _RollingMean:
    def __init__(self, window: int):
        self._values: deque[float] = deque(maxlen=window)
        self._total = 0.0

    def add(self, value: float) -> None:
        if len(self._values) == self._values.maxlen:
            self._total -= self._values[0]
        self._values.append(value)
        self._total += value

    @property
    def mean(self) -> float:
        return self._total / len(self._values) if self._values else 0.0


class Baseline(_RollingMean):
    """The background score accumulated from one printer camera."""

    def __init__(self):
        super().__init__(ROLLING_LONG)


@dataclass(frozen=True)
class Reading:
    score: float = 0.0
    short_rise: float = 0.0
    warmup: bool = True


@dataclass
class PrintState:
    baseline: Baseline = field(default_factory=Baseline)
    frame_count: int = 0
    ewm_mean: float = 0.0
    short: _RollingMean = field(default_factory=lambda: _RollingMean(ROLLING_SHORT))
    last: Reading = field(default_factory=Reading)

    def update(self, current_p: float) -> Reading:
        self.frame_count += 1
        if self.frame_count == 1:
            self.ewm_mean = current_p
        else:
            self.ewm_mean += EWM_ALPHA * (current_p - self.ewm_mean)
        self.short.add(current_p)
        self.baseline.add(current_p)
        background = self.baseline.mean
        self.last = Reading(
            score=self.ewm_mean - background,
            short_rise=self.short.mean - background,
            warmup=self.frame_count <= WARMUP_FRAMES,
        )
        return self.last


def _is_failing(reading: Reading, sensitivity: str, escalation: float) -> bool:
    low, high = thresholds(sensitivity)
    score = reading.score / escalation
    if reading.warmup or score < low:
        return False
    mult = SENSITIVITY_MULT.get(sensitivity, 1.0)
    return score > high or score > reading.short_rise * _SHORT_RISE_MULTIPLIER * mult


def classify(reading: Reading, sensitivity: str) -> str:
    """Return the notification or pause level reached by this reading."""
    if _is_failing(reading, sensitivity, ESCALATING_FACTOR):
        return "failure"
    if _is_failing(reading, sensitivity, 1.0):
        return "warning"
    return "safe"


def triggers_action(verdict: str, action: str) -> bool:
    return verdict == "failure" or (action == "notify" and verdict == "warning")


def score_from_detections(detections: object) -> float | None:
    """Sum finite confidences. A valid empty list is a clear frame."""
    if not isinstance(detections, list):
        return None
    total = 0.0
    valid = not detections
    for detection in detections:
        if not isinstance(detection, (list, tuple)) or len(detection) < 2:
            continue
        confidence = detection[1]
        if isinstance(confidence, bool):
            continue
        try:
            value = float(confidence)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value) and value >= 0:
            valid = True
            total += value
    return total if valid and math.isfinite(total) else None
