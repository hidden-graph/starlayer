"""Regression coverage for starlayergraph.rdfc, a from-scratch RDFC-1.0
(RDF Dataset Canonicalization, https://www.w3.org/TR/rdf-canon/)
implementation extended for RDF 1.2 triple terms.

No existing Python library both implements RDFC-1.0 correctly *and*
understands RDF 1.2 triple terms - confirmed by checking the two closest
PyPI candidates (`rdfcanon`, `diffable-rdf`) directly: both are single-
author, essentially unadopted projects (1 star each; one ~6 months stale,
the other ~6 weeks old and self-labeled alpha), and neither has any RDF 1.2
awareness. This module was verified directly against the spec's own worked
examples (below) and the official W3C RDFC-1.0 test suite (61/64
`RDFC10EvalTest` cases passing when run manually against a local checkout of
`w3c/rdf-canon`'s `tests/rdfc10/` - the 3 that don't pass are all the same
single, understood, non-algorithmic cause: rdflib's own `Literal` class
normalizes the lexical form of recognized XSD datatypes (`xsd:dateTime`,
`xsd:double`) at construction time, before this module's code ever runs, so
the *original* lexical form the fixture's input document used is
unrecoverable - confirmed live that even a bare `Literal("...Z",
datatype=XSD.dateTime)` constructor call normalizes `Z` to `+00:00` with no
parser involved at all. This is an inherent rdflib limitation affecting any
code built on it, not a gap in this module's own canonicalization logic -
the full official test suite isn't vendored into this repo (a possible
future improvement); the two spec examples below are checked exactly
instead, plus the specific behaviors (named graphs, SHA-384, the DoS budget)
that running the full suite surfaced as needing dedicated coverage.
"""

import pytest
from rdflib import Dataset, Graph

from starlayergraph.rdfc import CanonicalizationComplexityError, rdfc10_hash, to_canonical_nquads

_PREFIX = "@prefix : <http://example.com/#> .\n"


class TestSpecWorkedExamples:
    """https://www.w3.org/TR/rdf-canon/#example-unique, #example-shared -
    exact expected output transcribed from the spec text."""

    def test_example_2_unique_hashes(self) -> None:
        g = Graph()
        g.parse(data=_PREFIX + ":p :q _:e0 . :p :r _:e1 . _:e0 :s :u . _:e1 :t :u .", format="turtle")
        expected = (
            "<http://example.com/#p> <http://example.com/#q> _:c14n0 .\n"
            "<http://example.com/#p> <http://example.com/#r> _:c14n1 .\n"
            "_:c14n0 <http://example.com/#s> <http://example.com/#u> .\n"
            "_:c14n1 <http://example.com/#t> <http://example.com/#u> .\n"
        )
        assert to_canonical_nquads(g) == expected

    def test_example_3_shared_hashes(self) -> None:
        """Exercises Hash N-Degree Quads' permutation/recursion logic and
        step 5.3's ordered canonical-identifier issuance - the part of the
        algorithm most implementations get subtly wrong."""
        g = Graph()
        g.parse(
            data=_PREFIX + (
                ":p :q _:e0 . :p :q _:e1 . _:e0 :p _:e2 . _:e1 :p _:e3 . _:e2 :r _:e3 ."
            ),
            format="turtle",
        )
        expected = (
            "<http://example.com/#p> <http://example.com/#q> _:c14n2 .\n"
            "<http://example.com/#p> <http://example.com/#q> _:c14n3 .\n"
            "_:c14n0 <http://example.com/#r> _:c14n1 .\n"
            "_:c14n2 <http://example.com/#p> _:c14n1 .\n"
            "_:c14n3 <http://example.com/#p> _:c14n0 .\n"
        )
        assert to_canonical_nquads(g) == expected


class TestNamedGraphs:
    """Hash Related Blank Node's "position g" and Hash N-Degree Quads step 3
    ("subject, object, or graph name") explicitly cover a blank graph name -
    exercised here since StarLayerGraph itself never produces one, but the
    algorithm has to handle it for e.g. a raw rdflib.Dataset input."""

    def test_uriref_graph_name_round_trips(self) -> None:
        ds = Dataset()
        ds.parse(
            data="<urn:ex:s> <urn:ex:p> <urn:ex:o> <urn:ex:g> .",
            format="nquads",
        )
        assert to_canonical_nquads(ds) == "<urn:ex:s> <urn:ex:p> <urn:ex:o> <urn:ex:g> .\n"

    def test_blank_graph_name_gets_a_canonical_label(self) -> None:
        ds = Dataset()
        ds.parse(
            data="_:b1 <http://xmlns.com/foaf/0.1/homepage> <http://example.org/> _:g .",
            format="nquads",
        )
        got = to_canonical_nquads(ds)
        assert got.count("_:c14n") == 2  # both the subject and the graph name


class TestHashAlgorithm:
    def test_sha384_produces_a_96_hex_char_digest(self) -> None:
        g = Graph()
        g.parse(data=_PREFIX + ":p :q _:e0 .", format="turtle")
        digest = rdfc10_hash(g, hash_algorithm="sha384")
        assert len(digest) == 96  # SHA-384 -> 384 bits -> 96 hex chars

    def test_sha256_and_sha384_give_different_digests(self) -> None:
        g = Graph()
        g.parse(data=_PREFIX + ":p :q _:e0 .", format="turtle")
        assert rdfc10_hash(g, hash_algorithm="sha256") != rdfc10_hash(g, hash_algorithm="sha384")

    def test_unsupported_hash_algorithm_raises(self) -> None:
        g = Graph()
        g.parse(data=_PREFIX + ":p :q _:e0 .", format="turtle")
        with pytest.raises(ValueError):
            rdfc10_hash(g, hash_algorithm="not-a-real-algorithm")


class TestDenialOfServiceDefense:
    """RDFC-1.0 section 7.1 "Dataset Poisoning": "Implementations MUST
    defend against potential denial-of-service attacks by raising suitable
    exceptions and terminating early." Confirmed live, before this defense
    existed, that the official test suite's own poisoning fixture (test074,
    "poison - Clique Graph") hung indefinitely rather than raising anything -
    a fully-symmetric N-node blank-node clique makes the naive permutation
    search in Hash N-Degree Quads combinatorially explosive (10 nodes -> up
    to 10! = 3,628,800 permutations, and the shape recurses)."""

    @staticmethod
    def _clique(n: int) -> Graph:
        lines = [
            f"_:e{i} <http://example.com/p> _:e{j} ."
            for i in range(n)
            for j in range(n)
        ]
        g = Graph()
        g.parse(data="\n".join(lines), format="nt")
        return g

    def test_a_small_symmetric_clique_stays_within_the_default_budget(self) -> None:
        # A 4-node clique's permutation search is still small - this must
        # NOT raise, confirming the budget doesn't reject ordinary
        # (if unusual) legitimate input, only genuinely explosive cases.
        to_canonical_nquads(self._clique(4))

    def test_a_10_node_clique_raises_instead_of_hanging(self) -> None:
        with pytest.raises(CanonicalizationComplexityError):
            to_canonical_nquads(self._clique(10))

    def test_a_lower_budget_rejects_a_smaller_clique_too(self) -> None:
        with pytest.raises(CanonicalizationComplexityError):
            to_canonical_nquads(self._clique(4), permutation_budget=1)
