# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare reviewed candidate data designs without a composite score.

Run directly with Python 3.12+ to execute synthetic tests.

Exposure dimensions, in order:
    precision, recipients, retention, derivation

Values are caller-supplied review assessments, not measured probabilities.
Lower exposure values are preferable within the same assessment context.
The usefulness measure is a feature-level threshold, not a member score.

This module does not verify permission, evidence, or candidate completeness.
"""

from dataclasses import dataclass
import unittest


class ReviewError(ValueError):
    """Malformed candidate-review input."""


def natural(value):
    return type(value) is int and value >= 0


@dataclass(frozen=True, slots=True)
class Candidate:
    field_count: int
    exposure: tuple[int, int, int, int]
    usefulness: int
    allowed: bool

    def __post_init__(self):
        if (
            not natural(self.field_count)
            or not natural(self.usefulness)
        ):
            raise ReviewError(
                "field count and usefulness must be "
                "nonnegative integers"
            )

        if (
            type(self.exposure) is not tuple
            or len(self.exposure) != 4
        ):
            raise ReviewError(
                "four exposure dimensions required"
            )

        if any(
            not natural(value)
            for value in self.exposure
        ):
            raise ReviewError(
                "exposure dimensions must be "
                "nonnegative integers"
            )

        if type(self.allowed) is not bool:
            raise ReviewError(
                "allowed must be boolean"
            )

    @property
    def objectives(self):
        return (self.field_count,) + self.exposure


def dominates(
    left: Candidate,
    right: Candidate,
) -> bool:
    """Compare validated candidates in the same review context."""
    return (
        all(
            a <= b
            for a, b in zip(
                left.objectives,
                right.objectives,
            )
        )
        and any(
            a < b
            for a, b in zip(
                left.objectives,
                right.objectives,
            )
        )
    )


def frontier(
    candidates: tuple[Candidate, ...],
    minimum_usefulness: int,
) -> tuple[Candidate, ...]:
    """Return nondominated feasible assessment profiles.

    Identical profiles are deduplicated. This function does not preserve
    separate underlying designs with identical assessments; the review
    system must retain those designs and their evidence separately.

    Usefulness is a threshold, not an objective to maximize.
    An empty result means no supplied candidate is feasible.
    """
    if (
        type(candidates) is not tuple
        or any(
            type(candidate) is not Candidate
            for candidate in candidates
        )
    ):
        raise ReviewError(
            "immutable tuple of validated candidates required"
        )

    if not natural(minimum_usefulness):
        raise ReviewError(
            "minimum usefulness must be "
            "a nonnegative integer"
        )

    feasible = tuple(
        dict.fromkeys(
            candidate
            for candidate in candidates
            if (
                candidate.allowed
                and candidate.usefulness
                >= minimum_usefulness
            )
        )
    )

    result = tuple(
        candidate
        for candidate in feasible
        if not any(
            dominates(other, candidate)
            for other in feasible
        )
    )

    return tuple(
        sorted(
            result,
            key=lambda candidate: (
                candidate.objectives,
                candidate.usefulness,
            ),
        )
    )


class FrontierTests(unittest.TestCase):
    """Synthetic assessments are not privacy evidence."""

    def test_tradeoffs_preserved(self):
        precise = Candidate(
            1, (9, 1, 1, 1), 8, True
        )
        coarse = Candidate(
            3, (1, 1, 1, 1), 8, True
        )

        self.assertEqual(
            set(frontier((precise, coarse), 7)),
            {precise, coarse},
        )

    def test_dominated_removed(self):
        better = Candidate(
            1, (1, 1, 1, 1), 8, True
        )
        worse = Candidate(
            2, (2, 2, 2, 2), 9, True
        )

        self.assertEqual(
            frontier((worse, better), 7),
            (better,),
        )

    def test_hard_constraints(self):
        prohibited = Candidate(
            0, (0, 0, 0, 0), 9, False
        )
        insufficient = Candidate(
            0, (0, 0, 0, 0), 2, True
        )

        self.assertEqual(
            frontier(
                (prohibited, insufficient),
                7,
            ),
            (),
        )

    def test_order_and_duplicates(self):
        first = Candidate(
            1, (2, 1, 1, 1), 8, True
        )
        second = Candidate(
            2, (1, 1, 1, 1), 8, True
        )

        self.assertEqual(
            frontier(
                (first, second, first),
                7,
            ),
            frontier(
                (second, first),
                7,
            ),
        )

    def test_invalid(self):
        calls = (
            lambda: Candidate(
                True, (1, 1, 1, 1), 8, True
            ),
            lambda: Candidate(
                1, (1, -1, 1, 1), 8, True
            ),
            lambda: frontier([], 7),
            lambda: frontier((), True),
        )

        for call in calls:
            with self.assertRaises(ReviewError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
