"""Ground truth: excursion interval labels and separation of truth from observations (DATA-04, DATA-09)."""

from conftest import Data

from coldchain_sim.config import PRIMARY_SCENARIOS
from coldchain_sim.journey import DISTURBANCE_KINDS

FORBIDDEN_IN_OBSERVED = ("true", "scenario", "label", "excursion", "fault", "partition", "profile", "spike",
                         "bias", "drift", "missing", "cause")


def test_br02_policy_excursions_meet_the_duration_rule(full: Data) -> None:
    high = [e for e in full.events if e["event_type"] == "EXCURSION_HIGH"]
    low = [e for e in full.events if e["event_type"] == "EXCURSION_LOW"]
    assert high and low
    assert all(e["duration_min"] >= 30 for e in high)
    assert all(e["duration_min"] >= 15 for e in low)
    assert {e["label_source"] for e in high + low} == {"POLICY_RULE_ON_TRUE_TEMPERATURE"}


def test_br02_every_long_true_out_of_range_run_is_labelled_and_no_short_one_is(full: Data) -> None:
    truth = {(e["journey_id"], e["start_at"], e["end_at"]): e for e in full.events
             if e["event_type"] in ("TEMP_ABOVE_MAX", "TEMP_BELOW_MIN")}
    policy = {(e["journey_id"], e["start_at"], e["end_at"]): e for e in full.events
              if e["event_type"] in ("EXCURSION_HIGH", "EXCURSION_LOW")}
    assert set(policy) <= set(truth)
    for key, t in truth.items():
        assert (key in policy) == t["attributes"]["meets_policy_duration"]
    near_misses = [t for k, t in truth.items() if k not in policy]
    assert near_misses, "the dataset should contain short out-of-range runs that are not policy excursions"


def test_true_temperature_is_out_of_range_inside_every_policy_excursion(full: Data) -> None:
    slots_of: dict[str, list[dict[str, str]]] = {}
    for s in full.slots:
        slots_of.setdefault(s["journey_id"], []).append(s)
    flagged = {(s["journey_id"], s["slot_at"]) for s in full.slots if s["in_policy_excursion"] == "1"}
    inside = set()
    for e in full.events:
        if e["event_type"] not in ("EXCURSION_HIGH", "EXCURSION_LOW"):
            continue
        want = "ABOVE_MAX" if e["event_type"] == "EXCURSION_HIGH" else "BELOW_MIN"
        for s in slots_of[e["journey_id"]]:
            if e["start_at"] <= s["slot_at"] < e["end_at"]:
                assert s["true_temperature_state"] == want, (e["event_id"], s["slot_at"])
                inside.add((s["journey_id"], s["slot_at"]))
    assert inside == flagged


def test_every_policy_excursion_has_an_injected_physical_cause(full: Data) -> None:
    for e in full.events:
        if e["event_type"] in ("EXCURSION_HIGH", "EXCURSION_LOW"):
            causes = set(e["cause"].split(";"))
            assert causes & set(DISTURBANCE_KINDS), e


def test_sensor_only_scenarios_have_no_true_excursion(full: Data) -> None:
    """Spikes, bias and drift change observations only; the product stays in range."""
    for j in full.journeys:
        if j["primary_scenario"] in ("NORMAL", "SENSOR_SPIKE", "SENSOR_BIAS_DRIFT"):
            assert j["policy_excursion_count"] == "0", j["journey_id"]


def test_observed_value_equals_truth_plus_sensor_error_components(full: Data) -> None:
    """Physical temperature and observed measurement are distinct layers linked by documented terms."""
    checked = 0
    for r in full.readings:
        s = full.slot_index[(r["shipment_id"], r["event_at"])]
        expected = (float(s["true_product_temperature_c"]) + float(s["sensor_offset_c"])
                    + float(s["sensor_noise_c"]) + float(s["sensor_spike_c"]))
        expected = min(60.0, max(-40.0, expected))
        assert abs(float(r["temperature_c"]) - expected) <= 0.05 + 0.002, (r, s)
        checked += 1
    assert checked == len(full.readings)


def test_ground_truth_never_appears_in_observed_files(full: Data) -> None:
    """DATA-09: label columns only live in ground_truth/; observed files cannot leak them."""
    for rel in ("observed/shipments.csv", "observed/uploads.csv.gz", "observed/readings.csv.gz",
                "observed/context.csv.gz"):
        header = list(full.table(rel)[0])
        for col in header:
            assert not any(word in col for word in FORBIDDEN_IN_OBSERVED), (rel, col)
    assert list(full.split[0]) == ["journey_id", "partition"]
    text_values = {v for s in full.shipments for v in s.values()}
    for name in PRIMARY_SCENARIOS:
        assert not any(name in v for v in text_values)
    roles = {f["path"]: f["role"] for f in full.manifest["files"]}
    assert all(roles[p] == "ground_truth" for p in roles if p.startswith("ground_truth/"))
    assert all(roles[p] == "observed" for p in roles if p.startswith("observed/"))
