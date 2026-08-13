"""
starlayergraph.parsers.trix12

Parse TriX 1.2 XML into triples, preserving or merging named-graph structure.

TriX is an XML-based named-graph format. Each <graph> block contains <triple>
elements whose three children are term nodes. RDF 1.2 triple terms are
represented by nesting another <triple> element in a term position (subject
or object) - the same element used for an asserted statement, disambiguated
only by structural position, not a distinct tag name. This matches Apache
Jena's real TriX writer/reader (confirmed empirically 2026-07-17 against a
live Fuseki 5.5.0: it emits a lowercase <trix> root element and nests
<triple> for a triple term - the only production TriX implementation found
to actually support RDF 1.2 triple terms, since Oxigraph doesn't implement
TriX at all). StarLayer originally invented its own <TriX>/<tripleTerm>
spelling before this was checked against a real implementation; both the
old root-tag capitalization and <tripleTerm> are still accepted here for
backward compatibility with anything already serialized by this parser's
own prior convention, but are no longer emitted (see trix12.py serializer).

Entry points:
    parse_trix12(text)        -> list of (s, p, o)            (merges all graphs)
    parse_trix12_named(text)  -> list of (graph_id, triples)  (preserves structure)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from rdflib import URIRef, BNode, Literal

from starlayergraph.model.triple import TripleTerm

TRIX_NS  = 'http://www.w3.org/2004/03/trix/trix-1/'
_XML_NS  = 'http://www.w3.org/XML/1998/namespace'

_TAG_URI         = f'{{{TRIX_NS}}}uri'
_TAG_ID          = f'{{{TRIX_NS}}}id'
_TAG_PLAIN       = f'{{{TRIX_NS}}}plainLiteral'
_TAG_TYPED       = f'{{{TRIX_NS}}}typedLiteral'
_TAG_TRIPLE      = f'{{{TRIX_NS}}}triple'
_TAG_GRAPH       = f'{{{TRIX_NS}}}graph'
# StarLayer's original (pre-Jena-comparison) spelling for a triple term -
# still accepted on read for backward compatibility, never written anymore.
_TAG_TRIPLE_TERM_LEGACY = f'{{{TRIX_NS}}}tripleTerm'


def _parse_term(elem: ET.Element):
    """Convert a TriX term element to an rdflib node or TripleTerm."""
    tag = elem.tag

    if tag == _TAG_URI:
        return URIRef((elem.text or '').strip())

    if tag == _TAG_ID:
        return BNode((elem.text or '').strip())

    if tag == _TAG_PLAIN:
        lang = elem.get(f'{{{_XML_NS}}}lang')
        return Literal(elem.text or '', lang=lang if lang else None)

    if tag == _TAG_TYPED:
        datatype = elem.get('datatype', '')
        return Literal(elem.text or '', datatype=URIRef(datatype))

    if tag in (_TAG_TRIPLE, _TAG_TRIPLE_TERM_LEGACY):
        # A <triple> nested in a term position (subject/object) is a triple
        # term (RDF 1.2) - the Jena convention. <tripleTerm> is the legacy
        # starlayergraph-only spelling, accepted for backward compatibility only.
        children = list(elem)
        if len(children) != 3:
            raise ValueError(
                f'<{elem.tag.split("}")[-1]}> must have exactly 3 children, got {len(children)}'
            )
        return TripleTerm(
            _parse_term(children[0]),
            _parse_term(children[1]),
            _parse_term(children[2]),
        )

    raise ValueError(f'Unknown TriX term element: {tag!r}')


def _parse_graph(graph_elem: ET.Element) -> tuple[URIRef | None, list[tuple]]:
    """Parse a <graph> element; return (graph_id, triples).

    The graph is named when its first child is a <uri> element.
    """
    children = list(graph_elem)
    if not children:
        return None, []

    graph_id: URIRef | None = None
    start = 0
    if children[0].tag == _TAG_URI:
        graph_id = URIRef((children[0].text or '').strip())
        start = 1

    triples: list[tuple] = []
    for child in children[start:]:
        if child.tag != _TAG_TRIPLE:
            continue
        terms = list(child)
        if len(terms) != 3:
            raise ValueError(f'<triple> must have exactly 3 children, got {len(terms)}')
        s = _parse_term(terms[0])
        p = _parse_term(terms[1])
        o = _parse_term(terms[2])
        triples.append((s, p, o))

    return graph_id, triples


def _iter_graphs(text: str):
    """Yield (graph_id, triples) pairs from a TriX document."""
    root = ET.fromstring(text)
    # Lowercase <trix> matches Apache Jena's real implementation (confirmed
    # live 2026-07-17); <TriX> is starlayergraph's own legacy spelling, accepted
    # for backward compatibility only - see module docstring.
    accepted = (f'{{{TRIX_NS}}}trix', 'trix', f'{{{TRIX_NS}}}TriX', 'TriX')
    if root.tag not in accepted:
        raise ValueError(f'Expected <trix> root element, got {root.tag!r}')
    for child in root:
        if child.tag == _TAG_GRAPH:
            yield _parse_graph(child)


def parse_trix12(text: str) -> list[tuple]:
    """Parse TriX 1.2 text; return list of (s, p, o) triples.

    All named graphs are merged. Subjects and objects may be TripleTerm
    instances for RDF 1.2 triple terms.
    """
    triples: list[tuple] = []
    for _gid, graph_triples in _iter_graphs(text):
        triples.extend(graph_triples)
    return triples


def parse_trix12_named(text: str) -> list[tuple[URIRef | None, list[tuple]]]:
    """Parse TriX 1.2 text; return list of (graph_id, triples).

    graph_id is None for anonymous/default graphs, a URIRef for named graphs.
    Subjects and objects may be TripleTerm instances.
    """
    return [(gid, triples) for gid, triples in _iter_graphs(text) if triples]
