# SPDX-License-Identifier: MIT OR Apache-2.0
"""Separate mandatory outcomes from benefit observations.

Run directly with Python 3.12+ to execute synthetic tests.

Inputs are supplied review assertions, not verified evidence.
This component does not calculate thresholds or statistical tests.

A satisfied outcome gate is not deployment authorization, claims
approval, integration permission, or proof of complete outcome coverage.
"""

from dataclasses import dataclass
from enum import Enum
import unittest


class OutcomeError(ValueError):
    """Malformed outcome-plan input."""


class Role(Enum):
    SAFEGUARD = "safeguard"
    HARM_GUARDRAIL = "harm_guardrail"
    REQUIRED_BENEFIT = "required_benefit"
    CONFIRMATORY_BENEFIT = "confirmatory_benefit"
    EXPLORATORY = "exploratory"


class Status(Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class Outcome:
    name: str
    role: Role
    status: Status
    current: bool

    def __post_init__(self):
        if (
            type(self.name) is not str
            or not self.name.strip()
        ):
            raise OutcomeError(
                "outcome name required"
            )

        if (
            type(self.role) is not Role
            or type(self.status) is not Status
        ):
            raise OutcomeError(
                "explicit outcome role and status required"
            )

        if type(self.current) is not bool:
            raise OutcomeError(
                "current must be boolean"
            )


@dataclass(frozen=True, slots=True)
class GateResult:
    blockers: tuple[str, ...]
    benefit_results: tuple[
        tuple[str, Status, bool],
        ...,
    ]

    @property
    def mandatory_outcomes_satisfied(self):
        return not self.blockers


def evaluate(
    outcomes: tuple[Outcome, ...],
) -> GateResult:
    """Evaluate the supplied plan without combining outcome scores."""
    if (
        type(outcomes) is not tuple
        or any(
            type(value) is not Outcome
            for value in outcomes
        )
    ):
        raise OutcomeError(
            "immutable validated outcome tuple required"
        )

    names = tuple(
        value.name
        for value in outcomes
    )

    if len(set(names)) != len(names):
        raise OutcomeError(
            "duplicate outcome names"
        )

    mandatory = {
        Role.SAFEGUARD,
        Role.HARM_GUARDRAIL,
        Role.REQUIRED_BENEFIT,
    }
    blockers = []

    for role in (
        Role.SAFEGUARD,
        Role.HARM_GUARDRAIL,
    ):
        if not any(
            value.role is role
            for value in outcomes
        ):
            blockers.append(
                "missing required outcome class: "
                f"{role.value}"
            )

    for value in sorted(
        outcomes,
        key=lambda item: item.name,
    ):
        if value.role in mandatory:
            if value.status is not Status.PASS:
                blockers.append(
                    f"{value.name}: {value.status.value}"
                )

            if not value.current:
                blockers.append(
                    f"{value.name}: evidence not current"
                )

    benefits = tuple(
        (
            value.name,
            value.status,
            value.current,
        )
        for value in sorted(
            outcomes,
            key=lambda item: item.name,
        )
        if value.role in {
            Role.REQUIRED_BENEFIT,
            Role.CONFIRMATORY_BENEFIT,
            Role.EXPLORATORY,
        }
    )

    return GateResult(
        blockers=tuple(blockers),
        benefit_results=benefits,
    )


class OutcomeTests(unittest.TestCase):
    """Synthetic review assertions are not release evidence."""

    def setUp(self):
        self.base = (
            Outcome(
                "permission enforcement",
                Role.SAFEGUARD,
                Status.PASS,
                True,
            ),
            Outcome(
                "reported pressure",
                Role.HARM_GUARDRAIL,
                Status.PASS,
                True,
            ),
        )

    def test_benefit_cannot_offset_harm(self):
        values = (
            self.base[0],
            Outcome(
                "reported pressure",
                Role.HARM_GUARDRAIL,
                Status.FAIL,
                True,
            ),
            Outcome(
                "clarity",
                Role.CONFIRMATORY_BENEFIT,
                Status.PASS,
                True,
            ),
        )

        self.assertFalse(
            evaluate(values).mandatory_outcomes_satisfied
        )

    def test_unknown_and_stale_block(self):
        for status in (
            Status.FAIL,
            Status.INCONCLUSIVE,
            Status.NOT_ASSESSED,
        ):
            values = (
                self.base[0],
                Outcome(
                    "reported pressure",
                    Role.HARM_GUARDRAIL,
                    status,
                    True,
                ),
            )

            self.assertFalse(
                evaluate(values).mandatory_outcomes_satisfied
            )

        self.assertFalse(
            evaluate(
                (
                    self.base[0],
                    Outcome(
                        "reported pressure",
                        Role.HARM_GUARDRAIL,
                        Status.PASS,
                        False,
                    ),
                )
            ).mandatory_outcomes_satisfied
        )

    def test_exploration_is_separate(self):
        result = evaluate(
            self.base
            + (
                Outcome(
                    "optional observation",
                    Role.EXPLORATORY,
                    Status.INCONCLUSIVE,
                    True,
                ),
            )
        )

        self.assertTrue(
            result.mandatory_outcomes_satisfied
        )
        self.assertEqual(
            result.benefit_results[0][1],
            Status.INCONCLUSIVE,
        )

    def test_missing_and_duplicates(self):
        self.assertFalse(
            evaluate(()).mandatory_outcomes_satisfied
        )

        with self.assertRaises(OutcomeError):
            evaluate(
                self.base + self.base[:1]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
