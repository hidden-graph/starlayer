"""
starlayergraph.serializers.trix12

Serialize a StarLayerGraph or StarLayerDataset context to TriX 1.2 XML.

TriX is an XML-based named-graph format (http://www.w3.org/2004/03/trix/).
Each graph is a <graph> element containing <triple> elements. RDF 1.2 triple
terms are represented by nesting another <triple> element in a term position
(subject or object) - the same tag used for an asserted statement, since
TriX disambiguates by structural position, not a distinct tag name. This
matches Apache Jena's real TriX writer (confirmed empirically 2026-07-17
against a live Fuseki 5.5.0), including its lowercase <trix> root element -
the only production TriX implementation found to support RDF 1.2 triple
terms at all, since Oxigraph doesn't implement TriX. See the parser module
(starlayergraph.parsers.trix12) for the corresponding read side, which still
accepts starlayergraph's original <TriX>/<tripleTerm> spelling for backward
compatibility even though it's no longer emitted here.

Entry point:  serialize_trix12(g) -> str
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from rdflib import URIRef, BNode, Literal

from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import encode_dirlang_datatype

TRIX_NS = 'http://www.w3.org/2004/03/trix/trix-1/'
_XML_NS = 'http://www.w3.org/XML/1998/namespace'

_T = f'{{{TRIX_NS}}}'    # shorthand: '{ns}' prefix for element tags


def _term_elem(node, parent: ET.Element) -> ET.Element:
    """Append a TriX term element for *node* to *parent* and return it."""
    if isinstance(node, TripleTerm):
        # Jena convention: reuse the ordinary <triple> tag, nested in a term
        # position - not a distinct <tripleTerm> tag (see module docstring).
        tt = ET.SubElement(parent, f'{_T}triple')
        _term_elem(node.subject,   tt)
        _term_elem(node.predicate, tt)
        _term_elem(node.object,    tt)
        return tt

    if isinstance(node, URIRef):
        el = ET.SubElement(parent, f'{_T}uri')
        el.text = str(node)
        return el

    if isinstance(node, BNode):
        el = ET.SubElement(parent, f'{_T}id')
        el.text = str(node)
        return el

    if isinstance(node, DirLangString):
        # Same internal dirlang: datatype-URI encoding as every other format;
        # <typedLiteral datatype=...> round-trips it unchanged since the TriX
        # parser passes the datatype straight to Literal(text, datatype=...)
        # with no langtag validation involved.
        el = ET.SubElement(parent, f'{_T}typedLiteral')
        el.set('datatype', str(encode_dirlang_datatype(node.language, node.direction)))
        el.text = node.value
        return el

    if isinstance(node, Literal):
        if node.language:
            el = ET.SubElement(parent, f'{_T}plainLiteral')
            el.set(f'{{{_XML_NS}}}lang', node.language)
            el.text = str(node)
            return el
        dt = str(node.datatype) if node.datatype else 'http://www.w3.org/2001/XMLSchema#string'
        el = ET.SubElement(parent, f'{_T}typedLiteral')
        el.set('datatype', dt)
        el.text = str(node)
        return el

    raise TypeError(f'Unexpected node type: {type(node).__name__}: {node!r}')


def _sort_triple(t: tuple) -> tuple:
    return (str(t[0]), str(t[1]), str(t[2]))


def _append_graph(g, root: ET.Element) -> None:
    """Append a <graph> element for *g* to *root*."""
    graph_elem = ET.SubElement(root, f'{_T}graph')
    if isinstance(g.identifier, URIRef):
        uri_elem = ET.SubElement(graph_elem, f'{_T}uri')
        uri_elem.text = str(g.identifier)

    for s, p, o in sorted(g.triples((None, None, None)), key=_sort_triple):
        triple_elem = ET.SubElement(graph_elem, f'{_T}triple')
        _term_elem(s, triple_elem)
        _term_elem(p, triple_elem)
        _term_elem(o, triple_elem)


def serialize_trix12(g) -> str:
    """Serialize a StarLayerGraph to TriX 1.2 XML text.

    Named graph identifier → <uri> as first child of <graph>.
    BNode identifier        → anonymous <graph> (default/unnamed graph).
    Triple terms emitted as a nested <triple> (Jena convention), not a
    distinct <tripleTerm> tag.
    """
    ET.register_namespace('', TRIX_NS)
    ET.register_namespace('xml', _XML_NS)

    root = ET.Element(f'{_T}trix')
    _append_graph(g, root)

    ET.indent(root, space='  ')
    body = ET.tostring(root, encoding='unicode')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'


def serialize_trix12_dataset(ds) -> str:
    """Serialize a StarLayerDataset to TriX 1.2 XML text.

    Each non-empty named graph becomes a separate <graph> block.
    """
    ET.register_namespace('', TRIX_NS)
    ET.register_namespace('xml', _XML_NS)

    root = ET.Element(f'{_T}trix')
    for sg in ds.contexts():
        if len(sg) == 0:
            continue
        _append_graph(sg, root)

    ET.indent(root, space='  ')
    body = ET.tostring(root, encoding='unicode')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'
