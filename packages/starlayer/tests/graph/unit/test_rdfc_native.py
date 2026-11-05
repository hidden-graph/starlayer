"""starlayer.graph.rdfc_native: Oxigraph's RDFC-1.0, the W3C suite, properties, and a brute-force oracle."""

from __future__ import annotations

import random
from pathlib import Path

import pyoxigraph as ox
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from starlayer.graph.interop import to_basic
from starlayer.graph.rdfc_native import (
    CanonicalizationComplexityError,
    canonical_hash,
    canonical_nquads,
    canonical_quads,
    isomorphic,
)

from ._interop_corpus import (
    brute_isomorphic,
    gen_dataset,
    iri,
    mutate,
    relabel,
    symmetric_pair,
)

DG = ox.DefaultGraph()
B = ox.BlankNode
SUITE = Path(__file__).resolve().parents[1] / "vendor" / "rdfc10"
MF = "http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#"
RDFC = "https://w3c.github.io/rdf-canon/tests/vocab#"


def q(s, p, o, g=DG):
    return ox.Quad(s, p, o, g)


def tt(s, p, o):
    return ox.Triple(s, p, o)


def parse_nq(text: str):
    return list(ox.parse(text.encode(), format=ox.RdfFormat.N_QUADS, rename_blank_nodes=False))


# ------------------------------------------------------------------------------------------ W3C test suite


def _suite_cases():
    triples = list(ox.parse((SUITE / "manifest.ttl").read_bytes(), format=ox.RdfFormat.TURTLE, base_iri="http://x/"))
    props: dict = {}
    for t in triples:
        props.setdefault(t.subject, {}).setdefault(t.predicate.value, []).append(t.object)
    out = []
    for s, d in props.items():
        kinds = [o.value.removeprefix(RDFC) for o in d.get("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", [])]
        if "RDFC10EvalTest" in kinds:
            alg = d.get(RDFC + "hashAlgorithm", [ox.Literal("SHA256")])[0].value
            out.append((s.value.rsplit("#", 1)[-1], d[MF + "action"][0].value.removeprefix("http://x/"),
                        d[MF + "result"][0].value.removeprefix("http://x/"), alg))
    return sorted(out)


SUITE_CASES = _suite_cases()


def test_suite_is_vendored_and_complete():
    assert len(SUITE_CASES) == 64  # RDFC10EvalTest entries; 22 map tests and 1 negative test are not run here


@pytest.mark.parametrize("name,action,result,alg", SUITE_CASES, ids=[c[0] for c in SUITE_CASES])
def test_w3c_rdfc10_eval(name, action, result, alg):
    quads = parse_nq((SUITE / action).read_text(encoding="utf-8"))
    got = canonical_nquads(quads, algorithm=alg.lower(), basic=False)
    assert got == (SUITE / result).read_text(encoding="utf-8")


def test_w3c_poison_negative():
    """test074: a 10-blank-node clique is a NEGATIVE test, canonicalisation must raise instead of hanging."""
    manifest = (SUITE / "manifest.ttl").read_text(encoding="utf-8")
    assert "test074c a rdfc:RDFC10NegativeEvalTest" in manifest
    quads = parse_nq((SUITE / "rdfc10/test074-in.nq").read_text(encoding="utf-8"))
    with pytest.raises(CanonicalizationComplexityError):
        canonical_nquads(quads)


def _clique(n):
    p = ox.NamedNode("http://e/p")
    b = [B(f"b{i}") for i in range(n)]
    return [q(b[i], p, b[j]) for i in range(n) for j in range(n) if i != j]


def _torus(n):
    p = ox.NamedNode("http://e/p")
    b = {(i, j): B(f"g{i}_{j}") for i in range(n) for j in range(n)}
    return [q(x, p, b[((i + 1) % n, j)]) for (i, j), x in b.items()] + [q(x, p, b[(i, (j + 1) % n)]) for (i, j), x in b.items()]


@pytest.mark.parametrize("data", [_clique(10), _clique(8), _torus(6)], ids=["clique-10", "clique-8", "torus-6x6"])
def test_symmetric_blank_node_structures_raise_instead_of_hanging(data):
    with pytest.raises(CanonicalizationComplexityError):
        canonical_nquads(data)
    with pytest.raises(CanonicalizationComplexityError):
        isomorphic(data, data)
    with pytest.raises(CanonicalizationComplexityError):
        isomorphic(data, data, basic=True)


def test_a_symmetric_structure_inside_triple_terms_raises_too():
    p = ox.NamedNode("http://e/p")
    b = [B(f"b{i}") for i in range(10)]
    data = [q(iri("s"), p, tt(b[i], p, b[j])) for i in range(10) for j in range(10) if i != j]
    with pytest.raises(CanonicalizationComplexityError):
        canonical_nquads(data)


def test_large_but_harmless_blank_node_structures_are_accepted():
    p = ox.NamedNode("http://e/p")
    cycle = [q(B(f"c{i}"), p, B(f"c{(i + 1) % 100}")) for i in range(100)]
    leaves = [q(iri("s"), p, B(f"l{i}")) for i in range(500)]
    hub = [q(B("hub"), p, B(f"h{i}")) for i in range(100)]
    path = [q(B(f"q{i}"), p, B(f"q{i + 1}")) for i in range(60)]
    seven = _clique(7)
    for data in (leaves, hub, path):
        assert isomorphic(data, relabel(data, random.Random(1)))
    assert isomorphic(seven, relabel(seven, random.Random(1)))
    assert canonical_nquads(cycle)


# ----------------------------------------------------------------------------------------- spec examples


def test_spec_examples_2_and_3_through_the_basic_path():
    ex = "http://example.com/#"
    ds = [q(iri("x"), ox.NamedNode(ex + "q"), B("e0"))]
    assert canonical_nquads(ds, basic=False) == "<http://e/x> <http://example.com/#q> _:c14n0 .\n"
    shared = parse_nq(
        "<http://example.com/#p> <http://example.com/#q> _:e0 .\n<http://example.com/#p> <http://example.com/#q> _:e1 .\n"
        "_:e0 <http://example.com/#p> _:e2 .\n_:e1 <http://example.com/#p> _:e3 .\n_:e2 <http://example.com/#r> _:e3 .\n")
    assert canonical_nquads(shared) == (
        "<http://example.com/#p> <http://example.com/#q> _:c14n2 .\n<http://example.com/#p> <http://example.com/#q> _:c14n3 .\n"
        "_:c14n0 <http://example.com/#r> _:c14n1 .\n_:c14n2 <http://example.com/#p> _:c14n1 .\n_:c14n3 <http://example.com/#p> _:c14n0 .\n")


def test_named_graph_and_blank_graph_name_cases_of_the_old_suite():
    assert canonical_nquads(parse_nq("<urn:ex:s> <urn:ex:p> <urn:ex:o> <urn:ex:g> .")) == "<urn:ex:s> <urn:ex:p> <urn:ex:o> <urn:ex:g> .\n"
    got = canonical_nquads(parse_nq("_:b1 <http://xmlns.com/foaf/0.1/homepage> <http://example.org/> _:g ."))
    assert got.count("_:c14n") == 2


def test_hash_lengths_and_algorithm_names():
    ds = [q(iri("p"), iri("q"), B("e0"))]
    assert len(canonical_hash(ds)) == 64 and len(canonical_hash(ds, algorithm="sha384")) == 96
    assert canonical_hash(ds, algorithm=ox.CanonicalizationAlgorithm.RDFC_1_0_SHA_384) == canonical_hash(ds, algorithm="SHA-384")
    assert canonical_hash(ds) != canonical_hash(ds, algorithm="sha384")
    with pytest.raises(ValueError):
        canonical_hash(ds, algorithm="md5")
    with pytest.raises(ValueError):
        canonical_hash(ds, algorithm=ox.CanonicalizationAlgorithm.UNSTABLE)


def test_input_is_not_relabelled():
    ds = ox.Dataset([q(B("keep"), iri("p"), B("me"))])
    canonical_nquads(ds)
    isomorphic(ds, ds)
    assert {x.subject.value for x in ds} == {"keep"}


# ---------------------------------------------------------------------------------------------- properties

SEEDS = st.integers(0, 10**6)


@given(SEEDS)
@settings(max_examples=150, deadline=None)
def test_canonical_form_is_invariant_under_relabelling_and_quad_order(seed):
    rng = random.Random(seed)
    a = gen_dataset(rng)
    b = relabel(a, rng)
    assert canonical_nquads(a) == canonical_nquads(b)
    assert canonical_hash(a) == canonical_hash(b)
    assert canonical_nquads(a, basic=False) == canonical_nquads(b, basic=False)
    assert isomorphic(a, b) and isomorphic(a, b, basic=True)


@given(SEEDS)
@settings(max_examples=100, deadline=None)
def test_canonical_form_has_no_triple_term_and_canonical_labels(seed):
    qs = canonical_quads(gen_dataset(random.Random(seed)))
    assert not any(isinstance(x.object, ox.Triple) for x in qs)
    assert all(x.subject.value.startswith("c14n") for x in qs if isinstance(x.subject, B))


def test_triple_term_blank_node_identity_does_not_matter():
    def build(label, other):
        return [q(iri("c"), iri("says"), tt(B(label), iri("knows"), iri("carol"))), q(B(label), iri("name"), ox.Literal("Bob")),
                q(B(other), iri("name"), ox.Literal("Bob"))]

    a, b = build("b1", "z"), build("xyz", "k")
    assert isomorphic(a, b) and isomorphic(a, b, basic=True)
    assert canonical_hash(a) == canonical_hash(b)
    # a different blank node inside the triple term is a different dataset
    c = [q(iri("c"), iri("says"), tt(B("other"), iri("knows"), iri("carol"))), q(B("b1"), iri("name"), ox.Literal("Bob")),
         q(B("other"), iri("name"), ox.Literal("Bob"))]
    assert not isomorphic(a, c, basic=True) or isomorphic(a, c)  # verdicts agree, whatever they are
    assert isomorphic(a, c) == isomorphic(a, c, basic=True) == brute_isomorphic(a, c)


def test_the_encoding_blank_node_of_a_triple_term_is_not_identity():
    """Two datasets differing only in the (fresh) blank node of the encoding are isomorphic: canonical forms agree."""
    t = tt(iri("s"), iri("p"), B("x"))
    data = [q(iri("a"), iri("p"), t), q(B("x"), iri("n"), ox.Literal("v"))]
    assert canonical_nquads(to_basic(data)) == canonical_nquads(to_basic(data, bnode_prefix="q")) == canonical_nquads(data)


def test_shared_versus_unshared_triple_term_occurrences_are_different():
    t = tt(iri("s"), iri("p"), iri("o"))
    one = [q(iri("a"), iri("p"), t), q(iri("b"), iri("p"), t)]
    assert canonical_hash(one) != canonical_hash([q(iri("a"), iri("p"), t)])


@given(SEEDS)
@settings(max_examples=100, deadline=None)
def test_isomorphic_agrees_with_a_brute_force_oracle(seed):
    rng = random.Random(seed)
    a = gen_dataset(rng)
    r = rng.random()
    b = relabel(a, rng) if r < 0.4 else relabel(mutate(a, rng), rng) if r < 0.85 else gen_dataset(rng)
    truth = brute_isomorphic(a, b)
    assert isomorphic(a, b) is truth
    assert isomorphic(a, b, basic=True) is truth


def test_symmetric_structures_with_and_without_triple_terms():
    for w in range(6):
        a, b, c = symmetric_pair(random.Random(w))
        c = relabel(c, random.Random(w))
        assert not isomorphic(a, b) and not isomorphic(a, b, basic=True)  # 4-cycle versus two 2-cycles
        assert isomorphic(a, c) and isomorphic(a, c, basic=True)
        assert canonical_nquads(a) != canonical_nquads(b) and canonical_nquads(a) == canonical_nquads(c)


class TestBlankNodeGraphNames:
    """rdf-canon issue #233 (open upstream): isomorphic datasets with a blank node as graph name can get different
    canonical forms. Not reproduced here by pyoxigraph 0.5.13; the cases below are the random and symmetric ones."""

    def test_blank_graph_name_shared_with_subject(self):
        a = parse_nq("_:g <http://e/p> _:h _:g .\n_:h <http://e/p> _:g _:h .\n_:x <http://e/q> <http://e/o> _:g .\n")
        for seed in range(20):
            b = relabel(a, random.Random(seed))
            assert canonical_nquads(a) == canonical_nquads(b) and isomorphic(a, b)

    def test_two_symmetric_blank_graphs(self):
        a = parse_nq("<http://e/s> <http://e/p> _:x _:g1 .\n<http://e/s> <http://e/p> _:y _:g2 .\n_:g1 <http://e/p> _:g2 .\n_:g2 <http://e/p> _:g1 .\n")
        for seed in range(20):
            assert canonical_nquads(relabel(a, random.Random(seed))) == canonical_nquads(a)

    @given(SEEDS)
    @settings(max_examples=150, deadline=None)
    def test_random_datasets_with_blank_graph_names(self, seed):
        rng = random.Random(seed)
        a = gen_dataset(rng, triple_terms=False, directions=False, max_bnodes=5)
        b = relabel(a, rng)
        assert canonical_nquads(a, basic=False) == canonical_nquads(b, basic=False)
        assert isomorphic(a, b)

    def test_graph_names_count_in_isomorphism(self):
        a = [q(iri("s"), iri("p"), iri("o"), iri("g1"))]
        b = [q(iri("s"), iri("p"), iri("o"), iri("g2"))]
        c = [q(iri("s"), iri("p"), iri("o"), B("g"))]
        assert not isomorphic(a, b) and not isomorphic(a, c)
        assert isomorphic(c, [q(iri("s"), iri("p"), iri("o"), B("other"))])
        assert not isomorphic(a, [q(iri("s"), iri("p"), iri("o"))])


# ----------------------------------------------------------------------------------- verdicts against a brute-force oracle


@given(SEEDS)
@settings(max_examples=150, deadline=None)
def test_isomorphism_verdicts_agree_with_the_oracle(seed):
    rng = random.Random(seed)
    a = gen_dataset(rng)
    r = rng.random()
    b = relabel(a, rng) if r < 0.4 else relabel(mutate(a, rng), rng) if r < 0.85 else gen_dataset(rng)
    truth = brute_isomorphic(a, b)
    assert isomorphic(a, b) is isomorphic(a, b, basic=True) is truth


def test_known_disagreement_a_blank_node_twice_in_one_quad():
    """For `_:b0 p _:b2 _:b0` (b0 is subject and graph name) Oxigraph counts the quad once in b0's list (the spec's own gloss:
    'the set of quads of which it is a component'); the removed pure-Python rdfc.py added it twice and swapped the labels
    (documented in docs/working/interop-and-rdfc.md). Hand check: sha256 of b0's first-degree line is smaller than b2's, so b0 is c14n0."""
    a = parse_nq("_:b0 <http://e/p> _:b2 _:b0 .\n")
    assert canonical_nquads(a, basic=False) == "_:c14n0 <http://e/p> _:c14n1 _:c14n0 .\n"
    import hashlib

    h = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
    assert h("_:a <http://e/p> _:z _:a .\n") < h("_:z <http://e/p> _:a _:z .\n")
