"""Versioned, deterministic feature extraction from observed sensor records only."""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta
from typing import Any

from coldchain_ml.windows import Reading, causal_readings, window_start

WINDOW_MINUTES = 60
STRIDE_MINUTES = 5
SAMPLE_MINUTES = 5
MINIMUM_READINGS = 6
FEATURE_NAMES = (
    "temperature_mean_c", "temperature_min_c", "temperature_max_c", "temperature_std_c",
    "temperature_last_c", "temperature_range_c", "temperature_slope_c_per_hour",
    "largest_step_c", "observed_above_max_sample_minutes", "observed_below_min_sample_minutes",
    "longest_out_of_range_run_minutes", "observed_reading_count", "missing_fraction",
    "coverage_ratio", "longest_observed_gap_minutes", "spike_score_c",
    "ambient_mean_c", "product_minus_ambient_mean_c", "door_open_fraction",
    "battery_min_pct", "battery_slope_pct_per_hour", "latest_received_age_minutes",
    "ambient_observation_count", "door_observation_count", "battery_observation_count",
)


def extract_features(
    readings: list[Reading], as_of: datetime, *, min_temp_c: float = 2.0, max_temp_c: float = 8.0,
) -> dict[str, float]:
    """Return the fixed feature schema for [as_of - 60m, as_of], without interpolation.

    Expected coverage is 13 five-minute slots, including both endpoints. A missing slot contributes
    to missing_fraction and never contributes an assumed in-range temperature.
    """
    start = window_start(as_of, WINDOW_MINUTES)
    rows = [r for r in causal_readings(readings, as_of) if start <= r.event_at <= as_of]
    values = [float(r.temperature_c) for r in rows]
    n = len(values)
    expected = WINDOW_MINUTES // SAMPLE_MINUTES + 1
    diffs = [abs(values[i] - values[i - 1]) for i in range(1, n)]
    elapsed_hours = max((rows[-1].event_at - rows[0].event_at).total_seconds() / 3600, 1 / 12) if n > 1 else 1 / 12
    slope = ((values[-1] - values[0]) / elapsed_hours) if n > 1 else 0.0
    outside = [v > max_temp_c or v < min_temp_c for v in values]
    longest_run = 0.0
    run_start: datetime | None = None
    run_direction: int | None = None
    for index, row in enumerate(rows):
        direction = 1 if row.temperature_c > max_temp_c else (-1 if row.temperature_c < min_temp_c else 0)
        continuous = index > 0 and row.event_at - rows[index - 1].event_at <= timedelta(seconds=450)
        if direction and continuous and direction == run_direction:
            pass
        else:
            if run_start is not None:
                longest_run = max(longest_run, (rows[index - 1].event_at - run_start).total_seconds() / 60)
            run_start = row.event_at if direction else None
        run_direction = direction
    if run_start is not None:
        longest_run = max(longest_run, (rows[-1].event_at - run_start).total_seconds() / 60)
    gaps = [max(0.0, (rows[i].event_at - rows[i - 1].event_at).total_seconds() / 60 - SAMPLE_MINUTES)
            for i in range(1, n)]
    # A robust local residual: largest deviation from a trailing three-point median.
    spike_score = 0.0
    for i, value in enumerate(values):
        neighborhood = values[max(0, i - 1): min(n, i + 2)]
        spike_score = max(spike_score, abs(value - statistics.median(neighborhood)))
    context_rows = [r for r in rows if r.context_received_at is None or r.context_received_at <= as_of]
    ambients = [r.ambient_temperature_c for r in context_rows if r.ambient_temperature_c is not None]
    paired_deltas = [r.temperature_c - r.ambient_temperature_c for r in context_rows
                     if r.ambient_temperature_c is not None]
    doors = [r.door_open for r in context_rows if r.door_open is not None]
    batteries = [(r.event_at, r.battery_level_pct) for r in context_rows if r.battery_level_pct is not None]
    battery_slope = 0.0
    if len(batteries) > 1:
        hrs = max((batteries[-1][0] - batteries[0][0]).total_seconds() / 3600, 1 / 12)
        battery_slope = (float(batteries[-1][1]) - float(batteries[0][1])) / hrs
    out = {
        "temperature_mean_c": statistics.fmean(values) if n else 0.0,
        "temperature_min_c": min(values) if n else 0.0,
        "temperature_max_c": max(values) if n else 0.0,
        "temperature_std_c": statistics.pstdev(values) if n else 0.0,
        "temperature_last_c": values[-1] if n else 0.0,
        "temperature_range_c": max(values) - min(values) if n else 0.0,
        "temperature_slope_c_per_hour": slope,
        "largest_step_c": max(diffs, default=0.0),
        "observed_above_max_sample_minutes": min(WINDOW_MINUTES, sum(1 for v in values if v > max_temp_c) * SAMPLE_MINUTES),
        "observed_below_min_sample_minutes": min(WINDOW_MINUTES, sum(1 for v in values if v < min_temp_c) * SAMPLE_MINUTES),
        "longest_out_of_range_run_minutes": longest_run,
        "observed_reading_count": float(n),
        "missing_fraction": max(0.0, 1.0 - n / expected),
        "coverage_ratio": min(1.0, n / expected),
        "longest_observed_gap_minutes": max(gaps, default=0.0),
        "spike_score_c": spike_score,
        "ambient_mean_c": statistics.fmean(ambients) if ambients else 0.0,
        "product_minus_ambient_mean_c": statistics.fmean(paired_deltas) if paired_deltas else 0.0,
        "door_open_fraction": sum(1 for v in doors if v) / len(doors) if doors else 0.0,
        "battery_min_pct": min((float(v) for _, v in batteries), default=0.0),
        "battery_slope_pct_per_hour": battery_slope,
        "latest_received_age_minutes": max(0.0, (as_of - rows[-1].received_at).total_seconds() / 60) if n else float(WINDOW_MINUTES),
        "ambient_observation_count": float(len(ambients)),
        "door_observation_count": float(len(doors)),
        "battery_observation_count": float(len(batteries)),
    }
    assert tuple(out) == FEATURE_NAMES
    return out


def has_sufficient_evidence(features: dict[str, float]) -> bool:
    """Fixed abstention rule: require six observations and 40% of the expected slots."""
    return features["observed_reading_count"] >= MINIMUM_READINGS and features["coverage_ratio"] >= 0.4


def validate_feature_row(row: dict[str, Any]) -> None:
    if tuple(row) != FEATURE_NAMES or any(not math.isfinite(float(v)) for v in row.values()):
        raise ValueError("Feature schema mismatch or non-finite feature value")
