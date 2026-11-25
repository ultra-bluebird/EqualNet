# SPDX-License-Identifier: MIT OR Apache-2.0
"""Camera-necessity trade study over declared evidence. Local comparison only.

No aggregate score is computed. Privacy exposure ranks are a declared ordinal
convention, not a measurement of any person, consent, or psychological state.
"""
from dataclasses import dataclass
import math
import random
import re
import unittest

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
DATA_CLASSES = ("aggregate_count_only", "non_image_signal",
                "transient_image_edge", "image_retained")
CAMERA_RANK = 2


def _num(value):
    if type(value) not in (int, float):
        raise ValueError("number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("number")
    return result


def _token(value):
    return type(value) is str and TOKEN.fullmatch(value) is not None


@dataclass(frozen=True)
class Requirement:
    scenarios: tuple
    max_mean_abs_error: float
    max_abs_bias: float
    burden_units: dict
    min_trials: int = 30
    z: float = 1.645


@dataclass(frozen=True)
class Candidate:
    name: str
    data_class: str
    errors: dict
    burdens: dict


def _check_requirement(req):
    if not isinstance(req, Requirement):
        raise ValueError("requirement")
    ok = (type(req.scenarios) is tuple and req.scenarios
          and all(_token(s) for s in req.scenarios)
          and len(set(req.scenarios)) == len(req.scenarios)
          and _num(req.max_mean_abs_error) > 0 and _num(req.max_abs_bias) >= 0
          and type(req.burden_units) is dict
          and all(_token(k) and _token(v) for k, v in req.burden_units.items())
          and type(req.min_trials) is int and req.min_trials >= 2 and _num(req.z) > 0)
    if not ok:
        raise ValueError("requirement")


def _check_candidate(c, req):
    if not isinstance(c, Candidate) or not _token(c.name) or c.data_class not in DATA_CLASSES:
        raise ValueError("candidate")
    if type(c.errors) is not dict or type(c.burdens) is not dict:
        raise ValueError("candidate")
    for scenario, values in c.errors.items():
        if not _token(scenario) or type(values) not in (tuple, list):
            raise ValueError("candidate")
        for v in values:
            _num(v)
    for name, value in c.burdens.items():
        if name not in req.burden_units:
            raise ValueError("candidate")
        if value is not None and _num(value) < 0:
            raise ValueError("candidate")


def scenario_result(errors, req):
    """Errors are estimate minus reference, in persons per trial. Trials are
    treated as independent; dependence between trials is not modelled."""
    n = len(errors)
    if n < req.min_trials:
        return {"status": "undetermined", "n": n}
    e = [float(v) for v in errors]
    a = [abs(v) for v in e]
    mean_e, mae = sum(e) / n, sum(a) / n
    se_a = math.sqrt(sum((v - mae) ** 2 for v in a) / (n - 1)) / math.sqrt(n)
    se_e = math.sqrt(sum((v - mean_e) ** 2 for v in e) / (n - 1)) / math.sqrt(n)
    mae_lo, mae_hi = mae - req.z * se_a, mae + req.z * se_a
    bias_lo, bias_hi = abs(mean_e) - req.z * se_e, abs(mean_e) + req.z * se_e
    if mae_lo > req.max_mean_abs_error or bias_lo > req.max_abs_bias:
        status = "fails"
    elif mae_hi <= req.max_mean_abs_error and bias_hi <= req.max_abs_bias:
        status = "meets"
    else:
        status = "undetermined"
    return {"status": status, "n": n, "mean_abs_error": mae, "bias": mean_e,
            "mae_upper": mae_hi, "bias_abs_upper": bias_hi}


def _candidate_status(c, req):
    results = {s: scenario_result(c.errors.get(s, ()), req) for s in req.scenarios}
    states = [r["status"] for r in results.values()]
    if "fails" in states:
        overall = "fails"
    elif all(s == "meets" for s in states):
        overall = "meets"
    else:
        overall = "undetermined"
    return overall, results


def _dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def compare(req, candidates):
    """Return statuses, a Pareto front, and a necessity finding.

    A non-camera candidate that meets the requirement means camera necessity is
    not shown. Failing non-camera candidates do not establish necessity; they
    only fail this requirement on this evidence.
    """
    _check_requirement(req)
    if type(candidates) not in (list, tuple) or not candidates:
        raise ValueError("candidates")
    for c in candidates:
        _check_candidate(c, req)
    names = [c.name for c in candidates]
    if len(set(names)) != len(names):
        raise ValueError("duplicate candidate")
    burden_names = sorted(req.burden_units)
    results, vectors, incomparable = {}, {}, []
    for c in candidates:
        overall, scenarios = _candidate_status(c, req)
        results[c.name] = {"status": overall, "scenarios": scenarios,
                           "camera": DATA_CLASSES.index(c.data_class) >= CAMERA_RANK}
        if overall == "meets":
            values = [c.burdens.get(b) for b in burden_names]
            if any(v is None for v in values):
                incomparable.append(c.name)
            else:
                vectors[c.name] = (DATA_CLASSES.index(c.data_class),) + tuple(float(v) for v in values)
    dominated = {n: sorted(m for m in vectors if _dominates(vectors[m], vectors[n]))
                 for n in vectors}
    front = sorted(n for n in vectors if not dominated[n])
    non_camera = [n for n in names if not results[n]["camera"]]
    meeting_non_camera = [n for n in non_camera if results[n]["status"] == "meets"]
    if meeting_non_camera:
        finding = "camera_not_shown_necessary"
    elif not non_camera:
        finding = "unresolved_no_noncamera_candidate"
    elif all(results[n]["status"] == "fails" for n in non_camera):
        finding = "no_noncamera_candidate_meets_requirement"
    else:
        finding = "unresolved_noncamera_evidence_incomplete"
    return {"candidates": results, "pareto_front": tuple(front),
            "dominated_by": {n: tuple(v) for n, v in dominated.items() if v},
            "incomparable": tuple(sorted(incomparable)),
            "burden_order": tuple(burden_names),
            "necessity_finding": finding,
            "noncamera_meeting": tuple(meeting_non_camera),
            "camera_meeting": tuple(n for n in names if results[n]["camera"]
                                    and results[n]["status"] == "meets"),
            "selection_authorized": False}


class Tests(unittest.TestCase):
    def req(self, **changes):
        data = dict(scenarios=("normal", "occlusion"), max_mean_abs_error=0.5,
                    max_abs_bias=0.2, burden_units={"energy_kwh_per_year": "kWh",
                                                    "maintenance_hours_per_year": "h"})
        data.update(changes)
        return Requirement(**data)

    def errs(self, sd, n, seed, bias=0.0):
        rnd = random.Random(seed)
        return tuple(rnd.gauss(bias, sd) for _ in range(n))

    def cand(self, name, data_class, sd, energy=10.0, hours=5.0, n=200, seed=1, bad_scenario=None):
        errors = {"normal": self.errs(sd, n, seed), "occlusion": self.errs(sd, n, seed + 1)}
        if bad_scenario:
            errors[bad_scenario] = self.errs(1.5, n, seed + 2)
        return Candidate(name, data_class, errors,
                         {"energy_kwh_per_year": energy, "maintenance_hours_per_year": hours})

    def test_three_valued_scenario_status(self):
        req = self.req()
        self.assertEqual(scenario_result(self.errs(0.2, 200, 1), req)["status"], "meets")
        self.assertEqual(scenario_result(self.errs(1.5, 200, 1), req)["status"], "fails")
        self.assertEqual(scenario_result(self.errs(0.2, 29, 1), req)["status"], "undetermined")
        self.assertNotEqual(scenario_result(self.errs(0.2, 30, 1), req)["status"], "undetermined")

    def test_bias_alone_can_fail(self):
        req = self.req(max_mean_abs_error=5.0)
        self.assertEqual(scenario_result((1.0,) * 100, req)["status"], "fails")
        self.assertEqual(scenario_result((0.0,) * 100, req)["status"], "meets")

    def test_noncamera_meeting_means_necessity_not_shown(self):
        r = compare(self.req(), [self.cand("beam pair", "non_image_signal", 0.2),
                                 self.cand("edge camera", "transient_image_edge", 0.1, 30, 10)])
        self.assertEqual(r["necessity_finding"], "camera_not_shown_necessary")
        self.assertEqual(r["noncamera_meeting"], ("beam pair",))
        self.assertFalse(r["selection_authorized"])

    def test_failing_noncamera_does_not_prove_necessity_but_is_reported(self):
        r = compare(self.req(), [self.cand("beam pair", "non_image_signal", 0.2, bad_scenario="occlusion"),
                                 self.cand("edge camera", "transient_image_edge", 0.1, 30, 10)])
        self.assertEqual(r["necessity_finding"], "no_noncamera_candidate_meets_requirement")
        self.assertEqual(r["camera_meeting"], ("edge camera",))

    def test_incomplete_or_missing_alternatives_stay_unresolved(self):
        small = self.cand("beam pair", "non_image_signal", 0.2, n=10)
        r = compare(self.req(), [small, self.cand("edge camera", "transient_image_edge", 0.1)])
        self.assertEqual(r["necessity_finding"], "unresolved_noncamera_evidence_incomplete")
        only = compare(self.req(), [self.cand("edge camera", "transient_image_edge", 0.1)])
        self.assertEqual(only["necessity_finding"], "unresolved_no_noncamera_candidate")

    def test_pareto_front_keeps_incomparable_tradeoffs(self):
        r = compare(self.req(), [
            self.cand("beam pair", "non_image_signal", 0.2, 10, 5),
            self.cand("manual sampling", "aggregate_count_only", 0.2, 0, 200),
            self.cand("worse beam pair", "non_image_signal", 0.2, 20, 8),
            self.cand("edge camera", "transient_image_edge", 0.1, 30, 10)])
        self.assertEqual(r["pareto_front"], ("beam pair", "manual sampling"))
        self.assertEqual(r["dominated_by"]["worse beam pair"], ("beam pair",))
        self.assertEqual(r["dominated_by"]["edge camera"], ("beam pair", "worse beam pair"))

    def test_missing_burden_is_incomparable_not_zero(self):
        c = self.cand("beam pair", "non_image_signal", 0.2)
        c = Candidate(c.name, c.data_class, c.errors,
                      {"energy_kwh_per_year": 10.0, "maintenance_hours_per_year": None})
        r = compare(self.req(), [c])
        self.assertEqual(r["incomparable"], ("beam pair",))
        self.assertEqual(r["pareto_front"], ())

    def test_adding_a_camera_does_not_change_noncamera_statuses(self):
        beam = self.cand("beam pair", "non_image_signal", 0.2)
        alone = compare(self.req(), [beam])["candidates"]["beam pair"]
        both = compare(self.req(), [beam, self.cand("edge camera", "transient_image_edge", 0.1)])
        self.assertEqual(alone, both["candidates"]["beam pair"])

    def test_invalid_inputs(self):
        good = self.cand("beam pair", "non_image_signal", 0.2)
        bad_candidates = [
            Candidate("x\ny", "non_image_signal", {}, {}),
            Candidate("x", "mystery", {}, {}),
            Candidate("x", "non_image_signal", {"normal": (float("nan"),)}, {}),
            Candidate("x", "non_image_signal", {"normal": (True,)}, {}),
            Candidate("x", "non_image_signal", {}, {"unknown_burden": 1.0}),
            Candidate("x", "non_image_signal", {}, {"energy_kwh_per_year": -1.0})]
        for bad in bad_candidates:
            with self.assertRaises(ValueError):
                compare(self.req(), [bad])
        for req in (self.req(scenarios=()), self.req(scenarios=("a", "a")),
                    self.req(max_mean_abs_error=0), self.req(min_trials=1), self.req(z=0)):
            with self.assertRaises(ValueError):
                compare(req, [good])
        for cands in ([], [good, good], "x"):
            with self.assertRaises(ValueError):
                compare(self.req(), cands)


if __name__ == "__main__":
    unittest.main()
