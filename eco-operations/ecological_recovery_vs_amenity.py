# SPDX-License-Identifier: MIT OR Apache-2.0
"""Separate evidence statuses for amenity cooling versus ecological recovery (synthetic only).

Five indicator categories are judged on their own and never combined into a score.
A cooling or shade benefit is reported as an amenity finding. An ecological-recovery
finding needs repeated visits showing BOTH habitat structure and native-species
observations moving toward a documented reference, a qualified review of that
reference, and maintenance disturbance below a declared limit. A reference may never
be a baseline imposed on people. No biodiversity-recovery claim is authorized here.
"""
from dataclasses import dataclass
import math
import re
import unittest

CATEGORIES = ("temperature_modification", "water_demand", "habitat_structure", "native_species",
              "maintenance_disturbance")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
Z95 = 1.959963984540054


@dataclass(frozen=True)
class Series:
    intervention: tuple
    reference: tuple
    visit_days: tuple
    unit: str


@dataclass(frozen=True)
class Reference:
    site: str
    rationale_documented: bool
    reviewed_by_qualified_ecologist: bool
    imposes_restriction_on_people: bool


def _check(s):
    ok = (isinstance(s, Series) and type(s.unit) is str and TOKEN.fullmatch(s.unit)
          and all(type(t) is tuple for t in (s.intervention, s.reference, s.visit_days))
          and len(s.intervention) == len(s.reference) == len(s.visit_days) >= 1
          and all(type(v) is int for v in s.visit_days)
          and all(b > a for a, b in zip(s.visit_days, s.visit_days[1:]))
          and all(type(v) in (int, float) and math.isfinite(v) for v in s.intervention + s.reference))
    if not ok:
        raise ValueError("series")


def _slope_and_se(y):
    n = len(y)
    xb, yb = (n - 1) / 2, sum(y) / n
    sxx = sum((i - xb) ** 2 for i in range(n))
    slope = sum((i - xb) * (v - yb) for i, v in enumerate(y)) / sxx
    sse = sum((v - yb - slope * (i - xb)) ** 2 for i, v in enumerate(y))
    return slope, math.sqrt(sse / (n - 2) / sxx)


def trend_to_reference(s, min_visits=6, z=Z95):
    """Is the absolute distance to the reference shrinking across repeated visits?"""
    _check(s)
    if type(min_visits) is not int or min_visits < 3 or z <= 0:
        raise ValueError("options")
    if len(s.visit_days) < min_visits:
        return "insufficient_visits"
    slope, se = _slope_and_se([abs(a - b) for a, b in zip(s.intervention, s.reference)])
    if slope < 0 and abs(slope) > z * se:
        return "toward_reference"
    if slope > 0 and slope > z * se:
        return "away_from_reference"
    return "no_clear_change"


def paired_difference(s, min_visits=6, z=Z95):
    """Mean intervention-minus-reference difference with a paired standard error."""
    _check(s)
    n = len(s.visit_days)
    if n < min_visits or z <= 0:
        return {"status": "insufficient_visits", "mean": None, "se": None}
    d = [a - b for a, b in zip(s.intervention, s.reference)]
    mean = sum(d) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1) / n)
    status = "lower_than_reference" if mean < 0 and abs(mean) > z * se else (
        "higher_than_reference" if mean > 0 and mean > z * se else "no_clear_difference")
    return {"status": status, "mean": mean, "se": se}


def assess(evidence, ref, disturbance_limit, min_visits=6):
    if type(evidence) is not dict or not set(evidence) <= set(CATEGORIES) or not isinstance(ref, Reference) \
            or not (type(disturbance_limit) in (int, float) and disturbance_limit > 0):
        raise ValueError("assess inputs")
    out = {"amenity_cooling": "not_provided", "water_demand_burden": "not_provided"}
    if "temperature_modification" in evidence:
        r = paired_difference(evidence["temperature_modification"], min_visits)
        out["amenity_cooling"] = {"lower_than_reference": "cooling_observed", "insufficient_visits": "insufficient_visits"
                                  }.get(r["status"], "cooling_not_observed")
    if "water_demand" in evidence:
        r = paired_difference(evidence["water_demand"], min_visits)
        out["water_demand_burden"] = {"higher_than_reference": "HIGHER_THAN_REFERENCE",
                                      "insufficient_visits": "insufficient_visits"}.get(r["status"], "not_higher_than_reference")
    reasons = []
    if ref.imposes_restriction_on_people is not False:
        reasons.append("E_BASELINE_IMPOSED_ON_PEOPLE")
    if ref.rationale_documented is not True:
        reasons.append("REFERENCE_RATIONALE_MISSING")
    if ref.reviewed_by_qualified_ecologist is not True:
        reasons.append("NO_QUALIFIED_REVIEW")
    species = trend_to_reference(evidence["native_species"], min_visits) if "native_species" in evidence else "not_provided"
    habitat = trend_to_reference(evidence["habitat_structure"], min_visits) if "habitat_structure" in evidence else "not_provided"
    disturbed = None
    if "maintenance_disturbance" in evidence:
        _check(evidence["maintenance_disturbance"])
        vals = evidence["maintenance_disturbance"].intervention
        disturbed = sum(vals) / len(vals) >= disturbance_limit
    if habitat == "toward_reference" and species not in ("toward_reference", "insufficient_visits", "not_provided"):
        reasons.append("HABITAT_STRUCTURE_WITHOUT_SPECIES_EVIDENCE")
    if disturbed:
        reasons.append("DISTURBANCE_CONFOUNDS_RECOVERY")
    missing = {species, habitat} & {"insufficient_visits", "not_provided"} or disturbed is None
    if any(r.startswith("E_") for r in reasons) or "DISTURBANCE_CONFOUNDS_RECOVERY" in reasons:
        recovery = "not_assessable"
    elif missing:
        recovery = "recovery_unresolved"
    elif species == habitat == "toward_reference" and not reasons:
        recovery = "recovery_supported_under_review"
    else:
        recovery = "recovery_not_demonstrated"
    out.update(native_species=species, habitat_structure=habitat, ecological_recovery=recovery,
               reasons=tuple(reasons), combined_score=None, biodiversity_claim_authorized=False)
    return out


class Tests(unittest.TestCase):
    D = tuple(range(0, 80, 10))
    GOOD_REF = Reference("reference woodland", True, True, False)

    def s(self, a, b, unit="count"):
        return Series(tuple(a), tuple(b), self.D[:len(a)], unit)

    def evidence(self, species=(2, 3, 3, 5, 6, 7, 8, 9), habitat=(1, 1, 2, 2, 3, 3, 3, 4), dist=(0, 1, 0, 0, 1, 0, 0, 0)):
        return {"temperature_modification": self.s([30, 31] * 4, [34] * 8, "degC"),
                "water_demand": self.s([60, 62, 61, 63] * 2, [40] * 8, "mm"),
                "habitat_structure": self.s(habitat, [4] * 8), "native_species": self.s(species, [10] * 8),
                "maintenance_disturbance": self.s(dist, [0] * 8, "events")}

    def test_full_evidence_supports_recovery_under_review_but_never_authorizes_a_claim(self):
        r = assess(self.evidence(), self.GOOD_REF, 1.0)
        self.assertEqual((r["ecological_recovery"], r["amenity_cooling"], r["reasons"]),
                         ("recovery_supported_under_review", "cooling_observed", ()))
        self.assertIsNone(r["combined_score"])
        self.assertFalse(r["biodiversity_claim_authorized"])
        self.assertEqual(r["water_demand_burden"], "HIGHER_THAN_REFERENCE")

    def test_cooling_without_species_evidence_is_amenity_not_recovery(self):
        r = assess(self.evidence(species=(5,) * 8), self.GOOD_REF, 1.0)
        self.assertEqual((r["amenity_cooling"], r["native_species"], r["habitat_structure"]),
                         ("cooling_observed", "no_clear_change", "toward_reference"))
        self.assertEqual(r["ecological_recovery"], "recovery_not_demonstrated")
        self.assertIn("HABITAT_STRUCTURE_WITHOUT_SPECIES_EVIDENCE", r["reasons"])

    def test_trend_statuses_and_visit_boundary(self):
        self.assertEqual(trend_to_reference(self.s(range(2, 10), [10] * 8)), "toward_reference")
        self.assertEqual(trend_to_reference(self.s(range(9, 1, -1), [10] * 8)), "away_from_reference")
        self.assertEqual(trend_to_reference(self.s([5] * 8, [10] * 8)), "no_clear_change")
        self.assertEqual(trend_to_reference(self.s([2, 4, 5, 7, 8, 9], [10] * 6)), "toward_reference")
        self.assertEqual(trend_to_reference(self.s([2, 4, 5, 7, 8], [10] * 5)), "insufficient_visits")
        self.assertEqual(trend_to_reference(self.s([2, 4, 5, 7, 8], [10] * 5), min_visits=5), "toward_reference")

    def test_short_records_leave_recovery_unresolved(self):
        ev = self.evidence()
        ev["native_species"] = self.s([2, 4, 5, 7, 8], [10] * 5)
        self.assertEqual(assess(ev, self.GOOD_REF, 1.0)["ecological_recovery"], "recovery_unresolved")
        ev = self.evidence()
        del ev["native_species"]
        self.assertEqual(assess(ev, self.GOOD_REF, 1.0)["ecological_recovery"], "recovery_unresolved")
        ev = self.evidence()
        del ev["maintenance_disturbance"]
        self.assertEqual(assess(ev, self.GOOD_REF, 1.0)["ecological_recovery"], "recovery_unresolved")

    def test_reference_problems_and_disturbance_block_assessment(self):
        for ref, code in ((Reference("r", True, True, True), "E_BASELINE_IMPOSED_ON_PEOPLE"),
                          (Reference("r", False, True, False), "REFERENCE_RATIONALE_MISSING"),
                          (Reference("r", True, False, False), "NO_QUALIFIED_REVIEW")):
            r = assess(self.evidence(), ref, 1.0)
            self.assertIn(code, r["reasons"])
            if code.startswith("E_"):
                self.assertEqual(r["ecological_recovery"], "not_assessable")
            else:
                self.assertEqual(r["ecological_recovery"], "recovery_not_demonstrated")
        busy = assess(self.evidence(dist=(2,) * 8), self.GOOD_REF, 1.0)
        self.assertEqual((busy["ecological_recovery"], busy["reasons"]), ("not_assessable", ("DISTURBANCE_CONFOUNDS_RECOVERY",)))
        edge = assess(self.evidence(dist=(1,) * 8), self.GOOD_REF, 1.0)
        self.assertEqual(edge["ecological_recovery"], "not_assessable")
        self.assertEqual(assess(self.evidence(dist=(1,) * 8), self.GOOD_REF, 1.01)["ecological_recovery"],
                         "recovery_supported_under_review")

    def test_paired_difference_and_cooling_statuses(self):
        r = paired_difference(self.s([30, 31] * 4, [34] * 8))
        self.assertAlmostEqual(r["mean"], -3.5)
        self.assertEqual(r["status"], "lower_than_reference")
        self.assertEqual(paired_difference(self.s([34, 35] * 4, [34] * 8))["status"], "higher_than_reference")
        self.assertEqual(paired_difference(self.s([33, 35] * 4, [34] * 8))["status"], "no_clear_difference")
        ev = self.evidence()
        ev["temperature_modification"] = self.s([34, 33, 35, 34, 34, 35, 33, 34], [34] * 8)
        self.assertEqual(assess(ev, self.GOOD_REF, 1.0)["amenity_cooling"], "cooling_not_observed")

    def test_invalid_inputs(self):
        bad = [Series((1.0,), (1.0, 2.0), (1,), "u"), Series((1.0, 2.0), (1.0, 2.0), (2, 2), "u"),
               Series((float("nan"),), (1.0,), (1,), "u"), Series((True,), (1.0,), (1,), "u"),
               Series((1.0,), (1.0,), (1.5,), "u"), Series((1.0,), (1.0,), (1,), "x\n"), "series"]
        for s in bad:
            with self.assertRaises(ValueError):
                trend_to_reference(s)
        with self.assertRaises(ValueError):
            assess({"unknown": self.s([1], [1])}, self.GOOD_REF, 1.0)
        with self.assertRaises(ValueError):
            assess({}, "ref", 1.0)
        with self.assertRaises(ValueError):
            assess({}, self.GOOD_REF, 0)
        with self.assertRaises(ValueError):
            trend_to_reference(self.s([1, 2, 3], [1, 1, 1]), min_visits=2)


if __name__ == "__main__":
    unittest.main()
