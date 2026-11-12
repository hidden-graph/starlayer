"""Hunting under-extraction in ``extract_subgraph()``: randomized shapes (nested logic, complex paths, qualified shapes,
closed shapes, computed ``sh:values`` / ``sh:defaultValue``, the property-pair constraints) over random small graphs.

The rule (``subgraph_extraction`` docstring): over-extracting is allowed, under-extracting is a bug. For a focus node
that conforms to its shapes, the fragment must hold every triple validation reads. Properties checked per example:

* P1 the fragment, validated alone against the same shapes (the focus pinned with ``sh:targetNode``), conforms;
* P2 the fragment holds only stored triples of the data;
* P3 extraction is deterministic and does not depend on the order of the items of ``sh:or`` / ``sh:xone`` / ``sh:and``
  / ``sh:in`` / ``sh:alternativePath`` lists (compared by RDFC-1.0 hash);
* P4 ``evaluate()`` over the fragment computes the same virtual values as over the full data;
* P5 removing a stored triple that is not in the fragment does not change the focus node's outcome (it still conforms).

``STARLAYER_FUZZ_EXAMPLES`` sets the number of examples per property (default 200); ``STARLAYER_FUZZ_SEED`` pins the
hypothesis seed (``derandomize`` is used when it is ``ci``). Shrunk failures are printed as Turtle."""

from __future__ import annotations

import os
import warnings

import pytest
from hypothesis import HealthCheck, assume, given, note, settings
from hypothesis import strategies as st
from rdflib import RDF, SH, Graph, Namespace
from starlayer import StarLayerGraph
from starlayer.graph.rdfc import rdfc10_hash
from starlayer.shacl import evaluate, extract_subgraph, validate

E = Namespace("http://e/")
PREFIXES = (
    "@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix sparql: <http://www.w3.org/ns/sparql#> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)

NODES = ["n0", "n1", "n2", "n3"]
LITERALS = ['"a"', '"bb"', "1", "2", '"x"@en', '"y"@fr', '"x"@fr']
CLASSES = ["A", "B"]
PREDS = ["p", "q", "r"]
OBJECTS = [f":{n}" for n in NODES] + LITERALS

# A closed shape that must be *false* (under sh:not or in an sh:xone branch) needs the offending triple in the fragment;
# extraction does not record it (see test_a_violated_closed_shape_is_evidence). The generator stays out of that corner
# until the bug is fixed, so the other properties keep being hunted.
_NEGATIVE_CLOSED = os.environ.get("STARLAYER_FUZZ_NEGATIVE_CLOSED", "") == "1"
_EXAMPLES = int(os.environ.get("STARLAYER_FUZZ_EXAMPLES", "200"))
_SEED = os.environ.get("STARLAYER_FUZZ_SEED", "")
_FUZZ = settings(
    max_examples=_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow, HealthCheck.data_too_large],
    derandomize=_SEED == "ci",
    print_blob=True,
)


# ---------------------------------------------------------------------------------------------- generators
@st.composite
def _path(draw, allow_complex: bool = True) -> str:
    p, q = draw(st.sampled_from(PREDS)), draw(st.sampled_from(PREDS))
    simple = [f":{p}"]
    complex_ = [
        f"[ sh:inversePath :{p} ]",
        f"( :{p} :{q} )",
        f"[ sh:alternativePath ( :{p} :{q} ) ]",
        f"[ sh:zeroOrMorePath :{p} ]",
        f"[ sh:oneOrMorePath :{p} ]",
        f"[ sh:zeroOrOnePath :{p} ]",
        f"( [ sh:inversePath :{p} ] :{q} )",
        f"[ sh:zeroOrMorePath [ sh:inversePath :{p} ] ]",
    ]
    return draw(st.sampled_from(simple * 3 + (complex_ if allow_complex else [])))


def _value_constraint(draw, depth: int, kind: str, neg: bool) -> str:
    """One constraint of a property shape, applied to the values of its path."""
    cls = draw(st.sampled_from(CLASSES))
    n = draw(st.integers(1, 2))
    pred = draw(st.sampled_from(PREDS))
    obj = draw(st.sampled_from(OBJECTS))
    if kind == "class":
        return f"sh:class :{cls}"
    if kind == "datatype":
        return f"sh:datatype {draw(st.sampled_from(['xsd:string', 'xsd:integer', 'rdf:langString']))}"
    if kind == "nodeKind":
        return f"sh:nodeKind {draw(st.sampled_from(['sh:IRI', 'sh:Literal', 'sh:BlankNodeOrIRI']))}"
    if kind == "hasValue":
        return f"sh:hasValue {obj}"
    if kind == "in":
        members = " ".join(draw(st.lists(st.sampled_from(OBJECTS), min_size=1, max_size=3, unique=True)))
        return f"sh:in ( {members} )"
    if kind == "min":
        return f"sh:minCount {n}"
    if kind == "max":
        return f"sh:maxCount {n}"
    if kind == "pattern":
        return f'sh:pattern "{draw(st.sampled_from(["a", "^b", "x|1"]))}"'
    if kind == "minLength":
        return f"sh:minLength {n}"
    if kind == "qualified":
        bounds = draw(st.sampled_from([f"sh:qualifiedMinCount {n}", f"sh:qualifiedMaxCount {n}", f"sh:qualifiedMinCount 1 ; sh:qualifiedMaxCount {n + 1}"]))
        return f"sh:qualifiedValueShape [ sh:class :{cls} ] ; {bounds}"
    if kind == "uniqueLang":
        return "sh:uniqueLang true"
    if kind in ("equals", "disjoint", "lessThan", "lessThanOrEquals"):
        return f"sh:{kind} :{pred}"
    if kind == "closedNode":
        return f"sh:node [ sh:closed true ; sh:ignoredProperties ( :{pred} ) ; sh:property [ sh:path :{draw(st.sampled_from(PREDS))} ] ]"
    inner = [_property_item(draw, depth + 1, neg or kind == "not") for _ in range(2)]
    if kind == "node":
        return f"sh:node [ {inner[0]} ]"
    if kind == "not":
        return f"sh:not [ {inner[0]} ]"
    if kind == "and":
        return f"sh:and ( [ {inner[0]} ] [ {inner[1]} ] )"
    return f"sh:or ( [ {inner[0]} ] [ {inner[1]} ] )"


_SINGULAR = [
    "class", "datatype", "nodeKind", "hasValue", "in", "min", "max", "pattern", "minLength", "qualified",
    "uniqueLang", "equals", "disjoint", "lessThan", "lessThanOrEquals", "closedNode", "or",
]  # fmt: skip


def _property_item(draw, depth: int, neg: bool = False) -> str:
    singular = [k for k in _SINGULAR if not (neg and k == "closedNode" and not _NEGATIVE_CLOSED)]
    kinds = draw(st.lists(st.sampled_from(singular + (["node", "not", "and"] if depth < 2 else [])), min_size=1, max_size=2, unique=True))
    constraints = [_value_constraint(draw, depth, kind, neg) for kind in kinds]
    return f"sh:property [ sh:path {draw(_path())} ; {' ; '.join(constraints)} ]"


@st.composite
def _logical_item(draw, depth: int = 0, neg: bool = False) -> str:
    """A constraint of a node shape: a property shape, or a logical constructor over node shapes of property shapes."""
    closed = ["closed"] if (not neg or _NEGATIVE_CLOSED) else []
    kind = draw(st.sampled_from(["prop"] * 3 + ["and", "or", "xone", "not"] + closed + (["nested"] if depth < 1 else [])))
    if kind == "prop":
        return _property_item(draw, 0, neg)
    if kind == "closed":
        ignored = draw(st.lists(st.sampled_from(PREDS + ["type"]), max_size=2, unique=True))
        ignored_ttl = " ".join("rdf:type" if i == "type" else f":{i}" for i in ignored)
        declared = _property_item(draw, 1, neg)
        return f"sh:closed true ; sh:ignoredProperties ( {ignored_ttl} ) ; {declared}"
    inner_count = 1 if kind == "not" else draw(st.integers(2, 3))
    inner_neg = neg or kind in ("not", "xone")
    inner = [draw(_logical_item(depth + 1, inner_neg)) if depth < 1 else _property_item(draw, 1, inner_neg) for _ in range(inner_count)]
    if kind == "not":
        return f"sh:not [ {inner[0]} ]"
    if kind == "nested":
        return f"sh:node [ {inner[0]} ]"
    return f"sh:{kind} ( " + " ".join(f"[ {i} ]" for i in inner) + " )"


@st.composite
def _computed_item(draw) -> str:
    """A property shape with a single-IRI ``sh:path :v`` (never stored in the data) whose values come from an expression."""
    expr = draw(
        st.sampled_from(
            [
                "[ shnex:pathValues :p ]",
                "[ shnex:pathValues :q ]",
                "[ sparql:concat ( [ shnex:pathValues :p ] [ shnex:pathValues :q ] ) ]",
                '[ sparql:concat ( [ shnex:pathValues :p ] "-" [ shnex:pathValues :q ] ) ]',
                '"c"',
                ":n1",
                "[ shnex:count [ shnex:pathValues :p ] ]",
            ]
        )
    )
    kind = draw(st.sampled_from(["values", "values", "default"]))
    constraint = draw(
        st.sampled_from(
            [
                "sh:minCount 1",
                "sh:maxCount 1",
                "sh:datatype xsd:string",
                'sh:pattern "a"',
                "sh:nodeKind sh:Literal",
                "sh:hasValue :n1",
                "sh:minLength 2",
                "sh:class :A",
            ]
        )
    )
    return f"sh:property [ sh:path :v ; sh:{'values' if kind == 'values' else 'defaultValue'} {expr} ; {constraint} ]"


@st.composite
def _shapes_ttl(draw, computed: bool | None = None) -> tuple[str, str]:
    """(Turtle of the shapes, the focus node), the focus pinned with sh:targetNode."""
    focus = draw(st.sampled_from(NODES))
    items = [draw(_logical_item()) for _ in range(draw(st.integers(1, 3)))]
    if computed or (computed is None and draw(st.integers(0, 3)) == 0):
        items.append(draw(_computed_item()))
    # a shape holds several `sh:closed`s only by accident; keep one so the shape stays well-formed
    seen_closed = False
    kept = []
    for item in items:
        if item.startswith("sh:closed"):
            if seen_closed:
                continue
            seen_closed = True
        kept.append(item)
    return f":S sh:targetNode :{focus} ; " + " ; ".join(kept) + " .", focus


@st.composite
def _data_ttl(draw) -> str:
    most = draw(st.sampled_from([1, 2, 3, 4]))  # density varies per case: minCount needs it, maxCount and sh:not need sparsity
    triples = []
    for node in NODES:
        for cls in draw(st.lists(st.sampled_from(CLASSES), max_size=2, unique=True)):
            triples.append(f":{node} a :{cls} .")
        for pred in PREDS:
            for obj in draw(st.lists(st.sampled_from(OBJECTS), max_size=most, unique=True)):
                triples.append(f":{node} :{pred} {obj} .")
    return " ".join(triples)


@st.composite
def _case(draw, computed: bool | None = None):
    shapes, focus = draw(_shapes_ttl(computed))
    return shapes, draw(_data_ttl()), focus


# ---------------------------------------------------------------------------------------------- helpers
def _graph(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + ttl, format="turtle12")
    return graph


def _conforms(data, shapes) -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return validate(data, shapes, meta_shacl=False).conforms


def _extract(data, shapes):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract_subgraph(data, shapes)


def _conforming_case(case):
    """Parses a case, discarding (``assume``) the ones whose focus does not conform or that extract nothing."""
    shapes_ttl, data_ttl, focus = case
    note(f"SHAPES:\n{shapes_ttl}\nDATA:\n{data_ttl}")
    shapes, data = _graph(shapes_ttl), _graph(data_ttl)
    assume(_conforms(data, shapes))
    fragment = _extract(data, shapes)
    assume(len(fragment) > 0)
    return shapes, data, fragment, focus


def _reverse_lists(shapes: StarLayerGraph) -> StarLayerGraph:
    """The same shapes with the items of every order-free list (sh:or, sh:xone, sh:and, sh:in, sh:alternativePath) reversed."""
    plain = Graph()
    for t in shapes:
        plain.add(t)
    heads = {o for p in (SH["or"], SH.xone, SH["and"], SH["in"], SH.alternativePath) for o in plain.objects(None, p)}
    out = StarLayerGraph()
    for s, p, o in shapes:
        if (s, p, o) and p in (RDF.first, RDF.rest):
            continue
        out.add((s, p, o))
    for head in heads:
        items = list(plain.items(head))
        node = head
        # rebuild the list in place on the same nodes: the node ids stay, the first-values are reversed
        cells = []
        cur = head
        while cur != RDF.nil:
            cells.append(cur)
            cur = plain.value(cur, RDF.rest)
        for cell, item, nxt in zip(cells, reversed(items), cells[1:] + [RDF.nil], strict=True):
            out.add((cell, RDF.first, item))
            out.add((cell, RDF.rest, nxt))
        del node
    # lists not reversed (sequence paths, node expressions) keep their triples
    reversed_cells = set()
    for head in heads:
        cur = head
        while cur != RDF.nil:
            reversed_cells.add(cur)
            cur = plain.value(cur, RDF.rest)
    for s, p, o in plain:
        if p in (RDF.first, RDF.rest) and s not in reversed_cells:
            out.add((s, p, o))
    return out


# ---------------------------------------------------------------------------------------------- properties
@_FUZZ
@given(_case())
def test_p1_p2_the_fragment_conforms_alone_and_is_real_data(case) -> None:
    shapes, data, fragment, _focus = _conforming_case(case)
    stored = set(data)
    assert set(fragment) <= stored, "P2: the fragment holds a triple that is not in the data"
    assert _conforms(fragment, shapes), "P1: under-extraction, the focus node does not conform inside its fragment"


@_FUZZ
@given(_case())
def test_p3_extraction_is_deterministic_and_list_order_free(case) -> None:
    shapes, data, fragment, _focus = _conforming_case(case)
    assert rdfc10_hash(_extract(data, shapes)) == rdfc10_hash(fragment), "extraction is not deterministic"
    flipped = _reverse_lists(shapes)
    assert _conforms(data, flipped)
    other = _extract(data, flipped)
    assert set(other) == set(fragment), "the fragment depends on the order of a list in the shapes"
    assert rdfc10_hash(other) == rdfc10_hash(fragment)


@_FUZZ
@given(_case(computed=True))
def test_p4_evaluate_over_the_fragment_equals_over_the_data(case) -> None:
    shapes, data, fragment, focus = _conforming_case(case)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        full = {t for t in evaluate(data, shapes) if t[1] == E.v and t[0] == E[focus]}
        partial = {t for t in evaluate(fragment, shapes) if t[1] == E.v and t[0] == E[focus]}
    assert partial == full, "P4: the computed values differ over the fragment"


@_FUZZ
@given(_case(), st.data())
def test_p5_removing_a_triple_outside_the_fragment_keeps_the_node_conforming(case, data_strategy) -> None:
    shapes, data, fragment, _focus = _conforming_case(case)
    outside = sorted(set(data) - set(fragment), key=str)
    assume(outside)
    victims = data_strategy.draw(st.lists(st.sampled_from(outside), min_size=1, max_size=min(3, len(outside)), unique=True))
    note(f"REMOVED: {victims}")
    smaller = StarLayerGraph()
    for t in data:
        if t not in victims:
            smaller.add(t)
    assert _conforms(smaller, shapes), "P5: a triple outside the fragment mattered to the focus node's outcome"


def test_the_generator_makes_usable_cases() -> None:
    """A silent generator flaw would hide bugs: the shapes must parse, and a fair share of the cases must conform with a
    non-empty fragment (the cases the properties are about)."""
    seen = {"total": 0, "usable": 0}

    @settings(max_examples=80, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
    @given(_case())
    def check(case) -> None:
        shapes_ttl, data_ttl, _ = case
        shapes, data = _graph(shapes_ttl), _graph(data_ttl)
        seen["total"] += 1
        if _conforms(data, shapes) and len(_extract(data, shapes)) > 0:
            seen["usable"] += 1

    check()
    assert seen["usable"] >= 1, seen


# ---------------------------------------------------------------------------------------------- known open bugs
_NOT_CLOSED = (
    ":S sh:targetNode :n0 ; sh:not [ sh:closed true ; sh:property [ sh:path :p ] ] .",
    ":n0 :p :n1 . :n0 :r :n1 .",
)
_XONE_CLOSED = (
    ":S sh:targetNode :n0 ; sh:xone ( [ sh:property [ sh:path :p ; sh:minCount 1 ] ] [ sh:closed true ; sh:property [ sh:path :p ] ] ) .",
    ":n0 :p :n1 . :n0 :r :n1 .",
)


@pytest.mark.xfail(
    strict=True,
    reason="open bug: a closed shape that is false (under sh:not, or the false branch of sh:xone) is not evidence-extracted; "
    "the offending triple :n0 :r :n1 is missing from the fragment, so the node stops conforming inside it",
)
@pytest.mark.parametrize(("shapes", "data"), [_NOT_CLOSED, _XONE_CLOSED], ids=["not-closed", "xone-closed"])
def test_a_violated_closed_shape_is_evidence(shapes, data) -> None:
    shapes_graph, data_graph = _graph(shapes), _graph(data)
    assert _conforms(data_graph, shapes_graph)
    assert _conforms(_extract(data_graph, shapes_graph), shapes_graph)
