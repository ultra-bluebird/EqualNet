# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate statistics for a completed rooted occurrence traversal.

Run directly with Python 3.12+ to execute synthetic tests.

Statistics describe expanded occurrences, not distinct assets.
The root has depth zero.

Structural consistency does not authenticate a traversal or establish
lineage completeness, source-label accuracy, or permitted processing.
"""

from dataclasses import dataclass
import unittest


class StatisticsError(ValueError):
    """Inconsistent or malformed traversal statistics."""


@dataclass(frozen=True, slots=True)
class ExpansionStats:
    occurrences: int
    input_edges: int
    deepest_path: int

    def __post_init__(self):
        for value in (
            self.occurrences,
            self.input_edges,
            self.deepest_path,
        ):
            if type(value) is not int or value < 0:
                raise StatisticsError(
                    "statistics must be nonnegative "
                    "built-in integers"
                )

        if self.occurrences < 1:
            raise StatisticsError(
                "a completed rooted traversal includes its root"
            )

        if self.input_edges != self.occurrences - 1:
            raise StatisticsError(
                "expanded edge count must equal "
                "occurrences minus one"
            )

        if self.occurrences == 1:
            if self.deepest_path != 0:
                raise StatisticsError(
                    "a root-only traversal has depth zero"
                )

        elif not (
            1
            <= self.deepest_path
            <= self.input_edges
        ):
            raise StatisticsError(
                "a nontrivial traversal requires positive depth "
                "no greater than its edge count"
            )


class StatisticsTests(unittest.TestCase):
    """Synthetic statistics do not authenticate audit evidence."""

    def test_reference_shapes(self):
        examples = (
            (1, 0, 0),
            (3, 2, 1),
            (1501, 1500, 1500),
        )

        for values in examples:
            self.assertEqual(
                ExpansionStats(*values).occurrences,
                values[0],
            )

    def test_zero_depth_nontrivial_traversal_rejected(self):
        with self.assertRaises(StatisticsError):
            ExpansionStats(2, 1, 0)

    def test_bounded_statistics_space(self):
        checked = 0

        for occurrences in range(1, 21):
            for depth in range(occurrences + 2):
                valid = (
                    depth == 0
                    if occurrences == 1
                    else 1 <= depth <= occurrences - 1
                )

                if valid:
                    ExpansionStats(
                        occurrences,
                        occurrences - 1,
                        depth,
                    )

                else:
                    with self.assertRaises(StatisticsError):
                        ExpansionStats(
                            occurrences,
                            occurrences - 1,
                            depth,
                        )

                checked += 1

        self.assertEqual(checked, 250)

    def test_invalid_types_and_edges(self):
        invalid_values = (
            (True, 0, 0),
            (0, 0, 0),
            (3, 1, 1),
            (2, 1, 2),
            (1, 0, -1),
        )

        for values in invalid_values:
            with self.assertRaises(StatisticsError):
                ExpansionStats(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
