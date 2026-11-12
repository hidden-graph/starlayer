"""extract_subgraph() and computed values: ``sh:values`` / ``sh:defaultValue`` (GitHub issues #202 and #203).

The conformance check inside extraction evaluates what validate() evaluates, computed values included (#202); the
fragment holds the stored triples read to compute each value, in every expression form, and never a computed triple
itself (#203, design decision 5), so that evaluating the fragment recomputes the same values.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import evaluate, extract_subgraph, validate


class _Namespace:
    def __getattr__(self, name: str) -> ox.NamedNode:
        return ox.NamedNode(f"http://example.org/{name}")


EX = _Namespace()

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix sparql: <http://www.w3.org/ns/sparql#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

DATA = """
ex:a a ex:Person ; ex:first "Ada" ; ex:last "Lovelace" ; ex:noise "n" ; ex:child ex:c1 .
ex:c1 ex:name "C1" ; ex:other "o" .
"""

# the issue #202 repro, verbatim
ISSUE_202_SHAPES = """
ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:Name, ex:Full .
ex:Name a sh:PropertyShape ; sh:path ex:first ; sh:minCount 1 .
ex:Full a sh:PropertyShape ; sh:path ex:fullName ; sh:minCount 1 ;
    sh:values [ sparql:concat ( [ shnex:pathValues ex:first ] " " [ shnex:pathValues ex:last ] ) ] .
"""


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _shapes_for(expr: str, *, predicate: str = "sh:values", extra: str = "") -> str:
    return f"""
    ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:virtual ; {predicate} {expr} ; {extra} ] .
    """.replace("; ]", "]")


def _extract(shapes: str, data: str = DATA, node=EX.a, **kwargs):
    return extract_subgraph(_g(data), _g(shapes), shape=EX.S, focus_node=node, **kwargs)


def _stored(result, *predicates) -> set[tuple]:
    return {(s, p, o) for s, p, o in result if p in predicates}


class TestConformanceUsesComputedValues:
    """#202."""

    def test_issue_repro_extracts_non_empty(self) -> None:
        shapes, data = _g(ISSUE_202_SHAPES), _g(DATA)
        assert validate(data, shapes).conforms
        assert len(extract_subgraph(data, shapes, shape=EX.S, focus_node=EX.a)) > 0

    def test_extraction_in_a_fresh_process_does_not_depend_on_validate_having_run(self) -> None:
        # the sh:values patch is process-global and validate() installed it: run the extraction alone in a new process
        import subprocess
        import sys

        code = (
            "from starlayer.graph import StarLayerGraph\n"
            "from starlayer.shacl import extract_subgraph\n"
            "import pyoxigraph as ox\n"
            "class N:\n"
            "    def __getattr__(self, n): return ox.NamedNode('http://example.org/' + n)\n"
            "EX = N()\n"
            f"P = {PREFIXES!r}\n"
            f"s = StarLayerGraph(); s.parse(data=P + {ISSUE_202_SHAPES!r}, format='turtle12')\n"
            f"d = StarLayerGraph(); d.parse(data=P + {DATA!r}, format='turtle12')\n"
            "print(len(extract_subgraph(d, s, shape=EX.S, focus_node=EX.a)))\n"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert int(out.stdout.strip().splitlines()[-1]) > 0

    def test_conforms_only_through_the_computed_value_and_includes_its_inputs(self) -> None:
        result = _extract(ISSUE_202_SHAPES)
        assert _stored(result, EX.first, EX.last) == {
            (EX.a, EX.first, next(iter(_g(DATA).objects(EX.a, EX.first)))),
            (EX.a, EX.last, next(iter(_g(DATA).objects(EX.a, EX.last)))),
        }
        assert not _stored(result, EX.fullName)  # the computed triple is never output
        assert not _stored(result, EX.noise)

    def test_constraint_on_the_computed_value(self) -> None:
        shapes = ISSUE_202_SHAPES.replace("sh:minCount 1 ;\n    sh:values", "sh:minCount 1 ; sh:hasValue \"Ada Lovelace\" ;\n    sh:values")
        assert validate(_g(DATA), _g(shapes)).conforms
        assert len(_extract(shapes)) > 0

    def test_non_conforming_node_stays_empty(self) -> None:
        shapes = ISSUE_202_SHAPES.replace("sh:minCount 1 ;\n    sh:values", "sh:minCount 1 ; sh:minLength 50 ;\n    sh:values")
        assert not validate(_g(DATA), _g(shapes)).conforms
        assert len(_extract(shapes)) == 0


@pytest.mark.parametrize(
    ("label", "expr", "expected_predicates"),
    [
        ("pathValues", "[ shnex:pathValues ex:first ]", {EX.first}),
        ("multi-hop", "[ shnex:pathValues ( ex:child ex:name ) ]", {EX.child, EX.name}),
        (
            "nested in sparql:concat",
            '[ sparql:concat ( [ shnex:pathValues ex:first ] " " [ shnex:pathValues ex:last ] ) ]',
            {EX.first, EX.last},
        ),
        (
            "nested in several levels",
            '[ sparql:concat ( [ sparql:concat ( [ shnex:pathValues ex:first ] "-" ) ] [ shnex:pathValues ( ex:child ex:name ) ] ) ]',
            {EX.first, EX.child, EX.name},
        ),
        ("sh:select", '[ sh:select "SELECT ?n WHERE { $this <http://example.org/last> ?n }" ]', {EX.last}),
        ("sh:sparqlExpr (no read)", '[ sh:sparqlExpr "1 + 1" ]', set()),
    ],
)
class TestEveryExpressionFormReadsAreInTheFragment:
    """#203: the stored triples read are in the fragment, the computed value is not, and nothing else is."""

    @pytest.mark.parametrize("predicate", ["sh:values", "sh:defaultValue"])
    def test_reads_are_in_the_fragment(self, label, expr, expected_predicates, predicate) -> None:
        shapes = _shapes_for(expr, predicate=predicate)
        result = _extract(shapes, include_targets=False)
        data = _g(DATA)
        assert {p for _s, p, _o in result} == expected_predicates, label
        assert all(t in data for t in result)  # only real, stored triples
        assert not _stored(result, EX.virtual)

    def test_evaluating_the_fragment_gives_the_same_computed_values(self, label, expr, expected_predicates) -> None:
        shapes = _g(_shapes_for(expr))
        data = _g(DATA)
        fragment = extract_subgraph(data, shapes, shape=EX.S, focus_node=EX.a)
        assert _stored(evaluate(fragment, shapes), EX.virtual) == _stored(evaluate(data, shapes), EX.virtual)
        assert _stored(evaluate(data, shapes), EX.virtual), "the expression computes something"


class TestDefaultValue:
    def test_default_value_reads_are_included_only_when_it_is_used(self) -> None:
        shapes = _shapes_for("[ shnex:pathValues ex:first ]", predicate="sh:defaultValue")
        # no stored ex:virtual: the default is computed, so ex:first is read
        assert {p for _s, p, _o in _extract(shapes, include_targets=False)} == {EX.first}
        # a stored ex:virtual value wins: the default is not evaluated, nothing is read for it
        data = DATA + 'ex:a ex:virtual "stored" .'
        assert {p for _s, p, _o in _extract(shapes, data, include_targets=False)} == {EX.virtual}


class TestCustomFunction:
    FUNCTION = """
    ex:spacedConcat a sh:ListParameterExpressionFunction ;
      sh:bodyExpression [ sparql:concat ( [ shnex:arg 0 ] " " [ shnex:arg 1 ] ) ] ;
      sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ] ;
      sh:parameter [ a sh:Parameter ; sh:path shnex:arg1 ] .
    """

    def test_a_custom_function_call_reads_are_included(self) -> None:
        shapes = self.FUNCTION + _shapes_for(
            "[ ex:spacedConcat ( [ shnex:pathValues ex:first ] [ shnex:pathValues ( ex:child ex:name ) ] ) ]"
        )
        result = _extract(shapes, include_targets=False)
        assert {p for _s, p, _o in result} == {EX.first, EX.child, EX.name}
        assert _stored(evaluate(extract_subgraph(_g(DATA), _g(shapes), shape=EX.S, focus_node=EX.a), _g(shapes)), EX.virtual) == {
            (EX.a, EX.virtual, next(iter(_stored(evaluate(_g(DATA), _g(shapes)), EX.virtual)))[2])
        }

    def test_a_function_body_that_reads_the_data_is_included(self) -> None:
        shapes = (
            """
            ex:readsLast a sh:ListParameterExpressionFunction ;
              sh:bodyExpression [ sparql:concat ( [ shnex:arg 0 ] [ shnex:pathValues ex:last ] ) ] ;
              sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ] .
            """
            + _shapes_for('[ ex:readsLast ( "Dr " ) ]')
        )
        assert {p for _s, p, _o in _extract(shapes, include_targets=False)} == {EX.last}


class TestFragmentIsMoreThanTheReads:
    def test_value_nodes_that_are_computed_nodes_are_followed_by_nested_shapes(self) -> None:
        # sh:values computes ex:c1, a node; a nested property shape on the path reads ex:c1's own triples
        shapes = """
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:Virt .
        ex:Virt a sh:PropertyShape ; sh:path ex:virtual ; sh:values [ shnex:pathValues ex:child ] ;
          sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        """
        result = _extract(shapes, include_targets=False)
        assert _stored(result, EX.name) == {(EX.c1, EX.name, next(iter(_g(DATA).objects(EX.c1, EX.name))))}
        assert _stored(result, EX.child)

    def test_a_shape_without_computed_values_is_unchanged(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:first ; sh:minCount 1 ] ."
        assert {p for _s, p, _o in _extract(shapes, include_targets=False)} == {EX.first}


class TestConformanceInsideAnExpression:
    """A shape check inside ``sh:values`` reads data too; a cached answer must not hide those reads from the fragment."""

    SHAPES = """
    ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:Virt, ex:Virt2 .
    ex:Virt2 a sh:PropertyShape ; sh:path ex:virtual2 ;
      sh:values [ shnex:filterShape ex:HasName ; shnex:nodes [ shnex:pathValues ex:child ] ] .
    ex:Virt a sh:PropertyShape ; sh:path ex:virtual ; sh:minCount 1 ;
      sh:values [ shnex:filterShape ex:HasName ; shnex:nodes [ shnex:pathValues ex:child ] ] .
    ex:HasName a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .
    ex:Seen a sh:NodeShape ; sh:targetNode ex:c1 ; sh:node ex:HasName .
    """

    def test_the_triples_a_shape_check_reads_are_in_the_fragment(self) -> None:
        shapes, data = _g(self.SHAPES), _g(DATA)
        fragment = extract_subgraph(data, shapes, shape=EX.S, focus_node=EX.a)
        assert (EX.c1, EX.name, next(iter(data.objects(EX.c1, EX.name)))) in set(fragment)
        assert _stored(evaluate(fragment, shapes), EX.virtual) == _stored(evaluate(data, shapes), EX.virtual)
        assert _stored(evaluate(data, shapes), EX.virtual)
