# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validated administrative options for request-budget evaluation.

Run directly with Python 3.12+ to execute synthetic parser tests.

parse_options() returns options only. It does not assess budgets,
reserve capacity, send contact requests, or emit assessment logs.
ArgumentParser may print help or errors and raise SystemExit.
"""

import argparse
from contextlib import redirect_stderr
from dataclasses import dataclass
from io import StringIO
import unittest


@dataclass(frozen=True, slots=True)
class Options:
    self_test: bool
    budget: tuple[int, ...] | None
    requests: int
    log_summary: bool


def parse_count(value: str) -> int:
    """Parse a nonnegative CLI integer."""
    try:
        result = int(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "expected a nonnegative integer"
        ) from exc

    if result < 0:
        raise argparse.ArgumentTypeError(
            "expected a nonnegative integer"
        )

    return result


def parse_options(
    argv: list[str] | None = None,
) -> Options:
    parser = argparse.ArgumentParser(
        description="Local administrative budget options."
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--self-test",
        action="store_true",
    )
    mode.add_argument(
        "--budget",
        nargs=6,
        type=parse_count,
    )

    parser.add_argument(
        "--requests",
        type=parse_count,
        default=None,
    )
    parser.add_argument(
        "--log-summary",
        action="store_true",
    )

    args = parser.parse_args(argv)

    if args.budget is None and (
        args.requests is not None
        or args.log_summary
    ):
        parser.error(
            "--requests and --log-summary require --budget"
        )

    if args.requests == 0:
        parser.error(
            "--requests must be positive"
        )

    return Options(
        self_test=args.self_test,
        budget=(
            tuple(args.budget)
            if args.budget is not None
            else None
        ),
        requests=(
            1
            if args.requests is None
            else args.requests
        ),
        log_summary=args.log_summary,
    )


class OptionTests(unittest.TestCase):
    """Synthetic argument lists are not operational inputs."""

    def test_defaults(self):
        self.assertEqual(
            parse_options([]),
            Options(False, None, 1, False),
        )
        self.assertTrue(
            parse_options(["--self-test"]).self_test
        )

    def test_explicit_default_requires_budget(self):
        cases = (
            ["--requests", "1"],
            ["--self-test", "--requests", "1"],
            ["--self-test", "--log-summary"],
        )

        for argv in cases:
            with self.subTest(argv=argv):
                with redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        parse_options(argv)

                self.assertEqual(
                    raised.exception.code,
                    2,
                )

    def test_budget_options(self):
        base = [
            "--budget",
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
        ]

        self.assertEqual(
            parse_options(base).budget,
            (0, 1, 2, 3, 4, 5),
        )
        self.assertEqual(
            parse_options(
                base + ["--requests", "2"]
            ).requests,
            2,
        )
        self.assertTrue(
            parse_options(
                base + ["--log-summary"]
            ).log_summary
        )

    def test_invalid_arguments(self):
        cases = (
            [
                "--budget",
                "0", "0", "1", "1", "1", "1",
                "--requests", "0",
            ],
            [
                "--budget",
                "-1", "0", "1", "1", "1", "1",
            ],
            [
                "--self-test",
                "--budget",
                "0", "0", "1", "1", "1", "1",
            ],
        )

        for argv in cases:
            with self.subTest(argv=argv):
                with redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        parse_options(argv)

                self.assertEqual(
                    raised.exception.code,
                    2,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
