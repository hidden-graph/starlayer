"""
starlayergraph.serializers.trig12

Serialize a StarLayerGraph to TriG 1.2 text.

If the graph has a named identifier (URIRef) the triples are wrapped in a
``GRAPH <name> { ... }`` block.  If the identifier is a BNode (the rdflib
default) the content is emitted as plain Turtle 1.2 (the default-graph
convention in TriG).

Entry point:  serialize_trig12(g) -> str
"""

from __future__ import annotations

from rdflib import BNode

from starlayergraph.serializers.turtle12 import serialize_turtle12


def serialize_trig12(g) -> str:
    """Serialize *g* to TriG 1.2 text.

    Named graph identifier → ``GRAPH <uri> { ... }``
    BNode identifier        → plain Turtle 1.2 (default graph in TriG)
    """
    turtle_text = serialize_turtle12(g)

    if isinstance(g.identifier, BNode):
        # Default graph — plain Turtle 1.2 is valid TriG
        return turtle_text

    # Extract prefix declarations (all lines starting with '@prefix')
    prefix_lines: list[str] = []
    body_lines: list[str] = []
    for line in turtle_text.splitlines():
        if line.startswith('@prefix'):
            prefix_lines.append(line)
        else:
            body_lines.append(line)

    # Indent body content inside the GRAPH block
    indent = '    '
    indented_body = '\n'.join(
        indent + ln if ln.strip() else ln
        for ln in body_lines
    ).rstrip()

    graph_iri = str(g.identifier)
    graph_block = f'GRAPH <{graph_iri}> {{\n{indented_body}\n}}'

    parts = []
    if prefix_lines:
        parts.append('\n'.join(prefix_lines))
    parts.append(graph_block)
    return '\n\n'.join(parts) + '\n'
