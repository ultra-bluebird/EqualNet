# SPDX-License-Identifier: MIT OR Apache-2.0
"""Toy limits of a weighted quadratic residual V = sum(w_j * r_j^2) and its step predicate.

Locally defined toy model only. It does not read, test, or characterise any real
cyboquatic-ecosafety implementation; types and predicates such as RiskVector,
LyapunovResidual, and safestep_ok are modelled here only as the DESCRIBED interfaces.
Each function builds a counterexample showing what the predicate cannot establish:
a worsening component hidden by offsets, cumulative growth under repeated positive
epsilon, saturation by corridor clamping, a stuck sensor, weight dependence, and a
well-typed vector whose numbers are false. Nothing here weakens or replaces any
human protection with a score.
"""
from dataclasses import dataclass
import math
import unittest

TOL = 1e-12


@dataclass(frozen=True)
class RiskVector:
    names: tuple
    values: tuple


def validate(rv):
    if not (isinstance(rv, RiskVector) and type(rv.names) is tuple and type(rv.values) is tuple
            and len(rv.names) == len(rv.values) >= 1 and len(set(rv.names)) == len(rv.names)
            and all(type(n) is str and n for n in rv.names)
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in rv.values)):
        raise ValueError("risk vector")


def residual(rv, weights):
    validate(rv)
    if type(weights) is not dict or set(weights) != set(rv.names) or not all(
            type(w) in (int, float) and math.isfinite(w) and w > 0 for w in weights.values()):
        raise ValueError("weights")
    return sum(weights[n] * v * v for n, v in zip(rv.names, rv.values))


def safestep_ok(v_old, v_new, eps, tol=TOL):
    """The described predicate: V_new <= V_old + eps (within a numeric tolerance)."""
    if not all(type(x) in (int, float) and math.isfinite(x) for x in (v_old, v_new, eps, tol)) or eps < 0 or tol < 0:
        raise ValueError("predicate inputs")
    return v_new <= v_old + eps + tol


def componentwise_ok(old, new, eps_each, ceiling):
    """Alternative: no coordinate may rise by more than eps_each or exceed a ceiling."""
    validate(old)
    validate(new)
    if old.names != new.names or not (0 <= eps_each <= 1 and 0 < ceiling <= 1):
        raise ValueError("componentwise inputs")
    return all(n <= o + eps_each + TOL and n <= ceiling + TOL for o, n in zip(old.values, new.values))


class BudgetedGate:
    """Alternative: the predicate plus a cumulative budget on accepted increases of V."""

    def __init__(self, eps, budget):
        if not (eps >= 0 and budget >= 0):
            raise ValueError("gate")
        self.eps, self.budget, self.spent = eps, budget, 0.0

    def try_step(self, v_old, v_new):
        rise = max(0.0, v_new - v_old)
        if not safestep_ok(v_old, v_new, self.eps) or self.spent + rise > self.budget + TOL:
            return False
        self.spent += rise
        return True


def offsetting_move(old, weights, worsen, new_value, offset, eps=0.0):
    """Raise one coordinate and lower another so that V_new <= V_old + eps; None if infeasible."""
    v_old = residual(old, weights)
    if worsen not in old.names or offset not in old.names or worsen == offset or not 0 <= new_value <= 1:
        raise ValueError("move")
    vals = dict(zip(old.names, old.values))
    vals[worsen] = new_value
    rest = sum(weights[n] * vals[n] ** 2 for n in old.names if n != offset)
    room = (v_old + eps - rest) / weights[offset]
    if room < 0:
        return None
    vals[offset] = min(1.0, math.sqrt(room))
    return RiskVector(old.names, tuple(vals[n] for n in old.names))


def creeping_trajectory(r0, weight, eps, max_steps):
    """Single-coordinate path where every step satisfies the predicate yet r reaches 1."""
    if not (0 <= r0 <= 1 and weight > 0 and eps > 0 and type(max_steps) is int and max_steps > 0):
        raise ValueError("creep inputs")
    path = [r0]
    for _ in range(max_steps):
        path.append(min(1.0, math.sqrt(path[-1] ** 2 + eps / weight)))
        if path[-1] >= 1.0:
            break
    return path


def normalize(x, safe, critical):
    """Corridor mapping to [0, 1] with clamping; everything past critical looks the same."""
    if not (all(type(v) in (int, float) and math.isfinite(v) for v in (x, safe, critical)) and critical > safe):
        raise ValueError("normalize inputs")
    return min(1.0, max(0.0, (x - safe) / (critical - safe)))


@dataclass(frozen=True)
class Proposal:
    action: str
    claimed: RiskVector


def accepts(proposal, weights, v_old, eps):
    """A well-typed proposal is checked on its CLAIMED vector; truth of the numbers is out of scope."""
    if not isinstance(proposal, Proposal):
        raise ValueError("proposal")
    return safestep_ok(v_old, residual(proposal.claimed, weights), eps)


class Tests(unittest.TestCase):
    N = ("energy", "hydraulic")
    W = {"energy": 1.0, "hydraulic": 1.0}

    def rv(self, a, b):
        return RiskVector(self.N, (a, b))

    def test_a_component_can_worsen_sixfold_while_the_predicate_passes(self):
        old = self.rv(0.1, 0.9)
        new = offsetting_move(old, self.W, "energy", 0.6, "hydraulic")
        self.assertAlmostEqual(new.values[0], 0.6)
        self.assertAlmostEqual(new.values[1], math.sqrt(0.46))
        v_old, v_new = residual(old, self.W), residual(new, self.W)
        self.assertTrue(safestep_ok(v_old, v_new, 0.0))
        self.assertFalse(componentwise_ok(old, new, 0.05, 1.0))
        self.assertIsNone(offsetting_move(old, self.W, "energy", 1.0, "hydraulic"))
        self.assertIsNone(offsetting_move(self.rv(0.0, 0.1), self.W, "energy", 0.9, "hydraulic"))

    def test_repeated_positive_epsilon_allows_cumulative_growth_to_the_critical_value(self):
        path = creeping_trajectory(0.1, 1.0, 0.01, 200)
        self.assertEqual(path[-1], 1.0)
        self.assertGreaterEqual(len(path), 99)
        for a, b in zip(path, path[1:]):
            self.assertTrue(safestep_ok(a * a, b * b, 0.01))
        self.assertFalse(safestep_ok(path[0] ** 2, path[-1] ** 2, 0.01))
        gate, accepted = BudgetedGate(0.01, 0.055), 0
        for a, b in zip(path, path[1:]):
            if not gate.try_step(a * a, b * b):
                break
            accepted += 1
        self.assertEqual(accepted, 5)
        self.assertAlmostEqual(gate.spent, 0.05, places=9)
        self.assertFalse(componentwise_ok(self.rv(0.1, 0.1), self.rv(0.2, 0.1), 0.05, 1.0))

    def test_clamping_hides_how_far_past_critical_a_reading_is(self):
        self.assertEqual(normalize(10.0, 2.0, 8.0), 1.0)
        self.assertEqual(normalize(80.0, 2.0, 8.0), 1.0)
        self.assertAlmostEqual(normalize(5.0, 2.0, 8.0), 0.5)
        self.assertEqual(normalize(-3.0, 2.0, 8.0), 0.0)
        a, b = self.rv(normalize(10.0, 2.0, 8.0), 0.2), self.rv(normalize(80.0, 2.0, 8.0), 0.2)
        self.assertEqual(residual(a, self.W), residual(b, self.W))

    def test_a_stuck_sensor_keeps_the_predicate_satisfied_while_the_true_state_degrades(self):
        reading = 0.3
        true_path = [0.3 + 0.05 * t for t in range(10)]
        stuck = [residual(self.rv(reading, 0.2), self.W)] * 10
        true_v = [residual(self.rv(r, 0.2), self.W) for r in true_path]
        self.assertTrue(all(safestep_ok(a, b, 0.0) for a, b in zip(stuck, stuck[1:])))
        self.assertFalse(all(safestep_ok(a, b, 0.0) for a, b in zip(true_v, true_v[1:])))
        self.assertGreater(true_v[-1], 2 * stuck[-1])

    def test_acceptance_depends_on_the_weights_which_are_a_governance_choice(self):
        old, new = self.rv(0.2, 0.2), self.rv(0.2, 0.9)
        eq, low = {"energy": 1.0, "hydraulic": 1.0}, {"energy": 1.0, "hydraulic": 0.01}
        self.assertFalse(safestep_ok(residual(old, eq), residual(new, eq), 0.01))
        self.assertTrue(safestep_ok(residual(old, low), residual(new, low), 0.01))
        self.assertFalse(componentwise_ok(old, new, 0.05, 1.0))

    def test_a_well_typed_proposal_can_carry_false_numbers(self):
        v_old = residual(self.rv(0.3, 0.3), self.W)
        honest = Proposal("open valve", self.rv(0.3, 0.9))
        false = Proposal("open valve", self.rv(0.0, 0.0))
        self.assertFalse(accepts(honest, self.W, v_old, 0.01))
        self.assertTrue(accepts(false, self.W, v_old, 0.01))
        for bad in (RiskVector(("a",), (1.5,)), RiskVector(("a", "a"), (0.1, 0.1)), RiskVector((), ()),
                    RiskVector(("a",), (float("nan"),)), RiskVector(("a",), (True,)), "vector"):
            with self.assertRaises(ValueError):
                validate(bad)

    def test_predicate_boundaries_and_input_validation(self):
        self.assertTrue(safestep_ok(1.0, 1.01, 0.01))
        self.assertFalse(safestep_ok(1.0, 1.0100001, 0.01))
        self.assertTrue(safestep_ok(1.0, 1.0100001, 0.01, tol=1e-6))
        for args in ((1.0, 1.0, -0.1), (float("nan"), 1.0, 0.1)):
            with self.assertRaises(ValueError):
                safestep_ok(*args)
        with self.assertRaises(ValueError):
            residual(self.rv(0.1, 0.1), {"energy": 1.0})
        with self.assertRaises(ValueError):
            residual(self.rv(0.1, 0.1), {"energy": 1.0, "hydraulic": 0.0})
        with self.assertRaises(ValueError):
            offsetting_move(self.rv(0.1, 0.1), self.W, "energy", 0.5, "energy")
        with self.assertRaises(ValueError):
            creeping_trajectory(0.1, 1.0, 0.0, 10)
        with self.assertRaises(ValueError):
            normalize(1.0, 5.0, 5.0)
        with self.assertRaises(ValueError):
            componentwise_ok(self.rv(0.1, 0.1), RiskVector(("x", "y"), (0.1, 0.1)), 0.1, 1.0)


if __name__ == "__main__":
    unittest.main()
