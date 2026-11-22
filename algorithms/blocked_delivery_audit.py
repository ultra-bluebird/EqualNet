# SPDX-License-Identifier: MIT OR Apache-2.0
"""Audit one operation's supplied blocking and commitment trace.

Run directly with Python 3.12+ to execute synthetic tests.

The integration must supply:
- One protected operation on one declared channel.
- An authoritative event order.
- The initial block state.
- A reviewed definition of commitment.

No logging, networking, delivery, authorization, or persistence occurs.
An empty findings tuple is not evidence of complete observation.
"""

from dataclasses import dataclass
from enum import Enum
import unittest


class TraceError(ValueError):
    """Malformed or oversized trace input."""


class Event(Enum):
    BLOCK_CONFIRMED = "block_confirmed"
    UNBLOCK_CONFIRMED = "unblock_confirmed"
    COMMIT = "commit"
    ARRIVAL = "arrival"


class Finding(Enum):
    COMMIT_WHILE_BLOCKED = "commit_while_blocked"
    REPEATED_COMMIT = "repeated_commit"
    ARRIVAL_WITHOUT_COMMIT = "arrival_without_commit"
    REPEATED_ARRIVAL = "repeated_arrival"


@dataclass(frozen=True, slots=True)
class Assessment:
    findings: tuple[Finding, ...]
    committed: bool
    arrived: bool
    blocked_at_end: bool


def audit_trace(
    events: tuple[Event, ...],
    *,
    initially_blocked: bool,
    max_events: int = 1000,
) -> Assessment:
    """Describe observed ordering problems without changing live state.

    Observed prohibited commitments remain recorded as commitments.
    The auditor does not rewrite history to make a trace compliant.
    """
    if (
        type(events) is not tuple
        or type(initially_blocked) is not bool
    ):
        raise TraceError(
            "immutable trace and explicit initial block state required"
        )

    if (
        type(max_events) is not int
        or max_events <= 0
    ):
        raise TraceError(
            "positive event limit required"
        )

    if len(events) > max_events:
        raise TraceError(
            "trace event limit exceeded"
        )

    if any(
        type(event) is not Event
        for event in events
    ):
        raise TraceError(
            "known trace events required"
        )

    blocked = initially_blocked
    committed = False
    arrived = False
    findings = []

    for event in events:
        if event is Event.BLOCK_CONFIRMED:
            blocked = True

        elif event is Event.UNBLOCK_CONFIRMED:
            blocked = False

        elif event is Event.COMMIT:
            if blocked:
                findings.append(
                    Finding.COMMIT_WHILE_BLOCKED
                )

            if committed:
                findings.append(
                    Finding.REPEATED_COMMIT
                )

            committed = True

        else:
            if not committed:
                findings.append(
                    Finding.ARRIVAL_WITHOUT_COMMIT
                )

            if arrived:
                findings.append(
                    Finding.REPEATED_ARRIVAL
                )

            arrived = True

    return Assessment(
        findings=tuple(findings),
        committed=committed,
        arrived=arrived,
        blocked_at_end=blocked,
    )


class TraceTests(unittest.TestCase):
    """Synthetic histories are not production blocking evidence."""

    def test_block_precedes_commit(self):
        result = audit_trace(
            (
                Event.BLOCK_CONFIRMED,
                Event.COMMIT,
            ),
            initially_blocked=False,
        )

        self.assertIn(
            Finding.COMMIT_WHILE_BLOCKED,
            result.findings,
        )

    def test_prior_commit_late_arrival(self):
        result = audit_trace(
            (
                Event.COMMIT,
                Event.BLOCK_CONFIRMED,
                Event.ARRIVAL,
            ),
            initially_blocked=False,
        )

        self.assertEqual(
            result.findings,
            (),
        )
        self.assertTrue(
            result.blocked_at_end
        )

    def test_unblock_does_not_reset_replay_history(self):
        result = audit_trace(
            (
                Event.COMMIT,
                Event.BLOCK_CONFIRMED,
                Event.UNBLOCK_CONFIRMED,
                Event.COMMIT,
            ),
            initially_blocked=False,
        )

        self.assertIn(
            Finding.REPEATED_COMMIT,
            result.findings,
        )

    def test_missing_and_duplicate_commit_records(self):
        result = audit_trace(
            (
                Event.ARRIVAL,
                Event.ARRIVAL,
            ),
            initially_blocked=False,
        )

        self.assertIn(
            Finding.ARRIVAL_WITHOUT_COMMIT,
            result.findings,
        )
        self.assertIn(
            Finding.REPEATED_ARRIVAL,
            result.findings,
        )

        with self.assertRaises(TraceError):
            audit_trace(
                ("commit",),
                initially_blocked=False,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
