# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure recovery state for one already-scoped execution attempt.

Python: 3.12+

Usage:
    python algorithms/connection_recovery.py --self-test
    python algorithms/connection_recovery.py --demo

The core performs no authorization, persistence, networking, logging,
clock access, or delivery.

The integration must authenticate authoritative observations and bind
them to the same operation. A revision alone establishes neither
authenticity nor operation binding.

TERMINAL_NO_COMMIT means the operation cannot commit later. Absence
from a query result, a timeout, or a stale read is insufficient.

Recovery status never grants permission to resend.

CLI exit statuses:
    0: help displayed, demonstration completed, or tests passed
    1: tests failed
    2: invalid arguments

The demonstration uses synthetic state, not operational evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from enum import Enum
import platform
import unittest


__all__ = [
    "RecoveryError",
    "ValidationError",
    "StaleRevisionError",
    "ContradictionError",
    "Commitment",
    "Withdrawal",
    "Resolution",
    "Recovery",
    "Observation",
    "request_withdrawal",
    "resolve",
    "resolve_many",
]


class RecoveryError(ValueError):
    """Base error for recovery contract failures."""


class ValidationError(RecoveryError):
    """Malformed input or structurally invalid recovery state."""


class StaleRevisionError(RecoveryError):
    """An observation does not advance authoritative revision."""


class ContradictionError(RecoveryError):
    """An observation contradicts terminal commitment history."""


class Commitment(Enum):
    UNKNOWN = "unknown"
    NOT_COMMITTED = "not_committed"
    COMMITTED = "committed"


class Withdrawal(Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    CONFIRMED = "confirmed"


class Resolution(Enum):
    COMMITTED = "committed"
    TERMINAL_NO_COMMIT = "terminal_no_commit"
    WITHDRAWN_BEFORE_COMMIT = "withdrawn_before_commit"
    WITHDRAWN_AFTER_COMMIT = "withdrawn_after_commit"


def revision_value(value: object) -> None:
    """Require a nonnegative built-in integer, rejecting bool."""
    if type(value) is not int or value < 0:
        raise ValidationError(
            "revision must be a nonnegative built-in integer"
        )


@dataclass(frozen=True, slots=True)
class Recovery:
    commitment: Commitment = Commitment.UNKNOWN
    withdrawal: Withdrawal = Withdrawal.NOT_REQUESTED
    authority_revision: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.commitment) is not Commitment
            or type(self.withdrawal) is not Withdrawal
        ):
            raise ValidationError(
                "validated status values required"
            )

        revision_value(self.authority_revision)

        if (
            self.withdrawal is Withdrawal.CONFIRMED
            and self.commitment is Commitment.UNKNOWN
        ):
            raise ValidationError(
                "confirmed withdrawal requires "
                "resolved commitment history"
            )

    @property
    def permission_to_resend(self) -> bool:
        """Historical recovery status never supplies authorization."""
        return False


@dataclass(frozen=True, slots=True)
class Observation:
    """A resolution assertion supplied by a trusted integration.

    Construction validates shape, not authenticity or truth.
    """

    resolution: Resolution
    revision: int

    def __post_init__(self) -> None:
        if type(self.resolution) is not Resolution:
            raise ValidationError(
                "validated resolution required"
            )

        revision_value(self.revision)


def require_state(state: object) -> None:
    if type(state) is not Recovery:
        raise ValidationError(
            "validated recovery state required"
        )


def request_withdrawal(state: Recovery) -> Recovery:
    """Record a local request without claiming server confirmation.

    Repeated requests are idempotent. Commitment history and the
    authoritative revision remain unchanged.

    This function does not transmit the request.
    """
    require_state(state)

    if state.withdrawal is not Withdrawal.NOT_REQUESTED:
        return state

    return replace(
        state,
        withdrawal=Withdrawal.PENDING,
    )


def resolution_effect(
    resolution: Resolution,
) -> tuple[Commitment, bool]:
    """Map a validated resolution to its historical effect."""
    match resolution:
        case Resolution.COMMITTED:
            return Commitment.COMMITTED, False

        case Resolution.TERMINAL_NO_COMMIT:
            return Commitment.NOT_COMMITTED, False

        case Resolution.WITHDRAWN_BEFORE_COMMIT:
            return Commitment.NOT_COMMITTED, True

        case Resolution.WITHDRAWN_AFTER_COMMIT:
            return Commitment.COMMITTED, True

    raise ValidationError("unsupported resolution")


def resolve(
    state: Recovery,
    resolution: Resolution,
    revision: int,
) -> Recovery:
    """Apply a newer authoritative assertion without external effects.

    Terminal commitment history cannot change. Withdrawal confirmation
    cannot regress.

    A commit observation received after a local withdrawal request
    does not establish that commitment occurred after authoritative
    withdrawal. Observation order and execution order are distinct.

    Duplicate and older revisions are rejected. The integration must
    handle transport duplicates without weakening contradiction checks.
    """
    require_state(state)
    observation = Observation(resolution, revision)

    if observation.revision <= state.authority_revision:
        raise StaleRevisionError(
            "newer authoritative revision required"
        )

    commitment, confirmed = resolution_effect(
        observation.resolution
    )

    if (
        state.commitment is not Commitment.UNKNOWN
        and commitment is not state.commitment
    ):
        raise ContradictionError(
            "contradictory terminal commitment history"
        )

    return Recovery(
        commitment=commitment,
        withdrawal=(
            Withdrawal.CONFIRMED
            if confirmed
            else state.withdrawal
        ),
        authority_revision=observation.revision,
    )


def resolve_many(
    state: Recovery,
    observations: tuple[Observation, ...],
    *,
    max_observations: int = 1000,
) -> Recovery:
    """Evaluate an ordered, bounded batch and return its final state.

    An empty batch returns the original state.

    Observations are processed in supplied order, never silently sorted.
    Every observation must advance the authoritative revision.

    If evaluation raises, the immutable input state remains unchanged.
    This is local evaluation behavior, not a database transaction.
    """
    require_state(state)

    if (
        type(max_observations) is not int
        or max_observations <= 0
    ):
        raise ValidationError(
            "batch limit must be a positive built-in integer"
        )

    if (
        type(observations) is not tuple
        or any(
            type(item) is not Observation
            for item in observations
        )
    ):
        raise ValidationError(
            "immutable tuple of observations required"
        )

    if len(observations) > max_observations:
        raise ValidationError(
            "observation batch exceeds configured limit"
        )

    current = state

    for observation in observations:
        current = resolve(
            current,
            observation.resolution,
            observation.revision,
        )

    return current


class RecoveryTests(unittest.TestCase):
    """Synthetic tests establish only reference-model behavior."""

    def test_pending_preserves_history(self):
        state = resolve(
            Recovery(),
            Resolution.COMMITTED,
            1,
        )
        pending = request_withdrawal(state)

        self.assertEqual(
            pending.commitment,
            Commitment.COMMITTED,
        )
        self.assertEqual(
            pending.withdrawal,
            Withdrawal.PENDING,
        )

        with self.assertRaises(ContradictionError):
            resolve(
                pending,
                Resolution.WITHDRAWN_BEFORE_COMMIT,
                2,
            )

    def test_unknown_withdrawal(self):
        final = resolve(
            request_withdrawal(Recovery()),
            Resolution.WITHDRAWN_BEFORE_COMMIT,
            1,
        )

        self.assertEqual(
            final.commitment,
            Commitment.NOT_COMMITTED,
        )
        self.assertEqual(
            final.withdrawal,
            Withdrawal.CONFIRMED,
        )
        self.assertEqual(
            request_withdrawal(final),
            final,
        )

    def test_confirmation_never_regresses(self):
        final = resolve(
            Recovery(),
            Resolution.WITHDRAWN_AFTER_COMMIT,
            1,
        )
        later = resolve(
            final,
            Resolution.COMMITTED,
            2,
        )

        self.assertEqual(
            later.withdrawal,
            Withdrawal.CONFIRMED,
        )
        self.assertFalse(
            later.permission_to_resend
        )

    def test_stale_and_invalid(self):
        state = resolve(
            Recovery(),
            Resolution.TERMINAL_NO_COMMIT,
            1,
        )

        with self.assertRaises(StaleRevisionError):
            resolve(
                state,
                Resolution.TERMINAL_NO_COMMIT,
                1,
            )

        invalid_calls = (
            lambda: Recovery(
                withdrawal=Withdrawal.CONFIRMED
            ),
            lambda: Observation(
                Resolution.COMMITTED,
                True,
            ),
            lambda: resolve(
                None,
                Resolution.COMMITTED,
                1,
            ),
            lambda: Observation(
                "committed",
                1,
            ),
        )

        for call in invalid_calls:
            with self.assertRaises(ValidationError):
                call()

    def test_batch_and_failed_batch_preserve_input(self):
        start = request_withdrawal(Recovery())

        observations = (
            Observation(
                Resolution.COMMITTED,
                1,
            ),
            Observation(
                Resolution.WITHDRAWN_AFTER_COMMIT,
                2,
            ),
        )

        final = resolve_many(
            start,
            observations,
        )

        self.assertEqual(
            final,
            resolve(
                resolve(
                    start,
                    Resolution.COMMITTED,
                    1,
                ),
                Resolution.WITHDRAWN_AFTER_COMMIT,
                2,
            ),
        )

        with self.assertRaises(ContradictionError):
            resolve_many(
                start,
                observations + (
                    Observation(
                        Resolution.TERMINAL_NO_COMMIT,
                        3,
                    ),
                ),
            )

        self.assertEqual(
            start,
            Recovery(
                withdrawal=Withdrawal.PENDING
            ),
        )
        self.assertEqual(
            resolve_many(start, ()),
            start,
        )

        with self.assertRaises(ValidationError):
            resolve_many(
                start,
                observations,
                max_observations=1,
            )

    def test_all_valid_state_resolution_pairs(self):
        count = 0

        for commitment in Commitment:
            for withdrawal in Withdrawal:
                if (
                    commitment is Commitment.UNKNOWN
                    and withdrawal is Withdrawal.CONFIRMED
                ):
                    continue

                state = Recovery(
                    commitment,
                    withdrawal,
                )

                self.assertFalse(
                    state.permission_to_resend
                )
                self.assertEqual(
                    request_withdrawal(
                        request_withdrawal(state)
                    ),
                    request_withdrawal(state),
                )

                for resolution in Resolution:
                    target, confirmed = resolution_effect(
                        resolution
                    )

                    if (
                        commitment is not Commitment.UNKNOWN
                        and target is not commitment
                    ):
                        with self.assertRaises(
                            ContradictionError
                        ):
                            resolve(
                                state,
                                resolution,
                                1,
                            )

                    else:
                        result = resolve(
                            state,
                            resolution,
                            1,
                        )

                        self.assertEqual(
                            result.commitment,
                            target,
                        )
                        self.assertEqual(
                            result.withdrawal,
                            (
                                Withdrawal.CONFIRMED
                                if confirmed
                                else withdrawal
                            ),
                        )
                        self.assertFalse(
                            result.permission_to_resend
                        )

                    count += 1

        self.assertEqual(count, 32)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Local recovery model; "
            "no delivery or authorization."
        )
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic model tests",
    )
    mode.add_argument(
        "--demo",
        action="store_true",
        help="display a synthetic withdrawal outcome",
    )

    args = parser.parse_args(argv)

    if args.self_test:
        print(
            f"Python {platform.python_version()}; "
            "runner=unittest",
            flush=True,
        )

        suite = (
            unittest.defaultTestLoader
            .loadTestsFromTestCase(RecoveryTests)
        )

        result = unittest.TextTestRunner(
            verbosity=2
        ).run(suite)

        return 0 if result.wasSuccessful() else 1

    if args.demo:
        final = resolve(
            request_withdrawal(Recovery()),
            Resolution.WITHDRAWN_BEFORE_COMMIT,
            1,
        )

        print(
            f"commitment={final.commitment.value} "
            f"withdrawal={final.withdrawal.value} "
            f"permission_to_resend="
            f"{final.permission_to_resend}"
        )

        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
