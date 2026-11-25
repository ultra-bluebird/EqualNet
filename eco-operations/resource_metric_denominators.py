# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resource-metric ratios beside absolute burdens, with burden-shifting flags (synthetic only).

Every measurement declares a unit, a reporting period, and an accounting boundary; ratios
are computed only when all of them match. Absolute numerators and denominators are always
returned. A ratio that improves while an absolute burden rises, or while useful output
falls, is flagged and never rewarded. No value here is a measurement of a real facility.
"""
from dataclasses import dataclass
import math
import re
import unittest

UNITS = {"E_facility": "kWh", "E_it": "kWh", "W": "L", "G": "kgCO2e", "E_reused": "kWh", "service": "runs"}
REQUIRED = ("E_facility", "E_it", "W", "G")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
EPS = 1e-12


@dataclass(frozen=True)
class Measure:
    value: float
    unit: str
    period: tuple
    boundary: str


def metrics(m):
    """Return PUE, WUE, CUE, ERE and service intensity, or refuse with reason codes."""
    if type(m) is not dict or not set(REQUIRED) <= set(m) or not set(m) <= set(UNITS):
        raise ValueError("measures")
    reasons = []
    for name, x in m.items():
        if not (isinstance(x, Measure) and type(x.value) in (int, float) and math.isfinite(x.value) and x.value >= 0
                and type(x.period) is tuple and len(x.period) == 2 and all(type(v) is int for v in x.period)
                and x.period[0] < x.period[1] and type(x.boundary) is str and TOKEN.fullmatch(x.boundary)):
            raise ValueError("measure " + name)
        if x.unit != UNITS[name]:
            reasons.append("E_UNIT_" + name.upper())
    if len({x.period for x in m.values()}) > 1:
        reasons.append("E_PERIOD_MISMATCH")
    if len({x.boundary for x in m.values()}) > 1:
        reasons.append("E_BOUNDARY_MISMATCH")
    if reasons:
        return {"status": "refused", "reasons": tuple(reasons), "metrics": None, "absolute": None}
    v = {k: x.value for k, x in m.items()}
    e_it, e_fac, reused = v["E_it"], v["E_facility"], v.get("E_reused", 0.0)
    notes = []
    if e_it <= 0:
        notes.append("E_IT_NOT_POSITIVE")
    if e_fac < e_it:
        notes.append("FACILITY_ENERGY_BELOW_IT_ENERGY")
    if reused > e_fac:
        notes.append("REUSED_ENERGY_EXCEEDS_FACILITY_ENERGY")
    ok = e_it > 0 and not notes
    out = {"PUE": e_fac / e_it if ok else None, "WUE_L_per_kWh_IT": v["W"] / e_it if ok else None,
           "CUE_kg_per_kWh_IT": v["G"] / e_it if ok else None, "ERE": (e_fac - reused) / e_it if ok else None,
           "energy_per_service": e_fac / v["service"] if v.get("service", 0) > 0 else None}
    return {"status": "ok", "reasons": tuple(notes), "metrics": out, "absolute": dict(v)}


def compare(base, new):
    """Absolute and ratio changes with burden-shifting flags."""
    a, b = metrics(base), metrics(new)
    if a["status"] != "ok" or b["status"] != "ok" or a["reasons"] or b["reasons"]:
        return {"status": "refused", "reasons": ("E_UNUSABLE_INPUT",), "flags": ()}
    pa, pb = next(iter(base.values())).period, next(iter(new.values())).period
    if pa[1] - pa[0] != pb[1] - pb[0]:
        return {"status": "refused", "reasons": ("E_PERIOD_LENGTH_DIFFERS",), "flags": ()}
    ma, mb, aa, ab = a["metrics"], b["metrics"], a["absolute"], b["absolute"]
    flags = []
    for ratio, absolute in (("PUE", "E_facility"), ("ERE", "E_facility"), ("WUE_L_per_kWh_IT", "W"),
                            ("CUE_kg_per_kWh_IT", "G")):
        if mb[ratio] < ma[ratio] - EPS and ab[absolute] > aa[absolute] + EPS:
            flags.append("RATIO_IMPROVED_ABSOLUTE_WORSE_" + ratio)
    sa, sb = ma["energy_per_service"], mb["energy_per_service"]
    if sa is not None and sb is not None:
        if ab["service"] < aa["service"] - EPS:
            flags.append("SERVICE_OUTPUT_DOWN")
        if sb > sa + EPS and all(mb[r] <= ma[r] + EPS for r in ("PUE", "WUE_L_per_kWh_IT", "CUE_kg_per_kWh_IT")):
            flags.append("INTENSITY_UP_WITH_RATIOS_UNCHANGED_OR_BETTER")
    if abs(mb["PUE"] - ma["PUE"]) <= EPS and abs(ab["E_facility"] - aa["E_facility"]) <= EPS \
            and abs(mb["CUE_kg_per_kWh_IT"] - ma["CUE_kg_per_kWh_IT"]) > EPS:
        flags.append("CUE_CHANGED_WITHOUT_EFFICIENCY_CHANGE")
    return {"status": "ok", "reasons": (), "flags": tuple(flags),
            "absolute_change": {k: ab[k] - aa[k] for k in ab if k in aa},
            "ratio_change": {k: mb[k] - ma[k] for k in ma if ma[k] is not None and mb[k] is not None},
            "reward_for_extra_computation": False}


def cue_identity_check(m, emission_factor, rel_tol=1e-6):
    """CUE = PUE * EF only when G = E_facility * EF (electricity-only boundary)."""
    r = metrics(m)
    if r["status"] != "ok" or r["reasons"] or not (type(emission_factor) in (int, float) and emission_factor >= 0 and rel_tol > 0):
        raise ValueError("identity inputs")
    g, e = r["absolute"]["G"], r["absolute"]["E_facility"]
    return "electricity_only_boundary_consistent" if abs(g - e * emission_factor) <= rel_tol * max(g, EPS) \
        else "CUE_SIMPLIFICATION_INVALID"


class Tests(unittest.TestCase):
    P, BND = (0, 1), "site boundary A"

    def m(self, e_it=192.0, overhead=28.8, w=500.0, ef=0.4, service=100.0, period=None, boundary=None, **over):
        p, b = period or self.P, boundary or self.BND
        e_fac = e_it + overhead
        base = {"E_it": Measure(e_it, "kWh", p, b), "E_facility": Measure(e_fac, "kWh", p, b), "W": Measure(w, "L", p, b),
                "G": Measure(ef * e_fac, "kgCO2e", p, b), "service": Measure(service, "runs", p, b)}
        base.update(over)
        return base

    def test_ratios_and_absolutes_are_both_returned(self):
        r = metrics(self.m())
        self.assertAlmostEqual(r["metrics"]["PUE"], 1.15)
        self.assertAlmostEqual(r["metrics"]["WUE_L_per_kWh_IT"], 500 / 192)
        self.assertAlmostEqual(r["metrics"]["CUE_kg_per_kWh_IT"], 0.4 * 220.8 / 192)
        self.assertAlmostEqual(r["metrics"]["ERE"], 1.15)
        self.assertAlmostEqual(r["metrics"]["energy_per_service"], 2.208)
        self.assertEqual(r["absolute"]["W"], 500.0)
        withreuse = metrics({**self.m(), "E_reused": Measure(28.8, "kWh", self.P, self.BND)})
        self.assertAlmostEqual(withreuse["metrics"]["ERE"], 1.0)

    def test_mismatched_periods_boundaries_and_units_are_refused(self):
        w = self.m()
        w["W"] = Measure(500.0, "L", (0, 2), self.BND)
        self.assertEqual(metrics(w)["reasons"], ("E_PERIOD_MISMATCH",))
        w = self.m()
        w["W"] = Measure(500.0, "L", self.P, "site boundary B")
        self.assertEqual(metrics(w)["reasons"], ("E_BOUNDARY_MISMATCH",))
        w = self.m()
        w["E_it"] = Measure(192.0, "kW", self.P, self.BND)
        self.assertEqual(metrics(w)["reasons"], ("E_UNIT_E_IT",))
        self.assertEqual(metrics(w)["metrics"], None)

    def test_extra_computation_improves_ratios_but_raises_absolute_burden(self):
        c = compare(self.m(), self.m(e_it=292.0))
        self.assertIn("RATIO_IMPROVED_ABSOLUTE_WORSE_PUE", c["flags"])
        self.assertIn("RATIO_IMPROVED_ABSOLUTE_WORSE_CUE_kg_per_kWh_IT", c["flags"])
        self.assertNotIn("RATIO_IMPROVED_ABSOLUTE_WORSE_WUE_L_per_kWh_IT", c["flags"])
        self.assertLess(c["ratio_change"]["PUE"], 0)
        self.assertAlmostEqual(c["absolute_change"]["E_facility"], 100.0)
        self.assertFalse(c["reward_for_extra_computation"])

    def test_reduced_useful_output_is_flagged_even_when_ratios_do_not_move(self):
        c = compare(self.m(), self.m(service=50.0))
        self.assertEqual(set(c["flags"]), {"SERVICE_OUTPUT_DOWN", "INTENSITY_UP_WITH_RATIOS_UNCHANGED_OR_BETTER"})
        self.assertEqual(c["ratio_change"]["PUE"], 0.0)
        self.assertEqual(compare(self.m(), self.m(service=200.0))["flags"], ())

    def test_grid_factor_change_moves_cue_without_any_efficiency_change(self):
        c = compare(self.m(ef=0.4), self.m(ef=0.2))
        self.assertEqual(c["flags"], ("CUE_CHANGED_WITHOUT_EFFICIENCY_CHANGE",))
        self.assertLess(c["ratio_change"]["CUE_kg_per_kWh_IT"], 0)

    def test_cue_identity_depends_on_the_boundary(self):
        self.assertEqual(cue_identity_check(self.m(), 0.4), "electricity_only_boundary_consistent")
        extra_fuel = self.m(G=Measure(0.4 * 220.8 + 20.0, "kgCO2e", self.P, self.BND))
        self.assertEqual(cue_identity_check(extra_fuel, 0.4), "CUE_SIMPLIFICATION_INVALID")

    def test_comparison_refuses_different_period_lengths_and_impossible_inputs(self):
        self.assertEqual(compare(self.m(), self.m(period=(0, 2)))["reasons"], ("E_PERIOD_LENGTH_DIFFERS",))
        self.assertEqual(compare(self.m(), self.m(e_it=0.0))["reasons"], ("E_UNUSABLE_INPUT",))
        low = self.m(E_facility=Measure(100.0, "kWh", self.P, self.BND))
        self.assertIn("FACILITY_ENERGY_BELOW_IT_ENERGY", metrics(low)["reasons"])
        self.assertIsNone(metrics(low)["metrics"]["PUE"])
        over = {**self.m(), "E_reused": Measure(999.0, "kWh", self.P, self.BND)}
        self.assertIn("REUSED_ENERGY_EXCEEDS_FACILITY_ENERGY", metrics(over)["reasons"])

    def test_invalid_inputs(self):
        for bad in ({}, {"E_it": Measure(1.0, "kWh", self.P, "b")}, "m", {**self.m(), "other": Measure(1.0, "kWh", self.P, self.BND)}):
            with self.assertRaises(ValueError):
                metrics(bad)
        for x in (Measure(-1.0, "kWh", self.P, "b"), Measure(float("nan"), "kWh", self.P, "b"),
                  Measure(1.0, "kWh", (1, 1), "b"), Measure(1.0, "kWh", (0, 1.5), "b"), Measure(1.0, "kWh", self.P, "x\n"), 5):
            with self.assertRaises(ValueError):
                metrics({**self.m(), "E_it": x})
        with self.assertRaises(ValueError):
            cue_identity_check(self.m(), -1.0)


if __name__ == "__main__":
    unittest.main()
