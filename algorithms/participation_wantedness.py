# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exact aggregate wantedness reporting for Python 3.12+.

Run --self-test or --counts INVITED SUBMITTED ANSWERED WANTED.
Optional --missing-wanted accepts an exact fraction such as 1/2.

Units must share one eligible survey cohort, binary question, and window.
The outcome must be defined for every unit. Unknown and inapplicable
answers must not be silently coded as unwanted.

Bounds concern missing outcomes within that cohort, not confidence
intervals. Sensitivity values are assumptions, not inferred responses.
The core has no logging, I/O, clock, persistence, or ranking capability.
CLI output is administrative aggregate data requiring disclosure review.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from fractions import Fraction
import platform
import unittest


__all__ = [
    "MeasurementError",
    "CountError",
    "ScenarioError",
    "Wantedness",
    "main",
]


class MeasurementError(ValueError):
    """Base measurement contract error."""


class CountError(MeasurementError):
    """Malformed counts or inconsistent cohort partition."""


class ScenarioError(MeasurementError):
    """Malformed sensitivity assumption."""


def _probability(value: object) -> None:
    if type(value) is not Fraction or not 0 <= value <= 1:
        raise ScenarioError(
            "scenario must be a Fraction between zero and one"
        )


def _ratio(
    numerator: int,
    denominator: int,
) -> Fraction | None:
    return (
        Fraction(numerator, denominator)
        if denominator
        else None
    )


@dataclass(frozen=True, slots=True)
class Wantedness:
    invited: int
    submitted: int
    answered: int
    wanted: int

    def __post_init__(self) -> None:
        values = (
            self.invited,
            self.submitted,
            self.answered,
            self.wanted,
        )

        if any(
            type(value) is not int or value < 0
            for value in values
        ):
            raise CountError(
                "counts must be nonnegative built-in integers"
            )

        if not (
            self.wanted
            <= self.answered
            <= self.submitted
            <= self.invited
        ):
            raise CountError(
                "require wanted <= answered <= submitted <= invited"
            )

    @property
    def respondent_fraction(self) -> Fraction | None:
        return _ratio(
            self.wanted,
            self.answered,
        )

    @property
    def item_response_fraction(self) -> Fraction | None:
        return _ratio(
            self.answered,
            self.invited,
        )

    @property
    def survey_response_fraction(self) -> Fraction | None:
        return _ratio(
            self.submitted,
            self.invited,
        )

    @property
    def missing_item_count(self) -> int:
        return self.submitted - self.answered

    @property
    def no_submission_count(self) -> int:
        return self.invited - self.submitted

    @property
    def missing_outcome_count(self) -> int:
        return self.invited - self.answered

    @property
    def observed_unwanted_count(self) -> int:
        """Explicit binary negative answers, not missing responses."""
        return self.answered - self.wanted

    @property
    def bounds(self) -> tuple[Fraction, Fraction] | None:
        if not self.invited:
            return None

        return (
            Fraction(
                self.wanted,
                self.invited,
            ),
            Fraction(
                self.wanted + self.missing_outcome_count,
                self.invited,
            ),
        )

    def sensitivity(
        self,
        missing_wanted_fraction: Fraction,
    ) -> Fraction | None:
        _probability(missing_wanted_fraction)

        return self.stratified_sensitivity(
            missing_item_fraction=missing_wanted_fraction,
            no_submission_fraction=missing_wanted_fraction,
        )

    def stratified_sensitivity(
        self,
        *,
        missing_item_fraction: Fraction,
        no_submission_fraction: Fraction,
    ) -> Fraction | None:
        """Apply separate assumptions to item and survey nonresponse.

        These assumptions do not identify motives or create individual data.
        Validation applies even to empty cohorts or empty missingness strata.
        """
        _probability(missing_item_fraction)
        _probability(no_submission_fraction)

        if not self.invited:
            return None

        return (
            self.wanted
            + missing_item_fraction * self.missing_item_count
            + no_submission_fraction * self.no_submission_count
        ) / self.invited


def _parse_count(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected a nonnegative integer"
        ) from exc

    if result < 0:
        raise argparse.ArgumentTypeError(
            "expected a nonnegative integer"
        )

    return result


def _parse_probability(value: str) -> Fraction:
    try:
        result = Fraction(value)
        _probability(result)
        return result
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError(
            "expected a fraction between zero and one"
        ) from exc


def _display(value: Fraction | None) -> str:
    return "undefined" if value is None else str(value)


class WantednessTests(unittest.TestCase):
    """Synthetic conformance checks, not evidence of member benefit."""

    def test_original_example(self):
        result = Wantedness(10, 7, 6, 4)

        self.assertEqual(
            result.respondent_fraction,
            Fraction(2, 3),
        )
        self.assertEqual(
            result.item_response_fraction,
            Fraction(3, 5),
        )
        self.assertEqual(
            result.survey_response_fraction,
            Fraction(7, 10),
        )
        self.assertEqual(
            result.bounds,
            (Fraction(2, 5), Fraction(4, 5)),
        )
        self.assertEqual(
            (
                result.missing_item_count,
                result.no_submission_count,
            ),
            (1, 3),
        )

    def test_empty_and_unanswered(self):
        empty = Wantedness(0, 0, 0, 0)

        self.assertIsNone(empty.respondent_fraction)
        self.assertIsNone(empty.bounds)
        self.assertIsNone(
            empty.sensitivity(Fraction(1, 2))
        )

        unanswered = Wantedness(10, 0, 0, 0)

        self.assertEqual(
            unanswered.bounds,
            (Fraction(0), Fraction(1)),
        )
        self.assertIsNone(
            unanswered.respondent_fraction
        )

    def test_stratified_assumptions(self):
        result = Wantedness(10, 7, 6, 4)

        self.assertEqual(
            result.sensitivity(Fraction(1, 2)),
            Fraction(3, 5),
        )
        self.assertEqual(
            result.stratified_sensitivity(
                missing_item_fraction=Fraction(1),
                no_submission_fraction=Fraction(0),
            ),
            Fraction(1, 2),
        )

    def test_bounded_conformance(self):
        checked = 0

        for invited in range(6):
            for submitted in range(invited + 1):
                for answered in range(submitted + 1):
                    for wanted in range(answered + 1):
                        result = Wantedness(
                            invited,
                            submitted,
                            answered,
                            wanted,
                        )

                        self.assertEqual(
                            result.answered
                            + result.missing_item_count
                            + result.no_submission_count,
                            invited,
                        )

                        if invited:
                            low, high = result.bounds

                            self.assertEqual(
                                result.sensitivity(Fraction(0)),
                                low,
                            )
                            self.assertEqual(
                                result.sensitivity(Fraction(1)),
                                high,
                            )

                            values = [
                                result.sensitivity(Fraction(p, 4))
                                for p in range(5)
                            ]

                            self.assertEqual(
                                values,
                                sorted(values),
                            )
                            self.assertTrue(
                                all(
                                    low <= value <= high
                                    for value in values
                                )
                            )

                        checked += 1

        self.assertEqual(checked, 126)

    def test_immutability_and_invalid_counts(self):
        from dataclasses import FrozenInstanceError

        result = Wantedness(10, 7, 6, 4)

        with self.assertRaises(FrozenInstanceError):
            result.wanted = 0

        for field in (
            "invited",
            "submitted",
            "answered",
            "wanted",
        ):
            for value in (
                True,
                -1,
                1.5,
                "1",
                None,
            ):
                with self.assertRaises(CountError):
                    replace(
                        result,
                        **{field: value},
                    )

        for values in (
            (1, 2, 1, 1),
            (5, 4, 5, 3),
            (5, 4, 3, 4),
        ):
            with self.assertRaises(CountError):
                Wantedness(*values)

    def test_invalid_scenarios(self):
        for value in (
            True,
            0.5,
            Fraction(-1),
            Fraction(2),
            None,
        ):
            with self.assertRaises(ScenarioError):
                Wantedness(
                    0, 0, 0, 0
                ).sensitivity(value)

    def test_parsers(self):
        self.assertEqual(
            _parse_count("2"),
            2,
        )
        self.assertEqual(
            _parse_probability("0.5"),
            Fraction(1, 2),
        )

        for value in ("-1", "x", "1.5"):
            with self.assertRaises(
                argparse.ArgumentTypeError
            ):
                _parse_count(value)

        for value in ("-1", "2", "1/0", "nan"):
            with self.assertRaises(
                argparse.ArgumentTypeError
            ):
                _parse_probability(value)


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
        "--counts",
        nargs=4,
        type=_parse_count,
        metavar=(
            "INVITED",
            "SUBMITTED",
            "ANSWERED",
            "WANTED",
        ),
    )

    parser.add_argument(
        "--missing-wanted",
        type=_parse_probability,
        default=None,
    )

    args = parser.parse_args(argv)

    if (
        args.missing_wanted is not None
        and args.counts is None
    ):
        parser.error(
            "--missing-wanted requires --counts"
        )

    if args.self_test:
        print(
            f"Python {platform.python_version()}; "
            "runner=unittest",
            flush=True,
        )

        suite = (
            unittest.defaultTestLoader
            .loadTestsFromTestCase(WantednessTests)
        )
        result = unittest.TextTestRunner(
            verbosity=2
        ).run(suite)

        return 0 if result.wasSuccessful() else 1

    if args.counts is None:
        parser.print_help()
        return 0

    try:
        result = Wantedness(*args.counts)
    except MeasurementError as exc:
        parser.error(str(exc))

    print(
        "respondent_fraction="
        f"{_display(result.respondent_fraction)}"
    )
    print(
        "survey_response_fraction="
        f"{_display(result.survey_response_fraction)}"
    )
    print(
        "item_response_fraction="
        f"{_display(result.item_response_fraction)}"
    )
    print(
        f"missing_items={result.missing_item_count}; "
        f"no_submission={result.no_submission_count}"
    )

    if result.bounds is None:
        print("cohort_bounds=undefined")
    else:
        print(
            f"cohort_bounds=[{result.bounds[0]}, "
            f"{result.bounds[1]}]"
        )

    if args.missing_wanted is not None:
        print(
            "scenario_fraction="
            f"{_display(result.sensitivity(args.missing_wanted))}"
        )

    print(
        "Descriptive aggregates only; "
        "not a member score or confidence interval."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
