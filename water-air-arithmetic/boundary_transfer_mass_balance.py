# SPDX-License-Identifier: MIT OR Apache-2.0
"""Boundary-transfer estimate versus retained, relocated, and transformed mass (synthetic only).

M = sum(Q * (C_in - C_out) * dt) is a transfer ACROSS A BOUNDARY, not capture, detoxification,
exposure reduction, restoration, or safety. A durable-retention finding needs measured retained
mass, a closed balance across the declared streams, known and contained fates for relocated mass,
assessed transformation products, and accounted bypass. Nothing here authorizes a benefit claim.
"""
from dataclasses import dataclass
import math
import unittest

STREAMS = ("condensate", "process_water", "cleaning")
FATES = ("contained_and_disposed", "discharged_to_environment", "unknown")
NOT_SUPPORTED = ("community_exposure_reduction", "ecosystem_restoration", "detoxification", "carbon_removal",
                 "potable_suitability")


def _fin(v):
    return type(v) in (int, float) and math.isfinite(v)


@dataclass(frozen=True)
class Flow:
    q_m3_s: tuple
    c_in_mg_m3: tuple
    c_out_mg_m3: tuple
    dt_s: float
    u_c_rand: float = 0.0
    u_cin_sys: float = 0.0
    u_cout_sys: float = 0.0
    rho_sys: float = 0.0
    u_q_rel: float = 0.0


@dataclass(frozen=True)
class Term:
    mass_mg: float
    u_mg: float
    fate: str = "unknown"


def transfer_estimate(f):
    n = len(f.q_m3_s)
    if not (isinstance(f, Flow) and n >= 1 and len(f.c_in_mg_m3) == n == len(f.c_out_mg_m3)
            and all(_fin(v) for v in f.q_m3_s + f.c_in_mg_m3 + f.c_out_mg_m3) and _fin(f.dt_s) and f.dt_s > 0
            and all(_fin(v) and v >= 0 for v in (f.u_c_rand, f.u_cin_sys, f.u_cout_sys, f.u_q_rel))
            and _fin(f.rho_sys) and -1 <= f.rho_sys <= 1 and min(f.q_m3_s) >= 0 and min(f.c_in_mg_m3 + f.c_out_mg_m3) >= 0):
        raise ValueError("flow")
    mass = sum(q * (ci - co) * f.dt_s for q, ci, co in zip(f.q_m3_s, f.c_in_mg_m3, f.c_out_mg_m3))
    a = sum(q * f.dt_s for q in f.q_m3_s)
    var = sum((q * f.dt_s) ** 2 * 2 * f.u_c_rand ** 2 for q in f.q_m3_s)
    var += a ** 2 * (f.u_cin_sys ** 2 + f.u_cout_sys ** 2 - 2 * f.rho_sys * f.u_cin_sys * f.u_cout_sys)
    var += (mass * f.u_q_rel) ** 2
    return {"mass_mg": mass, "u_mg": math.sqrt(max(var, 0.0)), "meaning": "boundary transfer only"}


def bypass_adjusted_efficiency(c_in, c_out_mixed, bypass_fraction):
    """Apparent removal versus device removal when a fraction of flow bypasses the device."""
    if not (_fin(c_in) and c_in > 0 and _fin(c_out_mixed) and c_out_mixed >= 0 and _fin(bypass_fraction)
            and 0 <= bypass_fraction < 1):
        raise ValueError("bypass inputs")
    apparent = 1 - c_out_mixed / c_in
    return {"apparent": apparent, "device": 1 - (c_out_mixed / c_in - bypass_fraction) / (1 - bypass_fraction)}


def mass_balance(transfer_mg, u_transfer_mg, retained=None, streams=None, transformed=None,
                 products_assessed=None, bypass_accounted=False, k=2.0):
    streams = streams or {}
    terms = [t for t in [retained, transformed] + list(streams.values()) if t is not None]
    if not (_fin(transfer_mg) and _fin(u_transfer_mg) and u_transfer_mg >= 0 and _fin(k) and k > 0
            and set(streams) <= set(STREAMS) and type(bypass_accounted) is bool and products_assessed in (None, True, False)
            and all(isinstance(t, Term) and _fin(t.mass_mg) and t.mass_mg >= 0 and _fin(t.u_mg) and t.u_mg >= 0
                    and t.fate in FATES for t in terms)):
        raise ValueError("balance inputs")
    flags = tuple("TERM_NOT_PROVIDED_" + n.upper() for n, t in (("retained", retained), ("transformed", transformed))
                  if t is None)
    out = {"flags": flags, "claims_not_supported": NOT_SUPPORTED, "benefit_claim_authorized": False,
           "retention_fraction": None, "residual_mg": None}
    if transfer_mg <= k * u_transfer_mg:
        return {**out, "status": "transfer_not_distinguishable_from_zero"}
    if retained is None:
        return {**out, "status": "boundary_transfer_only"}
    residual = transfer_mg - sum(t.mass_mg for t in terms)
    u_res = math.sqrt(u_transfer_mg ** 2 + sum(t.u_mg ** 2 for t in terms))
    frac = retained.mass_mg / transfer_mg
    u_frac = math.sqrt((retained.u_mg / transfer_mg) ** 2 + (retained.mass_mg * u_transfer_mg / transfer_mg ** 2) ** 2)
    out.update(residual_mg=residual, u_residual_mg=u_res, retention_fraction=frac, u_retention_fraction=u_frac)
    moved = [t for t in streams.values() if t.mass_mg > 0]
    if abs(residual) > k * u_res:
        status = "balance_not_closed"
    elif any(t.fate == "discharged_to_environment" for t in moved):
        status = "partly_relocated_to_environment"
    elif any(t.fate == "unknown" for t in moved):
        status = "residual_fate_unknown"
    elif transformed is not None and transformed.mass_mg > 0 and products_assessed is not True:
        status = "transformation_products_unassessed"
    elif not bypass_accounted:
        status = "bypass_not_accounted"
    else:
        status = "durable_retention_supported_under_model"
    return {**out, "status": status}


class Tests(unittest.TestCase):
    def flow(self, **kw):
        base = dict(q_m3_s=(0.5,) * 4, c_in_mg_m3=(100.0,) * 4, c_out_mg_m3=(20.0,) * 4, dt_s=60.0)
        base.update(kw)
        return Flow(**base)

    def test_transfer_arithmetic_and_uncertainty_components(self):
        self.assertAlmostEqual(transfer_estimate(self.flow())["mass_mg"], 9600.0)
        self.assertEqual(transfer_estimate(self.flow())["u_mg"], 0.0)
        self.assertEqual(transfer_estimate(self.flow())["meaning"], "boundary transfer only")
        self.assertAlmostEqual(transfer_estimate(self.flow(u_cin_sys=2.0, u_cout_sys=2.0))["u_mg"], 120 * math.sqrt(8))
        self.assertAlmostEqual(transfer_estimate(self.flow(u_cin_sys=2.0, u_cout_sys=2.0, rho_sys=1.0))["u_mg"], 0.0, places=9)
        self.assertAlmostEqual(transfer_estimate(self.flow(u_c_rand=1.0))["u_mg"], math.sqrt(4 * 30 ** 2 * 2))
        self.assertAlmostEqual(transfer_estimate(self.flow(u_q_rel=0.1))["u_mg"], 960.0)

    def test_bypass_makes_apparent_removal_understate_the_device(self):
        r = bypass_adjusted_efficiency(100.0, 100 * (0.2 + 0.8 * 0.1), 0.2)
        self.assertAlmostEqual(r["apparent"], 0.72)
        self.assertAlmostEqual(r["device"], 0.9)
        self.assertAlmostEqual(bypass_adjusted_efficiency(100.0, 50.0, 0.0)["device"], 0.5)

    def terms(self, **kw):
        base = dict(retained=Term(6000, 300), streams={"condensate": Term(1500, 150, "contained_and_disposed"),
                                                       "cleaning": Term(1000, 100, "contained_and_disposed")},
                    transformed=Term(800, 200), products_assessed=True, bypass_accounted=True)
        base.update(kw)
        return base

    def test_status_ladder_from_transfer_only_to_durable_retention(self):
        self.assertEqual(mass_balance(9600, 300, **self.terms())["status"], "durable_retention_supported_under_model")
        self.assertEqual(mass_balance(100, 100)["status"], "transfer_not_distinguishable_from_zero")
        self.assertEqual(mass_balance(9600, 300)["status"], "boundary_transfer_only")
        self.assertEqual(mass_balance(9600, 300, retained=Term(3000, 300))["flags"], ("TERM_NOT_PROVIDED_TRANSFORMED",))
        self.assertEqual(mass_balance(9600, 300, **self.terms(retained=Term(3000, 300)))["status"], "balance_not_closed")
        self.assertEqual(mass_balance(9600, 300, **self.terms(products_assessed=False))["status"], "transformation_products_unassessed")
        self.assertEqual(mass_balance(9600, 300, **self.terms(bypass_accounted=False))["status"], "bypass_not_accounted")
        released = {"condensate": Term(1500, 150, "contained_and_disposed"), "cleaning": Term(1000, 100, "discharged_to_environment")}
        self.assertEqual(mass_balance(9600, 300, **self.terms(streams=released))["status"], "partly_relocated_to_environment")
        unknown = {"condensate": Term(1500, 150), "cleaning": Term(1000, 100, "contained_and_disposed")}
        self.assertEqual(mass_balance(9600, 300, **self.terms(streams=unknown))["status"], "residual_fate_unknown")

    def test_retention_fraction_and_unsupported_claims_are_explicit(self):
        r = mass_balance(9600, 300, **self.terms())
        self.assertAlmostEqual(r["retention_fraction"], 0.625)
        self.assertAlmostEqual(r["residual_mg"], 300.0)
        self.assertAlmostEqual(r["u_retention_fraction"], math.sqrt((300 / 9600) ** 2 + (6000 * 300 / 9600 ** 2) ** 2))
        self.assertIn("detoxification", r["claims_not_supported"])
        self.assertFalse(r["benefit_claim_authorized"])
        self.assertEqual(mass_balance(9600, 300, **self.terms(), k=0.5)["status"], "balance_not_closed")

    def test_transfer_boundary_is_strict_and_zero_mass_streams_do_not_block(self):
        self.assertEqual(mass_balance(600, 300, **self.terms())["status"], "transfer_not_distinguishable_from_zero")
        self.assertNotEqual(mass_balance(600.001, 300, **self.terms())["status"], "transfer_not_distinguishable_from_zero")
        empty = {"condensate": Term(0, 0, "unknown")}
        r = mass_balance(7000, 100, retained=Term(6000, 100), streams=empty, transformed=Term(1000, 100),
                         products_assessed=True, bypass_accounted=True)
        self.assertEqual(r["status"], "durable_retention_supported_under_model")

    def test_invalid_inputs(self):
        bad_flows = [self.flow(q_m3_s=()), self.flow(c_in_mg_m3=(1.0,)), self.flow(dt_s=0), self.flow(rho_sys=2.0),
                     self.flow(q_m3_s=(-1.0,) * 4), self.flow(u_q_rel=-1.0), "flow"]
        for f in bad_flows:
            with self.assertRaises((ValueError, AttributeError, TypeError)):
                transfer_estimate(f)
        for args in ((100.0, 5.0, -0.1), (0.0, 5.0, 0.2), (100.0, -1.0, 0.2), (100.0, 5.0, 1.0)):
            with self.assertRaises(ValueError):
                bypass_adjusted_efficiency(*args)
        for kw in (dict(retained=Term(-1, 0)), dict(retained=Term(1, 0, "gone")), dict(streams={"air": Term(1, 0)}),
                   dict(products_assessed="yes"), dict(k=0), dict(bypass_accounted=1)):
            with self.assertRaises(ValueError):
                mass_balance(100.0, 1.0, **kw)


if __name__ == "__main__":
    unittest.main()
