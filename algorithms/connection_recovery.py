# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure recovery-state model for one scoped interaction operation.

Run directly with Python 3.12+ to execute synthetic model tests.

No network, persistence, logging, authorization, or delivery is performed.
A committed state is historical status, never permission to resend.
"""

from enum import Enum
import unittest


class RecoveryError(ValueError):
    """An event is invalid for the supplied recovery state."""


class State(Enum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    OUTCOME_UNKNOWN = "outcome_unknown"
    NOT_COMMITTED = "not_committed"
    COMMITTED = "committed"
    WITHDRAWAL_PENDING = "withdrawal_pending"
    WITHDRAWN = "withdrawn"
    WITHDRAWN_AFTER_COMMIT = "withdrawn_after_commit"


class Event(Enum):
    INTERRUPTED = "interrupted"
    COMMIT_CONFIRMED = "commit_confirmed"
    NO_COMMIT_CONFIRMED = "no_commit_confirmed"
    REQUEST_WITHDRAWAL = "request_withdrawal"
    WITHDRAWAL_CONFIRMED = "withdrawal_confirmed"
    WITHDRAWAL_AFTER_COMMIT_CONFIRMED = (
        "withdrawal_after_commit_confirmed"
    )
    REVIEW_AGAIN = "review_again"


TRANSITIONS = {
    (State.DRAFT, Event.INTERRUPTED):
        State.REVIEW_REQUIRED,
    (State.REVIEW_REQUIRED, Event.REVIEW_AGAIN):
        State.DRAFT,
    (State.OUTCOME_UNKNOWN, Event.COMMIT_CONFIRMED):
        State.COMMITTED,
    (State.OUTCOME_UNKNOWN, Event.NO_COMMIT_CONFIRMED):
        State.NOT_COMMITTED,
    (State.NOT_COMMITTED, Event.REVIEW_AGAIN):
        State.DRAFT,
    (State.OUTCOME_UNKNOWN, Event.REQUEST_WITHDRAWAL):
        State.WITHDRAWAL_PENDING,
    (State.COMMITTED, Event.REQUEST_WITHDRAWAL):
        State.WITHDRAWAL_PENDING,
    (State.NOT_COMMITTED, Event.REQUEST_WITHDRAWAL):
        State.WITHDRAWAL_PENDING,
    (State.WITHDRAWAL_PENDING, Event.WITHDRAWAL_CONFIRMED):
        State.WITHDRAWN,
    (
        State.WITHDRAWAL_PENDING,
        Event.WITHDRAWAL_AFTER_COMMIT_CONFIRMED,
    ): State.WITHDRAWN_AFTER_COMMIT,
}


def recover(state: State, event: Event) -> State:
    """Return a recovery transition without executing an operation.

    OUTCOME_UNKNOWN must be supplied when a prior execution attempt may
    have committed. This module does not create or submit that attempt.
    """
    if type(state) is not State or type(event) is not Event:
        raise RecoveryError("validated state and event required")

    try:
        return TRANSITIONS[(state, event)]
    except KeyError as exc:
        raise RecoveryError(
            "transition requires separate review or authoritative evidence"
        ) from exc


class RecoveryTests(unittest.TestCase):
    """Synthetic tests establish only the reference transition behavior."""

    def test_private_interruption_requires_review(self):
        self.assertEqual(
            recover(State.DRAFT, Event.INTERRUPTED),
            State.REVIEW_REQUIRED,
        )

    def test_unknown_outcome_requires_confirmation(self):
        self.assertEqual(
            recover(
                State.OUTCOME_UNKNOWN,
                Event.NO_COMMIT_CONFIRMED,
            ),
            State.NOT_COMMITTED,
        )
        with self.assertRaises(RecoveryError):
            recover(
                State.OUTCOME_UNKNOWN,
                Event.REVIEW_AGAIN,
            )

    def test_withdrawal_preserves_prior_commit_history(self):
        pending = recover(
            State.COMMITTED,
            Event.REQUEST_WITHDRAWAL,
        )
        self.assertEqual(
            recover(
                pending,
                Event.WITHDRAWAL_AFTER_COMMIT_CONFIRMED,
            ),
            State.WITHDRAWN_AFTER_COMMIT,
        )

    def test_withdrawn_states_cannot_restart(self):
        for state in (
            State.WITHDRAWN,
            State.WITHDRAWN_AFTER_COMMIT,
        ):
            for event in Event:
                with self.assertRaises(RecoveryError):
                    recover(state, event)


if __name__ == "__main__":
    unittest.main(verbosity=2)
