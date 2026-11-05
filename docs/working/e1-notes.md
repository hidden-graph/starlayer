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

## Other changes that came with it

- `sqe_validate` closes the tree under the RDFS rules the sqe shapes need (sub-property, domain, range, sub-class from the sqe and
  spexpr ontology) in `sqe/shapes.py`, instead of `inference=ENTAILMENT.RDFS`: the general RDFS closure (`infer()`) runs on owlrl and
  so on rdflib. The result is the same for the shapes (all sqe tests and the shape-mutation audit pass).
- `starontology._resource_iri` is always a `NamedNode` (it imported rdflib to make a `URIRef`, which loaded rdflib on every
  ontology load); the public `get_resource_iri` still returns a `URIRef` when rdflib is installed (non-spec-behaviour row 29).
- `sqe_tree_to_text` and `sqe_validate` still accept an rdflib graph (and root): it is copied to a `StarLayerGraph` with the
  bridge (`sqe/_memtree.as_engine_graph`), which `tools/kg/codekg/queries.py` (the query library is an rdflib graph) relies on.
  `sqe_parse_to_tree(graph=<rdflib graph>)` fills it with rdflib terms; a relative IRI then shows as its stand-in IRI.

## Tests changed (none skipped or xfailed)

- `tests/test_core_without_rdflib.py`: the `_terms` stand-in tests are gone (`_terms.py` is deleted); the ImportError case for
  `query(entailment=RDFS)` is gone (it now works without rdflib); new tests run `sqe_parse_to_tree`, `sqe_tree_to_text`,
  `sqe_validate`, `rewrite_exists_text`, the RDF and RDFS entailment rewrites and `StarQuery`'s syntax check with rdflib blocked,
  check `sqe_tree_to_query` still says it needs rdflib, and check the sqe text path loads no rdflib module.
- `tests/sparql/test_parse_sparql.py`: **weakened one check.** `test_numeric_literals_keep_their_lexical_form` used to check that
  `sqe_tree_to_text(*sparql_to_tree(q))` keeps `007`, `+5`, `1E0`; `sparql_to_tree` now returns a store-backed `StarLayerGraph`, and
  Oxigraph normalises those lexical forms on storage. The check now renders through `TreeIndex` (no store), which keeps them, and
  the parser-level checks (the AST holds the lexical form) are unchanged.
- `tests/sparql/parse_sparql_support.py`, `test_parse_sparql*.py`, `parse_sparql_conformance/test_coverage_matrix.py`: the tree
  comparison uses native `isomorphic` on `StarLayerGraph`s and pyoxigraph terms instead of rdflib's.
- `tests/sparql/unit/{test_query_collection,test_shacl_shapes}.py`: import the salg names from `_vocab_rdflib`.
- `tests/sparql/unit/test_sqe_ontology.py`, `test_parse_sparql_update.py`: pyoxigraph terms for roots and tree edits.
- `tests/kg/unit/test_queries.py`: one rdflib `URIRef` in an rdflib library graph.
- The opt-in `--sqe-coverage` set (with `STARLAYER_SQE_FUZZ_EXAMPLES=20`) passes unchanged: 2,444 passed, 3 xfailed.

## Decisions for the owner

1. Lexical forms in a stored sqe tree (`sqe_parse_to_tree` returns a store-backed graph): accepted as the store's known
   normalisation (issue #190); the rewrites avoid it. Alternative: an in-memory `TreeIndex`-style graph type for trees.
2. `sqe_tree_to_query` stays rdflib-only (retire with salg), as does `_vocab_rdflib.py` and friends until SRL / salg convert.
3. The native RDFS rules in `sqe/shapes.py` are a private mini-closure; a native RDFS regime in `infer()` would replace it.
