# SPDX-License-Identifier: MIT OR Apache-2.0
"""Persistence-path inventory and synthetic-canary artifact scanning.

Local analysis of caller-supplied bytes only. A negative scan never proves
absence, and no finding here authorizes deployment or any external action.
"""
from dataclasses import dataclass
import hashlib
import re
import unittest

PATHS = ("sensor_firmware", "accelerator_memory", "os_buffers", "swap",
         "crash_capture", "remote_console", "network_egress", "diagnostic_logs",
         "maintenance_interfaces", "persistent_storage")
STATUSES = {"inspected_clean", "retention_observed", "not_applicable"}
ENCODINGS = {"raw", "hex"}
MARKER = b"SYNTHETIC-NOT-PERSON-DATA:"
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
HEX = re.compile(r"[0-9a-f]{64}")


def make_canaries(seed, count=4, size=128):
    """Deterministic synthetic byte strings built only from SHA-256 output."""
    if type(seed) is not bytes or not seed or type(count) is not int \
            or not 1 <= count <= 64 or type(size) is not int or not 64 <= size <= 4096:
        raise ValueError("canary options")
    canaries = []
    for i in range(count):
        body, counter = b"", 0
        while len(body) < size:
            block = seed + i.to_bytes(4, "big") + counter.to_bytes(4, "big")
            body += hashlib.sha256(block).digest()
            counter += 1
        canaries.append(MARKER + body[:size])
    return tuple(canaries)


def scan_artifact(data, canaries, fragment=16):
    """Search raw and hex-text forms for aligned canary fragments.

    Any contiguous leaked run of at least 2*fragment-1 canary-body bytes
    contains an aligned fragment, so it is detected. Other encodings,
    compression, encryption, and shorter runs are not searched.
    """
    if type(data) is not bytes or type(canaries) is not tuple or not canaries \
            or type(fragment) is not int or not 8 <= fragment <= 64:
        raise ValueError("scan options")
    hits = []
    for index, canary in enumerate(canaries):
        if type(canary) is not bytes or not canary.startswith(MARKER) \
                or len(canary) - len(MARKER) < 4 * fragment:
            raise ValueError("canary")
        body = canary[len(MARKER):]
        forms = {"raw": [body[i:i + fragment] for i in range(0, len(body) - fragment + 1, fragment)]}
        text = body.hex()
        chunks = [text[i:i + fragment] for i in range(0, len(text) - fragment + 1, fragment)]
        forms["hex"] = [c.encode() for c in chunks]
        upper = [c.upper().encode() for c in chunks]
        for encoding, chunk_list in (("raw", forms["raw"]), ("hex", forms["hex"] + upper)):
            matched = sum(1 for c in chunk_list if c in data)
            if matched:
                hits.append({"canary": index, "encoding": encoding,
                             "matched_chunks": matched, "total_chunks": len(chunk_list)})
    return tuple(hits)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Finding:
    path: str
    status: str
    method: str = ""
    artifact_sha256: str = ""
    canaries_used: int = 0
    encodings: tuple = ()
    rationale: str = ""


def assess(findings, required=PATHS):
    """Account for every enumerated path; return fixed reason codes."""
    if type(findings) not in (list, tuple) or not all(isinstance(f, Finding) for f in findings):
        raise ValueError("findings")
    if type(required) is not tuple or not required or not set(required) <= set(PATHS):
        raise ValueError("required")
    reasons, notes, seen, observed = [], [], set(), False
    for f in findings:
        if f.path not in required:
            reasons.append("E_UNKNOWN_PATH")
            continue
        tag = f.path.upper()
        if f.path in seen:
            reasons.append("E_DUPLICATE_" + tag)
            continue
        seen.add(f.path)
        if f.status not in STATUSES:
            reasons.append("E_STATUS_" + tag)
        elif f.status == "not_applicable":
            if type(f.rationale) is str and TOKEN.fullmatch(f.rationale):
                notes.append("HUMAN_REVIEW_NA_" + tag)
            else:
                reasons.append("E_RATIONALE_" + tag)
        else:
            evidence = (type(f.method) is str and TOKEN.fullmatch(f.method) is not None
                        and type(f.artifact_sha256) is str and HEX.fullmatch(f.artifact_sha256) is not None
                        and type(f.canaries_used) is int and f.canaries_used >= 1
                        and type(f.encodings) is tuple and f.encodings
                        and set(f.encodings) <= ENCODINGS)
            if not evidence:
                reasons.append("E_EVIDENCE_" + tag)
            if f.status == "retention_observed":
                observed = True
                reasons.append("F_" + tag + "_RETENTION_OBSERVED")
    for path in required:
        if path not in seen:
            reasons.append("E_NOT_INSPECTED_" + path.upper())
    accounted = not any(r.startswith("E_") for r in reasons)
    if observed:
        status = "retention_observed"
    elif accounted:
        status = "no_retention_found_in_inspected_conditions"
    else:
        status = "incomplete"
    return {"claim_status": status, "reasons": tuple(reasons), "notes": tuple(notes),
            "absence_established": False, "deployment_authorized": False}


class Tests(unittest.TestCase):
    def clean(self, path, **changes):
        data = dict(path=path, status="inspected_clean", method="offline image inspection",
                    artifact_sha256=sha256_hex(path.encode()), canaries_used=4,
                    encodings=("raw", "hex"))
        data.update(changes)
        return Finding(**data)

    def all_clean(self):
        return [self.clean(p) for p in PATHS]

    def test_canaries_are_deterministic_distinct_and_synthetic(self):
        a, b = make_canaries(b"seed one"), make_canaries(b"seed one")
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), len(a))
        self.assertNotEqual(a, make_canaries(b"seed two"))
        self.assertTrue(all(c.startswith(MARKER) for c in a))
        for bad in [(b"", 1, 128), ("s", 1, 128), (b"s", 0, 128), (b"s", 65, 128), (b"s", 1, 63)]:
            with self.assertRaises(ValueError):
                make_canaries(*bad)

    def test_detects_raw_hex_and_partial_leaks(self):
        canaries = make_canaries(b"scan seed")
        noise = make_canaries(b"unrelated noise", count=1, size=1024)[0]
        body = canaries[1][len(MARKER):]
        self.assertEqual(scan_artifact(noise, canaries), ())
        raw = scan_artifact(noise[:200] + canaries[1] + noise[200:400], canaries)
        self.assertEqual([h["canary"] for h in raw], [1])
        self.assertEqual(raw[0]["matched_chunks"], raw[0]["total_chunks"])
        lower = scan_artifact(b"log: " + body.hex().encode(), canaries)
        upper = scan_artifact(b"log: " + body.hex().upper().encode(), canaries)
        self.assertTrue(lower and upper and lower[0]["encoding"] == "hex")
        for start in range(0, 60):
            leaked = body[start:start + 31]
            hits = scan_artifact(noise[:50] + leaked + noise[50:100], canaries)
            self.assertIn(1, [h["canary"] for h in hits], start)

    def test_documented_blind_spots_stay_blind(self):
        import base64
        canaries = make_canaries(b"scan seed")
        self.assertEqual(scan_artifact(base64.b64encode(canaries[0]), canaries), ())
        short_run = canaries[0][len(MARKER):][3:15]
        self.assertEqual(scan_artifact(b"x" * 20 + short_run, canaries), ())

    def test_scan_rejects_bad_options(self):
        canaries = make_canaries(b"scan seed")
        for args in [("text", canaries), (b"x", ()), (b"x", [canaries[0]]), (b"x", (b"plain",))]:
            with self.assertRaises(ValueError):
                scan_artifact(*args)
        for fragment in (7, 65, True):
            with self.assertRaises(ValueError):
                scan_artifact(b"x", canaries, fragment)

    def test_complete_clean_inventory_is_limited_not_absolute(self):
        r = assess(self.all_clean())
        self.assertEqual(r["claim_status"], "no_retention_found_in_inspected_conditions")
        self.assertFalse(r["absence_established"] or r["deployment_authorized"])
        self.assertEqual(r["reasons"], ())

    def test_missing_path_is_incomplete(self):
        r = assess(self.all_clean()[:-1])
        self.assertEqual(r["claim_status"], "incomplete")
        self.assertIn("E_NOT_INSPECTED_PERSISTENT_STORAGE", r["reasons"])

    def test_observed_retention_dominates(self):
        findings = self.all_clean()
        findings[3] = self.clean("swap", status="retention_observed")
        r = assess(findings)
        self.assertEqual(r["claim_status"], "retention_observed")
        self.assertIn("F_SWAP_RETENTION_OBSERVED", r["reasons"])
        partial = assess([self.clean("swap", status="retention_observed")])
        self.assertEqual(partial["claim_status"], "retention_observed")

    def test_evidence_and_rationale_requirements(self):
        cases = [dict(artifact_sha256=""), dict(artifact_sha256="ABC"), dict(method="x\ny"),
                 dict(canaries_used=0), dict(encodings=()), dict(encodings=("base64",))]
        for change in cases:
            findings = self.all_clean()
            findings[0] = self.clean("sensor_firmware", **change)
            r = assess(findings)
            self.assertIn("E_EVIDENCE_SENSOR_FIRMWARE", r["reasons"], change)
            self.assertEqual(r["claim_status"], "incomplete")
        findings = self.all_clean()
        findings[1] = Finding("accelerator_memory", "not_applicable")
        self.assertIn("E_RATIONALE_ACCELERATOR_MEMORY", assess(findings)["reasons"])
        findings[1] = Finding("accelerator_memory", "not_applicable", rationale="no accelerator in test unit")
        r = assess(findings)
        self.assertIn("HUMAN_REVIEW_NA_ACCELERATOR_MEMORY", r["notes"])
        self.assertEqual(r["claim_status"], "no_retention_found_in_inspected_conditions")

    def test_unknown_duplicate_and_bad_status(self):
        findings = self.all_clean() + [self.clean("swap")]
        self.assertIn("E_DUPLICATE_SWAP", assess(findings)["reasons"])
        findings = self.all_clean() + [Finding("cloud_backup", "inspected_clean")]
        self.assertIn("E_UNKNOWN_PATH", assess(findings)["reasons"])
        findings = self.all_clean()
        findings[2] = Finding("os_buffers", "looks fine")
        self.assertIn("E_STATUS_OS_BUFFERS", assess(findings)["reasons"])
        for bad in ("x", [object()]):
            with self.assertRaises(ValueError):
                assess(bad)
        with self.assertRaises(ValueError):
            assess([], required=("unknown path",))


if __name__ == "__main__":
    unittest.main()
