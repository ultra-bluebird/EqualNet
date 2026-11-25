# SPDX-License-Identifier: MIT OR Apache-2.0
"""Structural review of rider-status presentations and analysis of comprehension
study responses. Local calculation only.

Passing the structural review does NOT establish accessibility conformance: it
checks a few declared properties (distinct text and shape cues, an age in stale
text, contrast arithmetic, no symbol-only text). Real accessibility needs
testing with assistive technology and with voluntary participants who choose
their own accommodations. Responses carry only random pseudonymous tokens.
"""
from dataclasses import dataclass
import math
import re
import unicodedata
import unittest

REQUIRED_STATES = ("estimated", "stale", "unavailable", "not_a_guarantee")
OUTCOMES = {"correct", "misread", "unsure"}
PROHIBITED = {"location", "route", "trip", "journey", "device", "account", "name", "email",
              "phone", "ip", "gps", "diagnosis", "disability", "wallet"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
PID = re.compile(r"p[0-9a-f]{8,32}")
AGE = re.compile(r"\b\d+\s?(s|sec|secs|seconds?|min|mins|minutes?|h|hours?)\b", re.IGNORECASE)
MAX_WORDS = 25
Z95 = 1.959963984540054


def _lin(c):
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    """WCAG 2.x relative luminance for 8-bit sRGB values."""
    if type(rgb) is not tuple or len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb):
        raise ValueError("rgb")
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    """(L1 + 0.05) / (L2 + 0.05) with L1 the lighter colour; not rounded."""
    a, b = relative_luminance(fg), relative_luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@dataclass(frozen=True)
class State:
    text: str
    icon: str
    fg: tuple | None = None
    bg: tuple | None = None
    large: bool = False


def review_presentation(states):
    """Return fixed reason codes. Absence of codes is not an accessibility claim."""
    if type(states) is not dict or set(states) != set(REQUIRED_STATES) \
            or not all(isinstance(s, State) for s in states.values()):
        return {"structurally_consistent": False, "reasons": ("E_STATES",), "notes": (),
                "accessibility_conformance_established": False}
    reasons, notes = [], []
    texts, icons = [], []
    for name in REQUIRED_STATES:
        s, tag = states[name], name.upper()
        ok_text = type(s.text) is str and s.text.strip() and len(s.text.split()) <= MAX_WORDS \
            and all(unicodedata.category(c)[0] != "C" for c in s.text)
        if not ok_text:
            reasons.append("E_TEXT_" + tag)
        else:
            texts.append(s.text.strip().lower())
            if any(unicodedata.category(c) in ("So", "Sk") for c in s.text):
                reasons.append("E_SYMBOL_IN_TEXT_" + tag)
        if type(s.icon) is not str or TOKEN.fullmatch(s.icon) is None:
            reasons.append("E_ICON_" + tag)
        else:
            icons.append(s.icon)
        if (s.fg is None) != (s.bg is None):
            reasons.append("E_CONTRAST_PAIR_" + tag)
        elif s.fg is None:
            notes.append("N_CONTRAST_UNCHECKED_" + tag)
        else:
            try:
                limit = 3.0 if s.large else 4.5
                if contrast_ratio(s.fg, s.bg) < limit:
                    reasons.append("E_CONTRAST_" + tag)
            except ValueError:
                reasons.append("E_CONTRAST_VALUE_" + tag)
    if len(set(texts)) != len(texts):
        reasons.append("E_TEXT_DUPLICATE")
    if len(set(icons)) != len(icons):
        reasons.append("E_ICON_DUPLICATE")
    if type(states["stale"].text) is str and AGE.search(states["stale"].text) is None:
        reasons.append("E_AGE_MISSING_STALE")
    return {"structurally_consistent": not reasons, "reasons": tuple(reasons), "notes": tuple(notes),
            "accessibility_conformance_established": False}


def wilson(hits, n, z=Z95):
    p = hits / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    den = 1 + z * z / n
    return max(0.0, (centre - margin) / den), min(1.0, (centre + margin) / den)


def sign_test_p(b, c):
    """Exact two-sided sign test on discordant pairs b and c."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def holm(pvalues):
    """Holm step-down adjusted p-values, returned in the original order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def validate_response(r):
    if type(r) is not dict or not {"pid", "presentation", "item", "outcome"} <= set(r) \
            or set(r) - {"pid", "presentation", "item", "outcome", "channel"}:
        raise ValueError("response fields")
    if set(map(str.lower, r)) & PROHIBITED:
        raise ValueError("prohibited field")
    if type(r["pid"]) is not str or PID.fullmatch(r["pid"]) is None \
            or not all(type(r[k]) is str and TOKEN.fullmatch(r[k]) for k in ("presentation", "item")) \
            or r["outcome"] not in OUTCOMES \
            or ("channel" in r and not (type(r["channel"]) is str and TOKEN.fullmatch(r["channel"]))):
        raise ValueError("response values")


def analyze(responses, min_cell=5):
    """Per presentation x item counts, and within-participant paired comparisons.

    Cells smaller than min_cell are suppressed. Channel is optional and
    self-chosen; it is never required and is not analysed here.
    """
    if type(min_cell) is not int or min_cell < 2 or type(responses) not in (list, tuple):
        raise ValueError("options")
    seen, cells, by_key = set(), {}, {}
    for r in responses:
        validate_response(r)
        key = (r["pid"], r["presentation"], r["item"])
        if key in seen:
            raise ValueError("duplicate response")
        seen.add(key)
        cells.setdefault((r["presentation"], r["item"]), []).append(r["outcome"])
        by_key[key] = r["outcome"] == "correct"
    table = {}
    for (pres, item), outcomes in sorted(cells.items()):
        n = len(outcomes)
        if n < min_cell:
            table[(pres, item)] = {"n": n, "suppressed": True}
            continue
        mis = outcomes.count("misread")
        table[(pres, item)] = {"n": n, "suppressed": False, "correct": outcomes.count("correct"),
                               "misread": mis, "unsure": outcomes.count("unsure"),
                               "misread_upper": wilson(mis, n)[1]}
    presentations = sorted({k[1] for k in by_key})
    items = sorted({k[2] for k in by_key})
    tests = []
    for item in items:
        for i, a in enumerate(presentations):
            for b in presentations[i + 1:]:
                both = [p for (p, pr, it) in by_key if pr == a and it == item and (p, b, item) in by_key]
                if len(both) < min_cell:
                    continue
                only_a = sum(by_key[(p, a, item)] and not by_key[(p, b, item)] for p in both)
                only_b = sum(by_key[(p, b, item)] and not by_key[(p, a, item)] for p in both)
                tests.append({"item": item, "pair": (a, b), "pairs": len(both), "only_first_correct": only_a,
                              "only_second_correct": only_b, "p": sign_test_p(only_a, only_b)})
    for t, adj in zip(tests, holm([t["p"] for t in tests])):
        t["p_holm"] = adj
    return {"cells": table, "paired": tests, "min_cell": min_cell}


class Tests(unittest.TestCase):
    def good(self, **overrides):
        base = {"estimated": State("Estimate based on door counts", "circle"),
                "stale": State("No recent estimate. Last observation was 12 min ago", "clock"),
                "unavailable": State("Estimate unavailable", "dash"),
                "not_a_guarantee": State("This is not a guarantee of space", "tilde")}
        base.update(overrides)
        return base

    def test_contrast_arithmetic_matches_wcag_definition(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=9)
        self.assertAlmostEqual(contrast_ratio((255, 255, 255), (255, 255, 255)), 1.0, places=12)
        self.assertAlmostEqual(relative_luminance((255, 255, 255)), 1.0, places=12)
        self.assertEqual(relative_luminance((0, 0, 0)), 0.0)
        self.assertGreaterEqual(contrast_ratio((0x76,) * 3, (255,) * 3), 4.5)
        self.assertLess(contrast_ratio((0x77,) * 3, (255,) * 3), 4.5)
        self.assertLess(contrast_ratio((0x95,) * 3, (255,) * 3), 3.0)
        self.assertGreaterEqual(contrast_ratio((0x94,) * 3, (255,) * 3), 3.0)
        for bad in ((0, 0), (0, 0, 256), (0, 0, True), [0, 0, 0]):
            with self.assertRaises(ValueError):
                relative_luminance(bad)

    def test_good_presentation_is_consistent_but_never_certified(self):
        r = review_presentation(self.good())
        self.assertTrue(r["structurally_consistent"])
        self.assertEqual(r["reasons"], ())
        self.assertEqual(len(r["notes"]), 4)
        self.assertFalse(r["accessibility_conformance_established"])

    def test_each_structural_failure_has_its_own_code(self):
        cases = [(dict(unavailable=State("Estimate based on door counts", "dash")), "E_TEXT_DUPLICATE"),
                 (dict(unavailable=State("Estimate unavailable", "circle")), "E_ICON_DUPLICATE"),
                 (dict(stale=State("No recent estimate", "clock")), "E_AGE_MISSING_STALE"),
                 (dict(unavailable=State("Unavailable \U0001F6AB", "dash")), "E_SYMBOL_IN_TEXT_UNAVAILABLE"),
                 (dict(unavailable=State("", "dash")), "E_TEXT_UNAVAILABLE"),
                 (dict(unavailable=State("a " * 30, "dash")), "E_TEXT_UNAVAILABLE"),
                 (dict(unavailable=State("Estimate unavailable", "")), "E_ICON_UNAVAILABLE"),
                 (dict(unavailable=State("Estimate unavailable", "dash", fg=(0, 0, 0))), "E_CONTRAST_PAIR_UNAVAILABLE"),
                 (dict(unavailable=State("Estimate unavailable", "dash", (0x77,) * 3, (255,) * 3)), "E_CONTRAST_UNAVAILABLE"),
                 (dict(unavailable=State("Estimate unavailable", "dash", (0, 0, 300), (255,) * 3)), "E_CONTRAST_VALUE_UNAVAILABLE")]
        for change, code in cases:
            r = review_presentation(self.good(**change))
            self.assertIn(code, r["reasons"], code)
            self.assertFalse(r["structurally_consistent"])

    def test_large_text_uses_the_lower_threshold(self):
        grey = (0x94,) * 3
        small = review_presentation(self.good(unavailable=State("Estimate unavailable", "dash", grey, (255,) * 3)))
        large = review_presentation(self.good(unavailable=State("Estimate unavailable", "dash", grey, (255,) * 3, True)))
        self.assertIn("E_CONTRAST_UNAVAILABLE", small["reasons"])
        self.assertNotIn("E_CONTRAST_UNAVAILABLE", large["reasons"])

    def test_missing_or_extra_states_are_rejected(self):
        short = self.good()
        del short["stale"]
        extra = {**self.good(), "extra": State("x", "y")}
        for bad in (short, extra, [], {"estimated": "text"}):
            self.assertEqual(review_presentation(bad)["reasons"], ("E_STATES",))

    def test_exact_sign_test_and_holm(self):
        self.assertEqual(sign_test_p(9, 1), 0.021484375)
        self.assertEqual(sign_test_p(5, 5), 1.0)
        self.assertEqual(sign_test_p(0, 8), 0.0078125)
        self.assertEqual(sign_test_p(0, 0), 1.0)
        self.assertEqual(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
        self.assertEqual(holm([0.5]), [0.5])

    @staticmethod
    def study(a_correct, b_correct, n=40):
        out = []
        for i in range(n):
            pid = "p%08x" % i
            out.append({"pid": pid, "presentation": "text", "item": "stale",
                        "outcome": "correct" if i in a_correct else "misread"})
            out.append({"pid": pid, "presentation": "layered", "item": "stale",
                        "outcome": "correct" if i in b_correct else ("unsure" if i % 7 == 0 else "misread")})
        return out

    def test_analysis_counts_pairs_and_corrects_for_multiple_comparisons(self):
        a = set(range(0, 30))
        b = set(range(21, 40)) | set(range(21, 30))
        result = analyze(self.study(a, b))
        text, layered = result["cells"][("text", "stale")], result["cells"][("layered", "stale")]
        self.assertEqual((text["n"], text["correct"], text["misread"]), (40, 30, 10))
        self.assertEqual(layered["correct"], 19)
        pair = result["paired"][0]
        self.assertEqual(pair["pair"], ("layered", "text"))
        only_layered, only_text = len(b - a), len(a - b)
        self.assertEqual((only_layered, only_text), (10, 21))
        self.assertEqual((pair["only_first_correct"], pair["only_second_correct"]), (only_layered, only_text))
        self.assertEqual(pair["p"], sign_test_p(only_layered, only_text))
        self.assertGreaterEqual(pair["p_holm"], pair["p"])

    def test_small_cells_are_suppressed_and_not_tested(self):
        result = analyze(self.study({0, 1}, {1, 2}, n=4), min_cell=5)
        self.assertTrue(all(c["suppressed"] for c in result["cells"].values()))
        self.assertEqual(result["paired"], [])
        self.assertNotIn("correct", result["cells"][("text", "stale")])

    def test_responses_cannot_carry_identity_or_tracking_fields(self):
        base = {"pid": "p00000001", "presentation": "text", "item": "stale", "outcome": "correct"}
        analyze([base])
        bad = [{**base, "location": "x"}, {**base, "Route": "x"}, {**base, "pid": "alice"},
               {**base, "outcome": "maybe"}, {**base, "channel": "x\n"}, {**base, "extra": 1},
               {k: v for k, v in base.items() if k != "item"}, "text"]
        for r in bad:
            with self.assertRaises(ValueError):
                analyze([r])
        with self.assertRaises(ValueError):
            analyze([base, dict(base)])
        analyze([{**base, "channel": "screen reader"}])
        for opts in (dict(min_cell=1), dict(min_cell=True)):
            with self.assertRaises(ValueError):
                analyze([base], **opts)


if __name__ == "__main__":
    unittest.main()
