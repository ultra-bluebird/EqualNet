# SPDX-License-Identifier: MIT OR Apache-2.0
"""Evaluation of immediate usefulness of small assistance without disclosure incentives.

Two tools, both local arithmetic on declared or aggregate inputs:
1. review_protocol: structural check of an evaluation design (no conditionality,
   separated roles, no identifying fields, non-digital channels, limited reminders).
2. Missingness-aware summaries: response is never required, so every usefulness
   figure is reported with worst-case bounds and a tipping point for the people who
   did not respond. Non-response and refusal describe the evaluation's limits; they
   say nothing about recipients, and assistance never depends on responding.
Nothing here replaces ethics review, consent, or a human reviewer.
"""
from dataclasses import dataclass
import math
import re
import unittest

MODES = ("optional_anonymous", "delayed_voluntary", "service_level")
ALLOWED_FIELDS = {"usefulness_rating", "free_text_optional", "channel_used", "service_count"}
IDENTIFYING = {"name", "email", "phone", "address", "account", "device", "location", "id",
               "diagnosis", "disability", "wallet", "gps"}
NONDIGITAL = {"paper", "verbal", "in_person", "phone_call"}
INCENTIVES = ("none", "unconditional_token", "conditional_on_response", "conditional_on_disclosure")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
Z95 = 1.959963984540054
NOTE = "response and refusal describe the evaluation's limits, not recipients; assistance never depends on responding"


@dataclass(frozen=True)
class Protocol:
    mode: str
    roles_separated: bool
    assistance_conditional_on_response: bool
    refusal_affects_service: bool
    channels: tuple
    reminders_max: int
    incentive: str
    consent_materials: tuple
    fields_collected: tuple
    delay_days: int = 0


def review_protocol(p):
    """Fixed reason codes; absence of codes is not ethical approval."""
    if not isinstance(p, Protocol):
        raise ValueError("protocol")
    reasons = []
    if p.mode not in MODES:
        reasons.append("E_MODE")
    if p.roles_separated is not True:
        reasons.append("E_ROLES_NOT_SEPARATED")
    if p.assistance_conditional_on_response is not False:
        reasons.append("E_ASSISTANCE_CONDITIONAL")
    if p.refusal_affects_service is not False:
        reasons.append("E_REFUSAL_PENALTY")
    chans = p.channels if type(p.channels) is tuple and all(
        type(c) is str and TOKEN.fullmatch(c) for c in p.channels) else None
    if chans is None or len(set(chans)) < 2 or not set(chans) & NONDIGITAL:
        reasons.append("E_CHANNELS")
    if type(p.reminders_max) is not int or not 0 <= p.reminders_max <= 1:
        reasons.append("E_REMINDERS")
    if p.incentive not in INCENTIVES:
        reasons.append("E_INCENTIVE")
    elif p.incentive == "conditional_on_response":
        reasons.append("E_RESPONSE_INCENTIVE")
    elif p.incentive == "conditional_on_disclosure":
        reasons.append("E_DISCLOSURE_INCENTIVE")
    if type(p.consent_materials) is not tuple or not p.consent_materials \
            or not all(type(c) is str and TOKEN.fullmatch(c) for c in p.consent_materials):
        reasons.append("E_CONSENT_MATERIALS")
    if type(p.fields_collected) is not tuple or not all(type(f) is str for f in p.fields_collected):
        reasons.append("E_FIELDS")
    else:
        for f in p.fields_collected:
            if f.lower() in IDENTIFYING:
                reasons.append("E_IDENTIFYING_FIELD")
            elif f not in ALLOWED_FIELDS:
                reasons.append("E_FIELD_NOT_ALLOWED")
    if type(p.delay_days) is not int or p.delay_days < 0 or (p.mode == "delayed_voluntary") != (p.delay_days > 0):
        reasons.append("E_DELAY")
    return {"structurally_consistent": not reasons, "reasons": tuple(dict.fromkeys(reasons)),
            "ethics_review_replaced": False}


def wilson(hits, n, z=Z95):
    p = hits / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    den = 1 + z * z / n
    return max(0.0, (centre - margin) / den), min(1.0, (centre + margin) / den)


def _counts(offered, responded, useful, refused=None):
    ok = all(type(v) is int for v in (offered, responded, useful)) and offered >= 1 \
        and 0 <= useful <= responded <= offered
    if refused is not None:
        ok = ok and type(refused) is int and 0 <= refused <= offered - responded
    if not ok:
        raise ValueError("counts")


def mode_summary(offered, responded, useful, refused=None, k_min=5):
    """Response rate, usefulness among respondents, and missingness-robust bounds."""
    _counts(offered, responded, useful, refused)
    if type(k_min) is not int or k_min < 2:
        raise ValueError("k_min")
    silent = offered - responded
    rate = wilson(responded, offered)
    robust_low = wilson(useful, offered)[0]
    robust_high = wilson(useful + silent, offered)[1]
    shown_refused = refused is not None and refused >= k_min and silent - refused >= k_min
    return {"offered": offered, "response_rate": responded / offered, "response_rate_interval": rate,
            "useful_among_respondents": None if responded < k_min else useful / responded,
            "useful_among_respondents_interval": None if responded < k_min else wilson(useful, responded),
            "bounds_all_nonrespondents_not_useful_to_useful": (useful / offered, (useful + silent) / offered),
            "bounds_with_sampling_uncertainty": (robust_low, robust_high),
            "refused": refused if shown_refused else None,
            "no_response": silent - refused if shown_refused else None,
            "missingness_note": NOTE}


def tipping_point(useful, responded, offered, threshold):
    """Nonrespondent usefulness rate q* at which overall usefulness equals the threshold."""
    _counts(offered, responded, useful)
    if not 0 < threshold < 1:
        raise ValueError("threshold")
    silent = offered - responded
    if useful / offered >= threshold:
        return {"classification": "holds_regardless_of_nonrespondents", "q_star": None}
    if (useful + silent) / offered < threshold:
        return {"classification": "fails_regardless_of_nonrespondents", "q_star": None}
    return {"classification": "depends_on_nonrespondents", "q_star": (threshold * offered - useful) / silent}


def compare_modes(modes, k_min=5):
    """Summaries per mode; modes are never pooled because their selection differs."""
    if type(modes) is not dict or not modes or any(k not in MODES for k in modes):
        raise ValueError("modes")
    out = {m: mode_summary(k_min=k_min, **counts) for m, counts in sorted(modes.items())}
    return {"modes": out, "pooled": None,
            "caution": "response rate is not a quality measure and modes reach different people"}


class Tests(unittest.TestCase):
    def good(self, **kw):
        base = dict(mode="optional_anonymous", roles_separated=True, assistance_conditional_on_response=False,
                    refusal_affects_service=False, channels=("paper", "web"), reminders_max=1, incentive="none",
                    consent_materials=("large print", "audio"), fields_collected=("usefulness_rating", "channel_used"))
        base.update(kw)
        return Protocol(**base)

    def test_good_design_is_consistent_but_not_approved(self):
        r = review_protocol(self.good())
        self.assertEqual((r["structurally_consistent"], r["reasons"], r["ethics_review_replaced"]), (True, (), False))
        self.assertTrue(review_protocol(self.good(mode="delayed_voluntary", delay_days=14))["structurally_consistent"])

    def test_each_violation_has_its_own_code(self):
        cases = [(dict(mode="mail"), "E_MODE"), (dict(roles_separated=False), "E_ROLES_NOT_SEPARATED"),
                 (dict(assistance_conditional_on_response=True), "E_ASSISTANCE_CONDITIONAL"),
                 (dict(refusal_affects_service=True), "E_REFUSAL_PENALTY"),
                 (dict(channels=("web", "app")), "E_CHANNELS"), (dict(channels=("paper",)), "E_CHANNELS"),
                 (dict(reminders_max=2), "E_REMINDERS"), (dict(reminders_max=-1), "E_REMINDERS"),
                 (dict(incentive="conditional_on_response"), "E_RESPONSE_INCENTIVE"),
                 (dict(incentive="conditional_on_disclosure"), "E_DISCLOSURE_INCENTIVE"),
                 (dict(incentive="cash"), "E_INCENTIVE"), (dict(consent_materials=()), "E_CONSENT_MATERIALS"),
                 (dict(fields_collected=("Email",)), "E_IDENTIFYING_FIELD"),
                 (dict(fields_collected=("favourite colour",)), "E_FIELD_NOT_ALLOWED"),
                 (dict(delay_days=3), "E_DELAY"), (dict(mode="delayed_voluntary"), "E_DELAY")]
        for change, code in cases:
            self.assertIn(code, review_protocol(self.good(**change))["reasons"], code)
        with self.assertRaises(ValueError):
            review_protocol("design")

    def test_bounds_arithmetic_and_sampling_uncertainty(self):
        s = mode_summary(100, 40, 30)
        self.assertEqual(s["bounds_all_nonrespondents_not_useful_to_useful"], (0.30, 0.90))
        self.assertAlmostEqual(s["response_rate"], 0.4)
        low, high = s["bounds_with_sampling_uncertainty"]
        self.assertLess(low, 0.30)
        self.assertGreater(high, 0.90)
        self.assertAlmostEqual(s["useful_among_respondents"], 0.75)
        self.assertIn("never depends on responding", s["missingness_note"])

    def test_tipping_point_classes(self):
        self.assertEqual(tipping_point(30, 40, 100, 0.5)["classification"], "depends_on_nonrespondents")
        self.assertAlmostEqual(tipping_point(30, 40, 100, 0.5)["q_star"], 20 / 60)
        self.assertEqual(tipping_point(60, 70, 100, 0.5)["classification"], "holds_regardless_of_nonrespondents")
        self.assertEqual(tipping_point(5, 60, 100, 0.5)["classification"], "fails_regardless_of_nonrespondents")
        self.assertEqual(tipping_point(50, 50, 100, 0.5)["classification"], "holds_regardless_of_nonrespondents")

    def test_small_counts_are_suppressed_with_complementary_suppression(self):
        self.assertIsNone(mode_summary(50, 4, 3)["useful_among_respondents"])
        self.assertIsNone(mode_summary(50, 30, 20, refused=3)["refused"])
        self.assertIsNone(mode_summary(50, 40, 20, refused=8)["refused"])
        shown = mode_summary(50, 30, 20, refused=8)
        self.assertEqual((shown["refused"], shown["no_response"]), (8, 12))
        self.assertIsNone(mode_summary(50, 30, 20)["refused"])

    def test_modes_are_never_pooled_and_language_is_neutral(self):
        out = compare_modes({"optional_anonymous": dict(offered=100, responded=20, useful=15),
                             "service_level": dict(offered=100, responded=100, useful=70)})
        self.assertIsNone(out["pooled"])
        self.assertEqual(list(out["modes"]), ["optional_anonymous", "service_level"])
        blob = repr(out).lower()
        for word in ("noncompliance", "refuser", "deficit", "lazy", "failed to respond"):
            self.assertNotIn(word, blob)

    def test_invalid_inputs(self):
        for args in ((0, 0, 0), (10, 11, 0), (10, 5, 6), (10, -1, 0), (True, 1, 1), (10.0, 5, 2)):
            with self.assertRaises(ValueError):
                mode_summary(*args)
        for kw in (dict(refused=6), dict(refused=-1), dict(k_min=1)):
            with self.assertRaises(ValueError):
                mode_summary(10, 5, 2, **kw)
        for t in (0, 1, 1.5):
            with self.assertRaises(ValueError):
                tipping_point(1, 5, 10, t)
        for bad in ({}, {"mail": dict(offered=1, responded=1, useful=1)}, "x"):
            with self.assertRaises(ValueError):
                compare_modes(bad)


if __name__ == "__main__":
    unittest.main()
