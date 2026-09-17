"""Regression coverage for starlayergraph.compare's RDF-1.2 (triple-term)
fix to isomorphism/canonicalization.

Confirmed live, before this fix existed, that plain rdflib.compare against a
StarLayerGraph containing a triple term:
- isomorphic() gave the WRONG answer for two graphs that are genuinely
  isomorphic but differ only in an arbitrary blank-node label nested inside
  a triple term.
- to_isomorphic() crashed outright (AssertionError: Term <<(...)>> must be
  an rdflib term), since TripleTerm isn't an rdflib.term.Node subclass.

Each test below would fail against that old, unpatched behavior - see
starlayergraph/compare.py's own module docstring for why the decomposition
fix is correct.
"""

from starlayergraph import StarLayerGraph
from starlayergraph.compare import isomorphic, to_canonical_hash, to_isomorphic


def _graph(data: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=data, format="turtle12")
    return g


class TestTripleTermIsomorphism:
    def test_renamed_blank_node_nested_inside_a_triple_term_is_still_isomorphic(self) -> None:
        g1 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:b1 ex:knows ex:carol )>> . _:b1 ex:name \"Bob\" ."
        )
        g2 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:xyz ex:knows ex:carol )>> . _:xyz ex:name \"Bob\" ."
        )
        assert isomorphic(g1, g2) is True

    def test_genuinely_different_triple_term_content_is_not_isomorphic(self) -> None:
        g1 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:b1 ex:knows ex:carol )>> . _:b1 ex:name \"Bob\" ."
        )
        g2 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:b1 ex:knows ex:dave )>> . _:b1 ex:name \"Bob\" ."
        )
        assert isomorphic(g1, g2) is False

    def test_ground_triple_term_repeated_across_two_triples_is_isomorphic(self) -> None:
        data = (
            "@prefix ex: <http://example.org/> ."
            "ex:a ex:p <<( ex:x ex:y ex:z )>> . ex:b ex:q <<( ex:x ex:y ex:z )>> ."
        )
        assert isomorphic(_graph(data), _graph(data)) is True

    def test_nested_triple_term_with_a_renamed_inner_blank_node_is_isomorphic(self) -> None:
        g1 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:a ex:p <<( ex:x ex:y <<( _:n1 ex:q ex:r )>> )>> . _:n1 ex:label \"inner\" ."
        )
        g2 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:a ex:p <<( ex:x ex:y <<( _:zzz ex:q ex:r )>> )>> . _:zzz ex:label \"inner\" ."
        )
        assert isomorphic(g1, g2) is True

    def test_to_isomorphic_no_longer_crashes_on_a_triple_term(self) -> None:
        g = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:b1 ex:knows ex:carol )>> . _:b1 ex:name \"Bob\" ."
        )
        to_isomorphic(g)  # would raise AssertionError before the fix

    def test_to_canonical_hash_agrees_with_isomorphic(self) -> None:
        g1 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:b1 ex:knows ex:carol )>> . _:b1 ex:name \"Bob\" ."
        )
        g2 = _graph(
            "@prefix ex: <http://example.org/> ."
            "ex:claim1 ex:says <<( _:xyz ex:knows ex:carol )>> . _:xyz ex:name \"Bob\" ."
        )
        assert to_canonical_hash(g1) == to_canonical_hash(g2)


class TestPlainGraphRegressionSafety:
    """Graphs with no triple terms at all must behave exactly as rdflib's
    own isomorphic() already did - the fix must not change behavior for the
    overwhelmingly common case."""

    def test_renamed_blank_node_with_no_triple_terms_is_isomorphic(self) -> None:
        g1 = _graph("@prefix ex: <http://example.org/> . ex:a ex:p _:b1 . _:b1 ex:q \"hi\" .")
        g2 = _graph("@prefix ex: <http://example.org/> . ex:a ex:p _:zzz . _:zzz ex:q \"hi\" .")
        assert isomorphic(g1, g2) is True


class TestDirLangStringIsomorphism:
    """DirLangString decodes to a plain, non-Node Python object on public
    iteration, exactly like TripleTerm - confirmed live this broke the same
    way once _decompose() started rebuilding a real graph via .add()."""

    def test_same_direction_is_isomorphic(self) -> None:
        g1 = _graph(
            '@prefix ex: <http://example.org/> . '
            'ex:a ex:greeting "hi"@en--ltr ; ex:friend _:b1 . _:b1 ex:name "Bob" .'
        )
        g2 = _graph(
            '@prefix ex: <http://example.org/> . '
            'ex:a ex:greeting "hi"@en--ltr ; ex:friend _:zzz . _:zzz ex:name "Bob" .'
        )
        assert isomorphic(g1, g2) is True

    def test_different_direction_is_not_isomorphic(self) -> None:
        g1 = _graph('@prefix ex: <http://example.org/> . ex:a ex:greeting "hi"@en--ltr .')
        g2 = _graph('@prefix ex: <http://example.org/> . ex:a ex:greeting "hi"@en--rtl .')
        assert isomorphic(g1, g2) is False

    def test_triple_term_and_dirlangstring_together(self) -> None:
        g1 = _graph(
            '@prefix ex: <http://example.org/> . '
            'ex:a ex:says <<( _:b1 ex:greeting "hi"@en--ltr )>> . _:b1 ex:name "Bob" .'
        )
        g2 = _graph(
            '@prefix ex: <http://example.org/> . '
            'ex:a ex:says <<( _:zzz ex:greeting "hi"@en--ltr )>> . _:zzz ex:name "Bob" .'
        )
        assert isomorphic(g1, g2) is True


class TestSimpleLiteralVsExplicitXsdStringIsomorphism:
    """rdflib's own Literal treats a simple literal (datatype=None) as
    unequal to the same lexical value with an explicit xsd:string datatype,
    even though RDF 1.1 Concepts defines a simple literal as sugar for the
    xsd:string-typed form - confirmed live this made isomorphic() see two
    genuinely identical graphs as different whenever one happened to have
    passed through a serializer (nt12/nq12/trix12) that writes the datatype
    explicitly and the other didn't. See compare.py's own module docstring."""

    def test_plain_and_explicit_xsd_string_are_isomorphic(self) -> None:
        g1 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "high" .')
        g2 = _graph(
            '@prefix ex: <http://example.org/> . '
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . '
            'ex:a ex:p "high"^^xsd:string .'
        )
        assert isomorphic(g1, g2) is True

    def test_plain_vs_language_tagged_is_still_not_isomorphic(self) -> None:
        g1 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "high" .')
        g2 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "high"@en .')
        assert isomorphic(g1, g2) is False

    def test_plain_vs_genuinely_different_value_is_still_not_isomorphic(self) -> None:
        g1 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "high" .')
        g2 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "low" .')
        assert isomorphic(g1, g2) is False

    def test_explicit_xsd_string_vs_other_explicit_datatype_is_not_isomorphic(self) -> None:
        g1 = _graph(
            '@prefix ex: <http://example.org/> . '
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . '
            'ex:a ex:p "1"^^xsd:string .'
        )
        g2 = _graph(
            '@prefix ex: <http://example.org/> . '
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . '
            'ex:a ex:p "1"^^xsd:integer .'
        )
        assert isomorphic(g1, g2) is False

    def test_to_canonical_hash_agrees_for_plain_and_explicit_xsd_string(self) -> None:
        g1 = _graph('@prefix ex: <http://example.org/> . ex:a ex:p "high" .')
        g2 = _graph(
            '@prefix ex: <http://example.org/> . '
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . '
            'ex:a ex:p "high"^^xsd:string .'
        )
        assert to_canonical_hash(g1) == to_canonical_hash(g2)
