# SPDX-License-Identifier: MIT OR Apache-2.0
"""Identifiability analysis for a well-mixed cabin CO2 model (synthetic only).

Model, with concentrations in ppm and rates per second:
    dc/dt = g(t) + q(t) * (c_out - c),   g = 1e6 * G / V,  q = Q / V
    dm/dt = (c - m) / tau                (optional first-order sensor lag)
Requires numpy for linear algebra. Parameter values in tests are illustrative
synthetic numbers, not measurements of any vehicle. Nothing here infers
ventilation adequacy, infection risk, safety, or the number of people.
"""
import math
import unittest

import numpy as np

RANK_TOL = 1e-12
MAX_STEPS = 2_000_000


def _finite(value, name):
    if isinstance(value, (bool, np.bool_)) \
            or not isinstance(value, (int, float, np.integer, np.floating)) \
            or not math.isfinite(value):
        raise ValueError(name)
    return float(value)


def to_rates(generation_m3_s, exchange_m3_s, volume_m3):
    """Convert G (m3/s CO2), Q (m3/s outdoor air), V (m3) to g (ppm/s) and q (1/s)."""
    G, Q, V = (_finite(v, n) for v, n in
               ((generation_m3_s, "G"), (exchange_m3_s, "Q"), (volume_m3, "V")))
    if G < 0 or Q <= 0 or V <= 0:
        raise ValueError("G, Q, V")
    return G / V * 1e6, Q / V


def simulate(g_fn, q_fn, c0, m0, c_out, tau, times, dt=1.0):
    """RK4 integration; returns the observed series (sensor reading m, or c if tau=0)."""
    if not callable(g_fn) or not callable(q_fn):
        raise ValueError("functions")
    c, m, co, tau, dt = (_finite(v, n) for v, n in
                         ((c0, "c0"), (m0, "m0"), (c_out, "c_out"), (tau, "tau"), (dt, "dt")))
    if min(c, m, co, tau) < 0 or dt <= 0 or (tau > 0 and dt > tau / 2):
        raise ValueError("state, tau, or dt")
    ts = [_finite(t, "time") for t in times]
    if not ts or ts[0] <= 0 or any(b <= a for a, b in zip(ts, ts[1:])) \
            or ts[-1] / dt > MAX_STEPS:
        raise ValueError("times")

    def rhs(t, cc, mm):
        dc = g_fn(t) + q_fn(t) * (co - cc)
        return dc, ((cc - mm) / tau if tau > 0 else dc)

    t, out = 0.0, []
    for target in ts:
        while t < target - 1e-12:
            h = min(dt, target - t)
            k1 = rhs(t, c, m)
            k2 = rhs(t + h / 2, c + h / 2 * k1[0], m + h / 2 * k1[1])
            k3 = rhs(t + h / 2, c + h / 2 * k2[0], m + h / 2 * k2[1])
            k4 = rhs(t + h, c + h * k3[0], m + h * k3[1])
            c += h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
            m += h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
            t += h
        if not (math.isfinite(c) and math.isfinite(m)):
            raise ValueError("non-finite state")
        out.append(m if tau > 0 else c)
    return np.array(out)


def closed_form(g, q, c0, m0, c_out, tau, times):
    """Exact solution for constant g and q (requires q*tau != 1 when tau > 0)."""
    g, q, c0, m0, co, tau = (_finite(v, n) for v, n in
                             ((g, "g"), (q, "q"), (c0, "c0"), (m0, "m0"),
                              (c_out, "c_out"), (tau, "tau")))
    if q <= 0 or tau < 0 or (tau > 0 and abs(q * tau - 1) < 1e-6):
        raise ValueError("q or tau")
    t = np.asarray([_finite(x, "time") for x in times])
    css = co + g / q
    a = c0 - css
    if tau == 0:
        return css + a * np.exp(-q * t)
    b = a / (1 - q * tau)
    return css + (m0 - css - b) * np.exp(-t / tau) + b * np.exp(-q * t)


def _information(model, p, sigma, tol):
    """Fisher information in log-parameters for independent Gaussian noise sigma."""
    p = np.asarray(p, float)
    if sigma <= 0 or not np.all(p > 0):
        raise ValueError("sigma or parameters")
    columns = []
    for i in range(len(p)):
        h = 1e-5 * p[i]
        up, down = p.copy(), p.copy()
        up[i] += h
        down[i] -= h
        columns.append((model(up) - model(down)) / (2 * h) * p[i])
    J = np.array(columns).T
    F = J.T @ J / sigma ** 2
    w, v = np.linalg.eigh(F)
    deficient = bool(w[0] <= tol * w[-1])
    return {"eigenvalues": w, "weakest_direction": v[:, 0], "rank_deficient": deficient,
            "condition": math.inf if w[0] <= 0 else float(w[-1] / w[0]),
            "crb_log_sd": None if deficient else np.sqrt(np.diag(np.linalg.inv(F)))}


def fim_constant(g, q, c0, c_out, tau, times, sigma, tol=RANK_TOL):
    """Information about (log g, log q) for constant parameters, known c0, c_out."""
    c0, co = _finite(c0, "c0"), _finite(c_out, "c_out")
    return _information(lambda p: simulate(lambda t: p[0], lambda t: p[1], c0, c0, co, tau, times),
                        (g, q), _finite(sigma, "sigma"), tol)


def fim_segments(durations, gs, qs, c0, c_out, tau, sample_dt, sigma, tol=RANK_TOL):
    """Information about per-segment (log g, log q); each segment is constant."""
    if not (len(durations) == len(gs) == len(qs) >= 1) or sample_dt <= 0:
        raise ValueError("segments")
    edges = np.cumsum([_finite(d, "duration") for d in durations])
    if np.any(np.diff(np.concatenate(([0.0], edges))) <= 0):
        raise ValueError("durations")
    times = np.arange(sample_dt, edges[-1] + 1e-9, sample_dt)
    c0, co = _finite(c0, "c0"), _finite(c_out, "c_out")

    def model(p):
        def seg(t, offset):
            k = int(np.searchsorted(edges, t, side="right"))
            return p[2 * min(k, len(edges) - 1) + offset]
        return simulate(lambda t: seg(t, 0), lambda t: seg(t, 1), c0, c0, co, tau, times)

    flat = [v for pair in zip(gs, qs) for v in pair]
    return _information(model, flat, _finite(sigma, "sigma"), tol)


def background_bias(g, q, delta_ppm):
    """Constant background error delta shifts the fitted g by -q*delta; q is unchanged.

    Follows from dc/dt = g + q(c_out + delta - c) = (g + q*delta) + q(c_out - c).
    """
    g, q, d = _finite(g, "g"), _finite(q, "q"), _finite(delta_ppm, "delta")
    if q <= 0:
        raise ValueError("q")
    return {"g_fitted": g - q * d, "q_fitted": q, "g_bias": -q * d}


def fit_constant(data, c0, c_out_assumed, tau, times, start, iterations=40):
    """Gauss-Newton fit of (g, q) in log space, used to verify the analytic result."""
    c0, co = _finite(c0, "c0"), _finite(c_out_assumed, "c_out")
    y = np.asarray(data, float)
    lp = np.log(np.asarray(start, float))

    def mdl(v):
        g, q = np.exp(v)
        return simulate(lambda t: g, lambda t: q, c0, c0, co, tau, times)

    for _ in range(iterations):
        r = y - mdl(lp)
        cols = []
        for i in range(2):
            a, b = lp.copy(), lp.copy()
            a[i] += 1e-6
            b[i] -= 1e-6
            cols.append((mdl(a) - mdl(b)) / 2e-6)
        J = np.array(cols).T
        step = np.linalg.solve(J.T @ J + 1e-12 * np.eye(2), J.T @ r)
        lp = lp + step
        if np.max(np.abs(step)) < 1e-12:
            break
    return np.exp(lp)


def alternative_generation(g, q, c0, c_out, k):
    """Return (g2_fn, q2) with q2 = k*q reproducing the constant-(g, q) trajectory.

    g2(t) = k*g + (k-1)*q*(c0 - c_ss)*exp(-q t), c_ss = c_out + g/q. Positive for
    k >= 1 when c0 <= c_ss. Shows that time-varying G and Q cannot both be
    recovered from the concentration series alone.
    """
    g, q, c0, co, k = (_finite(v, n) for v, n in
                       ((g, "g"), (q, "q"), (c0, "c0"), (c_out, "c_out"), (k, "k")))
    if g < 0 or q <= 0 or k < 1:
        raise ValueError("g, q, or k")
    a = c0 - (co + g / q)
    return (lambda t: k * g + (k - 1) * q * a * math.exp(-q * t)), k * q


class Tests(unittest.TestCase):
    C_OUT = 420.0
    G, Q = 3.33, 1 / 60
    TIMES = np.arange(10.0, 1201.0, 10.0)

    def test_unit_conversion(self):
        g, q = to_rates(1e-4, 0.5, 30.0)
        self.assertAlmostEqual(g, 1e-4 / 30 * 1e6, places=9)
        self.assertAlmostEqual(q, 1 / 60, places=12)
        self.assertAlmostEqual(g / q, 200.0, places=6)
        for args in [(-1e-4, 0.5, 30), (1e-4, 0, 30), (1e-4, 0.5, 0), (float("nan"), 0.5, 30), (True, 0.5, 30)]:
            with self.assertRaises(ValueError):
                to_rates(*args)

    def test_rk4_matches_closed_form(self):
        for tau in (0.0, 10.0, 30.0, 90.0):
            for c0 in (self.C_OUT, 500.0, 700.0):
                numeric = simulate(lambda t: self.G, lambda t: self.Q, c0, c0, self.C_OUT, tau, self.TIMES)
                exact = closed_form(self.G, self.Q, c0, c0, self.C_OUT, tau, self.TIMES)
                self.assertLess(np.max(np.abs(numeric - exact)), 1e-4, (tau, c0))
        errors = []
        for dt in (1.0, 0.5):
            numeric = simulate(lambda t: self.G, lambda t: self.Q, 500.0, 500.0, self.C_OUT, 10.0,
                               self.TIMES, dt=dt)
            exact = closed_form(self.G, self.Q, 500.0, 500.0, self.C_OUT, 10.0, self.TIMES)
            errors.append(float(np.max(np.abs(numeric - exact))))
        self.assertLess(errors[1], errors[0] / 8)
        with self.assertRaises(ValueError):
            closed_form(self.G, 1 / 60, 420, 420, 420, 60.0, [10.0])

    def test_steady_state_identifies_only_the_ratio(self):
        css = self.C_OUT + self.G / self.Q
        info = fim_constant(self.G, self.Q, css, self.C_OUT, 0.0, self.TIMES, 5.0)
        self.assertTrue(info["rank_deficient"])
        self.assertIsNone(info["crb_log_sd"])
        self.assertGreater(abs(info["weakest_direction"] @ np.array([1.0, 1.0]) / math.sqrt(2)), 0.999999)

    def test_transient_identifies_both_with_finite_bounds(self):
        info = fim_constant(self.G, self.Q, self.C_OUT, self.C_OUT, 0.0, self.TIMES, 5.0)
        self.assertFalse(info["rank_deficient"])
        self.assertTrue(np.all(info["crb_log_sd"] > 0) and np.all(info["crb_log_sd"] < 0.1))

    def test_sensor_lag_widens_bounds_monotonically(self):
        previous = 0.0
        for tau in (0.0, 10.0, 30.0, 60.0, 120.0, 300.0):
            info = fim_constant(self.G, self.Q, self.C_OUT, self.C_OUT, tau, self.TIMES, 5.0)
            worst = float(np.max(info["crb_log_sd"]))
            self.assertGreater(worst, previous, tau)
            previous = worst

    def test_short_segments_are_not_identifiable_and_conditioning_is_not_monotone(self):
        args = ([1, 1], (3.33, 1.5), (1 / 60, 1 / 20), self.C_OUT, self.C_OUT, 0.0, 10.0, 5.0)
        def run(T):
            return fim_segments([T, T], *args[1:])
        self.assertTrue(run(5.0)["rank_deficient"])
        short, long_ = run(20.0), run(60.0)
        self.assertFalse(short["rank_deficient"] or long_["rank_deficient"])
        self.assertGreater(short["condition"], 10 * long_["condition"])
        self.assertGreater(run(600.0)["condition"], long_["condition"])

    def test_background_error_shifts_g_exactly_and_q_not_at_all(self):
        data = simulate(lambda t: self.G, lambda t: self.Q, self.C_OUT, self.C_OUT, self.C_OUT, 0.0, self.TIMES)
        for delta in (5.0, -5.0, 20.0):
            predicted = background_bias(self.G, self.Q, delta)
            fitted = fit_constant(data, self.C_OUT, self.C_OUT + delta, 0.0, self.TIMES, (self.G, self.Q))
            self.assertAlmostEqual(fitted[0], predicted["g_fitted"], places=6)
            self.assertAlmostEqual(fitted[1], self.Q, places=9)
        residual = data - simulate(lambda t: self.G + self.Q * 5.0, lambda t: self.Q, self.C_OUT, self.C_OUT, self.C_OUT, 0.0, self.TIMES)
        self.assertGreater(np.max(np.abs(residual)), 1.0)

    def test_time_varying_g_and_q_are_not_jointly_identifiable(self):
        base = simulate(lambda t: self.G, lambda t: self.Q, self.C_OUT, self.C_OUT, self.C_OUT, 0.0, self.TIMES)
        for k in (1.5, 2.0, 4.0):
            g2, q2 = alternative_generation(self.G, self.Q, self.C_OUT, self.C_OUT, k)
            alt = simulate(g2, lambda t: q2, self.C_OUT, self.C_OUT, self.C_OUT, 0.0, self.TIMES)
            self.assertLess(np.max(np.abs(alt - base)), 1e-5, k)
            self.assertGreater(q2, self.Q)
            self.assertTrue(all(g2(t) > 0 for t in self.TIMES))
            self.assertGreater(abs(g2(600.0) - self.G), 0.1)
        constant = fim_constant(self.G, self.Q, self.C_OUT, self.C_OUT, 0.0, self.TIMES, 5.0)
        self.assertFalse(constant["rank_deficient"])

    def test_invalid_inputs(self):
        ok = (lambda t: 1.0, lambda t: 0.01, 420.0, 420.0, 420.0, 0.0, [10.0])
        bad = [("x", ok[1]) + ok[2:], ok[:2] + (-1.0,) + ok[3:], ok[:5] + (-1.0, [10.0]),
               ok[:6] + ([],), ok[:6] + ([10.0, 5.0],), ok[:6] + ([0.0],), ok[:6] + ([float("nan")],)]
        for args in bad:
            with self.assertRaises(ValueError):
                simulate(*args)
        with self.assertRaises(ValueError):
            simulate(*ok, dt=0.0)
        with self.assertRaises(ValueError):
            simulate(*ok[:5], 1.0, [10.0], dt=1.0)
        with self.assertRaises(ValueError):
            fim_constant(self.G, self.Q, 420, 420, 0.0, self.TIMES, 0.0)
        with self.assertRaises(ValueError):
            fim_segments([1], (1.0, 2.0), (0.01,), 420, 420, 0.0, 10.0, 5.0)
        with self.assertRaises(ValueError):
            background_bias(1.0, 0.0, 1.0)
        with self.assertRaises(ValueError):
            alternative_generation(1.0, 0.01, 420, 420, 0.5)


if __name__ == "__main__":
    unittest.main()
