"""
starlayergraph.parsers.rdfxml12

Parse RDF/XML 1.2 text into (s, p, o) triples with TripleTerm objects.

rdflib's own 'xml' parser is RDF 1.1 only: it doesn't recognize
rdf:parseType="Triple" (falls back to treating it as XMLLiteral) or the
rdf:annotation/rdf:annotationNodeID reifier-shorthand attributes (mishandled
as ordinary, incorrectly-shaped properties - confirmed empirically, not
merely assumed). So this module preprocesses the raw XML tree with
ElementTree first: every rdf:parseType="Triple" property element and every
rdf:annotation/rdf:annotationNodeID attribute is rewritten into the same
bnode-based rdf:TripleTerm intermediate encoding StarLayerTurtleParser's
_skolemize_encoding() family already uses, which rdflib's real 'xml' parser
*does* understand correctly (they're just ordinary rdf:type/rdf:subject/
rdf:predicate/rdf:object triples at that point). The rest of the document -
everything that isn't one of those two RDF 1.2 additions - is left completely
untouched and parsed by rdflib exactly as before.

Scope: only node elements directly under <rdf:RDF> and their direct
property-element children are inspected for rdf:parseType="Triple" or
rdf:annotation/rdf:annotationNodeID (this matches exactly what
serialize_rdfxml12() emits). A property carrying rdf:annotation/
rdf:annotationNodeID must resolve to rdf:resource, an rdf:nodeID, a single
nested node element, or plain literal content; rdf:parseType="Resource"/
"Collection" combined with either attribute is out of scope and raises
NotImplementedError rather than being silently mishandled. A single
xml:base (if present on the document element) is honored for relative IRIs
in the parts this module resolves itself; per-element xml:base overrides are
not.

RDF 1.2's third addition, the rdf:version announcement attribute (RDF 1.2
XML Syntax - confirmed via spec fetch: "a version announcement on an
in-scope node element with an rdf:version attribute"), is stripped wherever
found on a node or property element this module resolves, and recorded -
not just unhandled but actively dangerous to leave alone: confirmed
empirically that rdflib's real 'xml' parser treats any attribute it doesn't
specifically recognize as RDF/XML's ordinary "property attribute" shorthand,
so an untouched rdf:version asserts a bogus extra triple
(subject rdf:version "value") into the graph. Live Oxigraph 0.5.9 output
(2026-07-17) genuinely emits this attribute (on the property element
wrapping rdf:parseType="Triple", not just a node element), which is how this
was found - not a hypothetical. See extract_version_directive() for the
standalone scan used to surface the value for StarLayerGraph.parse()'s
RDF12ConformanceWarning check (starlayergraph.model.conformance).

Entry point:
    parse_rdfxml12(text) -> list of (s, p, o)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import rdflib
from rdflib import URIRef, BNode, Literal
from rdflib.namespace import RDF

from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.encoding import encode_dirlang_datatype

_RDF_NS          = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_XML_NS          = 'http://www.w3.org/XML/1998/namespace'
_ITS_NS          = 'http://www.w3.org/2005/11/its'
_RDF_TRIPLE_TERM = URIRef(_RDF_NS + 'TripleTerm')
_ENCODING_PREDS  = frozenset({RDF.type, RDF.subject, RDF.predicate, RDF.object})

_R   = f'{{{_RDF_NS}}}'
_X   = f'{{{_XML_NS}}}'
_ITS = f'{{{_ITS_NS}}}'

_RDF_VERSION_ATTR = _R + 'version'


def extract_version_directive(text: str) -> str | None:
    """Return the first rdf:version attribute value found anywhere in the
    document, or None.

    RDF 1.2 XML Syntax's version-announcement mechanism is structurally
    different from every other format's - an XML attribute on an in-scope
    node element, not a prologue-line directive - so it needs its own
    detection rather than reusing syntax.extract_fields()'s text-directive
    pattern. A separate, lightweight scan (rather than reusing
    _Preprocessor's own version-stripping pass below) keeps this a simple
    standalone function, matching ntriples12.py's/trig12.py's
    extract_version_directive() so StarLayerGraph.parse() can call it
    alongside parse_rdfxml12() without changing that function's existing
    list[tuple] return contract.
    """
    root = ET.fromstring(text)
    for elem in root.iter():
        version = elem.get(_RDF_VERSION_ATTR)
        if version is not None:
            return version
    return None


# ---------------------------------------------------------------------------
# Bnode-encoding → TripleTerm (shared with the pre-parseType="Triple" era;
# unchanged, since the intermediate encoding it expects hasn't changed)
# ---------------------------------------------------------------------------

def _convert_bnodes(raw: rdflib.Graph) -> list[tuple]:
    """Convert the bnode-based rdf:TripleTerm encoding in *raw* to TripleTerm objects.

    Returns a list of (s, p, o) with TripleTerm objects where the bnode
    encoding triples used to be.
    """
    # Identify all bnodes that represent triple terms
    tt_bnodes: dict[BNode, tuple] = {}
    for bnode in raw.subjects(RDF.type, _RDF_TRIPLE_TERM):
        if not isinstance(bnode, BNode):
            continue
        s_list = list(raw.objects(bnode, RDF.subject))
        p_list = list(raw.objects(bnode, RDF.predicate))
        o_list = list(raw.objects(bnode, RDF.object))
        if len(s_list) == 1 and len(p_list) == 1 and len(o_list) == 1:
            tt_bnodes[bnode] = (s_list[0], p_list[0], o_list[0])

    # Recursively build TripleTerm objects (handles nested triple terms)
    tt_cache: dict[BNode, TripleTerm] = {}

    def _build(bnode: BNode) -> TripleTerm:
        if bnode in tt_cache:
            return tt_cache[bnode]
        s_n, p_n, o_n = tt_bnodes[bnode]
        s = _build(s_n) if isinstance(s_n, BNode) and s_n in tt_bnodes else s_n
        o = _build(o_n) if isinstance(o_n, BNode) and o_n in tt_bnodes else o_n
        tt = TripleTerm(s, p_n, o)
        tt_cache[bnode] = tt
        return tt

    for bn in tt_bnodes:
        _build(bn)

    # Collect non-encoding triples, substituting TripleTerm objects for bnodes
    result: list[tuple] = []
    for s, p, o in raw:
        # Skip encoding triples that belong to a tt bnode
        if isinstance(s, BNode) and s in tt_bnodes and p in _ENCODING_PREDS:
            continue
        s_out = tt_cache.get(s, s) if isinstance(s, BNode) else s
        o_out = tt_cache.get(o, o) if isinstance(o, BNode) else o
        result.append((s_out, p, o_out))

    return result


# ---------------------------------------------------------------------------
# XML-tree preprocessing: rdf:parseType="Triple" and rdf:annotation(NodeID)
# ---------------------------------------------------------------------------

def _local_to_uriref(tag: str) -> URIRef:
    """Convert an ElementTree Clark-notation tag '{ns}local' to a URIRef."""
    if tag.startswith('{'):
        ns, local = tag[1:].split('}', 1)
        return URIRef(ns + local)
    return URIRef(tag)


class _Preprocessor:
    """Rewrites rdf:parseType="Triple" and rdf:annotation/rdf:annotationNodeID
    in place on an ElementTree, into the bnode-based rdf:TripleTerm
    intermediate _convert_bnodes() (and rdflib's own 'xml' parser) understand.
    """

    def __init__(self):
        self._counter = 0
        self._extra_elems: list[ET.Element] = []

    def _fresh_id(self) -> str:
        self._counter += 1
        return f'rx12_{self._counter}'

    def _strip_version_attr(self, elem: ET.Element) -> None:
        """Remove rdf:version if present on *elem* - it must never reach
        rdflib's real 'xml' parser, which would otherwise misinterpret it as
        an ordinary property attribute and assert a bogus extra triple (see
        module docstring). Recording the value itself is extract_version_directive()'s
        job via its own separate scan, not this method's - this only
        prevents the corruption.
        """
        if elem.get(_RDF_VERSION_ATTR) is not None:
            del elem.attrib[_RDF_VERSION_ATTR]

    def _resolve_node_element_subject(self, elem: ET.Element, base: str | None):
        self._strip_version_attr(elem)
        about = elem.get(_R + 'about')
        if about is not None:
            return URIRef(urljoin(base, about) if base else about)
        node_id = elem.get(_R + 'nodeID')
        if node_id is not None:
            return BNode(node_id)
        return BNode()

    def _resolve_object_from_property(self, elem: ET.Element, base: str | None):
        """Resolve the RDF term a property element denotes as its object,
        ignoring rdf:annotation/rdf:annotationNodeID/rdf:parseType (the caller
        handles those). Supports rdf:resource, rdf:nodeID, a single nested
        node element, or plain literal text content (with xml:lang/its:dir/
        rdf:datatype). Anything else raises NotImplementedError.
        """
        resource = elem.get(_R + 'resource')
        if resource is not None:
            return URIRef(urljoin(base, resource) if base else resource)
        node_id = elem.get(_R + 'nodeID')
        if node_id is not None:
            return BNode(node_id)
        children = list(elem)
        if len(children) == 1 and not (elem.text or '').strip():
            return self._resolve_node_element_subject(children[0], base)
        if not children:
            text = elem.text or ''
            lang = elem.get(_X + 'lang')
            direction = elem.get(_ITS + 'dir')
            datatype = elem.get(_R + 'datatype')
            if lang and direction:
                return Literal(text, datatype=encode_dirlang_datatype(lang.lower(), direction.lower()))
            if lang:
                return Literal(text, lang=lang)
            if datatype:
                return Literal(text, datatype=URIRef(datatype))
            return Literal(text)
        raise NotImplementedError(
            f'Unsupported RDF/XML 1.2 shape for <{elem.tag}> combined with '
            'rdf:annotation/rdf:annotationNodeID/rdf:parseType="Triple" - only '
            'rdf:resource, rdf:nodeID, a single nested node element, or plain '
            'literal content are supported there.'
        )

    def _append_term_component(self, parent: ET.Element, local: str, node) -> None:
        el = ET.SubElement(parent, _R + local)
        if isinstance(node, URIRef):
            el.set(_R + 'resource', str(node))
        elif isinstance(node, BNode):
            el.set(_R + 'nodeID', str(node))
        elif isinstance(node, Literal):
            el.text = str(node)
            if node.language:
                el.set(_X + 'lang', node.language)
            elif node.datatype:
                el.set(_R + 'datatype', str(node.datatype))
        else:
            raise TypeError(f'Unexpected node type in triple term: {type(node).__name__}')

    def _emit_triple_term_block(self, s, p, o) -> str:
        """Append an rdf:TripleTerm intermediate block for (s, p, o) as a new
        sibling node element; return its rdf:nodeID."""
        bn_id = self._fresh_id()
        desc = ET.Element(_R + 'Description')
        desc.set(_R + 'nodeID', bn_id)
        self._append_term_component(desc, 'subject', s)
        self._append_term_component(desc, 'predicate', p)
        self._append_term_component(desc, 'object', o)
        type_el = ET.SubElement(desc, _R + 'type')
        type_el.set(_R + 'resource', str(_RDF_TRIPLE_TERM))
        self._extra_elems.append(desc)
        return bn_id

    def _process_parse_type_triple(self, elem: ET.Element, base: str | None) -> str:
        """elem has rdf:parseType="Triple". Emits the intermediate block for
        its content (recursing for a nested triple term) and returns its
        rdf:nodeID."""
        children = list(elem)
        if len(children) != 1:
            raise ValueError(
                'rdf:parseType="Triple" must contain exactly one node element, '
                f'found {len(children)} in <{elem.tag}>'
            )
        node_el = children[0]
        inner_s = self._resolve_node_element_subject(node_el, base)
        prop_children = list(node_el)
        if len(prop_children) != 1:
            raise ValueError(
                "A triple term's node element must contain exactly one "
                f'property (one predicate-object pair), found {len(prop_children)}'
            )
        prop_el = prop_children[0]
        self._strip_version_attr(prop_el)
        inner_p = _local_to_uriref(prop_el.tag)
        if prop_el.get(_R + 'parseType') == 'Triple':
            inner_o = BNode(self._process_parse_type_triple(prop_el, base))
        else:
            inner_o = self._resolve_object_from_property(prop_el, base)
        return self._emit_triple_term_block(inner_s, inner_p, inner_o)

    def _process_property(self, elem: ET.Element, subject, base: str | None) -> None:
        """Rewrite a single property element of *subject* in place."""
        self._strip_version_attr(elem)
        parse_type = elem.get(_R + 'parseType')
        annotation = elem.get(_R + 'annotation')
        annotation_node_id = elem.get(_R + 'annotationNodeID')

        if parse_type == 'Triple':
            bn_id = self._process_parse_type_triple(elem, base)
            for child in list(elem):
                elem.remove(child)
            elem.text = None
            del elem.attrib[_R + 'parseType']
            elem.set(_R + 'nodeID', bn_id)

        if annotation is not None or annotation_node_id is not None:
            predicate = _local_to_uriref(elem.tag)
            obj = self._resolve_object_from_property(elem, base)
            bn_id = self._emit_triple_term_block(subject, predicate, obj)

            reifies_el = ET.Element(_R + 'Description')
            if annotation is not None:
                reifier_uri = urljoin(base, annotation) if base else annotation
                reifies_el.set(_R + 'about', reifier_uri)
                del elem.attrib[_R + 'annotation']
            else:
                reifies_el.set(_R + 'nodeID', annotation_node_id)
                del elem.attrib[_R + 'annotationNodeID']
            self._append_term_component(reifies_el, 'reifies', BNode(bn_id))
            self._extra_elems.append(reifies_el)

    def process(self, root: ET.Element, base: str | None) -> None:
        for node_el in list(root):
            subject = self._resolve_node_element_subject(node_el, base)
            for prop_el in list(node_el):
                self._process_property(prop_el, subject, base)
        for extra in self._extra_elems:
            root.append(extra)


def parse_rdfxml12(text: str) -> list[tuple]:
    """Parse RDF/XML 1.2 text; return list of (s, p, o) triples.

    rdf:parseType="Triple" (triple terms in object position) and
    rdf:annotation/rdf:annotationNodeID (the reifier-shorthand attributes) are
    the two RDF 1.2 additions to RDF/XML; both are preprocessed at the XML
    tree level (see _Preprocessor) into the bnode-based rdf:TripleTerm
    intermediate encoding, then handed to rdflib's real (RDF 1.1) 'xml'
    parser, then converted to TripleTerm objects exactly as before.
    Subjects and objects may be TripleTerm instances.
    """
    root = ET.fromstring(text)
    base = root.get(_X + 'base')
    _Preprocessor().process(root, base)
    modified_text = ET.tostring(root, encoding='unicode')

    raw = rdflib.Graph()
    raw.parse(data=modified_text, format='xml')
    return _convert_bnodes(raw)
