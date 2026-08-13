"""Encode a raw SPARQL parse tree (``rdflib.plugins.sparql.parser
.parseQuery``'s output, *before* ``translateQuery`` runs) as ``sast:`` RDF —
a prototype sibling to ``to_rdf.py``, one level lower (parse tree instead of
algebra).

Confirmed empirically (by directly inspecting ``parseQuery()``'s output)
that this needs almost no new machinery beyond what ``to_rdf.py`` already
established as a pattern:

- The tree is already overwhelmingly ``CompValue``-shaped, exactly like the
  algebra — same generic ``node.name`` -> ``rdf:type``, ``key: value`` ->
  predicate encoding works unchanged, just against grammar-production names
  (``TriplesBlock``, ``OptionalGraphPattern``, ``Filter``, ``PathAlternative``,
  ``ConditionalOrExpression``, ...) instead of algebra operator names.
- Property paths need *no* special-casing here at all (unlike ``to_rdf.py``'s
  dedicated ``_encode_path`` for ``rdflib.paths.Path`` objects) — at the
  parse-tree level a path is just an ordinary ``PathAlternative``/
  ``PathSequence``/``PathElt`` ``CompValue`` chain, already covered by the
  generic branch.
- The one real gap: a plain, unnamed ``pyparsing.ParseResults`` shows up on
  its own (not just as `CompValue`'s own storage) inside ``TriplesBlock
  .triples`` — a flat, *ungrouped* run of terms (e.g. ``[?p, path, :o,
  ?p, path2, ?x]`` for two semicolon-chained triples sharing a subject,
  always a multiple of 3 terms long — confirmed directly, not assumed).
  Grouping it into real ``(s, p, o)`` triples is *not* needed for a correct
  round trip: ``translateQuery`` groups it itself (that's exactly what it
  already does when called on a fresh parse straight from text), so this
  layer only needs to preserve the flat shape faithfully, encoded as an
  ordinary ``rdf:List`` — one new dispatch branch, not a new algorithm.
"""

from __future__ import annotations

from typing import Optional, Union

from pyparsing import ParseResults
from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.plugins.sparql.parserutils import CompValue

from .ast_vocab import PROLOGUE, PY_STR_DATATYPE, QUERY, SAST, VARIABLE_DATATYPE
from .to_rdf import _new_starlayergraph_graph

_LEAF_TERM_TYPES = (URIRef, BNode, Literal)
_PRIMITIVE_TYPES = (str, int, float, bool)


def query_ast_to_rdf(parse_result: ParseResults, graph: Optional[Graph] = None) -> tuple[Graph, BNode]:
    """Encode ``parseQuery(text)``'s raw output — ``[prologue, query]`` —
    as ``sast:`` RDF. Returns ``(graph, root)``, ``root`` the node for the
    query itself (``parse_result[1]``), additionally typed ``sast:Query``
    so parsed queries in a larger store can be found via ``?q a sast:Query``
    regardless of query form — same convention as ``to_rdf.query_to_rdf``.
    ``graph`` defaults to a fresh ``StarLayerGraph`` (see
    ``to_rdf._new_starlayergraph_graph``), never a plain ``rdflib.Graph``.
    """
    if graph is None:
        graph = _new_starlayergraph_graph()
    prologue, query = parse_result[0], parse_result[1]
    root = _encode(query, graph)
    graph.add((root, RDF.type, QUERY))
    graph.add((root, PROLOGUE, _encode(list(prologue), graph)))
    return graph, root


def _encode(value, graph: Graph):
    """Encode one parse-tree value; return the RDF term/node representing it."""
    if value is None:
        return None

    if isinstance(value, Variable):
        return Literal(str(value), datatype=VARIABLE_DATATYPE)

    if isinstance(value, _LEAF_TERM_TYPES):
        return value

    if isinstance(value, CompValue):
        return _encode_comp_value(value, graph)

    if isinstance(value, ParseResults):
        # A bare, unnamed parse-tree node — no grammar-production name of
        # its own, just an ordered sequence (e.g. one flat, ungrouped
        # TriplesBlock triple-run). See this module's docstring.
        return _encode_list(list(value), graph)

    if isinstance(value, (list, tuple)):
        return _encode_list(list(value), graph)

    if type(value) is str:
        # A bare Python str living in the parse tree (operators, prefix
        # labels, ...) — same reserved-datatype trick as to_rdf.py's own
        # bare-str handling, see ast_vocab.PY_STR_DATATYPE.
        return Literal(value, datatype=PY_STR_DATATYPE)

    if isinstance(value, _PRIMITIVE_TYPES):
        return Literal(value)

    raise NotImplementedError(
        f"starsparql.to_ast_rdf: no RDF encoding yet for parse-tree value "
        f"of type {type(value).__name__!r}: {value!r}"
    )


def _encode_comp_value(node: CompValue, graph: Graph) -> BNode:
    subj = BNode()
    graph.add((subj, RDF.type, SAST[node.name]))
    for key, value in node.items():
        encoded = _encode(value, graph)
        if encoded is None:
            continue
        graph.add((subj, SAST[key], encoded))
    return subj


def _encode_list(items: list, graph: Graph) -> Union[BNode, URIRef]:
    return _build_rdf_list([_encode(item, graph) for item in items], graph)


def _build_rdf_list(nodes: list, graph: Graph) -> Union[BNode, URIRef]:
    if not nodes:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, nodes)
    return list_node
