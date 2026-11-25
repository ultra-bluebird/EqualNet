# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spatial representativeness of cabin sensor locations (synthetic analysis only).

Compares synchronized readings from several declared locations. Local readings
are kept; a cabin-level claim is supported only when a candidate (one location
or a subset) matches the declared reference in EVERY declared condition stratum.
There is no ground truth here: the reference is a declared weighted mean of the
sensors, and nothing infers occupancy, air safety, or any person's state.
"""
from dataclasses import dataclass
import itertools
import math
import re
import unittest

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
Z95 = 1.959963984540054
MAX_SENSORS = 12


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("number")
    return float(v)


def _token(v):
    return type(v) is str and TOKEN.fullmatch(v) is not None


@dataclass(frozen=True)
class Observations:
    times_ns: tuple
    strata: tuple
    readings: dict


def check_sync(times_by_sensor, max_skew_ns):
    """Require identical sample counts and per-sample timestamp skew within a limit."""
    if type(times_by_sensor) is not dict or len(times_by_sensor) < 2 or type(max_skew_ns) is not int \
            or max_skew_ns < 0:
        raise ValueError("sync inputs")
    series = list(times_by_sensor.values())
    if len({len(s) for s in series}) != 1 or not series[0] \
            or not all(type(t) is int for s in series for t in s):
        raise ValueError("sync samples")
    skew = max(max(col) - min(col) for col in zip(*series))
    if skew > max_skew_ns:
        raise ValueError("sync skew")
    return skew


def _validate(obs, specs, weights):
    if not isinstance(obs, Observations) or type(obs.readings) is not dict \
            or not 2 <= len(obs.readings) <= MAX_SENSORS or type(specs) is not dict \
            or set(specs) != set(obs.readings) or not all(_token(k) for k in obs.readings):
        raise ValueError("observations")
    n = len(obs.times_ns)
    if n < 2 or len(obs.strata) != n or any(len(v) != n for v in obs.readings.values()) \
            or not all(type(t) is int for t in obs.times_ns) \
            or any(b <= a for a, b in zip(obs.times_ns, obs.times_ns[1:])) \
            or not all(_token(s) for s in obs.strata):
        raise ValueError("observations")
    for v in obs.readings.values():
        for x in v:
            _num(x)
    if any(_num(u) < 0 for u in specs.values()):
        raise ValueError("specs")
    weights = weights or {k: 1.0 for k in obs.readings}
    if set(weights) != set(obs.readings) or any(_num(w) <= 0 for w in weights.values()):
        raise ValueError("weights")
    return weights


def wilson_p(p, n, z=Z95):
    """Wilson bounds for a proportion p observed with (possibly fractional) size n."""
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    den = 1 + z * z / n
    return max(0.0, (centre - margin) / den), min(1.0, (centre + margin) / den)


def effective_n(d):
    """n * (1-r1)/(1+r1) from the lag-1 autocorrelation (positive r1 only)."""
    n = len(d)
    if n < 3:
        return float(n)
    mean = sum(d) / n
    den = sum((x - mean) ** 2 for x in d)
    if den == 0:
        return float(n)
    r1 = min(0.99, sum((a - mean) * (b - mean) for a, b in zip(d, d[1:])) / den)
    return float(n) if r1 <= 0 else max(1.0, n * (1 - r1) / (1 + r1))


def _group_u(names, specs, weights):
    total = sum(weights[k] for k in names)
    return math.sqrt(sum((weights[k] * specs[k]) ** 2 for k in names)) / total


def evaluate(obs, specs, candidate, mean_tol, sample_tol, max_exceed, weights=None,
             reference="complement", z=Z95, min_samples=30):
    """Per-stratum status of a candidate (tuple of sensor names) against a reference.

    reference "all" uses the weighted mean of every sensor (it contains the
    candidate, which makes the test lenient); "complement" uses the sensors not
    in the candidate. Calibration uncertainties are treated as independent.
    """
    w = _validate(obs, specs, weights)
    names = tuple(obs.readings)
    cand = tuple(candidate)
    mt, st, me, zz = _num(mean_tol), _num(sample_tol), _num(max_exceed), _num(z)
    if (not cand or len(set(cand)) != len(cand) or not set(cand) <= set(names)
            or reference not in ("all", "complement") or mt <= 0 or st <= 0
            or not 0 < me < 1 or zz <= 0 or type(min_samples) is not int or min_samples < 3):
        raise ValueError("evaluate options")
    ref_names = names if reference == "all" else tuple(k for k in names if k not in cand)
    if not ref_names:
        raise ValueError("empty reference")
    wc = sum(w[k] for k in cand)
    wr = sum(w[k] for k in ref_names)
    d_all = [sum(w[k] * obs.readings[k][i] for k in cand) / wc
             - sum(w[k] * obs.readings[k][i] for k in ref_names) / wr
             for i in range(len(obs.times_ns))]
    u_sys = math.hypot(_group_u(cand, specs, w), _group_u(ref_names, specs, w))
    report, failing = {}, []
    for label in sorted(set(obs.strata)):
        d = [x for x, s in zip(d_all, obs.strata) if s == label]
        n = len(d)
        if n < min_samples:
            report[label] = {"status": "undetermined", "n": n, "reason": "TOO_FEW_SAMPLES"}
            failing.append(label)
            continue
        mean = sum(d) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
        n_eff = effective_n(d)
        spread = zz * math.hypot(sd / math.sqrt(n_eff), u_sys)
        bias_lo, bias_hi = max(0.0, abs(mean) - spread), abs(mean) + spread
        frac = sum(abs(x) > st for x in d) / n
        ex_lo, ex_hi = wilson_p(frac, n_eff, zz)
        if bias_lo > mt or ex_lo > me:
            status = "does_not_represent"
        elif bias_hi <= mt and ex_hi <= me:
            status = "represents"
        else:
            status = "undetermined"
        if status != "represents":
            failing.append(label)
        report[label] = {"status": status, "n": n, "n_eff": n_eff, "mean_discrepancy": mean,
                         "bias_upper": bias_hi, "exceed_fraction": frac, "exceed_upper": ex_hi}
    pooled_mean = sum(d_all) / len(d_all)
    pooled_frac = sum(abs(x) > st for x in d_all) / len(d_all)
    return {"strata": report, "failing": tuple(failing),
            "claim_scope": "local_only" if failing else "cabin_level_supported",
            "pooled_for_comparison_only": {"n": len(d_all), "mean_discrepancy": pooled_mean,
                                           "exceed_fraction": pooled_frac},
            "publication_authorized": False}


def slice_obs(obs, start, stop):
    return Observations(obs.times_ns[start:stop], obs.strata[start:stop],
                        {k: v[start:stop] for k, v in obs.readings.items()})


def search(obs, specs, size, holdout=False, **options):
    """Evaluate every subset of the given size; optionally select on the first half
    and re-evaluate the selected subsets on the second half (selection on the same
    data that judges it is optimistic)."""
    names = tuple(obs.readings)
    if type(size) is not int or not 1 <= size < len(names):
        raise ValueError("size")
    fit, test = (slice_obs(obs, 0, len(obs.times_ns) // 2), slice_obs(obs, len(obs.times_ns) // 2, None)) \
        if holdout else (obs, None)
    rows = []
    for subset in itertools.combinations(names, size):
        row = {"subset": subset, "fit": evaluate(fit, specs, subset, **options)}
        if holdout and row["fit"]["claim_scope"] == "cabin_level_supported":
            row["test"] = evaluate(test, specs, subset, **options)
        rows.append(row)
    return {"rows": rows,
            "supported_on_fit": tuple(r["subset"] for r in rows
                                      if r["fit"]["claim_scope"] == "cabin_level_supported"),
            "supported_on_test": None if not holdout else tuple(
                r["subset"] for r in rows if r.get("test", {}).get("claim_scope") == "cabin_level_supported")}


class Tests(unittest.TestCase):
    OPT = dict(mean_tol=25.0, sample_tol=45.0, max_exceed=0.1, reference="all")
    SPECS = {"mid": 2.0, "rear": 2.0, "front": 2.0, "door": 2.0}

    @staticmethod
    def synth(seed=3, n=1200, door_drop=150.0, specs_noise=5.0):
        import random
        rnd = random.Random(seed)
        strata, readings = [], {k: [] for k in ("mid", "rear", "front", "door")}
        for t in range(n):
            door_open = 150 <= t % 400 < 180
            strata.append("door_open" if door_open else "closed")
            base = 800 + 100 * math.sin(2 * math.pi * t / 900)
            for k, off in (("mid", 0.0), ("rear", 30.0), ("front", -10.0), ("door", 5.0)):
                v = base + off + rnd.gauss(0, specs_noise)
                if k == "door" and door_open:
                    v -= door_drop
                readings[k].append(v)
        return Observations(tuple(range(n)), tuple(strata), {k: tuple(v) for k, v in readings.items()})

    def test_door_sensor_represents_when_closed_but_not_when_open(self):
        obs = self.synth()
        r = evaluate(obs, self.SPECS, ("door",), **self.OPT)
        self.assertEqual(r["strata"]["closed"]["status"], "represents")
        self.assertEqual(r["strata"]["door_open"]["status"], "does_not_represent")
        self.assertEqual((r["claim_scope"], r["failing"]), ("local_only", ("door_open",)))
        self.assertFalse(r["publication_authorized"])

    def test_pooled_figures_look_acceptable_while_a_stratum_fails(self):
        r = evaluate(self.synth(), self.SPECS, ("door",), **self.OPT)
        pooled = r["pooled_for_comparison_only"]
        self.assertLess(pooled["exceed_fraction"], self.OPT["max_exceed"])
        self.assertLess(abs(pooled["mean_discrepancy"]), self.OPT["mean_tol"])
        self.assertEqual(r["strata"]["door_open"]["exceed_fraction"], 1.0)

    def test_no_single_location_is_established_everywhere(self):
        obs = self.synth()
        for name in obs.readings:
            r = evaluate(obs, self.SPECS, (name,), **self.OPT)
            self.assertNotEqual(r["claim_scope"], "cabin_level_supported", name)

    def test_size_three_subsets_with_the_door_sensor_match_the_declared_reference(self):
        found = search(self.synth(), self.SPECS, 3, **self.OPT)
        self.assertEqual(set(found["supported_on_fit"]),
                         {s for s in found["supported_on_fit"] if "door" in s})
        self.assertGreaterEqual(len(found["supported_on_fit"]), 2)
        bad = [r for r in found["rows"] if "door" not in r["subset"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["fit"]["strata"]["door_open"]["status"], "does_not_represent")

    def test_holdout_selection_is_reevaluated_on_unseen_data(self):
        found = search(self.synth(n=2400), self.SPECS, 3, holdout=True, **self.OPT)
        self.assertEqual(set(found["supported_on_test"]), set(found["supported_on_fit"]))
        self.assertGreaterEqual(len(found["supported_on_test"]), 2)
        for r in found["rows"]:
            self.assertEqual("test" in r, r["fit"]["claim_scope"] == "cabin_level_supported")

    def test_too_little_unseen_data_stays_undetermined_not_supported(self):
        found = search(self.synth(n=1200), self.SPECS, 3, holdout=True, **self.OPT)
        self.assertTrue(found["supported_on_fit"])
        self.assertEqual(found["supported_on_test"], ())
        row = next(r for r in found["rows"] if r["subset"] == ("mid", "rear", "door"))
        self.assertEqual(row["test"]["strata"]["door_open"]["status"], "undetermined")

    def test_large_calibration_uncertainty_makes_a_good_match_undetermined(self):
        obs = self.synth(door_drop=0.0)
        tight = evaluate(obs, self.SPECS, ("mid",), **self.OPT)
        loose = evaluate(obs, {k: 40.0 for k in self.SPECS}, ("mid",), **self.OPT)
        self.assertEqual(tight["strata"]["closed"]["status"], "represents")
        self.assertEqual(loose["strata"]["closed"]["status"], "undetermined")
        self.assertEqual(loose["claim_scope"], "local_only")

    def test_too_few_samples_in_a_stratum_blocks_a_cabin_claim(self):
        obs = self.synth(n=500)
        r = evaluate(obs, self.SPECS, ("mid",), min_samples=200, **self.OPT)
        self.assertEqual(r["strata"]["door_open"]["reason"], "TOO_FEW_SAMPLES")
        self.assertEqual(r["claim_scope"], "local_only")

    def test_weights_change_the_reference(self):
        obs = self.synth(door_drop=0.0)
        equal = evaluate(obs, self.SPECS, ("rear",), **self.OPT)["strata"]["closed"]["mean_discrepancy"]
        heavy = evaluate(obs, self.SPECS, ("rear",), weights={"mid": 1, "rear": 1, "front": 1, "door": 20},
                         **self.OPT)["strata"]["closed"]["mean_discrepancy"]
        self.assertAlmostEqual(equal, 30 - 6.25, delta=1.0)
        self.assertAlmostEqual(heavy, 30 - (0 + 30 - 10 + 20 * 5) / 23, delta=1.0)

    def test_sync_check_and_effective_sample_size(self):
        self.assertEqual(check_sync({"a": [1, 2, 3], "b": [1, 3, 3]}, 1), 1)
        for bad in ({"a": [1, 2, 3], "b": [1, 2]}, {"a": [1, 2], "b": [1, 9]}, {"a": [1]}):
            with self.assertRaises(ValueError):
                check_sync(bad, 1)
        self.assertEqual(effective_n([1.0, -1.0] * 20), 40.0)
        self.assertLess(effective_n([float(i) for i in range(40)]), 5.0)
        self.assertEqual(effective_n([3.0] * 10), 10.0)

    def test_invalid_inputs(self):
        obs = self.synth(n=100)
        bad_obs = [Observations((1, 1), ("a", "a"), {"x": (1.0, 2.0), "y": (1.0, 2.0)}),
                   Observations((1, 2), ("a",), {"x": (1.0, 2.0), "y": (1.0, 2.0)}),
                   Observations((1, 2), ("a", "a"), {"x": (1.0, float("nan")), "y": (1.0, 2.0)}),
                   Observations((1, 2), ("a", "a"), {"x": (1.0, 2.0)})]
        for o in bad_obs:
            with self.assertRaises(ValueError):
                evaluate(o, {"x": 1.0, "y": 1.0}, ("x",), **{**self.OPT, "reference": "complement"})
        for change in (dict(mean_tol=0), dict(max_exceed=1.5), dict(reference="none"), dict(z=0)):
            with self.assertRaises(ValueError):
                evaluate(obs, self.SPECS, ("mid",), **{**self.OPT, **change})
        for cand in ((), ("nope",), ("mid", "mid")):
            with self.assertRaises(ValueError):
                evaluate(obs, self.SPECS, cand, **self.OPT)
        with self.assertRaises(ValueError):
            evaluate(obs, self.SPECS, tuple(obs.readings), **{**self.OPT, "reference": "complement"})
        with self.assertRaises(ValueError):
            search(obs, self.SPECS, 4, **self.OPT)
        with self.assertRaises(ValueError):
            evaluate(obs, {**self.SPECS, "mid": -1.0}, ("mid",), **self.OPT)


if __name__ == "__main__":
    unittest.main()
