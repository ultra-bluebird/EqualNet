# SPDX-License-Identifier: MIT OR Apache-2.0
"""Heat-reuse accounting: delivered, useful, rejected, and net burden (synthetic only).

Delivered heat E = sum(m_dot * cp * (T_out - T_in) * dt) from uniformly sampled series, with
uncertainty from random and common-mode temperature errors, flow and cp scale errors, and a
timing-offset sensitivity. Useful heat is time-matched to receiver demand. The net burden
compares avoided baseline energy with ADDED energy (pumping, lift, extra computation).
Nothing here authorizes operating equipment or a public benefit claim.
"""
import math
import unittest

J_PER_KWH = 3.6e6


def _fin(v):
    return type(v) in (int, float) and math.isfinite(v)


def _series(m, t_in, t_out, dt_s, cp):
    n = len(m)
    if n < 1 or len(t_in) != n or len(t_out) != n or not (_fin(dt_s) and dt_s > 0 and _fin(cp) and cp > 0):
        raise ValueError("series")
    if not all(_fin(v) for v in list(m) + list(t_in) + list(t_out)) or any(v < 0 for v in m):
        raise ValueError("values")


def delivered_heat(m, t_in, t_out, dt_s, cp, u):
    """Energy in kWh with standard uncertainty. u keys: t_rand, t_sys_in, t_sys_out, rho, m_rel, cp_rel."""
    _series(m, t_in, t_out, dt_s, cp)
    need = {"t_rand", "t_sys_in", "t_sys_out", "rho", "m_rel", "cp_rel"}
    if type(u) is not dict or set(u) != need or not all(_fin(v) for v in u.values()) \
            or not -1 <= u["rho"] <= 1 or any(u[k] < 0 for k in need - {"rho"}):
        raise ValueError("uncertainty")
    e = sum(mi * cp * (to - ti) * dt_s for mi, ti, to in zip(m, t_in, t_out))
    a = sum(mi * cp * dt_s for mi in m)
    var = sum((mi * cp * dt_s) ** 2 * 2 * u["t_rand"] ** 2 for mi in m)
    var += a ** 2 * (u["t_sys_in"] ** 2 + u["t_sys_out"] ** 2 - 2 * u["rho"] * u["t_sys_in"] * u["t_sys_out"])
    var += (e * u["m_rel"]) ** 2 + (e * u["cp_rel"]) ** 2
    return {"energy_kwh": e / J_PER_KWH, "u_kwh": math.sqrt(max(var, 0.0)) / J_PER_KWH}


def timing_sensitivity(m, t_in, t_out, dt_s, cp, shifts):
    """Energy when the temperature series is shifted by k samples against flow (edge values held)."""
    _series(m, t_in, t_out, dt_s, cp)
    if not shifts or not all(type(k) is int for k in shifts):
        raise ValueError("shifts")
    n, out = len(m), {}
    for k in shifts:
        idx = [min(max(i + k, 0), n - 1) for i in range(n)]
        out[k] = sum(m[i] * cp * (t_out[j] - t_in[j]) * dt_s for i, j in enumerate(idx)) / J_PER_KWH
    return {"energy_kwh_by_shift": out, "range_kwh": (min(out.values()), max(out.values()))}


def useful_heat(m, t_in, t_out, dt_s, cp, demand_w, stored_kwh=0.0):
    """Time-matched useful heat: sum(min(delivered power, demand) * dt); the rest is rejected or stored."""
    _series(m, t_in, t_out, dt_s, cp)
    if len(demand_w) != len(m) or not all(_fin(v) and v >= 0 for v in demand_w) or not (_fin(stored_kwh) and stored_kwh >= 0):
        raise ValueError("demand")
    q = [mi * cp * (to - ti) for mi, ti, to in zip(m, t_in, t_out)]
    delivered = sum(max(x, 0.0) for x in q) * dt_s / J_PER_KWH
    useful = sum(min(max(x, 0.0), d) for x, d in zip(q, demand_w)) * dt_s / J_PER_KWH
    if stored_kwh > delivered - useful + 1e-12:
        raise ValueError("stored exceeds unused heat")
    return {"delivered_kwh": delivered, "useful_kwh": useful, "stored_kwh": stored_kwh,
            "rejected_kwh": delivered - useful - stored_kwh,
            "flags": ("NEGATIVE_DELIVERY_INTERVALS",) if any(x < 0 for x in q) else ()}


def heat_closure(recoverable, delivered, losses, stored, k=2.0):
    """Each argument is (value_kwh, u_kwh). Residual = recoverable - (delivered + losses + stored)."""
    terms = (recoverable, delivered, losses, stored)
    if not all(type(t) is tuple and len(t) == 2 and _fin(t[0]) and _fin(t[1]) and t[1] >= 0 for t in terms) or not (_fin(k) and k > 0):
        raise ValueError("closure inputs")
    r = recoverable[0] - (delivered[0] + losses[0] + stored[0])
    u = math.sqrt(sum(t[1] ** 2 for t in terms))
    return {"residual_kwh": r, "u_kwh": u, "status": "closed_within_uncertainty" if abs(r) <= k * u else "not_closed"}


def net_burden(useful_kwh, u_useful_kwh, eta, u_eta_rel, e_pump_kwh, e_lift_kwh, e_extra_compute_kwh, u_added_kwh,
               k=2.0, reported_in_datacenter_ere=False, credited_in_receiver=False):
    """Net avoided energy = useful/eta - added energy; added includes any extra computation."""
    vals = (useful_kwh, u_useful_kwh, eta, u_eta_rel, e_pump_kwh, e_lift_kwh, e_extra_compute_kwh, u_added_kwh, k)
    if not all(_fin(v) for v in vals) or min(useful_kwh, u_useful_kwh, u_eta_rel, e_pump_kwh, e_lift_kwh,
                                             e_extra_compute_kwh, u_added_kwh) < 0 or not 0 < eta <= 5 or k <= 0 \
            or type(reported_in_datacenter_ere) is not bool or type(credited_in_receiver) is not bool:
        raise ValueError("net inputs")
    avoided = useful_kwh / eta
    added = e_pump_kwh + e_lift_kwh + e_extra_compute_kwh
    net = avoided - added
    u = math.sqrt((u_useful_kwh / eta) ** 2 + (avoided * u_eta_rel) ** 2 + u_added_kwh ** 2)
    flags = []
    if e_extra_compute_kwh > 0:
        flags.append("EXTRA_COMPUTE_ADDED_FOR_HEAT")
    if reported_in_datacenter_ere and credited_in_receiver:
        flags.append("DOUBLE_COUNT_RISK")
    status = "reduces_burden_under_declared_model" if net - k * u > 0 else (
        "increases_burden_under_declared_model" if net + k * u < 0 else "inconclusive")
    return {"avoided_kwh": avoided, "added_kwh": added, "net_avoided_kwh": net, "u_kwh": u, "status": status,
            "flags": tuple(flags), "benefit_claim_authorized": False}


class Tests(unittest.TestCase):
    U0 = {"t_rand": 0.0, "t_sys_in": 0.0, "t_sys_out": 0.0, "rho": 0.0, "m_rel": 0.0, "cp_rel": 0.0}

    def test_delivered_heat_is_exact(self):
        r = delivered_heat([2.0] * 3, [20.0] * 3, [30.0] * 3, 60.0, 4186.0, self.U0)
        self.assertAlmostEqual(r["energy_kwh"], 4.186, places=9)
        self.assertEqual(r["u_kwh"], 0.0)

    def test_uncertainty_components_and_common_mode_cancellation(self):
        m, ti, to = [2.0] * 3, [20.0] * 3, [30.0] * 3
        a = 3 * 2.0 * 4186.0 * 60.0
        e = a * 10.0
        def u(**kw):
            return delivered_heat(m, ti, to, 60.0, 4186.0, {**self.U0, **kw})["u_kwh"]
        self.assertAlmostEqual(u(cp_rel=0.01), 0.01 * e / 3.6e6, places=9)
        self.assertAlmostEqual(u(m_rel=0.02), 0.02 * e / 3.6e6, places=9)
        self.assertAlmostEqual(u(t_sys_in=0.5, t_sys_out=0.5), a * math.sqrt(0.5) / 3.6e6, places=9)
        self.assertAlmostEqual(u(t_sys_in=0.5, t_sys_out=0.5, rho=1.0), 0.0, places=9)
        self.assertAlmostEqual(u(t_sys_in=0.5, t_sys_out=0.5, rho=-1.0), a * 1.0 / 3.6e6, places=9)
        self.assertAlmostEqual(u(t_rand=1.0), math.sqrt(3 * (2 * 4186 * 60) ** 2 * 2) / 3.6e6, places=9)

    def test_timing_offset_changes_delivered_energy(self):
        m = [0.0, 0.0, 0.0, 2.0, 2.0, 2.0]
        ti, to = [20.0] * 6, [20.0, 20.0, 20.0, 30.0, 30.0, 30.0]
        r = timing_sensitivity(m, ti, to, 60.0, 4186.0, [-1, 0, 1])
        e0 = r["energy_kwh_by_shift"][0]
        self.assertAlmostEqual(r["energy_kwh_by_shift"][-1], e0 * 2 / 3, places=9)
        self.assertAlmostEqual(r["energy_kwh_by_shift"][1], e0, places=9)
        self.assertEqual(r["range_kwh"], (r["energy_kwh_by_shift"][-1], e0))

    def test_useful_rejected_and_stored_heat(self):
        r = useful_heat([1.0] * 3, [20.0] * 3, [21.0] * 3, 3600.0, 4000.0, [3000.0, 5000.0, 0.0])
        self.assertAlmostEqual(r["delivered_kwh"], 12.0)
        self.assertAlmostEqual(r["useful_kwh"], 7.0)
        self.assertAlmostEqual(r["rejected_kwh"], 5.0)
        self.assertAlmostEqual(useful_heat([1.0] * 3, [20.0] * 3, [21.0] * 3, 3600.0, 4000.0, [3000.0, 5000.0, 0.0], 2.0)["rejected_kwh"], 3.0)
        with self.assertRaises(ValueError):
            useful_heat([1.0] * 3, [20.0] * 3, [21.0] * 3, 3600.0, 4000.0, [3000.0, 5000.0, 0.0], 5.01)
        neg = useful_heat([1.0, 1.0], [21.0, 20.0], [20.0, 21.0], 3600.0, 4000.0, [4000.0, 4000.0])
        self.assertEqual(neg["flags"], ("NEGATIVE_DELIVERY_INTERVALS",))
        self.assertAlmostEqual(neg["delivered_kwh"], 4.0)

    def test_closure_and_net_burden_statuses(self):
        self.assertEqual(heat_closure((20, 1), (12, 1), (6, 1), (2, 0.5))["status"], "closed_within_uncertainty")
        self.assertEqual(heat_closure((20, 1), (12, 1), (1, 1), (2, 0.5))["status"], "not_closed")
        good = net_burden(7.0, 0.2, 0.9, 0.02, 1.0, 2.0, 0.0, 0.1)
        self.assertAlmostEqual(good["net_avoided_kwh"], 7 / 0.9 - 3.0)
        self.assertEqual(good["status"], "reduces_burden_under_declared_model")
        bad = net_burden(7.0, 0.2, 0.9, 0.02, 1.0, 2.0, 10.0, 0.1)
        self.assertEqual((bad["status"], bad["flags"]), ("increases_burden_under_declared_model", ("EXTRA_COMPUTE_ADDED_FOR_HEAT",)))
        self.assertEqual(net_burden(7.0, 3.0, 0.9, 0.02, 1.0, 2.0, 0.0, 0.1)["status"], "inconclusive")
        self.assertFalse(good["benefit_claim_authorized"])
        self.assertEqual(net_burden(7.0, 0.2, 0.9, 0.02, 1.0, 2.0, 0.0, 0.1, reported_in_datacenter_ere=True, credited_in_receiver=True)["flags"], ("DOUBLE_COUNT_RISK",))

    def test_invalid_inputs(self):
        ok = ([1.0], [20.0], [30.0], 60.0, 4186.0, self.U0)
        for i, bad in ((0, [-1.0]), (1, [20.0, 20.0]), (3, 0.0), (4, -1.0), (2, [float("nan")]), (0, [True])):
            args = list(ok)
            args[i] = bad
            with self.assertRaises(ValueError):
                delivered_heat(*args)
        for u in ({**self.U0, "rho": 2.0}, {**self.U0, "m_rel": -1.0}, {"t_rand": 0.0}):
            with self.assertRaises(ValueError):
                delivered_heat(*ok[:5], u)
        for args in ((0.0, 1.0, 0.0, 0.0, 1, 1, 0, 0), (1.0, 1.0, 0.9, 0.0, -1, 1, 0, 0)):
            with self.assertRaises(ValueError):
                net_burden(*args)
        with self.assertRaises(ValueError):
            timing_sensitivity(*ok[:5], [])
        with self.assertRaises(ValueError):
            heat_closure((1, -1), (1, 0), (1, 0), (1, 0))


if __name__ == "__main__":
    unittest.main()
