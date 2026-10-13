"""
starlayer.graph.serializers.trig12

Serialize a StarLayerGraph to TriG 1.2 text.

If the graph has a named identifier (URIRef) the triples are wrapped in a
``GRAPH <name> { ... }`` block.  If the identifier is a BNode (the rdflib
default) the content is emitted as plain Turtle 1.2 (the default-graph
convention in TriG).

Entry point:  serialize_trig12(g) -> str
"""

from __future__ import annotations

from rdflib import BNode

from starlayer.graph.serializers.turtle12 import (
    iter_lines_outside_strings,
    serialize_turtle12,
)


def _split_prefix_and_body_lines(turtle_text: str) -> tuple[list[str], list[str]]:
    """Split turtle_text's physical lines into (prefix_lines, body_lines) -
    prefix_lines being every line that's a genuine top-level '@prefix'
    directive, body_lines everything else.

    Uses iter_lines_outside_strings() to tell a real directive line from
    one that merely *starts with* the text '@prefix' while still inside an
    open string literal (see that function's docstring for the full
    rationale and the real bug this guards against - confirmed live via
    this project's own code-KG extractor feeding this project's own
    trig12.py, whose module docstring does exactly this, back through
    itself).
    """
    prefix_lines: list[str] = []
    body_lines: list[str] = []
    for line, in_string in iter_lines_outside_strings(turtle_text):
        if not in_string and line.startswith('@prefix'):
            prefix_lines.append(line)
        else:
            body_lines.append(line)
    return prefix_lines, body_lines


def serialize_trig12(g) -> str:
    """Serialize *g* to TriG 1.2 text.

    Named graph identifier → ``GRAPH <uri> { ... }``
    BNode identifier        → plain Turtle 1.2 (default graph in TriG)

    Args:
        g: The graph to serialize.

    Returns:
        The TriG 1.2 serialization of g.
    """
    turtle_text = serialize_turtle12(g)

    if isinstance(g.identifier, BNode):
        # Default graph — plain Turtle 1.2 is valid TriG
        return turtle_text

    # Extract prefix declarations (every genuine top-level '@prefix' line)
    prefix_lines, body_lines = _split_prefix_and_body_lines(turtle_text)

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
