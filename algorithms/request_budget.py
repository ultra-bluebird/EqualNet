# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure request-budget evaluation with an administrative CLI.

Python: 3.12+

Examples:
    python algorithms/request_budget.py --self-test
    python algorithms/request_budget.py --budget 0 1 2 3 4 5
    python algorithms/request_budget.py --budget 0 0 5 5 5 5 --requests 2

Budget arguments, in order:
    sender_used
    total_used
    member_sender_limit
    member_total_limit
    platform_sender_limit
    platform_total_limit

All counts must describe the same request category and window.

The evaluator does not reserve capacity, store counts, send requests,
authenticate callers, or authorize contact. Internal reasons and capacity
must not be exposed through a sender-facing interface.

CLI exit codes:
    0: admission allowed, tests passed, or help displayed
    1: admission denied or tests failed
    2: invalid CLI input

Optional CLI logging emits only the admission boolean. It does not
establish privacy-safe logging destinations, access, or retention.
"""

from __future__ import annotations

import argparse
import logging
import sys
import unittest
from dataclasses import dataclass, fields, replace
from enum import Enum
from itertools import product


class LimitError(ValueError):
    """Invalid budget or request quantity."""


def nonnegative(value: object, label: str) -> None:
    """Reject negative values, booleans, and non-integer values."""
    if type(value) is not int or value < 0:
        raise LimitError(
            f"{label} must be a nonnegative integer"
        )


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

    def __post_init__(self) -> None:
        for field in fields(self):
            nonnegative(
                getattr(self, field.name),
                field.name,
            )

        if self.sender_used > self.total_used:
            raise LimitError(
                "sender count cannot exceed recipient total"
            )

    @property
    def sender_limit(self) -> int:
        """Return the stricter member/platform sender ceiling."""
        return min(
            self.member_sender_limit,
            self.platform_sender_limit,
        )

    @property
    def total_limit(self) -> int:
        """Return the stricter member/platform recipient ceiling."""
        return min(
            self.member_total_limit,
            self.platform_total_limit,
        )

    @property
    def capacity(self) -> int:
        """Return additional capacity for this sender in this snapshot."""
        return max(
            0,
            min(
                self.sender_limit - self.sender_used,
                self.total_limit - self.total_used,
            ),
        )


@dataclass(frozen=True, slots=True)
class Result:
    admission: Admission
    sender_after: int
    total_after: int

    def __post_init__(self) -> None:
        if type(self.admission) is not Admission:
            raise LimitError(
                "admission must be Admission"
            )

        nonnegative(
            self.sender_after,
            "sender_after",
        )
        nonnegative(
            self.total_after,
            "total_after",
        )

        if self.sender_after > self.total_after:
            raise LimitError(
                "sender count cannot exceed recipient total"
            )

    @property
    def allowed(self) -> bool:
        """Describe this budget result, not permission to send."""
        return self.admission is Admission.ALLOW


def admit(
    budget: Budget,
    *,
    requests: int = 1,
) -> Result:
    """Evaluate one request or an all-or-nothing bundle; perform no I/O.

    Inputs must cover the same category and window. This calculation does
    not reserve capacity or authorize contact.

    On denial, counts remain unchanged. Total-capacity exhaustion takes
    precedence when both ceilings would be exceeded.

    Internal denial reasons and capacities must not be exposed to senders.
    """
    if type(budget) is not Budget:
        raise LimitError(
            "validated budget required"
        )

    nonnegative(
        requests,
        "requests",
    )

    if requests == 0:
        raise LimitError(
            "requests must be positive"
        )

    if budget.total_used + requests > budget.total_limit:
        status = Admission.RECIPIENT_TOTAL_LIMIT

    elif budget.sender_used + requests > budget.sender_limit:
        status = Admission.PER_SENDER_LIMIT

    else:
        return Result(
            Admission.ALLOW,
            budget.sender_used + requests,
            budget.total_used + requests,
        )

    return Result(
        status,
        budget.sender_used,
        budget.total_used,
    )


class BudgetTests(unittest.TestCase):
    """Synthetic fixtures; not operational telemetry."""

    def test_original_examples(self):
        self.assertEqual(
            admit(Budget(0, 1, 2, 3, 4, 5)),
            Result(Admission.ALLOW, 1, 2),
        )

        self.assertEqual(
            admit(Budget(1, 1, 1, 5, 5, 5)).admission,
            Admission.PER_SENDER_LIMIT,
        )

        self.assertEqual(
            admit(Budget(0, 2, 5, 2, 5, 5)).admission,
            Admission.RECIPIENT_TOTAL_LIMIT,
        )

    def test_small_state_space(self):
        for total in range(5):
            for sender in range(total + 1):
                combinations = product(
                    range(4),
                    range(4),
                    range(1, 4),
                )

                for sender_limit, total_limit, quantity in combinations:
                    budget = Budget(
                        sender,
                        total,
                        sender_limit,
                        total_limit,
                        2,
                        3,
                    )

                    result = admit(
                        budget,
                        requests=quantity,
                    )

                    expected = (
                        sender + quantity <= min(sender_limit, 2)
                        and total + quantity <= min(total_limit, 3)
                    )

                    self.assertEqual(
                        result.allowed,
                        expected,
                    )

                    increment = quantity if expected else 0

                    self.assertEqual(
                        (
                            result.sender_after,
                            result.total_after,
                        ),
                        (
                            sender + increment,
                            total + increment,
                        ),
                    )

                    self.assertEqual(
                        quantity <= budget.capacity,
                        expected,
                    )

    def test_zero_and_lowered_limits(self):
        budgets = (
            Budget(0, 0, 0, 0, 0, 0),
            Budget(3, 5, 1, 2, 8, 8),
        )

        for budget in budgets:
            self.assertFalse(
                admit(budget).allowed
            )
            self.assertEqual(
                budget.capacity,
                0,
            )

    def test_bundle_is_all_or_nothing(self):
        budget = Budget(
            0, 0, 5, 2, 5, 5
        )

        self.assertEqual(
            admit(budget, requests=2),
            Result(Admission.ALLOW, 2, 2),
        )

        self.assertEqual(
            admit(budget, requests=3),
            Result(
                Admission.RECIPIENT_TOTAL_LIMIT,
                0,
                0,
            ),
        )

    def test_invalid_budget_fields(self):
        base = Budget(
            0, 0, 2, 2, 2, 2
        )

        for field in fields(base):
            for value in (-1, True, 1.5, "1", None):
                with self.assertRaises(LimitError):
                    replace(
                        base,
                        **{field.name: value},
                    )

        with self.assertRaises(LimitError):
            Budget(
                2, 1, 3, 3, 3, 3
            )

    def test_invalid_calls_and_results(self):
        budget = Budget(
            0, 0, 2, 2, 2, 2
        )

        for quantity in (0, -1, True, 1.5, None):
            with self.assertRaises(LimitError):
                admit(
                    budget,
                    requests=quantity,
                )

        with self.assertRaises(LimitError):
            admit(None)

        with self.assertRaises(LimitError):
            Result(
                "allow",
                0,
                0,
            )

        with self.assertRaises(LimitError):
            Result(
                Admission.ALLOW,
                2,
                1,
            )

    def test_purity_and_repeatability(self):
        budget = Budget(
            0, 0, 2, 2, 2, 2
        )
        before = replace(budget)

        self.assertEqual(
            admit(budget),
            admit(budget),
        )
        self.assertEqual(
            budget,
            before,
        )

    def test_cli_validation(self):
        self.assertEqual(
            parse_count("2"),
            2,
        )

        for value in ("-1", "x", "1.5"):
            with self.assertRaises(
                argparse.ArgumentTypeError
            ):
                parse_count(value)


def parse_count(value: str) -> int:
    """Parse a CLI count without accepting negative values."""
    try:
        result = int(value)
        nonnegative(
            result,
            "count",
        )
        return result

    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "expected a nonnegative integer"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Local request-budget evaluator; "
            "not a delivery service."
        )
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic conformance tests",
    )

    mode.add_argument(
        "--budget",
        nargs=6,
        type=parse_count,
        metavar=(
            "SENDER_USED",
            "TOTAL_USED",
            "MEMBER_SENDER",
            "MEMBER_TOTAL",
            "PLATFORM_SENDER",
            "PLATFORM_TOTAL",
        ),
        help="evaluate an administrative count snapshot",
    )

    parser.add_argument(
        "--requests",
        type=parse_count,
        default=1,
        help="positive all-or-nothing bundle size; default: 1",
    )

    parser.add_argument(
        "--log-summary",
        action="store_true",
        help="emit only the admission boolean to standard error",
    )

    args = parser.parse_args(argv)

    if args.requests == 0:
        parser.error(
            "--requests must be positive"
        )

    if args.budget is None and (
        args.requests != 1 or args.log_summary
    ):
        parser.error(
            "--requests and --log-summary require --budget"
        )

    if args.self_test:
        print(
            f"Python {sys.version.split()[0]}; "
            "runner=unittest",
            flush=True,
        )

        suite = (
            unittest.defaultTestLoader
            .loadTestsFromTestCase(BudgetTests)
        )

        result = unittest.TextTestRunner(
            verbosity=2
        ).run(suite)

        return 0 if result.wasSuccessful() else 1

    if args.budget is None:
        parser.print_help()
        return 0

    try:
        result = admit(
            Budget(*args.budget),
            requests=args.requests,
        )

    except LimitError as exc:
        parser.error(str(exc))

    if args.log_summary:
        logger = logging.Logger(
            "hearthline.request_budget"
        )
        logger.addHandler(
            logging.StreamHandler()
        )
        logger.setLevel(
            logging.INFO
        )
        logger.info(
            "Budget evaluation completed; allowed=%s",
            result.allowed,
        )

    print(
        f"admission={result.admission.value} "
        f"sender_after={result.sender_after} "
        f"total_after={result.total_after}"
    )

    return 0 if result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
