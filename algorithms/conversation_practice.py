# SPDX-License-Identifier: MIT OR Apache-2.0
"""Member-selected fictional communication practice for Python 3.12+.

CLI examples:
    python algorithms/conversation_practice.py --self-test
    python algorithms/conversation_practice.py --list-scenarios
    python algorithms/conversation_practice.py --scenario refusal
    python algorithms/conversation_practice.py --scenario refusal --pause

The core provides prompts and immutable local state transitions only.
It does not analyze responses, predict people, score members, access
reflection histories, authorize contact, or send anything.

Paused and ended practice produces no prompt. Selecting another scenario
does not resume paused practice. Ended practice cannot be changed through
the scenario-selection function.

There is no automatic resume, reminder, publication, or notification.

Optional --log-summary writes only local practice status to stderr.
It does not configure a persistent logger. The invoking environment may
capture terminal output, so access and retention need separate review.

CLI exit statuses:
    0: help, catalog, prompt processing, or successful tests
    1: failed tests
    2: invalid arguments

Construction validates structure, not identity, consent, or authority.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, replace
from enum import Enum
from io import StringIO
import platform
import sys
from types import MappingProxyType
import unittest


__all__ = [
    "PracticeError",
    "ValidationError",
    "TransitionError",
    "Scenario",
    "Status",
    "Practice",
    "pause",
    "end",
    "select_scenario",
    "prompt",
    "main",
]


class PracticeError(ValueError):
    """Base practice contract error."""


class ValidationError(PracticeError):
    """Malformed input."""


class TransitionError(PracticeError):
    """An ended practice cannot be changed."""


class Scenario(Enum):
    AMBIGUITY = "ambiguity"
    REFUSAL = "refusal"
    MEMBER_BOUNDARY = "member_boundary"


class Status(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


_PREFIX = (
    "Fictional practice, not a prediction about a real person. "
    "You may skip or stop.\n"
)

_TEXT = MappingProxyType({
    Scenario.AMBIGUITY: (
        "They say: 'I am not sure about meeting.' "
        "Practice leaving the decision open without "
        "treating uncertainty as permission."
    ),
    Scenario.REFUSAL: (
        "They say: 'No, I do not want a date.' "
        "Practice acknowledging the refusal without "
        "asking them to reconsider. "
        "Ending the conversation is an available response."
    ),
    Scenario.MEMBER_BOUNDARY: (
        "You want no further contact. "
        "You may practice a short boundary statement or "
        "stop without drafting a message. "
        "No explanation is required."
    ),
})


@dataclass(frozen=True, slots=True)
class Practice:
    scenario: Scenario
    status: Status = Status.ACTIVE

    def __post_init__(self) -> None:
        if (
            type(self.scenario) is not Scenario
            or type(self.status) is not Status
        ):
            raise ValidationError(
                "explicit scenario and status required"
            )


def _require(practice: object) -> None:
    if type(practice) is not Practice:
        raise ValidationError(
            "validated practice required"
        )


def pause(practice: Practice) -> Practice:
    """Pause active practice without changing its scenario.

    Already paused or ended practice remains unchanged.
    """
    _require(practice)

    if practice.status is not Status.ACTIVE:
        return practice

    return replace(
        practice,
        status=Status.PAUSED,
    )


def end(practice: Practice) -> Practice:
    """End local practice without external effects."""
    _require(practice)

    if practice.status is Status.ENDED:
        return practice

    return replace(
        practice,
        status=Status.ENDED,
    )


def select_scenario(
    practice: Practice,
    scenario: Scenario,
) -> Practice:
    """Explicitly change the scenario without resuming paused practice.

    Ended practice cannot be changed. A separately requested practice
    requires a new state; this function never restarts an ended one.
    """
    _require(practice)

    if type(scenario) is not Scenario:
        raise ValidationError(
            "explicit scenario required"
        )

    if practice.status is Status.ENDED:
        raise TransitionError(
            "start a separately requested practice instead"
        )

    if scenario is practice.scenario:
        return practice

    return replace(
        practice,
        scenario=scenario,
    )


def prompt(practice: Practice) -> str:
    """Return a fictional prompt only for active practice."""
    _require(practice)

    if practice.status is not Status.ACTIVE:
        return ""

    return _PREFIX + _TEXT[practice.scenario]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Local fictional practice; "
            "no analysis, sending, or persistence."
        )
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--self-test",
        action="store_true",
    )
    mode.add_argument(
        "--list-scenarios",
        action="store_true",
    )
    mode.add_argument(
        "--scenario",
        choices=tuple(
            item.value
            for item in Scenario
        ),
    )

    state = parser.add_mutually_exclusive_group()

    state.add_argument(
        "--pause",
        action="store_true",
    )
    state.add_argument(
        "--end",
        action="store_true",
    )

    parser.add_argument(
        "--log-summary",
        action="store_true",
        help=(
            "write only practice status to stderr; "
            "no persistent logger"
        ),
    )

    args = parser.parse_args(argv)

    if args.scenario is None and (
        args.pause
        or args.end
        or args.log_summary
    ):
        parser.error(
            "--pause, --end, and --log-summary "
            "require --scenario"
        )

    if args.self_test:
        print(
            f"Python {platform.python_version()}; "
            "runner=unittest",
            flush=True,
        )

        suite = (
            unittest.defaultTestLoader
            .loadTestsFromTestCase(PracticeTests)
        )

        result = unittest.TextTestRunner(
            verbosity=2
        ).run(suite)

        return 0 if result.wasSuccessful() else 1

    if args.list_scenarios:
        print(
            "\n".join(
                item.value
                for item in Scenario
            )
        )
        return 0

    if args.scenario is None:
        parser.print_help()
        return 0

    practice = Practice(
        Scenario(args.scenario)
    )

    if args.pause:
        practice = pause(practice)
    elif args.end:
        practice = end(practice)

    text = prompt(practice)

    if text:
        print(text)

    if args.log_summary:
        print(
            f"practice_status={practice.status.value}",
            file=sys.stderr,
        )

    return 0


class PracticeTests(unittest.TestCase):
    """Synthetic checks, not evidence of learning effectiveness."""

    def test_catalog_and_active_prompts(self):
        self.assertEqual(
            set(_TEXT),
            set(Scenario),
        )

        for scenario in Scenario:
            text = prompt(Practice(scenario))

            self.assertTrue(
                text.startswith(
                    "Fictional practice, "
                    "not a prediction about a real person."
                )
            )
            self.assertIn(
                "You may skip or stop.",
                text,
            )

    def test_all_scenario_status_pairs(self):
        checked = 0

        for scenario in Scenario:
            for status in Status:
                practice = Practice(
                    scenario,
                    status,
                )

                self.assertEqual(
                    bool(prompt(practice)),
                    status is Status.ACTIVE,
                )
                self.assertEqual(
                    pause(pause(practice)),
                    pause(practice),
                )
                self.assertEqual(
                    end(end(practice)),
                    end(practice),
                )
                self.assertEqual(
                    pause(end(practice)),
                    end(practice),
                )

                checked += 1

        self.assertEqual(checked, 9)

    def test_scenario_change_does_not_resume(self):
        practice = Practice(
            Scenario.AMBIGUITY,
            Status.PAUSED,
        )

        changed = select_scenario(
            practice,
            Scenario.REFUSAL,
        )

        self.assertEqual(
            changed.status,
            Status.PAUSED,
        )
        self.assertEqual(
            prompt(changed),
            "",
        )
        self.assertEqual(
            practice.scenario,
            Scenario.AMBIGUITY,
        )

        with self.assertRaises(TransitionError):
            select_scenario(
                end(practice),
                Scenario.REFUSAL,
            )

    def test_boundary_and_refusal_wording(self):
        self.assertIn(
            "No explanation is required.",
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

    def test_invalid_inputs(self):
        calls = (
            lambda: Practice("refusal"),
            lambda: Practice(
                Scenario.REFUSAL,
                "active",
            ),
            lambda: prompt(None),
            lambda: pause(None),
            lambda: end(None),
            lambda: select_scenario(
                Practice(Scenario.REFUSAL),
                "ambiguity",
            ),
        )

        for call in calls:
            with self.assertRaises(ValidationError):
                call()

    def test_immutability(self):
        from dataclasses import FrozenInstanceError

        practice = Practice(
            Scenario.REFUSAL
        )

        with self.assertRaises(FrozenInstanceError):
            practice.status = Status.ACTIVE

        with self.assertRaises(TypeError):
            _TEXT[Scenario.REFUSAL] = "changed"

    def test_cli_output_and_status_summary(self):
        out = StringIO()
        err = StringIO()

        with redirect_stdout(out), redirect_stderr(err):
            result = main([
                "--scenario",
                "refusal",
                "--pause",
                "--log-summary",
            ])

        self.assertEqual(result, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(
            err.getvalue(),
            "practice_status=paused\n",
        )

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(
                main([
                    "--scenario",
                    "refusal",
                ]),
                0,
            )

        self.assertIn(
            "No, I do not want a date.",
            output.getvalue(),
        )

    def test_cli_invalid_combinations(self):
        cases = (
            ["--pause"],
            [
                "--self-test",
                "--log-summary",
            ],
            [
                "--scenario",
                "refusal",
                "--pause",
                "--end",
            ],
            [
                "--scenario",
                "unknown",
            ],
        )

        for argv in cases:
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)

            self.assertEqual(
                raised.exception.code,
                2,
            )

    def test_cli_help_and_catalog(self):
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(
                main([]),
                0,
            )

        self.assertIn(
            "usage:",
            output.getvalue(),
        )

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(
                main(["--list-scenarios"]),
                0,
            )

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                item.value
                for item in Scenario
            ],
        )


if __name__ == "__main__":
    raise SystemExit(main())
