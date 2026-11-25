# SPDX-License-Identifier: MIT OR Apache-2.0
"""Observation age, delivery delay, and stale-cache semantics. Local calculation only.

Times are integer nanoseconds on a declared clock. Freshness is judged from the
observation time, never from the time a value was received or displayed.
"""
from dataclasses import dataclass, replace
import math
import unittest

STAGE_NAMES = ("transport", "estimation", "release", "delivery")
CLOCKS = {"monotonic_local", "reviewed_utc"}
NS_PER_S = 1_000_000_000


@dataclass(frozen=True)
class Record:
    obs_end_ns: int
    ingest_ns: int
    estimate_ns: int
    release_ns: int
    receive_ns: int | None
    clock_source: str


@dataclass(frozen=True)
class Policy:
    fresh_ns: int
    stale_ns: int
    skew_ns: int = 0


def _int(v):
    return type(v) is int


def _check_record(r):
    if not isinstance(r, Record) or not all(_int(v) for v in (r.obs_end_ns, r.ingest_ns,
                                                              r.estimate_ns, r.release_ns)) \
            or not (r.receive_ns is None or _int(r.receive_ns)) or r.clock_source not in CLOCKS:
        raise ValueError("record")


def _check_policy(p):
    if not isinstance(p, Policy) or not all(_int(v) for v in (p.fresh_ns, p.stale_ns, p.skew_ns)) \
            or not 0 <= p.fresh_ns <= p.stale_ns or p.skew_ns < 0:
        raise ValueError("policy")


def stage_delays(record, skew_ns=0):
    """Stage delays in ns. Negative values are kept and flagged, never clipped."""
    _check_record(record)
    if not _int(skew_ns) or skew_ns < 0:
        raise ValueError("skew")
    times = [record.obs_end_ns, record.ingest_ns, record.estimate_ns, record.release_ns, record.receive_ns]
    delays = {}
    for name, a, b in zip(STAGE_NAMES, times, times[1:]):
        delays[name] = None if b is None else b - a
    known = [d for d in delays.values() if d is not None]
    return {"delays": delays, "order_violation": any(d < -skew_ns for d in known),
            "release_delay_ns": record.release_ns - record.obs_end_ns}


def classify(record, now_ns, policy):
    """Return (state, reason): current, aging, stale, or unknown."""
    _check_record(record)
    _check_policy(policy)
    if not _int(now_ns):
        raise ValueError("now")
    if stage_delays(record, policy.skew_ns)["order_violation"]:
        return "unknown", "ORDER_VIOLATION"
    age = now_ns - record.obs_end_ns
    if age < -policy.skew_ns:
        return "unknown", "FUTURE_OBSERVATION"
    if age <= policy.fresh_ns:
        return "current", "WITHIN_FRESH_LIMIT"
    if age <= policy.stale_ns:
        return "aging", "PAST_FRESH_LIMIT"
    return "stale", "PAST_STALE_LIMIT"


def render_text(state, age_ns):
    """Plain-text status usable on every channel; no colour or app needed."""
    seconds = None if age_ns is None else max(0, age_ns) // NS_PER_S
    if state == "current":
        return "Estimate observed %d s ago." % seconds
    if state == "aging":
        return "Estimate observed %d s ago. Newer data is overdue." % seconds
    if state == "stale":
        return "No recent verified estimate. Last observation was %d s ago." % seconds
    return "Estimate unavailable."


class DisplayCache:
    """Keeps the newest received record; judges it by observation age only."""

    def __init__(self, policy):
        _check_policy(policy)
        self._policy = policy
        self._record = None

    def receive(self, record, now_ns):
        _check_record(record)
        if not _int(now_ns) or record.receive_ns is None \
                or record.receive_ns > now_ns + self._policy.skew_ns:
            return False
        if self._record is not None and record.obs_end_ns <= self._record.obs_end_ns:
            return False
        self._record = record
        return True

    def view(self, now_ns):
        if self._record is None:
            state, reason = "unknown", "NO_OBSERVATION"
        else:
            state, reason = classify(self._record, now_ns, self._policy)
        shown = state in ("current", "aging", "stale")
        age = now_ns - self._record.obs_end_ns if shown else None
        return {"state": state, "reason": reason, "age_ns": age,
                "show_value": state in ("current", "aging"), "text": render_text(state, age)}


def uncertainty_at(sigma0_sq, q_per_s, age_ns):
    """Variance growth sigma0^2 + q * age, with age in seconds (persons^2)."""
    if min(sigma0_sq, q_per_s) < 0 or not _int(age_ns) or age_ns < 0 \
            or not all(math.isfinite(v) for v in (sigma0_sq, q_per_s)):
        raise ValueError("uncertainty")
    return sigma0_sq + q_per_s * age_ns / NS_PER_S


def limits_from_variance(sigma0_sq, q_per_s, fresh_var, stale_var, skew_ns=0):
    """Turn variance caps into age limits; the caps are policy, not measurements."""
    values = (sigma0_sq, q_per_s, fresh_var, stale_var)
    if type(skew_ns) is not int or not all(type(v) in (int, float) and math.isfinite(v) for v in values):
        raise ValueError("limits")
    if not (0 <= sigma0_sq < fresh_var <= stale_var) or q_per_s <= 0 or skew_ns < 0:
        raise ValueError("limits")
    return Policy(int((fresh_var - sigma0_sq) / q_per_s * NS_PER_S),
                  int((stale_var - sigma0_sq) / q_per_s * NS_PER_S), skew_ns)


def apply_outages(records, outages, deliver_at_reconnect=True):
    """Move receipt of records released during an outage to its end, or drop them."""
    spans = sorted(outages)
    if not all(_int(a) and _int(b) and a < b for a, b in spans) \
            or any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1)):
        raise ValueError("outages")
    result = []
    for r in records:
        _check_record(r)
        if r.receive_ns is None:
            result.append(r)
            continue
        hit = next((b for a, b in spans if a <= r.receive_ns < b), None)
        if hit is None:
            result.append(r)
        else:
            result.append(replace(r, receive_ns=hit if deliver_at_reconnect else None))
    return tuple(result)


def summarize(values):
    """Nearest-rank percentiles of integer delays."""
    if not values or not all(_int(v) for v in values):
        raise ValueError("values")
    ordered = sorted(values)
    pick = lambda p: ordered[max(1, math.ceil(p * len(ordered))) - 1]
    return {"n": len(ordered), "p50": pick(0.5), "p95": pick(0.95), "max": ordered[-1]}


def stage_summary(records, skew_ns=0):
    columns = {name: [] for name in STAGE_NAMES}
    violations = 0
    for r in records:
        report = stage_delays(r, skew_ns)
        violations += report["order_violation"]
        for name, value in report["delays"].items():
            if value is not None:
                columns[name].append(value)
    return {"stages": {k: summarize(v) for k, v in columns.items() if v},
            "order_violations": violations, "records": len(records)}


class Tests(unittest.TestCase):
    S = NS_PER_S

    def rec(self, obs=0, ingest=1, estimate=2, release=3, receive=4, clock="monotonic_local"):
        return Record(obs * self.S, ingest * self.S, estimate * self.S, release * self.S,
                      None if receive is None else receive * self.S, clock)

    def test_stage_delays_and_order_violations(self):
        report = stage_delays(self.rec(0, 2, 5, 9, 12))
        self.assertEqual(report["delays"], {"transport": 2 * self.S, "estimation": 3 * self.S,
                                            "release": 4 * self.S, "delivery": 3 * self.S})
        self.assertEqual(report["release_delay_ns"], 9 * self.S)
        self.assertFalse(report["order_violation"])
        backwards = stage_delays(self.rec(0, 5, 4, 9, 12))
        self.assertTrue(backwards["order_violation"])
        self.assertEqual(backwards["delays"]["estimation"], -self.S)
        self.assertFalse(stage_delays(self.rec(0, 5, 4, 9, 12), skew_ns=2 * self.S)["order_violation"])
        self.assertIsNone(stage_delays(self.rec(receive=None))["delays"]["delivery"])

    def test_classification_boundaries(self):
        policy = Policy(10 * self.S, 30 * self.S)
        r = self.rec(0, 0, 0, 0, 1)
        expected = [(10, "current"), (11, "aging"), (30, "aging"), (31, "stale")]
        for now, state in expected:
            self.assertEqual(classify(r, now * self.S, policy)[0], state, now)
        self.assertEqual(classify(r, -1 * self.S, policy), ("unknown", "FUTURE_OBSERVATION"))
        self.assertEqual(classify(self.rec(0, 5, 4, 9, 12), 5 * self.S, policy),
                         ("unknown", "ORDER_VIOLATION"))
        self.assertEqual(classify(r, -1 * self.S, Policy(10 * self.S, 30 * self.S, 2 * self.S))[0], "current")

    def test_variance_limits(self):
        policy = limits_from_variance(1.0, 0.5, 4.0, 9.0)
        self.assertEqual((policy.fresh_ns, policy.stale_ns), (6 * self.S, 16 * self.S))
        self.assertAlmostEqual(uncertainty_at(1.0, 0.5, 6 * self.S), 4.0)
        for args in [(1, 0, 4, 9), (4, 1, 4, 9), (1, 1, 9, 4), (-1, 1, 4, 9), (1, 1, float("nan"), 9)]:
            with self.assertRaises(ValueError):
                limits_from_variance(*args)

    def test_freshness_uses_observation_age_not_receipt_age(self):
        policy = Policy(300 * self.S, 600 * self.S)
        cache = DisplayCache(policy)
        slow = self.rec(0, 100, 150, 200, 290)
        self.assertTrue(cache.receive(slow, 290 * self.S))
        self.assertEqual(cache.view(300 * self.S)["state"], "current")
        view = cache.view(301 * self.S)
        self.assertEqual(view["state"], "aging")
        self.assertTrue(view["show_value"])
        self.assertIn("overdue", view["text"])
        self.assertNotIn("Estimate observed 11 s ago", view["text"])

    def test_cache_does_not_stay_current_through_an_outage(self):
        policy = Policy(300 * self.S, 600 * self.S)
        cache = DisplayCache(policy)
        cache.receive(self.rec(0, 1, 2, 3, 4), 4 * self.S)
        view = cache.view(2000 * self.S)
        self.assertEqual(view["state"], "stale")
        self.assertFalse(view["show_value"])
        self.assertNotIn("Estimate observed", view["text"])
        self.assertIn("2000 s", view["text"])

    def test_outage_replay_arrives_late_but_is_judged_by_observation(self):
        policy = Policy(300 * self.S, 600 * self.S)
        queued = [self.rec(100 * i, 100 * i + 1, 100 * i + 2, 100 * i + 3, 100 * i + 4) for i in range(1, 6)]
        delivered = apply_outages(queued, [(0, 1000 * self.S)])
        self.assertTrue(all(r.receive_ns == 1000 * self.S for r in delivered))
        cache = DisplayCache(policy)
        for r in delivered:
            cache.receive(r, 1000 * self.S)
        self.assertEqual(cache.view(1000 * self.S)["state"], "aging")
        dropped = apply_outages(queued, [(0, 1000 * self.S)], deliver_at_reconnect=False)
        self.assertTrue(all(r.receive_ns is None for r in dropped))
        self.assertFalse(cache.receive(dropped[0], 1000 * self.S))

    def test_out_of_order_and_unreceived_records_are_not_adopted(self):
        cache = DisplayCache(Policy(10 * self.S, 20 * self.S))
        self.assertEqual(cache.view(0)["reason"], "NO_OBSERVATION")
        self.assertTrue(cache.receive(self.rec(10, 11, 12, 13, 14), 14 * self.S))
        self.assertFalse(cache.receive(self.rec(5, 6, 7, 8, 9), 15 * self.S))
        self.assertFalse(cache.receive(self.rec(20, 21, 22, 23, None), 30 * self.S))
        self.assertFalse(cache.receive(self.rec(20, 21, 22, 23, 99), 30 * self.S))
        self.assertEqual(cache.view(15 * self.S)["age_ns"], 5 * self.S)

    def test_summaries(self):
        records = [self.rec(0, d, d + 1, d + 2, d + 3) for d in range(1, 21)]
        summary = stage_summary(records)
        self.assertEqual(summary["stages"]["transport"], {"n": 20, "p50": 10 * self.S,
                                                          "p95": 19 * self.S, "max": 20 * self.S})
        self.assertEqual(summary["order_violations"], 0)
        self.assertEqual(summarize([5]), {"n": 1, "p50": 5, "p95": 5, "max": 5})
        bad = stage_summary([self.rec(0, 5, 4, 9, 12)])
        self.assertEqual(bad["order_violations"], 1)
        self.assertEqual(bad["stages"]["estimation"]["max"], -self.S)

    def test_invalid_inputs(self):
        for args in [(Record(1.0, 1, 1, 1, 1, "monotonic_local"),), (Record(1, 1, 1, 1, 1, "wall"),),
                     (Record(True, 1, 1, 1, 1, "monotonic_local"),)]:
            with self.assertRaises(ValueError):
                stage_delays(*args)
        for policy in (Policy(5, 4), Policy(-1, 4), Policy(1, 2, -1), Policy(1.0, 2)):
            with self.assertRaises(ValueError):
                DisplayCache(policy)
        for outages in ([(5, 5)], [(0, 10), (5, 20)], [(1.0, 2)]):
            with self.assertRaises(ValueError):
                apply_outages([], outages)
        with self.assertRaises(ValueError):
            summarize([])


if __name__ == "__main__":
    unittest.main()
