# SPDX-License-Identifier: MIT OR Apache-2.0
"""Metadata-only provenance ledger with corrections, deletion receipts, and policy-revision checks.

The ledger stores hashes and opaque tokens, never payloads. Restricted payloads live in a
separate store; deleting one removes its salt too, so the ledger chain still verifies while
the content can no longer be confirmed. A SHA-256 chain shows tampering, not who wrote an
entry or whether it is true. Policy revisions inherit by default but cannot silently broaden
permissions or remove a protection. Local, in-memory, synthetic use only.
"""
from dataclasses import dataclass
import hashlib
import json
import os
import re
import unittest

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
SUBJECT = re.compile(r"s[0-9a-f]{16,32}")
HEX = re.compile(r"[0-9a-f]{64}")
KINDS = ("policy_revision", "decision", "correction", "deletion_receipt")
GENESIS = "0" * 64


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class PolicyRevision:
    permissions: frozenset
    protections: frozenset
    retention_days: int
    purposes: frozenset


def _check_rev(r):
    if not (isinstance(r, PolicyRevision) and all(type(s) is frozenset and all(type(x) is str and TOKEN.fullmatch(x) for x in s)
                                                  for s in (r.permissions, r.protections, r.purposes))
            and type(r.retention_days) is int and r.retention_days >= 0):
        raise ValueError("revision")


def revision_sha256(r):
    _check_rev(r)
    return sha256_hex(canonical({"permissions": sorted(r.permissions), "protections": sorted(r.protections),
                                 "retention_days": r.retention_days, "purposes": sorted(r.purposes)}))


def check_revision(old, new, review_sha256=None):
    """Reasons a revision may not be adopted. Protections are tightening-only, with no override."""
    _check_rev(old)
    _check_rev(new)
    if review_sha256 is not None and not (type(review_sha256) is str and HEX.fullmatch(review_sha256)):
        raise ValueError("review")
    reasons = []
    if old.protections - new.protections:
        reasons.append("PROTECTION_REMOVED")
    for broadened, code in ((new.permissions - old.permissions, "PERMISSION_BROADENED_WITHOUT_REVIEW"),
                            (new.purposes - old.purposes, "PURPOSE_WIDENED_WITHOUT_REVIEW"),
                            (new.retention_days > old.retention_days, "RETENTION_LONGER_WITHOUT_REVIEW")):
        if broadened and review_sha256 is None:
            reasons.append(code)
    return tuple(reasons)


class RestrictedStore:
    """Holds payload and salt together; deletion removes both."""

    def __init__(self):
        self._items = {}

    def put(self, key, payload, salt=None):
        if type(key) is not str or type(payload) is not bytes or (salt is not None and type(salt) is not bytes):
            raise ValueError("put")
        salt = os.urandom(16) if salt is None else salt
        self._items[key] = (salt, payload)
        return sha256_hex(salt + payload)

    def verify(self, key, commitment):
        if key not in self._items:
            return None
        salt, payload = self._items[key]
        return sha256_hex(salt + payload) == commitment

    def delete(self, key):
        if key not in self._items:
            raise ValueError("absent")
        del self._items[key]

    def has(self, key):
        return key in self._items


def dictionary_attack(commitment, candidates, salt=None):
    """Try candidate payloads against a commitment; succeeds only if the salt is known or absent."""
    for c in candidates:
        if sha256_hex((salt or b"") + c) == commitment:
            return c
    return None


class Ledger:
    def __init__(self):
        self._entries, self._revisions, self._latest = [], {}, None

    def _add(self, kind, subject, scope, policy_sha, commitment, ref):
        if not (kind in KINDS and (subject is None or (type(subject) is str and SUBJECT.fullmatch(subject)))
                and type(scope) is tuple and all(type(s) is str and TOKEN.fullmatch(s) for s in scope)
                and (commitment is None or (type(commitment) is str and HEX.fullmatch(commitment)))
                and (ref is None or (type(ref) is int and 0 <= ref < len(self._entries)))):
            raise ValueError("entry")
        body = {"seq": len(self._entries), "kind": kind, "subject": subject, "scope": sorted(scope),
                "policy": policy_sha, "commitment": commitment, "ref": ref,
                "prev": self._entries[-1]["hash"] if self._entries else GENESIS}
        entry = {**body, "hash": sha256_hex(canonical(body))}
        self._entries.append(entry)
        return dict(entry)

    def append_revision(self, rev, review_sha256=None):
        sha = revision_sha256(rev)
        if self._latest is not None:
            reasons = check_revision(self._revisions[self._latest], rev, review_sha256)
            if reasons:
                raise ValueError(",".join(reasons))
        entry = self._add("policy_revision", None, (), sha, review_sha256, None)
        self._revisions[sha], self._latest = rev, sha
        return entry

    def append(self, kind, subject, scope, commitment=None, ref=None, policy_sha=None):
        if kind == "policy_revision":
            raise ValueError("use append_revision")
        policy_sha = policy_sha or self._latest
        if policy_sha not in self._revisions:
            raise ValueError("UNKNOWN_POLICY_REVISION")
        if kind in ("correction", "deletion_receipt") and ref is None:
            raise ValueError("ref required")
        if kind == "deletion_receipt" and commitment != self._entries[ref]["commitment"]:
            raise ValueError("receipt must restate the deleted commitment")
        return self._add(kind, subject, scope, policy_sha, commitment, ref)

    def entries(self):
        return tuple(dict(e) for e in self._entries)

    @staticmethod
    def verify(entries):
        prev = GENESIS
        for i, e in enumerate(entries):
            try:
                body = {k: e[k] for k in ("seq", "kind", "subject", "scope", "policy", "commitment", "ref", "prev")}
                if e["seq"] != i or e["prev"] != prev or e["hash"] != sha256_hex(canonical(body)):
                    return False
            except (KeyError, TypeError):
                return False
            prev = e["hash"]
        return True

    def current_view(self, subject):
        """Latest decision or correction for a subject, its ancestry, and which payloads were deleted."""
        mine = [e for e in self._entries if e["subject"] == subject and e["kind"] in ("decision", "correction")]
        deleted = {e["ref"] for e in self._entries if e["kind"] == "deletion_receipt"}
        if not mine:
            return None
        latest = mine[-1]
        chain, cur = [latest["seq"]], latest
        while cur["kind"] == "correction":
            cur = self._entries[cur["ref"]]
            chain.append(cur["seq"])
        return {"latest": latest["seq"], "ancestry": tuple(chain), "payload_deleted": latest["seq"] in deleted,
                "authenticity_established": False, "truthfulness_established": False}


class Tests(unittest.TestCase):
    R1 = PolicyRevision(frozenset({"aggregate_report"}), frozenset({"refusal_free", "human_fallback"}), 30,
                        frozenset({"service_evaluation"}))
    S = "s" + "ab" * 8

    def ledger(self):
        led = Ledger()
        led.append_revision(self.R1)
        return led

    def test_chain_detects_edits_deletions_and_reordering(self):
        led = self.ledger()
        led.append("decision", self.S, ("scope a",), sha256_hex(b"x"))
        led.append("decision", self.S, ("scope a",), sha256_hex(b"y"))
        e = led.entries()
        self.assertTrue(Ledger.verify(e))
        edited = [dict(x) for x in e]
        edited[1]["scope"] = ["scope b"]
        self.assertFalse(Ledger.verify(edited))
        self.assertFalse(Ledger.verify(e[1:]))
        self.assertFalse(Ledger.verify([e[0], e[2], e[1]]))
        self.assertFalse(Ledger.verify([{"seq": 0}]))

    def test_deletion_keeps_the_chain_valid_but_content_can_no_longer_be_confirmed(self):
        store, led = RestrictedStore(), self.ledger()
        c = store.put("k1", b"restricted note")
        d = led.append("decision", self.S, ("scope a",), c)
        self.assertTrue(store.verify("k1", c))
        store.delete("k1")
        receipt = led.append("deletion_receipt", self.S, ("scope a",), c, ref=d["seq"])
        self.assertIsNone(store.verify("k1", c))
        self.assertTrue(Ledger.verify(led.entries()))
        self.assertTrue(led.current_view(self.S)["payload_deleted"])
        self.assertNotIn("payload", receipt)
        with self.assertRaises(ValueError):
            store.delete("k1")
        with self.assertRaises(ValueError):
            led.append("deletion_receipt", self.S, (), sha256_hex(b"other"), ref=d["seq"])

    def test_unsalted_commitments_of_guessable_payloads_can_be_reversed_but_salted_ones_cannot(self):
        guesses = [b"yes", b"no", b"maybe"]
        unsalted = sha256_hex(b"maybe")
        self.assertEqual(dictionary_attack(unsalted, guesses), b"maybe")
        store = RestrictedStore()
        salted = store.put("k", b"maybe", salt=b"\x01" * 16)
        self.assertIsNone(dictionary_attack(salted, guesses))
        self.assertEqual(dictionary_attack(salted, guesses, salt=b"\x01" * 16), b"maybe")
        self.assertNotEqual(store.put("a", b"same"), store.put("b", b"same"))
        store.delete("k")
        self.assertIsNone(dictionary_attack(salted, guesses))

    def test_corrections_preserve_the_original_and_expose_ancestry(self):
        led = self.ledger()
        a = led.append("decision", self.S, ("scope a",), sha256_hex(b"v1"))
        b = led.append("correction", self.S, ("scope a",), sha256_hex(b"v2"), ref=a["seq"])
        c = led.append("correction", self.S, ("scope a",), sha256_hex(b"v3"), ref=b["seq"])
        view = led.current_view(self.S)
        self.assertEqual((view["latest"], view["ancestry"]), (c["seq"], (c["seq"], b["seq"], a["seq"])))
        self.assertEqual(led.entries()[a["seq"]]["commitment"], sha256_hex(b"v1"))
        self.assertFalse(view["authenticity_established"] or view["truthfulness_established"])
        self.assertIsNone(led.current_view("s" + "cd" * 8))
        with self.assertRaises(ValueError):
            led.append("correction", self.S, (), sha256_hex(b"z"), ref=99)
        with self.assertRaises(ValueError):
            led.append("correction", self.S, (), sha256_hex(b"z"))

    def test_policy_inheritance_cannot_silently_broaden_or_remove_protections(self):
        r = self.R1
        same = PolicyRevision(r.permissions, r.protections, r.retention_days, r.purposes)
        self.assertEqual(check_revision(r, same), ())
        narrower = PolicyRevision(frozenset(), r.protections | {"extra_floor"}, 7, r.purposes)
        self.assertEqual(check_revision(r, narrower), ())
        broader = PolicyRevision(r.permissions | {"share_externally"}, r.protections, 90, r.purposes | {"marketing"})
        self.assertEqual(set(check_revision(r, broader)), {"PERMISSION_BROADENED_WITHOUT_REVIEW",
                                                           "PURPOSE_WIDENED_WITHOUT_REVIEW", "RETENTION_LONGER_WITHOUT_REVIEW"})
        self.assertEqual(check_revision(r, broader, sha256_hex(b"review")), ())
        weaker = PolicyRevision(r.permissions, frozenset({"human_fallback"}), r.retention_days, r.purposes)
        self.assertEqual(check_revision(r, weaker, sha256_hex(b"review")), ("PROTECTION_REMOVED",))
        led = self.ledger()
        with self.assertRaises(ValueError):
            led.append_revision(weaker, sha256_hex(b"review"))
        led.append_revision(broader, sha256_hex(b"review"))
        self.assertEqual(len(led.entries()), 2)
        self.assertEqual(led.entries()[1]["commitment"], sha256_hex(b"review"))

    def test_decisions_must_pin_a_known_revision_and_entries_stay_metadata_only(self):
        led = self.ledger()
        with self.assertRaises(ValueError):
            led.append("decision", self.S, ("a",), policy_sha=sha256_hex(b"unknown"))
        old = led.entries()[0]["policy"]
        led.append_revision(PolicyRevision(self.R1.permissions, self.R1.protections, 10, self.R1.purposes))
        pinned = led.append("decision", self.S, ("a",), policy_sha=old)
        self.assertEqual(pinned["policy"], old)
        for args in (("decision", "alice", ("a",)), ("decision", self.S, ("a\nb",)), ("memo", self.S, ("a",)),
                     ("decision", self.S, ("a",), "NOT-HEX")):
            with self.assertRaises(ValueError):
                led.append(*args)
        with self.assertRaises(ValueError):
            led.append("policy_revision", None, ())

    def test_invalid_revisions(self):
        for bad in (PolicyRevision(frozenset({"x\n"}), frozenset(), 1, frozenset()), PolicyRevision(frozenset(), frozenset(), -1, frozenset()),
                    PolicyRevision({"a"}, frozenset(), 1, frozenset()), "rev"):
            with self.assertRaises(ValueError):
                revision_sha256(bad)
        with self.assertRaises(ValueError):
            check_revision(self.R1, self.R1, "ABC")
        self.assertEqual(revision_sha256(self.R1), revision_sha256(PolicyRevision(
            frozenset({"aggregate_report"}), frozenset({"human_fallback", "refusal_free"}), 30, frozenset({"service_evaluation"}))))


if __name__ == "__main__":
    unittest.main()
