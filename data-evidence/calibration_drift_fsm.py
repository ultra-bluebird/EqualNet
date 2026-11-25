# SPDX-License-Identifier: MIT OR Apache-2.0
"""Calibration-drift state machine: literal and sticky variants with exhaustive checks.

States and the residual rule follow the corridor-calibration description: residual =
|observed - reference| / tolerance, an exceedance is residual > 1.0, a lockout needs
N consecutive exceedances. The LITERAL variant implements exactly those transitions,
so a later valid sample leaves a lockout. The STICKY variant treats lockouts as
absorbing until a recorded review. Decision support only: nothing here actuates
anything or denies service, and a lockout means "withhold the evidence claim".
"""
from collections import deque
import hashlib
import math
import random
import re
import statistics
import unittest

STATES = ("UNINITIALIZED", "NOMINAL", "SUSPECT", "DRIFT_LOCKOUT", "INVALID_INPUT_LOCKOUT")
LOCKS = ("DRIFT_LOCKOUT", "INVALID_INPUT_LOCKOUT")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
HEX = re.compile(r"[0-9a-f]{64}")


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("number")
    return float(v)


class CalibrationFSM:
    def __init__(self, n, sticky=True, overflow="saturate", counter_bits=8, window_rule=None):
        if type(n) is not int or n < 1 or type(sticky) is not bool or overflow not in ("saturate", "wrap") \
                or type(counter_bits) is not int or not 2 <= counter_bits <= 32 or (1 << counter_bits) <= n:
            raise ValueError("options")
        if window_rule is not None and not (type(window_rule) is tuple and len(window_rule) == 2
                                            and all(type(v) is int for v in window_rule)
                                            and 1 <= window_rule[0] <= window_rule[1] <= 64):
            raise ValueError("window rule")
        self.n, self.sticky, self.overflow = n, sticky, overflow
        self.max_count = (1 << counter_bits) - 1
        self.window_rule = window_rule
        self.state, self.count, self.window, self.audit = "UNINITIALIZED", 0, (), []

    def _log(self, kind, before):
        self.audit.append((kind, before, self.state, self.count))

    def _bump(self):
        if self.count < self.max_count:
            return self.count + 1
        return 0 if self.overflow == "wrap" else self.max_count

    def step(self, observed, reference, tolerance):
        before = self.state
        if self.sticky and before in LOCKS:
            self._log("IGNORED_WHILE_LOCKED", before)
            return self.state
        try:
            obs, ref, tol = _num(observed), _num(reference), _num(tolerance)
            if tol <= 0:
                raise ValueError("tolerance")
            residual = abs(obs - ref) / tol
            if not math.isfinite(residual):
                raise ValueError("residual")
        except (ValueError, OverflowError):
            self.state = "INVALID_INPUT_LOCKOUT"
            self._log("INVALID", before)
            return self.state
        exceed = residual > 1.0
        if self.window_rule:
            self.window = (self.window + (1 if exceed else 0,))[-self.window_rule[1]:]
        if not exceed:
            self.state, self.count = "NOMINAL", 0
        else:
            self.count = self._bump()
            self.state = "DRIFT_LOCKOUT" if self.count >= self.n else "SUSPECT"
        if self.window_rule and sum(self.window) >= self.window_rule[0]:
            self.state = "DRIFT_LOCKOUT"
        self._log("SAMPLE", before)
        return self.state

    def review(self, reviewer, evidence_sha256):
        before = self.state
        if not self.sticky:
            raise ValueError("no review event in the literal variant")
        if before not in LOCKS or not (type(reviewer) is str and TOKEN.fullmatch(reviewer)
                                       and type(evidence_sha256) is str and HEX.fullmatch(evidence_sha256)):
            raise ValueError("review")
        self.state, self.count, self.window = "UNINITIALIZED", 0, ()
        self._log("REVIEWED", before)
        return self.state

    def _consistent(self, state, count):
        return {"UNINITIALIZED": count == 0, "NOMINAL": count == 0, "SUSPECT": 1 <= count < self.n,
                "DRIFT_LOCKOUT": count >= self.n or (self.window_rule is not None),
                "INVALID_INPUT_LOCKOUT": True}[state]

    def consistent(self):
        return self._consistent(self.state, self.count)

    def persist(self):
        body = "%s|%d|%s" % (self.state, self.count, ",".join(map(str, self.window)))
        return {"state": self.state, "count": self.count, "window": self.window,
                "digest": hashlib.sha256(body.encode()).hexdigest()}

    def restore(self, record, provisioned=True):
        """Restore from a persisted record. Lost or damaged records fail closed (sticky)."""
        ok = False
        if isinstance(record, dict) and set(record) == {"state", "count", "window", "digest"}:
            try:
                body = "%s|%d|%s" % (record["state"], record["count"], ",".join(map(str, record["window"])))
                limit = self.window_rule[1] if self.window_rule else 0
                ok = (record["state"] in STATES and type(record["count"]) is int
                      and 0 <= record["count"] <= self.max_count
                      and type(record["window"]) is tuple and len(record["window"]) <= limit
                      and all(v in (0, 1) and type(v) is int for v in record["window"])
                      and self._consistent(record["state"], record["count"])
                      and record["digest"] == hashlib.sha256(body.encode()).hexdigest())
            except (TypeError, ValueError):
                ok = False
        before = self.state
        if ok:
            self.state, self.count, self.window = record["state"], record["count"], tuple(record["window"])
        elif self.sticky and (provisioned or record is not None):
            self.state, self.count, self.window = "INVALID_INPUT_LOCKOUT", 0, ()
        else:
            self.state, self.count, self.window = "UNINITIALIZED", 0, ()
        self._log("RESTORED" if ok else "RESTORE_FAILED", before)
        return self.state

    def snapshot(self):
        return (self.state, self.count, self.window)


SYMBOLS = ("ok", "exceed", "invalid", "review", "lost_record", "restart")


def _apply(m, symbol):
    if symbol == "ok":
        m.step(0.0, 0.0, 1.0)
    elif symbol == "exceed":
        m.step(2.0, 0.0, 1.0)
    elif symbol == "invalid":
        m.step(float("nan"), 0.0, 1.0)
    elif symbol == "review":
        if m.sticky and m.state in LOCKS:
            m.review("reviewer one", "0" * 64)
    elif symbol == "lost_record":
        m.restore(None, provisioned=True)
    else:
        m.restore(m.persist(), provisioned=True)


def shortest_escape(make, max_depth):
    """Shortest symbol sequence that leaves a lockout without a review, or None."""
    start = make()
    queue = deque([(start.snapshot(), False, ())])
    seen = {(start.snapshot(), False)}
    while queue:
        snap, locked, seq = queue.popleft()
        if len(seq) >= max_depth:
            continue
        for sym in SYMBOLS:
            m = make()
            m.state, m.count, m.window = snap
            was = m.state in LOCKS
            _apply(m, sym)
            now_locked = locked or (m.state in LOCKS)
            if sym == "review" and was and m.state not in LOCKS:
                now_locked = False
            elif was and m.state not in LOCKS and now_locked:
                return seq + (sym,)
            key = (m.snapshot(), now_locked and m.state in LOCKS)
            if key not in seen:
                seen.add(key)
                queue.append((m.snapshot(), now_locked and m.state in LOCKS, seq + (sym,)))
    return None


def reachable_states(make, max_depth):
    start = make()
    seen, queue, bad = {start.snapshot()}, deque([(start.snapshot(), 0)]), []
    while queue:
        snap, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for sym in SYMBOLS:
            m = make()
            m.state, m.count, m.window = snap
            _apply(m, sym)
            if not m.consistent():
                bad.append((snap, sym, m.snapshot()))
            if m.snapshot() not in seen:
                seen.add(m.snapshot())
                queue.append((m.snapshot(), depth + 1))
    return len(seen), bad


def exact_run_probability(p, n, length):
    """P(at least one run of n consecutive successes in `length` Bernoulli(p) trials)."""
    if not 0 < p < 1 or type(n) is not int or n < 1 or type(length) is not int or length < 1:
        raise ValueError("run inputs")
    dist = [1.0] + [0.0] * (n - 1)
    hit = 0.0
    for _ in range(length):
        nxt = [0.0] * n
        nxt[0] = sum(dist) * (1 - p)
        for k in range(n - 1):
            nxt[k + 1] += dist[k] * p
        hit += dist[n - 1] * p
        dist = nxt
    return hit


def false_lockout_probability(p, n, length, rho, trials, seed):
    """Monte Carlo: Gaussian AR(1) noise with marginal exceedance probability p."""
    if not 0 < p < 1 or not -1 < rho < 1 or type(trials) is not int or trials < 1:
        raise ValueError("mc inputs")
    sd = 1 / statistics.NormalDist().inv_cdf(1 - p / 2)
    rnd, root, locked = random.Random(seed), math.sqrt(1 - rho * rho), 0
    for _ in range(trials):
        e, run = rnd.gauss(0, sd), 0
        for _ in range(length):
            run = run + 1 if abs(e) > 1.0 else 0
            if run >= n:
                locked += 1
                break
            e = rho * e + root * rnd.gauss(0, sd)
    return locked / trials


class Tests(unittest.TestCase):
    def literal(self, **kw):
        return CalibrationFSM(3, sticky=False, **kw)

    def run_seq(self, m, symbols):
        for s in symbols:
            _apply(m, s)
        return m

    def test_literal_transitions_follow_the_described_rules(self):
        m = self.literal()
        self.assertEqual(m.state, "UNINITIALIZED")
        self.assertEqual(m.step(0.0, 0.0, 1.0), "NOMINAL")
        self.assertEqual(m.step(2.0, 0.0, 1.0), "SUSPECT")
        self.assertEqual((m.state, m.count), ("SUSPECT", 1))
        self.assertEqual(m.step(0.5, 0.0, 1.0), "NOMINAL")
        self.assertEqual(m.count, 0)
        self.run_seq(m, ["exceed"] * 3)
        self.assertEqual(m.state, "DRIFT_LOCKOUT")
        for args in ((float("nan"), 0, 1), (1, 0, 0), (1, 0, -1), (True, 0, 1), (1e308, -1e308, 1e-308)):
            n = self.literal()
            self.assertEqual(n.step(*args), "INVALID_INPUT_LOCKOUT", args)

    def test_threshold_equality_is_not_an_exceedance(self):
        m = self.literal()
        self.assertEqual(m.step(1.0, 0.0, 1.0), "NOMINAL")
        self.assertEqual(self.literal().step(math.nextafter(1.0, 2.0), 0.0, 1.0), "SUSPECT")
        self.assertEqual(self.literal().step(-1.0, 0.0, 1.0), "NOMINAL")
        self.assertEqual(self.literal().step(5.0, 3.0, 2.0), "NOMINAL")

    def test_literal_variant_lets_valid_samples_leave_a_lockout(self):
        for lock, seq in (("DRIFT_LOCKOUT", ["exceed"] * 3), ("INVALID_INPUT_LOCKOUT", ["invalid"])):
            m = self.run_seq(self.literal(), seq)
            self.assertEqual(m.state, lock)
            self.run_seq(m, ["ok"])
            self.assertEqual(m.state, "NOMINAL")
        self.assertEqual(shortest_escape(lambda: self.literal(), 8), ("invalid", "ok"))
        escape = shortest_escape(lambda: CalibrationFSM(3, sticky=False), 8)
        self.assertEqual(len(escape), 2)

    def test_literal_variant_also_escapes_through_a_lost_record(self):
        m = self.run_seq(self.literal(), ["exceed"] * 3 + ["lost_record"])
        self.assertEqual(m.state, "UNINITIALIZED")
        self.assertEqual(self.run_seq(m, ["ok"]).state, "NOMINAL")

    def test_sticky_variant_has_no_escape_without_review(self):
        for window in (None, (3, 6)):
            make = lambda w=window: CalibrationFSM(3, sticky=True, window_rule=w)
            self.assertIsNone(shortest_escape(make, 10), window)

    def test_sticky_lockouts_ignore_later_samples_until_reviewed(self):
        m = CalibrationFSM(3)
        self.run_seq(m, ["exceed"] * 3 + ["ok", "ok", "ok", "restart"])
        self.assertEqual(m.state, "DRIFT_LOCKOUT")
        self.assertEqual(m.audit[-2][0], "IGNORED_WHILE_LOCKED")
        self.assertEqual(m.review("reviewer one", "a" * 64), "UNINITIALIZED")
        self.assertEqual((m.count, m.state), (0, "UNINITIALIZED"))
        self.assertEqual(m.step(0.0, 0.0, 1.0), "NOMINAL")
        bad = CalibrationFSM(3)
        self.run_seq(bad, ["invalid"])
        for args in (("x\n", "a" * 64), ("reviewer", "A" * 64), ("reviewer", "abc"), (1, "a" * 64)):
            with self.assertRaises(ValueError):
                bad.review(*args)
        with self.assertRaises(ValueError):
            CalibrationFSM(3).review("reviewer one", "a" * 64)
        with self.assertRaises(ValueError):
            self.literal().review("reviewer one", "a" * 64)

    def test_restart_semantics(self):
        m = self.run_seq(CalibrationFSM(3), ["exceed", "exceed"])
        record = m.persist()
        fresh = CalibrationFSM(3)
        self.assertEqual(fresh.restore(record), "SUSPECT")
        self.assertEqual(fresh.count, 2)
        for broken in (None, {**record, "count": 0}, {**record, "digest": "0" * 64}, {"state": "NOMINAL"}, "x",
                       {**record, "state": "BOGUS"}, {**record, "count": 9999}):
            s = CalibrationFSM(3)
            self.assertEqual(s.restore(broken, provisioned=True), "INVALID_INPUT_LOCKOUT", broken)
        def forged(state, count, window=()):
            body = "%s|%d|%s" % (state, count, ",".join(map(str, window)))
            return {"state": state, "count": count, "window": window,
                    "digest": hashlib.sha256(body.encode()).hexdigest()}
        for fake in (forged("NOMINAL", 5), forged("SUSPECT", 0), forged("UNINITIALIZED", 2), forged("SUSPECT", 3),
                     forged("NOMINAL", 0, (1, 0))):
            s = CalibrationFSM(3)
            self.assertEqual(s.restore(fake, provisioned=True), "INVALID_INPUT_LOCKOUT", fake)
        self.assertEqual(CalibrationFSM(3, window_rule=(2, 4)).restore(forged("NOMINAL", 0, (1, 0))), "NOMINAL")
        self.assertEqual(CalibrationFSM(3, window_rule=(2, 4)).restore(forged("NOMINAL", 0, (2, 0))), "INVALID_INPUT_LOCKOUT")
        self.assertEqual(CalibrationFSM(3).restore(None, provisioned=False), "UNINITIALIZED")
        self.assertEqual(CalibrationFSM(3).restore({"state": "NOMINAL"}, provisioned=False), "INVALID_INPUT_LOCKOUT")
        locked = self.run_seq(CalibrationFSM(3), ["exceed"] * 3)
        again = CalibrationFSM(3)
        again.restore(locked.persist())
        self.assertEqual(again.state, "DRIFT_LOCKOUT")

    def test_counter_overflow_wrap_escapes_but_saturation_does_not(self):
        wrap = self.run_seq(CalibrationFSM(3, sticky=False, overflow="wrap", counter_bits=3), ["exceed"] * 7)
        self.assertEqual(wrap.state, "DRIFT_LOCKOUT")
        self.run_seq(wrap, ["exceed"])
        self.assertEqual((wrap.state, wrap.count), ("SUSPECT", 0))
        self.assertFalse(wrap.consistent())
        sat = self.run_seq(CalibrationFSM(3, sticky=False, overflow="saturate", counter_bits=3), ["exceed"] * 30)
        self.assertEqual((sat.state, sat.count), ("DRIFT_LOCKOUT", 7))
        self.assertTrue(sat.consistent())

    def test_alternating_exceedances_evade_the_consecutive_rule_but_not_a_window_rule(self):
        pattern = ["exceed", "ok"] * 20
        consecutive = self.run_seq(CalibrationFSM(3), pattern)
        self.assertNotIn(consecutive.state, LOCKS)
        windowed = self.run_seq(CalibrationFSM(3, window_rule=(3, 6)), pattern)
        self.assertEqual(windowed.state, "DRIFT_LOCKOUT")
        self.assertEqual(len([a for a in windowed.audit if a[0] == "SAMPLE"]), 5)

    def test_all_reachable_sticky_states_are_consistent(self):
        total, bad = reachable_states(lambda: CalibrationFSM(3), 8)
        self.assertEqual(bad, [])
        self.assertGreaterEqual(total, 6)
        total, bad = reachable_states(lambda: CalibrationFSM(3, sticky=False, overflow="wrap", counter_bits=3), 12)
        self.assertTrue(bad)

    def test_run_probability_exact_value_and_monte_carlo_agreement(self):
        self.assertAlmostEqual(exact_run_probability(0.5, 2, 3), 0.375, places=12)
        self.assertAlmostEqual(exact_run_probability(0.5, 1, 3), 0.875, places=12)
        exact = exact_run_probability(0.05, 3, 200)
        mc = false_lockout_probability(0.05, 3, 200, 0.0, 4000, 11)
        self.assertLess(abs(mc - exact), 0.012)

    def test_correlated_noise_raises_the_false_lockout_rate(self):
        independent = false_lockout_probability(0.05, 3, 200, 0.0, 3000, 5)
        correlated = false_lockout_probability(0.05, 3, 200, 0.8, 3000, 5)
        self.assertGreater(correlated, independent + 0.05)

    def test_constructor_boundaries(self):
        one = CalibrationFSM(1)
        self.assertEqual(self.run_seq(one, ["exceed"]).state, "DRIFT_LOCKOUT")
        CalibrationFSM(3, counter_bits=2)
        CalibrationFSM(3, counter_bits=32)
        for kw in (dict(n=4, counter_bits=2), dict(n=3, counter_bits=33), dict(n=3, counter_bits=1)):
            with self.assertRaises(ValueError):
                CalibrationFSM(**kw)
        for rule in ((1, 1), (3, 3), (64, 64), (1, 64)):
            CalibrationFSM(3, window_rule=rule)
        for rule in ((0, 1), (65, 65), (3, 2), (1, 65)):
            with self.assertRaises(ValueError):
                CalibrationFSM(3, window_rule=rule)

    def test_restore_count_limit_is_inclusive(self):
        def forged(state, count):
            body = "%s|%d|" % (state, count)
            return {"state": state, "count": count, "window": (), "digest": hashlib.sha256(body.encode()).hexdigest()}
        self.assertEqual(CalibrationFSM(3, counter_bits=8).restore(forged("DRIFT_LOCKOUT", 255)), "DRIFT_LOCKOUT")
        self.assertEqual(CalibrationFSM(3, counter_bits=8).restore(forged("DRIFT_LOCKOUT", 256)), "INVALID_INPUT_LOCKOUT")
        self.assertEqual(CalibrationFSM(3, counter_bits=8).restore(forged("NOMINAL", 0)), "NOMINAL")
        self.assertEqual(CalibrationFSM(3, counter_bits=8).restore(forged("NOMINAL", -1)), "INVALID_INPUT_LOCKOUT")

    def test_search_depth_limits_are_exact(self):
        self.assertIsNone(shortest_escape(lambda: self.literal(), 1))
        self.assertEqual(shortest_escape(lambda: self.literal(), 2), ("invalid", "ok"))
        self.assertEqual(reachable_states(lambda: CalibrationFSM(3), 0)[0], 1)
        self.assertEqual(reachable_states(lambda: CalibrationFSM(3), 1)[0], 4)
        self.assertLess(reachable_states(lambda: CalibrationFSM(3), 1)[0], reachable_states(lambda: CalibrationFSM(3), 2)[0])

    def test_probability_input_boundaries(self):
        self.assertAlmostEqual(exact_run_probability(0.5, 1, 1), 0.5, places=12)
        for args in ((0.0, 3, 5), (1.0, 3, 5)):
            with self.assertRaises(ValueError):
                exact_run_probability(*args)
        self.assertEqual(false_lockout_probability(0.5, 1, 5, 0.0, 1, 1) in (0.0, 1.0), True)
        for args in ((0.0, 3, 10, 0.0, 10, 1), (1.0, 3, 10, 0.0, 10, 1), (0.05, 3, 10, -1.0, 10, 1),
                     (0.05, 3, 10, 1.0, 10, 1), (0.05, 3, 10, 0.0, 0, 1)):
            with self.assertRaisesRegex(ValueError, "^mc inputs$"):
                false_lockout_probability(*args)

    def test_invalid_arguments(self):
        for kw in (dict(n=0), dict(n=3, sticky="yes"), dict(n=3, overflow="clip"), dict(n=3, counter_bits=1),
                   dict(n=300, counter_bits=8), dict(n=3, window_rule=(7, 6)), dict(n=3, window_rule=[3, 6])):
            with self.assertRaises(ValueError):
                CalibrationFSM(**kw)
        for args in ((0, 3, 5), (0.5, 0, 5), (0.5, 3, 0)):
            with self.assertRaises(ValueError):
                exact_run_probability(*args)
        with self.assertRaises(ValueError):
            false_lockout_probability(0.05, 3, 10, 1.0, 10, 1)


if __name__ == "__main__":
    unittest.main()
