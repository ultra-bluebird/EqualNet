# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bench-method controls on a synthetic stand-in, plus read-only tree inspection.

The stand-in is NOT any real device. It exists to show that the inspection
method detects a known planted leak (positive control) and stays quiet for a
clean run (negative control). Nothing here touches real devices, networks,
vehicles, or people, and a negative scan never proves absence.
"""
import base64
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

MARKER = b"SYNTHETIC-NOT-PERSON-DATA:"
LEAK_MODES = (None, "crash_dump", "debug_log")
MAX_FILE_BYTES = 64 * 1024 * 1024


def make_frames(seed, count=4, size=256):
    """Deterministic synthetic frames from SHA-256 output only."""
    if type(seed) is not bytes or not seed or type(count) is not int or not 1 <= count <= 64 \
            or type(size) is not int or not 64 <= size <= 4096:
        raise ValueError("frame options")
    frames = []
    for i in range(count):
        body, counter = b"", 0
        while len(body) < size:
            body += hashlib.sha256(seed + i.to_bytes(4, "big") + counter.to_bytes(4, "big")).digest()
            counter += 1
        frames.append(MARKER + body[:size])
    return tuple(frames)


def scan_bytes(data, frames, fragment=16):
    """Aligned-fragment search in raw and hex-text forms (other forms unsearched)."""
    hits = []
    for i, frame in enumerate(frames):
        body = frame[len(MARKER):]
        raw = [body[j:j + fragment] for j in range(0, len(body) - fragment + 1, fragment)]
        text = body.hex()
        hexed = [text[j:j + fragment].encode() for j in range(0, len(text) - fragment + 1, fragment)]
        hexed += [c.upper() for c in hexed]
        if any(c in data for c in raw):
            hits.append((i, "raw"))
        if any(c in data for c in hexed):
            hits.append((i, "hex"))
    return tuple(hits)


def inspect_tree(root, frames, fragment=16, max_bytes=MAX_FILE_BYTES):
    """Read-only walk of a directory; symlinks are recorded, never followed."""
    if not isinstance(root, (str, os.PathLike)) or not os.path.isdir(root):
        raise ValueError("root")
    if type(frames) is not tuple or not frames or not all(
            type(f) is bytes and f.startswith(MARKER) and len(f) - len(MARKER) >= 64
            for f in frames):
        raise ValueError("frames")
    if type(fragment) is not int or not 8 <= fragment <= 64 or type(max_bytes) is not int \
            or max_bytes < 1:
        raise ValueError("options")
    scanned, skipped, hits = 0, [], []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.islink(path):
                skipped.append((rel, "SYMLINK"))
            elif not os.path.isfile(path):
                skipped.append((rel, "NOT_REGULAR"))
            elif os.path.getsize(path) > max_bytes:
                skipped.append((rel, "TOO_LARGE"))
            else:
                try:
                    with open(path, "rb") as handle:
                        data = handle.read()
                except OSError:
                    skipped.append((rel, "UNREADABLE"))
                    continue
                scanned += 1
                hits.extend({"file": rel, "canary": i, "encoding": e}
                            for i, e in scan_bytes(data, frames, fragment))
    return {"files_scanned": scanned, "skipped": tuple(skipped), "hits": tuple(hits),
            "searched_encodings": ("raw", "hex"), "negative_is_not_absence": True}


class StandIn:
    """Synthetic stand-in edge counter. Persists data only in leaky modes after a fault."""

    def __init__(self, workdir, leak_mode=None):
        if leak_mode not in LEAK_MODES:
            raise ValueError("leak_mode")
        self.dir, self.leak_mode = Path(workdir), leak_mode

    def process(self, frame, fault=False):
        if type(frame) is not bytes or not frame:
            raise ValueError("frame")
        if fault:
            raise RuntimeError("injected fault")
        return sum(frame[:32]) % 7

    def on_fault(self, frame):
        if self.leak_mode == "crash_dump":
            (self.dir / "crash.dump").write_bytes(frame)
        elif self.leak_mode == "debug_log":
            (self.dir / "debug.log").write_text("fault frame: " + frame.hex() + "\n")


def run_trial(stand_in, frames, fault_index=None):
    """Process frames, optionally injecting one fault; returns aggregates only."""
    if fault_index is not None and (type(fault_index) is not int
                                    or not 0 <= fault_index < len(frames)):
        raise ValueError("fault_index")
    counts = []
    for i, frame in enumerate(frames):
        try:
            counts.append(stand_in.process(frame, fault=(i == fault_index)))
        except RuntimeError:
            stand_in.on_fault(frame)
            counts.append(None)
    return tuple(counts)


def run_controls(workdir, seed=b"bench controls"):
    """Positive and negative controls on the stand-in, inside workdir only."""
    root = Path(workdir)
    if not root.is_dir():
        raise ValueError("workdir")
    frames = make_frames(seed)
    plans = {"clean_with_fault": (None, 1), "crash_dump_with_fault": ("crash_dump", 1),
             "debug_log_with_fault": ("debug_log", 2), "debug_log_without_fault": ("debug_log", None)}
    results = {}
    for name, (mode, fault) in plans.items():
        sub = root / name
        sub.mkdir()
        run_trial(StandIn(sub, mode), frames, fault)
        results[name] = inspect_tree(sub, frames)
    valid = (not results["clean_with_fault"]["hits"]
             and not results["debug_log_without_fault"]["hits"]
             and {h["file"] for h in results["crash_dump_with_fault"]["hits"]} == {"crash.dump"}
             and {(h["file"], h["encoding"]) for h in results["debug_log_with_fault"]["hits"]}
             == {("debug.log", "hex")})
    return {"controls_valid": valid, "results": results,
            "applies_to": "synthetic stand-in only"}


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.frames = make_frames(b"unit frames")

    def test_controls_detect_planted_leaks_and_stay_quiet_otherwise(self):
        report = run_controls(self.root)
        self.assertTrue(report["controls_valid"])
        results = report["results"]
        self.assertEqual(results["clean_with_fault"]["files_scanned"], 0)
        self.assertEqual(results["debug_log_without_fault"]["files_scanned"], 0)
        self.assertEqual(results["crash_dump_with_fault"]["hits"][0]["canary"], 1)
        self.assertEqual(results["debug_log_with_fault"]["hits"][0]["canary"], 2)

    def test_stand_in_returns_aggregates_only(self):
        counts = run_trial(StandIn(self.root), self.frames, 0)
        self.assertIsNone(counts[0])
        self.assertTrue(all(c in range(7) for c in counts[1:]))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_documented_blind_spots(self):
        (self.root / "b64.txt").write_bytes(base64.b64encode(self.frames[0]))
        (self.root / "short.bin").write_bytes(self.frames[1][len(MARKER) + 3:len(MARKER) + 15])
        result = inspect_tree(self.root, self.frames)
        self.assertEqual(result["hits"], ())
        self.assertEqual(result["files_scanned"], 2)
        self.assertTrue(result["negative_is_not_absence"])

    def test_partial_leak_of_guaranteed_length_is_found(self):
        body = self.frames[2][len(MARKER):]
        for start in range(0, 40, 7):
            (self.root / "partial.bin").write_bytes(b"x" * 9 + body[start:start + 31] + b"y" * 9)
            hits = inspect_tree(self.root, self.frames)["hits"]
            self.assertEqual([h["canary"] for h in hits], [2], start)

    def test_symlinks_are_recorded_not_followed(self):
        outside = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.unlink, outside.name)
        outside.write(self.frames[0])
        outside.close()
        try:
            os.symlink(outside.name, self.root / "link.bin")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        result = inspect_tree(self.root, self.frames)
        self.assertEqual(result["skipped"], (("link.bin", "SYMLINK"),))
        self.assertEqual(result["hits"], ())

    def test_oversized_files_are_skipped_and_reported(self):
        (self.root / "big.bin").write_bytes(self.frames[0])
        result = inspect_tree(self.root, self.frames, max_bytes=10)
        self.assertEqual(result["skipped"], (("big.bin", "TOO_LARGE"),))
        self.assertEqual(result["files_scanned"], 0)

    def test_inspection_does_not_modify_the_tree(self):
        (self.root / "a.bin").write_bytes(self.frames[0])
        before = (self.root / "a.bin").read_bytes(), sorted(p.name for p in self.root.iterdir())
        inspect_tree(self.root, self.frames)
        after = (self.root / "a.bin").read_bytes(), sorted(p.name for p in self.root.iterdir())
        self.assertEqual(before, after)

    def test_invalid_inputs(self):
        for args in [(self.root / "missing", self.frames), (self.root, ()), (self.root, [self.frames[0]]),
                     (self.root, (b"plain",))]:
            with self.assertRaises(ValueError):
                inspect_tree(*args)
        for options in (dict(fragment=7), dict(fragment=65), dict(max_bytes=0), dict(fragment=True)):
            with self.assertRaises(ValueError):
                inspect_tree(self.root, self.frames, **options)
        for bad in (b"", "s"):
            with self.assertRaises(ValueError):
                make_frames(bad)
        with self.assertRaises(ValueError):
            StandIn(self.root, "other")
        for fault in (-1, 4, True, 1.0):
            with self.assertRaises(ValueError):
                run_trial(StandIn(self.root), self.frames, fault)
        with self.assertRaises(ValueError):
            StandIn(self.root).process(b"")
        with self.assertRaises(ValueError):
            run_controls(self.root / "missing")


if __name__ == "__main__":
    unittest.main()
