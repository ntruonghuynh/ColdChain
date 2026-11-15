"""Simulation of one journey: physics -> sensor -> transmission -> ground truth.

Layers (kept separate on purpose, DATA-09):

1. **Physical truth** — product temperature on a 1-minute grid from a first-order
   thermal model driven by ambient temperature, the refrigeration unit and doors.
2. **Observation** — the logger samples every ``sampling_interval_min`` and adds
   calibration bias, drift, noise and spikes; readings can be missing (never
   delivered) or delayed (delivered later with their original ``event_at``).
3. **Ground truth** — intervals derived from (1) and the injected causes, plus
   policy-derived labels (BR-02 on the true temperature, BR-03/BR-04 on the gaps).

Nothing from layer 3 is written into the observed rows.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from coldchain_sim.config import SimConfig, randint, uniform, weighted_choice
from coldchain_sim.policy import Policy, classify_gap, out_of_range_runs
from coldchain_sim.rng import make_rng

# Event types (ground truth, see data dictionary).
TEMP_ABOVE_MAX = "TEMP_ABOVE_MAX"
TEMP_BELOW_MIN = "TEMP_BELOW_MIN"
EXCURSION_HIGH = "EXCURSION_HIGH"
EXCURSION_LOW = "EXCURSION_LOW"
REEFER_FAILURE = "REEFER_FAILURE"
SETPOINT_FAULT_HIGH = "SETPOINT_FAULT_HIGH"
SETPOINT_FAULT_LOW = "SETPOINT_FAULT_LOW"
GRADUAL_WARMING = "GRADUAL_WARMING"
DOOR_OPEN = "DOOR_OPEN"
DEFROST_CYCLE = "DEFROST_CYCLE"
SENSOR_SPIKE = "SENSOR_SPIKE"
SENSOR_BIAS = "SENSOR_BIAS"
SENSOR_DRIFT = "SENSOR_DRIFT"
MISSING_DATA = "MISSING_DATA"
TRANSMISSION_DELAY = "TRANSMISSION_DELAY"

SRC_PHYSICAL = "PHYSICAL_SIMULATION"
SRC_POLICY = "POLICY_RULE_ON_TRUE_TEMPERATURE"
SRC_INJECTED = "INJECTED_SCENARIO"
SRC_OBSERVATION = "OBSERVATION_MODEL"

TX_ON_SCHEDULE = "ON_SCHEDULE"
TX_RETRIED = "RETRIED"
TX_BUFFERED = "BUFFERED_COVERAGE_GAP"

DISTURBANCE_KINDS = (REEFER_FAILURE, SETPOINT_FAULT_HIGH, SETPOINT_FAULT_LOW, GRADUAL_WARMING, DOOR_OPEN,
                     DEFROST_CYCLE)


@dataclass(frozen=True)
class JourneySpec:
    index: int
    journey_id: str
    shipment_id: str
    sensor_id: str
    journey_seed: int
    primary_scenario: str
    ambient_profile: str


@dataclass
class Episode:
    kind: str
    start_min: int
    end_min: int
    injected_by: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class JourneyResult:
    spec: JourneySpec
    shipment: dict[str, Any]
    gt_journey: dict[str, Any]
    readings: list[dict[str, Any]]
    context: list[dict[str, Any]]
    uploads: list[dict[str, Any]]
    slots: list[dict[str, Any]]
    events: list[dict[str, Any]]


# ---------------------------------------------------------------- formatting

def fmt_ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_num(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]
    return text


def quantize(value: float, resolution: float) -> float:
    return round(round(value / resolution) * resolution, 6)


# ---------------------------------------------------------------- planning helpers

def _duration_min(rng: random.Random, cfg: SimConfig, scenario: str) -> int:
    d = cfg.sim["journey_duration_h"]
    lo, mode, hi = float(d["min"]), float(d["mode"]), float(d["max"])
    if scenario == "OCEAN_COVERAGE_GAP":
        lo = max(lo, float(cfg.scenario("OCEAN_COVERAGE_GAP")["min_journey_h"]))
        mode = max(mode, lo)
    hours = rng.triangular(lo, hi, mode)
    step = int(cfg.sim["sampling_interval_min"])
    minutes = int(round(hours * 60 / step)) * step
    return max(int(lo * 60), min(int(hi * 60), minutes))


def _place(rng: random.Random, window_start: int, window_end: int, duration: int) -> tuple[int, int]:
    """Place an interval of ``duration`` inside ``[window_start, window_end)``; shrink if needed."""
    duration = max(1, min(duration, window_end - window_start))
    start = rng.randint(window_start, window_end - duration)
    return start, start + duration


def _ambient_series(rng: random.Random, cfg: SimConfig, profile: str, departure: datetime,
                    n_min: int) -> tuple[list[float], dict[str, float]]:
    amb = cfg.section("ambient_profiles")
    p = amb[profile]
    if profile == "VARIABLE":
        start_mean = uniform(rng, p["start_mean_c"])
        lo, hi = (float(v) for v in p["end_mean_bounds_c"])
        change = float(p["min_mean_change_c"])
        options = []
        if start_mean + change <= hi:
            options.append((start_mean + change, hi))
        if start_mean - change >= lo:
            options.append((lo, start_mean - change))
        a, b = options[0] if len(options) == 1 else options[rng.randrange(len(options))]
        end_mean = rng.uniform(a, b)
    else:
        start_mean = end_mean = uniform(rng, p["mean_c"])
    amplitude = uniform(rng, p["diurnal_amplitude_c"])
    phi = float(amb["weather_ar_coefficient"])
    sd = float(amb["weather_innovation_sd_c"])
    minute_of_day0 = departure.hour * 60 + departure.minute
    weather = 0.0
    series: list[float] = []
    for m in range(n_min + 1):
        frac = m / n_min if n_min else 0.0
        mean = start_mean + (end_mean - start_mean) * frac
        diurnal = amplitude * math.sin(2 * math.pi * ((minute_of_day0 + m) % 1440 - 540) / 1440)
        weather = phi * weather + rng.gauss(0.0, sd)
        series.append(mean + diurnal + weather)
    return series, {"ambient_mean_start_c": start_mean, "ambient_mean_end_c": end_mean,
                    "ambient_diurnal_amplitude_c": amplitude}


def _warming_fault(rng: random.Random, cfg: SimConfig, ambient: list[float], window: tuple[int, int],
                   injected_by: str, duration_bounds: list[int] | None = None) -> Episode:
    """HIGH temperature fault whose mechanism matches the ambient (cooling loss needs a warm ambient)."""
    hx = cfg.scenario("HIGH_EXCURSION")
    w0, w1 = window
    start = rng.randint(w0, max(w0, w1 - 30))
    if ambient[start] >= float(hx["reefer_failure_min_ambient_c"]):
        duration = randint(rng, duration_bounds or hx["reefer_failure_duration_min"])
        s, e = _place(rng, start, min(len(ambient) - 1, start + duration), duration)
        return Episode(REEFER_FAILURE, s, e, injected_by)
    duration = randint(rng, duration_bounds or hx["setpoint_fault_duration_min"])
    s, e = _place(rng, start, min(len(ambient) - 1, start + duration), duration)
    return Episode(SETPOINT_FAULT_HIGH, s, e, injected_by, {"setpoint_c": round(uniform(rng, hx["setpoint_fault_c"]), 3)})


def _segments(n_min: int, count: int, margin: int) -> list[tuple[int, int]]:
    size = (n_min - 2 * margin) // count
    return [(margin + i * size, margin + (i + 1) * size) for i in range(count)]


# ---------------------------------------------------------------- simulation

def simulate_journey(spec: JourneySpec, cfg: SimConfig, policy: Policy) -> JourneyResult:  # noqa: C901
    plan = make_rng(spec.journey_seed, "plan")
    scen_rng = make_rng(spec.journey_seed, "scenario")
    interval = int(cfg.sim["sampling_interval_min"])
    scenario = spec.primary_scenario
    tags: list[str] = [scenario]

    # ---- journey frame ------------------------------------------------------
    n_min = _duration_min(plan, cfg, scenario)
    w_from, w_to = cfg.departure_window
    window_minutes = int((w_to - w_from).total_seconds() // 60)
    departure = w_from + timedelta(minutes=plan.randrange(window_minutes))
    arrival = departure + timedelta(minutes=n_min)
    sec = cfg.section("secondary")
    if scenario == "OCEAN_COVERAGE_GAP":
        route_type = "SEA_ROAD"
    elif plan.random() < float(sec["sea_route_prob"]):
        route_type = "SEA_ROAD"
        tags.append("SEA_ROUTE_NO_OUTAGE")
    else:
        route_type = "ROAD"
    origin_site, destination_site = plan.sample(range(1, 13), 2)

    ambient, ambient_info = _ambient_series(make_rng(spec.journey_seed, "ambient"), cfg, spec.ambient_profile,
                                            departure, n_min)

    # ---- thermal and device parameters ---------------------------------------
    th = cfg.section("thermal")
    setpoint0 = uniform(plan, th["setpoint_c"])
    t0 = setpoint0 + uniform(plan, th["initial_offset_c"])
    k_cool = uniform(plan, th["cooling_coupling_per_min"])
    k_amb = uniform(plan, th["ambient_coupling_per_min"])
    k_res = float(th["residual_ambient_fraction"]) * k_amb
    noise_p = uniform(plan, th["process_noise_sd_c"])
    wobble_amp = uniform(plan, th["load_wobble_amplitude_c"])
    wobble_period = uniform(plan, th["load_wobble_period_h"]) * 60
    wobble_phase = plan.uniform(0, 2 * math.pi)

    sn = cfg.section("sensor")
    bias_c = uniform(plan, sn["calibration_bias_c"])
    drift_rate = 0.0
    drift_start = n_min
    sensor_noise_sd = uniform(plan, sn["noise_sd_c"])
    has_ambient_probe = plan.random() >= float(sn["no_ambient_probe_prob"])
    if not has_ambient_probe:
        tags.append("NO_AMBIENT_PROBE")

    bt = cfg.section("battery")
    battery_start = uniform(plan, bt["start_pct"])
    battery_drain_day = uniform(plan, bt["drain_pct_per_day"])
    battery_depleted = False

    episodes: list[Episode] = []
    spikes: dict[int, float] = {}
    gap_slots: set[int] = set()
    outage: tuple[int, int] | None = None
    restore_delay = 0
    n_slots = n_min // interval + 1  # slot k at minute k * interval, including arrival

    # defrost cycles: benign normal variation for every journey
    t = int(uniform(plan, th["defrost_interval_h"]) * 60)
    while t < n_min - 30:
        d = randint(plan, th["defrost_duration_min"])
        episodes.append(Episode(DEFROST_CYCLE, t, min(n_min, t + d), "NORMAL_VARIATION"))
        t += int(uniform(plan, th["defrost_interval_h"]) * 60)

    # ---- primary scenario ------------------------------------------------------
    sc = cfg.raw["scenarios"].get(scenario, {})
    if scenario == "GRADUAL_WARMING":
        dur = min(int(uniform(scen_rng, sc["duration_h"]) * 60), int(n_min * 0.8))
        s, e = _place(scen_rng, int(n_min * 0.1), n_min - 60, dur)
        rate = round(uniform(scen_rng, sc["creep_rate_c_per_h"]), 4)
        corrected = scen_rng.random() < float(sc["corrected_prob"])
        # The interval covers the whole time the drifted setpoint is in force: until the
        # correction, or until arrival when it is never corrected.
        episodes.append(Episode(GRADUAL_WARMING, s, e if corrected else n_min, scenario, {
            "creep_rate_c_per_h": rate, "corrected": corrected, "ramp_end_min": e,
            "setpoint_rise_c": round(rate * (e - s) / 60, 4),
        }))
    elif scenario == "HIGH_EXCURSION":
        count = 2 if scen_rng.random() < float(sc["second_event_prob"]) else 1
        for seg in _segments(n_min, count, 60):
            episodes.append(_warming_fault(scen_rng, cfg, ambient, seg, scenario))
    elif scenario == "LOW_EXCURSION":
        count = 2 if scen_rng.random() < float(sc["second_event_prob"]) else 1
        for w0, w1 in _segments(n_min, count, 60):
            dur = randint(scen_rng, sc["duration_min"])
            s, e = _place(scen_rng, w0, w1, dur)
            episodes.append(Episode(SETPOINT_FAULT_LOW, s, e, scenario,
                                    {"setpoint_c": round(uniform(scen_rng, sc["setpoint_fault_c"]), 3)}))
    elif scenario == "DOOR_OPENING":
        for _ in range(randint(scen_rng, sc["events"])):
            long_event = scen_rng.random() < float(sc["long_event_prob"])
            dur = randint(scen_rng, sc["long_duration_min"] if long_event else sc["short_duration_min"])
            s, e = _place(scen_rng, 30, n_min - 30, dur)
            episodes.append(Episode(DOOR_OPEN, s, e, scenario,
                                    {"door_coupling_per_min": round(uniform(scen_rng, sc["door_coupling_per_min"]), 5)}))
    elif scenario == "SENSOR_SPIKE":
        _add_spikes(scen_rng, sc, n_slots, spikes, randint(scen_rng, sc["events"]))
    elif scenario == "SENSOR_BIAS_DRIFT":
        mode = weighted_choice(scen_rng, sc["mode_weights"])
        if mode in ("BIAS", "BIAS_AND_DRIFT"):
            sign = 1 if scen_rng.random() < float(sc["positive_bias_prob"]) else -1
            bias_c = sign * uniform(scen_rng, sc["bias_c"])
        if mode in ("DRIFT", "BIAS_AND_DRIFT"):
            sign = 1 if scen_rng.random() < float(sc["positive_drift_prob"]) else -1
            drift_rate = sign * uniform(scen_rng, sc["drift_c_per_day"])
            drift_start = int(uniform(scen_rng, sc["drift_start_fraction"]) * n_min)
        tags.append(f"SENSOR_{mode}")
    elif scenario == "MISSING_READINGS":
        lengths = []
        for _ in range(randint(scen_rng, sc["gaps"])):
            cls = weighted_choice(scen_rng, sc["gap_class_weights"])
            lengths.append(randint(scen_rng, sc[f"{cls.lower()}_readings"]))
        hidden = scen_rng.random() < float(sc["hidden_excursion_prob"])
        min_hidden = int(sc["hidden_excursion_min_gap_readings"])
        if hidden and max(lengths) < min_hidden:
            lengths.append(randint(scen_rng, [min_hidden, int(sc["review_readings"][1])]))
        if scen_rng.random() < float(sc["battery_depleted_prob"]):
            battery_depleted = True
            tags.append("BATTERY_DEPLETED")
            battery_start = uniform(scen_rng, sc["battery_depleted_start_pct"])
            dead_at = int(uniform(scen_rng, sc["battery_depleted_at_fraction"]) * n_min)
            battery_drain_day = battery_start / dead_at * 1440
        usable_slots = n_slots - 2
        if battery_depleted:
            usable_slots = min(usable_slots, dead_at // interval - 2)
        placed = _place_gaps(scen_rng, lengths, usable_slots, int(sc["min_separation_readings"]))
        for start_slot, length in placed:
            gap_slots.update(range(start_slot, start_slot + length))
        if hidden and placed:
            longest = max(placed, key=lambda p: (p[1], -p[0]))
            g0, g1 = longest[0] * interval, (longest[0] + longest[1]) * interval
            fault_start = g0 + int((g1 - g0) * scen_rng.uniform(0.0, 0.3))
            episodes.append(_warming_fault(scen_rng, cfg, ambient, (fault_start, fault_start + 1), scenario,
                                           sc["hidden_excursion_duration_min"]))
            tags.append("HIDDEN_EXCURSION")
    elif scenario == "OCEAN_COVERAGE_GAP":
        length = int(uniform(scen_rng, sc["outage_h"]) * 60)
        o_start = int(uniform(scen_rng, sc["start_fraction"]) * n_min)
        o_end = min(o_start + length, n_min - 90)
        outage = (o_start, o_end)
        restore_delay = randint(scen_rng, sc["restore_upload_delay_min"])
        if scen_rng.random() < float(sc["hidden_excursion_prob"]):
            fault_start = o_start + int((o_end - o_start) * scen_rng.uniform(0.0, 0.5))
            episodes.append(_warming_fault(scen_rng, cfg, ambient, (fault_start, fault_start + 1), scenario,
                                           sc["hidden_excursion_duration_min"]))
            tags.append("HIDDEN_EXCURSION")

    # ---- secondary modifiers (own stream so they never shift the primary scenario) ----
    mod = make_rng(spec.journey_seed, "secondary")
    if scenario != "DOOR_OPENING" and mod.random() < float(sec["door_opening_prob"]):
        door_cfg = cfg.scenario("DOOR_OPENING")
        for _ in range(randint(mod, sec["door_opening_events"])):
            dur = randint(mod, door_cfg["short_duration_min"])
            s, e = _place(mod, 30, n_min - 30, dur)
            episodes.append(Episode(DOOR_OPEN, s, e, "SECONDARY_DOOR_OPENING",
                                    {"door_coupling_per_min": round(uniform(mod, door_cfg["door_coupling_per_min"]), 5)}))
        tags.append("DOOR_OPENING")
    if scenario != "SENSOR_SPIKE" and mod.random() < float(sec["sensor_spike_prob"]):
        _add_spikes(mod, cfg.scenario("SENSOR_SPIKE"), n_slots, spikes, randint(mod, sec["sensor_spike_events"]))
        tags.append("SENSOR_SPIKE")

    # ---- control arrays and physics -------------------------------------------
    cooling = [1.0] * (n_min + 1)
    setpoint = [setpoint0 + wobble_amp * math.sin(2 * math.pi * m / wobble_period + wobble_phase)
                for m in range(n_min + 1)]
    door = [0.0] * (n_min + 1)
    for ep in episodes:
        if ep.kind == GRADUAL_WARMING:
            rate = ep.params["creep_rate_c_per_h"] / 60
            ramp_end = ep.params["ramp_end_min"]
            tail_end = ep.end_min if ep.params["corrected"] else n_min + 1
            for m in range(ep.start_min, tail_end):
                setpoint[m] += rate * (min(m, ramp_end) - ep.start_min)
    for ep in episodes:
        if ep.kind in (SETPOINT_FAULT_HIGH, SETPOINT_FAULT_LOW):
            for m in range(ep.start_min, ep.end_min):
                setpoint[m] = ep.params["setpoint_c"]
        elif ep.kind in (REEFER_FAILURE, DEFROST_CYCLE):
            for m in range(ep.start_min, ep.end_min):
                cooling[m] = 0.0
        elif ep.kind == DOOR_OPEN:
            k = ep.params["door_coupling_per_min"]
            for m in range(ep.start_min, ep.end_min):
                door[m] = max(door[m], k)

    phys = make_rng(spec.journey_seed, "physics")
    temp = [0.0] * (n_min + 1)
    temp[0] = t0
    for m in range(n_min):
        c = cooling[m]
        a = ambient[m]
        temp[m + 1] = (temp[m] + c * k_cool * (setpoint[m] - temp[m])
                       + (k_res + (1 - c) * k_amb + door[m]) * (a - temp[m])
                       + phys.gauss(0.0, noise_p))

    # ---- battery ---------------------------------------------------------------
    battery = [0.0] * (n_min + 1)
    level = battery_start
    cold_mult = float(bt["cold_drain_multiplier"])
    cold_thr = float(bt["cold_ambient_threshold_c"])
    for m in range(n_min + 1):
        battery[m] = level
        mult = cold_mult if (ambient[m] < cold_thr and not battery_depleted) else 1.0
        level -= battery_drain_day / 1440 * mult
    death_min = next((m for m in range(n_min + 1) if battery[m] <= 0), None)

    # ---- observation: sensor values and missing readings ---------------------
    res_t = float(cfg.sim["temperature_resolution_c"])
    res_a = float(cfg.sim["ambient_resolution_c"])
    res_b = float(cfg.sim["battery_resolution_pct"])
    lo_c, hi_c = (float(v) for v in sn["physical_range_c"])
    sensor_rng = make_rng(spec.journey_seed, "sensor")
    context_rng = make_rng(spec.journey_seed, "context")
    dropout_rng = make_rng(spec.journey_seed, "dropout")
    p_drop = float(cfg.section("transmission")["random_dropout_prob"])
    amb_sd = float(sn["ambient_probe_noise_sd_c"])

    slot_info: list[dict[str, Any]] = []
    for k in range(n_slots):
        m = k * interval
        noise = sensor_rng.gauss(0.0, sensor_noise_sd)
        offset = bias_c + drift_rate * max(0, m - drift_start) / 1440
        spike = spikes.get(k, 0.0)
        observed = min(hi_c, max(lo_c, quantize(temp[m] + offset + noise + spike, res_t)))
        amb_noise = context_rng.gauss(0.0, amb_sd)
        dropped = dropout_rng.random() < p_drop and 0 < k < n_slots - 1
        causes = []
        if death_min is not None and m >= death_min:
            causes.append("BATTERY_DEPLETED")
        if k in gap_slots:
            causes.append("LOGGER_FAULT")
        if dropped:
            causes.append("RANDOM_DROPOUT")
        door_open = any(door[mm] > 0 for mm in range(max(0, m - interval + 1), m + 1))
        slot_info.append({
            "k": k, "m": m, "observed": observed, "noise": noise, "offset": offset, "spike": spike,
            "missing_causes": causes,
            "door_open": door_open,
            "ambient_obs": quantize(ambient[m] + amb_noise, res_a) if has_ambient_probe else None,
            "battery_obs": quantize(max(0.0, battery[m]), res_b),
        })
    if any("RANDOM_DROPOUT" in s["missing_causes"] for s in slot_info):
        tags.append("RANDOM_DROPOUT")

    # ---- transmission: uploads, delays --------------------------------------
    tx = cfg.section("transmission")
    comms = make_rng(spec.journey_seed, "comms")
    up_int = int(tx["upload_interval_min"])
    first_upload = comms.randint(1, up_int)
    scheduled = list(range(first_upload, n_min, up_int))
    failed_flags = [comms.random() < float(tx["upload_failure_prob"]) for _ in scheduled]
    final_upload = n_min + randint(comms, tx["final_flush_delay_min"])
    restore_u = outage[1] + restore_delay if outage is not None else None
    uploads_ok: list[tuple[int, str]] = []
    failed_times: list[int] = []
    for u, failed in zip(scheduled, failed_flags, strict=True):
        if outage is not None and outage[0] <= u <= restore_u:
            continue  # no coverage until the link is restored (the restore upload replaces this slot)
        if failed:
            failed_times.append(u)
            continue
        uploads_ok.append((u, TX_ON_SCHEDULE))
    if restore_u is not None:
        uploads_ok.append((restore_u, TX_BUFFERED))
    uploads_ok.append((final_upload, TX_ON_SCHEDULE))
    uploads_ok.sort()
    assert len({u for u, _ in uploads_ok}) == len(uploads_ok), "upload minutes must be unique"
    latency_s = {u: randint(comms, tx["network_latency_s"]) for u, _ in uploads_ok}
    if failed_times:
        tags.append("UPLOAD_RETRY")

    upload_of_slot: dict[int, tuple[int, str]] = {}
    pointer = 0
    for s in slot_info:
        if s["missing_causes"]:
            continue
        while uploads_ok[pointer][0] < s["m"]:
            pointer += 1
        u, kind = uploads_ok[pointer]
        if kind == TX_ON_SCHEDULE and any(s["m"] <= f < u for f in failed_times):
            kind = TX_RETRIED
        upload_of_slot[s["k"]] = (u, kind)

    members_by_upload: dict[int, list[int]] = {}
    for kk, (uu, _kind) in upload_of_slot.items():
        members_by_upload.setdefault(uu, []).append(kk)
    upload_ids: dict[int, str] = {}
    upload_rows: list[dict[str, Any]] = []
    for u, _ in uploads_ok:
        members = members_by_upload.get(u, [])
        if not members:
            continue  # nothing to send: no batch is received
        upload_id = f"{spec.shipment_id}-U{len(upload_rows) + 1:04d}"
        upload_ids[u] = upload_id
        received = departure + timedelta(minutes=u, seconds=latency_s[u])
        upload_rows.append({
            "upload_id": upload_id,
            "shipment_id": spec.shipment_id,
            "sensor_id": spec.sensor_id,
            "received_at": fmt_ts(received),
            "first_event_at": fmt_ts(departure + timedelta(minutes=min(members) * interval)),
            "last_event_at": fmt_ts(departure + timedelta(minutes=max(members) * interval)),
            "reading_count": len(members),
        })

    # ---- ground-truth events ----------------------------------------------------
    events: list[dict[str, Any]] = []

    def add_event(event_type: str, source: str, cause: str, start_min: int, end_min: int,
                  **attributes: Any) -> None:
        events.append({"event_type": event_type, "label_source": source, "cause": cause,
                       "start_min": start_min, "end_min": end_min, "attributes": attributes})

    in_excursion = [False] * n_slots
    oor = out_of_range_runs(temp[:n_min], 1, policy)
    for run in oor:
        slots_in = [s for s in slot_info if run.start_min <= s["m"] < run.end_min]
        overlapping = sorted({ep.kind for ep in episodes
                              if ep.start_min < run.end_min and ep.end_min > run.start_min
                              and ep.kind != DEFROST_CYCLE} or {"UNATTRIBUTED"})
        truth_type = TEMP_ABOVE_MAX if run.direction == "HIGH" else TEMP_BELOW_MIN
        add_event(truth_type, SRC_PHYSICAL, ";".join(overlapping), run.start_min, run.end_min,
                  peak_temperature_c=round(run.peak_c, 3), meets_policy_duration=run.meets_policy_duration)
        if run.meets_policy_duration:
            for s in slots_in:
                in_excursion[s["k"]] = True
            missing = sum(1 for s in slots_in if s["missing_causes"])
            delayed = sum(1 for s in slots_in if s["k"] in upload_of_slot
                          and upload_of_slot[s["k"]][1] != TX_ON_SCHEDULE)
            add_event(EXCURSION_HIGH if run.direction == "HIGH" else EXCURSION_LOW, SRC_POLICY,
                      ";".join(overlapping), run.start_min, run.end_min,
                      peak_temperature_c=round(run.peak_c, 3),
                      policy_min_duration_min=(policy.high_excursion_min_duration_min if run.direction == "HIGH"
                                               else policy.low_excursion_min_duration_min),
                      readings_in_interval=len(slots_in), missing_readings_in_interval=missing,
                      delayed_readings_in_interval=delayed)

    for ep in episodes:
        add_event(ep.kind, SRC_INJECTED, ep.injected_by, ep.start_min, ep.end_min, **ep.params)

    spike_slots = sorted(spikes)
    i = 0
    while i < len(spike_slots):
        j = i
        while j + 1 < len(spike_slots) and spike_slots[j + 1] == spike_slots[j] + 1:
            j += 1
        group = [slot_info[k] for k in spike_slots[i:j + 1]]
        add_event(SENSOR_SPIKE, SRC_INJECTED, scenario if scenario == "SENSOR_SPIKE" else "SECONDARY_SENSOR_SPIKE",
                  group[0]["m"], group[-1]["m"] + interval,
                  spike_c=[round(g["spike"], 3) for g in group],
                  observed_temperature_c=[g["observed"] for g in group],
                  observed_out_of_range=any(not policy.min_temp_c <= g["observed"] <= policy.max_temp_c
                                            for g in group),
                  delivered=all(not g["missing_causes"] for g in group))
        i = j + 1

    significant_bias = float(cfg.section("labels")["significant_bias_c"])
    if abs(bias_c) >= significant_bias:
        add_event(SENSOR_BIAS, SRC_INJECTED, scenario, 0, n_min, bias_c=round(bias_c, 4))
    if drift_rate != 0.0:
        add_event(SENSOR_DRIFT, SRC_INJECTED, scenario, drift_start, n_min,
                  drift_c_per_day=round(drift_rate, 4),
                  offset_at_arrival_c=round(bias_c + drift_rate * (n_min - drift_start) / 1440, 4))

    # missing data: maximal runs of missing slots, measured between delivered readings
    k = 0
    while k < n_slots:
        if not slot_info[k]["missing_causes"]:
            k += 1
            continue
        j = k
        while j + 1 < n_slots and slot_info[j + 1]["missing_causes"]:
            j += 1
        prev_m = slot_info[k - 1]["m"] if k > 0 else 0
        open_ended = j == n_slots - 1
        next_m = n_min if open_ended else slot_info[j + 1]["m"]
        gap_min = next_m - prev_m
        causes = sorted({c for s in slot_info[k:j + 1] for c in s["missing_causes"]})
        hidden_oor = [r for r in oor if r.start_min < next_m and r.end_min > prev_m]
        add_event(MISSING_DATA, SRC_OBSERVATION, ";".join(causes), prev_m, next_m,
                  missing_readings=j - k + 1, observed_gap_min=gap_min,
                  policy_gap_status=classify_gap(gap_min, policy), open_ended=open_ended,
                  overlaps_true_out_of_range=bool(hidden_oor),
                  overlaps_policy_excursion=any(r.meets_policy_duration for r in hidden_oor))
        k = j + 1

    if outage is not None and restore_u is not None:
        members = members_by_upload.get(restore_u, [])
        delays = [(restore_u * 60 + latency_s[restore_u] - slot_info[kk]["m"] * 60) / 60 for kk in members]
        add_event(TRANSMISSION_DELAY, SRC_OBSERVATION, "OCEAN_COVERAGE_GAP", outage[0], restore_u,
                  outage_start_min=outage[0], outage_end_min=outage[1],
                  upload_id=upload_ids.get(restore_u),
                  upload_received_at=fmt_ts(departure + timedelta(minutes=restore_u, seconds=latency_s[restore_u])),
                  buffered_readings=len(members), max_delay_min=round(max(delays), 2) if delays else 0.0)
    for f in failed_times:
        nxt = next(u for u, _ in uploads_ok if u > f)
        affected = [kk for kk in members_by_upload.get(nxt, []) if slot_info[kk]["m"] <= f]
        if affected:
            add_event(TRANSMISSION_DELAY, SRC_OBSERVATION, "UPLOAD_RETRY", f, nxt,
                      upload_id=upload_ids.get(nxt), delayed_readings=len(affected))

    # ---- rows -------------------------------------------------------------------
    readings: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    slots_rows: list[dict[str, Any]] = []
    delays_min: list[float] = []
    for s in slot_info:
        event_at = departure + timedelta(minutes=s["m"])
        tx_kind = ""
        delay_s: int | str = ""
        if not s["missing_causes"]:
            u, tx_kind = upload_of_slot[s["k"]]
            received = departure + timedelta(minutes=u, seconds=latency_s[u])
            delay_s = int((received - event_at).total_seconds())
            delays_min.append(delay_s / 60)
            common = {"shipment_id": spec.shipment_id, "sensor_id": spec.sensor_id,
                      "event_at": fmt_ts(event_at), "received_at": fmt_ts(received)}
            readings.append({**common, "temperature_c": fmt_num(s["observed"], 1), "upload_id": upload_ids[u]})
            context.append({**common,
                             "door_state": "OPEN" if s["door_open"] else "CLOSED",
                             "battery_level_pct": fmt_num(s["battery_obs"], 1),
                             "ambient_temperature_c": "" if s["ambient_obs"] is None else fmt_num(s["ambient_obs"], 1),
                             "upload_id": upload_ids[u]})
        true_t = temp[s["m"]]
        state = ("ABOVE_MAX" if true_t > policy.max_temp_c else
                 "BELOW_MIN" if true_t < policy.min_temp_c else "IN_RANGE")
        slots_rows.append({
            "journey_id": spec.journey_id,
            "slot_at": fmt_ts(event_at),
            "true_product_temperature_c": fmt_num(true_t, 3),
            "true_ambient_temperature_c": fmt_num(ambient[s["m"]], 2),
            "door_open_in_interval": int(s["door_open"]),
            "true_temperature_state": state,
            "in_policy_excursion": int(in_excursion[s["k"]]),
            "sensor_offset_c": fmt_num(s["offset"], 3),
            "sensor_noise_c": fmt_num(s["noise"], 3),
            "sensor_spike_c": fmt_num(s["spike"], 3),
            "observation_status": "MISSING" if s["missing_causes"] else "OBSERVED",
            "missing_cause": ";".join(s["missing_causes"]),
            "transmission": tx_kind,
            "delay_s": delay_s,
        })

    for ev in events:
        ev["start_at"] = fmt_ts(departure + timedelta(minutes=ev["start_min"]))
        ev["end_at"] = fmt_ts(departure + timedelta(minutes=ev["end_min"]))
        ev["duration_min"] = ev["end_min"] - ev["start_min"]
    events.sort(key=lambda e: (e["start_min"], e["end_min"], e["event_type"], e["cause"]))
    for n, ev in enumerate(events, start=1):
        ev["event_id"] = f"{spec.journey_id}-E{n:03d}"
        ev["journey_id"] = spec.journey_id

    shipment = {
        "shipment_id": spec.shipment_id,
        "sensor_id": spec.sensor_id,
        "product_id": policy.product_id,
        "policy_code": policy.policy_code,
        "policy_version": policy.policy_version,
        "origin": f"Simulated site {origin_site:02d}",
        "destination": f"Simulated site {destination_site:02d}",
        "route_type": route_type,
        "departure_at": fmt_ts(departure),
        "arrival_at": fmt_ts(arrival),
        "data_origin": "SIMULATED",
    }
    policy_events = [e for e in events if e["event_type"] in (EXCURSION_HIGH, EXCURSION_LOW)]
    gt_journey = {
        "journey_id": spec.journey_id,
        "shipment_id": spec.shipment_id,
        "sensor_id": spec.sensor_id,
        "journey_seed": spec.journey_seed,
        "primary_scenario": scenario,
        "scenario_tags": ";".join([tags[0], *sorted(set(tags[1:]))]),
        "ambient_profile": spec.ambient_profile,
        "route_type": route_type,
        "departure_at": fmt_ts(departure),
        "arrival_at": fmt_ts(arrival),
        "duration_min": n_min,
        "setpoint_c": fmt_num(setpoint0, 3),
        "cooling_coupling_per_min": fmt_num(k_cool, 5),
        "ambient_coupling_per_min": fmt_num(k_amb, 5),
        "process_noise_sd_c": fmt_num(noise_p, 4),
        "ambient_mean_start_c": fmt_num(ambient_info["ambient_mean_start_c"], 2),
        "ambient_mean_end_c": fmt_num(ambient_info["ambient_mean_end_c"], 2),
        "ambient_diurnal_amplitude_c": fmt_num(ambient_info["ambient_diurnal_amplitude_c"], 2),
        "sensor_bias_c": fmt_num(bias_c, 4),
        "sensor_drift_c_per_day": fmt_num(drift_rate, 4),
        "sensor_drift_start_at": fmt_ts(departure + timedelta(minutes=drift_start)) if drift_rate else "",
        "sensor_noise_sd_c": fmt_num(sensor_noise_sd, 4),
        "has_ambient_probe": int(has_ambient_probe),
        "battery_start_pct": fmt_num(battery_start, 2),
        "battery_drain_pct_per_day": fmt_num(battery_drain_day, 4),
        "expected_readings": n_slots,
        "observed_readings": len(readings),
        "missing_readings": n_slots - len(readings),
        "delayed_readings": sum(1 for r in slots_rows if r["transmission"] in (TX_RETRIED, TX_BUFFERED)),
        "max_delay_min": fmt_num(max(delays_min) if delays_min else 0.0, 2),
        "policy_excursion_count": len(policy_events),
        "true_minutes_above_max": sum(1 for v in temp[:n_min] if v > policy.max_temp_c),
        "true_minutes_below_min": sum(1 for v in temp[:n_min] if v < policy.min_temp_c),
    }
    return JourneyResult(spec, shipment, gt_journey, readings, context, upload_rows, slots_rows, events)


def _add_spikes(rng: random.Random, sc: dict[str, Any], n_slots: int, spikes: dict[int, float], count: int) -> None:
    for _ in range(count):
        for _attempt in range(50):
            k = rng.randint(2, n_slots - 4)
            width = 2 if rng.random() < float(sc["two_reading_prob"]) else 1
            if all(kk not in spikes and kk - 1 not in spikes and kk + 1 not in spikes for kk in range(k, k + width)):
                break
        else:
            continue
        positive = rng.random() < float(sc["positive_prob"])
        for kk in range(k, k + width):
            magnitude = uniform(rng, sc["positive_c"] if positive else sc["negative_c"])
            spikes[kk] = magnitude if positive else -magnitude


def _place_gaps(rng: random.Random, lengths: list[int], usable_slots: int,
                separation: int) -> list[tuple[int, int]]:
    """Non-overlapping gaps (start_slot, length) inside slots 1..usable_slots, separated by ``separation``."""
    placed: list[tuple[int, int]] = []
    for length in sorted(lengths, reverse=True):
        length = min(length, max(1, usable_slots // 4))
        for _attempt in range(200):
            start = rng.randint(1, max(1, usable_slots - length))
            if all(start + length + separation <= s or s + n + separation <= start for s, n in placed):
                placed.append((start, length))
                break
    placed.sort()
    return placed
