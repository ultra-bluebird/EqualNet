# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private drafting from explicitly selected access requests.

Run directly with Python 3.12+ to execute synthetic tests.

Draft inclusion is not disclosure authorization.
Requests are not verified statements about venues or services.

No diagnosis, message analysis, networking, logging, persistence,
notification, or sending capability is provided.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import product
import unittest


class ComposerError(ValueError):
    """Malformed access-request selections."""


class AccessRequest(Enum):
    QUIET_SETTING = "quiet_setting"
    TEXT_FIRST = "text_first"
    STEP_FREE = "step_free"
    CAPTIONS = "captions"
    REMOTE_OPTION = "remote_option"


PHRASES = (
    (
        AccessRequest.QUIET_SETTING,
        "Please choose a quieter setting.",
    ),
    (
        AccessRequest.TEXT_FIRST,
        "Please use text for initial communication.",
    ),
    (
        AccessRequest.STEP_FREE,
        "Please confirm a step-free route and entrance before planning.",
    ),
    (
        AccessRequest.CAPTIONS,
        "Please confirm captions are available for spoken remote activities.",
    ),
    (
        AccessRequest.REMOTE_OPTION,
        "Please include a remote participation option.",
    ),
)


@dataclass(frozen=True, slots=True)
class Selections:
    private: frozenset[AccessRequest]
    included_in_draft: frozenset[AccessRequest]

    def __post_init__(self):
        for values in (
            self.private,
            self.included_in_draft,
        ):
            if (
                type(values) is not frozenset
                or any(
                    type(value) is not AccessRequest
                    for value in values
                )
            ):
                raise ComposerError(
                    "explicit immutable access requests required"
                )

        if not self.included_in_draft <= self.private:
            raise ComposerError(
                "draft may include only selected requests"
            )


def compose_access_draft(
    selections: Selections,
) -> str:
    """Return private draft text without granting disclosure permission."""
    if type(selections) is not Selections:
        raise ComposerError(
            "validated selections required"
        )

    lines = [
        phrase
        for request, phrase in PHRASES
        if request in selections.included_in_draft
    ]

    if not lines:
        return ""

    return (
        "Requested arrangements; availability is not verified:\n"
        + "\n".join(lines)
    )


class ComposerTests(unittest.TestCase):
    """Synthetic selections are not usability or accessibility evidence."""

    def test_all_private_and_draft_combinations(self):
        requests = tuple(AccessRequest)
        checked = 0

        for assignments in product(
            range(3),
            repeat=len(requests),
        ):
            private = frozenset(
                value
                for value, mode in zip(
                    requests,
                    assignments,
                )
                if mode > 0
            )

            included = frozenset(
                value
                for value, mode in zip(
                    requests,
                    assignments,
                )
                if mode == 2
            )

            self.assertEqual(
                compose_access_draft(
                    Selections(private, included)
                ),
                compose_access_draft(
                    Selections(included, included)
                ),
            )

            checked += 1

        self.assertEqual(checked, 243)

    def test_requests_are_not_verified_claims(self):
        chosen = frozenset({
            AccessRequest.STEP_FREE,
        })

        draft = compose_access_draft(
            Selections(chosen, chosen)
        )

        self.assertIn(
            "availability is not verified",
            draft,
        )
        self.assertIn(
            "Please confirm",
            draft,
        )

    def test_empty_has_no_announcement(self):
        self.assertEqual(
            compose_access_draft(
                Selections(
                    frozenset(AccessRequest),
                    frozenset(),
                )
            ),
            "",
        )

    def test_invalid(self):
        calls = (
            lambda: Selections(
                frozenset(),
                frozenset({
                    AccessRequest.CAPTIONS,
                }),
            ),
            lambda: Selections(
                {AccessRequest.CAPTIONS},
                frozenset(),
            ),
            lambda: Selections(
                frozenset({"diagnosis"}),
                frozenset(),
            ),
        )

        for call in calls:
            with self.assertRaises(ComposerError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
