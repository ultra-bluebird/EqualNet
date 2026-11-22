# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure comparison of explicit interaction-format inputs.

Run directly with Python 3.12+ to execute synthetic tests.

The integration must authorize comparison of the supplied inputs.
Disclosure of the result requires separate authorization.

A common format is not permission to initiate that interaction.
An empty intersection is not a rejection or a notification request.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
import unittest


class ChoiceError(ValueError):
    """Malformed format-comparison input."""


class Format(Enum):
    TEXT = "text"
    REMOTE_ACTIVITY = "remote_activity"
    PUBLIC_MEETING = "public_meeting"


@dataclass(frozen=True, slots=True)
class ComparisonInput:
    formats: frozenset[Format]

    def __post_init__(self):
        if (
            type(self.formats) is not frozenset
            or any(
                type(value) is not Format
                for value in self.formats
            )
        ):
            raise ChoiceError(
                "immutable explicit format choices required"
            )


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    common: frozenset[Format]

    def __post_init__(self):
        if (
            type(self.common) is not frozenset
            or any(
                type(value) is not Format
                for value in self.common
            )
        ):
            raise ChoiceError(
                "immutable explicit common formats required"
            )

    @property
    def authorizes_interaction(self):
        return False

    @property
    def requests_notification(self):
        return False


def compare(
    left: ComparisonInput,
    right: ComparisonInput,
) -> ComparisonResult:
    """Compute options without publishing or acting on them."""
    if (
        type(left) is not ComparisonInput
        or type(right) is not ComparisonInput
    ):
        raise ChoiceError(
            "validated comparison inputs required"
        )

    return ComparisonResult(
        left.formats & right.formats
    )


class ChoiceTests(unittest.TestCase):
    """Synthetic choices are not member-consent evidence."""

    def test_every_subset_pair(self):
        values = tuple(Format)

        subsets = tuple(
            frozenset(group)
            for size in range(len(values) + 1)
            for group in combinations(values, size)
        )

        checked = 0

        for left in subsets:
            for right in subsets:
                result = compare(
                    ComparisonInput(left),
                    ComparisonInput(right),
                )

                self.assertEqual(
                    result.common,
                    left & right,
                )
                self.assertLessEqual(
                    result.common,
                    left,
                )
                self.assertLessEqual(
                    result.common,
                    right,
                )
                self.assertFalse(
                    result.authorizes_interaction
                )
                self.assertFalse(
                    result.requests_notification
                )

                checked += 1

        self.assertEqual(checked, 64)

    def test_no_automatic_upgrade(self):
        result = compare(
            ComparisonInput(
                frozenset({Format.TEXT})
            ),
            ComparisonInput(
                frozenset({Format.PUBLIC_MEETING})
            ),
        )

        self.assertEqual(
            result.common,
            frozenset(),
        )

    def test_invalid(self):
        calls = (
            lambda: ComparisonInput(
                {Format.TEXT}
            ),
            lambda: ComparisonInput(
                frozenset({"text"})
            ),
            lambda: compare(
                None,
                ComparisonInput(frozenset()),
            ),
        )

        for call in calls:
            with self.assertRaises(ChoiceError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
