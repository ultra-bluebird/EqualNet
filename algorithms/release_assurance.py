# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pure release-evidence assessment for Python 3.12+.

Run: python algorithms/release_assurance.py --self-test

Records are assertions supplied by a caller, not verified evidence.
No deployment, network, filesystem, or member-data operations are performed
by assess(). Optional logging contains aggregate counts only.
"""

from __future__ import annotations

import argparse
import logging
import sys
import unittest
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum


API_VERSION = "2.0.0"

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


class ContractError(ValueError):
    """Malformed input; callers must not interpret this as readiness."""


class DuplicateEvidenceError(ContractError):
    """Duplicate evidence requires explicit resolution."""


class ResourceLimitError(ContractError):
    """The configured assessment size limit was exceeded."""


def text(value: object, label: str) -> None:
    """Require nonempty text without silently modifying it."""
    if type(value) is not str or not value.strip():
        raise ContractError(
            f"{label} must be a nonempty string"
        )


def instant(value: object, label: str) -> datetime:
    """Validate a timezone-aware datetime and normalize it to UTC."""
    if type(value) is not datetime:
        raise ContractError(
            f"{label} must be a datetime"
        )

    try:
        if value.utcoffset() is None:
            raise ContractError(
                f"{label} must be timezone-aware"
            )
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ContractError(
            f"{label} must be a valid aware datetime"
        ) from exc


@dataclass(frozen=True, slots=True)
class Scope:
    build: str
    configuration: str
    architecture: str

    def __post_init__(self) -> None:
        for name in (
            "build",
            "configuration",
            "architecture",
        ):
            text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class Evidence:
    obligation: str
    scope: Scope
    passed: bool
    reviewed_at: datetime
    expires_at: datetime
    owner: str
    reference: str
    invalidated: bool = False

    def __post_init__(self) -> None:
        for name in (
            "obligation",
            "owner",
            "reference",
        ):
            text(getattr(self, name), name)

        if type(self.scope) is not Scope:
            raise ContractError(
                "evidence scope must be Scope"
            )

        if (
            type(self.passed) is not bool
            or type(self.invalidated) is not bool
        ):
            raise ContractError(
                "evidence flags must be boolean"
            )

        start = instant(
            self.reviewed_at,
            "reviewed_at",
        )
        end = instant(
            self.expires_at,
            "expires_at",
        )

        if start >= end:
            raise ContractError(
                "review must precede expiry"
            )

        object.__setattr__(
            self,
            "reviewed_at",
            start,
        )
        object.__setattr__(
            self,
            "expires_at",
            end,
        )


@dataclass(frozen=True, slots=True)
class Policy:
    """May add obligations, but cannot remove the mandatory baseline."""

    required: frozenset[str] = OBLIGATIONS
    max_records: int = 1000
    max_review_age: timedelta | None = None

    def __post_init__(self) -> None:
        if type(self.required) is not frozenset:
            raise ContractError(
                "required must be a frozenset"
            )

        for name in self.required:
            text(name, "required obligation")

        if not OBLIGATIONS <= self.required:
            raise ContractError(
                "mandatory obligations cannot be removed"
            )

        if (
            type(self.max_records) is not int
            or self.max_records < len(self.required)
        ):
            raise ContractError(
                "max_records must cover all required obligations"
            )

        if self.max_review_age is not None:
            if type(self.max_review_age) is not timedelta:
                raise ContractError(
                    "max_review_age must be a timedelta"
                )

            if self.max_review_age <= timedelta(0):
                raise ContractError(
                    "max_review_age must be positive"
                )


class Reason(StrEnum):
    MISSING = "missing"
    SCOPE_MISMATCH = "scope_mismatch"
    FAILED = "failed"
    INVALIDATED = "invalidated"
    NOT_CURRENT = "not_current"
    TOO_OLD = "too_old"


@dataclass(frozen=True, slots=True)
class Blocker:
    obligation: str
    reason: Reason


@dataclass(frozen=True, slots=True)
class Decision:
    scope: Scope
    assessed_at: datetime
    blockers: tuple[Blocker, ...]
    next_review_at: datetime | None

    @property
    def ready(self) -> bool:
        """Readiness is derived, never supplied independently."""
        return not self.blockers

    @property
    def blocker_messages(self) -> tuple[str, ...]:
        """Provide stable text for callers migrating from string blockers."""
        return tuple(
            f"{blocker.obligation}:{blocker.reason.value}"
            for blocker in self.blockers
        )


def assess(
    scope: Scope,
    records: tuple[Evidence, ...],
    now: datetime,
    *,
    policy: Policy = Policy(),
    logger: logging.Logger | None = None,
) -> Decision:
    """Evaluate a validated in-memory snapshot; never authorize deployment.

    Expiry and maximum age are exclusive upper bounds.

    Unknown obligations, duplicates, malformed containers, and resource
    overflow raise ContractError. Any exception means no affirmative
    readiness decision was produced.

    next_review_at is the earliest scheduled loss of currentness for a ready
    decision. Architectural changes or external invalidation can require
    reassessment sooner.
    """
    if type(scope) is not Scope or type(policy) is not Policy:
        raise ContractError(
            "Scope and Policy instances required"
        )

    now = instant(now, "now")

    if type(records) is not tuple:
        raise ContractError(
            "records must be an immutable tuple"
        )

    if (
        logger is not None
        and not isinstance(logger, logging.Logger)
    ):
        raise ContractError(
            "logger must be a logging.Logger"
        )

    if len(records) > policy.max_records:
        raise ResourceLimitError(
            "too many evidence records"
        )

    indexed: dict[str, Evidence] = {}

    for record in records:
        if type(record) is not Evidence:
            raise ContractError(
                "each record must be Evidence"
            )

        if record.obligation not in policy.required:
            raise ContractError(
                "unknown obligation"
            )

        if record.obligation in indexed:
            raise DuplicateEvidenceError(
                "duplicate obligation"
            )

        indexed[record.obligation] = record

    blockers: list[Blocker] = []
    deadlines: list[datetime] = []

    for name in sorted(policy.required):
        record = indexed.get(name)

        if record is None:
            blockers.append(
                Blocker(name, Reason.MISSING)
            )
            continue

        reasons: list[Reason] = []

        if record.scope != scope:
            reasons.append(
                Reason.SCOPE_MISMATCH
            )

        if not record.passed:
            reasons.append(
                Reason.FAILED
            )

        if record.invalidated:
            reasons.append(
                Reason.INVALIDATED
            )

        if not record.reviewed_at <= now < record.expires_at:
            reasons.append(
                Reason.NOT_CURRENT
            )

        deadline = record.expires_at

        if policy.max_review_age is not None:
            if now - record.reviewed_at >= policy.max_review_age:
                reasons.append(
                    Reason.TOO_OLD
                )

            try:
                deadline = min(
                    deadline,
                    record.reviewed_at + policy.max_review_age,
                )
            except OverflowError:
                # An age deadline beyond representable datetime values
                # cannot precede the already valid expiry timestamp.
                pass

        deadlines.append(deadline)

        blockers.extend(
            Blocker(name, reason)
            for reason in reasons
        )

    decision = Decision(
        scope=scope,
        assessed_at=now,
        blockers=tuple(blockers),
        next_review_at=(
            min(deadlines)
            if not blockers
            else None
        ),
    )

    if logger is not None:
        logger.info(
            "Assurance assessment: ready=%s records=%d blockers=%d",
            decision.ready,
            len(records),
            len(blockers),
        )

    return decision


class AssuranceTests(unittest.TestCase):
    """Synthetic fixtures are not operational evidence."""

    def setUp(self) -> None:
        self.now = datetime(
            2030,
            1,
            1,
            tzinfo=timezone.utc,
        )

        self.scope = Scope(
            "test-build",
            "test-config",
            "test-architecture",
        )

        self.records = tuple(
            Evidence(
                obligation=name,
                scope=self.scope,
                passed=True,
                reviewed_at=(
                    self.now - timedelta(days=1)
                ),
                expires_at=(
                    self.now + timedelta(days=1)
                ),
                owner="test-owner",
                reference="test-reference",
            )
            for name in sorted(OBLIGATIONS)
        )

    def test_ready_and_order_independent(self) -> None:
        decision = assess(
            self.scope,
            self.records,
            self.now,
        )

        self.assertTrue(
            decision.ready
        )

        self.assertEqual(
            decision.next_review_at,
            self.now + timedelta(days=1),
        )

        self.assertEqual(
            decision,
            assess(
                self.scope,
                self.records[::-1],
                self.now,
            ),
        )

    def test_every_missing_record_blocks(self) -> None:
        for index in range(len(self.records)):
            remaining = (
                self.records[:index]
                + self.records[index + 1:]
            )

            self.assertFalse(
                assess(
                    self.scope,
                    remaining,
                    self.now,
                ).ready
            )

    def test_independent_failures(self) -> None:
        changes_to_test = (
            {"passed": False},
            {"invalidated": True},
            {
                "scope": replace(
                    self.scope,
                    build="changed",
                )
            },
            {
                "scope": replace(
                    self.scope,
                    configuration="changed",
                )
            },
            {
                "scope": replace(
                    self.scope,
                    architecture="changed",
                )
            },
            {"expires_at": self.now},
            {
                "reviewed_at": (
                    self.now + timedelta(hours=1)
                )
            },
        )

        for changes in changes_to_test:
            with self.subTest(changes=changes):
                records = (
                    replace(
                        self.records[0],
                        **changes,
                    ),
                ) + self.records[1:]

                self.assertFalse(
                    assess(
                        self.scope,
                        records,
                        self.now,
                    ).ready
                )

    def test_temporal_boundaries(self) -> None:
        self.assertTrue(
            assess(
                self.scope,
                self.records,
                self.records[0].reviewed_at,
            ).ready
        )

        policy = Policy(
            max_review_age=timedelta(days=1)
        )

        self.assertFalse(
            assess(
                self.scope,
                self.records,
                self.now,
                policy=policy,
            ).ready
        )

        offset_now = self.now.astimezone(
            timezone(timedelta(hours=5))
        )

        self.assertEqual(
            assess(
                self.scope,
                self.records,
                self.now,
            ),
            assess(
                self.scope,
                self.records,
                offset_now,
            ),
        )

    def test_invalid_inputs(self) -> None:
        calls = (
            lambda: Scope(
                "",
                "config",
                "architecture",
            ),
            lambda: replace(
                self.records[0],
                scope=None,
            ),
            lambda: replace(
                self.records[0],
                passed=1,
            ),
            lambda: replace(
                self.records[0],
                expires_at=self.records[0].reviewed_at,
            ),
            lambda: replace(
                self.records[0],
                obligation=[],
            ),
            lambda: assess(
                self.scope,
                list(self.records),
                self.now,
            ),
            lambda: assess(
                self.scope,
                self.records,
                self.now.replace(tzinfo=None),
            ),
            lambda: assess(
                self.scope,
                self.records + self.records[:1],
                self.now,
            ),
            lambda: assess(
                self.scope,
                (
                    replace(
                        self.records[0],
                        obligation="unknown",
                    ),
                ),
                self.now,
            ),
            lambda: Policy(
                required=frozenset()
            ),
            lambda: Policy(
                max_review_age=timedelta(0)
            ),
            lambda: assess(
                self.scope,
                self.records * 101,
                self.now,
            ),
        )

        for call in calls:
            with self.assertRaises(ContractError):
                call()

    def test_extra_obligations_cannot_be_skipped(self) -> None:
        policy = Policy(
            required=(
                OBLIGATIONS | {"independent_review"}
            )
        )

        decision = assess(
            self.scope,
            self.records,
            self.now,
            policy=policy,
        )

        self.assertIn(
            "independent_review:missing",
            decision.blocker_messages,
        )

        extra = replace(
            self.records[0],
            obligation="independent_review",
        )

        self.assertTrue(
            assess(
                self.scope,
                self.records + (extra,),
                self.now,
                policy=policy,
            ).ready
        )

    def test_logging_is_aggregate_only(self) -> None:
        logger = logging.getLogger(
            "hearthline.assurance.tests"
        )

        with self.assertLogs(
            logger,
            level="INFO",
        ) as captured:
            assess(
                self.scope,
                self.records,
                self.now,
                logger=logger,
            )

        output = " ".join(captured.output)

        self.assertNotIn(
            "test-owner",
            output,
        )
        self.assertNotIn(
            "test-reference",
            output,
        )
        self.assertNotIn(
            "test-build",
            output,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic conformance tests",
    )

    args = parser.parse_args(argv)

    if not args.self_test:
        parser.print_help()
        return 0

    print(
        f"Python {sys.version.split()[0]}; "
        f"runner=unittest; API={API_VERSION}"
    )

    suite = (
        unittest.defaultTestLoader
        .loadTestsFromTestCase(AssuranceTests)
    )

    result = unittest.TextTestRunner(
        verbosity=2
    ).run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
