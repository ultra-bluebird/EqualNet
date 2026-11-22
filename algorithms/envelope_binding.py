# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exact action-scope comparison for connection proposals.

Run directly with Python 3.12+ to execute synthetic tests.

This component does not authorize actions, publish changes, mutate
permissions, or process private workspace history.

The integration must construct a complete reviewed scope. Values are
explicit strings; interpretation belongs to the reviewed semantics
contract. No implicit normalization is performed.
"""

from dataclasses import dataclass, replace
import unittest


class BindingError(ValueError):
    """Malformed action-scope input."""


def require_text(value):
    if type(value) is not str or not value.strip():
        raise BindingError(
            "nonempty built-in text required"
        )


@dataclass(frozen=True, slots=True)
class ReviewedScope:
    action: str
    recipient_scope: tuple[str, ...]
    disclosures: tuple[tuple[str, str], ...]
    conditions: tuple[tuple[str, str], ...]
    semantics_version: str

    def __post_init__(self):
        require_text(self.action)
        require_text(self.semantics_version)

        if type(self.recipient_scope) is not tuple:
            raise BindingError(
                "immutable recipient scope required"
            )

        for value in self.recipient_scope:
            require_text(value)

        if (
            len(set(self.recipient_scope))
            != len(self.recipient_scope)
        ):
            raise BindingError(
                "duplicate recipient scope entries"
            )

        for pairs in (
            self.disclosures,
            self.conditions,
        ):
            if type(pairs) is not tuple:
                raise BindingError(
                    "immutable field-value pairs required"
                )

            keys = set()

            for pair in pairs:
                if (
                    type(pair) is not tuple
                    or len(pair) != 2
                ):
                    raise BindingError(
                        "field-value pair required"
                    )

                key, value = pair
                require_text(key)

                if type(value) is not str:
                    raise BindingError(
                        "values must be explicit strings"
                    )

                if key in keys:
                    raise BindingError(
                        "duplicate field"
                    )

                keys.add(key)


def requires_reapproval(
    reviewed: ReviewedScope,
    proposed: ReviewedScope,
) -> bool:
    """Return whether the exact reviewed scope changed.

    A false result does not establish current authorization.
    A true result performs no invalidation or notification.
    """
    if (
        type(reviewed) is not ReviewedScope
        or type(proposed) is not ReviewedScope
    ):
        raise BindingError(
            "validated reviewed scopes required"
        )

    return reviewed != proposed


class BindingTests(unittest.TestCase):
    """Synthetic scope labels do not represent actual members."""

    def setUp(self):
        self.scope = ReviewedScope(
            action="text_invitation",
            recipient_scope=("synthetic-recipient",),
            disclosures=(
                ("activity", "remote discussion"),
            ),
            conditions=(
                ("duration", "30 minutes"),
                ("recording", "not permitted"),
            ),
            semantics_version="reviewed-text-v1",
        )

    def test_identical_scope(self):
        self.assertFalse(
            requires_reapproval(
                self.scope,
                replace(self.scope),
            )
        )

    def test_every_scope_component(self):
        changes = (
            {"action": "call_invitation"},
            {
                "recipient_scope": (
                    "different-synthetic-recipient",
                )
            },
            {
                "disclosures": (
                    ("activity", "public discussion"),
                )
            },
            {
                "conditions": (
                    ("duration", "60 minutes"),
                    ("recording", "not permitted"),
                )
            },
            {
                "semantics_version":
                    "reviewed-text-v2"
            },
        )

        for change in changes:
            self.assertTrue(
                requires_reapproval(
                    self.scope,
                    replace(self.scope, **change),
                )
            )

    def test_removal_and_order_changes_require_review(self):
        self.assertTrue(
            requires_reapproval(
                self.scope,
                replace(
                    self.scope,
                    disclosures=(),
                ),
            )
        )

        self.assertTrue(
            requires_reapproval(
                self.scope,
                replace(
                    self.scope,
                    conditions=self.scope.conditions[::-1],
                ),
            )
        )

    def test_invalid(self):
        changes = (
            {"action": " "},
            {"recipient_scope": []},
            {
                "conditions": (
                    ("cost", "free"),
                    ("cost", "paid"),
                )
            },
        )

        for change in changes:
            with self.assertRaises(BindingError):
                replace(self.scope, **change)

        with self.assertRaises(BindingError):
            requires_reapproval(
                self.scope,
                None,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
