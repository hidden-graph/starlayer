"""Regression tests from the entailment bug hunt (one per bug)."""

import os
import shutil
import tempfile
import time
import warnings

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT
from starlayer.graph.graph import _timeout
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

warnings.simplefilter("ignore")

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWLNS = "http://www.w3.org/2002/07/owl#"
PRE = "@prefix : <http://e/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"


def _N(x):
    return ox.NamedNode("http://e/" + x)


def _g(ttl, fmt="turtle"):
    g = StarLayerGraph()
    g.parse(data=PRE + ttl, format=fmt)
    return g


try:
    import owlready2  # noqa: F401
    _HERMIT = shutil.which("java") is not None
except ImportError:
    _HERMIT = False
try:
    import rustdl  # noqa: F401
    _RUSTDL = True
except ImportError:
    _RUSTDL = False

hermit = pytest.mark.skipif(not _HERMIT, reason="needs owlready2 and java")
rustdl_ = pytest.mark.skipif(not _RUSTDL, reason="needs rustdl")
DIRECT = ENTAILMENT["OWL-Direct"]
ENGINES = [pytest.param("hermit", marks=hermit), pytest.param("rustdl", marks=rustdl_)]


def _bnodes(g):
    return {t for tr in g.triples() for t in tr if isinstance(t, ox.BlankNode)}


@hermit
def test_hermit_full_keeps_blank_nodes_and_triple_terms():  # bugs 1, 5, 6, 9
    g = _g(":A a owl:Class . :B a owl:Class . :A rdfs:subClassOf :B . _:anon a :A . :r <" + RDF + "reifies> <<( :s :p :o )>> .", "turtle12")
    before = set(g.triples())
    full = g.infer(DIRECT, mode="full", engine="hermit")
    new = set(full.triples()) - before
    assert not [t for t in new if "canon-tt" in str(t[1])]
    assert len(_bnodes(full)) == len(_bnodes(g))
    assert not [t for t in new if t[1] == ox.NamedNode(RDF + "reifies")]
    assert ox.NamedNode("http://anonymous") not in {t[0] for t in new}
    anon_types = {t[2] for t in full.triples() if isinstance(t[0], ox.BlankNode) and t[1] == ox.NamedNode(RDF + "type")}
    assert _N("B") in anon_types  # the entailment about the anonymous individual survives, on the same node


@hermit
def test_hermit_in_place_does_not_clone_blank_nodes():  # bug 5
    g = _g(":A a owl:Class . :q a owl:ObjectProperty . :x a :A ; :q _:n . _:n a :A .")
    n0 = len(_bnodes(g))
    g.infer(DIRECT, mode="in-place", engine="hermit")
    assert len(_bnodes(g)) == n0
    assert len(list(g.triples((_N("x"), _N("q"), None)))) == 1


@hermit
def test_hermit_in_place_adds_no_triple_term_fragment():  # bug 6
    g = StarLayerGraph()
    g.add((_N("A"), ox.NamedNode(RDF + "type"), ox.NamedNode(OWLNS + "Class")))
    g.add((_N("x"), ox.NamedNode(RDF + "type"), _N("A")))
    g.add((_N("r"), ox.NamedNode(RDF + "reifies"), ox.Triple(_N("x"), _N("q"), _N("y"))))
    n = len(g)
    g.infer(DIRECT, mode="in-place", engine="hermit")
    assert not [t for t in g.triples() if "canon-tt" in t[1].value]
    assert len(_bnodes(g)) == 0
    assert len(g) >= n


@pytest.mark.parametrize("regime", ["RDFS", "OWL-RDF-Based"])
def test_owlrl_delta_hides_the_triple_term_decomposition(regime):  # bugs 2, 7
    g = _g(":a :p :b . :r <" + RDF + "reifies> <<( :a :p :b )>> .", "turtle12")
    for t in g.infer(ENTAILMENT[regime], mode="delta").triples():
        assert not any("canon-tt" in str(x) for x in t), t
        assert not any(isinstance(x, ox.BlankNode) for x in t), t


@hermit
def test_hermit_derives_subproperty_and_inverse():  # bug 3
    g = _g(":q a owl:ObjectProperty . :r a owl:ObjectProperty . :p a owl:ObjectProperty . :x :r :y . :r rdfs:subPropertyOf :q . :p owl:inverseOf :r .")
    full = set(g.infer(DIRECT, mode="full", engine="hermit").triples())
    assert (_N("x"), _N("q"), _N("y")) in full
    assert (_N("y"), _N("p"), _N("x")) in full


@pytest.mark.parametrize("engine", ENGINES)
def test_equivalent_property_entails_the_other_assertion(engine):  # bug 12
    g = _g(":p a owl:ObjectProperty . :q a owl:ObjectProperty . :p owl:equivalentProperty :q . :a :p :b .")
    assert (_N("a"), _N("q"), _N("b")) in set(g.infer(DIRECT, mode="delta", engine=engine).triples())


@pytest.mark.parametrize("engine", ENGINES)
def test_subclass_chain_and_equivalence_are_closed(engine):  # bug 13
    g = _g(":A a owl:Class . :B a owl:Class . :C a owl:Class . :D a owl:Class . :A rdfs:subClassOf :B . :B rdfs:subClassOf :C . :C owl:equivalentClass :D .")
    full = set(g.infer(DIRECT, mode="full", engine=engine).triples())
    sub = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")
    assert (_N("A"), sub, _N("C")) in full
    assert (_N("C"), sub, _N("D")) in full
    assert (_N("D"), sub, _N("C")) in full


def test_owl_rl_query_sees_entailment_in_named_graph():  # bug 4
    d = StarLayerDataset(default_union=True)
    d.graph("http://e/g1").parse(data=PRE + ":A rdfs:subClassOf :B . :x a :A .", format="turtle")
    q = "ASK { GRAPH <http://e/g1> { <http://e/x> a <http://e/B> } }"
    assert bool(d.query(q, entailment=ENTAILMENT.RDFS))
    assert bool(d.query(q, entailment=ENTAILMENT["OWL-RDF-Based"]))


@pytest.mark.parametrize("engine", ENGINES)
def test_direct_delta_has_no_triple_the_graph_holds(engine):  # bug 8
    g = _g(':A a owl:Class . :p a owl:DatatypeProperty . :x a :A ; :p "plain" .')
    have = set(g.triples())
    assert not [t for t in g.infer(DIRECT, mode="delta", engine=engine).triples() if t in have]


@hermit
def test_hermit_empty_graph_has_empty_delta():  # bug 9
    assert len(StarLayerGraph().infer(DIRECT, mode="delta", engine="hermit")) == 0


def _sleep_then_mark(marker, queue):
    time.sleep(3)
    open(marker, "w").write("x")
    queue.put(("ok", None))


def test_timeout_kills_child_started_but_not_yet_in_its_group():  # bug 10
    d = tempfile.mkdtemp()
    marker = os.path.join(d, "m")
    with pytest.raises(_timeout.ReasoningTimeoutError):
        _timeout.run_with_timeout(_sleep_then_mark, (marker,), 0.01)
    time.sleep(6)
    assert not os.path.exists(marker)


def _die(queue):
    raise RuntimeError("child dies without a result")


def test_no_timeout_still_detects_a_dead_child():  # bug 14
    import signal

    def alarm(*_):
        raise TimeoutError("hung")

    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(20)
    try:
        with pytest.raises(_timeout.ReasoningTimeoutError):
            _timeout.run_with_timeout(_die, (), None)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_native_is_not_promised_by_the_regime_docs():  # bug 11
    from starlayer.graph.graph import entailment_regimes

    with pytest.raises(NotImplementedError):
        StarLayerGraph().query("ASK {}", entailment="native")
    assert '"native"' not in (entailment_regimes.__doc__ or "")


@rustdl_
def test_rustdl_types_anonymous_individuals():  # bug 15
    g = _g(":A a owl:Class . :B a owl:Class . :A rdfs:subClassOf :B . _:i a :A .")
    assert bool(g.query("ASK { ?x a <http://e/B> }", entailment=DIRECT, engine="rustdl"))


def test_entailment_copy_keeps_empty_named_graphs():  # bug 16
    d = StarLayerDataset()
    d.graph("http://e/empty")
    d.graph("http://e/full").parse(data="<http://e/a> <http://e/p> <http://e/b> .", format="turtle")
    q = "SELECT ?g WHERE { GRAPH ?g { } }"
    rl = ENTAILMENT["OWL-RDF-Based"]
    plain = sorted(str(r[0]) for r in d.query(q))
    assert sorted(str(r[0]) for r in d.query(q, entailment=rl)) == plain
    s = d.entailment_session(rl)
    try:
        assert sorted(str(r[0]) for r in s.query(q)) == plain
    finally:
        s.close()


def test_rdf_entailment_types_only_real_container_membership_properties():  # bug 17
    g = StarLayerGraph()
    for n in ("_0", "_01", "_1", "_²", "_٣"):
        g.add((_N("a"), _N("p"), ox.NamedNode(RDF + n)))
    d = g.infer(ENTAILMENT.RDF, mode="delta")
    typed = {t[0].value[len(RDF):] for t in d.triples() if t[0].value.startswith(RDF)}
    assert typed == {"_1", "type"}
