"""Load and validate the simulator configuration (YAML).

The configuration is kept as a nested dict (it is copied verbatim next to every
generated dataset), with validation of the parts the generator relies on.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PRIMARY_SCENARIOS = (
    "NORMAL",
    "GRADUAL_WARMING",
    "HIGH_EXCURSION",
    "LOW_EXCURSION",
    "SENSOR_SPIKE",
    "SENSOR_BIAS_DRIFT",
    "MISSING_READINGS",
    "OCEAN_COVERAGE_GAP",
    "DOOR_OPENING",
)
AMBIENT_PROFILES = ("TEMPERATE", "HOT", "COLD", "VARIABLE")
PARTITIONS = ("train", "validation", "test")


class ConfigError(ValueError):
    """The configuration file is invalid."""


@dataclass(frozen=True)
class SimConfig:
    raw: dict[str, Any]
    path: Path
    file_bytes: bytes

    # ---- convenient accessors -------------------------------------------------
    @property
    def config_version(self) -> str:
        return str(self.raw["config_version"])

    @property
    def dataset(self) -> dict[str, Any]:
        return self.raw["dataset"]

    @property
    def sim(self) -> dict[str, Any]:
        return self.raw["simulation"]

    def section(self, name: str) -> dict[str, Any]:
        return self.raw[name]

    def scenario(self, name: str) -> dict[str, Any]:
        return self.raw["scenarios"][name]

    @property
    def departure_window(self) -> tuple[datetime, datetime]:
        w = self.dataset["departure_window"]
        return parse_utc(w["from"]), parse_utc(w["to"])


def parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ConfigError(f"Timestamp {value!r} must be UTC and end with 'Z'")
    return datetime.fromisoformat(value[:-1]).replace(tzinfo=UTC)


def _require(raw: dict[str, Any], dotted: str) -> Any:
    node: Any = raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"Missing configuration key: {dotted}")
        node = node[part]
    return node


def _check_range(raw: dict[str, Any], dotted: str) -> None:
    value = _require(raw, dotted)
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)):
        raise ConfigError(f"{dotted} must be a [min, max] pair of numbers")
    if value[0] > value[1]:
        raise ConfigError(f"{dotted}: min {value[0]} is greater than max {value[1]}")


def _check_weights(weights: dict[str, Any], allowed: tuple[str, ...], dotted: str) -> None:
    unknown = set(weights) - set(allowed)
    if unknown:
        raise ConfigError(f"{dotted}: unknown keys {sorted(unknown)}")
    if any(float(w) < 0 for w in weights.values()):
        raise ConfigError(f"{dotted}: weights must be non-negative")
    total = sum(float(w) for w in weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ConfigError(f"{dotted}: weights must sum to 1 (got {total})")


def validate(raw: dict[str, Any]) -> None:
    for key in ("config_version", "dataset.name", "dataset.version", "dataset.journey_count",
                "dataset.id_prefix", "policy.file", "simulation.physics_step_min",
                "simulation.sampling_interval_min", "transmission.upload_interval_min"):
        _require(raw, key)
    if int(raw["dataset"]["journey_count"]) < 1:
        raise ConfigError("dataset.journey_count must be at least 1")
    if int(raw["simulation"]["physics_step_min"]) != 1:
        raise ConfigError("simulation.physics_step_min must be 1 in config v1")
    if int(raw["simulation"]["sampling_interval_min"]) < 1:
        raise ConfigError("simulation.sampling_interval_min must be positive")
    d = _require(raw, "simulation.journey_duration_h")
    if not (0 < d["min"] <= d["mode"] <= d["max"]):
        raise ConfigError("simulation.journey_duration_h must satisfy 0 < min <= mode <= max")
    _check_weights(_require(raw, "scenario_mix"), PRIMARY_SCENARIOS, "scenario_mix")
    _check_weights(_require(raw, "ambient_profiles.weights"), AMBIENT_PROFILES, "ambient_profiles.weights")
    _check_weights(_require(raw, "splits.fractions"), PARTITIONS, "splits.fractions")
    for dotted in (
        "thermal.setpoint_c", "thermal.cooling_coupling_per_min", "thermal.ambient_coupling_per_min",
        "thermal.process_noise_sd_c", "sensor.calibration_bias_c", "sensor.noise_sd_c",
        "battery.start_pct", "battery.drain_pct_per_day", "transmission.network_latency_s",
        "scenarios.HIGH_EXCURSION.reefer_failure_duration_min", "scenarios.LOW_EXCURSION.duration_min",
        "scenarios.OCEAN_COVERAGE_GAP.outage_h", "scenarios.MISSING_READINGS.review_readings",
    ):
        _check_range(raw, dotted)
    start, end = (parse_utc(raw["dataset"]["departure_window"][k]) for k in ("from", "to"))
    if end <= start:
        raise ConfigError("dataset.departure_window.to must be after from")


def load_config(path: Path) -> SimConfig:
    file_bytes = path.read_bytes()
    raw = yaml.safe_load(file_bytes.decode("utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} does not contain a mapping")
    validate(raw)
    return SimConfig(raw=raw, path=path, file_bytes=file_bytes)


def find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the directory that contains ``backend/app/seed``."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "backend" / "app" / "seed").is_dir() and (candidate / "data").is_dir():
            return candidate
    raise ConfigError(f"Cannot find the repository root above {start}. Pass --repo-root.")


# ---------------------------------------------------------------- sampling helpers

def uniform(rng: random.Random, bounds: list[float]) -> float:
    return rng.uniform(float(bounds[0]), float(bounds[1]))


def randint(rng: random.Random, bounds: list[int]) -> int:
    return rng.randint(int(bounds[0]), int(bounds[1]))


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[float(weights[k]) for k in keys], k=1)[0]


def largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Integer counts summing to ``total`` that follow ``weights`` (ties: config order)."""
    keys = list(weights)
    exact = {k: float(weights[k]) * total for k in keys}
    counts = {k: int(exact[k]) for k in keys}
    remaining = total - sum(counts.values())
    order = sorted(keys, key=lambda k: (-(exact[k] - counts[k]), keys.index(k)))
    for k in order[:remaining]:
        counts[k] += 1
    return counts
