"""Conformance of the ported StarLayer helpers (infer, derive_shape, imports, skolemize, cbd, qnames) on ``OxGraph`` /
``OxDataset`` against the old ``StarLayerGraph`` / ``StarLayerDataset``.

Each scenario builds the same data (Turtle text) in both classes, runs the same call, and compares the resulting triple sets up
to blank-node isomorphism (``starlayer.graph.rdfc_native.isomorphic``). Inputs are taken from tests/graph/unit/test_infer.py,
test_resolve_imports.py, test_shape_derivation.py, test_dataset.py and test_leftovers_72_75_83.py.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.graph.starlayer_dataset import StarLayerDataset
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.oxgraph import OxDataset, OxGraph
from starlayer.graph.oxgraph.helpers import entailment as ent
from starlayer.graph.oxgraph.helpers import qnames
from starlayer.graph.rdfc_native import isomorphic
from starlayer.shacl_engine.terms import to_engine

owlrl = pytest.importorskip("owlrl")

PFX = """@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""
EX = "http://example.org/"


def old(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def new(ttl: str) -> OxGraph:
    g = OxGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


def ox_triples(g) -> set[ox.Triple]:
    """The triples of an old or new graph as pyoxigraph triples."""
    return {ox.Triple(to_engine(s), to_engine(p), to_engine(o)) for s, p, o in g.triples((None, None, None))}


def same(a, b) -> bool:
    return isomorphic(ox_triples(a), ox_triples(b))


# ---- infer ----------------------------------------------------------------------------------------------------------------

DATA = {
    "rdfs_basic": "ex:Dog rdfs:subClassOf ex:Animal . ex:fido a ex:Dog .",
    "domain_range": "ex:knows rdfs:domain ex:Person ; rdfs:range ex:Person . ex:a ex:knows ex:b . ex:p rdfs:subPropertyOf ex:q . ex:x ex:p ex:y .",
    "bnodes_literals": 'ex:a ex:p [ ex:q "v" , 3 ; a ex:T ] . ex:T rdfs:subClassOf [ a owl:Class ] .',
    "owl_rl": (
        "ex:p a owl:TransitiveProperty . ex:a ex:p ex:b . ex:b ex:p ex:c . ex:r owl:inverseOf ex:s . ex:a ex:r ex:z . "
        "ex:i owl:sameAs ex:j . ex:i ex:p ex:k . ex:C owl:equivalentClass ex:D . ex:m a ex:C . "
        "ex:Hd a owl:Class ; owl:intersectionOf ( ex:A ex:B ) . ex:n a ex:A , ex:B ."
    ),
    "owl_inconsistent": "ex:A owl:disjointWith ex:B . ex:x a ex:A , ex:B . ex:f a owl:FunctionalProperty . ex:u ex:f ex:v , ex:w .",
    "triple_term": "ex:claim ex:asserts <<( ex:alice ex:age 30 )>> . ex:claim a ex:Claim . ex:Claim rdfs:subClassOf ex:Thing .",
    "reifier": "ex:r rdf:reifies <<( ex:s ex:p ex:o )>> ; ex:by ex:me . ex:s ex:p ex:o .",
    "rdf_container": "ex:l rdf:_1 ex:a ; rdf:_2 ex:b ; rdf:first ex:a ; rdf:rest rdf:nil . ex:b a rdf:List .",
    "empty": "",
}
R = ent.ENTAILMENT
REGIMES = {
    "rdfs": [R.RDFS],
    "rdf": [R.RDF],
    "owlrl": [R["OWL-RDF-Based"]],
    "rdfs+owlrl": [R.RDFS, R["OWL-RDF-Based"]],
    "rdf+rdfs": [R.RDF, R.RDFS],
    "rdf+owlrl": [R.RDF, R["OWL-RDF-Based"]],
}


def _old_regimes(regs):
    from rdflib import URIRef

    return [URIRef(r.value) for r in regs]


@pytest.mark.parametrize("mode", ["full", "delta"])
@pytest.mark.parametrize("regime", list(REGIMES))
@pytest.mark.parametrize("data", list(DATA))
def test_infer_matches_old(data, regime, mode):
    regs = REGIMES[regime]
    o = old(DATA[data]).infer(entailment=_old_regimes(regs), mode=mode)
    n = new(DATA[data]).infer(regs, mode=mode)
    assert isinstance(n, OxGraph)
    if data == "owl_inconsistent" and "owl" in regime:
        # owlrl itself is not deterministic here (the old class gives 127 or 128 triples depending on the hash seed: the number of
        # err:ErrorMessage nodes), so compare the triples without blank nodes, and require an error message in both.
        a, b = ox_triples(o), ox_triples(n)
        flat = lambda ts: {t for t in ts if not any(isinstance(x, ox.BlankNode) for x in (t.subject, t.object))}  # noqa: E731
        assert flat(a) == flat(b)
        msg = ox.NamedNode("http://www.daml.org/2002/03/agents/agent-ont#ErrorMessage")
        assert any(t.object == msg for t in a) and any(t.object == msg for t in b)
        return
    assert same(o, n)


@pytest.mark.parametrize("data", ["rdfs_basic", "owl_rl", "triple_term"])
def test_infer_in_place_matches_old(data):
    go, gn = old(DATA[data]), new(DATA[data])
    ro = go.infer(entailment=_old_regimes([R["OWL-RDF-Based"]]), mode="in-place")
    rn = gn.infer(R["OWL-RDF-Based"], mode="in-place")
    assert ro is go and rn is gn
    assert same(go, gn)


def test_infer_default_is_rdfs_full():
    assert same(old(DATA["rdfs_basic"]).infer(), new(DATA["rdfs_basic"]).infer())


def test_infer_leaves_source_and_uses_target_graph_without_clearing():
    g = new(DATA["rdfs_basic"])
    before = set(g.triples())
    target = OxGraph()
    target.add((ox.NamedNode(EX + "someone"), ox.NamedNode(EX + "marker"), ox.NamedNode(EX + "value")))
    out = g.infer(target_graph=target)
    assert out is target and set(g.triples()) == before
    assert (ox.NamedNode(EX + "fido"), ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), ox.NamedNode(EX + "Animal")) in out
    assert (ox.NamedNode(EX + "someone"), ox.NamedNode(EX + "marker"), ox.NamedNode(EX + "value")) in out


def test_infer_accepts_str_regime_and_old_uriref_regime():
    from rdflib import RDFS

    assert same(old(DATA["rdfs_basic"]).infer(), new(DATA["rdfs_basic"]).infer(R.RDFS.value))
    assert same(new(DATA["rdfs_basic"]).infer(R.RDFS), new(DATA["rdfs_basic"]).infer(str(R.RDFS.value)))
    del RDFS


ERROR_CASES = {
    "bogus_regime": dict(entailment="bogus"),
    "bad_mode": dict(mode="nope"),
    "empty_regimes": dict(entailment=[]),
    "d_entailment": dict(entailment="http://www.w3.org/ns/entailment/D"),
    "engine_for_rdfs": dict(engine="rustdl"),
    "timeout_for_rdfs": dict(timeout=5),
    "target_with_in_place": dict(mode="in-place", target_graph="graph"),
    "owl_direct_with_other": dict(entailment=["http://www.w3.org/ns/entailment/OWL-Direct", "http://www.w3.org/ns/entailment/RDFS"]),
}


@pytest.mark.parametrize("case", list(ERROR_CASES))
def test_infer_errors_match_old(case):
    kw = dict(ERROR_CASES[case])
    outcomes = []
    for make, graph_cls in ((old, StarLayerGraph), (new, OxGraph)):
        g = make(DATA["rdfs_basic"])
        k = dict(kw)
        if k.get("target_graph") == "graph":
            k["target_graph"] = graph_cls()
        if "entailment" in k and isinstance(k["entailment"], list):
            k["entailment"] = [e for e in k["entailment"]]
        try:
            g.infer(**k)
            outcomes.append(None)
        except Exception as e:  # noqa: BLE001
            outcomes.append(type(e).__name__)
    assert outcomes[0] == outcomes[1] and outcomes[0] is not None


def test_infer_target_graph_type_error_both():
    from rdflib import Graph

    with pytest.raises(TypeError):
        old(DATA["rdfs_basic"]).infer(target_graph=Graph())
    with pytest.raises(TypeError):
        new(DATA["rdfs_basic"]).infer(target_graph=object())


def test_infer_repeats_owlrl_to_a_fixpoint_issue_97():
    """Inferring on the closure adds nothing more (the closure is closed), as in the old class."""
    for make in (old, new):
        closed = make(DATA["rdfs_basic"]).infer()
        assert len(closed.infer(mode="delta")) == 0


def test_entailment_constants_match_old():
    from starlayer.graph.graph import entailment_regimes as old_ent

    for name in ("RDF", "RDFS", "D", "OWL-RDF-Based", "OWL-Direct"):
        assert str(old_ent.ENTAILMENT[name]) == R[name].value
    assert {str(x) for x in old_ent.SUPPORTED_REGIMES} == set(ent.SUPPORTED_REGIMES)
    assert {str(x) for x in old_ent.KNOWN_REGIMES} == set(ent.KNOWN_REGIMES)


def test_default_timeout_matches_old():
    from starlayer.graph.graph import _timeout

    assert _timeout.DEFAULT_TIMEOUT_SECONDS == ent.DEFAULT_TIMEOUT


def _owl_direct_available() -> str:
    import shutil

    try:
        import owlready2  # noqa: F401
    except ImportError:
        return "no owlready2"
    return "" if shutil.which("java") else "no java"


def test_owl_direct_hermit_same_outcome_as_old():
    """Without owlready2 / java both raise the same RuntimeError; with them the closures are isomorphic."""
    outcomes = []
    for make, regs in ((old, _old_regimes([R["OWL-Direct"]])), (new, R["OWL-Direct"])):
        try:
            r = make(DATA["rdfs_basic"]).infer(entailment=regs, timeout=60) if make is old else make(DATA["rdfs_basic"]).infer(regs, timeout=60)
            outcomes.append(r)
        except RuntimeError as e:
            outcomes.append(("RuntimeError", str(e)[:60]))
    if _owl_direct_available():
        assert outcomes[0] == outcomes[1] and isinstance(outcomes[0], tuple)
    else:
        assert same(outcomes[0], outcomes[1])


def test_owl_direct_rustdl_same_outcome_as_old():
    outcomes = []
    for make in (old, new):
        g = make(DATA["rdfs_basic"])
        try:
            if make is old:
                outcomes.append(g.infer(entailment=_old_regimes([R["OWL-Direct"]]), engine="rustdl", timeout=60))
            else:
                outcomes.append(g.infer(R["OWL-Direct"], engine="rustdl", timeout=60))
        except RuntimeError as e:
            outcomes.append(("RuntimeError", str(e)[:50]))
    if isinstance(outcomes[0], tuple):
        assert outcomes[0] == outcomes[1]
    else:
        assert same(outcomes[0], outcomes[1])


def test_owl_direct_unknown_engine_value_error_both():
    for make, regs in ((old, _old_regimes([R["OWL-Direct"]])), (new, R["OWL-Direct"])):
        g = make(DATA["rdfs_basic"])
        with pytest.raises((ValueError, RuntimeError)) as e:
            g.infer(entailment=regs, engine="x") if make is old else g.infer(regs, engine="x")
        assert type(e.value).__name__ == "ValueError"


def test_owl_direct_timeout_wrapper_is_the_old_one(monkeypatch):
    """The OWL-DL path goes through the old subprocess timeout wrapper with the timeout passed on."""
    seen = {}

    def fake_classify(graph, timeout=None):
        seen["timeout"] = timeout
        return graph, graph.__class__()

    import starlayer.graph.graph.owl_dl as owl_dl

    monkeypatch.setattr(owl_dl, "classify_owl_dl", fake_classify)
    new(DATA["rdfs_basic"]).infer(R["OWL-Direct"], timeout=7)
    assert seen["timeout"] == 7


# ---- derive_shape ---------------------------------------------------------------------------------------------------------

PEOPLE = (
    "ex:alice a ex:Person ; ex:name 'Alice' ; ex:age 30 ; ex:knows ex:bob . ex:bob a ex:Person ; ex:name 'Bob' ; ex:age 25 ."
)
SHAPE_DATA = {
    "people": PEOPLE,
    "two_classes": PEOPLE + " ex:acme a ex:Organization ; ex:name 'Acme' .",
    "triple_terms": "ex:c1 a ex:Claim ; ex:asserts <<( ex:alice ex:age 30 )>> . ex:c2 a ex:Claim ; ex:asserts <<( ex:bob ex:age 25 )>> .",
    "mixed_kinds": "ex:c1 a ex:Claim ; ex:asserts <<( ex:alice ex:age 30 )>> . ex:c2 a ex:Claim ; ex:asserts ex:someResource .",
    "default_ignored": PEOPLE + " ex:alice rdfs:label 'Alice the person' . ex:bob rdfs:label 'Bob the person' .",
    "langs_and_bnodes": "ex:a a ex:T ; ex:l 'x'@en , 'y'@fr ; ex:b [ ex:q 1 ] . ex:b2 a ex:T ; ex:l 'z'@en ; ex:b [ ex:q 2 ] .",
}


def _template(extra: str) -> str:
    return "[] a sh:NodeShape ; sh:targetClass ex:Person ; sh:closed true ; sh:property [ sh:path ex:name " + extra + " ] ."


TEMPLATES = {
    "min_count_too_high": ("ex:alice a ex:Person ; ex:name 'Alice' . ex:bob a ex:Person ; ex:name 'Bob', 'Bobby' .", _template("; sh:minCount 2")),
    "wrong_datatype": ("ex:alice a ex:Person ; ex:name 'Alice' . ex:bob a ex:Person ; ex:name 'Bob' .", _template("; sh:datatype xsd:integer")),
    "violated_pattern": ("ex:alice a ex:Person ; ex:name 'Alice' .", _template("; sh:pattern '^Z'")),
    "in_widened": ("ex:alice a ex:Person ; ex:name 'Alice' . ex:bob a ex:Person ; ex:name 'Zed' .", _template("; sh:in ( 'Alice' )")),
    "new_property_and_class": (PEOPLE + " ex:acme a ex:Organization ; ex:name 'Acme' .", _template("")),
}


@pytest.mark.parametrize("name", list(SHAPE_DATA))
def test_derive_shape_fresh_matches_old(name):
    o, n = old(SHAPE_DATA[name]).derive_shape(), new(SHAPE_DATA[name]).derive_shape()
    assert isinstance(n, OxGraph) and len(n) > 0
    assert same(o, n)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_derive_shape_with_template_matches_old(name):
    data, tpl = TEMPLATES[name]
    o = old(data).derive_shape(old(tpl))
    n = new(data).derive_shape(new(tpl))
    assert same(o, n)


def test_derive_shape_ignored_properties_options_match_old():
    from rdflib import URIRef

    o = old(PEOPLE).derive_shape(ignored_properties=[URIRef(EX + "age")])
    n = new(PEOPLE).derive_shape(ignored_properties=[ox.NamedNode(EX + "age")])
    assert same(o, n)
    o2 = old(SHAPE_DATA["default_ignored"]).derive_shape(use_default_ignored_properties=False)
    n2 = new(SHAPE_DATA["default_ignored"]).derive_shape(use_default_ignored_properties=False)
    assert same(o2, n2)


def test_derive_shape_result_validates_the_data():
    from starlayer.shacl_engine import validate

    data = new(PEOPLE)
    assert validate(data, data.derive_shape()).conforms


# ---- resolve_imports ------------------------------------------------------------------------------------------------------

IMPORT_REGISTRY = {
    "chain": ("ex:a owl:imports ex:b .", {"b": "ex:b owl:imports ex:c . ex:bFact a ex:BThing .", "c": "ex:cFact a ex:CThing ."}),
    "cycle": ("ex:a owl:imports ex:b .", {"b": "ex:b owl:imports ex:a . ex:bFact a ex:BThing .", "a": "ex:a owl:imports ex:b ."}),
    "versioned": (
        "ex:this owl:imports ex:versionedOntology .",
        {"versionedOntology": "ex:baseOntology owl:versionIRI ex:versionedOntology ; owl:imports ex:furtherThing . ex:versionedFact a ex:Thing .",
         "furtherThing": "ex:furtherFact a ex:FurtherThing ."},
    ),
    "unresolvable": ("ex:a owl:imports ex:nowhere . ex:s ex:p ex:o .", {}),
    "local_import": ("ex:a owl:imports ex:b . ex:b a owl:Ontology . ex:b owl:imports ex:c .", {"c": "ex:cFact a ex:CThing ."}),
    "overlap_with_self": ("ex:a owl:imports ex:b . ex:shared ex:p ex:o .", {"b": "ex:shared ex:p ex:o . ex:only ex:p ex:o ."}),
    "bnode_content": ("ex:a owl:imports ex:b .", {"b": "ex:x ex:p [ ex:q 1 ] ."}),
}


@pytest.mark.parametrize("mode", ["full", "delta", "in-place"])
@pytest.mark.parametrize("name", list(IMPORT_REGISTRY))
def test_resolve_imports_matches_old(name, mode):
    text, modules = IMPORT_REGISTRY[name]
    calls_old, calls_new = [], []

    def loader_for(make, calls):
        graphs = {EX + k: make(v) for k, v in modules.items()}

        def loader(iri):
            calls.append(str(iri.value if hasattr(iri, "value") else iri))
            return graphs.get(str(iri.value if hasattr(iri, "value") else iri))

        return loader

    go, gn = old(text), new(text)
    ro = go.resolve_imports(loader=loader_for(old, calls_old), mode=mode)
    rn = gn.resolve_imports(loader=loader_for(new, calls_new), mode=mode)
    assert same(ro, rn)
    assert calls_old == calls_new  # same loader calls in the same order
    if mode == "in-place":
        assert ro is go and rn is gn


def test_resolve_imports_without_loader_and_owl_imports():
    text = "ex:a owl:imports ex:b , ex:c . ex:z owl:imports ex:b ."
    o, n = old(text), new(text)
    # the order is that of a set (it follows the hash seed), so compare sorted
    assert sorted(str(x) for x in o.owl_imports()) == sorted(x.value for x in n.owl_imports())
    assert same(o.resolve_imports(), n.resolve_imports())
    assert same(o.resolve_imports(mode="delta"), n.resolve_imports(mode="delta")) and len(n.resolve_imports(mode="delta")) == 0


def test_has_import_locally_matches_old():
    o, n = old("ex:a ex:p ex:b ."), new("ex:a ex:p ex:b .")
    from rdflib import URIRef

    for iri in ("a", "b", "nope"):
        assert o.has_import_locally(URIRef(EX + iri)) == n.has_import_locally(ox.NamedNode(EX + iri))


def test_resolve_imports_errors_match_old():
    for g in (old("ex:a ex:p ex:b ."), new("ex:a ex:p ex:b .")):
        with pytest.raises(ValueError):
            g.resolve_imports(mode="bogus")
        with pytest.raises(ValueError):
            g.resolve_imports(mode="in-place", target_graph=type(g)())


def test_resolve_imports_accepts_an_old_graph_from_the_loader():
    """Migration aid: a loader that still returns an old StarLayerGraph works."""
    o = old("ex:a owl:imports ex:b .")
    ob = old("ex:bFact a ex:BThing .")
    n = new("ex:a owl:imports ex:b .")
    assert same(o.resolve_imports(loader=lambda i: ob), n.resolve_imports(loader=lambda i: ob))


def test_can_resolve_import():
    from starlayer.graph.oxgraph.helpers.imports import can_resolve_import

    assert can_resolve_import(ox.NamedNode(EX + "x"), loader=lambda i: OxGraph())
    assert not can_resolve_import(ox.NamedNode(EX + "x"), loader=lambda i: None)


# ---- skolemize / de_skolemize ---------------------------------------------------------------------------------------------

def _same_bnode_ids(cls, extra_triple_term: bool):
    """Both classes with literally the same blank node ids, so skolem IRIs can be compared exactly."""
    from rdflib import BNode, URIRef
    from starlayer.graph.model import TripleTerm
    from starlayer.graph.oxgraph import terms

    g = cls()
    if cls is StarLayerGraph:
        N, B, L = URIRef, BNode, __import__("rdflib").Literal
        add = g.add
    else:
        N, B, L = ox.NamedNode, ox.BlankNode, ox.Literal
        add = g.add
    add((B("b1"), N(EX + "p"), B("b2")))
    add((B("b2"), N(EX + "q"), L("v")))
    add((N(EX + "s"), N(EX + "p"), B("b1")))
    if extra_triple_term:
        tt = TripleTerm(N(EX + "q"), N(EX + "r"), B("b1")) if cls is StarLayerGraph else terms.Triple(N(EX + "q"), N(EX + "r"), B("b1"))
        add((N(EX + "x"), N(EX + "s"), tt))
        tt2 = TripleTerm(B("b2"), N(EX + "r"), N(EX + "o")) if cls is StarLayerGraph else terms.Triple(B("b2"), N(EX + "r"), N(EX + "o"))
        add((N(EX + "y"), N(EX + "s"), tt2))
    return g


@pytest.mark.parametrize("tt", [False, True])
def test_skolemize_exactly_matches_old(tt):
    o, n = _same_bnode_ids(StarLayerGraph, tt), _same_bnode_ids(OxGraph, tt)
    so, sn = o.skolemize(), n.skolemize()
    assert isinstance(sn, OxGraph)
    assert ox_triples(so) == ox_triples(sn)
    assert not any(isinstance(t, ox.BlankNode) for tr in sn.triples() for t in tr)


def test_skolemize_single_bnode_authority_basepath_match_old():
    from rdflib import BNode

    o, n = _same_bnode_ids(StarLayerGraph, True), _same_bnode_ids(OxGraph, True)
    assert ox_triples(o.skolemize(bnode=BNode("b1"))) == ox_triples(n.skolemize(bnode=ox.BlankNode("b1")))
    assert ox_triples(o.skolemize(authority="http://ex.org/", basepath="/g/")) == ox_triples(n.skolemize(authority="http://ex.org/", basepath="/g/"))


@pytest.mark.parametrize("tt", [False, True])
def test_de_skolemize_round_trip_matches_old(tt):
    o, n = _same_bnode_ids(StarLayerGraph, tt), _same_bnode_ids(OxGraph, tt)
    assert ox_triples(o.skolemize().de_skolemize()) == ox_triples(o) == ox_triples(n.skolemize().de_skolemize()) == ox_triples(n)


def test_de_skolemize_foreign_genid_gives_fresh_bnodes_both():
    ttl = "<http://other.org/.well-known/genid/xyz> ex:p <http://other.org/.well-known/genid/xyz> , ex:o ."
    o, n = old(ttl).de_skolemize(), new(ttl).de_skolemize()
    assert same(o, n)
    (s, _, ob), = [t for t in n.triples((None, ox.NamedNode(EX + "p"), None)) if isinstance(t[2], ox.BlankNode)]
    assert s == ob  # one IRI -> one blank node
    assert len(n) == 2


def test_de_skolemize_single_uriref():
    """Known difference (old quirk): rdflib compares a ``Genid`` argument with a plain ``URIRef`` as unequal, so the old method
    leaves everything skolemized when ``uriref=`` is given; the new one restores just that IRI."""
    n = _same_bnode_ids(OxGraph, False).skolemize()
    iri = "https://rdflib.github.io/.well-known/genid/rdflib/b1"
    out = n.de_skolemize(uriref=ox.NamedNode(iri))
    assert ox.BlankNode("b1") in {t[0] for t in out.triples()} | {t[2] for t in out.triples()}
    assert ox.NamedNode(iri.replace("b1", "b2")) in {t[0] for t in out.triples()} | {t[2] for t in out.triples()}
    assert ox.NamedNode(iri) not in {t[0] for t in out.triples()} | {t[2] for t in out.triples()}


def test_skolemize_target_graph_type_checked():
    with pytest.raises(TypeError):
        new("ex:a ex:p ex:b .").skolemize(new_graph=object())
    t = OxGraph()
    assert new("ex:a ex:p ex:b .").skolemize(new_graph=t) is t


# ---- cbd -----------------------------------------------------------------------------------------------------------------

CBD_DATA = (
    "ex:alice ex:name 'Alice' ; ex:address [ ex:city 'X' ; ex:geo [ ex:lat 1 ] ] ; ex:knows ex:bob . ex:bob ex:name 'Bob' . "
    "ex:r a rdf:Statement ; rdf:subject ex:alice ; rdf:predicate ex:name ; rdf:object 'Alice' ; ex:source ex:src ; ex:note [ ex:t 'n' ] . "
    "ex:r2 rdf:subject ex:alice ; rdf:predicate ex:knows ; rdf:object ex:bob ; ex:conf 1 . ex:other ex:p ex:q ."
)


@pytest.mark.parametrize("resource", ["alice", "bob", "other", "missing", "r"])
@pytest.mark.parametrize("reif", [True, False])
def test_cbd_matches_old(resource, reif):
    from rdflib import URIRef

    o = old(CBD_DATA).cbd(URIRef(EX + resource), include_reifications=reif)
    n = new(CBD_DATA).cbd(ox.NamedNode(EX + resource), include_reifications=reif)
    assert same(o, n)


def test_cbd_with_triple_term_and_target_graph():
    from rdflib import URIRef

    ttl = "ex:claim1 ex:asserts <<( ex:alice ex:age 30 )>> ; ex:by [ ex:n 'x' ] . ex:z ex:p ex:q ."
    o = old(ttl).cbd(URIRef(EX + "claim1"))
    t = OxGraph()
    n = new(ttl).cbd(ox.NamedNode(EX + "claim1"), target_graph=t)
    assert n is t and same(o, n)
    with pytest.raises(TypeError):
        new(ttl).cbd(ox.NamedNode(EX + "claim1"), target_graph=object())


def test_dataset_cbd_scoped_by_default_union_like_old():
    from rdflib import Namespace as RNs

    ex = RNs(EX)
    od = StarLayerDataset(default_union=True)
    od.default_graph.add((ex.alice, ex.p, ex.o1))
    od.graph(ex.g1).add((ex.alice, ex.p, ex.o2))
    nd = OxDataset(default_union=True)
    N = ox.NamedNode
    nd.add((N(EX + "alice"), N(EX + "p"), N(EX + "o1")))
    nd.graph(N(EX + "g1")).add((N(EX + "alice"), N(EX + "p"), N(EX + "o2")))
    nd_iso = OxDataset(default_union=False, store=nd.store)
    od_iso = StarLayerDataset(default_union=False)
    assert len(nd.cbd(N(EX + "alice"))) == 2
    assert len(nd_iso.cbd(N(EX + "alice"))) == 1
    od_iso.default_graph.add((ex.alice, ex.p, ex.o1))
    od_iso.graph(ex.g1).add((ex.alice, ex.p, ex.o2))
    assert len(od_iso.cbd(ex.alice)) == 1
    assert len(od.cbd(ex.alice)) == len(nd.cbd(N(EX + "alice")))


def test_dataset_skolemize_and_empty_like():
    nd = OxDataset()
    nd.add((ox.BlankNode("b"), ox.NamedNode(EX + "p"), ox.Literal("v")))
    assert isinstance(nd.skolemize(), OxGraph) and len(nd.skolemize()) == 1
    e = nd.empty_like()
    assert isinstance(e, OxDataset) and len(e) == 0 and e.default_union == nd.default_union


# ---- empty_like and qnames ------------------------------------------------------------------------------------------------

def test_empty_like_matches_old_shape():
    o, n = old("ex:a ex:p ex:b ."), new("ex:a ex:p ex:b .")
    eo, en = o.empty_like(), n.empty_like()
    assert len(eo) == len(en) == 0
    assert dict((p, str(ns)) for p, ns in eo.namespaces() if p == "ex") == {"ex": EX} == {p: ns for p, ns in en.prefixes.items() if p == "ex"}
    en.add((ox.NamedNode(EX + "x"), ox.NamedNode(EX + "y"), ox.NamedNode(EX + "z")))
    assert len(n) == 1  # independent


def test_empty_like_is_independent_of_persistent_source(tmp_path):
    g = OxGraph(path=str(tmp_path / "db"))
    g.add((ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.NamedNode(EX + "b")))
    e = g.empty_like()
    assert len(e) == 0 and len(g) == 1


@pytest.mark.parametrize("iri", [EX + "Thing", "http://www.w3.org/2001/XMLSchema#integer", EX + "a/b", "http://nowhere.org/ns#name", "http://nowhere.org/a/b/c"])
def test_qname_matches_old(iri):
    """Bound namespaces give the same qname; for an unbound one both generate a prefix (``ns1`` vs rdflib's ``ns1``) with the
    same local name. Where rdflib fails (a local name containing ``/``) the new helper fails too, with ``ValueError``."""
    from rdflib import URIRef

    o, n = old(""), OxGraph()
    for g in (o, n):
        g.bind("ex", EX)
        g.bind("xsd", "http://www.w3.org/2001/XMLSchema#")
    try:
        qo = o.qname(URIRef(iri))
    except Exception:  # noqa: BLE001
        qo = None
    try:
        qn = n.qname(ox.NamedNode(iri))
    except ValueError:
        qn = None
    if qo is None or qn is None:
        assert iri in (EX + "a/b",) or qo == qn
        return
    assert qo == qn


def test_compute_qname_expand_curie_and_no_generate():
    n = OxGraph()
    n.bind("ex", EX)
    assert n.compute_qname(ox.NamedNode(EX + "Thing")) == ("ex", EX, "Thing")
    assert n.expand_curie("ex:Thing") == ox.NamedNode(EX + "Thing")
    with pytest.raises(KeyError):
        n.compute_qname(ox.NamedNode("http://nowhere.org/ns#name"), generate=False)
    assert n.qname(ox.NamedNode("http://nowhere.org/ns#name")).endswith(":name")
    assert "ns1" in n.prefixes
    assert qnames.expand_curie({"a": "http://a/"}, "a:b").value == "http://a/b"
