# SPDX-License-Identifier: MIT OR Apache-2.0
"""Declared-lineage auditing for Python 3.12+.

Run --self-test or --demo. Core functions perform no external I/O.
All protected sources are prohibited at every listed sink.
Unlabelled ancestry does not establish complete or permitted processing.
Traversal counts occurrences, not distinct nodes. Shared inputs are revisited.
Limits bound traversal, not caller allocation or metadata authenticity.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import platform
import sys
from typing import Iterator
import unittest


__all__ = [
    "LineageError",
    "ValidationError",
    "ResourceLimitError",
    "Source",
    "Sink",
    "Node",
    "Finding",
    "AuditReport",
    "audit_lineage",
    "inspect_lineage",
    "main",
]


class LineageError(ValueError):
    """Base declared-lineage contract error."""


class ValidationError(LineageError):
    """Malformed input or result."""


class ResourceLimitError(LineageError):
    """No completed result: traversal exceeded a configured limit."""


class Source(Enum):
    REFLECTION = "reflection"
    RESEARCH_RESPONSE = "research_response"
    PRACTICE_CONTENT = "practice_content"
    SCOPED_ATTESTATION = "scoped_attestation"


class Sink(Enum):
    DISCOVERY_RANKING = "discovery_ranking"
    ADVERTISING = "advertising"
    MEMBER_SCORING = "member_scoring"


def _sources(value: object) -> None:
    if (
        type(value) is not frozenset
        or any(
            type(item) is not Source
            for item in value
        )
    ):
        raise ValidationError(
            "immutable protected-source labels required"
        )


def _integer(
    value: object,
    minimum: int,
    label: str,
) -> None:
    if type(value) is not int or value < minimum:
        raise ValidationError(
            f"{label} must be a built-in integer >= {minimum}"
        )


@dataclass(frozen=True, slots=True)
class Node:
    sources: frozenset[Source] = frozenset()
    inputs: tuple[Node, ...] = ()

    def __post_init__(self) -> None:
        _sources(self.sources)

        if (
            type(self.inputs) is not tuple
            or any(
                type(item) is not Node
                for item in self.inputs
            )
        ):
            raise ValidationError(
                "immutable validated lineage inputs required"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    sink: Sink
    prohibited_sources: frozenset[Source]

    def __post_init__(self) -> None:
        if type(self.sink) is not Sink:
            raise ValidationError(
                "explicit sink required"
            )

        _sources(self.prohibited_sources)


@dataclass(frozen=True, slots=True)
class AuditReport:
    finding: Finding
    occurrences: int
    input_edges: int
    deepest_path: int

    def __post_init__(self) -> None:
        if type(self.finding) is not Finding:
            raise ValidationError(
                "validated finding required"
            )

        _integer(
            self.occurrences,
            1,
            "occurrences",
        )
        _integer(
            self.input_edges,
            0,
            "input_edges",
        )
        _integer(
            self.deepest_path,
            0,
            "deepest_path",
        )

        if self.input_edges != self.occurrences - 1:
            raise ValidationError(
                "expanded occurrence accounting is inconsistent"
            )

        if self.deepest_path > self.input_edges:
            raise ValidationError(
                "path depth exceeds expanded edge count"
            )


def inspect_lineage(
    root: Node,
    sink: Sink,
    *,
    max_visits: int = 1000,
    max_depth: int | None = None,
    max_inputs: int | None = None,
) -> AuditReport:
    """Audit supplied ancestry without recursion or node hashing.

    The root has depth zero. Optional depth and fan-out limits are inclusive.
    Scheduling counts every input occurrence, including shared dependencies.
    Limits never produce partial findings or a successful fallback.
    """
    if type(root) is not Node or type(sink) is not Sink:
        raise ValidationError(
            "validated root and sink required"
        )

    _integer(
        max_visits,
        1,
        "max_visits",
    )

    for value, name in (
        (max_depth, "max_depth"),
        (max_inputs, "max_inputs"),
    ):
        if value is not None:
            _integer(
                value,
                0,
                name,
            )

    stack: list[tuple[Iterator[Node], int]] = [
        (iter((root,)), 0)
    ]

    scheduled = 1
    visited = 0
    deepest = 0
    protected: set[Source] = set()

    while stack:
        iterator, depth = stack[-1]

        try:
            node = next(iterator)
        except StopIteration:
            stack.pop()
            continue

        if (
            max_depth is not None
            and depth > max_depth
        ):
            raise ResourceLimitError(
                "depth limit exceeded"
            )

        if (
            max_inputs is not None
            and len(node.inputs) > max_inputs
        ):
            raise ResourceLimitError(
                "input fan-out limit exceeded"
            )

        scheduled += len(node.inputs)

        if scheduled > max_visits:
            raise ResourceLimitError(
                "occurrence budget exceeded"
            )

        visited += 1
        deepest = max(deepest, depth)
        protected.update(node.sources)

        if node.inputs:
            stack.append(
                (
                    iter(node.inputs),
                    depth + 1,
                )
            )

    return AuditReport(
        finding=Finding(
            sink,
            frozenset(protected),
        ),
        occurrences=visited,
        input_edges=scheduled - 1,
        deepest_path=deepest,
    )


def audit_lineage(
    root: Node,
    sink: Sink,
    *,
    max_visits: int = 1000,
) -> Finding:
    """Compatibility API: return a finding, never a permitted-use decision."""
    return inspect_lineage(
        root,
        sink,
        max_visits=max_visits,
    ).finding


class LineageTests(unittest.TestCase):
    """Synthetic fixtures do not establish production pipeline coverage."""

    def test_every_source_sink(self):
        for source in Source:
            for sink in Sink:
                result = audit_lineage(
                    Node(frozenset({source})),
                    sink,
                )

                self.assertEqual(
                    result,
                    Finding(
                        sink,
                        frozenset({source}),
                    ),
                )

    def test_transformation_propagation(self):
        leaf = Node(
            frozenset({
                Source.REFLECTION,
            })
        )
        root = Node(
            inputs=(
                Node(inputs=(leaf,)),
            )
        )

        self.assertEqual(
            audit_lineage(
                root,
                Sink.ADVERTISING,
            ).prohibited_sources,
            leaf.sources,
        )

    def test_shared_occurrences_and_exact_budget(self):
        leaf = Node()
        root = Node(
            inputs=(leaf, leaf)
        )

        report = inspect_lineage(
            root,
            Sink.MEMBER_SCORING,
            max_visits=3,
        )

        self.assertEqual(
            (
                report.occurrences,
                report.input_edges,
                report.deepest_path,
            ),
            (3, 2, 1),
        )

        with self.assertRaises(ResourceLimitError):
            audit_lineage(
                root,
                Sink.MEMBER_SCORING,
                max_visits=2,
            )

    def test_deep_without_recursion(self):
        root = Node(
            frozenset({
                Source.PRACTICE_CONTENT,
            })
        )

        for _ in range(1500):
            root = Node(inputs=(root,))

        report = inspect_lineage(
            root,
            Sink.DISCOVERY_RANKING,
            max_visits=1501,
        )

        self.assertEqual(
            report.deepest_path,
            1500,
        )
        self.assertIn(
            Source.PRACTICE_CONTENT,
            report.finding.prohibited_sources,
        )

    def test_optional_limits(self):
        leaf = Node()
        root = Node(
            inputs=(leaf, leaf)
        )

        with self.assertRaises(ResourceLimitError):
            inspect_lineage(
                root,
                Sink.ADVERTISING,
                max_depth=0,
            )

        with self.assertRaises(ResourceLimitError):
            inspect_lineage(
                root,
                Sink.ADVERTISING,
                max_inputs=1,
            )

        self.assertEqual(
            inspect_lineage(
                leaf,
                Sink.ADVERTISING,
                max_depth=0,
                max_inputs=0,
            ).occurrences,
            1,
        )

    def test_empty_labels(self):
        result = audit_lineage(
            Node(),
            Sink.ADVERTISING,
        )

        self.assertEqual(
            result.prohibited_sources,
            frozenset(),
        )

    def test_invalid_inputs(self):
        calls = (
            lambda: Node(
                sources={
                    Source.REFLECTION,
                }
            ),
            lambda: Node(
                inputs=[]
            ),
            lambda: Node(
                inputs=(None,)
            ),
            lambda: Finding(
                "advertising",
                frozenset(),
            ),
            lambda: audit_lineage(
                None,
                Sink.ADVERTISING,
            ),
            lambda: audit_lineage(
                Node(),
                Sink.ADVERTISING,
                max_visits=True,
            ),
            lambda: inspect_lineage(
                Node(),
                Sink.ADVERTISING,
                max_depth=-1,
            ),
            lambda: AuditReport(
                Finding(
                    Sink.ADVERTISING,
                    frozenset(),
                ),
                2,
                0,
                0,
            ),
        )

        for call in calls:
            with self.assertRaises(ValidationError):
                call()

    def test_input_order_does_not_change_finding(self):
        left = Node(
            frozenset({
                Source.REFLECTION,
            })
        )
        right = Node(
            frozenset({
                Source.RESEARCH_RESPONSE,
            })
        )

        self.assertEqual(
            audit_lineage(
                Node(inputs=(left, right)),
                Sink.ADVERTISING,
            ),
            audit_lineage(
                Node(inputs=(right, left)),
                Sink.ADVERTISING,
            ),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--self-test",
        action="store_true",
    )
    mode.add_argument(
        "--demo",
        action="store_true",
    )

    parser.add_argument(
        "--log-summary",
        action="store_true",
        help=(
            "demo only: write aggregate traversal counts to stderr"
        ),
    )

    args = parser.parse_args(argv)

    if args.log_summary and not args.demo:
        parser.error(
            "--log-summary requires --demo"
        )

    if args.self_test:
        print(
            f"Python {platform.python_version()}; "
            "runner=unittest",
            flush=True,
        )

        suite = (
            unittest.defaultTestLoader
            .loadTestsFromTestCase(LineageTests)
        )
        result = unittest.TextTestRunner(
            verbosity=2
        ).run(suite)

        return 0 if result.wasSuccessful() else 1

    if args.demo:
        leaf = Node(
            frozenset({
                Source.REFLECTION,
            })
        )

        report = inspect_lineage(
            Node(inputs=(leaf,)),
            Sink.DISCOVERY_RANKING,
        )

        print(
            "Synthetic declared-lineage finding; "
            "not production evidence."
        )
        print(
            "prohibited_source_detected="
            + str(
                bool(
                    report.finding.prohibited_sources
                )
            )
        )
        print(
            "Unlabelled or missing lineage "
            "cannot establish permitted use."
        )

        if args.log_summary:
            print(
                f"occurrences={report.occurrences}; "
                f"input_edges={report.input_edges}; "
                f"deepest_path={report.deepest_path}",
                file=sys.stderr,
            )

        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
