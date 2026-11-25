# SPDX-License-Identifier: MIT OR Apache-2.0
"""Comparability tools for housing-outcome evidence tables (extraction schema and guards).

Each row is one study arm and one outcome domain, entered by a human reader from a
published report; unreported items are recorded explicitly as "not_reported", never
guessed. The tools compare arms by their ACTUAL characteristics (conditions and
supports), not by comparator labels, keep outcome domains apart, and state when
pooling is not justified. They never compute or imply an effect size.
"""
from dataclasses import dataclass
import re
import unittest

DOMAINS = ("housing_stability", "time_housed", "service_use", "substance_use")
MEASURES = ("binary_housed_at_followup", "proportion_days_housed", "days_in_shelter", "service_contacts",
            "self_reported_use_days", "other", "not_reported")
CONDITIONS = ("abstinence_required", "treatment_participation_required", "no_conditions_stated", "not_reported")
SUPPORTS = ("case_management", "clinical_services", "peer_support", "none_stated", "not_reported")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")


@dataclass(frozen=True)
class Arm:
    study: str
    arm: str
    label: str
    domain: str
    measure: str
    followup_months: int | None
    conditions: tuple
    supports: tuple
    comparator_note: str
    n_assigned: int | None


def validate_arm(a):
    ok = (isinstance(a, Arm) and all(type(v) is str and TOKEN.fullmatch(v) for v in (a.study, a.arm, a.label, a.comparator_note))
          and a.domain in DOMAINS and a.measure in MEASURES
          and (a.followup_months is None or (type(a.followup_months) is int and a.followup_months > 0))
          and type(a.conditions) is tuple and a.conditions and set(a.conditions) <= set(CONDITIONS)
          and type(a.supports) is tuple and a.supports and set(a.supports) <= set(SUPPORTS)
          and (a.n_assigned is None or (type(a.n_assigned) is int and a.n_assigned > 0)))
    if not ok:
        raise ValueError("arm")


def signature(a):
    """Characteristics only; the comparator label is deliberately excluded."""
    return tuple(sorted(set(a.conditions))), tuple(sorted(set(a.supports)))


def label_conflicts(arms):
    arms = list(arms)
    for a in arms:
        validate_arm(a)
    by_label, by_sig = {}, {}
    for a in arms:
        by_label.setdefault(a.label, set()).add(signature(a))
        by_sig.setdefault(signature(a), set()).add(a.label)
    return {"same_label_different_characteristics": sorted(l for l, s in by_label.items() if len(s) > 1),
            "different_labels_same_characteristics": sorted(tuple(sorted(l)) for l in by_sig.values() if len(l) > 1)}


def missing_report(arms):
    arms = list(arms)
    for a in arms:
        validate_arm(a)
    fields = {"measure": lambda a: a.measure == "not_reported", "followup_months": lambda a: a.followup_months is None,
              "conditions": lambda a: "not_reported" in a.conditions, "supports": lambda a: "not_reported" in a.supports,
              "n_assigned": lambda a: a.n_assigned is None}
    return {"arms": len(arms), "not_reported": {f: sum(1 for a in arms if test(a)) for f, test in fields.items()}}


def pooling_guard(arms, followup_tol_months=3):
    """Reasons pooling would not be justified. Never computes a pooled effect."""
    arms = list(arms)
    if type(followup_tol_months) is not int or followup_tol_months < 0 or not arms:
        raise ValueError("guard options")
    for a in arms:
        validate_arm(a)
    reasons = []
    if len({a.domain for a in arms}) > 1:
        reasons.append("CROSS_DOMAIN")
    if len({a.study for a in arms}) < 2:
        reasons.append("FEWER_THAN_TWO_STUDIES")
    measures = {a.measure for a in arms}
    if "not_reported" in measures:
        reasons.append("MEASURE_NOT_REPORTED")
    elif len(measures) > 1:
        reasons.append("MEASURES_DIFFER")
    months = [a.followup_months for a in arms]
    if None in months:
        reasons.append("FOLLOWUP_NOT_REPORTED")
    elif max(months) - min(months) > followup_tol_months:
        reasons.append("FOLLOWUP_SPREAD")
    if any("not_reported" in a.conditions or "not_reported" in a.supports for a in arms):
        reasons.append("CHARACTERISTICS_NOT_REPORTED")
    elif len({signature(a) for a in arms}) > 1:
        reasons.append("CHARACTERISTICS_DIFFER")
    return {"pooling_justified": not reasons, "reasons": tuple(reasons), "effect_size_computed": False}


def comparability_matrix(arms, followup_tol_months=3):
    arms = list(arms)
    for a in arms:
        validate_arm(a)
    rows = []
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            if a.domain != b.domain:
                continue
            gap = None if None in (a.followup_months, b.followup_months) else abs(a.followup_months - b.followup_months)
            rows.append({"pair": ((a.study, a.arm), (b.study, b.arm)), "domain": a.domain,
                         "same_measure": a.measure == b.measure and a.measure != "not_reported",
                         "followup_gap_months": gap,
                         "followup_within_tolerance": gap is not None and gap <= followup_tol_months,
                         "same_characteristics": signature(a) == signature(b) and "not_reported" not in signature(a)[0]
                         and "not_reported" not in signature(a)[1]})
    return rows


class Tests(unittest.TestCase):
    def arm(self, study="S1", arm="A", label="Housing First", domain="housing_stability", measure="binary_housed_at_followup",
            months=18, cond=("no_conditions_stated",), sup=("case_management",), n=100):
        return Arm(study, arm, label, domain, measure, months, cond, sup, "synthetic placeholder row", n)

    def test_labels_hide_heterogeneity_and_characteristics_expose_it(self):
        arms = [self.arm("S1", label="Treatment First", cond=("abstinence_required",)),
                self.arm("S2", label="Treatment First", cond=("treatment_participation_required",), sup=("clinical_services",)),
                self.arm("S3", label="Usual services", cond=("abstinence_required",)),
                self.arm("S4", label="Housing First")]
        c = label_conflicts(arms)
        self.assertEqual(c["same_label_different_characteristics"], ["Treatment First"])
        self.assertEqual(c["different_labels_same_characteristics"], [("Treatment First", "Usual services")])
        self.assertEqual(signature(arms[0]), (("abstinence_required",), ("case_management",)))

    def test_pooling_guard_reasons_and_boundaries(self):
        a, b = self.arm("S1"), self.arm("S2", months=21)
        self.assertEqual(pooling_guard([a, b])["reasons"], ())
        self.assertTrue(pooling_guard([a, b])["pooling_justified"])
        self.assertFalse(pooling_guard([a, b])["effect_size_computed"])
        self.assertEqual(pooling_guard([a, self.arm("S2", months=22)])["reasons"], ("FOLLOWUP_SPREAD",))
        self.assertEqual(pooling_guard([a, self.arm("S2", months=22)], followup_tol_months=4)["reasons"], ())
        cases = [([a, self.arm("S2", domain="substance_use")], "CROSS_DOMAIN"), ([a, self.arm("S1", arm="B")], "FEWER_THAN_TWO_STUDIES"),
                 ([a, self.arm("S2", measure="proportion_days_housed")], "MEASURES_DIFFER"),
                 ([a, self.arm("S2", measure="not_reported")], "MEASURE_NOT_REPORTED"),
                 ([a, self.arm("S2", months=None)], "FOLLOWUP_NOT_REPORTED"),
                 ([a, self.arm("S2", cond=("abstinence_required",))], "CHARACTERISTICS_DIFFER"),
                 ([a, self.arm("S2", cond=("not_reported",))], "CHARACTERISTICS_NOT_REPORTED")]
        for arms, code in cases:
            self.assertIn(code, pooling_guard(arms)["reasons"], code)

    def test_missing_information_is_counted_not_filled(self):
        r = missing_report([self.arm(months=None, n=None), self.arm("S2", measure="not_reported", cond=("not_reported",)),
                            self.arm("S3")])
        self.assertEqual(r["not_reported"], {"measure": 1, "followup_months": 1, "conditions": 1, "supports": 0, "n_assigned": 1})
        self.assertEqual(r["arms"], 3)

    def test_matrix_keeps_domains_apart(self):
        rows = comparability_matrix([self.arm("S1"), self.arm("S2", months=24), self.arm("S3", domain="substance_use", measure="self_reported_use_days")])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["followup_gap_months"], rows[0]["followup_within_tolerance"], rows[0]["same_measure"]), (6, False, True))
        self.assertTrue(comparability_matrix([self.arm("S1"), self.arm("S2", months=21)])[0]["followup_within_tolerance"])
        self.assertFalse(comparability_matrix([self.arm("S1"), self.arm("S2", measure="not_reported")])[0]["same_measure"])
        self.assertFalse(comparability_matrix([self.arm("S1", cond=("not_reported",)), self.arm("S2", cond=("not_reported",))])[0]["same_characteristics"])

    def test_invalid_rows(self):
        bad = [self.arm(domain="outcomes"), self.arm(measure="mystery"), self.arm(months=0), self.arm(cond=()),
               self.arm(cond=("abstinence",)), self.arm(sup=("everything",)), self.arm(n=-1), self.arm(label="x\n"), "row"]
        for a in bad:
            with self.assertRaises(ValueError):
                label_conflicts([a])
        for args in (([],), ([self.arm()], -1), ([self.arm()], 1.5)):
            with self.assertRaises(ValueError):
                pooling_guard(*args)


if __name__ == "__main__":
    unittest.main()
