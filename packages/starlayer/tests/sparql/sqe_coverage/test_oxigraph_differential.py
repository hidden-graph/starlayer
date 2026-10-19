"""Differential testing against Oxigraph, an independent SPARQL 1.2 engine (pyoxigraph, in-process).

Plain rdflib is a reference for SPARQL 1.1 only; Oxigraph also implements RDF 1.2 (triple terms, reifiers,
annotations, base-direction strings) and the SPARQL 1.2 functions, so it can referee those too.

* ``test_generated_queries_agree_with_oxigraph``: the generated 1.1 queries from the sqe property tests,
  run through StarLayer's regular query path and through Oxigraph.
* ``test_sparql12_queries_agree_with_oxigraph``: generated queries that use the 1.2 syntax and functions.
* ``test_sqe_text_agrees_with_oxigraph``: the text sqe renders for a generated query, run on StarLayer,
  against the ORIGINAL query on Oxigraph - so sqe is checked against an engine that is not StarLayer.

Results are compared as sets of canonical terms (blank-node labels masked, since two engines never agree on
them). Opt-in (``pytest --sqe-coverage``); example count from ``STARLAYER_SQE_FUZZ_EXAMPLES``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

pyoxigraph = pytest.importorskip("pyoxigraph")

from rdflib import BNode, Literal, URIRef  # noqa: E402
from starlayer.graph.model.encoding import decode_dirlang_datatype  # noqa: E402
from starlayer.graph.model.triple import TripleTerm  # noqa: E402
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text  # noqa: E402
from tests.sparql.sqe_coverage.test_sqe_features import (  # noqa: E402
    RDF12_TURTLE,
    P,
    build_dataset,
    synthetic_triples,
)
from tests.sparql.sqe_coverage.test_sqe_property_based import (  # noqa: E402
    _QUERIES,
    _SETTINGS,
)

pytestmark = pytest.mark.sqe_coverage

XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"


# --------------------------------------------------------------------------
# the same data in both engines

def _oxigraph_store():
    triples, tags = synthetic_triples()

    def line(triple):
        return " ".join(term.n3() for term in triple) + " ."

    default = "\n".join(line(t) for t in triples + tags)
    g1 = "\n".join(line(t) for t in triples)
    g2 = "\n".join(line(t) for t in tags)
    trig = f"{default}\n<http://x/g1> {{ {g1} }}\n<http://x/g2> {{ {g2} }}\n"
    store = pyoxigraph.Store()
    store.load(trig.encode(), format=pyoxigraph.RdfFormat.TRIG)
    store.load(RDF12_TURTLE.encode(), format=pyoxigraph.RdfFormat.TURTLE)
    return store


_STARLAYER = build_dataset()
_OXIGRAPH = _oxigraph_store()


# --------------------------------------------------------------------------
# canonical terms

def _canonical_number(lexical, datatype):
    """Numbers compared by value: engines write 0, 0.0 and 0.00 for the same decimal."""
    from decimal import Decimal, InvalidOperation

    suffix = datatype.rsplit("#", 1)[-1]
    try:
        if suffix in ("decimal", "integer"):
            number = Decimal(lexical)
            return str(number.quantize(Decimal(1))) if number == number.to_integral() else str(number.normalize())
        if suffix in ("double", "float"):
            return repr(float(lexical))
    except (InvalidOperation, ValueError):
        pass
    return lexical


def _lit(lexical, language=None, direction=None, datatype=None):
    if datatype:
        lexical = _canonical_number(lexical, datatype)
    if language:
        return f'"{lexical}"@{language}' + (f"--{direction}" if direction else "")
    if datatype and datatype != XSD_STRING:
        return f'"{lexical}"^^<{datatype}>'
    return f'"{lexical}"'


def _starlayer_term(term):
    if term is None:
        return None
    if isinstance(term, TripleTerm):
        return f"<<( {_starlayer_term(term.subject)} {_starlayer_term(term.predicate)} {_starlayer_term(term.object)} )>>"
    if isinstance(term, URIRef):
        return f"<{term}>"
    if isinstance(term, BNode):
        return "_:b"
    if isinstance(term, Literal):
        decoded = decode_dirlang_datatype(term.datatype) if term.datatype else None
        if decoded:
            return _lit(str(term), language=decoded[0], direction=decoded[1])
        return _lit(str(term), language=term.language, datatype=str(term.datatype) if term.datatype else None)
    return str(term)


def _oxigraph_term(term):
    if term is None:
        return None
    if isinstance(term, pyoxigraph.Triple):
        return f"<<( {_oxigraph_term(term.subject)} {_oxigraph_term(term.predicate)} {_oxigraph_term(term.object)} )>>"
    if isinstance(term, pyoxigraph.NamedNode):
        return f"<{term.value}>"
    if isinstance(term, pyoxigraph.BlankNode):
        return "_:b"
    return _lit(
        term.value,
        language=term.language,
        direction=getattr(term, "direction", None),
        datatype=term.datatype.value if term.datatype else None,
    )


def _starlayer_outcome(query):
    try:
        result = _STARLAYER.query(query)
        if result.type == "ASK":
            return ("ask", result.askAnswer)
        if result.type == "CONSTRUCT":
            return ("graph", sorted(tuple(_starlayer_term(t) for t in triple) for triple in result.graph))
        rows = [
            tuple(sorted((str(k), _starlayer_term(v)) for k, v in row.asdict().items() if v is not None))
            for row in result
        ]
        return ("rows", sorted(rows, key=repr))
    except Exception:  # noqa: BLE001 - an engine error is an outcome to compare
        return ("error",)


def _oxigraph_outcome(query):
    try:
        result = _OXIGRAPH.query(query)
        if isinstance(result, pyoxigraph.QueryBoolean):
            return ("ask", bool(result))
        if isinstance(result, pyoxigraph.QueryTriples):
            return ("graph", sorted(tuple(_oxigraph_term(t) for t in (q.subject, q.predicate, q.object)) for q in result))
        variables = [v.value for v in result.variables]
        rows = []
        for solution in result:
            row = tuple(
                sorted((name, _oxigraph_term(solution[name])) for name in variables if solution[name] is not None)
            )
            rows.append(row)
        return ("rows", sorted(rows, key=repr))
    except Exception:  # noqa: BLE001
        return ("error",)


def _order_sensitive(query: str) -> bool:
    return "LIMIT" in query or "OFFSET" in query


# --------------------------------------------------------------------------
# properties

@_SETTINGS
@given(query=_QUERIES)
def test_generated_queries_agree_with_oxigraph(query):
    assert _starlayer_outcome(query) == _oxigraph_outcome(query)


@_SETTINGS
@given(query=_QUERIES)
def test_sqe_text_agrees_with_oxigraph(query):
    tree, root = sqe_parse_to_tree(query)
    assert _starlayer_outcome(sqe_tree_to_text(tree, root)) == _oxigraph_outcome(query)


# --- SPARQL 1.2 ------------------------------------------------------------

_TITLE_FUNCTIONS = [
    "STR(?t)",
    "LANG(?t)",
    "LANGDIR(?t)",
    "hasLANG(?t)",
    "hasLANGDIR(?t)",
    "DATATYPE(?t)",
    "STRLEN(?t)",
    "UCASE(?t)",
    "LCASE(?t)",
    "SUBSTR(?t, 2)",
    "CONTAINS(?t, 'l')",
    "STRSTARTS(?t, 'h')",
    "STRENDS(?t, 'm')",
    "STRBEFORE(?t, 'l')",
    "STRAFTER(?t, 'l')",
    "REPLACE(?t, 'l', 'L')",
    "CONCAT(?t, '!')",
    "isLiteral(?t)",
    "STRLANGDIR(STR(?t), 'en', 'rtl')",
    "STRLANGDIR('x', 'fr', 'ltr')",
]
_TRIPLE_FUNCTIONS = ["isTRIPLE(?t)", "SUBJECT(?t)", "PREDICATE(?t)", "OBJECT(?t)"]


@st.composite
def _sparql12_query(draw):
    kind = draw(
        st.sampled_from(
            ["title", "title-filter", "triple-term", "triple-fn", "annotation", "reifier", "reifies", "construct", "values", "ask"]
        )
    )
    if kind == "title":
        expressions = draw(st.lists(st.sampled_from(_TITLE_FUNCTIONS), min_size=1, max_size=3, unique=True))
        projection = " ".join(f"({e} AS ?e{i})" for i, e in enumerate(expressions))
        return f"{P}SELECT ?s {projection} WHERE {{ ?s ex:title ?t }}"
    if kind == "title-filter":
        condition = draw(st.sampled_from(_TITLE_FUNCTIONS[:6] + ["STRLEN(?t) > 4", "isLiteral(?t)", "LANGDIR(?t) = 'ltr'"]))
        return f"{P}SELECT ?s ?t WHERE {{ ?s ex:title ?t FILTER({condition}) }}"
    if kind == "triple-term":
        subject = draw(st.sampled_from(["?x", "ex:s1", "ex:s3"]))
        obj = draw(st.sampled_from(["?n", "1", "3"]))
        outer = draw(st.sampled_from(["?s", "ex:s0", "ex:s2"]))
        return f"{P}SELECT * WHERE {{ {outer} ex:believes <<( {subject} ex:num {obj} )>> }}"
    if kind == "triple-fn":
        function = draw(st.sampled_from(_TRIPLE_FUNCTIONS))
        return f"{P}SELECT ?b ?t (({function}) AS ?r) WHERE {{ ?b ex:believes ?t }}"
    if kind == "annotation":
        shape = draw(st.sampled_from(["ex:s1 ex:num 1 {| ex:certainty ?c |}", "?x ex:num ?n {| ex:certainty ?c |}"]))
        return f"{P}SELECT * WHERE {{ {shape} }}"
    if kind == "reifier":
        return f"{P}SELECT ?x ?n WHERE {{ ?x ex:num ?n ~ ?r . ?r ex:certainty ?c }}"
    if kind == "reifies":
        return f"{P}SELECT ?r ?c WHERE {{ ?r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ?x ex:num ?n )>> . OPTIONAL {{ ?r ex:certainty ?c }} }}"
    if kind == "construct":
        return f"{P}CONSTRUCT {{ ?s ex:said <<( ?x ex:num ?n )>> }} WHERE {{ ?s ex:believes <<( ?x ex:num ?n )>> }}"
    if kind == "values":
        return f"{P}SELECT ?t WHERE {{ VALUES ?t {{ <<( ex:s1 ex:num 1 )>> <<( ex:s9 ex:num 9 )>> }} ?s ex:believes ?t }}"
    return f"{P}ASK {{ ?b ex:believes <<( ex:s1 ex:num 1 )>> }}"


@_SETTINGS
@given(query=_sparql12_query())
def test_sparql12_queries_agree_with_oxigraph(query):
    assert _starlayer_outcome(query) == _oxigraph_outcome(query)


@_SETTINGS
@given(query=_sparql12_query())
def test_sqe_text_of_sparql12_agrees_with_oxigraph(query):
    tree, root = sqe_parse_to_tree(query)
    assert _starlayer_outcome(sqe_tree_to_text(tree, root)) == _oxigraph_outcome(query)
