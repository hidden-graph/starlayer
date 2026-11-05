# E1 notes: the sqe path off rdflib (branch `mig-e1-sqe`)

Goal (d4-notes follow-up 1): `sqe_parse_to_tree`, `sqe_tree_to_text`, `sqe_validate`, `rewrite_exists_text`, the RDF / RDFS
entailment rewrite and `StarQuery`'s syntax check run on pyoxigraph terms with no `import rdflib`; the sqe tree is a
`StarLayerGraph`.

## The redesign, and a correction to the brief

The brief said the sqe tree builder depends on an rdflib / pyparsing grammar through `parse_sparql.py`. It does not:
`parse_sparql.py` is the owned, hand-written SPARQL 1.2 parser (tokenizer plus recursive descent, a generic `Node` AST), and
`sqe_parse_to_tree` already went `parse_sparql` -> `Node` AST -> encoder. Only the *terms* in that AST were rdflib's (through
`_terms.py`, rdflib classes or stand-ins) and the encoder wrote an rdflib graph. So nothing was ported from a grammar; the work was:

1. The parser's terms are pyoxigraph terms (`NamedNode`, `BlankNode`, `Literal`, `Variable`). `_terms.py` is deleted. A base
   direction is a real directional literal (it was an internal datatype IRI).
2. The encoder (`parse_sparql._Encoder`) collects `(s, p, o)` triples (`ast_to_triples`) and `ast_to_tree` adds them to a
   `StarLayerGraph`. The tree shape is unchanged.
3. `sqe/to_text.py` and `sqe/expr_text.py` read the tree through the graph methods (`objects`, `predicate_objects`, `value`,
   `items`, `in`) with pyoxigraph terms, and write property paths straight from the `spexpr:` path nodes (no rdflib `Path`).
4. `sqe/shapes.py` validates on `StarLayerGraph`s with the native SHACL engine (the shapes graphs were already native).
5. `sqe/rewrite.py` and `sqe/entailment.py` walk the AST and render it with `TreeIndex` (`sqe/_memtree.py`), an in-memory triple
   index that answers the same read calls. No store is involved, so a rewritten query keeps the lexical forms written (an Oxigraph
   store rewrites `"007"^^xsd:integer` to `"7"`, which a query about to be run must not suffer).
6. `StarQuery(text)` without rdflib checks the syntax with `parse_sparql` at construction (it prepares with rdflib when installed).
   `StarLayerGraph.query(entailment=RDF|RDFS)` no longer calls `require_rdflib`.

## Text an RDF term cannot be

A query may hold a relative IRI (`<s>` with no `BASE`), a blank node label or a language tag pyoxigraph rejects. The tree keeps
each as the opaque, reversible stand-in the SHACL engine uses under `term_policy("lenient")` (`urn:starlayer:invalid-iri:<pct>`,
`starlayer-invalid-bnode-<hex>`, a literal with datatype `urn:starlayer:invalid-lang:<tag>`); `sparql/_oxterms.py` makes and
takes them apart, and `sqe_tree_to_text` writes the original text back. `sqe_validate` already ran with `invalid_terms="lenient"`.

## Shared modules and compat layers

- `sparql/vocab.py` is now pyoxigraph (`SQE`, `SPEXPR`, `SALG` as `NS`, `VARIABLE_DATATYPE`, `PY_STR_DATATYPE`) and has no guard.
  The old rdflib module is `sparql/_vocab_rdflib.py` (git mv, content unchanged, still guarded); salg, SRL, the algebra encoder and
  decoder (`to_rdf.py`, `from_rdf.py`, `spexpr_codec.py`), `serialize12.py` and `_grammar12.py` import it.
- `sparql/sqe/vocab.py` is pyoxigraph terms (same names, same IRIs). `sparql/sqe/_vocab_rdflib.py` mirrors every name as an rdflib
  `URIRef` for `sqe/from_rdf.py` and SRL.
- `sparql/_sqe_rdflib.py` (git mv of the old `sqe/expr_text.py`) holds the rdflib `expr_text` and `_encode_expr` that SRL still
  uses on its rdflib `srl:` trees; `srl.py` imports them from there. `EXISTS` is not rendered there (it is not part of SRL).
- `parse_srl.py` converts the parser's pyoxigraph terms to rdflib terms in one function (`_rl`); the SRL tree and evaluator are
  unchanged.
- `shacl_engine/sparql_support.py` reads a variable's name with `.value`.
- Tests of salg that imported `starlayer.sparql.vocab` import `_vocab_rdflib` instead.

## Still rdflib

`sqe/from_rdf.py` (`sqe_tree_to_query`: decodes a tree to an rdflib `Query`; reads the `StarLayerGraph` through the bridge's
snapshot). `from starlayer.sparql.sqe import sqe_tree_to_query` calls `require_rdflib`. Retire it with salg.

## Tests changed

See the commit messages; the list of weakened or removed expectations is below.
