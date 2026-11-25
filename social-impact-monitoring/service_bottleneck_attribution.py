# SPDX-License-Identifier: MIT OR Apache-2.0
"""Service bottleneck attribution on AGGREGATE referral cells (synthetic tests only).

A record is one (destination, zone, day) cell: counts of referrals attempted and
completed, plus dated verification of the destination (open, appointment slots)
and of the route and accommodation for that zone. Nothing identifies a person.
Shortfall is split into the part bounded by VERIFIED barriers and an
"unattributed" remainder. The remainder is NOT a measure of nonparticipation or
choice: it holds every unverified reason, unrecorded barrier, and change of plan.
"""
import re
import unittest

BARRIER_ORDER = ("closed", "route_inaccessible", "accommodation_unmet", "no_appointments", "capacity_limited")
FIELDS = {"destination", "zone", "day", "attempted", "completed", "verified_day",
          "open", "route_accessible", "accommodation_ok", "slots"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
NOTE = "unattributed shortfall is NOT a measure of nonparticipation or choice"


def _int(v, low=0):
    return type(v) is int and v >= low


def _opt_bool(v):
    return v is None or type(v) is bool


def validate_cell(rec):
    if type(rec) is not dict or set(rec) != FIELDS:
        raise ValueError("cell fields")
    if not all(type(rec[k]) is str and TOKEN.fullmatch(rec[k]) for k in ("destination", "zone")):
        raise ValueError("cell names")
    if not (_int(rec["day"]) and _int(rec["attempted"]) and _int(rec["completed"])
            and rec["completed"] <= rec["attempted"]):
        raise ValueError("cell counts")
    if not (rec["verified_day"] is None or type(rec["verified_day"]) is int) \
            or not all(_opt_bool(rec[k]) for k in ("open", "route_accessible", "accommodation_ok")) \
            or not (rec["slots"] is None or _int(rec["slots"])):
        raise ValueError("cell verification")


def _fresh(rec, max_age):
    return rec["verified_day"] is not None and 0 <= rec["day"] - rec["verified_day"] <= max_age


def evaluate(records, max_age):
    """Per-entry attribution plus excluded groups. Conservation holds for every entry."""
    if type(records) not in (list, tuple) or not _int(max_age):
        raise ValueError("evaluate options")
    seen, groups = set(), {}
    for rec in records:
        validate_cell(rec)
        key = (rec["destination"], rec["zone"], rec["day"])
        if key in seen:
            raise ValueError("duplicate cell")
        seen.add(key)
        groups.setdefault((rec["destination"], rec["day"]), []).append(rec)
    entries, excluded = [], []
    for (dest, day), cells in sorted(groups.items()):
        cells = sorted(cells, key=lambda c: c["zone"])
        open_vals = {c["open"] for c in cells if _fresh(c, max_age) and c["open"] is not None}
        slot_vals = {c["slots"] for c in cells if _fresh(c, max_age) and c["slots"] is not None}
        if len(open_vals) > 1 or len(slot_vals) > 1:
            excluded.append(("VERIFICATION_CONFLICT", len(cells)))
            continue
        d_open = next(iter(open_vals), None)
        d_slots = next(iter(slot_vals), None)
        pool = []
        for c in cells:
            fresh = _fresh(c, max_age)
            route = c["route_accessible"] if fresh else None
            accom = c["accommodation_ok"] if fresh else None
            hard = []
            if d_open is False:
                hard.append("closed")
            if route is False:
                hard.append("route_inaccessible")
            if accom is False:
                hard.append("accommodation_unmet")
            if d_slots == 0:
                hard.append("no_appointments")
            unknown = int(d_open is None or d_slots is None or route is None or accom is None)
            if hard:
                if c["completed"] > 0:
                    excluded.append(("COMPLETED_WHILE_VERIFIED_BLOCKED", 1))
                    continue
                entries.append({"destination": dest, "day": day, "key": "+".join(
                    b for b in BARRIER_ORDER if b in hard), "cells": 1, "attempted": c["attempted"],
                    "completed": 0, "explained": c["attempted"], "unattributed": 0,
                    "unverified_cells": unknown})
            else:
                pool.append((c, unknown))
        if pool:
            total = sum(c["attempted"] for c, _ in pool)
            done = sum(c["completed"] for c, _ in pool)
            shortage = max(0, total - d_slots) if d_slots is not None else 0
            if done > total - shortage:
                excluded.append(("COMPLETED_EXCEEDS_VERIFIED_CAPACITY", len(pool)))
                continue
            entries.append({"destination": dest, "day": day,
                            "key": "capacity_limited" if shortage > 0 else "none_verified",
                            "cells": len(pool), "attempted": total, "completed": done,
                            "explained": shortage, "unattributed": total - shortage - done,
                            "unverified_cells": sum(u for _, u in pool)})
    return {"entries": entries, "excluded": excluded}


def summarize(records, max_age, k_min=5, min_attempted=10):
    """Group totals by verified-barrier set with small-cell and complementary suppression."""
    if not (_int(k_min, 2) and _int(min_attempted, 1)):
        raise ValueError("summary options")
    result = evaluate(records, max_age)
    groups = {}
    for e in result["entries"]:
        g = groups.setdefault(e["key"], {"cells": 0, "attempted": 0, "completed": 0, "explained": 0,
                                         "unattributed": 0, "unverified_cells": 0})
        for field in g:
            g[field] += e[field]
    hidden = {k for k, g in groups.items() if g["cells"] < k_min or g["attempted"] < min_attempted}
    shown = {k: g for k, g in groups.items() if k not in hidden}
    if len(hidden) == 1 and shown:
        hidden.add(min(shown, key=lambda k: (shown[k]["attempted"], k)))
        shown = {k: g for k, g in groups.items() if k not in hidden}
    total = None
    if not hidden and groups:
        total = {f: sum(g[f] for g in groups.values()) for f in next(iter(groups.values()))}
    return {"groups": shown, "suppressed_groups": len(hidden), "total": total,
            "excluded_cells": sum(n for _, n in result["excluded"]),
            "excluded_reasons": tuple(sorted({r for r, _ in result["excluded"]})),
            "interpretation": NOTE}


def destination_pressure(records, max_age, k_min=5, min_attempted=10):
    """Per destination: attempts into verified closed or full days; thresholds apply."""
    if not (_int(k_min, 2) and _int(min_attempted, 1)):
        raise ValueError("pressure options")
    per = {}
    for e in evaluate(records, max_age)["entries"]:
        p = per.setdefault(e["destination"], {"cells": 0, "attempted": 0, "into_closed_or_no_slots": 0,
                                              "over_capacity": 0})
        p["cells"] += e["cells"]
        p["attempted"] += e["attempted"]
        if "closed" in e["key"] or "no_appointments" in e["key"]:
            p["into_closed_or_no_slots"] += e["attempted"]
        if e["key"] == "capacity_limited":
            p["over_capacity"] += e["explained"]
    return {"destinations": {d: p for d, p in sorted(per.items())
                             if p["cells"] >= k_min and p["attempted"] >= min_attempted},
            "suppressed_destinations": sum(1 for p in per.values()
                                           if p["cells"] < k_min or p["attempted"] < min_attempted)}


def cell(destination="clinic", zone="north", day=10, attempted=10, completed=8, verified_day=10,
         open=True, route_accessible=True, accommodation_ok=True, slots=20):
    return {"destination": destination, "zone": zone, "day": day, "attempted": attempted,
            "completed": completed, "verified_day": verified_day, "open": open,
            "route_accessible": route_accessible, "accommodation_ok": accommodation_ok, "slots": slots}


class Tests(unittest.TestCase):
    def one(self, **kw):
        out = evaluate([cell(**kw)], 3)
        self.assertEqual(len(out["entries"]) + len(out["excluded"]), 1)
        return out

    def test_unblocked_cell_leaves_only_an_unattributed_remainder(self):
        e = self.one()["entries"][0]
        self.assertEqual((e["key"], e["explained"], e["unattributed"], e["unverified_cells"]), ("none_verified", 0, 2, 0))

    def test_closed_destination_explains_the_whole_shortfall(self):
        e = self.one(open=False, completed=0)["entries"][0]
        self.assertEqual((e["key"], e["explained"], e["unattributed"]), ("closed", 10, 0))

    def test_capacity_limit_is_pooled_across_zones_not_double_counted(self):
        recs = [cell(zone="north", attempted=6, completed=3, slots=8), cell(zone="south", attempted=6, completed=5, slots=8)]
        out = evaluate(recs, 3)
        (e,) = out["entries"]
        self.assertEqual((e["key"], e["cells"], e["attempted"], e["explained"], e["completed"], e["unattributed"]),
                         ("capacity_limited", 2, 12, 4, 8, 0))
        self.assertEqual(evaluate([recs[0]], 3)["entries"][0]["explained"], 0)

    def test_completions_beyond_verified_limits_exclude_the_record(self):
        out = evaluate([cell(zone="a", attempted=6, completed=5, slots=8), cell(zone="b", attempted=6, completed=5, slots=8)], 3)
        self.assertEqual((out["entries"], out["excluded"]), ([], [("COMPLETED_EXCEEDS_VERIFIED_CAPACITY", 2)]))
        out = evaluate([cell(open=False, completed=1)], 3)
        self.assertEqual(out["excluded"], [("COMPLETED_WHILE_VERIFIED_BLOCKED", 1)])
        self.assertEqual(self.one(slots=0, completed=0)["entries"][0]["key"], "no_appointments")

    def test_co_occurring_barriers_are_reported_jointly_never_split(self):
        e = self.one(open=False, route_accessible=False, completed=0)["entries"][0]
        self.assertEqual((e["key"], e["explained"]), ("closed+route_inaccessible", 10))
        e = self.one(route_accessible=False, accommodation_ok=False, completed=0, slots=0)["entries"][0]
        self.assertEqual(e["key"], "route_inaccessible+accommodation_unmet+no_appointments")

    def test_unknown_or_stale_verification_explains_nothing(self):
        for kw in (dict(open=None), dict(slots=None), dict(route_accessible=None), dict(accommodation_ok=None)):
            e = self.one(**kw)["entries"][0]
            self.assertEqual((e["key"], e["explained"], e["unverified_cells"]), ("none_verified", 0, 1), kw)
        stale = self.one(verified_day=6, open=False, route_accessible=False, slots=0, completed=5)["entries"][0]
        self.assertEqual((stale["key"], stale["explained"], stale["unverified_cells"], stale["unattributed"]),
                         ("none_verified", 0, 1, 5))
        for day_gap, key in ((3, "closed"), (4, "none_verified"), (0, "closed")):
            e = self.one(verified_day=10 - day_gap, open=False, completed=0)["entries"][0]
            self.assertEqual(e["key"], key, day_gap)
        self.assertEqual(self.one(verified_day=11, open=False, completed=0)["entries"][0]["key"], "none_verified")
        self.assertEqual(self.one(verified_day=None, open=False, completed=0)["entries"][0]["key"], "none_verified")

    def test_conflicting_destination_verification_is_excluded(self):
        out = evaluate([cell(zone="a", open=True), cell(zone="b", open=False)], 3)
        self.assertEqual(out["excluded"], [("VERIFICATION_CONFLICT", 2)])
        out = evaluate([cell(zone="a", slots=5, attempted=2, completed=1), cell(zone="b", slots=6, attempted=2, completed=1)], 3)
        self.assertEqual(out["excluded"], [("VERIFICATION_CONFLICT", 2)])

    def test_conservation_holds_for_random_cells(self):
        import random
        rnd = random.Random(4)
        recs, dest_state = [], {}
        for i in range(600):
            dest, day = "d%d" % (i % 5), 10 + (i // 5) % 7
            state = dest_state.setdefault((dest, day), (rnd.choice([True, True, False, None]),
                                                        rnd.choice([None, 0, 3, 8, 30])))
            a = rnd.randint(0, 12)
            recs.append(cell(destination=dest, zone="z%d" % i, day=day, attempted=a, completed=rnd.randint(0, a),
                             verified_day=rnd.choice([None, day, day - 5]), open=state[0], slots=state[1],
                             route_accessible=rnd.choice([True, False, None]), accommodation_ok=rnd.choice([True, None])))
        out = evaluate(recs, 3)
        self.assertGreater(len(out["entries"]), 50)
        self.assertGreater(len(out["excluded"]), 0)
        self.assertGreater(sum(e["explained"] > 0 for e in out["entries"]), 10)
        for e in out["entries"]:
            self.assertEqual(e["completed"] + e["explained"] + e["unattributed"], e["attempted"])
            self.assertGreaterEqual(e["unattributed"], 0)
            self.assertLessEqual(e["explained"], e["attempted"])

    def groups(self):
        recs = []
        for i in range(6):
            recs.append(cell(destination="d%d" % i, zone="a", open=False, completed=0, attempted=5))
        for i in range(8):
            recs.append(cell(destination="e%d" % i, zone="a", attempted=4, completed=3))
        for i in range(2):
            recs.append(cell(destination="f%d" % i, zone="a", route_accessible=False, completed=0, attempted=9))
        return recs

    def test_small_groups_are_suppressed_with_a_complementary_group_and_no_total(self):
        s = summarize(self.groups(), 3)
        self.assertEqual(s["suppressed_groups"], 2)
        self.assertEqual(set(s["groups"]), {"none_verified"})
        self.assertIsNone(s["total"])
        self.assertIn("NOT a measure of nonparticipation", s["interpretation"])
        self.assertNotIn("closed", s["groups"])

    def test_without_suppression_the_total_is_published_and_conserved(self):
        recs = [r for r in self.groups() if not r["destination"].startswith("f")]
        s = summarize(recs, 3)
        self.assertEqual(s["suppressed_groups"], 0)
        t = s["total"]
        self.assertEqual(t["completed"] + t["explained"] + t["unattributed"], t["attempted"])
        self.assertEqual(t["attempted"], 6 * 5 + 8 * 4)
        self.assertEqual(summarize([cell(attempted=3, completed=1)], 3)["suppressed_groups"], 1)
        self.assertEqual(summarize([], 3)["total"], None)

    def test_threshold_boundaries(self):
        recs = [cell(destination="d%d" % i, attempted=2, completed=1) for i in range(5)]
        self.assertEqual(summarize(recs, 3, k_min=5, min_attempted=10)["suppressed_groups"], 0)
        self.assertEqual(summarize(recs, 3, k_min=5, min_attempted=11)["suppressed_groups"], 1)
        self.assertEqual(summarize(recs[:4], 3, k_min=5, min_attempted=1)["suppressed_groups"], 1)

    def test_output_does_not_depend_on_record_order(self):
        import random
        recs = self.groups()
        shuffled = recs[:]
        random.Random(2).shuffle(shuffled)
        self.assertEqual(summarize(recs, 3), summarize(shuffled, 3))
        self.assertEqual(destination_pressure(recs, 3, k_min=2), destination_pressure(shuffled, 3, k_min=2))

    def test_destination_pressure_counts_attempts_into_closed_or_full_days(self):
        recs = [cell(destination="hub", zone="z%d" % i, day=10 + i, attempted=4, completed=0, open=False) for i in range(3)]
        recs += [cell(destination="hub", zone="y", day=20, verified_day=20, attempted=10, completed=4, slots=6)]
        recs += [cell(destination="tiny", zone="a", attempted=1, completed=1)]
        p = destination_pressure(recs, 3, k_min=2, min_attempted=5)
        self.assertEqual(p["destinations"]["hub"], {"cells": 4, "attempted": 22, "into_closed_or_no_slots": 12,
                                                    "over_capacity": 4})
        self.assertNotIn("tiny", p["destinations"])
        self.assertEqual(p["suppressed_destinations"], 1)

    def test_destination_pressure_threshold_boundaries(self):
        recs = [cell(destination="hub", zone="z%d" % i, day=10 + i, attempted=2, completed=1) for i in range(5)]
        for k_min, min_att, shown in ((5, 10, True), (5, 11, False), (6, 10, False), (2, 1, True)):
            p = destination_pressure(recs, 3, k_min=k_min, min_attempted=min_att)
            self.assertEqual(("hub" in p["destinations"], p["suppressed_destinations"]), (shown, 0 if shown else 1),
                             (k_min, min_att))

    def test_outputs_never_use_participation_language(self):
        s = summarize(self.groups(), 3)
        blob = repr(s) + repr(evaluate(self.groups(), 3)) + repr(destination_pressure(self.groups(), 3))
        for word in ("refus", "choice", "non-participation", "noncompliance", "declined"):
            self.assertNotIn(word, blob.replace("NOT a measure of nonparticipation or choice", ""))

    def test_invalid_records_and_options(self):
        bad = [cell(attempted=3, completed=4), cell(attempted=-1), cell(day=True), cell(destination="x\n"),
               cell(slots=-1), cell(open="yes"), cell(verified_day=1.5), {**cell(), "person": "x"},
               {k: v for k, v in cell().items() if k != "zone"}, "cell"]
        for r in bad:
            with self.assertRaises(ValueError):
                evaluate([r], 3)
        with self.assertRaises(ValueError):
            evaluate([cell(), cell()], 3)
        for args in (([cell()], -1), ("x", 3), ([cell()], True)):
            with self.assertRaises(ValueError):
                evaluate(*args)
        for kw in (dict(k_min=1), dict(min_attempted=0), dict(k_min=True)):
            with self.assertRaises(ValueError):
                summarize([cell()], 3, **kw)
            with self.assertRaises(ValueError):
                destination_pressure([cell()], 3, **kw)


if __name__ == "__main__":
    unittest.main()
