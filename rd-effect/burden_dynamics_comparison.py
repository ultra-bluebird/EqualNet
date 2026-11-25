# SPDX-License-Identifier: MIT OR Apache-2.0
"""Burden-dynamics model comparison on AGGREGATE series (synthetic tests only).

Scalar aggregate burden x_t (for example unmet requests per week), intervention
quantity u_t, external conditions z_t. M0 is additive:
    x_{t+1} = c + a x_t + b u_t + d z_t + e_t
M1 lets the intervention change persistence:
    x_{t+1} = c + (a + k u_t) x_t + b u_t + d z_t + e_t
Series convention: x has n+1 values; u and every z series have n values (the
values in force when moving from x_t to x_{t+1}). Nothing here identifies a
causal effect: a comparison "under the model" is not a causal claim, and no
result may be used to decide who receives assistance. Requires numpy.
"""
import math
import random
import unittest

import numpy as np

MIN_STEPS = 12


def _vec(v, name, length=None):
    if isinstance(v, (str, bytes)) or not hasattr(v, "__len__"):
        raise ValueError(name)
    out = []
    for item in v:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, (int, float, np.integer, np.floating)) \
                or not math.isfinite(item):
            raise ValueError(name)
        out.append(float(item))
    if length is not None and len(out) != length:
        raise ValueError(name)
    return np.array(out)


def _prepare(x, u, z):
    x = _vec(x, "x")
    n = len(x) - 1
    if n < MIN_STEPS:
        raise ValueError("series too short")
    u = _vec(u, "u", n)
    zs = []
    if z is not None:
        if isinstance(z, (str, bytes)) or not hasattr(z, "__len__") or not len(z):
            raise ValueError("z")
        zs = [_vec(s, "z", n) for s in z]
    return x, u, zs


def _design(x, u, zs, interaction, intercept):
    cols = ([np.ones(len(u))] if intercept else []) + [x[:-1], u] + list(zs)
    names = (["c"] if intercept else []) + ["a", "b"] + ["d%d" % i for i in range(len(zs))]
    if interaction:
        cols.append(u * x[:-1])
        names.append("k")
    return np.column_stack(cols), names


def _fit(X, y, names):
    m, p = X.shape
    if m <= p or np.linalg.matrix_rank(X) < p:
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    rss = float(resid @ resid)
    if rss <= 0:
        return None
    sigma2 = rss / (m - p)
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
    return {"names": tuple(names), "beta": dict(zip(names, map(float, beta))),
            "se": dict(zip(names, map(float, se))), "rss": rss, "m": m, "p": p,
            "sigma": math.sqrt(sigma2), "resid": resid,
            "aic": m * math.log(rss / m) + 2 * p, "bic": m * math.log(rss / m) + p * math.log(m)}


def _max_vif(R):
    worst = 1.0
    for j in range(R.shape[1]):
        col = R[:, j]
        total = float(((col - col.mean()) ** 2).sum())
        if total == 0:
            return math.inf
        others = np.column_stack([np.ones(len(col))] + [R[:, i] for i in range(R.shape[1]) if i != j])
        coef, *_ = np.linalg.lstsq(others, col, rcond=None)
        resid = col - others @ coef
        r2 = 1 - float(resid @ resid) / total
        worst = max(worst, math.inf if r2 >= 1 - 1e-12 else 1 / (1 - r2))
    return worst


def _durbin_watson(resid):
    den = float(resid @ resid)
    return float(np.diff(resid) @ np.diff(resid)) / den if den > 0 else math.nan


def persistence(fit, u):
    """a + k*u for an M1 fit, or a for an M0 fit."""
    return fit["beta"]["a"] + fit["beta"].get("k", 0.0) * u


def equilibrium(fit, u, z=()):
    """Constant-input equilibrium burden, or None when persistence is not below 1 in size."""
    rho = persistence(fit, u)
    if abs(rho) >= 1:
        return None
    b = fit["beta"]
    level = b.get("c", 0.0) + b["b"] * u + sum(b["d%d" % i] * v for i, v in enumerate(z))
    return level / (1 - rho)


def compare(x, u, z=None, intercept=True, boot=300, seed=1, alpha=0.05, corr_flag=0.3, vif_flag=10.0,
            dw_band=(1.5, 2.5), stationarity_limit=1.0):
    x, u, zs = _prepare(x, u, z)
    if (type(boot) is not int or not 50 <= boot <= 5000 or type(seed) is not int
            or not 0 < alpha < 1 or corr_flag <= 0 or vif_flag <= 1 or type(intercept) is not bool
            or type(dw_band) is not tuple or len(dw_band) != 2
            or not 0 < float(dw_band[0]) < float(dw_band[1]) < 4 or not stationarity_limit > 0):
        raise ValueError("options")
    y = x[1:]
    X0, n0 = _design(x, u, zs, False, intercept)
    X1, n1 = _design(x, u, zs, True, intercept)
    m0 = _fit(X0, y, n0)
    if m0 is None:
        return {"status": "not_identified", "reasons": ("INTERVENTION_NOT_IDENTIFIED",),
                "causal_claim_authorized": False}
    m1 = _fit(X1, y, n1)
    flags = ["UNOBSERVED_CONFOUNDING_NOT_TESTABLE"]
    regressors = np.column_stack([x[:-1], u] + zs)
    if _max_vif(regressors) > vif_flag:
        flags.append("WEAK_IDENTIFICATION")
    if np.std(u) > 0 and abs(float(np.corrcoef(u, x[:-1])[0, 1])) > corr_flag:
        flags.append("ALLOCATION_TRACKS_OBSERVED_BURDEN")
    dw = _durbin_watson(m0["resid"])
    if not dw_band[0] <= dw <= dw_band[1]:
        flags.append("RESIDUAL_AUTOCORRELATION")
    if len(y) < 10 * (m1["p"] if m1 else m0["p"]):
        flags.append("SMALL_SAMPLE")
    if abs(m0["beta"]["a"]) >= stationarity_limit or (
            m1 is not None and abs(persistence(m1, float(u.mean()))) >= stationarity_limit):
        flags.append("NONSTATIONARY_FIT")
    out = {"status": "ok", "m0": m0, "m1": m1, "flags": tuple(flags), "durbin_watson": dw,
           "causal_claim_authorized": False}
    if m1 is None:
        out.update(label="interaction_not_identified", boot_p=None, f_stat=None)
        return out
    f_stat = (m0["rss"] - m1["rss"]) / (m1["rss"] / (m1["m"] - m1["p"]))
    rnd, beta0, count = random.Random(seed), np.array([m0["beta"][k] for k in n0]), 0
    for _ in range(boot):
        xs = [x[0]]
        for t in range(len(u)):
            row = ([1.0] if intercept else []) + [xs[-1], u[t]] + [s[t] for s in zs]
            xs.append(float(np.dot(row, beta0)) + m0["sigma"] * rnd.gauss(0, 1))
        xs = np.array(xs)
        a0, _ = _design(xs, u, zs, False, intercept)
        a1, _ = _design(xs, u, zs, True, intercept)
        f0, f1 = _fit(a0, xs[1:], n0), _fit(a1, xs[1:], n1)
        if f0 is None or f1 is None:
            continue
        if (f0["rss"] - f1["rss"]) / (f1["rss"] / (f1["m"] - f1["p"])) >= f_stat:
            count += 1
    boot_p = (1 + count) / (boot + 1)
    aic_pref, bic_pref = m1["aic"] < m0["aic"], m1["bic"] < m0["bic"]
    if aic_pref and bic_pref and boot_p < alpha:
        label = "interaction_supported_under_model"
    elif not aic_pref and not bic_pref:
        label = "additive_sufficient_under_model"
    else:
        label = "inconclusive"
    out.update(label=label, boot_p=boot_p, f_stat=f_stat, delta_aic=m1["aic"] - m0["aic"],
               delta_bic=m1["bic"] - m0["bic"])
    return out


class Tests(unittest.TestCase):
    @staticmethod
    def gen(n, seed, a=0.7, b=-0.5, k=0.0, d=0.3, c=2.0, sig=0.5, conf=0.0, g=0.0, persist=0.0, track=0.0, u_sd=0.3):
        rnd = random.Random(seed)
        x, u, z, w, zz = [5.0], [], [], 0.0, 0.0
        for _ in range(n):
            zz = 0.7 * zz + rnd.gauss(0, 1)
            w = persist * w + rnd.gauss(0, 1)
            ut = max(0.0, 1.0 + conf * w + track * (x[-1] - 5.0) + rnd.gauss(0, u_sd))
            z.append(zz)
            u.append(ut)
            x.append(c + (a + k * ut) * x[-1] + b * ut + d * zz + g * w + rnd.gauss(0, sig))
        return x, u, [z]

    @staticmethod
    def shift(n, seed, zsd=1.0):
        rnd = random.Random(seed)
        x, u, z = [8.0], [], []
        for t in range(n):
            zt = (2.0 if t < n // 2 else 0.0) + rnd.gauss(0, zsd)
            ut = 0.0 if t < n // 2 else 1.0
            z.append(zt)
            u.append(ut)
            x.append(0.7 * x[-1] + zt + 1.0 + rnd.gauss(0, 0.3))
        return x, u, [z]

    def test_additive_truth_is_recovered_and_the_additive_model_suffices(self):
        r = compare(*self.gen(400, 1))
        truth = {"c": 2.0, "a": 0.7, "b": -0.5, "d0": 0.3}
        for name, value in truth.items():
            self.assertLess(abs(r["m0"]["beta"][name] - value), 3 * r["m0"]["se"][name], name)
        self.assertEqual(r["label"], "additive_sufficient_under_model")
        self.assertGreater(r["boot_p"], 0.05)
        self.assertFalse(r["causal_claim_authorized"])

    def test_a_persistence_change_is_detected_and_summarised(self):
        r = compare(*self.gen(400, 2, a=0.8, b=-0.2, k=-0.3, u_sd=0.8))
        self.assertEqual(r["label"], "interaction_supported_under_model")
        self.assertLess(r["delta_bic"], -10)
        self.assertLess(abs(r["m1"]["beta"]["k"] + 0.3), 3 * r["m1"]["se"]["k"])
        self.assertAlmostEqual(persistence(r["m1"], 1.0), 0.5, delta=0.1)
        self.assertLess(persistence(r["m1"], 2.0), persistence(r["m1"], 0.0))
        self.assertGreater(equilibrium(r["m1"], 0.0), equilibrium(r["m1"], 1.0))

    def test_little_variation_in_the_intervention_leaves_a_real_change_inconclusive(self):
        r = compare(*self.gen(400, 2, a=0.8, b=-0.2, k=-0.3, u_sd=0.3))
        self.assertEqual(r["label"], "inconclusive")
        self.assertLess(r["m1"]["beta"]["a"], 0.7)
        self.assertGreater(r["m1"]["se"]["k"], 0.06)

    def test_equilibrium_arithmetic_and_nonstationary_case(self):
        fit = {"beta": {"c": 2.0, "a": 0.5, "b": -1.0, "d0": 0.5, "k": -0.1}}
        self.assertAlmostEqual(equilibrium(fit, 1.0, (2.0,)), (2.0 - 1.0 + 1.0) / (1 - 0.4), places=12)
        self.assertIsNone(equilibrium({"beta": {"c": 1.0, "a": 1.0, "b": 0.0}}, 0.0))
        self.assertIsNone(equilibrium({"beta": {"a": 0.9, "k": 0.2, "b": 0.0}}, 1.0))
        self.assertEqual(equilibrium({"beta": {"a": 0.5, "b": 1.0}}, 2.0), 4.0)

    def test_unobserved_confounder_flips_the_sign_without_any_flag(self):
        r = compare(*self.gen(600, 3, conf=0.5, g=1.0, persist=0.0))
        b = r["m0"]["beta"]["b"]
        self.assertGreater(b, 0.5)
        self.assertGreater(b - (-0.5), 10 * r["m0"]["se"]["b"])
        self.assertEqual(r["flags"], ("UNOBSERVED_CONFOUNDING_NOT_TESTABLE",))

    def test_targeting_on_observed_burden_is_flagged_and_harmless_only_when_modelled(self):
        r = compare(*self.gen(600, 5, track=0.15))
        self.assertIn("ALLOCATION_TRACKS_OBSERVED_BURDEN", r["flags"])
        self.assertLess(abs(r["m0"]["beta"]["b"] + 0.5), 3 * r["m0"]["se"]["b"])

    def test_external_shift_coinciding_with_the_intervention_creates_a_spurious_effect(self):
        x, u, z = self.shift(300, 4)
        without = compare(x, u, None)
        self.assertGreater(abs(without["m0"]["beta"]["b"]) / without["m0"]["se"]["b"], 5)
        self.assertLess(without["m0"]["beta"]["b"], -1.0)
        with_z = compare(x, u, z)
        self.assertLess(abs(with_z["m0"]["beta"]["b"]), 3 * with_z["m0"]["se"]["b"])

    def test_near_collinear_intervention_and_external_series_are_flagged(self):
        weak = compare(*self.shift(300, 4, zsd=0.3))
        strong = compare(*self.shift(300, 4, zsd=2.0))
        self.assertIn("WEAK_IDENTIFICATION", weak["flags"])
        self.assertNotIn("WEAK_IDENTIFICATION", strong["flags"])
        self.assertGreater(weak["m0"]["se"]["b"], strong["m0"]["se"]["b"])

    def test_constant_intervention_is_not_identified(self):
        x, _, z = self.gen(100, 6)
        r = compare(x, [1.0] * 100, z)
        self.assertEqual((r["status"], r["reasons"]), ("not_identified", ("INTERVENTION_NOT_IDENTIFIED",)))
        self.assertFalse(r["causal_claim_authorized"])

    def test_bootstrap_is_deterministic_and_not_wildly_anti_conservative(self):
        x, u, z = self.gen(150, 7)
        first, again = compare(x, u, z, boot=100, seed=9), compare(x, u, z, boot=100, seed=9)
        self.assertEqual(first["boot_p"], again["boot_p"])
        rejections = 0
        for s in range(20):
            r = compare(*self.gen(150, 100 + s), boot=80, seed=s)
            rejections += r["boot_p"] < 0.05
        self.assertLessEqual(rejections / 20, 0.2)

    def test_small_samples_and_residual_autocorrelation_are_flagged(self):
        r = compare(*self.gen(30, 8), boot=60)
        self.assertIn("SMALL_SAMPLE", r["flags"])
        rnd, x, u = random.Random(3), [0.0], []
        for t in range(200):
            u.append(float(t % 5))
            x.append(0.1 * x[-1] + 0.5 * math.sin(t / 8) * 3 + rnd.gauss(0, 0.1))
        self.assertIn("RESIDUAL_AUTOCORRELATION", compare(x, u, boot=60)["flags"])

    def test_nonstationary_fit_is_flagged(self):
        rnd, x, u = random.Random(1), [1.0], [float(i % 3) for i in range(100)]
        for t in range(100):
            x.append(1.02 * x[-1] + 0.2 * u[t] + rnd.gauss(0, 0.05))
        self.assertIn("NONSTATIONARY_FIT", compare(x, u, boot=60)["flags"])

    def test_series_length_and_parameter_count_boundaries(self):
        x, u, z = self.gen(12, 11)
        self.assertEqual(compare(x, u, z, boot=50)["status"], "ok")
        x, u, z = self.gen(11, 11)
        with self.assertRaises(ValueError):
            compare(x, u, z, boot=50)
        rnd = random.Random(5)
        x, u, _ = self.gen(12, 12)
        many = [[rnd.gauss(0, 1) for _ in range(12)] for _ in range(9)]
        self.assertEqual(compare(x, u, many, boot=50)["status"], "not_identified")
        self.assertEqual(compare(x, u, many[:8], boot=50)["status"], "ok")

    def test_threshold_options_are_inclusive_exactly_where_documented(self):
        x, u, z = self.gen(300, 21, track=0.15)
        base = compare(x, u, z, boot=50)
        regs = np.column_stack([np.array(x)[:-1], np.array(u)] + [np.array(s) for s in z])
        vif = _max_vif(regs)
        self.assertNotIn("WEAK_IDENTIFICATION", compare(x, u, z, boot=50, vif_flag=vif)["flags"])
        self.assertIn("WEAK_IDENTIFICATION", compare(x, u, z, boot=50, vif_flag=vif - 1e-9)["flags"])
        corr = abs(float(np.corrcoef(np.array(u), np.array(x)[:-1])[0, 1]))
        self.assertNotIn("ALLOCATION_TRACKS_OBSERVED_BURDEN", compare(x, u, z, boot=50, corr_flag=corr)["flags"])
        self.assertIn("ALLOCATION_TRACKS_OBSERVED_BURDEN", compare(x, u, z, boot=50, corr_flag=corr - 1e-9)["flags"])
        dw = base["durbin_watson"]
        self.assertNotIn("RESIDUAL_AUTOCORRELATION", compare(x, u, z, boot=50, dw_band=(dw, dw + 0.5))["flags"])
        self.assertIn("RESIDUAL_AUTOCORRELATION", compare(x, u, z, boot=50, dw_band=(dw + 1e-9, dw + 0.5))["flags"])
        self.assertNotIn("RESIDUAL_AUTOCORRELATION", compare(x, u, z, boot=50, dw_band=(dw - 0.5, dw))["flags"])
        self.assertIn("RESIDUAL_AUTOCORRELATION", compare(x, u, z, boot=50, dw_band=(dw - 0.5, dw - 1e-9))["flags"])
        top = max(abs(base["m0"]["beta"]["a"]), abs(persistence(base["m1"], float(np.mean(u)))))
        self.assertIn("NONSTATIONARY_FIT", compare(x, u, z, boot=50, stationarity_limit=top)["flags"])
        self.assertNotIn("NONSTATIONARY_FIT", compare(x, u, z, boot=50, stationarity_limit=top + 1e-9)["flags"])

    def test_sample_size_flag_boundary_and_exact_alpha_comparison(self):
        self.assertNotIn("SMALL_SAMPLE", compare(*self.gen(50, 13), boot=50)["flags"])
        self.assertIn("SMALL_SAMPLE", compare(*self.gen(49, 13), boot=50)["flags"])
        x, u, z = self.gen(400, 2, a=0.8, b=-0.2, k=-0.3, u_sd=0.8)
        p = compare(x, u, z, boot=100, seed=3)["boot_p"]
        self.assertEqual(compare(x, u, z, boot=100, seed=3, alpha=p)["label"], "inconclusive")
        self.assertEqual(compare(x, u, z, boot=100, seed=3, alpha=min(0.99, p + 1e-9))["label"],
                         "interaction_supported_under_model")

    def test_option_bounds_are_exact(self):
        x, u, z = self.gen(30, 14)
        compare(x, u, z, boot=50)
        for kw in (dict(boot=49), dict(boot=5001), dict(alpha=0.0), dict(alpha=1.0), dict(dw_band=(2.5, 1.5)),
                   dict(dw_band=(0.0, 2.0)), dict(dw_band=(1.0, 4.0)), dict(dw_band=[1.5, 2.5]),
                   dict(stationarity_limit=0)):
            with self.assertRaises(ValueError):
                compare(x, u, z, **kw)

    def test_invalid_inputs(self):
        x, u, z = self.gen(40, 9)
        for args in ((x, u[:-1], z), (x[:5], u[:4], None), (x[:-1], u, z), ("abc", u, z),
                     ([float("nan")] + x[1:], u, z), ([True] + x[1:], u, z), (x, u, [z[0][:-1]]),
                     (x, u, []), (x, u, "z")):
            with self.assertRaises(ValueError):
                compare(*args)
        for kw in (dict(boot=10), dict(boot=True), dict(alpha=1.0), dict(corr_flag=0), dict(vif_flag=1),
                   dict(intercept=1)):
            with self.assertRaises(ValueError):
                compare(x, u, z, **kw)


if __name__ == "__main__":
    unittest.main()
