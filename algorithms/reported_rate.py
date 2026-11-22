# SPDX-License-Identifier: MIT OR Apache-2.0
"""Observed reported-event rates with explicit zero-exposure handling.

Run directly with Python 3.12+ to execute synthetic tests.

Inputs must already share an approved category, population, attribution
rule, and observation window. This module does not verify those conditions.

Rates are descriptive count ratios, not probabilities or safety scores.
No logging, persistence, networking, or member data processing occurs.
"""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import unittest


class MetricError(ValueError):
    """Malformed metric input."""


class Numerator(Enum):
    REPORTS = "reports"
    DISTINCT_REPORTED_EVENTS = "distinct_reported_events"
    REPORTING_MEMBERS = "reporting_members"


@dataclass(frozen=True, slots=True)
class ReportedRate:
    count: int
    exposures: int
    numerator: Numerator

    def __post_init__(self):
        if any(
            type(value) is not int or value < 0
            for value in (self.count, self.exposures)
        ):
            raise MetricError(
                "counts must be nonnegative built-in integers"
            )

        if type(self.numerator) is not Numerator:
            raise MetricError(
                "explicit numerator definition required"
            )

    @property
    def rate(self) -> Fraction | None:
        if self.exposures == 0:
            return None

        return Fraction(
            self.count,
            self.exposures,
        )

    @property
    def reconciliation_required(self) -> bool:
        return (
            self.exposures == 0
            and self.count > 0
        )

    def summary(self) -> str:
        """Return administrative text; perform no external output."""
        if self.exposures == 0:
            value = "undefined"
        else:
            value = str(self.rate)

        return (
            f"numerator={self.numerator.value}; "
            f"count={self.count}; "
            f"exposures={self.exposures}; "
            f"reported_rate={value}; "
            f"reconciliation_required="
            f"{self.reconciliation_required}; "
            "not an estimate of total harm or individual safety"
        )


class RateTests(unittest.TestCase):
    """Synthetic counts are not operational safety evidence."""

    def test_undefined_zero(self):
        result = ReportedRate(
            0,
            0,
            Numerator.REPORTS,
        )

        self.assertIsNone(result.rate)
        self.assertFalse(
            result.reconciliation_required
        )

    def test_reports_without_exposure(self):
        result = ReportedRate(
            2,
            0,
            Numerator.REPORTS,
        )

        self.assertIsNone(result.rate)
        self.assertTrue(
            result.reconciliation_required
        )

    def test_exact_and_unbounded_rate(self):
        self.assertEqual(
            ReportedRate(
                1,
                3,
                Numerator.DISTINCT_REPORTED_EVENTS,
            ).rate,
            Fraction(1, 3),
        )

        self.assertEqual(
            ReportedRate(
                3,
                2,
                Numerator.REPORTS,
            ).rate,
            Fraction(3, 2),
        )

        self.assertEqual(
            ReportedRate(
                0,
                10,
                Numerator.REPORTS,
            ).rate,
            Fraction(0),
        )

    def test_invalid(self):
        calls = (
            lambda: ReportedRate(
                True,
                2,
                Numerator.REPORTS,
            ),
            lambda: ReportedRate(
                -1,
                2,
                Numerator.REPORTS,
            ),
            lambda: ReportedRate(
                1,
                2,
                "reports",
            ),
        )

        for call in calls:
            with self.assertRaises(MetricError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
