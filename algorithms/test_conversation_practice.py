# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent conversation-practice regression expectations.

Run from the repository root:

    python -m unittest algorithms.test_conversation_practice -v

These tests require algorithms/conversation_practice.py.

They establish component behavior only. They do not establish durable
session integrity, learning effectiveness, accessibility, or consent.
"""

from itertools import product
import unittest

from algorithms.conversation_practice import (
    Practice,
    Scenario,
    Status,
    TransitionError,
    end,
    pause,
    prompt,
    select_scenario,
)


EXPECTED_PROMPTS = (
    (
        Scenario.AMBIGUITY,
        "Fictional practice, not a prediction about a real person. "
        "You may skip or stop.\n"
        "They say: 'I am not sure about meeting.' "
        "Practice leaving the decision open without "
        "treating uncertainty as permission.",
    ),
    (
        Scenario.REFUSAL,
        "Fictional practice, not a prediction about a real person. "
        "You may skip or stop.\n"
        "They say: 'No, I do not want a date.' "
        "Practice acknowledging the refusal without "
        "asking them to reconsider. "
        "Ending the conversation is an available response.",
    ),
    (
        Scenario.MEMBER_BOUNDARY,
        "Fictional practice, not a prediction about a real person. "
        "You may skip or stop.\n"
        "You want no further contact. "
        "You may practice a short boundary statement or "
        "stop without drafting a message. "
        "No explanation is required.",
    ),
)


class PracticeConformanceTests(unittest.TestCase):
    def test_exact_reviewed_prompt_wording(self):
        self.assertEqual(
            {scenario for scenario, _ in EXPECTED_PROMPTS},
            set(Scenario),
        )

        for scenario, expected in EXPECTED_PROMPTS:
            with self.subTest(scenario=scenario):
                self.assertEqual(
                    prompt(Practice(scenario)),
                    expected,
                )

    def test_all_nonactive_prompts_are_empty(self):
        for scenario in Scenario:
            for status in (
                Status.PAUSED,
                Status.ENDED,
            ):
                with self.subTest(
                    scenario=scenario,
                    status=status,
                ):
                    self.assertEqual(
                        prompt(
                            Practice(
                                scenario=scenario,
                                status=status,
                            )
                        ),
                        "",
                    )

    def test_bounded_transition_sequences(self):
        operations = (
            "pause",
            "end",
            Scenario.AMBIGUITY,
            Scenario.REFUSAL,
            Scenario.MEMBER_BOUNDARY,
        )

        checked = 0

        for initial_scenario in Scenario:
            for initial_status in Status:
                for sequence in product(
                    operations,
                    repeat=4,
                ):
                    current = Practice(
                        initial_scenario,
                        initial_status,
                    )
                    expected_scenario = initial_scenario
                    expected_status = initial_status

                    for operation in sequence:
                        before = current

                        if operation == "pause":
                            current = pause(current)

                            if expected_status is Status.ACTIVE:
                                expected_status = Status.PAUSED

                        elif operation == "end":
                            current = end(current)
                            expected_status = Status.ENDED

                        elif expected_status is Status.ENDED:
                            with self.assertRaises(TransitionError):
                                select_scenario(
                                    current,
                                    operation,
                                )

                        else:
                            current = select_scenario(
                                current,
                                operation,
                            )
                            expected_scenario = operation

                        self.assertEqual(
                            current,
                            Practice(
                                expected_scenario,
                                expected_status,
                            ),
                        )

                        if before.status is Status.ENDED:
                            self.assertEqual(
                                current,
                                before,
                            )

                        self.assertEqual(
                            bool(prompt(current)),
                            expected_status is Status.ACTIVE,
                        )

                    checked += 1

        self.assertEqual(checked, 5625)

    def test_scenario_switch_preserves_paused_status(self):
        for original in Scenario:
            for selected in Scenario:
                practice = Practice(
                    original,
                    Status.PAUSED,
                )

                changed = select_scenario(
                    practice,
                    selected,
                )

                self.assertEqual(
                    changed,
                    Practice(
                        selected,
                        Status.PAUSED,
                    ),
                )
                self.assertEqual(
                    practice,
                    Practice(
                        original,
                        Status.PAUSED,
                    ),
                )
                self.assertEqual(
                    prompt(changed),
                    "",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
