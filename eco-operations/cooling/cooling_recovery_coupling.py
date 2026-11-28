# SPDX-License-Identifier: MIT OR Apache-2.0
"""Does cooling energy track wet-bulb exceedance, once ambient dry-bulb and IT load are controlled?

Destination: eco-operations/cooling/
Self-contained: imports only numpy and scipy. Daily features: wet-bulb degree-minutes above a
threshold (DM), dry-bulb cooling degree-minutes (CDD), mean IT load, and a noisy per-day
recovery tau. Candidate models: intercept only (a site-constant, "canopy-only" stand-in),
DM only, DM with controls, and DM with controls plus a DM x tau term. Inference uses a
Newey-West (HAC) interval and a moving-block bootstrap over days. A claim gate requires an
interval excluding zero, BIC improvement of at least 10 and a held-out RMSE improvement.
Synthetic scenarios are MODEL_CONSISTENT. Real paired series are UNRESOLVED until independent
review. Real site data was not available to this code.
"""
import argparse
import hashlib
import json
import math
import platform

import numpy as np
import scipy
from scipy.signal import lfilter

SPD = 288
STEP_MIN = 5.0
SCENARIOS = ("no_weather_term", "wetbulb_linear", "wetbulb_times_tau", "drybulb_only")
SPECS = ("dm_only", "dm_controls", "dm_tau_controls")


def ar1(n, sd, phi, rng, burn=200):
    if n < 1 or sd < 0 or not (0.0 <= phi < 1.0):
        raise ValueError("need n>=1, sd>=0, 0<=phi<1")
    e = rng.normal(0.0, sd * math.sqrt(1.0 - phi * phi), n + burn)
    return lfilter([1.0], [1.0, -phi], e)[burn:]


def manifest(params, seed, source):
    blob = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
    return {"params_sha256": hashlib.sha256(blob).hexdigest(), "seed": seed,
            "data_source": source, "python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__,
            "license": "MIT OR Apache-2.0"}


def evidence_status(source):
    return "MODEL_CONSISTENT" if source.startswith("synthetic") else "UNRESOLVED"


def daily_exceedance(series, thr, step_min=STEP_MIN):
    """Degree-minutes above thr per day; series length must be a whole number of days."""
    s = np.asarray(series, float)
    if s.size % SPD or s.size == 0 or not np.all(np.isfinite(s)):
        raise ValueError("series must be finite and a whole number of 5-minute days")
    return np.maximum(s - thr, 0.0).reshape(-1, SPD).sum(axis=1) * step_min


def synth_days(days, scenario, rng, thr=23.5):
    if scenario not in SCENARIOS or days < 40:
        raise ValueError("unknown scenario or too few days")
    n = days * SPD
    t = np.arange(n) * STEP_MIN
    doy = 120.0 + t / 1440.0
    h = (t % 1440.0) / 60.0
    di = (t // 1440.0).astype(int)
    day_off = rng.normal(0.0, 1.5, days)[di]
    tdb = (34.0 + 4.0 * np.cos(2 * math.pi * (doy - 200.0) / 365.0)
           + 8.0 * np.cos(2 * math.pi * (h - 16.0) / 24.0) + day_off + ar1(n, 0.3, 0.9, rng))
    monsoon = 1.0 / (1.0 + np.exp(-(doy - 185.0) / 10.0)) - 1.0 / (1.0 + np.exp(-(doy - 265.0) / 10.0))
    monsoon = np.clip(monsoon + rng.normal(0.0, 0.2, days)[di], 0.0, 1.0)
    dep = (18.0 - 8.0 * monsoon) * (0.7 + 0.3 * np.cos(2 * math.pi * (h - 16.0) / 24.0))
    tw = tdb - dep
    dm = daily_exceedance(tw, thr) / 100.0
    cdd = daily_exceedance(tdb, 25.0) / 1000.0
    it = 7200.0 + ar1(days, 100.0, 0.7, rng)
    tau = np.exp(np.log(20.0) + rng.normal(0.0, 0.3, days))
    tau_hat = tau * np.exp(rng.normal(0.0, 0.15, days))
    e = 900.0 + 0.1 * (it - 7200.0) + rng.normal(0.0, 60.0, days)
    if scenario == "wetbulb_linear":
        e = e + 2.0 * dm
    elif scenario == "wetbulb_times_tau":
        e = e + 2.0 * dm * (tau / 20.0)
    elif scenario == "drybulb_only":
        e = e + 6.0 * cdd
    return {"E": e, "dm": dm, "cdd": cdd, "it": it, "tau_hat": tau_hat}


def design(d, spec):
    one = np.ones_like(d["dm"])
    if spec == "intercept":
        return np.column_stack([one])
    if spec == "dm_only":
        return np.column_stack([one, d["dm"]])
    ctrl = [one, d["dm"], d["cdd"], d["it"] / 1000.0]
    if spec == "dm_controls":
        return np.column_stack(ctrl)
    if spec == "dm_tau_controls":
        return np.column_stack(ctrl + [d["dm"] * (d["tau_hat"] / 20.0 - 1.0)])
    raise ValueError("unknown spec")


def ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    return beta, r, float(r @ r)


def hac_ci(X, y, j=1, lag=5):
    n, k = X.shape
    beta, r, _ = ols(X, y)
    inv = np.linalg.inv(X.T @ X)
    u = X * r[:, None]
    S = u.T @ u
    for m in range(1, lag + 1):
        G = u[m:].T @ u[:-m]
        S = S + (1 - m / (lag + 1.0)) * (G + G.T)
    cov = inv @ S @ inv * n / (n - k)
    se = math.sqrt(max(cov[j, j], 0.0))
    return float(beta[j] - 1.959964 * se), float(beta[j] + 1.959964 * se)


def block_bootstrap_ci(X, y, rng, j=1, block=7, B=200):
    n = y.size
    nb = int(math.ceil(n / block))
    vals = []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, nb)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        vals.append(np.linalg.lstsq(X[idx], y[idx], rcond=None)[0][j])
    q = np.percentile(vals, [2.5, 97.5])
    return float(q[0]), float(q[1])


def bic(rss, n, k):
    return n * math.log(rss / n) + k * math.log(n)


def split_rmse(d, spec, frac=0.6):
    n = d["E"].size
    m = int(n * frac)
    X = design(d, spec)
    beta, *_ = np.linalg.lstsq(X[:m], d["E"][:m], rcond=None)
    return float(np.sqrt(np.mean((d["E"][m:] - X[m:] @ beta) ** 2)))


def analyse(d, rng, B=200, ref_spec="intercept"):
    n = d["E"].size
    y = d["E"]
    _, _, rss0 = ols(design(d, ref_spec), y)
    rmse0 = split_rmse(d, ref_spec)
    out = {}
    for spec in SPECS:
        X = design(d, spec)
        beta, _, rss = ols(X, y)
        lo, hi = hac_ci(X, y)
        blo, bhi = block_bootstrap_ci(X, y, rng, B=B)
        dbic = bic(rss, n, X.shape[1]) - bic(rss0, n, 1)
        ratio = split_rmse(d, spec) / rmse0
        out[spec] = {"b_dm": float(beta[1]), "hac_ci95": [lo, hi], "boot_ci95": [blo, bhi],
                     "dbic_vs_intercept": dbic, "heldout_rmse_ratio": ratio,
                     "claim_supported": claim_gate(lo, hi, dbic, ratio)}
    X1, X2 = design(d, "dm_controls"), design(d, "dm_tau_controls")
    _, _, r1 = ols(X1, y)
    _, _, r2 = ols(X2, y)
    out["tau_term_dbic_vs_controls"] = bic(r2, n, X2.shape[1]) - bic(r1, n, X1.shape[1])
    return out


def claim_gate(lo, hi, dbic, rmse_ratio):
    """Supported only if the interval excludes zero, BIC improves by >= 10 and held-out RMSE improves."""
    return bool((lo > 0 or hi < 0) and dbic <= -10.0 and rmse_ratio < 0.95)


def run_scenarios(reps=60, days=120, seed=61, B=100):
    if reps < 10:
        raise ValueError("reps >= 10")
    out = {}
    for si, sc in enumerate(SCENARIOS):
        agg = {s: {"supported": 0, "hac_excl0": 0, "boot_excl0": 0, "b": []} for s in SPECS}
        tau_gain = 0
        corr = []
        for r in range(reps):
            rng = np.random.default_rng([seed, si, r])
            d = synth_days(days, sc, rng)
            corr.append(float(np.corrcoef(d["dm"], d["cdd"])[0, 1]) if d["dm"].std() > 0 else float("nan"))
            res = analyse(d, rng, B=B)
            for s in SPECS:
                a, v = agg[s], res[s]
                a["supported"] += v["claim_supported"]
                a["hac_excl0"] += (v["hac_ci95"][0] > 0 or v["hac_ci95"][1] < 0)
                a["boot_excl0"] += (v["boot_ci95"][0] > 0 or v["boot_ci95"][1] < 0)
                a["b"].append(v["b_dm"])
            tau_gain += res["tau_term_dbic_vs_controls"] <= -10.0
        out[sc] = {"median_corr_dm_cdd": float(np.nanmedian(corr)),
                   "tau_term_supported_share": tau_gain / reps,
                   "specs": {s: {"claim_supported_share": a["supported"] / reps,
                                 "hac_ci_excludes_zero_share": a["hac_excl0"] / reps,
                                 "boot_ci_excludes_zero_share": a["boot_excl0"] / reps,
                                 "b_dm_quartiles": [float(x) for x in np.percentile(a["b"], [25, 50, 75])]}
                             for s, a in agg.items()}}
    params = {"reps": reps, "days": days, "B": B}
    return {"evidence_status": evidence_status("synthetic"),
            "manifest": manifest(params, seed, "synthetic_demo_not_observations"),
            "params": params, "results": out,
            "unresolved": ["real_paired_series_not_analysed", "canopy_across_sites_not_modelled",
                           "linear_effects_assumed"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reps", type=int, default=60)
    ap.add_argument("--seed", type=int, default=61)
    ap.add_argument("--boot", type=int, default=100)
    a = ap.parse_args()
    print(json.dumps(run_scenarios(reps=a.reps, seed=a.seed, B=a.boot), indent=2, default=float))


if __name__ == "__main__":
    main()
