# SPDX-License-Identifier: MIT OR Apache-2.0
"""Synthetic counterfactual audit for resource-dependent eligibility.

Run directly with Python 3.12+ to execute synthetic tests.

The adapter must hold permitted eligibility inputs fixed and vary only
the supplied synthetic resource context.

No real housing, payment, or device data is required.

The harness invokes caller-supplied code. It does not guarantee that the
adapter is deterministic, isolated, or free of external side effects.

No observed dependence is a bounded test result, not proof of fairness.
"""

from dataclasses import dataclass
from itertools import product
from typing import Callable
import unittest


class AuditError(ValueError):
    """Malformed audit input or adapter output."""


@dataclass(frozen=True, slots=True)
class SyntheticResources:
    stable_address: bool
    premium_device: bool
    payment_present: bool


@dataclass(frozen=True, slots=True)
class AuditResult:
    evaluated: int
    differing_from_baseline: int

    @property
    def dependence_observed(self) -> bool:
        return self.differing_from_baseline > 0


def audit_resources(
    decide: Callable[[SyntheticResources], bool],
) -> AuditResult:
    """Compare all eight contexts with the all-false baseline.

    False describes a synthetic fixture value, not a judgment about
    an actual person's circumstances.

    Exceptions propagate without producing an affirmative audit result.
    """
    if not callable(decide):
        raise AuditError(
            "isolated test adapter required"
        )

    baseline = None
    different = 0
    evaluated = 0

    for values in product(
        (False, True),
        repeat=3,
    ):
        result = decide(
            SyntheticResources(*values)
        )

        if type(result) is not bool:
            raise AuditError(
                "adapter must return a boolean eligibility result"
            )

        if evaluated == 0:
            baseline = result
        else:
            different += result != baseline

        evaluated += 1

    return AuditResult(
        evaluated=evaluated,
        differing_from_baseline=different,
    )


class AuditTests(unittest.TestCase):
    """Synthetic adapters test the harness, not a production platform."""

    def test_independent_allowed_and_excluded(self):
        for fixed in (False, True):
            result = audit_resources(
                lambda context: fixed
            )

            self.assertEqual(
                result.evaluated,
                8,
            )
            self.assertFalse(
                result.dependence_observed
            )

    def test_each_proxy_dependence_detected(self):
        for name in (
            "stable_address",
            "premium_device",
            "payment_present",
        ):
            result = audit_resources(
                lambda context, name=name:
                    getattr(context, name)
            )

            self.assertTrue(
                result.dependence_observed
            )
            self.assertEqual(
                result.differing_from_baseline,
                4,
            )

    def test_interaction_dependence_detected(self):
        result = audit_resources(
            lambda context:
                context.stable_address
                and context.payment_present
        )

        self.assertEqual(
            result.differing_from_baseline,
            2,
        )

    def test_invalid(self):
        with self.assertRaises(AuditError):
            audit_resources(None)

        with self.assertRaises(AuditError):
            audit_resources(
                lambda context: 1
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
