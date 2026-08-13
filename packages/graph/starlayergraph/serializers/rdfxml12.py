"""
starlayergraph.serializers.rdfxml12

Serialize a StarLayerGraph to RDF/XML 1.2.

Triple terms in object position are emitted using the real RDF 1.2 XML Syntax
mechanism: ``rdf:parseType="Triple"`` on the property element, wrapping a
single ``<rdf:Description>`` that holds exactly one property (the triple's
predicate/object) - see RDF 1.2 XML Syntax sec 2.19. A nested triple term
(the inner property's object is itself a triple term) recurses the same way.

There is no separate representation for reification: ``rdf:reifies`` is just
an ordinary predicate whose object is a triple term, so it's emitted exactly
like any other triple-term-valued property - this is the "formal" pattern
already used as the canonical form across every other format in this codebase
(see docs/sparql12_design.md). The spec's ``rdf:annotation``/
``rdf:annotationNodeID`` attribute shorthand is a convenience the *parser*
also accepts (for reading documents from other tools) but this serializer
never emits it, keeping one predictable output shape.

A triple term can only ever be an *object* in RDF 1.2 (never a subject), so
unlike earlier versions of this module there is no top-level "triple term as
subject" case to handle.

Predicate IRIs must be QName-able (i.e. splittable at a '#' or '/' boundary
with a non-digit local name).  IRIs that cannot be expressed as QNames raise
ValueError.

Entry point:  serialize_rdfxml12(graph) -> str
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from rdflib import URIRef, BNode, Literal

from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import encode_dirlang_datatype

_RDF_NS  = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_XML_NS  = 'http://www.w3.org/XML/1998/namespace'
_XSD_STR = 'http://www.w3.org/2001/XMLSchema#string'

_R = f'{{{_RDF_NS}}}'


# ---------------------------------------------------------------------------
# IRI → Clark-notation tag
# ---------------------------------------------------------------------------

def _split_iri(iri: str) -> tuple[str, str]:
    """Split an IRI into (namespace_uri, local_name).

    Tries '#' first, then '/'.  Raises ValueError if the local name cannot
    form a valid XML name start character.
    """
    for sep in ('#', '/'):
        if sep in iri:
            idx = iri.rfind(sep)
            ns, local = iri[:idx + 1], iri[idx + 1:]
            if local and (local[0].isalpha() or local[0] == '_'):
                return ns, local
    raise ValueError(f'Cannot express as a QName: {iri!r}')


def _clark(iri: str) -> str:
    """Return Clark-notation tag {ns}local for *iri*."""
    ns, local = _split_iri(iri)
    return f'{{{ns}}}{local}'


# ---------------------------------------------------------------------------
# Namespace registration
# ---------------------------------------------------------------------------

def _register_ns(sg) -> None:
    """Register graph namespaces with ElementTree so prefixes are stable."""
    ET.register_namespace('rdf', _RDF_NS)
    ET.register_namespace('xml', _XML_NS)
    for prefix, ns_uri in sg.namespaces():
        if prefix and str(ns_uri) not in (_RDF_NS, _XML_NS):
            ET.register_namespace(prefix, str(ns_uri))


# ---------------------------------------------------------------------------
# Object serialization helpers
# ---------------------------------------------------------------------------

def _set_object(prop: ET.Element, obj) -> None:
    """Configure *prop* for the given object node (attribute or nested element)."""
    if isinstance(obj, URIRef):
        prop.set(f'{_R}resource', str(obj))

    elif isinstance(obj, BNode):
        prop.set(f'{_R}nodeID', str(obj))

    elif isinstance(obj, DirLangString):
        # Same internal dirlang: datatype-URI encoding as every other format;
        # rdflib's real RDF/XML parser reads rdf:datatype back into
        # Literal(text, datatype=...) unchanged, no langtag validation
        # involved (that only fires for the xml:lang attribute).
        prop.text = obj.value
        prop.set(f'{_R}datatype', str(encode_dirlang_datatype(obj.language, obj.direction)))

    elif isinstance(obj, Literal):
        prop.text = str(obj)
        if obj.language:
            prop.set(f'{{{_XML_NS}}}lang', obj.language)
        elif obj.datatype and str(obj.datatype) != _XSD_STR:
            prop.set(f'{_R}datatype', str(obj.datatype))

    elif isinstance(obj, TripleTerm):
        # rdf:parseType="Triple" wrapping a single <rdf:Description> that
        # holds exactly one property - the real RDF 1.2 XML Syntax mechanism
        # (sec 2.19), not an invented element. Recurses for a nested triple
        # term (the inner property's own object is itself a TripleTerm).
        prop.set(f'{_R}parseType', 'Triple')
        desc = ET.SubElement(prop, f'{_R}Description')
        if isinstance(obj.subject, URIRef):
            desc.set(f'{_R}about', str(obj.subject))
        else:  # BNode - triple terms are only ever objects, so this can't recurse
            desc.set(f'{_R}nodeID', str(obj.subject))
        inner_prop = ET.SubElement(desc, _clark(str(obj.predicate)))
        _set_object(inner_prop, obj.object)

    else:
        raise TypeError(f'Unexpected object type: {type(obj).__name__}: {obj!r}')


def _sort_key(node) -> str:
    return str(node)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def serialize_rdfxml12(graph) -> str:
    """Serialize a StarLayerGraph to RDF/XML 1.2 text.

    Triple terms in object position → ``rdf:parseType="Triple"`` wrapping a
    single ``<rdf:Description>`` (RDF 1.2 XML Syntax sec 2.19). Reification is
    the ordinary ``rdf:reifies`` predicate with a triple-term-valued object -
    the same "formal pattern" used as the canonical form everywhere else in
    this codebase, not the ``rdf:annotation``/``rdf:annotationNodeID``
    shorthand (which the parser accepts for reading, but this serializer
    never emits).
    """
    from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

    sg = graph if isinstance(graph, StarLayerGraph) else StarLayerGraph.from_rdflib(graph)
    _register_ns(sg)

    by_subj: dict = defaultdict(list)
    for s, p, o in sg.triples((None, None, None)):
        by_subj[s].append((p, o))

    root = ET.Element(f'{_R}RDF')

    for subj in sorted(by_subj.keys(), key=_sort_key):
        desc = ET.SubElement(root, f'{_R}Description')
        if isinstance(subj, URIRef):
            desc.set(f'{_R}about', str(subj))
        else:  # BNode
            desc.set(f'{_R}nodeID', str(subj))

        for pred, obj in sorted(by_subj[subj], key=lambda x: (str(x[0]), str(x[1]))):
            prop_tag = _clark(str(pred))
            prop = ET.SubElement(desc, prop_tag)
            _set_object(prop, obj)

    ET.indent(root, space='  ')
    body = ET.tostring(root, encoding='unicode')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'
