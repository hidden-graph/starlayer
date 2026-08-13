"""
Turtle 1.2 round-trip demo.

Shows three views of the same graph:
  1. The TTL 1.2 input
  2. StarLayerGraph internal store — Turtle 1.1 serialization of the underlying
     rdflib store after skolemization (tt:HASH URIRefs, no sl: type triples)
  3. StarLayer Turtle 1.2 output — triple terms as <<( )>>, encoding hidden

Run from anywhere:
  python examples/ttl12_roundtrip_demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rdflib import Graph
from starlayergraph.parsers.turtle_parser import StarLayerTurtleParser
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

INPUT = """\
@prefix : <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

# Named reifier — :stmt1 reifies the triple and carries provenance
:alice :says <<( :bob :knows :carol )>> .
:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" ;
       :source :WikiData .

# Inline annotation shorthand {| |} — anonymous reifier
:bob :knows :carol {| :since "2020" ; :via :LinkedIn |} .

# Reification shorthand — anonymous reifier, base triple NOT asserted
<< :bob :knows :carol >> :verifiedBy :ResearchTeam .
"""

DIVIDER = '-' * 60


def _serialize_store(sg):
    """Serialize the raw rdflib store inside a StarLayerGraph to Turtle 1.1.

    Bypasses StarLayerGraph.triples() so the internal tt: encoding triples
    are visible, but skips prefixes whose namespace doesn't appear in the data.
    """
    # Copy the raw store into a plain rdflib Graph to use rdflib's serializer
    store_graph = Graph()
    for prefix, ns in sg.namespaces():
        store_graph.bind(prefix, ns)
    # Use Graph.triples directly (unbound) to bypass our override
    for triple in Graph.triples(sg, (None, None, None)):
        store_graph.add(triple)

    ttl = store_graph.serialize(format='turtle')
    nt  = store_graph.serialize(format='nt')
    # Keep only prefix lines whose namespace actually appears in the data
    return '\n'.join(
        ln for ln in ttl.splitlines()
        if not ln.startswith('@prefix') or _ns_used(ln, nt)
    )


def _ns_used(prefix_line, nt_text):
    parts = prefix_line.split()
    if len(parts) >= 3:
        return parts[2].strip('<>') in nt_text
    return False


def main():
    parser = StarLayerTurtleParser()
    raw = parser.parse(INPUT)
    sg  = StarLayerGraph.from_rdflib(raw)

    print(DIVIDER)
    print('INPUT (Turtle 1.2)')
    print(DIVIDER)
    print(INPUT)

    print(DIVIDER)
    print('STARLIGHT INTERNAL STORE  (Turtle 1.1 view, encoding exposed)')
    print(DIVIDER)
    print(_serialize_store(sg))

    print()
    print(DIVIDER)
    print('STARLIGHT TURTLE 1.2  (encoding hidden, triple terms as <<( )>>)')
    print(DIVIDER)
    print(sg.serialize(format='turtle12'))


OUTPUT = Path(__file__).parent.parent / 'samples' / 'ttl_1.2_output.txt'


if __name__ == '__main__':
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main()
    text = buf.getvalue()
    print(text)
    OUTPUT.write_text(text)
    print(f'(also written to {OUTPUT})')
