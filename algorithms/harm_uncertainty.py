# SPDX-License-Identifier: MIT OR Apache-2.0
"""Classify a supplied harm interval against a reviewed ceiling.

Run directly with Python 3.12+ to execute synthetic tests.

The caller must establish the outcome definition, scale, direction,
confidence procedure, multiplicity handling, and ceiling before analysis.

Lower harm values are preferable. Equality is not a passing result.
No release authorization or benefit offset is implemented.
"""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import unittest


class GuardrailError(ValueError):
    """Malformed interval or ceiling input."""


class Finding(Enum):
    BELOW_CEILING = "below_ceiling"
    AT_OR_ABOVE_CEILING = "at_or_above_ceiling"
    INCONCLUSIVE = "inconclusive"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class Interval:
    lower: Fraction
    upper: Fraction

    def __post_init__(self):
        if (
            type(self.lower) is not Fraction
            or type(self.upper) is not Fraction
        ):
            raise GuardrailError(
                "exact Fraction endpoints required"
            )

        if self.lower > self.upper:
            raise GuardrailError(
                "lower endpoint exceeds upper endpoint"
            )


def assess_harm(
    interval: Interval | None,
    ceiling: Fraction,
) -> Finding:
    """Classify supplied uncertainty without estimating evidence."""
    if type(ceiling) is not Fraction:
        raise GuardrailError(
            "exact reviewed ceiling required"
        )

    if interval is None:
        return Finding.NOT_ASSESSED

    if type(interval) is not Interval:
        raise GuardrailError(
            "validated interval required"
        )

    if interval.upper < ceiling:
        return Finding.BELOW_CEILING

    if interval.lower >= ceiling:
        return Finding.AT_OR_ABOVE_CEILING

    return Finding.INCONCLUSIVE


class GuardrailTests(unittest.TestCase):
    """Synthetic thresholds are not approved product policy."""

    def test_below_and_equal(self):
        ceiling = Fraction(1, 20)

        self.assertIs(
            assess_harm(
                Interval(
                    Fraction(-1, 100),
                    Fraction(1, 100),
                ),
                ceiling,
            ),
            Finding.BELOW_CEILING,
        )

        self.assertIs(
            assess_harm(
                Interval(ceiling, ceiling),
                ceiling,
            ),
            Finding.AT_OR_ABOVE_CEILING,
        )

    def test_crossing_and_boundary(self):
        ceiling = Fraction(1, 20)

        self.assertIs(
            assess_harm(
                Interval(
                    Fraction(0),
                    ceiling,
                ),
                ceiling,
            ),
            Finding.INCONCLUSIVE,
        )

        self.assertIs(
            assess_harm(
                Interval(
                    Fraction(0),
                    Fraction(1, 10),
                ),
                ceiling,
            ),
            Finding.INCONCLUSIVE,
        )

    def test_missing(self):
        self.assertIs(
            assess_harm(
                None,
                Fraction(0),
            ),
            Finding.NOT_ASSESSED,
        )

    def test_invalid(self):
        calls = (
            lambda: Interval(
                Fraction(1),
                Fraction(0),
            ),
            lambda: Interval(
                0.0,
                Fraction(1),
            ),
            lambda: assess_harm(
                None,
                0.05,
            ),
        )

        for call in calls:
            with self.assertRaises(GuardrailError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
