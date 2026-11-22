# SPDX-License-Identifier: MIT OR Apache-2.0
"""Member-selected fictional communication practice.

Run directly with Python 3.12+ to execute synthetic tests.

This component provides prompts only. It does not analyze responses,
predict real people, score members, or access reflection histories.

Paused and ended practice produces no prompt. There is no automatic
resume, reminder, publication, or notification operation.
"""

from dataclasses import dataclass, replace
from enum import Enum
import unittest


class PracticeError(ValueError):
    """Malformed practice input."""


class Scenario(Enum):
    AMBIGUITY = "ambiguity"
    REFUSAL = "refusal"
    MEMBER_BOUNDARY = "member_boundary"


class Status(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class Practice:
    scenario: Scenario
    status: Status = Status.ACTIVE

    def __post_init__(self):
        if (
            type(self.scenario) is not Scenario
            or type(self.status) is not Status
        ):
            raise PracticeError(
                "explicit scenario and status required"
            )


def pause(practice: Practice) -> Practice:
    if type(practice) is not Practice:
        raise PracticeError(
            "validated practice required"
        )

    if practice.status is Status.ENDED:
        return practice

    return replace(
        practice,
        status=Status.PAUSED,
    )


def end(practice: Practice) -> Practice:
    if type(practice) is not Practice:
        raise PracticeError(
            "validated practice required"
        )

    return replace(
        practice,
        status=Status.ENDED,
    )


def prompt(practice: Practice) -> str:
    if type(practice) is not Practice:
        raise PracticeError(
            "validated practice required"
        )

    if practice.status is not Status.ACTIVE:
        return ""

    prefix = (
        "Fictional practice, not a prediction about a real person. "
        "You may skip or stop.\n"
    )

    if practice.scenario is Scenario.AMBIGUITY:
        return prefix + (
            "They say: 'I am not sure about meeting.' "
            "Practice leaving the decision open without "
            "treating uncertainty as permission."
        )

    if practice.scenario is Scenario.REFUSAL:
        return prefix + (
            "They say: 'No, I do not want a date.' "
            "Practice acknowledging the refusal without "
            "asking them to reconsider. "
            "Ending the conversation is an available response."
        )

    return prefix + (
        "You want no further contact. "
        "You may practice a short boundary statement or "
        "stop without drafting a message. "
        "No explanation is required."
    )


class PracticeTests(unittest.TestCase):
    """Synthetic checks are not evidence of learning effectiveness."""

    def test_each_scenario_is_labeled(self):
        for scenario in Scenario:
            self.assertIn(
                "not a prediction",
                prompt(Practice(scenario)),
            )

    def test_pause_and_end_are_silent(self):
        for scenario in Scenario:
            active = Practice(scenario)

            self.assertEqual(
                prompt(pause(active)),
                "",
            )
            self.assertEqual(
                prompt(end(active)),
                "",
            )
            self.assertEqual(
                pause(end(active)),
                end(active),
            )
            self.assertEqual(
                end(end(active)),
                end(active),
            )

    def test_boundary_requires_no_explanation(self):
        self.assertIn(
            "No explanation is required",
            prompt(
                Practice(
                    Scenario.MEMBER_BOUNDARY
                )
            ),
        )

        self.assertIn(
            "without asking them to reconsider",
            prompt(
                Practice(
                    Scenario.REFUSAL
                )
            ),
        )

    def test_invalid(self):
        calls = (
            lambda: Practice("refusal"),
            lambda: prompt(None),
            lambda: pause(None),
            lambda: end(None),
        )

        for call in calls:
            with self.assertRaises(PracticeError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
