"""
examples/sqlalchemy_store_demo.py

Demonstrates StarLayerGraph backed by a SQLAlchemy (SQLite) persistent store.

Steps:
  1. Parse a Turtle 1.2 file containing RDF 1.2 triple terms
  2. Store the data in a SQLite database via rdflib-sqlalchemy
  3. Reload the graph from the database in a fresh StarLayerGraph
  4. Run a SPARQL 1.2 query against the reloaded graph
  5. Assert expected results

Requires the `sqlalchemy` extra: pip install -e ".[sqlalchemy]"

Run from the project root:
    .venv/bin/python examples/sqlalchemy_store_demo.py
"""

import os
import tempfile

# --- register the SQLAlchemy store plugin (Python 3.14 compat workaround) ---
import rdflib_sqlalchemy
rdflib_sqlalchemy.registerplugins()

from rdflib import URIRef
from starlayergraph.graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'

TTL = """\
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> ;
         ex:confidence "0.9" .

ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> ;
         ex:source ex:newspaper .

ex:alice ex:knows ex:bob .
"""

GRAPH_URI = URIRef(EX + 'main')

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _section(title):
    print(f'\n{"─" * 60}')
    print(f'  {title}')
    print(f'{"─" * 60}')


# ---------------------------------------------------------------------------
# Step 1 — parse Turtle 1.2
# ---------------------------------------------------------------------------

_section('Step 1: Parse Turtle 1.2')

src = StarLayerGraph()
src.parse(data=TTL, format='turtle12')
print(f'Parsed {len(src)} user-visible triples')
print(f'Triple terms found: {len(src._tt_nodes)}')
for tt in src.triple_terms():
    print(f'  {tt}')


# ---------------------------------------------------------------------------
# Step 2 — write to SQLite via rdflib-sqlalchemy
# ---------------------------------------------------------------------------

_section('Step 2: Write to SQLite')

db_file = tempfile.mktemp(suffix='.db')
conn_str = f'sqlite:///{db_file}'
print(f'Database: {db_file}')

writer = StarLayerGraph(store='SQLAlchemy', identifier=GRAPH_URI)
writer.open(conn_str, create=True)

for triple in src:
    writer.add(triple)
# Copy namespace bindings
for prefix, ns in src.namespaces():
    writer.bind(prefix, ns)

writer.close()
print(f'Wrote and closed. File size: {os.path.getsize(db_file):,} bytes')


# ---------------------------------------------------------------------------
# Step 3 — reload from SQLite in a fresh graph
# ---------------------------------------------------------------------------

_section('Step 3: Reload from SQLite')

sg = StarLayerGraph(store='SQLAlchemy', identifier=GRAPH_URI)
sg.open(conn_str, create=False)   # open existing; open() calls _build_registry_from_store

print(f'Reloaded {len(sg)} user-visible triples')
print(f'Registry rebuilt: {len(sg._tt_nodes)} triple term(s)')
for tt in sg.triple_terms():
    print(f'  {tt}')


# ---------------------------------------------------------------------------
# Step 4 — SPARQL 1.2 query
# ---------------------------------------------------------------------------

_section('Step 4: SPARQL 1.2 query')

QUERY = """
PREFIX ex: <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?tt ?s ?p ?o ?conf WHERE {
    ?stmt rdf:reifies ?tt .
    ?tt rdf:subject ?s ; rdf:predicate ?p ; rdf:object ?o .
    OPTIONAL { ?stmt ex:confidence ?conf }
}
ORDER BY ?stmt
"""

results = list(sg.query(QUERY))
print(f'Rows returned: {len(results)}')
for row in results:
    conf = f'  confidence={row.conf}' if row.conf else ''
    print(f'  {row.stmt}  {row.tt}{conf}')


# ---------------------------------------------------------------------------
# Step 5 — assertions
# ---------------------------------------------------------------------------

_section('Step 5: Assertions')

assert len(results) == 2, f'Expected 2 rows, got {len(results)}'

stmts = {row.stmt for row in results}
assert URIRef(EX + 'stmt1') in stmts
assert URIRef(EX + 'stmt2') in stmts

# ?tt must be restored to a TripleTerm (not left as a tt:HASH URIRef)
for row in results:
    assert isinstance(row.tt, TripleTerm), \
        f'Expected TripleTerm, got {type(row.tt).__name__}: {row.tt!r}'

# stmt1 confidence
stmt1_row = next(r for r in results if r.stmt == URIRef(EX + 'stmt1'))
assert str(stmt1_row.conf) == '0.9', f'Unexpected confidence: {stmt1_row.conf}'

# Verify round-trip identity: reloaded TripleTerms equal originals
alice_knows_bob = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
bob_likes_carol  = TripleTerm(URIRef(EX+'bob'),   URIRef(EX+'likes'), URIRef(EX+'carol'))
loaded_tts = {row.tt for row in results}
assert alice_knows_bob in loaded_tts, f'alice_knows_bob not found in {loaded_tts}'
assert bob_likes_carol  in loaded_tts, f'bob_likes_carol not found in {loaded_tts}'

print('All assertions passed.')

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

sg.close()
os.unlink(db_file)
print(f'\nDatabase removed. Done.')
