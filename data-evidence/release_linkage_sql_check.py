# SPDX-License-Identifier: MIT OR Apache-2.0
"""Runs release_linkage_synthetic.sql on an in-memory SQLite database with a tiny
synthetic fixture and compares the views with an independent Python oracle."""
import pathlib
import sqlite3
import unittest

SQL_PATH = pathlib.Path(__file__).with_name("release_linkage_synthetic.sql")
RUNS = {"r1": [10, 10, 11, 11, 11, 12, 12, 12], "r2": [4, 5, 5, 5]}
EVENTS = [("r1", 2)]
POLICIES = [("identity", 1, 0, 1), ("grid5", 5, 0, 1),
            ("window3", 1, 0, 3), ("suppress11", 1, 11, 1)]


def connect():
    con = sqlite3.connect(":memory:")
    con.executescript(SQL_PATH.read_text(encoding="utf-8"))
    con.executemany("INSERT INTO policy VALUES (?, ?, ?, ?)", POLICIES)
    for run, occupancy in RUNS.items():
        con.executemany("INSERT INTO synthetic_occupancy (run_id, step, occupancy) VALUES (?, ?, ?)",
                        [(run, i, o) for i, o in enumerate(occupancy)])
    con.executemany("INSERT INTO synthetic_target_event VALUES (?, ?)", EVENTS)
    return con


def oracle():
    summary, error = {}, {}
    for pid, rounding, below, window in POLICIES:
        tp = fp = fn = tn = releases = suppressed = 0
        total_error = kept = 0
        for run, occupancy in RUNS.items():
            previous = None
            for step, occ in enumerate(occupancy):
                if step % window:
                    continue
                value = None if occ < below else ((2 * occ + rounding) // (2 * rounding)) * rounding
                releases += 1
                if value is None:
                    suppressed += 1
                else:
                    kept += 1
                    total_error += abs(value - occ)
                if previous is not None:
                    pstep, pvalue = previous
                    guessed = value is not None and pvalue is not None and value - pvalue == rounding
                    actual = any(r == run and pstep < s <= step for r, s in EVENTS)
                    tp += guessed and actual
                    fp += guessed and not actual
                    fn += (not guessed) and actual
                    tn += (not guessed) and not actual
                previous = (step, value)
        summary[pid] = (tp, fp, fn, tn)
        error[pid] = (releases, suppressed, total_error / kept if kept else None)
    return summary, error


class Tests(unittest.TestCase):
    def setUp(self):
        self.con = connect()
        self.addCleanup(self.con.close)

    def test_summary_matches_independent_oracle(self):
        expected, _ = oracle()
        rows = self.con.execute("SELECT policy_id, true_positive, false_positive, false_negative, "
                                "true_negative FROM policy_summary").fetchall()
        self.assertEqual({r[0]: tuple(r[1:]) for r in rows}, expected)

    def test_known_outcomes(self):
        rows = {r[0]: r[1:] for r in self.con.execute("SELECT * FROM policy_summary")}
        self.assertEqual(rows["identity"][:4], (1, 2, 0, 7))
        self.assertEqual(rows["identity"][4], 1 / 3)
        self.assertEqual(rows["grid5"][:3], (0, 0, 1))
        self.assertIsNone(rows["grid5"][4])
        self.assertEqual(rows["suppress11"][2], 1)
        self.assertEqual(rows["window3"][0], 1)

    def test_transformation_error_is_separate_and_matches_oracle(self):
        _, expected = oracle()
        got = {r[0]: r[1:] for r in self.con.execute("SELECT * FROM transformation_error")}
        for pid, (releases, suppressed, mean_error) in expected.items():
            self.assertEqual(got[pid][:2], (releases, suppressed))
            if mean_error is None:
                self.assertIsNone(got[pid][2])
            else:
                self.assertAlmostEqual(got[pid][2], mean_error)
        self.assertEqual(got["identity"][2], 0)
        self.assertAlmostEqual(got["grid5"][2], 10 / 12)
        self.assertEqual(got["suppress11"][1], 6)

    def test_constraints_reject_unsafe_rows(self):
        bad = [("INSERT INTO synthetic_occupancy (run_id, step, occupancy, origin) VALUES ('x', 0, 1, 'field')",),
               ("INSERT INTO synthetic_occupancy (run_id, step, occupancy) VALUES ('x', 0, -1)",),
               ("INSERT INTO policy VALUES ('bad', 0, 0, 1)",),
               ("INSERT INTO policy VALUES ('bad', 1, 0, 0)",),
               ("INSERT INTO synthetic_target_event VALUES ('r1', 99)",)]
        for (statement,) in bad:
            with self.assertRaises(sqlite3.IntegrityError):
                self.con.execute(statement)

    def test_rerunning_the_script_is_safe(self):
        self.con.executescript(SQL_PATH.read_text(encoding="utf-8"))
        count = self.con.execute("SELECT COUNT(*) FROM policy_summary").fetchone()[0]
        self.assertEqual(count, len(POLICIES))


if __name__ == "__main__":
    unittest.main()
