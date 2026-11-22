# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded propagation of supplied protected-source labels.

Run directly with Python 3.12+ to execute synthetic tests.

This component checks declared lineage only. It does not inspect code,
discover stores, authenticate metadata, or prove lineage completeness.

Every listed source is prohibited at every listed sink under this
reference policy. No permitted-use decision is returned.

A shared dependency may be visited more than once. The visit budget
bounds traversal work and pending expansion, not caller allocations.
"""

from dataclasses import dataclass
from enum import Enum
import unittest


class LineageError(ValueError):
    """Malformed declared-lineage input."""


class ResourceLimitError(LineageError):
    """Declared lineage exceeds the traversal budget."""


class Source(Enum):
    REFLECTION = "reflection"
    RESEARCH_RESPONSE = "research_response"
    PRACTICE_CONTENT = "practice_content"
    SCOPED_ATTESTATION = "scoped_attestation"


class Sink(Enum):
    DISCOVERY_RANKING = "discovery_ranking"
    ADVERTISING = "advertising"
    MEMBER_SCORING = "member_scoring"


@dataclass(frozen=True, slots=True)
class Node:
    sources: frozenset[Source] = frozenset()
    inputs: tuple["Node", ...] = ()

    def __post_init__(self):
        if (
            type(self.sources) is not frozenset
            or any(
                type(value) is not Source
                for value in self.sources
            )
        ):
            raise LineageError(
                "explicit immutable source labels required"
            )

        if (
            type(self.inputs) is not tuple
            or any(
                type(value) is not Node
                for value in self.inputs
            )
        ):
            raise LineageError(
                "immutable validated lineage inputs required"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    sink: Sink
    prohibited_sources: frozenset[Source]


def audit_lineage(
    root: Node,
    sink: Sink,
    *,
    max_visits: int = 1000,
) -> Finding:
    """Report protected-source ancestry for one declared consumer.

    Exceptions produce no completed audit finding. Empty labels mean
    only that no protected ancestry was declared in this input.
    """
    if (
        type(root) is not Node
        or type(sink) is not Sink
    ):
        raise LineageError(
            "validated lineage and prohibited sink required"
        )

    if (
        type(max_visits) is not int
        or max_visits <= 0
    ):
        raise LineageError(
            "positive visit budget required"
        )

    pending = [root]
    visits = 0
    sources = set()

    while pending:
        node = pending.pop()
        visits += 1

        if visits > max_visits:
            raise ResourceLimitError(
                "lineage visit budget exceeded"
            )

        sources.update(node.sources)

        if (
            visits
            + len(pending)
            + len(node.inputs)
            > max_visits
        ):
            raise ResourceLimitError(
                "lineage visit budget exceeded"
            )

        pending.extend(node.inputs)

    return Finding(
        sink=sink,
        prohibited_sources=frozenset(sources),
    )


class LineageTests(unittest.TestCase):
    """Synthetic graphs test propagation, not actual pipeline coverage."""

    def test_renamed_derived_input_remains_prohibited(self):
        source = Node(
            frozenset({
                Source.REFLECTION,
            })
        )
        transformed = Node(
            inputs=(
                Node(inputs=(source,)),
            )
        )

        result = audit_lineage(
            transformed,
            Sink.DISCOVERY_RANKING,
        )

        self.assertEqual(
            result.prohibited_sources,
            frozenset({
                Source.REFLECTION,
            }),
        )

    def test_single_source_is_enough(self):
        for source in Source:
            for sink in Sink:
                self.assertIn(
                    source,
                    audit_lineage(
                        Node(frozenset({source})),
                        sink,
                    ).prohibited_sources,
                )

    def test_empty_labels_are_not_proof_of_complete_lineage(self):
        self.assertEqual(
            audit_lineage(
                Node(),
                Sink.ADVERTISING,
            ).prohibited_sources,
            frozenset(),
        )

    def test_budget_and_invalid(self):
        leaf = Node()

        with self.assertRaises(ResourceLimitError):
            audit_lineage(
                Node(inputs=(leaf, leaf)),
                Sink.MEMBER_SCORING,
                max_visits=2,
            )

        with self.assertRaises(LineageError):
            Node(
                sources={
                    Source.REFLECTION,
                }
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
