# SPDX-License-Identifier: MIT OR Apache-2.0
"""Sequential reference model for a single protected operation.

Run directly with Python 3.12+ to execute synthetic tests.

The caller supplies an already-scoped operation. This module does not
authenticate callers, issue authorization, perform delivery, or implement
a distributed atomic store.
"""

from dataclasses import dataclass, replace
from enum import Enum
from itertools import permutations
import unittest


class ProtocolError(ValueError):
    """Malformed protocol input."""


class Outcome(Enum):
    COMMITTED = "committed"
    ALREADY_COMMITTED = "already_committed"
    WITHDRAWN = "withdrawn"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class State:
    revision: int = 0
    withdrawn: bool = False
    committed: bool = False

    def __post_init__(self):
        if type(self.revision) is not int or self.revision < 0:
            raise ProtocolError(
                "revision must be a nonnegative integer"
            )

        if (
            type(self.withdrawn) is not bool
            or type(self.committed) is not bool
        ):
            raise ProtocolError(
                "state flags must be boolean"
            )


@dataclass(frozen=True, slots=True)
class Result:
    state: State
    outcome: Outcome


def withdraw(state: State) -> State:
    """Withdraw future permission without undoing a prior commitment."""
    if type(state) is not State:
        raise ProtocolError("validated state required")

    if state.withdrawn:
        return state

    return replace(
        state,
        withdrawn=True,
        revision=state.revision + 1,
    )


def commit(
    state: State,
    expected_revision: int,
) -> Result:
    """Apply one transition in an externally enforced operation order.

    ALREADY_COMMITTED is historical status, not permission to repeat an
    external side effect. WITHDRAWN takes precedence on subsequent calls.
    """
    if type(state) is not State:
        raise ProtocolError("validated state required")

    if (
        type(expected_revision) is not int
        or expected_revision < 0
    ):
        raise ProtocolError(
            "expected revision must be a nonnegative integer"
        )

    if state.withdrawn:
        return Result(state, Outcome.WITHDRAWN)

    if state.committed:
        return Result(state, Outcome.ALREADY_COMMITTED)

    if expected_revision != state.revision:
        return Result(state, Outcome.STALE)

    return Result(
        replace(
            state,
            committed=True,
            revision=state.revision + 1,
        ),
        Outcome.COMMITTED,
    )


class ProtocolTests(unittest.TestCase):
    """Synthetic schedules are not production concurrency evidence."""

    def test_withdrawal_precedes_commit(self):
        state = withdraw(State())
        result = commit(state, 0)

        self.assertEqual(
            result.outcome,
            Outcome.WITHDRAWN,
        )
        self.assertFalse(result.state.committed)

    def test_commit_precedes_withdrawal(self):
        result = commit(State(), 0)
        state = withdraw(result.state)

        self.assertTrue(state.committed)
        self.assertTrue(state.withdrawn)
        self.assertEqual(
            commit(state, state.revision).outcome,
            Outcome.WITHDRAWN,
        )

    def test_retry_and_stale_revision(self):
        self.assertEqual(
            commit(State(), 1).outcome,
            Outcome.STALE,
        )

        result = commit(State(), 0)
        retry = commit(result.state, 0)

        self.assertEqual(
            retry.outcome,
            Outcome.ALREADY_COMMITTED,
        )
        self.assertEqual(
            retry.state,
            result.state,
        )
        self.assertEqual(
            withdraw(withdraw(State())),
            withdraw(State()),
        )

    def test_all_three_event_orders(self):
        for order in permutations(
            ("withdraw", "attempt", "retry")
        ):
            state = State()
            commits = 0

            for event in order:
                if event == "withdraw":
                    state = withdraw(state)
                    continue

                was_withdrawn = state.withdrawn
                result = commit(state, 0)

                if was_withdrawn:
                    self.assertNotEqual(
                        result.outcome,
                        Outcome.COMMITTED,
                    )

                commits += (
                    result.outcome is Outcome.COMMITTED
                )
                state = result.state

            self.assertLessEqual(commits, 1)

    def test_invalid_inputs(self):
        calls = (
            lambda: State(-1),
            lambda: State(withdrawn=1),
            lambda: commit(State(), True),
            lambda: withdraw(None),
        )

        for call in calls:
            with self.assertRaises(ProtocolError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
