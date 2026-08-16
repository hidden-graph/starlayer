"""
starlayergraph.serializers.ntriples12

Serialize a StarLayerGraph to N-Triples 1.2 or N-Quads 1.2.

Triple terms in subject / object position are written as <<( s p o )>>.
All terms are written in long form (full IRIs; no prefix abbreviation).

Entry points:
    serialize_ntriples12(g) -> str
    serialize_nquads12(g, graph_uri=None) -> str
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.triple import TripleTerm

# ---------------------------------------------------------------------------
# Node formatter
# ---------------------------------------------------------------------------

_NT_ESCAPE = str.maketrans({
    '\\': '\\\\',
    '"':  '\\"',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
})


def _node_to_nt(node) -> str:
    """Format a node as an N-Triples 1.2 term string."""
    if isinstance(node, TripleTerm):
        s = _node_to_nt(node.subject)
        p = _node_to_nt(node.predicate)
        o = _node_to_nt(node.object)
        return f'<<( {s} {p} {o} )>>'

    if isinstance(node, DirLangString):
        escaped = _escape_non_ascii(node.value.translate(_NT_ESCAPE))
        return f'"{escaped}"@{node.language}--{node.direction}'

    if isinstance(node, URIRef):
        # Escape characters forbidden inside <> per N-Triples spec
        iri = str(node)
        iri = iri.replace('\\', '\\\\').replace('>', '\\>')
        return f'<{iri}>'

    if isinstance(node, BNode):
        return f'_:{node}'

    if isinstance(node, Literal):
        value = str(node).translate(_NT_ESCAPE)
        # Also escape non-ASCII as \uXXXX / \UXXXXXXXX for strict N-Triples
        escaped = _escape_non_ascii(value)
        if node.language:
            return f'"{escaped}"@{node.language}'
        dt = str(node.datatype) if node.datatype else 'http://www.w3.org/2001/XMLSchema#string'
        return f'"{escaped}"^^<{dt}>'

    raise TypeError(f'Unexpected node type: {type(node).__name__}: {node!r}')


def _escape_non_ascii(s: str) -> str:
    """Escape non-ASCII characters as \\uXXXX or \\UXXXXXXXX."""
    out: list[str] = []
    for ch in s:
        cp = ord(ch)
        if cp > 0xFFFF:
            out.append(f'\\U{cp:08X}')
        elif cp > 0x7F:
            out.append(f'\\u{cp:04X}')
        else:
            out.append(ch)
    return ''.join(out)


# ---------------------------------------------------------------------------
# Sort key — deterministic output
# ---------------------------------------------------------------------------

def _sort_key(node) -> tuple:
    if isinstance(node, TripleTerm):
        return (2, _node_to_nt(node))
    if isinstance(node, URIRef):
        return (0, str(node))
    if isinstance(node, BNode):
        return (1, str(node))
    if isinstance(node, DirLangString):
        return (3, node.n3())
    return (3, str(node))


def _triple_sort_key(triple) -> tuple:
    s, p, o = triple
    return (_sort_key(s), _sort_key(p), _sort_key(o))


def _needs_version_header(g) -> bool:
    if getattr(g, '_tt_nodes', None):
        return True
    return any(isinstance(o, DirLangString) for _, _, o in g.triples((None, None, None)))


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def serialize_ntriples12(g) -> str:
    """Serialize a StarLayerGraph to N-Triples 1.2 text.

    One triple per line: ``subject predicate object .``
    Triple terms are written as ``<<( s p o )>>``.
    """
    header = 'VERSION "1.2"\n' if _needs_version_header(g) else ''
    lines = []
    for s, p, o in sorted(g.triples((None, None, None)), key=_triple_sort_key):
        lines.append(f'{_node_to_nt(s)} {_node_to_nt(p)} {_node_to_nt(o)} .')
    return header + '\n'.join(lines) + ('\n' if lines else '')


def serialize_nquads12(g, graph_uri=None, _include_header: bool = True) -> str:
    """Serialize a StarLayerGraph to N-Quads 1.2 text.

    One quad per line: ``subject predicate object graph .``
    If *graph_uri* is None the graph's own identifier is used.
    """
    if graph_uri is None:
        graph_uri = g.identifier
    g_term = _node_to_nt(graph_uri) if not isinstance(graph_uri, BNode) else None

    header = 'VERSION "1.2"\n' if (_include_header and _needs_version_header(g)) else ''
    lines = []
    for s, p, o in sorted(g.triples((None, None, None)), key=_triple_sort_key):
        s_t = _node_to_nt(s)
        p_t = _node_to_nt(p)
        o_t = _node_to_nt(o)
        if g_term:
            lines.append(f'{s_t} {p_t} {o_t} {g_term} .')
        else:
            lines.append(f'{s_t} {p_t} {o_t} .')
    return header + '\n'.join(lines) + ('\n' if lines else '')
