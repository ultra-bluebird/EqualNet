# SPDX-License-Identifier: MIT OR Apache-2.0
"""Attainable finite-cohort proportions under binary missing outcomes.

Run directly with Python 3.12+ to execute synthetic tests.

Inputs must describe one compatible cohort and applicable binary question.
The function does not validate cohort membership or infer responses.

Returned values are mathematical possibilities, not probabilities,
observations, confidence intervals, or publication-approved statistics.
"""

from fractions import Fraction
import unittest


class CompletionError(ValueError):
    """Malformed finite-cohort input."""


class CompletionLimitError(CompletionError):
    """The requested support exceeds the configured output limit."""


def completion_values(
    invited: int,
    answered: int,
    wanted: int,
    *,
    max_points: int = 1000,
) -> tuple[Fraction, ...] | None:
    """Return attainable aggregate proportions, without individual labels.

    None means the cohort denominator is zero.

    The maximum number of returned points is checked before constructing
    the tuple. No missing responses are created or stored.
    """
    for value in (invited, answered, wanted):
        if type(value) is not int or value < 0:
            raise CompletionError(
                "counts must be nonnegative built-in integers"
            )

    if (
        type(max_points) is not int
        or max_points <= 0
    ):
        raise CompletionError(
            "max_points must be a positive built-in integer"
        )

    if not wanted <= answered <= invited:
        raise CompletionError(
            "require wanted <= answered <= invited"
        )

    if invited == 0:
        return None

    missing = invited - answered

    if missing + 1 > max_points:
        raise CompletionLimitError(
            "completion support exceeds the configured point limit"
        )

    return tuple(
        Fraction(
            wanted + positive,
            invited,
        )
        for positive in range(missing + 1)
    )


class CompletionTests(unittest.TestCase):
    """Synthetic arithmetic checks, not member-outcome evidence."""

    def test_support_and_endpoints(self):
        self.assertEqual(
            completion_values(10, 6, 4),
            (
                Fraction(2, 5),
                Fraction(1, 2),
                Fraction(3, 5),
                Fraction(7, 10),
                Fraction(4, 5),
            ),
        )

    def test_scenario_need_not_be_attainable(self):
        support = completion_values(3, 2, 1)

        self.assertEqual(
            support,
            (
                Fraction(1, 3),
                Fraction(2, 3),
            ),
        )
        self.assertNotIn(
            Fraction(1, 2),
            support,
        )

    def test_empty_complete_and_limit(self):
        self.assertIsNone(
            completion_values(0, 0, 0)
        )
        self.assertEqual(
            completion_values(10, 10, 4),
            (Fraction(2, 5),),
        )

        with self.assertRaises(CompletionLimitError):
            completion_values(
                1000,
                0,
                0,
                max_points=1000,
            )

    def test_invalid(self):
        invalid_counts = (
            (True, 0, 0),
            (2, 3, 1),
            (3, 1, 2),
            (-1, 0, 0),
        )

        for values in invalid_counts:
            with self.assertRaises(CompletionError):
                completion_values(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
