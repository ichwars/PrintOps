"""Unit tests for Obico detection smoothing math."""

import pytest

from backend.app.services.obico_smoothing import (
    BASE_HIGH,
    BASE_LOW,
    ESCALATING_FACTOR,
    WARMUP_FRAMES,
    Baseline,
    PrintState,
    Reading,
    classify,
    score_from_detections,
    thresholds,
    triggers_action,
)


class TestThresholds:
    def test_medium_matches_base(self):
        low, high = thresholds("medium")
        assert low == pytest.approx(BASE_LOW)
        assert high == pytest.approx(BASE_HIGH)

    def test_low_sensitivity_is_stricter(self):
        low, high = thresholds("low")
        assert low > BASE_LOW
        assert high > BASE_HIGH

    def test_high_sensitivity_is_looser(self):
        low, high = thresholds("high")
        assert low < BASE_LOW
        assert high < BASE_HIGH

    def test_unknown_falls_back_to_medium(self):
        assert thresholds("bogus") == thresholds("medium")


class TestScoreFromDetections:
    def test_empty(self):
        assert score_from_detections([]) == 0.0
        assert score_from_detections(None) is None

    def test_sums_confidences(self):
        dets = [["failure", 0.3, [0, 0, 10, 10]], ["failure", 0.5, [0, 0, 10, 10]]]
        assert score_from_detections(dets) == pytest.approx(0.8)

    def test_ignores_malformed(self):
        dets = [["failure", 0.4, []], ["bad"], ["failure", "nan", []]]
        assert score_from_detections(dets) == pytest.approx(0.4)


class TestPrintState:
    def test_warmup_never_triggers(self):
        state = PrintState()
        for index in range(WARMUP_FRAMES):
            reading = state.update(2.0 if index % 2 else 0.0)
            assert reading.warmup
            assert classify(reading, "medium") == "safe"

    def test_static_camera_pattern_is_background_across_prints(self):
        baseline = Baseline()
        first = PrintState(baseline=baseline)
        for _ in range(WARMUP_FRAMES + 100):
            first.update(0.8)
        second = PrintState(baseline=baseline)
        for _ in range(WARMUP_FRAMES + 100):
            second.update(0.8)
        assert second.last.score == pytest.approx(0)
        assert classify(second.last, "medium") == "safe"

    def test_sustained_rise_above_background_reaches_the_pause_level(self):
        state = PrintState()
        for _ in range(WARMUP_FRAMES + 500):
            state.update(0.1)
        for _ in range(40):
            reading = state.update(2.0)
        assert classify(reading, "medium") == "failure"

    def test_isolated_spike_stays_below_the_alert_level(self):
        state = PrintState()
        for _ in range(WARMUP_FRAMES + 50):
            state.update(0.0)
        assert classify(state.update(1.0), "medium") == "safe"


class TestClassify:
    def test_warning_depends_on_recent_baseline(self):
        score = (BASE_LOW + BASE_HIGH) / 2
        assert classify(Reading(score, 0.0, False), "medium") == "warning"
        assert classify(Reading(score, 0.5, False), "medium") == "safe"

    def test_pause_needs_a_clearer_signal_than_notification(self):
        assert classify(Reading(BASE_HIGH + 0.01, 0.2, False), "medium") == "warning"
        assert classify(Reading(BASE_HIGH * ESCALATING_FACTOR + 0.01, 0.2, False), "medium") == "failure"
        assert triggers_action("warning", "notify")
        assert not triggers_action("warning", "pause")
        assert not triggers_action("warning", "pause_and_off")
        assert triggers_action("failure", "pause_and_off")
