# SPDX-License-Identifier: MIT OR Apache-2.0
"""Aggregate wantedness reporting with explicit missing-outcome bounds.

Run directly with Python 3.12+ to execute synthetic tests.

The binary outcome must be defined for every invitation unit in the
supplied cohort. Invitations here are survey invitations, not social
contact requests.

Bounds describe missing-outcome uncertainty within the supplied cohort.
They are not confidence intervals or population-generalization claims.

No individual outcomes are inferred or written.
"""

from dataclasses import dataclass
from fractions import Fraction
import unittest


class MeasurementError(ValueError):
    """Malformed aggregate measurement input."""


@dataclass(frozen=True, slots=True)
class Wantedness:
    invited: int
    submitted: int
    answered: int
    wanted: int

    def __post_init__(self):
        values = (
            self.invited,
            self.submitted,
            self.answered,
            self.wanted,
        )

        if any(
            type(value) is not int or value < 0
            for value in values
        ):
            raise MeasurementError(
                "counts must be nonnegative built-in integers"
            )

        if not (
            self.wanted
            <= self.answered
            <= self.submitted
            <= self.invited
        ):
            raise MeasurementError(
                "counts must satisfy "
                "wanted <= answered <= submitted <= invited"
            )

    @property
    def respondent_fraction(self):
        if not self.answered:
            return None

        return Fraction(
            self.wanted,
            self.answered,
        )

    @property
    def item_response_fraction(self):
        if not self.invited:
            return None

        return Fraction(
            self.answered,
            self.invited,
        )

    @property
    def survey_response_fraction(self):
        if not self.invited:
            return None

        return Fraction(
            self.submitted,
            self.invited,
        )

    @property
    def missing_item_count(self):
        return self.submitted - self.answered

    @property
    def no_submission_count(self):
        return self.invited - self.submitted

    @property
    def bounds(self):
        if not self.invited:
            return None

        missing = self.invited - self.answered

        return (
            Fraction(
                self.wanted,
                self.invited,
            ),
            Fraction(
                self.wanted + missing,
                self.invited,
            ),
        )

    def sensitivity(
        self,
        missing_wanted_fraction: Fraction,
    ):
        """Return a scenario value, not inferred individual responses."""
        if (
            type(missing_wanted_fraction) is not Fraction
            or not 0 <= missing_wanted_fraction <= 1
        ):
            raise MeasurementError(
                "scenario fraction must be a Fraction "
                "between zero and one"
            )

        if not self.invited:
            return None

        missing = self.invited - self.answered

        return (
            self.wanted
            + missing_wanted_fraction * missing
        ) / self.invited


class WantednessTests(unittest.TestCase):
    """Synthetic counts are not evidence of member benefit."""

    def test_partial_response(self):
        result = Wantedness(10, 7, 6, 4)

        self.assertEqual(
            result.respondent_fraction,
            Fraction(2, 3),
        )
        self.assertEqual(
            result.item_response_fraction,
            Fraction(3, 5),
        )
        self.assertEqual(
            result.survey_response_fraction,
            Fraction(7, 10),
        )
        self.assertEqual(
            result.bounds,
            (Fraction(2, 5), Fraction(4, 5)),
        )
        self.assertEqual(
            (
                result.missing_item_count,
                result.no_submission_count,
            ),
            (1, 3),
        )

    def test_empty_and_no_responses(self):
        self.assertIsNone(
            Wantedness(0, 0, 0, 0).bounds
        )

        result = Wantedness(10, 0, 0, 0)

        self.assertIsNone(
            result.respondent_fraction
        )
        self.assertEqual(
            result.bounds,
            (Fraction(0), Fraction(1)),
        )

    def test_sensitivity_endpoints(self):
        result = Wantedness(10, 7, 6, 4)

        self.assertEqual(
            result.sensitivity(Fraction(0)),
            result.bounds[0],
        )
        self.assertEqual(
            result.sensitivity(Fraction(1)),
            result.bounds[1],
        )
        self.assertEqual(
            result.sensitivity(Fraction(1, 2)),
            Fraction(3, 5),
        )

    def test_complete_responses(self):
        result = Wantedness(10, 10, 10, 4)

        self.assertEqual(
            result.bounds,
            (Fraction(2, 5), Fraction(2, 5)),
        )

    def test_invalid(self):
        invalid_counts = (
            (True, 0, 0, 0),
            (1, 2, 1, 1),
            (5, 4, 5, 3),
            (5, 4, 3, 4),
        )

        for values in invalid_counts:
            with self.assertRaises(MeasurementError):
                Wantedness(*values)

        with self.assertRaises(MeasurementError):
            Wantedness(
                1, 0, 0, 0
            ).sensitivity(0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
