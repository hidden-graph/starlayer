"""JSON form of the plan: proof that ``Plan`` / ``Shape`` / ``Path`` serialise, for a Rust executor to read.

``plan_to_json(plan)`` returns a JSON-serialisable ``dict`` (format version ``FORMAT_VERSION``); ``plan_from_json`` rebuilds a
``Plan`` whose shapes compare equal (as ``Shape`` dataclasses) to the originals. Spec of the format and the executor
contract: ``docs/working/shacl-engine-plan-format.md``.

What is serialised:

* ``shapes``: every shape reachable from the declared shape nodes (through ``sh:property``, ``sh:node``, ``sh:not``,
  ``sh:and/or/xone`` lists, ``sh:qualifiedValueShape``, ``sh:memberShape``, ``sh:reifierShape``, ``sh:targetWhere``, rule
  ``sh:condition``, and shape references inside node expressions), as ``Shape`` fields with terms in the tagged form below.
* ``declared``: the declared shape nodes in the order the executor visits them (``Plan.all_shape_nodes``).
* ``errors``: shapes that failed to build (``ShapeError``), so a malformed shape is a recorded plan error.
* ``rules`` / ``rule_sets`` / ``entailment``: ``rules.read_rule`` records, rule sets and ``sh:entailment`` values.
* ``prefixes``: the SPARQL prefix map per ``sh:prefixes`` holder and the default map (``sh:declare`` fallback).
* ``graph``: the *term store*: the triples of the shapes graph that expressions, lists, SPARQL nodes, SPARQL-based
  constraint component declarations, custom functions, rules and prefix declarations are read from. The ``Shape``
  fields are data; node expressions and SPARQL queries stay RDF subgraphs inside this store (the engine does not compile
  them to a tree yet).

Terms: ``{"t":"iri","v":...}``, ``{"t":"bnode","v":...}``, ``{"t":"lit","v":lexical,"dt":iri|null,"lang":...|null,
"dir":...|null}``, ``{"t":"triple","s":...,"p":...,"o":...}``. Blank node labels are preserved so references hold.

CLI: ``python -m starlayer.shacl_engine.plan_json shapes.ttl > plan.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from starlayer.shacl_engine.plan import (
    SH,
    Path,
    Plan,
    Shape,
    ShapeError,
    Term,
    is_shape_type,
)
from starlayer.shacl_engine.terms import (
    OWL,
    RDF,
    RDFS,
    BlankNode,
    Literal,
    NamedNode,
    Triple,
)
from starlayer.shacl_engine.terms import BlankNode as BNode
from starlayer.shacl_engine.terms import NamedNode as URIRef

FORMAT_VERSION = 1
SHNEX = "http://www.w3.org/ns/shacl-node-expr#"
_SHAPE_REF_KEYS = {SHNEX + "filterShape", SHNEX + "findFirst", SHNEX + "matchAll", SHNEX + "nodesMatching"}


# --------------------------------------------------------------------------------------------------------------------
# Terms


def term_to_json(term: Term) -> dict:
    if isinstance(term, NamedNode):
        return {"t": "iri", "v": term.value}
    if isinstance(term, BlankNode):
        return {"t": "bnode", "v": term.value}
    if isinstance(term, Literal):
        return {
            "t": "lit",
            "v": term.value,
            "dt": term.datatype.value if not term.language else None,
            "lang": term.language,
            "dir": str(term.direction) if term.direction is not None else None,
        }
    if isinstance(term, Triple):
        return {
            "t": "triple",
            "s": term_to_json(term.subject),
            "p": term_to_json(term.predicate),
            "o": term_to_json(term.object),
        }
    raise TypeError(f"cannot serialise {term!r} ({type(term).__name__}) as an RDF term")


def term_from_json(obj: dict) -> Term:
    kind = obj["t"]
    if kind == "iri":
        return NamedNode(obj["v"])
    if kind == "bnode":
        return BlankNode(obj["v"])
    if kind == "lit":
        if obj.get("lang"):
            from pyoxigraph import BaseDirection

            direction = {"ltr": BaseDirection.LTR, "rtl": BaseDirection.RTL}[obj["dir"]] if obj.get("dir") else None
            return Literal(obj["v"], language=obj["lang"], direction=direction)
        dt = obj.get("dt")
        return Literal(obj["v"], datatype=NamedNode(dt)) if dt else Literal(obj["v"])
    if kind == "triple":
        return Triple(term_from_json(obj["s"]), term_from_json(obj["p"]), term_from_json(obj["o"]))
    raise ValueError(f"unknown term tag {kind!r}")


def _terms(items: Iterable[Term]) -> list[dict]:
    return [term_to_json(t) for t in items]


def _from_terms(items: Iterable[dict]) -> tuple[Term, ...]:
    return tuple(term_from_json(t) for t in items)


# --------------------------------------------------------------------------------------------------------------------
# Paths and shapes


def path_to_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    out: dict[str, Any] = {"kind": path.kind}
    if path.iri is not None:
        out["iri"] = term_to_json(path.iri)
    if path.args:
        out["args"] = [path_to_json(a) for a in path.args]
    out["node"] = term_to_json(path.node) if path.node is not None else None
    return out


def path_from_json(obj: dict | None) -> Path | None:
    if obj is None:
        return None
    return Path(
        kind=obj["kind"],
        iri=term_from_json(obj["iri"]) if "iri" in obj else None,
        args=tuple(path_from_json(a) for a in obj.get("args", ())),
        node=term_from_json(obj["node"]) if obj.get("node") is not None else None,
    )


def shape_to_json(shape: Shape) -> dict:
    return {
        "node": term_to_json(shape.node),
        "is_property": shape.is_property,
        "path": path_to_json(shape.path),
        "targets": [[p.value, term_to_json(v)] for p, v in shape.targets],
        "params": {p.value: _terms(vs) for p, vs in shape.params.items()},
        "property_shapes": _terms(shape.property_shapes),
        "severity": term_to_json(shape.severity),
        "deactivated": shape.deactivated,
        "deactivated_exprs": _terms(shape.deactivated_exprs),
        "messages": _terms(shape.messages),
        "values": _terms(shape.values),
        "default_values": _terms(shape.default_values),
        "annotations": [
            {
                "predicate": term_to_json(p),
                "value": term_to_json(v),
                "deactivated": bool(info["deactivated"]),
                "severity": term_to_json(info["severity"]) if info["severity"] is not None else None,
            }
            for (p, v), info in shape.annotations.items()
        ],
    }


def shape_from_json(obj: dict) -> Shape:
    return Shape(
        node=term_from_json(obj["node"]),
        is_property=obj["is_property"],
        path=path_from_json(obj["path"]),
        targets=tuple((URIRef(p), term_from_json(v)) for p, v in obj["targets"]),
        params={URIRef(p): _from_terms(vs) for p, vs in obj["params"].items()},
        property_shapes=_from_terms(obj["property_shapes"]),
        severity=term_from_json(obj["severity"]),
        deactivated=obj["deactivated"],
        messages=_from_terms(obj["messages"]),
        values=_from_terms(obj["values"]),
        default_values=_from_terms(obj["default_values"]),
        annotations={
            (term_from_json(a["predicate"]), term_from_json(a["value"])): {
                "deactivated": a["deactivated"],
                "severity": term_from_json(a["severity"]) if a["severity"] is not None else None,
            }
            for a in obj["annotations"]
        },
        deactivated_exprs=_from_terms(obj["deactivated_exprs"]),
    )


# --------------------------------------------------------------------------------------------------------------------
# Enumerating the shapes a plan can reach (the builder is lazy and does not enumerate references)

_DIRECT_REF_PARAMS = (SH.node, SH["not"], SH.qualifiedValueShape, SH.memberShape, SH.reifierShape)
_LIST_REF_PARAMS = (SH["and"], SH["or"], SH.xone)


def _walk_bnodes(graph: Any, start: Term, seen: set) -> Iterable[tuple[Term, Term, Term]]:
    """Triples of the blank-node closure of ``start`` (a node expression, list, ...)."""
    queue = [start]
    while queue:
        n = queue.pop()
        if not isinstance(n, BNode) or n in seen:
            continue
        seen.add(n)
        for p, o in graph.predicate_objects(n):
            yield n, p, o
            queue.append(o)


def _expression_refs(graph: Any, exprs: Iterable[Term]) -> list[Term]:
    """Shape nodes mentioned inside node expressions: objects of the shape-taking operators, and any constant that is typed
    as a shape (covers ``shnex:conformsToShape ( ?x ex:Shape )``)."""
    out: list[Term] = []
    seen: set = set()
    for expr in exprs:
        for _s, p, o in _walk_bnodes(graph, expr, seen):
            if p.value in _SHAPE_REF_KEYS and not isinstance(o, Literal):
                out.append(o)
            elif isinstance(o, URIRef) and is_shape_type(graph, o):
                out.append(o)
            elif isinstance(o, BNode) and (o, RDF.first, None) not in graph and is_shape_type(graph, o):
                out.append(o)
        # list members that are shapes (conformsToShape arguments)
        for s in list(seen):
            for o in graph.objects(s, RDF.first):
                if isinstance(o, URIRef) and is_shape_type(graph, o):
                    out.append(o)
    return out


def shape_references(graph: Any, shape: Shape) -> list[Term]:
    """Every shape node a shape refers to, in a stable order (duplicates removed)."""
    from starlayer.shacl_engine.components.core_shape_based import shacl_list

    refs: list[Term] = list(shape.property_shapes)
    for pred in _DIRECT_REF_PARAMS:
        refs.extend(shape.params.get(pred, ()))
    for pred in _LIST_REF_PARAMS:
        for head in shape.params.get(pred, ()):
            try:
                refs.extend(shacl_list(graph, head))
            except ShapeError:
                pass  # the component raises when evaluated; the plan just records no references
    refs.extend(v for p, v in shape.targets if p == SH.targetWhere)
    # parameters of SPARQL-based component declarations or anything else that names a shape
    known = set(_DIRECT_REF_PARAMS) | set(_LIST_REF_PARAMS)
    for pred, vs in shape.params.items():
        if pred not in known:
            refs.extend(v for v in vs if isinstance(v, (URIRef, BNode)) and is_shape_type(graph, v))
    exprs = [*shape.values, *shape.default_values, *shape.deactivated_exprs]
    exprs += [v for p, vs in shape.params.items() if p in (SH.expression, SH.nodeByExpression) for v in vs]
    exprs += [v for p, v in shape.targets if p == SH.targetNode and isinstance(v, BNode)]
    refs.extend(_expression_refs(graph, exprs))
    return [r for r in dict.fromkeys(refs) if isinstance(r, (URIRef, BNode))]


# --------------------------------------------------------------------------------------------------------------------
# Rules, prefixes, term store


def _rule_to_json(graph: Any, node: Term) -> dict:
    from starlayer.shacl_engine.rules import RuleError, read_rule

    try:
        rule = read_rule(graph, node)
    except RuleError as exc:
        return {"node": term_to_json(node), "error": str(exc)}
    return {
        "node": term_to_json(rule.node),
        "types": _terms(rule.types),
        "layer": rule.layer,
        "order": rule.order,
        "run_once": rule.run_once,
        "shapes": _terms(rule.shapes),
        "conditions": _terms(rule.conditions),
        "expected_predicates": _terms(rule.expected_predicates),
    }


def _prefix_section(plan: Plan, graph: Any) -> dict:
    from starlayer.shacl_engine.sparql_support import prefixes_for

    out: dict[str, Any] = {"default": {}, "holders": []}
    try:
        out["default"] = dict(prefixes_for(plan, BNode("plan-json-default-holder")))
    except ShapeError as exc:
        out["default_error"] = str(exc)
    for holder in dict.fromkeys(graph.subjects(SH.prefixes, None)):
        entry: dict[str, Any] = {"holder": term_to_json(holder)}
        try:
            entry["declarations"] = dict(prefixes_for(plan, holder))
        except ShapeError as exc:
            entry["error"] = str(exc)
        out["holders"].append(entry)
    return out


def _follow_iris(plan: Plan, graph: Any, rule_nodes: list[Term]) -> set:
    """IRI nodes whose triples belong in the term store (their blank-node neighbourhood always does)."""
    from starlayer.shacl_engine.components.sparql_components import _subclass_closure

    follow: set = set(rule_nodes)
    for cls in _subclass_closure(graph, SH.ConstraintComponent):
        follow.update(graph.subjects(RDF.type, cls))
    for cls in (SH.ListParameterExpressionFunction, SH.NamedParameterExpressionFunction, SH.RuleSet):
        follow.update(graph.subjects(RDF.type, cls))
    follow.update(graph.subjects(SH.declare, None))
    for holder in graph.subjects(SH.prefixes, None):
        follow.update(graph.objects(holder, SH.prefixes))
    queue = list(follow)
    while queue:  # owl:imports / owl:versionIRI / rule set inclusion chains
        n = queue.pop()
        for pred in (OWL.imports, SH.includesRuleSet, SH.hasRule):
            for o in graph.objects(n, pred):
                if o not in follow:
                    follow.add(o)
                    queue.append(o)
        for s in graph.subjects(OWL.versionIRI, n):
            if s not in follow:
                follow.add(s)
                queue.append(s)
    return {n for n in follow if isinstance(n, URIRef | BNode)}


def _terms_in(term: Term) -> list[Term]:
    if isinstance(term, Triple):
        return [x for part in (term.subject, term.predicate, term.object) for x in _terms_in(part)]
    return [term]


# Predicates whose IRI objects are nodes the executor reads further (declarations, validators, annotations).
_FOLLOW_PREDS = frozenset(
    {
        SH.parameter, SH.validator, SH.nodeValidator, SH.propertyValidator, SH.prefixes, SH.declare, SH.resultAnnotation,
        SH.bodyExpression, SH.condition, SH.sparql, SH.expression, SH.nodeByExpression, SH.hasRule, SH.includesRuleSet,
        OWL.imports,
    }
)  # fmt: skip


def _term_store(plan: Plan, graph: Any, shapes: list[Shape], rule_nodes: list[Term]) -> list[list[dict]]:
    """Triples the executor reads from the shapes graph by pattern: every shape's own triples (siblings of qualified
    shapes, ``sh:closed`` property lists), the blank-node closure of everything the shapes refer to (lists, expressions,
    paths, SPARQL nodes), and the declarations (components, functions, rules, prefixes) with the IRI nodes they name."""
    from starlayer.shacl_engine.components.registry import all_param_predicates

    seeds: list[Term] = []
    static_preds = all_param_predicates()
    follow = _follow_iris(plan, graph, rule_nodes)
    for s in shapes:
        follow.add(s.node)
        seeds.append(s.node)
        seeds.extend(v for vs in s.params.values() for v in vs)
        seeds.extend([*s.values, *s.default_values, *s.deactivated_exprs, *s.messages, *s.property_shapes])
        seeds.extend(v for _p, v in s.targets)
        seeds.extend(info["severity"] for info in s.annotations.values() if info["severity"] is not None)
        seeds.extend(v for _p, v in s.annotations)
        for pred, vs in s.params.items():  # IRI-valued nodes that carry structure (a named sh:sparql node, custom parameters)
            if pred in (SH.sparql, SH.expression, SH.nodeByExpression) or pred not in static_preds:
                follow.update(v for v in vs if isinstance(v, URIRef))
    seeds.extend(follow)
    triples: dict = {}
    seen: set = set()
    queue = [x for t in seeds for x in _terms_in(t)]
    while queue:
        n = queue.pop()
        if n in seen:
            continue
        seen.add(n)
        if not (isinstance(n, BNode) or n in follow):
            continue
        for p, o in graph.predicate_objects(n):
            triples[(n, p, o)] = None
            if isinstance(o, URIRef) and p in _FOLLOW_PREDS:
                follow.add(o)
            queue.extend(_terms_in(o))
    # facts the executor reads by pattern rather than by walking from a node
    for pred in (SH.rule, SH.hasRule, SH.entailment):
        for t in graph.triples((None, pred, None)):
            triples[tuple(t)] = None
    for t in graph.triples((None, RDFS.subClassOf, None)):
        triples[tuple(t)] = None
    return [[term_to_json(x) for x in t] for t in triples]


# --------------------------------------------------------------------------------------------------------------------
# Plan <-> JSON


def plan_to_json(plan: Plan, *, shapes: Iterable[Term] | None = None) -> dict:
    """The whole plan as a JSON-serialisable dict. ``shapes`` limits the root shape nodes (default: every declared shape
    node); shapes reachable from the roots are included either way."""
    from starlayer.shacl_engine.rules import all_rule_nodes, entailment_selection

    graph = plan.shapes_graph
    declared = list(plan.all_shape_nodes())
    roots = list(shapes) if shapes is not None else list(declared)
    built: dict[Term, Shape] = {}
    errors: list[dict] = []
    queue = list(roots)
    rule_nodes = list(all_rule_nodes(graph))
    for r in rule_nodes:  # sh:condition shapes of rules are reachable too
        queue.extend(graph.objects(r, SH.condition))
    while queue:
        node = queue.pop(0)
        if node in built or any(e["_node"] == node for e in errors):
            continue
        try:
            shape = plan.shape(node)
        except ShapeError as exc:
            errors.append({"_node": node, "message": str(exc)})
            continue
        built[node] = shape
        queue.extend(shape_references(graph, shape))
    shape_list = list(built.values())
    rule_sets = [
        {
            "node": term_to_json(rs),
            "rules": _terms(graph.objects(rs, SH.hasRule)),
            "includes": _terms(graph.objects(rs, SH.includesRuleSet)),
        }
        for rs in dict.fromkeys(graph.subjects(RDF.type, SH.RuleSet))
    ]
    active, selected_sets = entailment_selection(graph)
    return {
        "format_version": FORMAT_VERSION,
        "declared": _terms(declared),
        "shapes": [shape_to_json(s) for s in shape_list],
        "errors": [{"node": term_to_json(e["_node"]), "message": e["message"]} for e in errors],
        "rules": [_rule_to_json(graph, r) for r in rule_nodes],
        "rule_sets": rule_sets,
        "entailment": {
            "values": _terms(o for _s, _p, o in graph.triples((None, SH.entailment, None))),
            "rules_active": active,
            "rule_sets": _terms(selected_sets),
        },
        "prefixes": _prefix_section(plan, graph),
        "graph": _term_store(plan, graph, shape_list, rule_nodes),
    }


@dataclass
class SerializedPlan(Plan):
    """A ``Plan`` rebuilt from JSON: shapes come from the file (not the shapes graph); ``shapes_graph`` is the term store
    (or the graph the caller passed). Shapes not in the file are built lazily from the graph, as in ``Plan``."""

    declared: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)  # node -> message of shapes that failed to build
    rules: list = field(default_factory=list)  # the rule records as in the JSON
    prefixes: dict = field(default_factory=dict)
    format_version: int = FORMAT_VERSION

    def shape(self, node: Term) -> Shape:
        if node in self.errors:
            raise ShapeError(self.errors[node])
        return super().shape(node)

    def all_shape_nodes(self) -> list[Term]:
        return list(self.declared)


def plan_from_json(obj: dict, shapes_graph: Any = None) -> Plan:
    """Rebuild a plan. With ``shapes_graph=None`` an ``OxGraph`` is filled from the ``graph`` term store; else the
    given graph is used for expressions, lists and SPARQL nodes (it must be the graph the plan was built from)."""
    version = obj.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported plan format_version {version!r} (this reader reads {FORMAT_VERSION})")
    if shapes_graph is None:
        from starlayer.shacl_engine.graphs import new_graph

        shapes_graph = new_graph()
        shapes_graph.extend([(term_from_json(s), term_from_json(p), term_from_json(o)) for s, p, o in obj["graph"]])
    plan = SerializedPlan(
        shapes_graph=shapes_graph,
        declared=[term_from_json(t) for t in obj["declared"]],
        errors={term_from_json(e["node"]): e["message"] for e in obj["errors"]},
        rules=obj["rules"],
        prefixes=obj["prefixes"],
        format_version=version,
    )
    for s in obj["shapes"]:
        shape = shape_from_json(s)
        plan._cache[shape.node] = shape
    return plan


def load_shapes_graph(location: str) -> Any:
    from starlayer.shacl_engine.graphs import new_graph

    g = new_graph()
    fmt = "turtle12" if location.endswith((".ttl", ".turtle")) else None
    g.parse(location, format=fmt)
    return g


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m starlayer.shacl_engine.plan_json", description=__doc__.split("\n")[0])
    ap.add_argument("shapes", help="shapes graph file (Turtle 1.2 by default)")
    ap.add_argument("--indent", type=int, default=None, help="pretty-print with this indent")
    args = ap.parse_args(argv)
    plan = Plan(shapes_graph=load_shapes_graph(args.shapes))
    json.dump(plan_to_json(plan), sys.stdout, indent=args.indent, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
