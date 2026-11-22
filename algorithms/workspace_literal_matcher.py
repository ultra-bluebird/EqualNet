# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded literal matching over immutable logical records.

Run directly with Python 3.12+ to execute synthetic tests.

Contract:
- Each inner tuple contains ordered transport chunks for one record.
- A marker may span chunks within that record.
- Separate records are never concatenated.
- Empty records and empty input do not establish capture completion.
- Detection says nothing about capture provenance or observation coverage.
- Matching is exact, case-sensitive byte matching only.

No capture collection, logging, networking, persistence, or authorization
is performed. Caller allocations occur outside this module's bounds.
"""

from dataclasses import dataclass, fields
from enum import Enum
import unittest


__all__ = [
    "MatchError",
    "ValidationError",
    "ResourceLimitError",
    "Detection",
    "Limits",
    "literal_match",
]


class MatchError(ValueError):
    """Base literal-matching contract error."""


class ValidationError(MatchError):
    """Malformed matcher input."""


class ResourceLimitError(MatchError):
    """A configured matcher resource limit was exceeded."""


class Detection(Enum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected_in_supplied_records"


@dataclass(frozen=True, slots=True)
class Limits:
    markers: int = 32
    marker_bytes: int = 256
    total_marker_bytes: int = 4096
    records: int = 256
    chunks_per_record: int = 256
    total_chunks: int = 4096
    capture_bytes: int = 1000000

    def __post_init__(self):
        # This class deliberately contains only numeric limit fields.
        for field in fields(Limits):
            value = getattr(self, field.name)

            if type(value) is not int or value <= 0:
                raise ValidationError(
                    "limits must be positive built-in integers"
                )


def literal_match(
    markers: tuple[bytes, ...],
    records: tuple[tuple[bytes, ...], ...],
    *,
    limits: Limits = Limits(),
) -> Detection:
    """Validate the complete input, then scan each record once.

    The function returns no marker values or captured content.

    An exception means no successful scan result was produced.
    NOT_DETECTED is not a statement about unobserved content,
    transformed content, metadata leakage, or privacy compliance.
    """
    if type(limits) is not Limits:
        raise ValidationError(
            "validated limits required"
        )

    if type(markers) is not tuple or not markers:
        raise ValidationError(
            "nonempty immutable marker tuple required"
        )

    if len(markers) > limits.markers:
        raise ResourceLimitError(
            "marker count limit exceeded"
        )

    marker_total = 0

    for marker in markers:
        if type(marker) is not bytes or not marker:
            raise ValidationError(
                "nonempty byte markers required"
            )

        if len(marker) > limits.marker_bytes:
            raise ResourceLimitError(
                "individual marker limit exceeded"
            )

        marker_total += len(marker)

        if marker_total > limits.total_marker_bytes:
            raise ResourceLimitError(
                "total marker byte limit exceeded"
            )

    if type(records) is not tuple:
        raise ValidationError(
            "immutable record tuple required"
        )

    if len(records) > limits.records:
        raise ResourceLimitError(
            "record count limit exceeded"
        )

    chunk_total = 0
    byte_total = 0

    for record in records:
        if type(record) is not tuple:
            raise ValidationError(
                "immutable transport chunks required"
            )

        if len(record) > limits.chunks_per_record:
            raise ResourceLimitError(
                "record chunk limit exceeded"
            )

        chunk_total += len(record)

        if chunk_total > limits.total_chunks:
            raise ResourceLimitError(
                "total chunk limit exceeded"
            )

        for chunk in record:
            if type(chunk) is not bytes:
                raise ValidationError(
                    "byte chunks required"
                )

            byte_total += len(chunk)

            if byte_total > limits.capture_bytes:
                raise ResourceLimitError(
                    "capture byte limit exceeded"
                )

    detected = False

    for record in records:
        data = b"".join(record)

        if any(
            marker in data
            for marker in markers
        ):
            detected = True

        del data

    return (
        Detection.DETECTED
        if detected
        else Detection.NOT_DETECTED
    )


class MatcherTests(unittest.TestCase):
    """Synthetic tests establish matcher behavior only."""

    def test_cross_chunk_not_cross_record(self):
        marker = (b"synthetic private phrase",)

        self.assertIs(
            literal_match(
                marker,
                (
                    (
                        b"synthetic private ",
                        b"phrase",
                    ),
                ),
            ),
            Detection.DETECTED,
        )

        self.assertIs(
            literal_match(
                marker,
                (
                    (b"synthetic private ",),
                    (b"phrase",),
                ),
            ),
            Detection.NOT_DETECTED,
        )

    def test_every_chunk_partition(self):
        data = b"a-marker-z"

        for mask in range(
            1 << (len(data) - 1)
        ):
            chunks = []
            start = 0

            for position in range(1, len(data)):
                if mask & (1 << (position - 1)):
                    chunks.append(
                        data[start:position]
                    )
                    start = position

            chunks.append(data[start:])

            self.assertIs(
                literal_match(
                    (b"marker",),
                    (tuple(chunks),),
                ),
                Detection.DETECTED,
            )

    def test_empty_chunks_are_bounded(self):
        with self.assertRaises(ResourceLimitError):
            literal_match(
                (b"x",),
                ((b"", b"", b""),),
                limits=Limits(
                    chunks_per_record=2,
                ),
            )

    def test_complete_validation_before_detection(self):
        with self.assertRaises(ValidationError):
            literal_match(
                (b"x",),
                (
                    (b"x",),
                    ("invalid",),
                ),
            )

        with self.assertRaises(ResourceLimitError):
            literal_match(
                (b"x",),
                ((b"x", b"too long"),),
                limits=Limits(
                    capture_bytes=1,
                ),
            )

    def test_limits_and_types(self):
        cases = (
            lambda: literal_match(
                (b"a", b"b"),
                (),
                limits=Limits(markers=1),
            ),
            lambda: literal_match(
                (b"long",),
                (),
                limits=Limits(marker_bytes=2),
            ),
            lambda: literal_match(
                (b"ab", b"cd"),
                (),
                limits=Limits(
                    total_marker_bytes=3,
                ),
            ),
            lambda: literal_match(
                (b"x",),
                ((), ()),
                limits=Limits(records=1),
            ),
            lambda: literal_match(
                (b"x",),
                (
                    (b"",),
                    (b"",),
                ),
                limits=Limits(total_chunks=1),
            ),
        )

        for call in cases:
            with self.assertRaises(ResourceLimitError):
                call()

        with self.assertRaises(ValidationError):
            literal_match(
                (b"x",),
                [],
            )

        with self.assertRaises(ValidationError):
            Limits(markers=True)

        self.assertIs(
            literal_match(
                (b"x",),
                (),
            ),
            Detection.NOT_DETECTED,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
