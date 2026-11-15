"""Generate a complete dataset for one seed: files, splits, statistics and manifest."""

import json
import statistics as stats
from collections import Counter
from pathlib import Path
from typing import Any

from coldchain_sim import GENERATOR_NAME, GENERATOR_VERSION, MANIFEST_SCHEMA_VERSION
from coldchain_sim.config import (
    AMBIENT_PROFILES,
    PARTITIONS,
    PRIMARY_SCENARIOS,
    SimConfig,
    find_repo_root,
    largest_remainder,
    load_config,
)
from coldchain_sim.fileio import json_bytes, sha256_hex, write_table
from coldchain_sim.journey import (
    EXCURSION_HIGH,
    EXCURSION_LOW,
    MISSING_DATA,
    TX_BUFFERED,
    TX_RETRIED,
    JourneyResult,
    JourneySpec,
    simulate_journey,
)
from coldchain_sim.policy import Policy, load_policy
from coldchain_sim.rng import derive_seed, make_rng
from coldchain_sim.splits import assign_partitions

SHIPMENT_COLUMNS = ("shipment_id", "sensor_id", "product_id", "policy_code", "policy_version", "origin",
                    "destination", "route_type", "departure_at", "arrival_at", "data_origin", "dataset_id")
UPLOAD_COLUMNS = ("upload_id", "shipment_id", "sensor_id", "received_at", "first_event_at", "last_event_at",
                  "reading_count")
READING_COLUMNS = ("shipment_id", "sensor_id", "event_at", "received_at", "temperature_c", "upload_id")
CONTEXT_COLUMNS = ("shipment_id", "sensor_id", "event_at", "received_at", "door_state", "battery_level_pct",
                   "ambient_temperature_c", "upload_id")
GT_JOURNEY_COLUMNS = (
    "journey_id", "shipment_id", "sensor_id", "journey_seed", "primary_scenario", "scenario_tags",
    "ambient_profile", "route_type", "departure_at", "arrival_at", "duration_min", "setpoint_c",
    "cooling_coupling_per_min", "ambient_coupling_per_min", "process_noise_sd_c", "ambient_mean_start_c",
    "ambient_mean_end_c", "ambient_diurnal_amplitude_c", "sensor_bias_c", "sensor_drift_c_per_day",
    "sensor_drift_start_at", "sensor_noise_sd_c", "has_ambient_probe", "battery_start_pct",
    "battery_drain_pct_per_day", "expected_readings", "observed_readings", "missing_readings",
    "delayed_readings", "max_delay_min", "policy_excursion_count", "true_minutes_above_max",
    "true_minutes_below_min",
)
GT_EVENT_COLUMNS = ("event_id", "journey_id", "event_type", "label_source", "cause", "start_at", "end_at",
                    "duration_min", "attributes")
GT_SLOT_COLUMNS = (
    "journey_id", "slot_at", "true_product_temperature_c", "true_ambient_temperature_c", "door_open_in_interval",
    "true_temperature_state", "in_policy_excursion", "sensor_offset_c", "sensor_noise_c", "sensor_spike_c",
    "observation_status", "missing_cause", "transmission", "delay_s",
)
SPLIT_COLUMNS = ("journey_id", "partition")

OUTPUT_FILES = (
    "README.md", "config.yaml", "manifest.json", "statistics.json",
    "observed/shipments.csv", "observed/uploads.csv.gz", "observed/readings.csv.gz", "observed/context.csv.gz",
    "ground_truth/journeys.csv", "ground_truth/events.csv.gz", "ground_truth/slots.csv.gz",
    "splits/journey_split.csv",
)


class OutputExistsError(FileExistsError):
    """The output directory already contains a dataset."""


def dataset_id_for(cfg: SimConfig, seed: int, journey_count: int) -> str:
    base = f"{cfg.dataset['name']}-v{cfg.dataset['version']}-seed{seed}"
    return base if journey_count == int(cfg.dataset["journey_count"]) else f"{base}-n{journey_count}"


def plan_journeys(cfg: SimConfig, seed: int, journey_count: int) -> list[JourneySpec]:
    """Scenario and ambient quotas, shuffled so the journey index carries no label information."""
    scenario_counts = largest_remainder(journey_count, cfg.raw["scenario_mix"])
    ambient_weights = cfg.section("ambient_profiles")["weights"]
    entries: list[tuple[str, str]] = []
    for scenario in PRIMARY_SCENARIOS:
        n = scenario_counts.get(scenario, 0)
        ambient_counts = largest_remainder(n, ambient_weights)
        ambients = [a for a in AMBIENT_PROFILES for _ in range(ambient_counts.get(a, 0))]
        make_rng(cfg.dataset["name"], seed, "ambient-order", scenario).shuffle(ambients)
        entries.extend((scenario, a) for a in ambients)
    make_rng(cfg.dataset["name"], seed, "assignment").shuffle(entries)
    prefix = cfg.dataset["id_prefix"]
    specs = []
    for index, (scenario, ambient) in enumerate(entries, start=1):
        journey_id = f"{prefix}-S{seed}-J{index:04d}"
        specs.append(JourneySpec(
            index=index,
            journey_id=journey_id,
            shipment_id=journey_id,
            sensor_id=f"{prefix}-S{seed}-L{index:04d}",
            journey_seed=derive_seed(cfg.dataset["name"], seed, "journey", index),
            primary_scenario=scenario,
            ambient_profile=ambient,
        ))
    return specs


def compute_statistics(results: list[JourneyResult], partitions: dict[str, str],
                       policy: Policy) -> dict[str, Any]:
    journeys = [r.gt_journey for r in results]
    events = [e for r in results for e in r.events]
    slots = [s for r in results for s in r.slots]
    durations_h = [j["duration_min"] / 60 for j in journeys]
    by_scenario = Counter(j["primary_scenario"] for j in journeys)
    with_excursion = Counter(j["primary_scenario"] for j in journeys if j["policy_excursion_count"] > 0)
    gap_events = [e for e in events if e["event_type"] == MISSING_DATA]
    policy_events = [e for e in events if e["event_type"] in (EXCURSION_HIGH, EXCURSION_LOW)]
    delays = [int(s["delay_s"]) / 60 for s in slots if s["delay_s"] != ""]
    scen_of = {j["journey_id"]: j["primary_scenario"] for j in journeys}
    amb_of = {j["journey_id"]: j["ambient_profile"] for j in journeys}
    return {
        "note": "Computed from the generated files by coldchain_sim. Synthetic data; values describe the simulator.",
        "journeys": {
            "count": len(journeys),
            "by_primary_scenario": dict(sorted(by_scenario.items())),
            "by_ambient_profile": dict(sorted(Counter(j["ambient_profile"] for j in journeys).items())),
            "by_route_type": dict(sorted(Counter(j["route_type"] for j in journeys).items())),
            "scenario_by_ambient": {
                s: dict(sorted(Counter(j["ambient_profile"] for j in journeys if j["primary_scenario"] == s).items()))
                for s in sorted(by_scenario)
            },
            "duration_h": {"min": round(min(durations_h), 2), "mean": round(stats.fmean(durations_h), 2),
                           "max": round(max(durations_h), 2)},
            "with_policy_excursion_by_primary_scenario": {s: with_excursion.get(s, 0) for s in sorted(by_scenario)},
            "with_policy_excursion_total": sum(with_excursion.values()),
            "secondary_tags": dict(sorted(Counter(t for j in journeys for t in j["scenario_tags"].split(";")[1:]).items())),
        },
        "readings": {
            "expected": len(slots),
            "observed": sum(len(r.readings) for r in results),
            "missing": sum(1 for s in slots if s["observation_status"] == "MISSING"),
            "delayed_retried_upload": sum(1 for s in slots if s["transmission"] == TX_RETRIED),
            "delayed_coverage_gap": sum(1 for s in slots if s["transmission"] == TX_BUFFERED),
            "delay_min": {"median": round(stats.median(delays), 2), "max": round(max(delays), 2)},
            "observed_out_of_range": sum(
                1 for r in results for row in r.readings
                if not policy.min_temp_c <= float(row["temperature_c"]) <= policy.max_temp_c),
        },
        "context": {
            "rows": sum(len(r.context) for r in results),
            "ambient_temperature_null": sum(1 for r in results for c in r.context if c["ambient_temperature_c"] == ""),
            "door_open": sum(1 for r in results for c in r.context if c["door_state"] == "OPEN"),
        },
        "uploads": {
            "count": sum(len(r.uploads) for r in results),
        },
        "slots_true_state": dict(sorted(Counter(s["true_temperature_state"] for s in slots).items())),
        "events": {
            "by_type": dict(sorted(Counter(e["event_type"] for e in events).items())),
            "policy_excursions": {
                "high": sum(1 for e in policy_events if e["event_type"] == EXCURSION_HIGH),
                "low": sum(1 for e in policy_events if e["event_type"] == EXCURSION_LOW),
                "duration_min": {
                    "min": min((e["duration_min"] for e in policy_events), default=0),
                    "median": stats.median([e["duration_min"] for e in policy_events]) if policy_events else 0,
                    "max": max((e["duration_min"] for e in policy_events), default=0),
                },
                "with_missing_readings_inside": sum(
                    1 for e in policy_events if e["attributes"]["missing_readings_in_interval"] > 0),
                "with_delayed_readings_inside": sum(
                    1 for e in policy_events if e["attributes"]["delayed_readings_in_interval"] > 0),
            },
            "missing_data_by_policy_gap_status": dict(sorted(Counter(
                e["attributes"]["policy_gap_status"] for e in gap_events).items())),
            "missing_data_overlapping_policy_excursion": sum(
                1 for e in gap_events if e["attributes"]["overlaps_policy_excursion"]),
        },
        "splits": {
            "by_partition": {p: sum(1 for v in partitions.values() if v == p) for p in PARTITIONS},
            "partition_by_ambient": {p: dict(sorted(Counter(amb_of[j] for j, v in partitions.items() if v == p).items()))
                                     for p in PARTITIONS},
            "partition_by_primary_scenario": {
                p: dict(sorted(Counter(scen_of[j] for j, v in partitions.items() if v == p).items()))
                for p in PARTITIONS},
        },
    }


def _dataset_readme(manifest: dict[str, Any]) -> bytes:
    lines = [
        f"# {manifest['dataset_id']} — SYNTHETIC DATASET",
        "",
        "**All data in this folder is simulated** by the `coldchain_sim` generator for a teaching",
        "prototype. It does not describe real shipments, products, sensors or organizations.",
        "Policy values are teaching values, not regulatory or clinical limits.",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Dataset ID | `{manifest['dataset_id']}` |",
        f"| Dataset version | {manifest['dataset_version']} |",
        f"| Generator | {manifest['generator']['name']} {manifest['generator']['version']} |",
        f"| Configuration version | {manifest['config']['config_version']} |",
        f"| Seed | {manifest['seed']} |",
        f"| Journeys | {manifest['journey_count']} |",
        f"| Policy | {manifest['policy']['policy_code']} v{manifest['policy']['policy_version']} |",
        "| Timezone | UTC (every timestamp ends in `Z`) |",
        "| Units | °C, percent, minutes, seconds (see column names) |",
        "",
        "Folders: `observed/` is what a monitoring system would receive; `ground_truth/` holds the",
        "simulated physical truth and labels and must never be used as model input; `splits/` assigns",
        "each journey to one partition.",
        "",
        "Field definitions, label rules and limitations: `data/dictionary/data-dictionary.md`.",
        "Checksums: `manifest.json`. Statistics: `statistics.json`.",
        "",
        f"Regenerate: `{manifest['regenerate_command']}`",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def generate_dataset(config_path: Path, seed: int, out_dir: Path, *, journey_count: int | None = None,
                     repo_root: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    cfg = load_config(config_path)
    root = repo_root or find_repo_root(config_path)
    policy_rel = cfg.raw["policy"]["file"]
    policy: Policy = load_policy(root / policy_rel, policy_rel)
    n = int(journey_count if journey_count is not None else cfg.dataset["journey_count"])
    dataset_id = dataset_id_for(cfg, seed, n)

    if out_dir.exists() and any(out_dir.iterdir()):
        if not overwrite:
            raise OutputExistsError(f"{out_dir} is not empty. Use --overwrite to replace the dataset files.")
        for rel in OUTPUT_FILES:
            target = out_dir / rel
            if target.is_file():
                target.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = plan_journeys(cfg, seed, n)
    results = [simulate_journey(spec, cfg, policy) for spec in specs]

    split_cfg = cfg.section("splits")
    split_seed = int(split_cfg["seed"]) if split_cfg.get("seed") is not None else seed
    partitions = assign_partitions(
        ((r.spec.journey_id, r.spec.primary_scenario, r.spec.ambient_profile) for r in results),
        split_cfg["fractions"], split_seed)

    files: list[dict[str, Any]] = []
    files.append(write_table(out_dir, "observed/shipments.csv", SHIPMENT_COLUMNS,
                             ({**r.shipment, "dataset_id": dataset_id} for r in results), "observed",
                             "One row per shipment (journey) with its logger, policy and planned route."))
    files.append(write_table(out_dir, "observed/uploads.csv.gz", UPLOAD_COLUMNS,
                             (u for r in results for u in r.uploads), "observed",
                             "Every batch received from a gateway, with its received time."))
    files.append(write_table(out_dir, "observed/readings.csv.gz", READING_COLUMNS,
                             (x for r in results for x in r.readings), "observed",
                             "Temperature readings as received (DATA-01). Missing readings are absent rows."))
    files.append(write_table(out_dir, "observed/context.csv.gz", CONTEXT_COLUMNS,
                             (x for r in results for x in r.context), "observed",
                             "Context records as received (DATA-02). Empty = not reported."))
    files.append(write_table(out_dir, "ground_truth/journeys.csv", GT_JOURNEY_COLUMNS,
                             (r.gt_journey for r in results), "ground_truth",
                             "Scenario, ambient profile and simulation parameters per journey. NOT a model input."))
    files.append(write_table(out_dir, "ground_truth/events.csv.gz", GT_EVENT_COLUMNS,
                             ({**e, "attributes": json.dumps(e["attributes"], sort_keys=True, separators=(",", ":"))}
                              for r in results for e in r.events), "ground_truth",
                             "Labelled intervals: true out-of-range runs, policy excursions, injected causes, "
                             "sensor faults, missing data and transmission delays. NOT a model input."))
    files.append(write_table(out_dir, "ground_truth/slots.csv.gz", GT_SLOT_COLUMNS,
                             (s for r in results for s in r.slots), "ground_truth",
                             "Per expected reading: true temperature, sensor error components and observation "
                             "status. NOT a model input."))
    files.append(write_table(out_dir, "splits/journey_split.csv", SPLIT_COLUMNS,
                             ({"journey_id": j, "partition": p} for j, p in partitions.items()), "split",
                             "Journey-level partition assignment (train / validation / test)."))

    (out_dir / "config.yaml").write_bytes(cfg.file_bytes)
    files.append({"path": "config.yaml", "role": "config", "format": "yaml",
                  "description": "Exact copy of the configuration used.", "rows": None,
                  "bytes": len(cfg.file_bytes), "sha256": sha256_hex(cfg.file_bytes),
                  "content_sha256": sha256_hex(cfg.file_bytes)})

    statistics = compute_statistics(results, partitions, policy)
    stats_bytes = json_bytes(statistics)
    (out_dir / "statistics.json").write_bytes(stats_bytes)
    files.append({"path": "statistics.json", "role": "statistics", "format": "json",
                  "description": "Counts computed from the generated files.", "rows": None,
                  "bytes": len(stats_bytes), "sha256": sha256_hex(stats_bytes),
                  "content_sha256": sha256_hex(stats_bytes)})

    config_rel = config_path.resolve().relative_to(root.resolve()).as_posix() \
        if config_path.resolve().is_relative_to(root.resolve()) else config_path.name
    regenerate = (f"docker compose --profile tools run --rm data-tools python -m coldchain_sim generate "
                  f"--config {config_rel} --seed {seed}"
                  + ("" if journey_count is None else f" --journeys {n}")
                  + " --out data/generated/<folder>")
    manifest: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_name": cfg.dataset["name"],
        "dataset_version": str(cfg.dataset["version"]),
        "synthetic": True,
        "data_origin": "SIMULATED",
        "description": "Synthetic cold-chain journeys for a teaching prototype. Not real data.",
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "config": {"source_path": config_rel, "copy": "config.yaml",
                   "config_version": cfg.config_version, "sha256": sha256_hex(cfg.file_bytes)},
        "seed": seed,
        "split_seed": split_seed,
        "journey_count": n,
        "policy": policy.manifest_entry(),
        "conventions": {
            "timezone": "UTC; ISO 8601 with 'Z'",
            "temperature_unit": "degree Celsius",
            "missing_reading": "absent row in observed/readings and observed/context; never filled",
            "empty_field": "not reported (NULL), never a default value",
        },
        "files": sorted(files, key=lambda f: f["path"]),
        "regenerate_command": regenerate,
    }
    manifest["dataset_fingerprint"] = fingerprint(manifest["files"])
    (out_dir / "README.md").write_bytes(_dataset_readme(manifest))
    (out_dir / "manifest.json").write_bytes(json_bytes(manifest))
    return manifest


def fingerprint(files: list[dict[str, Any]]) -> str:
    """SHA-256 over (path, content_sha256) of every data file: identifies the dataset content."""
    text = "\n".join(f"{f['path']} {f['content_sha256']}" for f in sorted(files, key=lambda f: f["path"]))
    return sha256_hex(text.encode("utf-8"))
