# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent conformance expectations for connection recovery.

Run from the repository root:

    python -m unittest algorithms.test_connection_recovery -v

These tests use synthetic states and authoritative assertions.
They do not authenticate observations or establish distributed correctness.
"""

import unittest

from algorithms.connection_recovery import (
    Commitment,
    ContradictionError,
    Observation,
    Recovery,
    Resolution,
    StaleRevisionError,
    ValidationError,
    Withdrawal,
    request_withdrawal,
    resolve,
    resolve_many,
)


# Expected meanings are deliberately independent of implementation helpers.
EXPECTED_EFFECTS = (
    (
        Resolution.COMMITTED,
        Commitment.COMMITTED,
        False,
    ),
    (
        Resolution.TERMINAL_NO_COMMIT,
        Commitment.NOT_COMMITTED,
        False,
    ),
    (
        Resolution.WITHDRAWN_BEFORE_COMMIT,
        Commitment.NOT_COMMITTED,
        True,
    ),
    (
        Resolution.WITHDRAWN_AFTER_COMMIT,
        Commitment.COMMITTED,
        True,
    ),
)


class RecoveryConformanceTests(unittest.TestCase):
    def test_independent_transition_matrix(self):
        checked = 0

        for commitment in Commitment:
            for withdrawal in Withdrawal:
                if (
                    commitment is Commitment.UNKNOWN
                    and withdrawal is Withdrawal.CONFIRMED
                ):
                    continue

                original = Recovery(
                    commitment=commitment,
                    withdrawal=withdrawal,
                    authority_revision=7,
                )

                for resolution, expected_commitment, confirms in (
                    EXPECTED_EFFECTS
                ):
                    with self.subTest(
                        commitment=commitment,
                        withdrawal=withdrawal,
                        resolution=resolution,
                    ):
                        contradictory = (
                            commitment is not Commitment.UNKNOWN
                            and commitment is not expected_commitment
                        )

                        if contradictory:
                            with self.assertRaises(ContradictionError):
                                resolve(
                                    original,
                                    resolution,
                                    8,
                                )
                        else:
                            updated = resolve(
                                original,
                                resolution,
                                8,
                            )

                            expected_withdrawal = (
                                Withdrawal.CONFIRMED
                                if confirms
                                else withdrawal
                            )

                            self.assertEqual(
                                updated,
                                Recovery(
                                    commitment=expected_commitment,
                                    withdrawal=expected_withdrawal,
                                    authority_revision=8,
                                ),
                            )
                            self.assertFalse(
                                updated.permission_to_resend
                            )

                        self.assertEqual(
                            original,
                            Recovery(
                                commitment=commitment,
                                withdrawal=withdrawal,
                                authority_revision=7,
                            ),
                        )

                    checked += 1

        self.assertEqual(checked, 32)

    def test_local_request_preserves_authoritative_history(self):
        original = Recovery(
            commitment=Commitment.COMMITTED,
            withdrawal=Withdrawal.NOT_REQUESTED,
            authority_revision=12,
        )

        pending = request_withdrawal(original)

        self.assertEqual(
            pending,
            Recovery(
                commitment=Commitment.COMMITTED,
                withdrawal=Withdrawal.PENDING,
                authority_revision=12,
            ),
        )
        self.assertEqual(
            request_withdrawal(pending),
            pending,
        )

    def test_old_and_duplicate_revisions_are_rejected(self):
        original = Recovery(
            commitment=Commitment.COMMITTED,
            authority_revision=12,
        )

        for revision in (0, 11, 12):
            with self.subTest(revision=revision):
                with self.assertRaises(StaleRevisionError):
                    resolve(
                        original,
                        Resolution.COMMITTED,
                        revision,
                    )

    def test_out_of_order_batch_is_not_silently_sorted(self):
        original = Recovery()

        observations = (
            Observation(
                Resolution.COMMITTED,
                2,
            ),
            Observation(
                Resolution.WITHDRAWN_AFTER_COMMIT,
                1,
            ),
        )

        with self.assertRaises(StaleRevisionError):
            resolve_many(
                original,
                observations,
            )

        self.assertEqual(original, Recovery())

    def test_terminal_negative_cannot_become_committed(self):
        original = Recovery(
            commitment=Commitment.NOT_COMMITTED,
            withdrawal=Withdrawal.CONFIRMED,
            authority_revision=4,
        )

        for resolution in (
            Resolution.COMMITTED,
            Resolution.WITHDRAWN_AFTER_COMMIT,
        ):
            with self.subTest(resolution=resolution):
                with self.assertRaises(ContradictionError):
                    resolve(
                        original,
                        resolution,
                        5,
                    )

    def test_batch_limit_and_empty_batch(self):
        original = Recovery()
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

        self.assertEqual(
            resolve_many(original, ()),
            original,
        )

        with self.assertRaises(ValidationError):
            resolve_many(
                original,
                observations,
                max_observations=1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
