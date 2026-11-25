# SPDX-License-Identifier: MIT OR Apache-2.0
"""Stream-processing correctness model with a synthetic event oracle.

An in-memory model of event-time windowing, deduplication, late-event policy,
checkpoint restart, and sink replay. It contains no Kafka client and makes no
exactly-once assumption: the source replays from the last checkpoint, and the
sink is either an append-only log or an idempotent upsert, as the caller
declares. Events are synthetic and carry no rider, journey, or device identity.
"""
from collections import deque
from dataclasses import dataclass
import copy
import random
import re
import unittest

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


@dataclass(frozen=True)
class Config:
    window: int
    out_of_orderness: int
    allowed_lateness: int
    max_future_skew: int
    max_event_age: int
    max_abs_delta: int
    dedup_capacity: int
    checkpoint_every: int


def _check(cfg):
    values = (cfg.window, cfg.out_of_orderness, cfg.allowed_lateness, cfg.max_future_skew,
              cfg.max_event_age, cfg.max_abs_delta, cfg.dedup_capacity, cfg.checkpoint_every)
    if not isinstance(cfg, Config) or not all(type(v) is int for v in values):
        raise ValueError("config")
    if (cfg.window < 1 or cfg.out_of_orderness < 0 or cfg.allowed_lateness < 0
            or cfg.max_future_skew < 0 or cfg.max_event_age < 0 or cfg.max_abs_delta < 1
            or cfg.dedup_capacity < 1 or cfg.checkpoint_every < 1):
        raise ValueError("config")


def parse_event(raw):
    """Return (id, event_time, delta) or raise ValueError with a fixed reason code.

    Schema 1 uses key "d"; schema 2 renames it "delta". Floats (including NaN),
    booleans, extra keys, and unknown versions are all schema failures.
    """
    if type(raw) is not dict or type(raw.get("v")) is not int:
        raise ValueError("SCHEMA")
    if raw["v"] == 1:
        keys, delta_key = {"v", "id", "t", "d"}, "d"
    elif raw["v"] == 2:
        keys, delta_key = {"v", "id", "t", "delta"}, "delta"
    else:
        raise ValueError("SCHEMA")
    if set(raw) != keys or type(raw["id"]) is not str or ID.fullmatch(raw["id"]) is None \
            or type(raw["t"]) is not int or type(raw[delta_key]) is not int:
        raise ValueError("SCHEMA")
    return raw["id"], raw["t"], raw[delta_key]


class Pipeline:
    """Event-time windows with dedup and a watermark. Late events are reported."""

    def __init__(self, config):
        _check(config)
        self.cfg = config
        self.watermark = None
        self.open = {}
        self.seen = deque()
        self.seen_set = set()
        self.counted = {}
        self.late = []
        self.duplicates = []
        self.rejected = []

    def _reject(self, code, raw):
        eid = raw.get("id") if type(raw) is dict else None
        self.rejected.append((code, eid if type(eid) is str else None))
        return []

    def _close(self, force=False):
        out = []
        for start in sorted(self.open):
            if force or start + self.cfg.window + self.cfg.allowed_lateness <= self.watermark:
                out.append((start, self.open.pop(start)))
            else:
                break
        return out

    def process(self, arrival, raw):
        """Handle one arrival; return the (window_start, count) results it closes."""
        if type(arrival) is not int:
            raise ValueError("arrival")
        try:
            eid, t, delta = parse_event(raw)
        except ValueError as exc:
            return self._reject(str(exc), raw)
        cfg = self.cfg
        if abs(delta) > cfg.max_abs_delta:
            return self._reject("VALUE", raw)
        if t > arrival + cfg.max_future_skew:
            return self._reject("TIME_FUTURE", raw)
        if t < arrival - cfg.max_event_age:
            return self._reject("TIME_OLD", raw)
        if eid in self.seen_set:
            self.duplicates.append(eid)
            return []
        self.seen.append(eid)
        self.seen_set.add(eid)
        while len(self.seen) > cfg.dedup_capacity:
            self.seen_set.discard(self.seen.popleft())
        start = (t // cfg.window) * cfg.window
        if self.watermark is not None and start + cfg.window + cfg.allowed_lateness <= self.watermark:
            self.late.append(eid)
            return []
        self.open[start] = self.open.get(start, 0) + delta
        self.counted[eid] = self.counted.get(eid, 0) + 1
        if self.watermark is None or t - cfg.out_of_orderness > self.watermark:
            self.watermark = t - cfg.out_of_orderness
        return self._close()

    def finish(self):
        """End of input: emit every remaining open window."""
        return self._close(force=True) if self.open else []

    def snapshot(self):
        return copy.deepcopy((self.watermark, self.open, self.seen, self.seen_set,
                              self.counted, self.late, self.duplicates, self.rejected))

    def restore(self, snap):
        (self.watermark, self.open, self.seen, self.seen_set, self.counted,
         self.late, self.duplicates, self.rejected) = copy.deepcopy(snap)


def run(config, arrivals, crash_before=None):
    """Run arrivals with checkpoints; optionally crash once before arrivals[crash_before].

    On the crash the pipeline restores its last checkpoint and the source
    replays from that checkpoint offset (at-least-once). Emissions already
    delivered to the sink are not retracted.
    """
    _check(config)
    if crash_before is not None and (type(crash_before) is not int
                                     or not 0 <= crash_before < len(arrivals)):
        raise ValueError("crash_before")
    pipe, emissions = Pipeline(config), []
    checkpoint, i, crashed = (pipe.snapshot(), 0), 0, False
    while i < len(arrivals):
        if crash_before == i and not crashed:
            crashed = True
            pipe.restore(checkpoint[0])
            i = checkpoint[1]
            continue
        emissions.extend(pipe.process(*arrivals[i]))
        i += 1
        if i % config.checkpoint_every == 0:
            checkpoint = (pipe.snapshot(), i)
    emissions.extend(pipe.finish())
    return {"emissions": emissions, "late": tuple(pipe.late),
            "duplicates": tuple(pipe.duplicates), "rejected": tuple(pipe.rejected),
            "counted": dict(pipe.counted)}


def sink_counts(emissions, idempotent):
    """Idempotent sink: last write per window. Append-only sink: sum of emissions."""
    result = {}
    for start, count in emissions:
        result[start] = count if idempotent else result.get(start, 0) + count
    return result


def oracle_counts(truth, window):
    """Ground-truth counts: each true event counted exactly once at its true time."""
    result = {}
    for t, delta in truth.values():
        start = (t // window) * window
        result[start] = result.get(start, 0) + delta
    return result


def accounting(truth, counted):
    """Deltas lost (never counted) and over-counted (counted more than once)."""
    lost = sum(d for eid, (_, d) in truth.items() if counted.get(eid, 0) == 0)
    extra = sum(d * (counted[eid] - 1) for eid, (_, d) in truth.items() if counted.get(eid, 0) > 1)
    return lost, extra


def reconcile(oracle, observed):
    windows = sorted(set(oracle) | set(observed))
    differences = {w: observed.get(w, 0) - oracle.get(w, 0) for w in windows
                   if observed.get(w, 0) != oracle.get(w, 0)}
    return {"window_differences": differences,
            "total_difference": sum(observed.values()) - sum(oracle.values()),
            "exact_match": not differences}


def make_raw(version, eid, t, delta):
    if version == 1:
        return {"v": 1, "id": eid, "t": t, "d": delta}
    return {"v": 2, "id": eid, "t": t, "delta": delta}


def synthetic_stream(seed, n, max_delay, dup_prob=0.0, dup_delay=(1, 1), jumps=None):
    """Synthetic truth and a perturbed arrival list (delays, duplicates, time jumps)."""
    rnd, truth, items, t = random.Random(seed), {}, [], 1000
    for i in range(n):
        t += rnd.randint(1, 7)
        delta = rnd.choice((-1, 1, 1, 2))
        eid = "e%d" % i
        truth[eid] = (t, delta)
        raw = make_raw(1 if rnd.random() < 0.7 else 2, eid, t + (jumps or {}).get(eid, 0), delta)
        arrival = t + rnd.randint(0, max_delay)
        items.append((arrival, i, raw))
        if rnd.random() < dup_prob:
            items.append((arrival + rnd.randint(*dup_delay), i, copy.deepcopy(raw)))
    items.sort(key=lambda x: (x[0], x[1]))
    return truth, [(a, r) for a, _, r in items]


class Tests(unittest.TestCase):
    CFG = Config(window=100, out_of_orderness=40, allowed_lateness=0, max_future_skew=60,
                 max_event_age=5000, max_abs_delta=5, dedup_capacity=1000, checkpoint_every=5)

    def observed(self, result):
        return sink_counts(result["emissions"], True)

    def test_clean_stream_matches_oracle_and_uses_both_schemas(self):
        truth, arrivals = synthetic_stream(1, 60, 30)
        self.assertEqual({r["v"] for _, r in arrivals}, {1, 2})
        result = run(self.CFG, arrivals)
        self.assertEqual(self.observed(result), oracle_counts(truth, 100))
        self.assertEqual((result["late"], result["duplicates"], result["rejected"]), ((), (), ()))
        self.assertEqual(accounting(truth, result["counted"]), (0, 0))

    def test_reordering_within_watermark_lag_never_drops(self):
        for seed in range(25):
            truth, arrivals = synthetic_stream(seed, 50, 40)
            result = run(self.CFG, arrivals)
            self.assertEqual(result["late"], (), seed)
            self.assertEqual(self.observed(result), oracle_counts(truth, 100), seed)

    def test_duplicates_within_capacity_are_removed(self):
        truth, arrivals = synthetic_stream(3, 60, 30, dup_prob=0.3, dup_delay=(1, 20))
        result = run(self.CFG, arrivals)
        self.assertEqual(len(result["duplicates"]), len(arrivals) - 60)
        self.assertGreater(len(result["duplicates"]), 0)
        self.assertEqual(self.observed(result), oracle_counts(truth, 100))

    def test_small_dedup_capacity_overcounts_by_exactly_the_slipped_duplicates(self):
        cfg = Config(100, 40, 0, 60, 5000, 5, 1, 5)
        truth, arrivals = synthetic_stream(4, 80, 30, dup_prob=0.4, dup_delay=(5, 30))
        result = run(cfg, arrivals)
        lost, extra = accounting(truth, result["counted"])
        self.assertGreater(extra, 0)
        observed_total = sum(self.observed(result).values())
        self.assertEqual(observed_total, sum(oracle_counts(truth, 100).values()) - lost + extra)

    def test_late_events_are_reported_and_conserved(self):
        truth, arrivals = synthetic_stream(5, 80, 400)
        result = run(self.CFG, arrivals)
        lost, extra = accounting(truth, result["counted"])
        self.assertGreater(len(result["late"]), 0)
        self.assertEqual(set(result["late"]), {e for e in truth if result["counted"].get(e, 0) == 0})
        observed_total = sum(self.observed(result).values())
        self.assertEqual(observed_total, sum(oracle_counts(truth, 100).values()) - lost + extra)

    def test_plausible_clock_jump_misplaces_without_changing_total(self):
        cfg = Config(100, 40, 0, 200, 5000, 5, 100, 5)
        truth = {"a": (1005, 1), "b": (1210, 1)}
        arrivals = [(1010, make_raw(1, "a", 1100, 1)), (1210, make_raw(1, "b", 1210, 1))]
        result = run(cfg, arrivals)
        diff = reconcile(oracle_counts(truth, 100), self.observed(result))
        self.assertFalse(diff["exact_match"])
        self.assertEqual(diff["total_difference"], 0)
        self.assertEqual(diff["window_differences"], {1000: -1, 1100: 1})

    def test_implausible_clock_jump_is_rejected_and_accounted(self):
        truth, arrivals = synthetic_stream(6, 40, 30, jumps={"e7": 10000})
        result = run(self.CFG, arrivals)
        self.assertIn(("TIME_FUTURE", "e7"), result["rejected"])
        lost, _ = accounting(truth, result["counted"])
        self.assertEqual(lost, truth["e7"][1])

    def test_old_value_and_schema_rejections(self):
        pipe = Pipeline(self.CFG)
        cases = [(10000, make_raw(1, "x", 1, 1), "TIME_OLD"), (1000, make_raw(1, "x", 1000, 99), "VALUE"),
                 (1000, {"v": 3, "id": "x", "t": 1000, "d": 1}, "SCHEMA"),
                 (1000, {"v": 1, "id": "x", "t": 1000, "d": float("nan")}, "SCHEMA"),
                 (1000, {"v": 1, "id": "x", "t": 1000, "d": True}, "SCHEMA"),
                 (1000, {"v": 1, "id": "x", "t": 1000, "delta": 1}, "SCHEMA"),
                 (1000, {"v": 2, "id": "x", "t": 1000, "delta": 1, "extra": 1}, "SCHEMA"),
                 (1000, {"v": True, "id": "x", "t": 1000, "d": 1}, "SCHEMA"),
                 (1000, "not an object", "SCHEMA"), (1000, {"v": 1, "id": "x\n", "t": 1000, "d": 1}, "SCHEMA")]
        for arrival, raw, code in cases:
            pipe.process(arrival, raw)
            self.assertEqual(pipe.rejected[-1][0], code, raw)
        self.assertEqual(pipe.counted, {})
        self.assertIsNone(pipe.watermark)

    def test_rejected_events_do_not_advance_the_watermark(self):
        pipe = Pipeline(self.CFG)
        pipe.process(1000, make_raw(1, "a", 1000, 1))
        before = pipe.watermark
        pipe.process(1000, make_raw(1, "b", 90000, 1))
        self.assertEqual(pipe.watermark, before)

    def test_every_crash_point_recovers_with_an_idempotent_sink(self):
        truth, arrivals = synthetic_stream(7, 40, 30, dup_prob=0.2, dup_delay=(1, 10))
        for every, doubled_at in ((5, None), (7, 50)):  # doubled_at: first replaying crash
            cfg = Config(100, 40, 0, 60, 5000, 5, 1000, every)
            base = run(cfg, arrivals)
            self.assertEqual(len(base["emissions"]), 2)
            self.assertEqual(sink_counts(base["emissions"], False), oracle_counts(truth, 100))
            differing = []
            for crash in range(len(arrivals)):
                crashed = run(cfg, arrivals, crash_before=crash)
                self.assertEqual(sink_counts(crashed["emissions"], True),
                                 sink_counts(base["emissions"], True), (every, crash))
                for key in ("late", "duplicates", "rejected", "counted"):
                    self.assertEqual(crashed[key], base[key], (every, crash, key))
                if sink_counts(crashed["emissions"], False) != sink_counts(base["emissions"], False):
                    differing.append(crash)
            if doubled_at is None:
                self.assertEqual(differing, [])
            else:
                self.assertEqual(differing, list(range(doubled_at, len(arrivals))))
                crashed = run(cfg, arrivals, crash_before=doubled_at)
                self.assertEqual(sink_counts(crashed["emissions"], False)[1000],
                                 2 * oracle_counts(truth, 100)[1000])

    def test_invalid_configuration_and_arguments(self):
        for cfg in (Config(0, 0, 0, 0, 0, 1, 1, 1), Config(1, -1, 0, 0, 0, 1, 1, 1),
                    Config(1, 0, 0, 0, 0, 0, 1, 1), Config(1, 0, 0, 0, 0, 1, 0, 1),
                    Config(1, 0, 0, 0, 0, 1, 1, 0), Config(1.5, 0, 0, 0, 0, 1, 1, 1)):
            with self.assertRaises(ValueError):
                Pipeline(cfg)
        with self.assertRaises(ValueError):
            run(self.CFG, [(1, make_raw(1, "a", 1, 1))], crash_before=1)
        with self.assertRaises(ValueError):
            Pipeline(self.CFG).process(1.0, make_raw(1, "a", 1, 1))


if __name__ == "__main__":
    unittest.main()
