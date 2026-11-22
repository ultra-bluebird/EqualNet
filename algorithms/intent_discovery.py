# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reference model for private intent edits and introduction eligibility.

Run directly to execute the included synthetic model tests.

This module does not implement authentication, authorization, delivery,
persistence, or production cache auditing.
"""

from dataclasses import dataclass, replace
from enum import Enum
from itertools import product
import unittest


# Document credit only; not identity, consent, or execution authority.
ATTRIBUTION = "bostrom18sd2ujv24ual9c9pshtxys6j8knh6xaead9ye7"

INTENTS = frozenset({
    "conversation",
    "friendship",
    "dating",
    "romance",
    "intimacy",
    "activities",
})


@dataclass(frozen=True)
class IntentState:
    selected: frozenset[str] = frozenset()
    revision: int = 0

    def __post_init__(self):
        if not isinstance(self.selected, frozenset):
            raise TypeError("selected must be a frozenset")
        if not self.selected <= INTENTS:
            raise ValueError("unknown intention")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be a nonnegative integer")


@dataclass(frozen=True)
class SurfaceState:
    """Immutable observable-state fixtures, not authorization records."""

    disclosed: frozenset[str] = frozenset()
    notifications: tuple[str, ...] = ()
    discovery_index: tuple[str, ...] = ()
    ranking_cache: tuple[str, ...] = ()


@dataclass(frozen=True)
class Model:
    private: IntentState = IntentState()
    surfaces: SurfaceState = SurfaceState()


def edit_private(model: Model, selected: frozenset[str]) -> Model:
    """Change private selections without changing modeled public surfaces."""
    updated = IntentState(selected, model.private.revision + 1)
    return replace(model, private=updated)


class Match(Enum):
    NO = 0
    YES = 1
    UNKNOWN = 2


class MissingPolicy(Enum):
    EXCLUDE = "exclude"
    ASK_PRIVATELY = "ask_privately"


class Eligibility(Enum):
    EXCLUDED = "excluded"
    NEEDS_CLARIFICATION = "needs_clarification"
    ELIGIBLE = "eligible"


def eligibility(
    uv: Match,
    vu: Match,
    restrictions_allow: bool,
    policy: MissingPolicy,
) -> Eligibility:
    """Evaluate introduction eligibility without performing any action.

    Inputs are criterion-evaluation results, not raw profile attributes.
    An absent criterion imposes no constraint and is evaluated upstream as YES.
    UNKNOWN means a selected criterion cannot currently be evaluated.
    ASK_PRIVATELY returns a state; it does not contact either participant.
    """
    if not isinstance(uv, Match) or not isinstance(vu, Match):
        raise TypeError("criteria must use Match")
    if type(restrictions_allow) is not bool:
        raise TypeError("restrictions_allow must be boolean")
    if not isinstance(policy, MissingPolicy):
        raise TypeError("missing policy required")

    if not restrictions_allow or Match.NO in (uv, vu):
        return Eligibility.EXCLUDED

    if Match.UNKNOWN in (uv, vu):
        if policy is MissingPolicy.ASK_PRIVATELY:
            return Eligibility.NEEDS_CLARIFICATION
        return Eligibility.EXCLUDED

    return Eligibility.ELIGIBLE


class ModelTests(unittest.TestCase):
    def test_all_private_subsets_leave_surfaces_unchanged(self):
        names = sorted(INTENTS)
        base = Model()

        for bits in product((False, True), repeat=len(names)):
            selected = frozenset(
                name for name, bit in zip(names, bits) if bit
            )
            updated = edit_private(base, selected)

            self.assertEqual(updated.private.selected, selected)
            self.assertIs(updated.surfaces, base.surfaces)
            self.assertEqual(base.private, IntentState())

    def test_edit_preserves_previously_disclosed_snapshot(self):
        base = Model(
            IntentState(frozenset({"friendship"})),
            SurfaceState(disclosed=frozenset({"friendship"})),
        )

        updated = edit_private(base, frozenset())

        self.assertEqual(updated.surfaces, base.surfaces)
        self.assertEqual(updated.private.revision, 1)

    def test_all_eligibility_combinations(self):
        combinations = product(
            Match,
            Match,
            (False, True),
            MissingPolicy,
        )

        for uv, vu, allowed, policy in combinations:
            result = eligibility(uv, vu, allowed, policy)

            if not allowed or Match.NO in (uv, vu):
                expected = Eligibility.EXCLUDED
            elif Match.UNKNOWN in (uv, vu):
                expected = (
                    Eligibility.NEEDS_CLARIFICATION
                    if policy is MissingPolicy.ASK_PRIVATELY
                    else Eligibility.EXCLUDED
                )
            else:
                expected = Eligibility.ELIGIBLE

            self.assertIs(result, expected)
            self.assertIs(
                result,
                eligibility(vu, uv, allowed, policy),
            )

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            IntentState(frozenset({"inferred_intent"}))

        with self.assertRaises(TypeError):
            IntentState({"friendship"})

        with self.assertRaises(TypeError):
            eligibility(
                Match.YES,
                Match.YES,
                1,
                MissingPolicy.EXCLUDE,
            )

        with self.assertRaises(TypeError):
            eligibility(
                Match.YES,
                Match.YES,
                True,
                None,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
