# SPDX-License-Identifier: MIT OR Apache-2.0
"""Evaluate evidence completeness, scope, and currentness.

Run directly with Python 3.12+ to execute synthetic conformance tests.
This module has no deployment, notification, or member-data capabilities.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import unittest


# Document credit only; not identity, consent, or execution authority.
ATTRIBUTION = "bostrom18sd2ujv24ual9c9pshtxys6j8knh6xaead9ye7"

OBLIGATIONS = frozenset({
    "state_semantics",
    "observable_leakage",
    "authorization_concurrency",
    "eligibility_uncertainty",
    "derived_data_lineage",
    "research_telemetry",
    "accessible_control",
    "causal_identification",
    "outcome_interpretation",
    "assurance_governance",
})


class ContractError(Exception):
    """The supplied assurance contract is malformed or ambiguous."""


@dataclass(frozen=True)
class Scope:
    build: str
    configuration: str
    architecture: str


@dataclass(frozen=True)
class Evidence:
    obligation: str
    scope: Scope
    passed: bool
    reviewed_at: datetime
    expires_at: datetime
    owner: str
    reference: str
    invalidated: bool = False


@dataclass(frozen=True)
class Decision:
    ready: bool
    blockers: tuple[str, ...]


def aware(value):
    return (
        isinstance(value, datetime)
        and value.utcoffset() is not None
    )


def assess(
    scope: Scope,
    records: tuple[Evidence, ...],
    now: datetime,
) -> Decision:
    """Assess supplied records without performing external actions.

    Evidence intervals are inclusive at review and exclusive at expiry.
    Duplicate records require explicit resolution rather than last-write-wins.
    """
    if not isinstance(scope, Scope) or not aware(now):
        raise ContractError(
            "scope and timezone-aware assessment time required"
        )

    if any(
        not isinstance(value, str) or not value.strip()
        for value in (
            scope.build,
            scope.configuration,
            scope.architecture,
        )
    ):
        raise ContractError(
            "scope components must be nonempty strings"
        )

    indexed = {}

    for record in records:
        if not isinstance(record, Evidence):
            raise ContractError("invalid evidence record")

        if record.obligation not in OBLIGATIONS:
            raise ContractError("unknown obligation")

        if record.obligation in indexed:
            raise ContractError(
                "duplicate evidence requires explicit resolution"
            )

        if (
            type(record.passed) is not bool
            or type(record.invalidated) is not bool
        ):
            raise ContractError("evidence flags must be boolean")

        if (
            not aware(record.reviewed_at)
            or not aware(record.expires_at)
        ):
            raise ContractError(
                "timezone-aware evidence times required"
            )

        if record.reviewed_at >= record.expires_at:
            raise ContractError("invalid evidence interval")

        if any(
            not isinstance(value, str) or not value.strip()
            for value in (record.owner, record.reference)
        ):
            raise ContractError(
                "evidence owner and reference required"
            )

        indexed[record.obligation] = record

    blockers = []

    for name in sorted(OBLIGATIONS):
        record = indexed.get(name)

        if record is None:
            blockers.append(f"{name}:missing")
            continue

        if record.scope != scope:
            blockers.append(f"{name}:scope_mismatch")

        if not record.passed:
            blockers.append(f"{name}:failed")

        if record.invalidated:
            blockers.append(f"{name}:invalidated")

        if not record.reviewed_at <= now < record.expires_at:
            blockers.append(f"{name}:not_current")

    return Decision(
        ready=not blockers,
        blockers=tuple(blockers),
    )


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        # Synthetic fixtures are not operational release evidence.
        self.now = datetime(
            2030, 1, 1, tzinfo=timezone.utc
        )
        self.scope = Scope(
            "synthetic-build",
            "synthetic-config",
            "synthetic-architecture",
        )
        self.records = tuple(
            Evidence(
                obligation=name,
                scope=self.scope,
                passed=True,
                reviewed_at=self.now - timedelta(days=1),
                expires_at=self.now + timedelta(days=1),
                owner="synthetic-owner",
                reference="synthetic-reference",
            )
            for name in sorted(OBLIGATIONS)
        )

    def test_complete_current_set(self):
        decision = assess(
            self.scope, self.records, self.now
        )
        self.assertTrue(decision.ready)

    def test_each_missing_obligation_blocks(self):
        for index in range(len(self.records)):
            records = (
                self.records[:index]
                + self.records[index + 1:]
            )
            decision = assess(
                self.scope, records, self.now
            )
            self.assertFalse(decision.ready)

    def test_failures_and_scope_changes_block(self):
        changes_to_test = (
            {"passed": False},
            {"invalidated": True},
            {"expires_at": self.now},
            {
                "reviewed_at":
                    self.now + timedelta(hours=1)
            },
            {
                "scope": replace(
                    self.scope,
                    configuration="changed",
                )
            },
        )

        for changes in changes_to_test:
            records = (
                replace(self.records[0], **changes),
            ) + self.records[1:]

            decision = assess(
                self.scope, records, self.now
            )
            self.assertFalse(decision.ready)

    def test_duplicate_and_naive_time_rejected(self):
        with self.assertRaises(ContractError):
            assess(
                self.scope,
                self.records + self.records[:1],
                self.now,
            )

        with self.assertRaises(ContractError):
            assess(
                self.scope,
                self.records,
                self.now.replace(tzinfo=None),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
