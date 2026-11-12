"""Engine ``extract_subgraph`` / ``extract_shapes_graph`` / ``close_shape`` against the old implementations.

The old ones (``starlayer.shacl``) are the oracle: every case the project's existing tests cover is run through both on the
same inline Turtle and the results must be equal (as triple sets), plus the Conformance Theorem checked with the engine's
own ``validate``. Deviations are tested on their own (sh:target error, focus_node anchoring, backends).
"""

from __future__ import annotations

import importlib.util
import re
import warnings
from pathlib import Path

import pytest
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl import extract_subgraph as old_extract
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.shapes_graphs import close_shape, extract_shapes_graph
from starlayer.shacl_engine.subgraph import extract_subgraph
from starlayer.shacl_engine.terms import NS as Namespace
from starlayer.shacl_engine.terms import from_engine, text

EX = Namespace("http://example.org/")
PRE = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PRE + ttl, format="turtle")
    return g


def _old(*args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return set(old_extract(*args, **kwargs))


def _new(*args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return set(extract_subgraph(*args, **kwargs))


def _same(data, shapes=None, **kwargs):
    old, new = _old(data, shapes, **kwargs), _new(data, shapes, **kwargs)
    assert new == old
    return new


# ---------------------------------------------------------------- test_extract_subgraph.py cases
JE_DATA = 'ex:je1 a ex:JournalEntry ; ex:amount 100 ; ex:account ex:acct1 ; ex:note "later note" .'
JE_SHAPE = (
    "ex:JEShape a sh:NodeShape ; sh:targetClass ex:JournalEntry ; sh:property [ sh:path ex:amount ; sh:minCount 1 ] ; "
    "sh:property [ sh:path ex:account ; sh:minCount 1 ] ."
)
OR_SHAPES = (
    "ex:HasEmail a sh:NodeShape ; sh:property [ sh:path ex:email ; sh:minCount 1 ] . "
    "ex:HasPhone a sh:NodeShape ; sh:property [ sh:path ex:phone ; sh:minCount 1 ] . "
    "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:{kw} ( ex:HasEmail ex:HasPhone ) ."
)
QV_DATA = "ex:alice ex:employee ex:bob, ex:carol, ex:dave . ex:bob ex:dept ex:Sales . ex:carol ex:dept ex:Sales . ex:dave ex:dept ex:Eng ."
QV = "[ sh:property [ sh:path ex:dept ; sh:hasValue ex:Sales ] ]"
PEOPLE_DATA = 'ex:alice a ex:Person ; ex:name "Alice" . ex:acme a ex:Company ; ex:name "Acme" . ex:bob a ex:Person .'
PEOPLE_SHAPES = (
    "ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] . "
    "ex:CompanyShape a sh:NodeShape ; sh:targetClass ex:Company ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
)

CASES = {
    "journal entry pair": (JE_DATA, JE_SHAPE, {"shape": EX.JEShape, "focus_node": EX.je1}),
    "journal entry no targets": (JE_DATA, JE_SHAPE, {"shape": EX.JEShape, "focus_node": EX.je1, "include_targets": False}),
    "journal entry non conforming": ("ex:je2 a ex:JournalEntry .", JE_SHAPE, {"shape": EX.JEShape, "focus_node": EX.je2}),
    "sequence path": (
        'ex:alice ex:employee ex:bob ; ex:unrelated "noise" . ex:bob ex:name "Bob" ; ex:secret "shh" .',
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path (ex:employee ex:name) ; sh:minCount 1 ] .",
        {"shape": EX.S, "focus_node": EX.alice},
    ),
    "zeroOrMore cycle": (
        "ex:alice ex:friend ex:bob . ex:bob ex:friend ex:alice, ex:carol . ex:carol ex:friend ex:carol . ex:dave a ex:Unrelated .",
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path [ sh:zeroOrMorePath ex:friend ] ; sh:minCount 1 ] .",
        {"shape": EX.S, "focus_node": EX.alice},
    ),
    "sh:node": (
        'ex:alice ex:employee ex:bob . ex:bob ex:name "Bob" ; ex:secret "shh" .',
        "ex:PersonShape a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] . "
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:employee ; sh:node ex:PersonShape ] .",
        {"shape": EX.S, "focus_node": EX.alice},
    ),
    "or one branch": ('ex:alice ex:email "a@x" ; ex:phoneUnused "555" .', OR_SHAPES.format(kw="or"), {"shape": EX.S, "focus_node": EX.alice}),
    "or both branches": ('ex:alice ex:email "a@x" ; ex:phone "555" .', OR_SHAPES.format(kw="or"), {"shape": EX.S, "focus_node": EX.alice}),
    "xone one branch": ('ex:alice ex:email "a@x" .', OR_SHAPES.format(kw="xone"), {"shape": EX.S, "focus_node": EX.alice}),
    "xone two branches": ('ex:alice ex:email "a@x" ; ex:phone "555" .', OR_SHAPES.format(kw="xone"), {"shape": EX.S, "focus_node": EX.alice}),
    "qualified narrowing": (
        QV_DATA,
        f"ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:employee ; sh:qualifiedValueShape {QV} ; sh:qualifiedMinCount 1 ] .",
        {"shape": EX.S, "focus_node": EX.alice},
    ),
    "qualified with minCount": (
        QV_DATA,
        f"ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:employee ; sh:minCount 3 ; sh:qualifiedValueShape {QV} ; sh:qualifiedMinCount 1 ] .",
        {"shape": EX.S, "focus_node": EX.alice},
    ),
    "qualified inverse path narrowing": (
        "ex:bob ex:boss ex:alice . ex:carol ex:boss ex:alice . ex:bob ex:dept ex:Sales . ex:carol ex:dept ex:Eng .",
        f"ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path [ sh:inversePath ex:boss ] ; sh:qualifiedValueShape {QV} ; sh:qualifiedMinCount 1 ] .",
        {},
    ),
    "qualified max count": (
        QV_DATA,
        f"ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:employee ; sh:qualifiedValueShape {QV} ; sh:qualifiedMaxCount 2 ] .",
        {},
    ),
    "embedded shapes, no shapes graph": (JE_SHAPE + " " + JE_DATA, None, {"shape": EX.JEShape, "focus_node": EX.je1}),
    "whole graph": (PEOPLE_DATA, PEOPLE_SHAPES, {}),
    "shape alone": (PEOPLE_DATA, PEOPLE_SHAPES, {"shape": EX.PersonShape}),
    "focus alone": (PEOPLE_DATA, PEOPLE_SHAPES, {"focus_node": EX.alice}),
    "both filters": (PEOPLE_DATA, PEOPLE_SHAPES, {"shape": EX.PersonShape, "focus_node": EX.alice}),
    "deactivated whole graph": (
        PEOPLE_DATA,
        "ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:deactivated true ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        {},
    ),
    "deactivated by shape": (
        "ex:a a ex:C ; ex:q 2 .",
        "ex:D a sh:NodeShape ; sh:deactivated true ; sh:targetClass ex:C ; sh:property [sh:path ex:q ; sh:minCount 1] .",
        {"shape": EX.D},
    ),
    # target kinds (paper section 5.2 tests)
    "class target subclass chain": (
        'ex:rex a ex:Dog ; ex:name "Rex" . ex:Dog rdfs:subClassOf ex:Mammal . ex:Mammal rdfs:subClassOf ex:Animal . ex:Dog rdfs:subClassOf ex:Pet .',
        "ex:S sh:targetClass ex:Animal ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        {},
    ),
    "subjectsOf target": (
        'ex:a ex:owns ex:x, ex:y ; ex:name "A" . ex:b ex:name "B" .',
        "ex:S sh:targetSubjectsOf ex:owns ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        {},
    ),
    "objectsOf target": (
        'ex:a ex:owns ex:x . ex:x ex:name "X" . ex:b ex:owns ex:y . ex:y ex:name "Y" .',
        "ex:S sh:targetObjectsOf ex:owns ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        {},
    ),
    "node target": ('ex:a a ex:T ; ex:name "A" .', "ex:S sh:targetNode ex:a ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .", {}),
    "not a target": ("ex:x a ex:U ; ex:a 1 .", "ex:S sh:targetClass ex:T ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .", {}),
    "implicit class target": (
        'ex:i a ex:K ; ex:name "I" .',
        "ex:K a rdfs:Class, sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        {},
    ),
    # constructors of the paper: class evidence, not, equals/disjoint/lessThan, list-valued class, alternative path
    "sh:class evidence": (
        "ex:p1 a ex:Paper ; ex:author ex:Alice . ex:Alice a ex:Student . ex:Student rdfs:subClassOf ex:Person .",
        "ex:S sh:targetClass ex:Paper ; sh:property [ sh:path ex:author ; sh:class ex:Person ] .",
        {},
    ),
    "sh:not": (
        "ex:v a ex:Person ; ex:friend ex:b ; ex:colleague ex:b, ex:c .",
        "ex:S sh:targetClass ex:Person ; sh:property [ sh:path ex:friend ; sh:not [ sh:property [ sh:path ex:colleague ; sh:minCount 5 ] ] ] .",
        {},
    ),
    "equals disjoint lessThan": (
        "ex:n a ex:C ; ex:a 1 ; ex:b 1 ; ex:c 5 ; ex:d 7 ; ex:e 9 .",
        "ex:S sh:targetClass ex:C ; sh:property [ sh:path ex:a ; sh:equals ex:b ; sh:disjoint ex:c ; sh:lessThan ex:d ] .",
        {},
    ),
    "alternative and inverse of sequence": (
        "ex:n a ex:C ; ex:p ex:m ; ex:q ex:o . ex:m ex:r ex:z . ex:k ex:s ex:n .",
        "ex:S sh:targetClass ex:C ; sh:property [ sh:path [ sh:alternativePath (ex:p ex:q) ] ; sh:minCount 1 ] ; "
        "sh:property [ sh:path [ sh:inversePath ex:s ] ; sh:minCount 1 ] ; sh:property [ sh:path (ex:p ex:r) ; sh:minCount 1 ] .",
        {},
    ),
    "oneOrMore with cycle": (
        "ex:n0 ex:p ex:n1 . ex:n1 ex:p ex:n0 . ex:n1 ex:p ex:n2 .",
        "ex:A a sh:NodeShape ; sh:targetNode ex:n0 ; sh:property [ sh:path [ sh:oneOrMorePath ex:p ] ; sh:minCount 1 ] .",
        {},
    ),
    "and members": (
        "ex:n a ex:C ; ex:p 1 ; ex:q 2 ; ex:z 3 .",
        "ex:S sh:targetClass ex:C ; sh:and ( [ sh:property [ sh:path ex:p ; sh:minCount 1 ] ] [ sh:property [ sh:path ex:q ; sh:minCount 1 ] ] ) .",
        {},
    ),
    "recursive shape": (
        "ex:a a ex:P ; ex:knows ex:b . ex:b a ex:P ; ex:knows ex:a .",
        "ex:S sh:targetClass ex:P ; sh:property [ sh:path ex:knows ; sh:node ex:S ] .",
        {},
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_extract_subgraph_agrees_with_old(name) -> None:
    data_ttl, shapes_ttl, kwargs = CASES[name]
    data = _g(data_ttl)
    shapes = _g(shapes_ttl) if shapes_ttl is not None else None
    if shapes is None:
        data = _g(data_ttl)
    _same(data, shapes, **kwargs)


def test_extract_subgraph_nonempty_sanity() -> None:
    """The agreement above is not vacuous: representative cases extract something, and the non-conforming ones nothing."""
    assert len(_new(_g(PEOPLE_DATA), _g(PEOPLE_SHAPES))) > 0
    assert _new(_g("ex:je2 a ex:JournalEntry ."), _g(JE_SHAPE), shape=EX.JEShape, focus_node=EX.je2) == set()
    assert _new(_g('ex:alice ex:email "a@x" ; ex:phone "555" .'), _g(OR_SHAPES.format(kw="xone"))) == set()


def test_conformance_theorem_with_the_engine_validate() -> None:
    cases = ["sequence path", "zeroOrMore cycle", "oneOrMore with cycle", "sh:class evidence", "sh:not", "and members", "recursive shape"]
    for name in cases:
        data_ttl, shapes_ttl, kwargs = CASES[name]
        data, shapes = _g(data_ttl), _g(shapes_ttl)
        assert validate(data, shapes, meta_shacl=False).conforms, name
        fragment = extract_subgraph(data, shapes)
        assert len(fragment) > 0, name
        # the fragment keeps the focus nodes targeted and conforms
        assert validate(fragment, shapes, meta_shacl=False).conforms, name


PAPER = Path(__file__).resolve().parents[1] / "shacl" / "integration" / "test_shape_fragments_paper.py"


def _paper_cases():
    spec = importlib.util.spec_from_file_location("_paper_cases", PAPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CASES, module._with_focus_targets, module.PREFIXES


_PAPER_CASES, _FOCUS, _PREFIXES = _paper_cases()


@pytest.mark.parametrize("name", list(_PAPER_CASES))
def test_paper_cases_agree_with_old_and_conform(name) -> None:
    focus, shapes_ttl, data_ttl = _PAPER_CASES[name]
    for shapes_src in (shapes_ttl, _FOCUS(shapes_ttl, focus)):
        shapes, data = StarLayerGraph(), StarLayerGraph()
        shapes.parse(data=_PREFIXES + shapes_src, format="turtle")
        data.parse(data=_PREFIXES + data_ttl, format="turtle")
        _same(data, shapes)
    fragment = extract_subgraph(data, shapes)
    assert validate(fragment, shapes, meta_shacl=False).conforms


# ---------------------------------------------------------------- entailment
def test_entailment_reads_entailed_triples_but_returns_only_real_ones() -> None:
    data = _g("ex:rex a ex:Dog ; ex:name 'Rex' . ex:Dog rdfs:subClassOf ex:Animal .")
    shapes = _g("ex:S sh:targetClass ex:Animal ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    new = _same(data, shapes, inference=ENTAILMENT.RDFS)
    assert new and all(t in data for t in new)


# ---------------------------------------------------------------- contracts and deviations
def test_rejects_str_arguments_and_unknown_shapes() -> None:
    g = _g(JE_SHAPE + " " + JE_DATA)
    with pytest.raises(TypeError):
        extract_subgraph(g, g, shape="http://example.org/JEShape")
    with pytest.raises(TypeError):
        extract_subgraph(g, g, focus_node="http://example.org/je1")
    with pytest.raises(ValueError, match="not a shape"):
        extract_subgraph(StarLayerGraph(), _g(JE_SHAPE), shape=EX.Nope, focus_node=EX.x)


def test_does_not_mutate_the_shapes_graph() -> None:
    shapes = _g(JE_SHAPE)
    before = set(shapes)
    extract_subgraph(_g(JE_DATA), shapes)
    assert set(shapes) == before


def test_sparql_target_is_a_shape_error() -> None:
    from starlayer.shacl import ShapeError

    shapes = _g(
        'ex:NamedThingShape a sh:NodeShape ; sh:target [ a sh:SPARQLTarget ; sh:select "SELECT $this WHERE { $this ex:name ?n }" ] ; '
        "sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
    )
    with pytest.raises(ShapeError, match="NamedThingShape"):
        extract_subgraph(_g(PEOPLE_DATA), shapes)


def test_focus_node_alone_only_uses_shapes_that_target_it() -> None:
    shapes = _g(PEOPLE_SHAPES + " ex:Any a sh:NodeShape ; sh:targetNode ex:acme ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    got = _new(_g(PEOPLE_DATA), shapes, focus_node=EX.alice)
    assert (EX.alice, EX.name, None) not in got and any(s == EX.alice for s, _, _ in got)
    assert not any(s == EX.acme for s, _, _ in got)


def test_oxigraph_backend_matches_rdflib() -> None:
    pytest.importorskip("pyoxigraph")
    from starlayer.shacl_engine.oxigraph_view import OxigraphGraph

    data_ttl, shapes_ttl, kwargs = CASES["whole graph"]
    data, shapes = _g(data_ttl), _g(shapes_ttl)
    try:
        ox = OxigraphGraph()
    except TypeError:
        pytest.skip("OxigraphGraph needs a store")
    for t in data:
        ox.add(t)
    assert _new(ox, shapes) == _new(data, shapes)


# ---------------------------------------------------------------- extract_shapes_graph
MODULES = """
ex:ModuleA a sh:ShapesGraph ; rdfs:member ex:PersonShape .
ex:ModuleB a sh:ShapesGraph ; rdfs:member ex:PersonWorksFor, ex:Unrelated .
ex:ModuleC a sh:ShapesGraph .
ex:Defined a sh:NodeShape ; rdfs:isDefinedBy ex:ModuleC ; sh:nodeKind sh:IRI .
ex:ModuleD a sh:ShapesGraph ; owl:imports ex:ModuleA .
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:PersonWorksFor ; sh:node ex:NamedNode ;
  sh:or ( ex:OrA ex:OrB ) ; sh:property [ sh:path ex:age ; sh:minCount 1 ] .
ex:PersonWorksFor a sh:PropertyShape ; sh:path ex:worksFor ; sh:minCount 1 ; sh:node ex:Company .
ex:Company a sh:NodeShape ; sh:nodeKind sh:IRI ; sh:property ex:CompanyName .
ex:CompanyName a sh:PropertyShape ; sh:path ex:name ; sh:minCount 1 ; sh:node ex:PersonShape .
ex:NamedNode a sh:NodeShape ; sh:nodeKind sh:BlankNodeOrIRI .
ex:OrA a sh:NodeShape ; sh:nodeKind sh:IRI .
ex:OrB a sh:NodeShape ; sh:nodeKind sh:Literal .
ex:Unrelated a sh:NodeShape ; sh:nodeKind sh:Literal .
"""
OWL_PRE = "@prefix owl: <http://www.w3.org/2002/07/owl#> . "


def _mod():
    return _g(OWL_PRE + MODULES)


@pytest.mark.parametrize("iri", ["ModuleA", "ModuleB", "ModuleC", "ModuleD", "PersonShape", "Missing"])
@pytest.mark.parametrize("include", [False, True])
def test_extract_shapes_graph_agrees_with_old(iri, include) -> None:
    graph = _mod()
    old = StarShaclSchema(shacl_graph=graph).extract_shapes_graph(EX[iri], include_referenced=include)
    new = extract_shapes_graph(graph, EX[iri], include_referenced=include)
    if old is None:
        assert new is None
    else:
        assert set(new) == set(old)
        assert len(new) > 0


def test_extract_shapes_graph_closure_and_validation() -> None:
    graph = _mod()
    before = set(graph)
    extract = extract_shapes_graph(graph, EX.ModuleA, include_referenced=True)
    assert set(graph) == before
    names = {s for s in extract.subjects() if text(s).startswith(str(EX))}
    assert {EX.PersonWorksFor, EX.Company, EX.CompanyName, EX.NamedNode, EX.OrA, EX.OrB} <= names and EX.Unrelated not in names
    assert (EX.CompanyName, URIRef("http://www.w3.org/ns/shacl#node"), EX.PersonShape) in extract
    data = _g("ex:alice a ex:Person ; ex:worksFor ex:acme ; ex:age 3 .")
    assert not validate(data, extract, meta_shacl=False).conforms


@pytest.mark.parametrize("target", ["missing", "untyped"])
def test_extract_shapes_graph_unresolvable_imports_raise_like_old(target) -> None:
    ttl = OWL_PRE + "ex:M a sh:ShapesGraph ; owl:imports ex:N . " + ("ex:N a ex:Other ." if target == "untyped" else "")
    graph = _g(ttl)
    with pytest.raises(ValueError):
        StarShaclSchema(shacl_graph=graph).extract_shapes_graph(EX.M)
    with pytest.raises(ValueError):
        extract_shapes_graph(graph, EX.M)


def test_extract_shapes_graph_import_cycle_terminates() -> None:
    graph = _g(OWL_PRE + "ex:A a sh:ShapesGraph ; owl:imports ex:B ; rdfs:member ex:SA . ex:B a sh:ShapesGraph ; owl:imports ex:A ; rdfs:member ex:SB .")
    assert set(extract_shapes_graph(graph, EX.A)) == set(StarShaclSchema(shacl_graph=graph).extract_shapes_graph(EX.A))


# ---------------------------------------------------------------- close_shape
CLOSE_CASES = {
    "production shape": (
        "ex:JEShape a sh:NodeShape ; sh:targetClass ex:JournalEntry ; sh:closed true ; sh:ignoredProperties ( rdf:type ex:note ) ; "
        "sh:property [ sh:path ex:amount ; sh:minCount 1 ] ; sh:property [ sh:path ex:account ; sh:minCount 1 ] .",
        EX.JEShape,
    ),
    "no class": ("ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .", EX.S),
    "or group": (
        "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:or ([sh:property [sh:path ex:p ; sh:minCount 1]] [sh:property [sh:path ex:q ; sh:minCount 1]]) .",
        EX.S,
    ),
    "complex paths and equals": (
        "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [sh:path ex:p ; sh:equals ex:q] ; sh:property [sh:path (ex:r ex:s) ; sh:minCount 1] .",
        EX.S,
    ),
    "nested node and qualified": (
        "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:t ; sh:property [ sh:path ex:e ; sh:node ex:N ; sh:qualifiedValueShape ex:N ; sh:qualifiedMinCount 1 ] . "
        "ex:N a sh:NodeShape ; sh:ignoredProperties ( ex:x ) ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .",
        EX.S,
    ),
}


def _canon(graph) -> set:
    """Triples with list/blank nodes of ignoredProperties abstracted to their member lists, so isomorphic outputs compare equal."""
    from rdflib import Graph
    from rdflib.collection import Collection
    from rdflib.compare import to_isomorphic

    rg = Graph()  # rdflib's isomorphism check wants an rdflib graph: convert the result at this boundary
    for t in graph:
        rg.add(tuple(from_engine(x) for x in t))
    ignored = from_engine(URIRef("http://www.w3.org/ns/shacl#ignoredProperties"))
    return to_isomorphic(rg), {tuple(Collection(rg, h)) for h in rg.objects(None, ignored)}


@pytest.mark.parametrize("name", list(CLOSE_CASES))
def test_close_shape_agrees_with_old(name) -> None:
    ttl, shape = CLOSE_CASES[name]
    graph = _g(ttl)
    before = set(graph)
    old = StarShaclSchema(shacl_graph=_g(ttl)).close_shape(shape)
    new = close_shape(graph, shape)
    assert set(graph) == before
    assert _canon(new) == _canon(old)
    assert len(new) == len(old)


def test_close_shape_accepts_the_fragment_and_stays_strict() -> None:
    shapes = _g(
        "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:xone ([sh:property [sh:path ex:p ; sh:minCount 1]] [sh:property [sh:path ex:q ; sh:minCount 0]]) ."
    )
    data = _g("ex:n a ex:C ; ex:p 1 ; ex:z 2 .")
    closed = close_shape(shapes, EX.S)
    fragment = extract_subgraph(data, shapes)
    assert validate(fragment, closed, meta_shacl=False).conforms
    assert not validate(data, closed, meta_shacl=False).conforms


def test_extracted_fragment_of_the_production_shape_conforms_to_its_closed_form() -> None:
    ttl, shape = CLOSE_CASES["production shape"]
    shapes = _g(ttl)
    fragment = extract_subgraph(_g(JE_DATA), shapes, shape=shape, focus_node=EX.je1)
    assert "later note" not in fragment.serialize(format="turtle")
    assert validate(fragment, close_shape(shapes, shape), meta_shacl=False).conforms
    assert re.search("note", fragment.serialize(format="turtle")) is None


def test_target_where_is_a_target_the_old_pyshacl_path_did_not_discover() -> None:
    """Engine-only (SHACL 1.2 sh:targetWhere): focus nodes are the nodes conforming to the shape, and the fragment holds
    the evidence of that conformance too."""
    data = _g('ex:a ex:name "A" ; ex:age 3 . ex:b ex:name "B" .')
    shapes = _g(
        "ex:W a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minCount 1 ] . "
        "ex:S sh:targetWhere ex:W ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
    )
    got = _new(data, shapes, shape=EX.S)
    assert {s for s, _, _ in got} == {EX.a}
    assert any(p == EX.age for _, p, _ in got) and any(p == EX.name for _, p, _ in got)
