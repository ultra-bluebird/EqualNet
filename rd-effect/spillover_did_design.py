# SPDX-License-Identifier: MIT OR Apache-2.0
"""Difference-in-differences under declared spillovers, on AGGREGATE units (synthetic only).

Unit outcome change: dY_i = tau * (T_i + sum_j S_ij T_j) + gamma * T_i + noise. S is a
DECLARED interference matrix (S_ij = effect on unit i of treating unit j, as a multiple of
tau); positive entries leak benefit, negative entries displace demand. It is an input to a
simulation, not something estimated here. gamma is a differential trend. Nothing here
identifies a causal effect from data; it shows what a chosen comparison would target.
"""
import math
import random
import unittest


def _check(S, treated):
    n = len(S)
    if n < 2 or len(treated) != n or any(len(r) != n for r in S) or not all(type(t) is bool for t in treated):
        raise ValueError("shape")
    if not all(type(v) in (int, float) and math.isfinite(v) for r in S for v in r):
        raise ValueError("values")
    if sum(treated) < 1:
        raise ValueError("no treated units")


def exposure(S, treated):
    """Spillover received by each unit from OTHER treated units (diagonal ignored)."""
    _check(S, treated)
    return [sum(S[i][j] for j in range(len(S)) if j != i and treated[j]) for i in range(len(S))]


def _controls(treated, controls):
    pool = [i for i, t in enumerate(treated) if not t]
    chosen = pool if controls is None else list(controls)
    if not chosen or any(c not in pool for c in chosen) or len(set(chosen)) != len(chosen):
        raise ValueError("controls")
    return chosen


def did_expectation(S, treated, tau, gamma=0.0, controls=None):
    """Expected (treated change) - (control change)."""
    exp = exposure(S, treated)
    t_idx = [i for i, t in enumerate(treated) if t]
    c_idx = _controls(treated, controls)
    mean_t = sum(1 + exp[i] for i in t_idx) / len(t_idx)
    mean_c = sum(exp[c] for c in c_idx) / len(c_idx)
    return tau * (mean_t - mean_c) + gamma


def estimands(S, treated, tau, weights=None):
    exp = exposure(S, treated)
    n = len(S)
    w = [1.0 / n] * n if weights is None else list(weights)
    if len(w) != n or any(x < 0 for x in w) or abs(sum(w) - 1) > 1e-9:
        raise ValueError("weights")
    t_idx = [i for i, t in enumerate(treated) if t]
    c_idx = [i for i, t in enumerate(treated) if not t]
    return {"direct_site_effect": tau,
            "treated_total": tau * sum(1 + exp[i] for i in t_idx) / len(t_idx),
            "control_spillover": tau * sum(exp[c] for c in c_idx) / len(c_idx) if c_idx else None,
            "network_average": tau * sum((1 if treated[i] else 0) + exp[i] for i in range(n)) / n,
            "area_weighted": tau * sum(w[i] * ((1 if treated[i] else 0) + exp[i]) for i in range(n))}


def shared_use_matrix(shares, leak, displace):
    """S_ij = shares_ij * (leak - displace) for i != j; shares_ij = fraction of unit i's users also using site j."""
    n = len(shares)
    if n < 2 or any(len(r) != n for r in shares) or leak < 0 or displace < 0:
        raise ValueError("shares")
    for i, r in enumerate(shares):
        if any(not 0 <= v <= 1 for v in r) or sum(v for j, v in enumerate(r) if j != i) > 1:
            raise ValueError("shares")
    return [[0.0 if i == j else shares[i][j] * (leak - displace) for j in range(n)] for i in range(n)]


def buffered_controls(S, treated, max_abs_exposure):
    exp = exposure(S, treated)
    return tuple(i for i, t in enumerate(treated) if not t and abs(exp[i]) <= max_abs_exposure)


def design_report(S, treated, tau, gamma=0.0, thresholds=(None, 0.05, 0.0)):
    """Expected DiD bias against the direct effect for several control choices."""
    rows = []
    for th in thresholds:
        ctrl = None if th is None else buffered_controls(S, treated, th)
        if ctrl is not None and not ctrl:
            rows.append({"max_abs_exposure": th, "controls": (), "status": "no_controls", "expected_did": None, "bias": None})
            continue
        d = did_expectation(S, treated, tau, gamma, ctrl)
        rows.append({"max_abs_exposure": th, "controls": ctrl, "status": "ok", "expected_did": d, "bias": d - tau})
    return {"rows": rows, "spillover_model": "declared, not estimated", "causal_claim_authorized": False}


def simulate(S, treated, tau, gamma, noise_sd, reps, seed, controls=None):
    exp = exposure(S, treated)
    t_idx = [i for i, t in enumerate(treated) if t]
    c_idx = _controls(treated, controls)
    if type(reps) is not int or reps < 1 or noise_sd < 0:
        raise ValueError("simulate options")
    rnd, out = random.Random(seed), []
    for _ in range(reps):
        dy = [tau * ((1 if treated[i] else 0) + exp[i]) + (gamma if treated[i] else 0.0) + rnd.gauss(0, noise_sd)
              for i in range(len(S))]
        out.append(sum(dy[i] for i in t_idx) / len(t_idx) - sum(dy[c] for c in c_idx) / len(c_idx))
    mean = sum(out) / reps
    sd = math.sqrt(sum((x - mean) ** 2 for x in out) / (reps - 1)) if reps > 1 else 0.0
    return {"mean": mean, "sd": sd, "expected": did_expectation(S, treated, tau, gamma, controls)}


def _slope(y):
    n = len(y)
    xb, yb = (n - 1) / 2, sum(y) / n
    return sum((i - xb) * (v - yb) for i, v in enumerate(y)) / sum((i - xb) ** 2 for i in range(n))


def pre_trend_gap(pre_treated, pre_control, tol):
    """Slope difference of aggregate pre-period means; a check, never proof of parallel trends."""
    if len(pre_treated) != len(pre_control) or len(pre_treated) < 3 or tol <= 0:
        raise ValueError("pre-trend inputs")
    gap = _slope(pre_treated) - _slope(pre_control)
    return {"gap": gap, "flag": abs(gap) > tol}


class Tests(unittest.TestCase):
    def S(self, c0=0.2, c1=0.1, tt=0.1):
        return [[0, tt, 0, 0], [tt, 0, 0, 0], [c0, c1, 0, 0], [0, 0, 0, 0]]

    T = [True, True, False, False]

    def test_no_spillover_recovers_the_direct_effect_exactly(self):
        zero = [[0.0] * 4 for _ in range(4)]
        self.assertEqual(did_expectation(zero, self.T, 2.0), 2.0)
        self.assertAlmostEqual(did_expectation(zero, self.T, 2.0, gamma=0.4), 2.4)

    def test_leakage_displacement_and_treated_amplification_move_the_estimand(self):
        self.assertAlmostEqual(did_expectation(self.S(), self.T, 1.0), 1.1 - 0.15)
        self.assertAlmostEqual(did_expectation(self.S(0, 0), self.T, 1.0), 1.1)
        self.assertAlmostEqual(did_expectation(self.S(-0.2, -0.1), self.T, 1.0), 1.1 + 0.15)
        self.assertAlmostEqual(did_expectation(self.S(tt=0.0), self.T, 2.0), 2.0 * (1 - 0.15))

    def test_estimands_differ_and_area_weights_matter(self):
        e = estimands(self.S(), self.T, 2.0)
        self.assertAlmostEqual(e["direct_site_effect"], 2.0)
        self.assertAlmostEqual(e["treated_total"], 2.2)
        self.assertAlmostEqual(e["control_spillover"], 0.3)
        self.assertAlmostEqual(e["network_average"], 2.0 * 0.625)
        self.assertAlmostEqual(estimands(self.S(), self.T, 2.0, [0.4, 0.4, 0.1, 0.1])["area_weighted"],
                               2.0 * (0.4 * 1.1 + 0.4 * 1.1 + 0.1 * 0.3))
        with self.assertRaises(ValueError):
            estimands(self.S(), self.T, 1.0, [0.5, 0.5, 0.5, 0.5])

    def test_buffering_removes_contamination_but_may_leave_no_controls(self):
        rep = design_report(self.S(), self.T, 1.0)
        rows = {r["max_abs_exposure"]: r for r in rep["rows"]}
        self.assertAlmostEqual(rows[None]["bias"], 0.1 - 0.15)
        self.assertEqual(rows[0.05]["controls"], (3,))
        self.assertAlmostEqual(rows[0.05]["bias"], 0.1)
        self.assertEqual(buffered_controls(self.S(), self.T, exposure(self.S(), self.T)[2]), (2, 3))
        self.assertEqual(buffered_controls(self.S(), self.T, 0.29), (3,))
        none_left = design_report([[0, 0.1, 0, 0], [0.1, 0, 0, 0], [0.3, 0, 0, 0], [0.3, 0, 0, 0]], self.T, 1.0)
        self.assertEqual(none_left["rows"][1]["status"], "no_controls")
        self.assertFalse(rep["causal_claim_authorized"])

    def test_shared_use_matrix_sign_depends_on_leakage_versus_displacement(self):
        shares = [[0, 0.5, 0.1], [0.2, 0, 0.3], [0.0, 0.4, 0]]
        up = shared_use_matrix(shares, 0.5, 0.2)
        down = shared_use_matrix(shares, 0.2, 0.5)
        self.assertAlmostEqual(up[0][1], 0.15)
        self.assertAlmostEqual(down[0][1], -0.15)
        self.assertEqual(up[0][0], 0.0)
        for bad in ([[0, 0.8, 0.8], [0, 0, 0], [0, 0, 0]], [[0, -0.1], [0, 0]]):
            with self.assertRaises(ValueError):
                shared_use_matrix(bad, 0.5, 0.2)

    def test_simulation_matches_the_analytic_expectation(self):
        r = simulate(self.S(), self.T, 1.0, 0.3, 0.5, 300, 1)
        se = 0.5 * math.sqrt(1 / 2 + 1 / 2) / math.sqrt(300)
        self.assertLess(abs(r["mean"] - r["expected"]), 4 * se)
        self.assertAlmostEqual(r["expected"], 0.95 + 0.3)
        self.assertEqual(simulate(self.S(), self.T, 1.0, 0.3, 0.0, 3, 1)["sd"], 0.0)

    def test_pre_trend_check(self):
        self.assertTrue(pre_trend_gap([10, 11, 12, 13], [10, 10, 10, 10], 0.5)["flag"])
        r = pre_trend_gap([10, 11, 12, 13], [20, 21, 22, 23], 0.5)
        self.assertFalse(r["flag"])
        self.assertAlmostEqual(r["gap"], 0.0)

    def test_invalid_inputs(self):
        for S, T in (([[0, 0], [0, 0]], [True]), ([[0, float("nan")], [0, 0]], [True, False]),
                     ([[0, 0], [0, 0]], [False, False]), ([[0, 0], [0, 0]], [1, 0]), ([[0]], [True])):
            with self.assertRaises(ValueError):
                exposure(S, T)
        for c in ([0], [2, 2], []):
            with self.assertRaises(ValueError):
                did_expectation(self.S(), self.T, 1.0, controls=c)
        with self.assertRaises(ValueError):
            simulate(self.S(), self.T, 1.0, 0.0, 1.0, 0, 1)
        with self.assertRaises(ValueError):
            pre_trend_gap([1, 2], [1, 2], 0.5)


if __name__ == "__main__":
    unittest.main()
