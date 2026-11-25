# SPDX-License-Identifier: MIT OR Apache-2.0
"""Time-dependent heat-access analysis on a declared network (synthetic tests only).

Exposure uses a DECLARED environmental metric, h(t, segment) = max(0, T_air(t) + shift
+ sun_increment * (1 - shade) - T_ref), integrated along an itinerary in degree-seconds.
It is not a physiological or individual risk score and no validity is claimed for
the parameters. Vehicle interiors are assumed to contribute zero exposure (a declared
assumption). Itineraries are enumerated exhaustively on small graphs, never inferred
from anyone's movements.
"""
from dataclasses import dataclass
import re
import unittest

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
UNITS = "degree-seconds above a declared reference; environmental metric, not an individual risk score"


@dataclass(frozen=True)
class Node:
    name: str
    shade: float = 0.0


@dataclass(frozen=True)
class Segment:
    name: str
    src: str
    dst: str
    kind: str
    duration_s: int = 0
    shade: float = 0.0
    accessible: bool | None = None
    bidirectional: bool = False
    timetable: tuple = ()


@dataclass(frozen=True)
class Facility:
    node: str
    open_intervals: tuple | None


@dataclass(frozen=True)
class Weather:
    observations: tuple
    sigma_c: float
    t_ref_c: float
    sun_increment_c: float


def _num(v):
    return type(v) in (int, float) and v == v and abs(v) != float("inf")


def validate(nodes, segments, facilities, w):
    names = [n.name for n in nodes]
    if not nodes or len(set(names)) != len(names) or not all(type(x) is str and TOKEN.fullmatch(x) for x in names) \
            or not all(_num(n.shade) and 0 <= n.shade <= 1 for n in nodes):
        raise ValueError("nodes")
    seg_names = [s.name for s in segments]
    if len(set(seg_names)) != len(seg_names):
        raise ValueError("segments")
    for s in segments:
        ok = (type(s.name) is str and TOKEN.fullmatch(s.name) and s.src in names and s.dst in names
              and s.kind in ("walk", "transit") and s.accessible in (None, True, False)
              and type(s.bidirectional) is bool and _num(s.shade) and 0 <= s.shade <= 1)
        if s.kind == "walk":
            ok = ok and type(s.duration_s) is int and s.duration_s > 0 and not s.timetable
        else:
            tt = s.timetable
            ok = ok and type(tt) is tuple and tt and not s.bidirectional and all(
                type(p) is tuple and len(p) == 2 and all(type(v) is int for v in p) and p[0] < p[1] for p in tt) \
                and all(a[0] < b[0] for a, b in zip(tt, tt[1:]))
        if not ok:
            raise ValueError("segment " + str(s.name))
    for f in facilities:
        if f.node not in names or not (f.open_intervals is None or (type(f.open_intervals) is tuple and all(
                type(p) is tuple and len(p) == 2 and all(type(v) is int for v in p) and p[0] < p[1]
                for p in f.open_intervals))):
            raise ValueError("facility")
    obs = w.observations
    if type(obs) is not tuple or not obs or not all(type(p) is tuple and len(p) == 2 and type(p[0]) is int
                                                    and _num(p[1]) for p in obs) \
            or any(b[0] <= a[0] for a, b in zip(obs, obs[1:])) \
            or not (_num(w.sigma_c) and w.sigma_c >= 0 and _num(w.t_ref_c) and _num(w.sun_increment_c)
                    and w.sun_increment_c >= 0):
        raise ValueError("weather")


def _temp(obs, t):
    if t <= obs[0][0]:
        return obs[0][1]
    if t >= obs[-1][0]:
        return obs[-1][1]
    for (t0, v0), (t1, v1) in zip(obs, obs[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def _hinge(y0, y1, dt):
    """Exact integral of max(0, linear from y0 to y1) over a duration dt."""
    if y0 >= 0 and y1 >= 0:
        return dt * (y0 + y1) / 2
    if y0 <= 0 and y1 <= 0:
        return 0.0
    if y0 > 0:
        return 0.5 * y0 * (y0 / (y0 - y1)) * dt
    return 0.5 * y1 * (y1 / (y1 - y0)) * dt


def exposure(w, t0, t1, shade, shift=0.0):
    """Degree-seconds over [t0, t1] at a given shade fraction; shift moves T_air."""
    if t1 <= t0:
        return 0.0
    extra = w.sun_increment_c * (1 - shade)
    pts = sorted({t0, t1} | {k for k, _ in w.observations if t0 < k < t1})
    return sum(_hinge(_temp(w.observations, a) + shift + extra - w.t_ref_c,
                      _temp(w.observations, b) + shift + extra - w.t_ref_c, b - a)
               for a, b in zip(pts, pts[1:]))


def _enumerate(nodes, segments, origin, goal, start_s, w, max_paths, max_hops):
    adj, shade = {}, {n.name: n.shade for n in nodes}
    for s in segments:
        adj.setdefault(s.src, []).append((s, False))
        if s.kind == "walk" and s.bidirectional:
            adj.setdefault(s.dst, []).append((s, True))
    out, state = [], {"truncated": False}

    def go(node, t, visited, edges, lo, hi, unverified, blocked):
        if node == goal:
            out.append((edges, t, lo, hi, unverified, blocked))
            if len(out) >= max_paths:
                state["truncated"] = True
            return
        if len(edges) >= max_hops:
            return
        for seg, rev in adj.get(node, ()):
            if state["truncated"]:
                return
            dst = seg.src if rev else seg.dst
            if dst in visited:
                continue
            if seg.kind == "walk":
                arrive, sh, t_end = t + seg.duration_s, seg.shade, t + seg.duration_s
            else:
                nxt = next(((d, a) for d, a in seg.timetable if d >= t), None)
                if nxt is None:
                    continue
                t_end, arrive, sh = nxt[0], nxt[1], shade[node]
            go(dst, arrive, visited | {dst}, edges + (seg.name,),
               lo + exposure(w, t, t_end, sh, -w.sigma_c), hi + exposure(w, t, t_end, sh, w.sigma_c),
               unverified + (seg.accessible is None), blocked or seg.accessible is False)

    go(origin, start_s, {origin}, (), 0.0, 0.0, 0, False)
    return out, state["truncated"]


def _pareto(items):
    keep = []
    for a in items:
        dominated = any(b is not a and b["arrival_s"] <= a["arrival_s"] and b["exposure_hi"] <= a["exposure_hi"]
                        and (b["arrival_s"] < a["arrival_s"] or b["exposure_hi"] < a["exposure_hi"]) for b in items)
        if not dominated:
            keep.append(a)
    return tuple(sorted(keep, key=lambda i: (i["arrival_s"], i["exposure_hi"], i["edges"])))


def access_report(nodes, segments, facilities, w, origin, start_s, min_stay_s, max_paths=500, max_hops=8):
    validate(nodes, segments, facilities, w)
    names = {n.name: n.shade for n in nodes}
    if origin not in names or type(start_s) is not int or type(min_stay_s) is not int or min_stay_s < 0 \
            or type(max_paths) is not int or max_paths < 1 or type(max_hops) is not int or max_hops < 1:
        raise ValueError("report options")
    report, latest = {}, start_s
    for fac in sorted(facilities, key=lambda f: f.node):
        paths, truncated = _enumerate(nodes, segments, origin, fac.node, start_s, w, max_paths, max_hops)
        usable = [p for p in paths if not p[5]]
        feasible, unverified_hours = [], False
        for edges, arrival, lo, hi, unv, _ in usable:
            latest = max(latest, arrival)
            if fac.open_intervals is None:
                unverified_hours = True
                continue
            start = next((max(arrival, o) for o, c in sorted(fac.open_intervals) if max(arrival, o) + min_stay_s <= c), None)
            if start is None:
                continue
            wl = exposure(w, arrival, start, names[fac.node], -w.sigma_c)
            wh = exposure(w, arrival, start, names[fac.node], w.sigma_c)
            feasible.append({"edges": edges, "arrival_s": start, "exposure_lo": lo + wl, "exposure_hi": hi + wh,
                             "exposure_mid": (lo + wl + hi + wh) / 2, "unverified_segments": unv,
                             "waited_outside_s": start - arrival})
        if truncated:
            status = "unresolved_truncated"
        elif not paths:
            status = "no_path"
        elif not usable:
            status = "no_accessible_path"
        elif feasible:
            status = "reachable"
        elif unverified_hours:
            status = "hours_unverified"
        else:
            status = "not_open_in_time"
        report[fac.node] = {"status": status, "paths_considered": len(paths), "itineraries": _pareto(feasible)}
    return {"facilities": report, "exposure_units": UNITS, "individual_risk_score": False,
            "extrapolated_weather": start_s < w.observations[0][0] or latest > w.observations[-1][0]}


class Tests(unittest.TestCase):
    W = Weather(((0, 40.0), (3600, 40.0)), 1.0, 35.0, 5.0)

    def net(self, hours=((0, 3000),), mall_hours=((0, 3000),)):
        nodes = (Node("home"), Node("stop_a", 0.5), Node("library", 1.0), Node("mall", 1.0))
        segs = (Segment("direct", "home", "library", "walk", 600, 0.0, True),
                Segment("shaded", "home", "library", "walk", 900, 0.9, True),
                Segment("to_stop", "home", "stop_a", "walk", 120, 0.5, True),
                Segment("bus", "stop_a", "library", "transit", accessible=True, timetable=((1000, 1300), (2200, 2500))),
                Segment("steps", "home", "mall", "walk", 900, 0.8, False))
        return nodes, segs, (Facility("library", hours), Facility("mall", mall_hours))

    def report(self, hours=((0, 3000),), min_stay=300, **kw):
        nodes, segs, facs = self.net(hours)
        return access_report(nodes, segs, facs, kw.pop("w", self.W), "home", 0, min_stay, **kw)

    def test_exposure_integral_is_exact(self):
        w = Weather(((0, 30.0), (100, 40.0)), 0.0, 35.0, 0.0)
        self.assertAlmostEqual(exposure(w, 0, 100, 1.0), 125.0)
        self.assertAlmostEqual(exposure(w, 50, 100, 1.0), 125.0)
        self.assertEqual(exposure(w, 0, 50, 1.0), 0.0)
        flat = Weather(((0, 40.0), (50, 40.0)), 0.0, 35.0, 5.0)
        self.assertEqual(exposure(flat, 0, 20, 0.0), 20 * 10.0)
        self.assertEqual(exposure(flat, 0, 20, 1.0), 20 * 5.0)
        self.assertEqual(exposure(flat, 0, 20, 0.5), 20 * 7.5)
        self.assertEqual(exposure(flat, 0, 20, 1.0, shift=-10.0), 0.0)
        self.assertAlmostEqual(exposure(w, 0, 100, 1.0, shift=0.0), exposure(w, 0, 60, 1.0) + exposure(w, 60, 100, 1.0))

    def test_itineraries_trade_arrival_against_exposure_and_a_dominated_route_is_dropped(self):
        r = self.report(min_stay=0)["facilities"]["library"]
        by = {i["edges"]: i for i in r["itineraries"]}
        self.assertEqual(set(by), {("direct",), ("shaded",)})
        self.assertEqual((by[("direct",)]["arrival_s"], by[("direct",)]["exposure_mid"]), (600, 6000.0))
        self.assertEqual((by[("shaded",)]["arrival_s"], by[("shaded",)]["exposure_mid"]), (900, 4950.0))
        self.assertLess(by[("direct",)]["exposure_lo"], by[("direct",)]["exposure_hi"])
        self.assertEqual((r["status"], r["paths_considered"]), ("reachable", 3))

    def test_waiting_for_a_timetabled_vehicle_counts_as_exposure(self):
        w = Weather(((0, 40.0), (3600, 40.0)), 0.0, 35.0, 5.0)
        nodes, segs, facs = self.net()
        segs = tuple(s for s in segs if s.name not in ("direct", "shaded"))
        r = access_report(nodes, segs, (facs[0],), w, "home", 0, 0)["facilities"]["library"]
        (i,) = r["itineraries"]
        self.assertEqual((i["edges"], i["arrival_s"]), (("to_stop", "bus"), 1300))
        self.assertAlmostEqual(i["exposure_mid"], 120 * 7.5 + 880 * 7.5)
        late = access_report(nodes, segs, (facs[0],), w, "home", 1100, 0)["facilities"]["library"]["itineraries"][0]
        self.assertEqual(late["arrival_s"], 2500)

    def test_facility_hours_and_minimum_stay_boundaries(self):
        self.assertEqual(self.report(((0, 900),))["facilities"]["library"]["itineraries"][0]["edges"], ("direct",))
        self.assertEqual(self.report(((0, 899),))["facilities"]["library"]["status"], "not_open_in_time")
        waited = self.report(((700, 3000),), min_stay=0)["facilities"]["library"]["itineraries"]
        d = [i for i in waited if i["edges"] == ("direct",)][0]
        self.assertEqual((d["arrival_s"], d["waited_outside_s"]), (700, 100))
        self.assertAlmostEqual(d["exposure_mid"], 6000.0 + 100 * 5.0)
        self.assertEqual(self.report(None)["facilities"]["library"]["status"], "hours_unverified")

    def test_inaccessible_and_missing_routes_are_reported_separately(self):
        r = self.report()["facilities"]
        self.assertEqual(r["mall"]["status"], "no_accessible_path")
        nodes, segs, facs = self.net()
        nodes += (Node("island"),)
        out = access_report(nodes, segs, facs + (Facility("island", ((0, 10),)),), self.W, "home", 0, 0)
        self.assertEqual(out["facilities"]["island"]["status"], "no_path")
        unknown = tuple(Segment("steps", "home", "mall", "walk", 900, 0.8, None) if s.name == "steps" else s for s in segs)
        i = access_report(nodes, unknown, facs, self.W, "home", 0, 0)["facilities"]["mall"]["itineraries"][0]
        self.assertEqual((i["edges"], i["unverified_segments"]), (("steps",), 1))

    def test_truncation_never_claims_a_complete_answer(self):
        self.assertEqual(self.report(max_paths=1)["facilities"]["library"]["status"], "unresolved_truncated")
        self.assertEqual(self.report(max_hops=1)["facilities"]["library"]["paths_considered"], 2)

    def test_declared_metric_flags(self):
        out = self.report()
        self.assertFalse(out["individual_risk_score"])
        self.assertIn("not an individual risk score", out["exposure_units"])
        self.assertFalse(out["extrapolated_weather"])
        self.assertTrue(self.report(w=Weather(((0, 40.0), (100, 40.0)), 1.0, 35.0, 5.0))["extrapolated_weather"])

    def test_invalid_inputs(self):
        nodes, segs, facs = self.net()
        bad = [Segment("x", "home", "nowhere", "walk", 5), Segment("x", "home", "mall", "walk", 0),
               Segment("x", "home", "mall", "transit", timetable=()), Segment("x", "home", "mall", "transit", timetable=((5, 5),)),
               Segment("x", "home", "mall", "walk", 5, 1.5), Segment("x", "home", "mall", "walk", 5, accessible="yes")]
        for s in bad:
            with self.assertRaises(ValueError):
                access_report(nodes, segs + (s,), facs, self.W, "home", 0, 0)
        for w in (Weather((), 0.0, 35.0, 5.0), Weather(((5, 1.0), (5, 2.0)), 0.0, 35.0, 5.0), Weather(((0, 1.0),), -1.0, 35.0, 5.0)):
            with self.assertRaises(ValueError):
                access_report(nodes, segs, facs, w, "home", 0, 0)
        for kw in (dict(origin="nope"), dict(start_s=1.5), dict(min_stay_s=-1), dict(max_paths=0)):
            args = dict(origin="home", start_s=0, min_stay_s=0, max_paths=5)
            args.update(kw)
            with self.assertRaises(ValueError):
                access_report(nodes, segs, facs, self.W, args["origin"], args["start_s"], args["min_stay_s"],
                              max_paths=args["max_paths"])


if __name__ == "__main__":
    unittest.main()
