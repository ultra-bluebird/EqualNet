# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exact descriptive metrics for a supplied pair-linkage experiment.

Run directly with Python 3.12+ to execute synthetic tests.

Counts must come from one prespecified attack, decision threshold,
observer model, configuration, and evaluation population.

No credentials, presentation records, or member data are processed.
Metrics are not confidence intervals or cryptographic security bounds.
"""

from dataclasses import dataclass
from fractions import Fraction
import unittest


class LinkabilityError(ValueError):
    """Malformed linkage-experiment counts."""


@dataclass(frozen=True, slots=True)
class LinkageCounts:
    linked_same: int
    missed_same: int
    linked_different: int
    unlinked_different: int

    def __post_init__(self):
        for value in (
            self.linked_same,
            self.missed_same,
            self.linked_different,
            self.unlinked_different,
        ):
            if type(value) is not int or value < 0:
                raise LinkabilityError(
                    "counts must be nonnegative built-in integers"
                )

    @property
    def same_pairs(self):
        return self.linked_same + self.missed_same

    @property
    def different_pairs(self):
        return (
            self.linked_different
            + self.unlinked_different
        )

    @property
    def true_link_rate(self):
        if not self.same_pairs:
            return None

        return Fraction(
            self.linked_same,
            self.same_pairs,
        )

    @property
    def false_link_rate(self):
        if not self.different_pairs:
            return None

        return Fraction(
            self.linked_different,
            self.different_pairs,
        )

    @property
    def link_precision(self):
        predicted = (
            self.linked_same
            + self.linked_different
        )

        if not predicted:
            return None

        return Fraction(
            self.linked_same,
            predicted,
        )

    @property
    def distinguishing_gap(self):
        if (
            not self.same_pairs
            or not self.different_pairs
        ):
            return None

        return abs(
            self.true_link_rate
            - self.false_link_rate
        )


class LinkageTests(unittest.TestCase):
    """Synthetic confusion tables are not credential-security evidence."""

    def test_perfect_linkage(self):
        result = LinkageCounts(
            10, 0, 0, 10
        )

        self.assertEqual(
            result.distinguishing_gap,
            Fraction(1),
        )
        self.assertEqual(
            result.link_precision,
            Fraction(1),
        )

    def test_uninformative_fixed_outputs(self):
        self.assertEqual(
            LinkageCounts(
                0, 10, 0, 10
            ).distinguishing_gap,
            Fraction(0),
        )
        self.assertEqual(
            LinkageCounts(
                10, 0, 10, 0
            ).distinguishing_gap,
            Fraction(0),
        )
        self.assertIsNone(
            LinkageCounts(
                0, 10, 0, 10
            ).link_precision
        )

    def test_inverted_and_missing_classes(self):
        self.assertEqual(
            LinkageCounts(
                0, 10, 10, 0
            ).distinguishing_gap,
            Fraction(1),
        )
        self.assertIsNone(
            LinkageCounts(
                0, 0, 0, 10
            ).distinguishing_gap
        )
        self.assertIsNone(
            LinkageCounts(
                0, 0, 0, 0
            ).true_link_rate
        )

    def test_invalid(self):
        invalid_counts = (
            (True, 0, 0, 0),
            (-1, 0, 0, 0),
            (1.0, 0, 0, 0),
        )

        for values in invalid_counts:
            with self.assertRaises(LinkabilityError):
                LinkageCounts(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
