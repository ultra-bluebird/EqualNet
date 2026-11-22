# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure admission calculation for recipient request budgets.

Run directly with Python 3.12+ to execute synthetic tests.

Counts must describe the same request category and window.
ALLOW is a budget result, not authorization to contact anyone.
"""

from dataclasses import dataclass
from enum import Enum
import unittest


class LimitError(ValueError):
    """Malformed budget input."""


class Admission(Enum):
    ALLOW = "allow"
    PER_SENDER_LIMIT = "per_sender_limit"
    RECIPIENT_TOTAL_LIMIT = "recipient_total_limit"


@dataclass(frozen=True, slots=True)
class Budget:
    sender_used: int
    total_used: int
    member_sender_limit: int
    member_total_limit: int
    platform_sender_limit: int
    platform_total_limit: int

    def __post_init__(self):
        values = (
            self.sender_used,
            self.total_used,
            self.member_sender_limit,
            self.member_total_limit,
            self.platform_sender_limit,
            self.platform_total_limit,
        )

        if any(
            type(value) is not int or value < 0
            for value in values
        ):
            raise LimitError(
                "counts and limits must be nonnegative integers"
            )

        if self.sender_used > self.total_used:
            raise LimitError(
                "sender count cannot exceed recipient total"
            )


@dataclass(frozen=True, slots=True)
class Result:
    admission: Admission
    sender_after: int
    total_after: int


def admit(budget: Budget) -> Result:
    """Calculate admission without mutating or storing counts.

    Total-capacity exhaustion takes precedence in the internal result
    when both ceilings are reached. Do not expose this reason directly
    to senders.
    """
    if type(budget) is not Budget:
        raise LimitError("validated budget required")

    sender_limit = min(
        budget.member_sender_limit,
        budget.platform_sender_limit,
    )
    total_limit = min(
        budget.member_total_limit,
        budget.platform_total_limit,
    )

    if budget.total_used >= total_limit:
        status = Admission.RECIPIENT_TOTAL_LIMIT
    elif budget.sender_used >= sender_limit:
        status = Admission.PER_SENDER_LIMIT
    else:
        return Result(
            Admission.ALLOW,
            budget.sender_used + 1,
            budget.total_used + 1,
        )

    return Result(
        status,
        budget.sender_used,
        budget.total_used,
    )


class BudgetTests(unittest.TestCase):
    """Synthetic counts are not operational telemetry."""

    def test_allow_and_increment(self):
        self.assertEqual(
            admit(Budget(0, 1, 2, 3, 4, 5)),
            Result(Admission.ALLOW, 1, 2),
        )

    def test_limits_and_zero(self):
        self.assertEqual(
            admit(Budget(1, 1, 1, 5, 5, 5)).admission,
            Admission.PER_SENDER_LIMIT,
        )
        self.assertEqual(
            admit(Budget(0, 2, 5, 2, 5, 5)).admission,
            Admission.RECIPIENT_TOTAL_LIMIT,
        )
        self.assertEqual(
            admit(Budget(0, 0, 5, 5, 5, 0)).admission,
            Admission.RECIPIENT_TOTAL_LIMIT,
        )

    def test_small_state_space(self):
        for total in range(5):
            for sender in range(total + 1):
                for sender_limit in range(4):
                    for total_limit in range(4):
                        budget = Budget(
                            sender,
                            total,
                            sender_limit,
                            total_limit,
                            2,
                            3,
                        )
                        result = admit(budget)

                        expected = (
                            sender < min(sender_limit, 2)
                            and total < min(total_limit, 3)
                        )

                        self.assertEqual(
                            result.admission is Admission.ALLOW,
                            expected,
                        )

                        if not expected:
                            self.assertEqual(
                                (
                                    result.sender_after,
                                    result.total_after,
                                ),
                                (sender, total),
                            )

    def test_invalid_inputs(self):
        invalid_values = (
            (True, 0, 1, 1, 1, 1),
            (-1, 0, 1, 1, 1, 1),
            (2, 1, 1, 1, 1, 1),
        )

        for values in invalid_values:
            with self.assertRaises(LimitError):
                Budget(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
