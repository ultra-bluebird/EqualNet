# SPDX-License-Identifier: MIT OR Apache-2.0
"""Command-path analysis over a declared architecture model. Local analysis only.

The model is an input, not a discovery: nothing here scans, connects to, or tests
any real system. A finding of "no command path" means none exists IN THE MODEL
and only matters if the inventory is complete; absence in reality is never
established. Authorizations are checked and plans are produced, never executed.
"""
from collections import deque
from dataclasses import dataclass, field
import hashlib
import json
import re
import unittest

PLANES = ("physical", "observation", "research_compute", "governance")
SEMANTICS = ("telemetry", "control", "unknown")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,119}")
HEX = re.compile(r"[0-9a-f]{64}")
MAX_NODES = 200


@dataclass(frozen=True)
class Node:
    name: str
    plane: str
    actuator: bool = False
    capabilities: frozenset = frozenset()
    stores: frozenset = frozenset()
    dependencies: tuple = ()


@dataclass(frozen=True)
class Edge:
    name: str
    src: str
    dst: str
    semantics: str
    bidirectional: bool = False
    requires_credential: str | None = None
    requires_capability: str | None = None
    exposes_stored: bool = False


@dataclass(frozen=True)
class Model:
    nodes: tuple
    edges: tuple
    dependency_capabilities: dict = field(default_factory=dict)
    inventory_complete: bool = False


def _tok(v):
    return type(v) is str and TOKEN.fullmatch(v) is not None


def validate(model):
    if not isinstance(model, Model) or not model.nodes or len(model.nodes) > MAX_NODES:
        raise ValueError("model")
    names = [n.name for n in model.nodes if isinstance(n, Node)]
    if len(names) != len(model.nodes) or len(set(names)) != len(names) or not all(map(_tok, names)):
        raise ValueError("nodes")
    for n in model.nodes:
        if n.plane not in PLANES or type(n.actuator) is not bool or (n.actuator and n.plane != "physical") \
                or not all(_tok(c) for c in n.capabilities | n.stores) \
                or any(d not in model.dependency_capabilities for d in n.dependencies):
            raise ValueError("node " + n.name)
    edge_names = [e.name for e in model.edges if isinstance(e, Edge)]
    if len(edge_names) != len(model.edges) or len(set(edge_names)) != len(edge_names) \
            or not all(map(_tok, edge_names)):
        raise ValueError("edges")
    for e in model.edges:
        if e.src not in names or e.dst not in names or e.semantics not in SEMANTICS \
                or type(e.bidirectional) is not bool or type(e.exposes_stored) is not bool \
                or not all(x is None or _tok(x) for x in (e.requires_credential, e.requires_capability)):
            raise ValueError("edge " + e.name)
    if type(model.dependency_capabilities) is not dict or not all(
            _tok(k) and all(map(_tok, v)) for k, v in model.dependency_capabilities.items()) \
            or type(model.inventory_complete) is not bool:
        raise ValueError("dependencies")


def effective_capabilities(model, node):
    caps = set(node.capabilities)
    for d in node.dependencies:
        caps |= set(model.dependency_capabilities[d])
    return caps


def _search(model, start, allowed):
    by_name = {n.name: n for n in model.nodes}
    caps = {n.name: effective_capabilities(model, n) for n in model.nodes}
    first = (start.name, frozenset(start.stores))
    parent, queue, found = {first: None}, deque([first]), {}
    while queue:
        state = queue.popleft()
        here, creds = state
        for e in model.edges:
            if e.semantics not in allowed:
                continue
            targets = []
            if e.src == here:
                targets.append(e.dst)
            if e.bidirectional and e.dst == here:
                targets.append(e.src)
            for there in targets:
                if e.requires_credential is not None and e.requires_credential not in creds:
                    continue
                if e.requires_capability is not None and e.requires_capability not in caps[here]:
                    continue
                gained = creds | by_name[there].stores if e.exposes_stored else creds
                nxt = (there, frozenset(gained))
                if nxt in parent:
                    continue
                parent[nxt] = (state, e)
                queue.append(nxt)
                if by_name[there].actuator and there not in found:
                    path, cur = [], nxt
                    while parent[cur] is not None:
                        cur, edge = parent[cur]
                        path.append(edge)
                    found[there] = tuple(reversed(path))
    return found


def analyze(model):
    """Per non-physical start node and actuator: command paths and influence paths."""
    validate(model)
    findings = []
    for start in model.nodes:
        if start.plane == "physical":
            continue
        direct = _search(model, start, {"control", "unknown"})
        every = _search(model, start, set(SEMANTICS))
        for actuator, path in sorted(direct.items()):
            findings.append({"start": start.name, "actuator": actuator, "class": "command_path",
                             "edges": tuple(e.name for e in path),
                             "unknown_semantics": any(e.semantics == "unknown" for e in path)})
        for actuator, path in sorted(every.items()):
            if actuator not in direct:
                findings.append({"start": start.name, "actuator": actuator, "class": "influence_path",
                                 "edges": tuple(e.name for e in path), "unknown_semantics": False})
    if any(f["class"] == "command_path" for f in findings):
        overall = "command_path_found"
    elif findings:
        overall = "influence_path_needs_review"
    elif not model.inventory_complete:
        overall = "unresolved_inventory_incomplete"
    else:
        overall = "no_command_path_in_model"
    return {"overall": overall, "findings": tuple(findings),
            "absence_established": False, "deployment_authorized": False}


def single_edge_cuts(model):
    """Edges whose removal alone removes every command path (empty if none do)."""
    base = analyze(model)
    if base["overall"] != "command_path_found":
        return ()
    on_path = sorted({e for f in base["findings"] if f["class"] == "command_path" for e in f["edges"]})
    cuts = []
    for name in on_path:
        reduced = Model(model.nodes, tuple(e for e in model.edges if e.name != name),
                        model.dependency_capabilities, model.inventory_complete)
        if analyze(reduced)["overall"] != "command_path_found":
            cuts.append(name)
    return tuple(cuts)


def model_digest(model):
    """SHA-256 over a canonical JSON form of the model."""
    validate(model)
    body = {"nodes": sorted(({"name": n.name, "plane": n.plane, "actuator": n.actuator,
                              "capabilities": sorted(n.capabilities), "stores": sorted(n.stores),
                              "dependencies": sorted(n.dependencies)} for n in model.nodes),
                            key=lambda x: x["name"]),
            "edges": sorted(({"name": e.name, "src": e.src, "dst": e.dst, "semantics": e.semantics,
                              "bidirectional": e.bidirectional, "cred": e.requires_credential,
                              "cap": e.requires_capability, "exposes": e.exposes_stored}
                             for e in model.edges), key=lambda x: x["name"]),
            "dependencies": {k: sorted(v) for k, v in sorted(model.dependency_capabilities.items())},
            "inventory_complete": model.inventory_complete}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Authorization:
    approver: str
    model_sha256: str
    scope_edges: tuple
    not_before: int
    not_after: int


def plan_tests(model, auth, now):
    """Check an authorization and return a NON-executed synthetic test plan."""
    validate(model)
    reasons = []
    if not (isinstance(auth, Authorization) and _tok(auth.approver) and type(now) is int
            and type(auth.not_before) is int and type(auth.not_after) is int
            and type(auth.scope_edges) is tuple and auth.scope_edges
            and type(auth.model_sha256) is str and HEX.fullmatch(auth.model_sha256)):
        return {"approved": False, "reasons": ("E_AUTHORIZATION",), "plan": (), "executed": False}
    if auth.model_sha256 != model_digest(model):
        reasons.append("E_MODEL_CHANGED_SINCE_APPROVAL")
    if not auth.not_before <= now <= auth.not_after:
        reasons.append("E_OUTSIDE_TIME_WINDOW")
    known = {e.name for e in model.edges}
    if not set(auth.scope_edges) <= known:
        reasons.append("E_SCOPE_UNKNOWN_EDGE")
    if reasons:
        return {"approved": False, "reasons": tuple(reasons), "plan": (), "executed": False}
    witnessed = {e for f in analyze(model)["findings"] for e in f["edges"]}
    plan = tuple({"edge": name, "attempt": "synthetic_message_from_evidence_side",
                  "model_predicts_traversable": name in witnessed, "executed": False}
                 for name in sorted(auth.scope_edges))
    return {"approved": True, "reasons": (), "plan": plan, "executed": False}


def _base():
    nodes = (Node("flow_sensor", "physical"), Node("pump_ctrl", "physical", actuator=True),
             Node("valve_ctrl", "physical", actuator=True), Node("relay", "physical"),
             Node("sensor_gw", "observation"), Node("broker", "observation"),
             Node("analyzer", "research_compute"), Node("ledger", "governance"))
    edges = (Edge("sense", "flow_sensor", "sensor_gw", "telemetry"),
             Edge("ingest", "sensor_gw", "broker", "telemetry"),
             Edge("consume", "broker", "analyzer", "telemetry"),
             Edge("record", "analyzer", "ledger", "telemetry"))
    return nodes, edges


class Tests(unittest.TestCase):
    def model(self, extra_edges=(), extra_nodes=(), deps=None, complete=True, replace=None):
        nodes, edges = _base()
        nodes = tuple(replace.get(n.name, n) if replace else n for n in nodes) + tuple(extra_nodes)
        return Model(nodes, edges + tuple(extra_edges), deps or {}, complete)

    def test_clean_model_has_no_command_path_but_never_proves_absence(self):
        r = analyze(self.model())
        self.assertEqual((r["overall"], r["findings"]), ("no_command_path_in_model", ()))
        self.assertFalse(r["absence_established"] or r["deployment_authorized"])
        self.assertEqual(analyze(self.model(complete=False))["overall"], "unresolved_inventory_incomplete")

    def test_a_consumed_control_topic_creates_a_witnessed_command_path(self):
        r = analyze(self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control")]))
        self.assertEqual(r["overall"], "command_path_found")
        hit = [f for f in r["findings"] if f["start"] == "analyzer"][0]
        self.assertEqual((hit["actuator"], hit["edges"], hit["class"]), ("valve_ctrl", ("setpoints",), "command_path"))
        starts = {f["start"] for f in r["findings"]}
        self.assertIn("analyzer", starts)

    def test_direction_matters(self):
        back = analyze(self.model([Edge("status", "valve_ctrl", "analyzer", "control")]))
        self.assertEqual(back["overall"], "no_command_path_in_model")
        both = analyze(self.model([Edge("console", "analyzer", "valve_ctrl", "control", bidirectional=True)]))
        self.assertEqual(both["overall"], "command_path_found")
        reverse = analyze(self.model([Edge("console", "valve_ctrl", "analyzer", "control", bidirectional=True)]))
        self.assertEqual(reverse["overall"], "command_path_found")
        self.assertEqual({(f["start"], f["class"], f["edges"]) for f in reverse["findings"]},
                         {("analyzer", "command_path", ("console",)),
                          ("sensor_gw", "influence_path", ("ingest", "consume", "console")),
                          ("broker", "influence_path", ("consume", "console"))})
        self.assertEqual({(f["start"], f["class"]) for f in both["findings"]},
                         {("analyzer", "command_path"), ("sensor_gw", "influence_path"), ("broker", "influence_path")})

    def test_credentials_gate_edges_and_can_be_harvested(self):
        jump = Node("jump_host", "observation", stores=frozenset({"valve_key"}))
        ssh = Edge("ssh", "jump_host", "valve_ctrl", "control", requires_credential="valve_key")
        share = Edge("share", "analyzer", "jump_host", "telemetry", exposes_stored=True)
        shell = Edge("analyzer_ssh", "analyzer", "jump_host", "control", exposes_stored=True)
        without = analyze(self.model([ssh], [Node("jump_host", "observation")]))
        self.assertEqual(without["overall"], "no_command_path_in_model")
        with_key = analyze(self.model([ssh, shell], [jump]))
        by_start = {f["start"]: f["edges"] for f in with_key["findings"] if f["class"] == "command_path"}
        self.assertEqual(by_start["jump_host"], ("ssh",))
        self.assertEqual(by_start["analyzer"], ("analyzer_ssh", "ssh"))
        passive = analyze(self.model([ssh, Edge("share", "analyzer", "jump_host", "control")], [jump]))
        self.assertNotIn("analyzer", {f["start"] for f in passive["findings"]})
        self.assertEqual(passive["overall"], "command_path_found")

    def test_dependency_capabilities_enlarge_reach(self):
        node = Node("analyzer", "research_compute", dependencies=("toolkit",))
        shell = Edge("maint_shell", "analyzer", "valve_ctrl", "control", requires_capability="exec")
        deps = {"toolkit": frozenset({"exec"})}
        self.assertEqual(analyze(self.model([shell], deps=deps, replace={"analyzer": node}))["overall"],
                         "command_path_found")
        self.assertEqual(analyze(self.model([shell], deps={"toolkit": frozenset()}, replace={"analyzer": node}))["overall"],
                         "no_command_path_in_model")
        self.assertEqual(analyze(self.model([shell]))["overall"], "no_command_path_in_model")

    def test_unknown_semantics_is_treated_conservatively(self):
        r = analyze(self.model([Edge("mystery", "analyzer", "pump_ctrl", "unknown")]))
        hit = [f for f in r["findings"] if f["start"] == "analyzer"][0]
        self.assertEqual((r["overall"], hit["class"], hit["unknown_semantics"]), ("command_path_found", "command_path", True))

    def test_influence_through_a_telemetry_hop_needs_review_not_a_verdict(self):
        r = analyze(self.model([Edge("to_relay", "analyzer", "relay", "telemetry"),
                                Edge("relay_out", "relay", "valve_ctrl", "control")]))
        self.assertEqual(r["overall"], "influence_path_needs_review")
        hit = [f for f in r["findings"] if f["start"] == "analyzer"][0]
        self.assertEqual((hit["class"], hit["edges"]), ("influence_path", ("to_relay", "relay_out")))

    def test_single_edge_cuts(self):
        one = self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control")])
        self.assertEqual(single_edge_cuts(one), ("setpoints",))
        two = self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control"),
                          Edge("console", "analyzer", "valve_ctrl", "control", bidirectional=True)])
        self.assertEqual(single_edge_cuts(two), ())
        self.assertEqual(single_edge_cuts(self.model()), ())
        nodes, edges = _base()
        no_upstream = Model(nodes, tuple(e for e in edges if e.name != "consume")
                            + (Edge("setpoints", "analyzer", "valve_ctrl", "control"),), {}, True)
        self.assertEqual({f["class"] for f in analyze(no_upstream)["findings"]}, {"command_path"})
        self.assertEqual(single_edge_cuts(no_upstream), ("setpoints",))

    def test_authorization_binds_to_the_model_and_never_executes(self):
        m = self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control")])
        auth = Authorization("reviewer one", model_digest(m), ("setpoints", "record"), 100, 200)
        ok = plan_tests(m, auth, 150)
        self.assertTrue(ok["approved"])
        self.assertFalse(ok["executed"] or any(p["executed"] for p in ok["plan"]))
        self.assertEqual({p["edge"]: p["model_predicts_traversable"] for p in ok["plan"]},
                         {"setpoints": True, "record": False})
        changed = self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control"),
                              Edge("extra", "analyzer", "relay", "telemetry")])
        self.assertIn("E_MODEL_CHANGED_SINCE_APPROVAL", plan_tests(changed, auth, 150)["reasons"])
        self.assertIn("E_OUTSIDE_TIME_WINDOW", plan_tests(m, auth, 201)["reasons"])
        self.assertIn("E_OUTSIDE_TIME_WINDOW", plan_tests(m, auth, 99)["reasons"])
        self.assertTrue(plan_tests(m, auth, 100)["approved"])
        self.assertTrue(plan_tests(m, auth, 200)["approved"])
        every = tuple(e.name for e in m.edges)
        full = plan_tests(m, Authorization("reviewer one", model_digest(m), every, 100, 200), 150)
        self.assertTrue(full["approved"])
        self.assertEqual(len(full["plan"]), len(m.edges))
        self.assertIn("E_SCOPE_UNKNOWN_EDGE", plan_tests(m, Authorization("r", model_digest(m), ("nope",), 1, 9), 5)["reasons"])
        for bad in (Authorization("r", "ABC", ("record",), 1, 9), Authorization("r", model_digest(m), (), 1, 9), "text"):
            self.assertEqual(plan_tests(m, bad, 5)["reasons"], ("E_AUTHORIZATION",))
        self.assertEqual(model_digest(m), model_digest(self.model([Edge("setpoints", "analyzer", "valve_ctrl", "control")])))
        self.assertNotEqual(model_digest(m), model_digest(self.model()))

    def test_node_limit_boundary(self):
        nodes, edges = _base()
        padding = tuple(Node("pad %d" % i, "observation") for i in range(MAX_NODES - len(nodes)))
        self.assertEqual(analyze(Model(nodes + padding, edges, {}, True))["overall"], "no_command_path_in_model")
        with self.assertRaises(ValueError):
            analyze(Model(nodes + padding + (Node("one more", "observation"),), edges, {}, True))

    def test_invalid_models_are_rejected(self):
        nodes, edges = _base()
        bad = [Model((), edges), Model(nodes + (nodes[0],), edges),
               Model(nodes, edges + (Edge("sense", "flow_sensor", "sensor_gw", "telemetry"),)),
               Model(nodes, edges + (Edge("x", "ghost", "analyzer", "control"),)),
               Model(nodes, edges + (Edge("x", "analyzer", "relay", "maybe"),)),
               Model(nodes + (Node("rogue", "governance", actuator=True),), edges),
               Model(nodes + (Node("n", "observation", dependencies=("missing",)),), edges),
               Model(nodes, edges, {"d": frozenset({"bad\nname"})}), "model"]
        for m in bad:
            with self.assertRaises(ValueError):
                analyze(m)


if __name__ == "__main__":
    unittest.main()
