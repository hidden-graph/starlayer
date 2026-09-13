"""Regression coverage for StarShaclValidator.extract_subgraph() - see
starshacl/subgraph_extraction.py's module docstring for the full design
(agreed with the user across several turns before implementation: multi-hop
paths keep every intervening triple with cycle detection, nested/referenced
shapes are included recursively, only the branch that actually passed is
included for sh:or/sh:xone, ambiguous "at least one" requirements widen to
include every satisfying candidate rather than picking an arbitrary one,
and only real stored triples are ever included).
"""

from starlayergraph import StarLayerGraph
from starshacl import StarShaclValidator, close_shape


def _graph(data: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=data, format="turtle12")
    return g


def _closes(data_graph, shapes_ttl: str) -> bool:
    """The acceptance test the user specified: the extracted subgraph,
    re-validated against the same shape but with sh:closed true and no
    ignored properties, must itself conform."""
    closed_shapes = _graph(shapes_ttl)
    return StarShaclValidator().validate(data_graph=data_graph, shacl_graph=closed_shapes, meta_shacl=False).conforms


class TestBasicExtractionAndAcceptanceTest:
    """The motivating use case: a journal entry with a note added later that
    isn't part of the shape - the note must not survive extraction, and the
    result must independently conform when the shape is closed."""

    DATA = """
        @prefix ex: <http://example.org/> .
        ex:je1 a ex:JournalEntry ; ex:amount 100 ; ex:account ex:acct1 ; ex:note "later note" .
    """
    SHAPE = """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:JEShape a sh:NodeShape ; sh:targetClass ex:JournalEntry ;
          sh:property [ sh:path ex:amount ; sh:minCount 1 ] ;
          sh:property [ sh:path ex:account ; sh:minCount 1 ] .
    """
    CLOSED_SHAPE = """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:JEShape a sh:NodeShape ; sh:targetClass ex:JournalEntry ; sh:closed true ;
          sh:property [ sh:path ex:amount ; sh:minCount 1 ] ;
          sh:property [ sh:path ex:account ; sh:minCount 1 ] .
    """

    def _extract(self):
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        result = StarShaclValidator().extract_subgraph(
            data_graph=_graph(self.DATA),
            shacl_graph=_graph(self.SHAPE),
            shape=EX.JEShape,
            focus_node=EX.je1,
        )
        return result

    def test_conforms_and_note_is_excluded(self) -> None:
        result = self._extract()
        assert result.conforms is True
        serialized = result.data_graph.serialize(format="turtle12")
        assert "later note" not in serialized
        assert "100" in serialized  # amount
        assert "acct1" in serialized  # account

    def test_extracted_subgraph_passes_the_closed_shape_acceptance_test(self) -> None:
        result = self._extract()
        assert _closes(result.data_graph, self.CLOSED_SHAPE) is True

    def test_non_conforming_focus_node_gives_conforms_false_and_no_subgraph(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph("@prefix ex: <http://example.org/> . ex:je2 a ex:JournalEntry .")  # missing amount/account
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=_graph(self.SHAPE), shape=EX.JEShape, focus_node=EX.je2
        )
        assert result.conforms is False
        assert result.data_graph is None


class TestMultiHopPaths:
    """Decision 1: a sequence path keeps every intervening triple, not just
    the endpoint."""

    def test_sequence_path_includes_both_hops(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            "@prefix ex: <http://example.org/> . "
            'ex:alice ex:employee ex:bob ; ex:unrelated "noise" . '
            'ex:bob ex:name "Bob" ; ex:secret "shh" .'
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; "
            "sh:property [ sh:path (ex:employee ex:name) ; sh:minCount 1 ] ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "ex:bob" in serialized or "bob" in serialized
        assert "Bob" in serialized
        assert "noise" not in serialized
        assert "shh" not in serialized

    def test_zero_or_more_path_terminates_on_a_cycle_and_captures_reachable_edges(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            "@prefix ex: <http://example.org/> . "
            "ex:alice ex:friend ex:bob . "
            "ex:bob ex:friend ex:alice, ex:carol . "
            "ex:carol ex:friend ex:carol . "  # self-loop
            "ex:dave a ex:Unrelated ."
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; "
            "sh:property [ sh:path [ sh:zeroOrMorePath ex:friend ] ; sh:minCount 1 ] ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        assert result.conforms is True
        serialized = result.data_graph.serialize(format="turtle12")
        assert "dave" not in serialized
        # alice, bob, carol should all appear via their friend edges,
        # including the self-loop - and it must have terminated at all
        # (this test itself timing out would be the real failure mode).
        assert serialized.count("friend") == 3


class TestNestedShapes:
    """Decision 2: sh:node recurses into the referenced shape."""

    def test_sh_node_includes_the_nested_shapes_own_required_triples(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            "@prefix ex: <http://example.org/> . "
            'ex:alice ex:employee ex:bob . ex:bob ex:name "Bob" ; ex:secret "shh" .'
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:PersonShape a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; "
            "sh:property [ sh:path ex:employee ; sh:node ex:PersonShape ] ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "Bob" in serialized
        assert "shh" not in serialized


class TestLogicalConstraints:
    """Decision 3 (revised): sh:or includes *every* disjunct that passes -
    not just the first in list order, since sh:or only requires at least
    one to pass and more than one may legitimately conform at once. sh:xone
    includes just the one that passes, since sh:xone requires *exactly*
    one - not an arbitrary determinism choice, but the only value that can
    ever legitimately exist (see test_sh_xone below for the consequence
    when data later makes a second disjunct pass too)."""

    def test_sh_or_excludes_the_failing_branch(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            '@prefix ex: <http://example.org/> . ex:alice ex:email "a@example.org" ; ex:phoneUnused "555" .'
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:HasEmail a sh:NodeShape ; sh:property [ sh:path ex:email ; sh:minCount 1 ] . "
            "ex:HasPhone a sh:NodeShape ; sh:property [ sh:path ex:phone ; sh:minCount 1 ] . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:or ( ex:HasEmail ex:HasPhone ) ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "a@example.org" in serialized
        assert "phoneUnused" not in serialized

    def test_sh_or_includes_every_passing_branch(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            '@prefix ex: <http://example.org/> . ex:alice ex:email "a@example.org" ; ex:phone "555" .'
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:HasEmail a sh:NodeShape ; sh:property [ sh:path ex:email ; sh:minCount 1 ] . "
            "ex:HasPhone a sh:NodeShape ; sh:property [ sh:path ex:phone ; sh:minCount 1 ] . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:or ( ex:HasEmail ex:HasPhone ) ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "a@example.org" in serialized
        assert "555" in serialized

    def test_sh_xone_includes_the_one_passing_branch(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph('@prefix ex: <http://example.org/> . ex:alice ex:email "a@example.org" .')
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:HasEmail a sh:NodeShape ; sh:property [ sh:path ex:email ; sh:minCount 1 ] . "
            "ex:HasPhone a sh:NodeShape ; sh:property [ sh:path ex:phone ; sh:minCount 1 ] . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:xone ( ex:HasEmail ex:HasPhone ) ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        assert result.conforms is True
        assert "a@example.org" in result.data_graph.serialize(format="turtle12")

    def test_sh_xone_second_passing_branch_breaks_conformance(self) -> None:
        """If data later changes so a second xone disjunct also passes,
        sh:xone itself is no longer satisfied - extraction must fail
        outright (conforms=False, data_graph=None), not silently include a
        different subgraph."""
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        data = _graph(
            '@prefix ex: <http://example.org/> . ex:alice ex:email "a@example.org" ; ex:phone "555" .'
        )
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:HasEmail a sh:NodeShape ; sh:property [ sh:path ex:email ; sh:minCount 1 ] . "
            "ex:HasPhone a sh:NodeShape ; sh:property [ sh:path ex:phone ; sh:minCount 1 ] . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:xone ( ex:HasEmail ex:HasPhone ) ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=data, shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        assert result.conforms is False
        assert result.data_graph is None


class TestQualifiedValueShapeDeterminism:
    """Decision 4 (include every satisfying candidate, not just the
    minimum) plus the narrowing fix found via live testing (a candidate that
    does *not* satisfy the qualifying shape should be excluded entirely when
    sh:qualifiedValueShape is the only thing constraining the property)."""

    DATA = """
        @prefix ex: <http://example.org/> .
        ex:alice ex:employee ex:bob, ex:carol, ex:dave .
        ex:bob ex:dept ex:Sales . ex:carol ex:dept ex:Sales . ex:dave ex:dept ex:Eng .
    """

    def test_all_qualifying_candidates_are_included_non_qualifying_excluded(self) -> None:
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; "
            "sh:property [ sh:path ex:employee ; "
            "sh:qualifiedValueShape [ sh:property [ sh:path ex:dept ; sh:hasValue ex:Sales ] ] ; "
            "sh:qualifiedMinCount 1 ] ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=_graph(self.DATA), shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "bob" in serialized and "carol" in serialized
        assert "dave" not in serialized
        assert "Eng" not in serialized

    def test_a_coexisting_plain_mincount_forces_the_full_raw_value_set(self) -> None:
        """When something else on the same property shape needs every
        value (here, a plain sh:minCount on the raw path), narrowing must
        not drop the non-qualifying candidate."""
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        shapes = _graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; "
            "sh:property [ sh:path ex:employee ; sh:minCount 3 ; "
            "sh:qualifiedValueShape [ sh:property [ sh:path ex:dept ; sh:hasValue ex:Sales ] ] ; "
            "sh:qualifiedMinCount 1 ] ."
        )
        result = StarShaclValidator().extract_subgraph(
            data_graph=_graph(self.DATA), shacl_graph=shapes, shape=EX.S, focus_node=EX.alice
        )
        serialized = result.data_graph.serialize(format="turtle12")
        assert "dave" in serialized


class TestCloseShape:
    """close_shape() derives the strict, no-exemptions verification shape
    the closed-shape acceptance test needs from a shape's normal production
    form (which very often *does* need sh:ignoredProperties, e.g. for
    rdf:type) - without hand-maintaining a second, drift-prone copy."""

    PROD_SHAPE = """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:JEShape a sh:NodeShape ; sh:targetClass ex:JournalEntry ; sh:closed true ;
          sh:ignoredProperties ( rdf:type ex:note ) ;
          sh:property [ sh:path ex:amount ; sh:minCount 1 ] ;
          sh:property [ sh:path ex:account ; sh:minCount 1 ] .
    """
    DATA = """
        @prefix ex: <http://example.org/> .
        ex:je1 a ex:JournalEntry ; ex:amount 100 ; ex:account ex:acct1 ; ex:note "reviewed by Bob" .
    """

    def test_derived_shape_drops_ignored_properties_but_keeps_closed(self) -> None:
        from rdflib import Namespace
        from rdflib.namespace import SH

        EX = Namespace("http://example.org/")
        prod_shapes = _graph(self.PROD_SHAPE)
        strict_shapes = close_shape(prod_shapes, EX.JEShape)

        closed_values = list(strict_shapes.objects(EX.JEShape, SH.closed))
        assert len(closed_values) == 1 and bool(closed_values[0].toPython())
        assert list(strict_shapes.objects(EX.JEShape, SH.ignoredProperties)) == []

    def test_original_shape_is_never_mutated(self) -> None:
        from rdflib import Namespace
        from rdflib.namespace import SH

        EX = Namespace("http://example.org/")
        prod_shapes = _graph(self.PROD_SHAPE)
        before = len(prod_shapes)
        close_shape(prod_shapes, EX.JEShape)
        assert len(prod_shapes) == before
        assert list(prod_shapes.objects(EX.JEShape, SH.ignoredProperties)) != []

    def test_extract_subgraph_does_not_mutate_the_callers_shapes_graph(self) -> None:
        """A real bug found while testing close_shape(): extract_subgraph()'s
        internal ShapesGraph() wrapper was mutating the caller's own
        shacl_graph in place (injecting RDFS/OWL axiom triples as a side
        effect of shape harvesting) - confirmed live before the fix that
        len(shacl_graph) grew after a single extract_subgraph() call."""
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        prod_shapes = _graph(self.PROD_SHAPE)
        before = len(prod_shapes)
        StarShaclValidator().extract_subgraph(
            data_graph=_graph(self.DATA), shacl_graph=prod_shapes, shape=EX.JEShape, focus_node=EX.je1
        )
        assert len(prod_shapes) == before

    def test_extracted_subgraph_conforms_to_the_derived_strict_shape(self) -> None:
        """The end-to-end workflow: production shape (open enough to tolerate
        rdf:type and free-form notes) -> extract_subgraph() -> close_shape()
        derives the strict version -> the extracted subgraph conforms to it
        with no exemptions needed at all, since extraction already dropped
        both rdf:type and the note."""
        from rdflib import Namespace

        EX = Namespace("http://example.org/")
        prod_shapes = _graph(self.PROD_SHAPE)
        result = StarShaclValidator().extract_subgraph(
            data_graph=_graph(self.DATA), shacl_graph=prod_shapes, shape=EX.JEShape, focus_node=EX.je1
        )
        assert result.conforms is True

        strict_shapes = close_shape(prod_shapes, EX.JEShape)
        check = StarShaclValidator().validate(data_graph=result.data_graph, shacl_graph=strict_shapes, meta_shacl=False)
        assert check.conforms is True
