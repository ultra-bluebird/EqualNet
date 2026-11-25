# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independence checks for a portfolio of research objects (synthetic, local).

Three checks: (1) parse the declared optional-connection column and confirm every edge is
well formed and no cell reads as a requirement; (2) statically scan module source for
hidden execution dependencies (imports of sibling modules, file, network, process, or
environment access, dynamic imports); (3) score an independent reconstruction of an object
against a reference without credit for using other objects' results. Edges are optional
opportunities for comparison, never prerequisites. Static scanning can miss dependencies.
"""
import ast
import re
import sys
import unittest

N_OBJECTS = 30
REQUIRED_WORDS = ("requires", "depends on", "prerequisite", "must be completed", "after object")
ELEMENTS = ("question", "local_inputs", "authorization_boundary", "evaluation_method", "missing_evidence")
STDLIB = set(sys.stdlib_module_names)


def parse_connections(cells, n=N_OBJECTS):
    """cells: {object: cell text}. Returns (directed edge set, objects that compare with every object)."""
    if type(cells) is not dict or not cells:
        raise ValueError("cells")
    edges, everyone = set(), set()
    for obj, cell in cells.items():
        if type(obj) is not int or not 1 <= obj <= n or type(cell) is not str:
            raise ValueError("cell")
        if "every object" in cell.lower():
            everyone.add(obj)
            continue
        for part in cell.split(";"):
            m = re.match(r"\s*(\d+)\s+\S", part)
            if not m:
                raise ValueError("connection")
            target = int(m.group(1))
            if not 1 <= target <= n or target == obj:
                raise ValueError("target")
            edges.add((obj, target))
    return edges, everyone


def asymmetric(edges):
    return sorted(e for e in edges if (e[1], e[0]) not in edges)


def required_edge_flags(cells):
    flags = []
    for obj, cell in sorted(cells.items()):
        text = cell.lower().replace("no prerequisite", "")
        if any(w in text for w in REQUIRED_WORDS):
            flags.append(obj)
    return flags


def reachable(edges, start):
    seen, stack = {start}, [start]
    while stack:
        a = stack.pop()
        for x, y in edges:
            if x == a and y not in seen:
                seen.add(y)
                stack.append(y)
    return seen


def scan_module_source(src, portfolio_modules):
    """Static indicators of hidden dependencies in one module's source."""
    tree = ast.parse(src)
    found = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".")[0]]
        for name in names:
            if name in portfolio_modules:
                found.add("PORTFOLIO_IMPORT:" + name)
            elif name not in STDLIB:
                found.add("THIRD_PARTY:" + name)
            if name in ("socket", "urllib", "http", "requests", "ftplib", "smtplib"):
                found.add("NETWORK")
            if name in ("subprocess", "multiprocessing"):
                found.add("PROCESS_SPAWN")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in ("open", "__import__", "exec", "eval"):
                found.add({"open": "FILE_ACCESS", "__import__": "DYNAMIC_IMPORT"}.get(f.id, "DYNAMIC_EXECUTION"))
            if isinstance(f, ast.Attribute) and f.attr == "import_module":
                found.add("DYNAMIC_IMPORT")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os" \
                and node.attr in ("environ", "getenv"):
            found.add("ENVIRONMENT_ACCESS")
    return sorted(found)


def score_reconstruction(reference, reviewer, own_object, mentioned_objects):
    """Jaccard overlap per element; any mention of another object is flagged, not rewarded."""
    if type(reference) is not dict or set(reference) != set(ELEMENTS) or type(reviewer) is not dict \
            or not set(reviewer) <= set(ELEMENTS) or not all(type(v) is frozenset and v for v in reference.values()) \
            or not all(type(v) is frozenset for v in reviewer.values()) or type(own_object) is not int \
            or not all(type(o) is int for o in mentioned_objects):
        raise ValueError("reconstruction inputs")
    scores = {}
    for e in ELEMENTS:
        r = reviewer.get(e, frozenset())
        scores[e] = len(r & reference[e]) / len(r | reference[e])
    foreign = sorted(set(mentioned_objects) - {own_object})
    flags = (["USED_OTHER_OBJECTS"] if foreign else []) + (["ELEMENT_MISSING"] if set(ELEMENTS) - set(reviewer) else [])
    return {"scores": scores, "mean": sum(scores.values()) / len(ELEMENTS), "foreign_objects": foreign, "flags": tuple(flags)}


CELLS = {1: "9 freshness claims; 12 accessible explanations; 28 provenance",
         2: "3 interval coverage; 4 accumulated error; 5 alternatives", 3: "2 fusion assumptions; 11 representativeness",
         4: "8 replay behavior; 15 calibration findings", 5: "6 persistence; 24 burden accounting",
         6: "7 release risk; 14 isolation", 7: "9 time precision; 28 retention", 8: "4 conservation; 29 overload",
         9: "1 supported claims; 12 comprehension", 10: "11 placement; 1 inference labels",
         11: "10 model assumptions; 3 coverage", 12: "9 stale states; 13 decision pressure",
         13: "12 information design; 19 heat context", 14: "6 egress; 29 fault isolation",
         15: "4 correction history; 1 degraded claims", 16: "17 supply constraints; 21 causal boundaries",
         17: "16 burden pathways; 19 travel access", 18: "16 downstream hypotheses; 21 spillovers",
         19: "13 usable alternatives; 22 resource boundaries", 20: "16 hypothesis selection; 17 implementation conditions",
         21: "16 dynamics; 18 immediate outcomes", 22: "23 ecological outcomes; 24 absolute burdens",
         23: "19 access benefit; 22 water demand", 24: "5 sensing options; 25 thermal service",
         25: "24 accounting; 26 boundary claims", 26: "22 water accounting; 23 ecological claims",
         27: "1 claim scope; 28 governance limits", 28: "1 evidence contracts; 7 disclosure",
         29: "8 stream correctness; 14 non-actuation", 30: "Optional comparison with every object; no prerequisite"}


class Tests(unittest.TestCase):
    def test_the_declared_connection_column_is_well_formed_and_purely_optional(self):
        edges, everyone = parse_connections(CELLS)
        self.assertEqual((len(edges), everyone), (60, {30}))
        self.assertEqual(required_edge_flags(CELLS), [])
        self.assertTrue(all(1 <= a <= 30 and 1 <= b <= 30 and a != b for a, b in edges))
        asym = asymmetric(edges)
        self.assertIn((1, 12), asym)
        self.assertNotIn((1, 9), asym)
        self.assertNotIn((1, 28), asym)
        self.assertTrue(set(asym) <= edges)
        self.assertEqual(len(edges) - len(asym), len([e for e in edges if (e[1], e[0]) in edges]))

    def test_optional_edges_connect_objects_without_creating_a_prerequisite(self):
        edges, _ = parse_connections(CELLS)
        group = reachable(edges, 1)
        self.assertIn(28, group)
        self.assertIn(7, group)
        self.assertNotIn(30, group)
        self.assertGreater(len(reachable(edges, 16)), 4)
        self.assertEqual(reachable(set(), 3), {3})

    def test_requirement_language_and_bad_edges_are_caught(self):
        bad = dict(CELLS)
        bad[12] = "9 stale states; 13 decision pressure requires object 9 results"
        self.assertEqual(required_edge_flags(bad), [12])
        bad[7] = "after object 9 completes"
        self.assertEqual(required_edge_flags(bad), [7, 12])
        for cells in ({5: "5 self; 6 other"}, {5: "31 missing"}, {5: "no number here"}, {0: "1 x"}, {}, {5: 7}):
            with self.assertRaises(ValueError):
                parse_connections(cells)

    def test_source_scan_flags_hidden_dependencies(self):
        mods = {"claim_review", "fusion_review"}
        self.assertEqual(scan_module_source("import math\nfrom dataclasses import dataclass\nx = 1\n", mods), [])
        self.assertEqual(scan_module_source("import claim_review\n", mods), ["PORTFOLIO_IMPORT:claim_review"])
        self.assertEqual(scan_module_source("from fusion_review import fuse_two\n", mods), ["PORTFOLIO_IMPORT:fusion_review"])
        self.assertEqual(scan_module_source("import numpy as np\n", mods), ["THIRD_PARTY:numpy"])
        self.assertEqual(scan_module_source("with open('f') as h:\n    pass\n", mods), ["FILE_ACCESS"])
        self.assertEqual(scan_module_source("import os\nx = os.environ['A']\n", mods), ["ENVIRONMENT_ACCESS"])
        self.assertEqual(scan_module_source("import subprocess\n", mods), ["PROCESS_SPAWN"])
        self.assertEqual(scan_module_source("import socket\n", mods), ["NETWORK"])
        self.assertEqual(scan_module_source("import importlib\nimportlib.import_module('x')\n", mods), ["DYNAMIC_IMPORT"])
        self.assertEqual(scan_module_source("__import__('x')\n", mods), ["DYNAMIC_IMPORT"])
        self.assertIn("DYNAMIC_EXECUTION", scan_module_source("eval('1')\n", mods))
        with self.assertRaises(SyntaxError):
            scan_module_source("def (:\n", mods)

    def test_reconstruction_scoring_and_use_of_other_objects(self):
        ref = {e: frozenset({"a", "b"}) for e in ELEMENTS}
        same = score_reconstruction(ref, dict(ref), 5, [5])
        self.assertEqual((same["mean"], same["flags"], same["foreign_objects"]), (1.0, (), []))
        half = score_reconstruction(ref, {**ref, "question": frozenset({"a", "c"})}, 5, [5, 5])
        self.assertAlmostEqual(half["scores"]["question"], 1 / 3)
        partial = score_reconstruction(ref, {"question": frozenset({"a", "b"})}, 5, [])
        self.assertEqual((partial["scores"]["local_inputs"], partial["flags"]), (0.0, ("ELEMENT_MISSING",)))
        foreign = score_reconstruction(ref, dict(ref), 5, [5, 9, 12])
        self.assertEqual((foreign["foreign_objects"], foreign["flags"]), ([9, 12], ("USED_OTHER_OBJECTS",)))
        for args in (({}, {}, 1, []), (ref, {"nope": frozenset()}, 1, []), (ref, {"question": {"a"}}, 1, []),
                     (ref, dict(ref), "5", []), (ref, dict(ref), 5, ["9"]), ({**ref, "question": frozenset()}, dict(ref), 5, [])):
            with self.assertRaises(ValueError):
                score_reconstruction(*args)


if __name__ == "__main__":
    unittest.main()
