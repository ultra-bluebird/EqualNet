# SPDX-License-Identifier: MIT OR Apache-2.0
"""Review of rider-information wording for unsupported pressure, plus study design
and coding-agreement tools. Local calculation only.

The wording check is structural and heuristic. Phrase matching can miss pressure
and can flag harmless text, so it only asks a human reviewer to look; it never
decides what a message means. Rider study responses carry only random
pseudonymous tokens, and no journey, location, device, or account field.
"""
from dataclasses import dataclass
import hashlib
import itertools
import math
import random
import re
import unittest

KINDS = ("information", "option", "recommendation", "condition")
READINGS = ("option", "unsupported_recommendation", "implied_condition", "unclear")
FACTORS = {"frequency": ("frequent", "infrequent"), "accessibility_info": ("verified", "unverified"),
           "heat": ("mild", "extreme"), "urgency": ("low", "high")}
PROHIBITED = {"location", "route", "trip", "journey", "device", "account", "name", "email",
              "phone", "ip", "gps", "diagnosis", "disability", "wallet"}
TEXT = re.compile(r"[A-Za-z0-9 .,;:'\"()/%-]{1,200}")
PID = re.compile(r"p[0-9a-f]{8,32}")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
DIRECTIVES = (re.compile(r"\bmust\b", re.I), re.compile(r"\bdo not board\b", re.I),
              re.compile(r"\bdon't board\b", re.I), re.compile(r"\bshould wait\b", re.I),
              re.compile(r"\bhave to\b", re.I), re.compile(r"\brequired to\b", re.I),
              re.compile(r"\bavoid (this|the) (vehicle|bus|train|car)\b", re.I))
Z95 = 1.959963984540054


@dataclass(frozen=True)
class Verification:
    service_observed_ns: int | None = None
    accessible_alternative: bool | None = None


@dataclass(frozen=True)
class Message:
    kind: str
    text: str
    verification: Verification | None = None


def review_message(msg, now_ns, max_age_ns):
    """Fixed reason codes; notes request human review. Never a meaning judgment."""
    if not isinstance(msg, Message) or type(now_ns) is not int or type(max_age_ns) is not int \
            or max_age_ns < 0:
        raise ValueError("review inputs")
    reasons, notes = [], []
    if msg.kind not in KINDS:
        reasons.append("E_KIND")
    if type(msg.text) is not str or TEXT.fullmatch(msg.text) is None:
        reasons.append("E_TEXT")
    elif any(p.search(msg.text) for p in DIRECTIVES):
        notes.append("N_DIRECTIVE_WORDING")
    v = msg.verification
    if v is not None and not (isinstance(v, Verification)
                              and (v.service_observed_ns is None or type(v.service_observed_ns) is int)
                              and v.accessible_alternative in (None, True, False)):
        reasons.append("E_VERIFICATION")
        v = None
    if msg.kind == "condition":
        reasons.append("E_IMPLIED_CONDITION")
    elif msg.kind == "recommendation":
        fresh = v is not None and v.service_observed_ns is not None \
            and 0 <= now_ns - v.service_observed_ns <= max_age_ns
        if not fresh or v.accessible_alternative is not True:
            reasons.append("E_UNSUPPORTED_RECOMMENDATION")
    elif msg.kind == "option" and v is not None:
        if v.accessible_alternative is False:
            reasons.append("E_ALTERNATIVE_NOT_ACCESSIBLE")
        elif v.accessible_alternative is None:
            notes.append("N_ALTERNATIVE_ACCESSIBILITY_UNKNOWN")
    return {"structurally_consistent": not reasons, "reasons": tuple(reasons), "notes": tuple(notes),
            "meaning_determined": False}


def scenarios():
    """All 2^4 scenario combinations as dicts, in a fixed order."""
    keys = list(FACTORS)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(FACTORS[k] for k in keys))]


def scenario_order(pid, seed):
    """Deterministic pseudo-random order of the 16 scenarios for one participant."""
    if type(pid) is not str or PID.fullmatch(pid) is None or type(seed) is not str or not seed:
        raise ValueError("order inputs")
    h = int.from_bytes(hashlib.sha256((seed + ":" + pid).encode()).digest()[:8], "big")
    order = list(range(len(scenarios())))
    random.Random(h).shuffle(order)
    return order


def cohens_kappa(a, b, categories):
    """Cohen's kappa for two coders; None when chance agreement is 1 (undefined)."""
    cats = tuple(categories)
    if len(a) != len(b) or not a or len(set(cats)) != len(cats) \
            or not all(x in cats for x in itertools.chain(a, b)):
        raise ValueError("kappa inputs")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if math.isclose(pe, 1.0) else (po - pe) / (1 - pe)


def specific_agreement(a, b, category):
    """2*both / (2*both + only_one): agreement on one category."""
    both = sum(x == category and y == category for x, y in zip(a, b))
    one = sum((x == category) != (y == category) for x, y in zip(a, b))
    return None if 2 * both + one == 0 else 2 * both / (2 * both + one)


def wilson(hits, n, z=Z95):
    p = hits / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    den = 1 + z * z / n
    return max(0.0, (centre - margin) / den), min(1.0, (centre + margin) / den)


def reading_rates(readings, min_cell=5):
    """Per scenario: how many participants read the message as something other than an option."""
    if type(min_cell) is not int or min_cell < 2 or type(readings) not in (list, tuple):
        raise ValueError("options")
    seen, cells = set(), {}
    for r in readings:
        if type(r) is not dict or set(r) != {"pid", "scenario", "reading"} \
                or set(map(str.lower, r)) & PROHIBITED or type(r["pid"]) is not str \
                or PID.fullmatch(r["pid"]) is None or not (type(r["scenario"]) is str
                                                           and TOKEN.fullmatch(r["scenario"])) \
                or r["reading"] not in READINGS:
            raise ValueError("reading record")
        key = (r["pid"], r["scenario"])
        if key in seen:
            raise ValueError("duplicate reading")
        seen.add(key)
        cells.setdefault(r["scenario"], []).append(r["reading"])
    out = {}
    for scenario, labels in sorted(cells.items()):
        n = len(labels)
        if n < min_cell:
            out[scenario] = {"n": n, "suppressed": True}
            continue
        other = n - labels.count("option")
        low, high = wilson(other, n)
        out[scenario] = {"n": n, "suppressed": False, "share_not_option": other / n,
                         "wilson_low": low, "wilson_high": high,
                         "implied_condition": labels.count("implied_condition"),
                         "unsupported_recommendation": labels.count("unsupported_recommendation"),
                         "unclear": labels.count("unclear")}
    return out


class Tests(unittest.TestCase):
    NOW, AGE = 1_000_000, 100

    def verified(self, **kw):
        base = dict(service_observed_ns=self.NOW - 10, accessible_alternative=True)
        base.update(kw)
        return Verification(**base)

    def reasons(self, kind, text="A later vehicle is expected", verification=None):
        return review_message(Message(kind, text, verification), self.NOW, self.AGE)

    def test_plain_information_and_supported_recommendation_pass(self):
        self.assertTrue(self.reasons("information")["structurally_consistent"])
        r = self.reasons("recommendation", "Another vehicle is scheduled soon", self.verified())
        self.assertTrue(r["structurally_consistent"])
        self.assertFalse(r["meaning_determined"])

    def test_boarding_conditions_are_always_rejected(self):
        for v in (None, self.verified()):
            self.assertIn("E_IMPLIED_CONDITION", self.reasons("condition", verification=v)["reasons"])

    def test_recommendations_need_fresh_verified_accessible_alternatives(self):
        stale = self.verified(service_observed_ns=self.NOW - 101)
        future = self.verified(service_observed_ns=self.NOW + 5)
        cases = [None, stale, future, self.verified(accessible_alternative=False),
                 self.verified(accessible_alternative=None), self.verified(service_observed_ns=None)]
        for v in cases:
            self.assertIn("E_UNSUPPORTED_RECOMMENDATION", self.reasons("recommendation", verification=v)["reasons"])
        edge = self.verified(service_observed_ns=self.NOW - 100)
        self.assertTrue(self.reasons("recommendation", verification=edge)["structurally_consistent"])

    def test_options_must_not_point_to_an_inaccessible_alternative(self):
        self.assertIn("E_ALTERNATIVE_NOT_ACCESSIBLE",
                      self.reasons("option", verification=self.verified(accessible_alternative=False))["reasons"])
        unknown = self.reasons("option", verification=self.verified(accessible_alternative=None))
        self.assertTrue(unknown["structurally_consistent"])
        self.assertIn("N_ALTERNATIVE_ACCESSIBILITY_UNKNOWN", unknown["notes"])

    def test_directive_wording_is_flagged_for_a_human_with_known_blind_spots(self):
        for text in ("You must wait for the next vehicle", "Do not board this vehicle",
                     "Riders should wait for another one", "Avoid this bus today"):
            self.assertIn("N_DIRECTIVE_WORDING", self.reasons("information", text)["notes"], text)
        for text in ("It would be better to let this one pass", "Most people prefer the next one"):
            self.assertEqual(self.reasons("option", text)["notes"], (), text)
        self.assertEqual(self.reasons("information", "Estimate observed 12 min ago")["notes"], ())

    def test_invalid_messages(self):
        self.assertIn("E_KIND", self.reasons("advice")["reasons"])
        self.assertIn("E_TEXT", self.reasons("information", "line\nbreak")["reasons"])
        self.assertIn("E_TEXT", self.reasons("information", "x" * 201)["reasons"])
        self.assertIn("E_VERIFICATION", self.reasons("information", verification="yes")["reasons"])
        for args in (("not a message", self.NOW, 1), (Message("option", "ok"), 1.5, 1),
                     (Message("option", "ok"), 1, -1)):
            with self.assertRaises(ValueError):
                review_message(*args)

    def test_design_has_sixteen_unique_scenarios_and_deterministic_orders(self):
        sc = scenarios()
        self.assertEqual(len(sc), 16)
        self.assertEqual(len({tuple(s.values()) for s in sc}), 16)
        order = scenario_order("p00000001", "study one")
        self.assertEqual(sorted(order), list(range(16)))
        self.assertEqual(order, scenario_order("p00000001", "study one"))
        self.assertNotEqual(order, scenario_order("p00000002", "study one"))
        self.assertNotEqual(order, scenario_order("p00000001", "study two"))
        for bad in (("alice", "s"), ("p00000001", ""), (1, "s")):
            with self.assertRaises(ValueError):
                scenario_order(*bad)

    def test_first_position_is_roughly_balanced_across_participants(self):
        first = [0] * 16
        for i in range(320):
            first[scenario_order("p%08x" % i, "s1")[0]] += 1
        self.assertEqual(sum(first), 320)
        self.assertLessEqual(max(abs(c - 20) for c in first), 12)

    def test_kappa_and_specific_agreement_match_hand_computation(self):
        a = ["yes"] * 25 + ["no"] * 25
        b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
        self.assertAlmostEqual(cohens_kappa(a, b, ("yes", "no")), 0.4, places=12)
        self.assertAlmostEqual(specific_agreement(a, b, "yes"), 40 / 55, places=12)
        self.assertAlmostEqual(specific_agreement(a, b, "no"), 30 / 45, places=12)
        self.assertEqual(cohens_kappa(a, a, ("yes", "no")), 1.0)
        self.assertIsNone(cohens_kappa(["yes"] * 5, ["yes"] * 5, ("yes", "no")))
        self.assertIsNone(specific_agreement(["x"], ["x"], "y"))
        for args in ((["a"], ["a", "b"], ("a", "b")), ([], [], ("a",)), (["z"], ["a"], ("a", "b"))):
            with self.assertRaises(ValueError):
                cohens_kappa(*args)

    def test_reading_rates_with_suppression_and_validation(self):
        def rec(i, scenario, reading):
            return {"pid": "p%08x" % i, "scenario": scenario, "reading": reading}
        data = [rec(i, "high urgency", "implied_condition" if i < 3 else "option") for i in range(10)]
        data += [rec(i, "tiny", "option") for i in range(3)]
        out = reading_rates(data)
        cell = out["high urgency"]
        low, high = wilson(3, 10)
        self.assertEqual((cell["n"], cell["implied_condition"]), (10, 3))
        self.assertAlmostEqual(cell["wilson_high"], high)
        self.assertAlmostEqual(cell["wilson_low"], low)
        self.assertAlmostEqual(cell["share_not_option"], 0.3)
        self.assertTrue(out["tiny"]["suppressed"])
        bad = [{**rec(1, "s", "option"), "route": "x"}, {**rec(1, "s", "option"), "pid": "bob"},
               rec(1, "s", "dislike"), {"pid": "p00000001", "scenario": "s"}]
        for r in bad:
            with self.assertRaises(ValueError):
                reading_rates([r])
        with self.assertRaises(ValueError):
            reading_rates([rec(1, "s", "option"), rec(1, "s", "option")])
        with self.assertRaises(ValueError):
            reading_rates([], min_cell=1)


if __name__ == "__main__":
    unittest.main()
