# SPDX-License-Identifier: MIT OR Apache-2.0
"""Water-budget closure with uncertainty (synthetic tests only).

Residual r = dS - (P + I + Qin - ET - Qout), every term a depth in mm over ONE declared
area and interval. Closure is judged against the propagated standard uncertainty;
omitted flows (groundwater exchange, leakage) must be declared as bounds, never
silently set to zero. A closed budget does not establish ecological validity.
"""
from dataclasses import dataclass
import math
import re
import unittest

COEF = {"dS": 1.0, "P": -1.0, "I": -1.0, "Qin": -1.0, "ET": 1.0, "Qout": 1.0}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")


@dataclass(frozen=True)
class Term:
    value: float
    u: float
    unit: str = "mm"
    source_ids: tuple = ()


@dataclass(frozen=True)
class Omitted:
    name: str
    lo: float
    hi: float


@dataclass(frozen=True)
class Basis:
    area_m2: float
    interval_s: int


def _fin(v):
    return type(v) in (int, float) and math.isfinite(v)


def volume_to_depth_mm(volume_m3, area_m2):
    if not (_fin(volume_m3) and _fin(area_m2)) or area_m2 <= 0:
        raise ValueError("volume")
    return volume_m3 / area_m2 * 1000.0


def residual(terms, basis, k=2.0, correlations=None, omitted=()):
    if not (isinstance(basis, Basis) and _fin(basis.area_m2) and basis.area_m2 > 0
            and type(basis.interval_s) is int and basis.interval_s > 0 and _fin(k) and k > 0):
        raise ValueError("basis")
    if type(terms) is not dict or set(terms) != set(COEF):
        raise ValueError("terms")
    for t in terms.values():
        if not (isinstance(t, Term) and _fin(t.value) and _fin(t.u) and t.u >= 0 and t.unit == "mm"
                and type(t.source_ids) is tuple and all(type(s) is str and TOKEN.fullmatch(s) for s in t.source_ids)):
            raise ValueError("term")
    t = terms
    r = t["dS"].value - (t["P"].value + t["I"].value + t["Qin"].value - t["ET"].value - t["Qout"].value)
    var = sum(x.u ** 2 for x in terms.values())
    shares = {n: (x.u ** 2 / var if var > 0 else 0.0) for n, x in terms.items()}
    for (a, b), rho in (correlations or {}).items():
        if a not in COEF or b not in COEF or a == b or not _fin(rho) or not -1 <= rho <= 1:
            raise ValueError("correlations")
        var += 2 * COEF[a] * COEF[b] * rho * terms[a].u * terms[b].u
    if var < -1e-12:
        raise ValueError("variance")
    u_r = math.sqrt(max(var, 0.0))
    lo = hi = 0.0
    for o in omitted:
        if not (isinstance(o, Omitted) and TOKEN.fullmatch(o.name) and _fin(o.lo) and _fin(o.hi) and o.lo <= o.hi):
            raise ValueError("omitted")
        lo, hi = lo + o.lo, hi + o.hi
    seen, dup = {}, set()
    for n, x in terms.items():
        for s in x.source_ids:
            if s in seen and seen[s] != n:
                dup.add(s)
            seen.setdefault(s, n)
    gap = 0.0 if r - hi <= 0 <= r - lo else min(abs(r - hi), abs(r - lo))
    if abs(r) <= k * u_r:
        status = "closed_within_uncertainty"
    elif omitted and gap <= k * u_r:
        status = "closable_by_declared_omitted_flows"
    else:
        status = "not_closed"
    return {"residual_mm": r, "u_residual_mm": u_r, "status": status, "variance_shares": shares,
            "flags": ("DOUBLE_COUNT_RISK",) if dup else (), "double_counted_sources": tuple(sorted(dup)),
            "basis_note": "all terms are mm over the declared area and interval"}


def savings_credibility(res_a, res_b, saving_mm, u_saving_mm, k=2.0):
    if not (_fin(saving_mm) and _fin(u_saving_mm) and u_saving_mm >= 0 and _fin(k) and k > 0):
        raise ValueError("savings")
    if res_a["status"] != "closed_within_uncertainty" or res_b["status"] != "closed_within_uncertainty":
        return "not_credible_budget_not_closed"
    return "credible_under_declared_model" if abs(saving_mm) > k * u_saving_mm else "within_uncertainty"


class Tests(unittest.TestCase):
    B = Basis(2000.0, 86400)

    def terms(self, dS=13.0, **over):
        base = {"P": Term(10, 1), "I": Term(50, 2), "Qin": Term(5, 0.5), "ET": Term(40, 4), "Qout": Term(15, 1),
                "dS": Term(dS, 1)}
        base.update(over)
        return base

    def test_residual_arithmetic_propagation_and_dominance(self):
        r = residual(self.terms(), self.B)
        self.assertAlmostEqual(r["residual_mm"], 3.0)
        self.assertAlmostEqual(r["u_residual_mm"], math.sqrt(23.25))
        self.assertEqual(r["status"], "closed_within_uncertainty")
        self.assertAlmostEqual(sum(r["variance_shares"].values()), 1.0)
        self.assertEqual(max(r["variance_shares"], key=r["variance_shares"].get), "ET")
        self.assertAlmostEqual(r["variance_shares"]["ET"], 16 / 23.25)
        self.assertAlmostEqual(residual(self.terms(dS=10.0), self.B)["residual_mm"], 0.0)

    def test_closure_boundary_is_inclusive(self):
        zero = {n: Term(0, 0) for n in COEF}
        t = {**zero, "P": Term(10, 3), "ET": Term(5, 4), "dS": Term(15, 0)}
        self.assertEqual(residual(t, self.B)["status"], "closed_within_uncertainty")
        t["dS"] = Term(15.000001, 0)
        self.assertEqual(residual(t, self.B)["status"], "not_closed")
        t["dS"] = Term(15, 0)
        self.assertEqual(residual(t, self.B, k=1.9999)["status"], "not_closed")

    def test_declared_omitted_flows_can_explain_a_residual_but_not_silently(self):
        t = self.terms(dS=30.0)
        self.assertEqual(residual(t, self.B)["status"], "not_closed")
        self.assertEqual(residual(t, self.B, omitted=(Omitted("groundwater", 10, 25),))["status"],
                         "closable_by_declared_omitted_flows")
        self.assertEqual(residual(t, self.B, omitted=(Omitted("leakage", 0, 5),))["status"], "not_closed")
        two = residual(t, self.B, omitted=(Omitted("groundwater", 5, 10), Omitted("leakage", 5, 15)))
        self.assertEqual(two["status"], "closable_by_declared_omitted_flows")

    def test_correlated_errors_change_the_uncertainty(self):
        zero = {n: Term(0, 0) for n in COEF}
        t = {**zero, "P": Term(1, 1), "I": Term(1, 2)}
        self.assertAlmostEqual(residual(t, self.B)["u_residual_mm"], math.sqrt(5))
        self.assertAlmostEqual(residual(t, self.B, correlations={("P", "I"): 1.0})["u_residual_mm"], 3.0)
        self.assertAlmostEqual(residual(t, self.B, correlations={("P", "I"): -1.0})["u_residual_mm"], 1.0)
        self.assertAlmostEqual(residual({**zero, "P": Term(1, 1), "ET": Term(1, 2)}, self.B,
                                        correlations={("P", "ET"): 1.0})["u_residual_mm"], 1.0)

    def test_double_counted_irrigation_is_flagged(self):
        t = self.terms(P=Term(10, 1, source_ids=("gauge1",)), I=Term(50, 2, source_ids=("meter7",)),
                       Qin=Term(5, 0.5, source_ids=("meter7",)))
        r = residual(t, self.B)
        self.assertEqual((r["flags"], r["double_counted_sources"]), (("DOUBLE_COUNT_RISK",), ("meter7",)))
        self.assertEqual(residual(self.terms(), self.B)["flags"], ())

    def test_volume_conversion_and_savings_credibility(self):
        self.assertAlmostEqual(volume_to_depth_mm(5000, 2000), 2500.0)
        closed = residual(self.terms(), self.B)
        open_ = residual(self.terms(dS=30.0), self.B)
        self.assertEqual(savings_credibility(closed, closed, 12, 4), "credible_under_declared_model")
        self.assertEqual(savings_credibility(closed, closed, 8, 4), "within_uncertainty")
        self.assertEqual(savings_credibility(closed, open_, 12, 4), "not_credible_budget_not_closed")

    def test_invalid_inputs(self):
        for kw in (dict(basis=Basis(0, 5)), dict(basis=Basis(10, 0)), dict(basis=Basis(10, 1.5)), dict(basis="b")):
            args = dict(terms=self.terms(), basis=self.B)
            args.update(kw)
            with self.assertRaises(ValueError):
                residual(**args)
        bad = [self.terms(P=Term(1, -1)), self.terms(P=Term(1, 1, unit="in")), self.terms(P=Term(float("nan"), 1)),
               self.terms(P=Term(1, 1, source_ids=("x\n",))), {k: v for k, v in self.terms().items() if k != "P"}]
        for t in bad:
            with self.assertRaises(ValueError):
                residual(t, self.B)
        for kw in (dict(correlations={("P", "P"): 0.5}), dict(correlations={("P", "I"): 2.0}),
                   dict(correlations={("P", "Z"): 0.1}), dict(omitted=(Omitted("g", 5, 1),)), dict(k=0)):
            with self.assertRaises(ValueError):
                residual(self.terms(), self.B, **kw)
        self.assertAlmostEqual(volume_to_depth_mm(-500, 2000), -250.0)
        for args in ((10, -5), (10, 0), (float("nan"), 10)):
            with self.assertRaises(ValueError):
                volume_to_depth_mm(*args)


if __name__ == "__main__":
    unittest.main()
