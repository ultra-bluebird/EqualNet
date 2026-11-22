# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validated aggregate presentation for assurance results.

Run directly with Python 3.12+ to execute synthetic tests.

This module does not assess evidence, authenticate decisions, emit logs,
or authorize deployment.
"""

from dataclasses import dataclass
import unittest


class SummaryError(ValueError):
    """Invalid aggregate assessment metadata."""


@dataclass(frozen=True, slots=True)
class AggregateSummary:
    required_count: int
    supplied_count: int
    blocker_count: int

    def __post_init__(self):
        for value in (
            self.required_count,
            self.supplied_count,
            self.blocker_count,
        ):
            if type(value) is not int or value < 0:
                raise SummaryError(
                    "counts must be nonnegative integers"
                )

        if self.required_count == 0:
            raise SummaryError(
                "at least one obligation is required"
            )

        if self.supplied_count > self.required_count:
            raise SummaryError(
                "supplied count exceeds the reviewed obligation set"
            )

        if (
            self.supplied_count < self.required_count
            and self.blocker_count == 0
        ):
            raise SummaryError(
                "missing records require blockers"
            )

    @property
    def ready(self):
        """Describe these counts; do not authorize any operation."""
        return self.blocker_count == 0

    def render(self):
        """Return fixed labels and validated aggregate values only."""
        return (
            f"Assurance assessment: ready={self.ready} "
            f"required={self.required_count} "
            f"records={self.supplied_count} "
            f"blockers={self.blocker_count}"
        )


class SummaryTests(unittest.TestCase):
    """Synthetic summaries are not operational evidence."""

    def test_complete(self):
        summary = AggregateSummary(10, 10, 0)

        self.assertTrue(summary.ready)
        self.assertEqual(
            summary.render(),
            "Assurance assessment: ready=True "
            "required=10 records=10 blockers=0",
        )

    def test_missing_and_multiple_reasons(self):
        self.assertFalse(
            AggregateSummary(10, 0, 10).ready
        )
        self.assertFalse(
            AggregateSummary(10, 10, 30).ready
        )

    def test_invalid_counts(self):
        invalid_values = (
            (0, 0, 0),
            (10, 11, 0),
            (10, 9, 0),
            (10, 10, -1),
            (True, 1, 0),
            (10, 10.0, 0),
        )

        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(SummaryError):
                    AggregateSummary(*values)

    def test_render_contains_only_fixed_labels_and_counts(self):
        summary = AggregateSummary(10, 9, 1)

        self.assertEqual(
            set(summary.__slots__),
            {
                "required_count",
                "supplied_count",
                "blocker_count",
            },
        )
        self.assertEqual(
            summary.render(),
            "Assurance assessment: ready=False "
            "required=10 records=9 blockers=1",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
