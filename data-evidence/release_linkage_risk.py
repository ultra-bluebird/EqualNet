# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exact release-differencing advantage on synthetic occupancy models.

Only synthetic distributions are analysed. The result is the best possible
distinguishing advantage for an adversary who knows the declared model; it is
not a guarantee of anonymity outside that model.
"""
from dataclasses import dataclass
import math
import unittest


def _num(value, name):
    if type(value) not in (int, float):
        raise ValueError(name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(name)
    return result


def _poisson(mu, kmax):
    probs = [math.exp(-mu)]
    for k in range(1, kmax + 1):
        probs.append(probs[-1] * mu / k)
    return probs


def ambient_pmf(lam_in, lam_out, steps=1):
    """Net ambient change over `steps` intervals: Poisson in minus Poisson out.

    Returns the truncated pmf and the probability mass lost to truncation.
    """
    a, b = _num(lam_in, "lam_in"), _num(lam_out, "lam_out")
    if type(steps) is not int or not 1 <= steps <= 1000 or a < 0 or b < 0 \
            or max(a, b) * steps > 500:
        raise ValueError("ambient options")
    mu_in, mu_out = a * steps, b * steps
    pin = _poisson(mu_in, int(mu_in + 12 * math.sqrt(mu_in) + 30))
    pout = _poisson(mu_out, int(mu_out + 12 * math.sqrt(mu_out) + 30))
    pmf = {}
    for i, pi in enumerate(pin):
        for j, pj in enumerate(pout):
            mass = pi * pj
            if mass > 0:
                pmf[i - j] = pmf.get(i - j, 0.0) + mass
    return {"pmf": pmf, "truncation_mass": max(0.0, 1.0 - sum(pmf.values()))}


def point_prior(occupancy):
    if type(occupancy) is not int or occupancy < 0:
        raise ValueError("occupancy")
    return {occupancy: 1.0}


def uniform_prior(low, high):
    if type(low) is not int or type(high) is not int or not 0 <= low <= high:
        raise ValueError("range")
    return {o: 1.0 / (high - low + 1) for o in range(low, high + 1)}


@dataclass(frozen=True)
class Policy:
    rounding: int = 1
    suppress_below: int = 0

    def publish(self, value):
        """Round half up to the grid; None means suppressed (true value too low)."""
        if value < self.suppress_below:
            return None
        return ((2 * value + self.rounding) // (2 * self.rounding)) * self.rounding


def _check_policy(policy):
    if not isinstance(policy, Policy) or type(policy.rounding) is not int \
            or not 1 <= policy.rounding <= 1000 or type(policy.suppress_below) is not int \
            or policy.suppress_below < 0:
        raise ValueError("policy")


def risk(prior, ambient, policies, effect=1):
    """Advantage of distinguishing 'target effect absent' from 'present'.

    The adversary sees the pair of published values before and after the
    interval, under every policy at once, and knows prior, ambient model, and
    policies. Advantage = total variation distance = best accuracy - 0.5 under
    a balanced prior. Occupancy after the interval is clamped at zero.
    """
    if type(prior) is not dict or not prior or type(ambient) is not dict \
            or type(policies) is not tuple or not policies or type(effect) is not int \
            or not 1 <= effect <= 10:
        raise ValueError("risk options")
    for policy in policies:
        _check_policy(policy)
    total = 0.0
    for o, p in prior.items():
        if type(o) is not int or o < 0 or _num(p, "prior") < 0:
            raise ValueError("prior")
        total += p
    pmf = ambient.get("pmf")
    if abs(total - 1.0) > 1e-9 or type(pmf) is not dict or not pmf:
        raise ValueError("prior or ambient")
    absent, present = {}, {}
    suppressed = [0.0] * len(policies)
    error_sum = [0.0] * len(policies)
    kept = [0.0] * len(policies)
    for o, po in prior.items():
        for n, pn in pmf.items():
            mass = po * pn
            for shift, store in ((0, absent), (effect, present)):
                after = max(0, o + n + shift)
                key = tuple((g.publish(o), g.publish(after)) for g in policies)
                store[key] = store.get(key, 0.0) + mass
                if shift == 0:
                    for i, g in enumerate(policies):
                        published = g.publish(after)
                        if published is None:
                            suppressed[i] += mass
                        else:
                            kept[i] += mass
                            error_sum[i] += mass * abs(published - after)
    keys = set(absent) | set(present)
    advantage = 0.5 * sum(abs(absent.get(k, 0.0) - present.get(k, 0.0)) for k in keys)
    return {"advantage": advantage, "distinct_outcomes": len(keys),
            "truncation_mass": ambient.get("truncation_mass", 0.0),
            "suppression_probability": tuple(suppressed),
            "mean_abs_transformation_error": tuple(
                (error_sum[i] / kept[i]) if kept[i] > 0 else None for i in range(len(policies))),
            "release_authorized": False}


class Tests(unittest.TestCase):
    def test_pmf_moments_and_truncation(self):
        for lam_in, lam_out, steps in [(2.0, 2.0, 1), (3.0, 1.0, 2), (0.5, 0.0, 4)]:
            amb = ambient_pmf(lam_in, lam_out, steps)
            mean = sum(n * p for n, p in amb["pmf"].items())
            var = sum((n - mean) ** 2 * p for n, p in amb["pmf"].items())
            self.assertAlmostEqual(mean, (lam_in - lam_out) * steps, places=6)
            self.assertAlmostEqual(var, (lam_in + lam_out) * steps, places=6)
            self.assertLess(amb["truncation_mass"], 1e-9)
        for args in [(-1, 1), (1, -1), (float("nan"), 1), (True, 1), (600, 1)]:
            with self.assertRaises(ValueError):
                ambient_pmf(*args)
        with self.assertRaises(ValueError):
            ambient_pmf(1, 1, steps=0)

    def test_exact_values_for_identity_release(self):
        amb = ambient_pmf(0.01, 0.01)
        quiet = risk(point_prior(10), amb, (Policy(),))["advantage"]
        self.assertGreater(quiet, 0.9)
        busy = risk(point_prior(100), ambient_pmf(50, 50), (Policy(),))["advantage"]
        self.assertLess(busy, 0.1)
        self.assertGreater(busy, 0.0)

    def test_more_ambient_steps_reduce_advantage(self):
        one = risk(point_prior(10), ambient_pmf(1, 1, 1), (Policy(),))["advantage"]
        four = risk(point_prior(10), ambient_pmf(1, 1, 4), (Policy(),))["advantage"]
        self.assertLess(four, one)

    def test_rounding_protects_away_from_boundary_and_leaks_at_it(self):
        amb, grid = ambient_pmf(0.01, 0.01), (Policy(rounding=5),)
        self.assertGreater(risk(point_prior(7), amb, grid)["advantage"], 0.9)
        self.assertLess(risk(point_prior(5), amb, grid)["advantage"], 0.05)

    def test_uncertain_alignment_reduces_leak_below_identity(self):
        amb, prior = ambient_pmf(0.5, 0.5), uniform_prior(40, 59)
        identity = risk(prior, amb, (Policy(),))["advantage"]
        rounded = risk(prior, amb, (Policy(rounding=5),))["advantage"]
        self.assertLess(rounded, identity - 0.05)

    def test_suppression_boundary(self):
        amb, policy = ambient_pmf(0.01, 0.01), (Policy(suppress_below=5),)
        self.assertLess(risk(point_prior(2), amb, policy)["advantage"], 0.05)
        self.assertGreater(risk(point_prior(4), amb, policy)["advantage"], 0.9)
        r = risk(point_prior(2), amb, policy)
        self.assertGreater(r["suppression_probability"][0], 0.9)

    def test_combining_releases_never_reduces_advantage(self):
        amb, prior = ambient_pmf(0.5, 0.5), uniform_prior(40, 59)
        coarse, fine = (Policy(rounding=5),), (Policy(),)
        both = risk(prior, amb, coarse + fine)["advantage"]
        self.assertGreaterEqual(both + 1e-12, risk(prior, amb, coarse)["advantage"])
        self.assertGreaterEqual(both + 1e-12, risk(prior, amb, fine)["advantage"])

    def test_transformation_error_is_separate_from_advantage(self):
        r = risk(uniform_prior(40, 59), ambient_pmf(0.5, 0.5), (Policy(), Policy(rounding=5)))
        self.assertEqual(r["mean_abs_transformation_error"][0], 0.0)
        self.assertGreater(r["mean_abs_transformation_error"][1], 0.5)
        self.assertEqual(r["suppression_probability"], (0.0, 0.0))

    def test_invalid_inputs(self):
        amb = ambient_pmf(1, 1)
        bad_calls = [({}, amb, (Policy(),)), ({5: 0.5}, amb, (Policy(),)),
                     ({-1: 1.0}, amb, (Policy(),)), ({5: 1.0}, {}, (Policy(),)),
                     ({5: 1.0}, amb, ()), ({5: 1.0}, amb, (Policy(rounding=0),)),
                     ({5: 1.0}, amb, (Policy(suppress_below=-1),)), ({5: 1.0}, amb, [Policy()])]
        for args in bad_calls:
            with self.assertRaises(ValueError):
                risk(*args)
        with self.assertRaises(ValueError):
            risk({5: 1.0}, amb, (Policy(),), effect=0)
        for args in [(True,), (-1,)]:
            with self.assertRaises(ValueError):
                point_prior(*args)
        with self.assertRaises(ValueError):
            uniform_prior(5, 4)


if __name__ == "__main__":
    unittest.main()
