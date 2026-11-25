# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded-queue overload simulation with explicit loss reporting (synthetic only).

Arrivals follow a fixed schedule that does NOT react to queue state (no silent change to
sampling). The simulator has no output to any physical system. Every generated item ends
as processed, lost (with a reason), refused by policy, or still in flight, so counts always
conserve. Compared policies: plain FIFO, priority service with eviction of deferrable work,
and priority service that also pauses deferrable admission above a high-water mark.
"""
from dataclasses import dataclass
import math
import unittest

POLICIES = {"fifo_drop_newest": ("fifo", False, "drop_newest"),
            "priority_evict": ("priority", True, "drop_newest"),
            "priority_pause": ("priority", True, "pause")}


@dataclass(frozen=True)
class Config:
    capacity: int
    service_per_tick: int
    durable_buffer: int
    policy: str
    high_water: int
    stale_ticks: int


def _check(cfg, arrivals, outages, corrections):
    if not (isinstance(cfg, Config) and cfg.policy in POLICIES
            and all(type(v) is int for v in (cfg.capacity, cfg.service_per_tick, cfg.durable_buffer, cfg.high_water, cfg.stale_ticks))
            and cfg.capacity >= 1 and cfg.service_per_tick >= 1 and cfg.durable_buffer >= 0
            and 1 <= cfg.high_water <= cfg.capacity and cfg.stale_ticks >= 0):
        raise ValueError("config")
    if type(arrivals) not in (list, tuple) or not arrivals or not all(type(t) in (list, tuple) for t in arrivals) \
            or not all(type(a) is tuple and len(a) == 2 and a[0] in ("critical", "deferrable")
                       and type(a[1]) in (int, float) and math.isfinite(a[1]) for t in arrivals for a in t):
        raise ValueError("arrivals")
    n = len(arrivals)
    if not all(type(t) is int and 0 <= t < n for t in outages):
        raise ValueError("outages")
    if not all(type(k) is int and 0 <= k < n and type(v) is int and v >= 0 for k, v in corrections.items()):
        raise ValueError("corrections")


def simulate(cfg, arrivals, outages=frozenset(), corrections=None):
    corrections = corrections or {}
    _check(cfg, arrivals, outages, corrections)
    order, evict_for_critical, deferrable_rule = POLICIES[cfg.policy]
    queue, durable, processed, lost, refused, items = [], [], [], [], [], {}
    seq, age, last_gen = 0, [], None
    for tick, batch in enumerate(arrivals):
        while durable and len(queue) < cfg.capacity:
            queue.append(durable.pop(0))
        new = [(seq + i, k, v, tick, "obs", None) for i, (k, v) in enumerate(batch)]
        seq += len(new)
        if tick in corrections:
            new.append((seq, "critical", 0.0, tick, "corr", corrections[tick]))
            seq += 1
        for it in new:
            items[it[0]] = it
            if it[1] == "critical":
                if len(queue) < cfg.capacity:
                    queue.append(it)
                elif evict_for_critical and any(q[1] == "deferrable" for q in queue):
                    victim = next(q for q in queue if q[1] == "deferrable")
                    queue.remove(victim)
                    lost.append((victim[0], "deferrable", "evicted_for_critical", tick))
                    queue.append(it)
                elif len(durable) < cfg.durable_buffer:
                    durable.append(it)
                else:
                    lost.append((it[0], "critical", "critical_overflow", tick))
            elif deferrable_rule == "pause" and len(queue) >= cfg.high_water:
                refused.append((it[0], tick))
            elif len(queue) < cfg.capacity:
                queue.append(it)
            else:
                lost.append((it[0], "deferrable", "queue_full", tick))
        if tick not in outages:
            for _ in range(cfg.service_per_tick):
                if not queue:
                    break
                pick = 0
                if order == "priority":
                    pick = next((i for i, q in enumerate(queue) if q[1] == "critical"), 0)
                it = queue.pop(pick)
                processed.append((it[0], it[1], it[4], it[3], tick, it[2], it[5]))
                if it[1] == "critical" and it[4] == "obs":
                    last_gen = it[3] if last_gen is None else max(last_gen, it[3])
        age.append(None if last_gen is None else tick - last_gen)
    return _report(cfg, items, processed, lost, refused, queue, durable, age, outages)


def _report(cfg, items, processed, lost, refused, queue, durable, age, outages):
    crit_obs = [s for s, it in sorted(items.items()) if it[1] == "critical" and it[4] == "obs"]
    lost_crit = {s for s, k, _, _ in lost if k == "critical"}
    run = best = 0
    for s in crit_obs:
        run = run + 1 if s in lost_crit else 0
        best = max(best, run)
    gen_vals = [items[s][2] for s in crit_obs]
    done_vals = [v for s, k, kind, g, t, v, tg in processed if k == "critical" and kind == "obs"]
    bias = (sum(done_vals) / len(done_vals) - sum(gen_vals) / len(gen_vals)) if done_vals and gen_vals else None
    corr = {s: it for s, it in items.items() if it[4] == "corr"}
    done = {s: t - g for s, k, kind, g, t, v, tg in processed if kind == "corr"}
    known = [a for a in age if a is not None]
    return {"generated": len(items), "processed": len(processed), "lost": len(lost), "refused": len(refused),
            "in_flight": len(queue) + len(durable),
            "lost_by_reason": {r: sum(1 for x in lost if x[2] == r) for r in sorted({x[2] for x in lost})},
            "critical_lost": len(lost_crit), "longest_lost_critical_run": best, "bias_critical_mean": bias,
            "max_status_age": max(known) if known else None,
            "ticks_stale": sum(1 for a in known if a > cfg.stale_ticks),
            "corrections": {"total": len(corr), "processed": len(done), "not_processed": len(corr) - len(done),
                            "max_latency": max(done.values()) if done else None},
            "processed_ticks_during_outage": sum(1 for p in processed if p[4] in outages),
            "physical_actions_taken": 0, "loss_log": tuple(lost)}


def explain(result, tick_s=60):
    """Plain-text, colour-free explanation of a degraded period."""
    if type(tick_s) is not int or tick_s < 1 or result["critical_lost"] < 0:
        raise ValueError("explain inputs")
    if result["critical_lost"] == 0 and result["ticks_stale"] == 0:
        return "All key records in this period were recorded, and the status stayed current."
    parts = []
    if result["critical_lost"]:
        parts.append("%d key records were not recorded in this period." % result["critical_lost"])
    if result["ticks_stale"]:
        parts.append("The status was out of date for up to %d minutes." % math.ceil(result["max_status_age"] * tick_s / 60))
    parts.append("Estimates for this period are less reliable.")
    parts.append("No equipment was changed.")
    return " ".join(parts)


class Tests(unittest.TestCase):
    def cfg(self, policy="fifo_drop_newest", cap=1, service=1, durable=0, high=1, stale=5):
        return Config(cap, service, durable, policy, high, stale)

    def scenario(self):
        arr = []
        for t in range(100):
            batch = [("deferrable", 1.0)] * 3 + [("critical", 10.0 if 40 <= t < 50 else 1.0)] * 2
            arr.append([("deferrable", 1.0)] * 8 + batch if 40 <= t < 50 else batch)
        return arr, frozenset(range(60, 70)), {45: 5, 52: 7}

    def run_all(self):
        arr, outs, corr = self.scenario()
        return {p: simulate(Config(20, 4, 3, p, 12, 5), arr, outs, corr) for p in POLICIES}

    def test_every_item_is_accounted_for_under_every_policy(self):
        for p, r in self.run_all().items():
            self.assertEqual(r["generated"], r["processed"] + r["lost"] + r["refused"] + r["in_flight"], p)
        self.assertEqual({r["generated"] for r in self.run_all().values()}, {582})

    def test_throughput_is_service_bound_so_policies_change_what_is_dropped_not_how_much_is_done(self):
        runs = self.run_all()
        self.assertEqual({r["processed"] for r in runs.values()}, {4 * 90})
        self.assertGreater(runs["fifo_drop_newest"]["critical_lost"], 0)
        self.assertEqual(runs["priority_evict"]["critical_lost"], 0)
        self.assertEqual(runs["priority_pause"]["critical_lost"], 0)
        self.assertEqual(runs["fifo_drop_newest"]["longest_lost_critical_run"], runs["fifo_drop_newest"]["critical_lost"])

    def test_pausing_deferrable_work_replaces_loss_with_explicit_refusal(self):
        runs = self.run_all()
        self.assertEqual((runs["priority_pause"]["refused"], runs["priority_pause"]["lost"]), (200, 12))
        self.assertEqual(runs["priority_evict"]["refused"], 0)
        self.assertGreater(runs["priority_evict"]["lost"], 100)
        self.assertEqual(set(runs["priority_pause"]["lost_by_reason"]), {"evicted_for_critical"})

    def test_power_interruption_stops_processing_and_the_status_ages(self):
        for p, r in self.run_all().items():
            self.assertEqual(r["processed_ticks_during_outage"], 0, p)
            self.assertGreaterEqual(r["max_status_age"], 10, p)
        runs = self.run_all()
        self.assertGreater(runs["fifo_drop_newest"]["max_status_age"], runs["priority_evict"]["max_status_age"])
        self.assertGreater(runs["fifo_drop_newest"]["ticks_stale"], runs["priority_evict"]["ticks_stale"])

    def test_corrections_reach_the_consumer_sooner_under_priority_service(self):
        runs = self.run_all()
        self.assertEqual(runs["fifo_drop_newest"]["corrections"]["not_processed"], 0)
        self.assertGreater(runs["fifo_drop_newest"]["corrections"]["max_latency"], runs["priority_evict"]["corrections"]["max_latency"])
        self.assertEqual(runs["priority_evict"]["corrections"]["max_latency"], 0)

    def test_hand_checkable_loss_and_bias(self):
        r = simulate(self.cfg(), [[("critical", 1.0), ("critical", 10.0)]])
        self.assertEqual((r["critical_lost"], r["lost_by_reason"], r["processed"]), (1, {"critical_overflow": 1}, 1))
        self.assertAlmostEqual(r["bias_critical_mean"], 1.0 - 5.5)
        mixed = [[("deferrable", 5.0), ("critical", 1.0)]]
        self.assertEqual(simulate(self.cfg(), mixed)["critical_lost"], 1)
        e = simulate(self.cfg("priority_evict"), mixed)
        self.assertEqual((e["critical_lost"], e["lost_by_reason"], e["bias_critical_mean"]), (0, {"evicted_for_critical": 1}, 0.0))
        self.assertEqual(simulate(self.cfg("priority_evict"), [[("critical", 1.0), ("critical", 10.0)]])["critical_lost"], 1)

    def test_a_durable_buffer_absorbs_a_critical_burst_without_loss(self):
        r = simulate(self.cfg(durable=1), [[("critical", 1.0), ("critical", 2.0)], []])
        self.assertEqual((r["lost"], r["processed"], r["in_flight"]), (0, 2, 0))

    def test_outage_and_correction_arithmetic(self):
        r = simulate(self.cfg(cap=5), [[("critical", 1.0)]] * 3, outages=frozenset({1}))
        self.assertEqual((r["processed"], r["in_flight"], r["max_status_age"], r["processed_ticks_during_outage"]), (2, 1, 1, 0))
        tight = simulate(self.cfg(), [[("critical", 1.0)]] * 3, outages=frozenset({1}))
        self.assertEqual((tight["processed"], tight["lost"], tight["in_flight"]), (2, 1, 0))
        c = simulate(self.cfg(), [[("critical", 1.0)], []], corrections={1: 0})
        self.assertEqual(c["corrections"], {"total": 1, "processed": 1, "not_processed": 0, "max_latency": 0})

    def test_explanations_are_plain_numeric_and_colour_free(self):
        runs = self.run_all()
        text = explain(runs["fifo_drop_newest"])
        self.assertIn("19 key records were not recorded", text)
        self.assertIn("up to 15 minutes", text)
        self.assertIn("No equipment was changed.", text)
        self.assertEqual(explain(runs["priority_evict"]), "The status was out of date for up to 10 minutes. Estimates for this period are less reliable. No equipment was changed.")
        clean = simulate(Config(10, 4, 0, "priority_evict", 8, 5), [[("critical", 1.0)] * 2] * 5)
        self.assertEqual(explain(clean), "All key records in this period were recorded, and the status stayed current.")
        for t in (text, explain(runs["priority_pause"])):
            self.assertTrue(t.isascii() and len(t.split()) <= 60)
            self.assertFalse({"red", "green", "amber"} & set(t.lower().split()))
        self.assertEqual(explain(runs["priority_evict"], tick_s=120).count("20 minutes"), 1)

    def test_invalid_inputs(self):
        ok = [[("critical", 1.0)]]
        for cfg in (self.cfg(policy="lifo"), self.cfg(cap=0), self.cfg(high=2), self.cfg(durable=-1), "cfg"):
            with self.assertRaises(ValueError):
                simulate(cfg, ok)
        for arr in ([], [[("urgent", 1.0)]], [[("critical", float("nan"))]], [[("critical",)]], "x"):
            with self.assertRaises(ValueError):
                simulate(self.cfg(), arr)
        with self.assertRaises(ValueError):
            simulate(self.cfg(), ok, outages=frozenset({5}))
        with self.assertRaises(ValueError):
            simulate(self.cfg(), ok, corrections={3: 0})
        with self.assertRaises(ValueError):
            explain(simulate(self.cfg(), ok), tick_s=0)


if __name__ == "__main__":
    unittest.main()
