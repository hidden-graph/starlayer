# E4 notes: SRL and the salg retirement off rdflib (branch `mig-e4-srl-salg`)

Goal (migration plan B2 and B4, owner direction): every module of `packages/starlayer/starlayer` that imported rdflib at module
level, other than `owl_dl*`, the bridge and the extra-guarded reasoners, is rdflib-free. SRL runs on pyoxigraph terms; the salg
export and the algebra encoder are deleted.

## What was done

### SRL (stage 1)

SRL needed less than a new engine. The parser (`parse_srl`) already sat on the owned parser, and the evaluator (`srl_eval`)
already matched rule bodies and evaluated expressions by sending SPARQL text to Oxigraph (a `StarLayerGraph`). What was rdflib
was the *tree* the two shared: rdflib terms, rdflib `Expr` / `CompValue` expression nodes, and the `srl:` encoder and decoder
on rdflib's graph and on the algebra codec (`spexpr_codec`). So:

- Terms in the SRL tree are pyoxigraph terms (`NamedNode`, `BlankNode`, `Literal`, `Variable`). A base direction is a real
  directional literal (it was a datatype IRI). A `TriplePattern` also accepts rdflib terms (converted by the bridge, imported
  only then) and `pyoxigraph.Triple` (stored as a `TripleTermNode`).
- Expressions are the parser's own `Node` trees. `triple_term.py` is now `ExprNode` (a `Node` with structural equality and hash,
  so rule sets compare equal after a round trip) and `TripleTermNode(ExprNode)`; `parse_srl._convert` keeps the check that a
  built-in is one SRL's `BuiltInCall` lists. `expr_text.py` (rdflib) is replaced by a 40-line module: `render_expression` goes
  through the same encoder and `sqe/expr_text.py` renderer the `sqe:` / `srl:` text uses, and `expr_variables` walks a node.
- `srl.py`: `ruleset_to_tree` writes with `parse_sparql._Encoder` (terms, variables, expressions, triple terms exactly as `sqe:`
  does) into a `StarLayerGraph` by default (an rdflib graph argument is filled through the bridge). `tree_to_ruleset` reads a
  tree with the graph methods; an expression node is **rendered to text and parsed again** (`_decode_expr`), which is why the
  decoder needs no inverse of the encoder. `ruleset_to_text` takes a prefix dict, a `StarLayerGraph` or anything with
  `namespaces()`.
- `srl_validate` / `parse_ruleset(validate=True)`: the RDFS closure the shapes need is native now
  (`expr_validation.rdfs_schema` / `rdfs_entailed_copy`, moved out of `sqe/shapes.py` and shared); before, `srl_validate`
  passed `inference=RDFS`, which runs owlrl and so rdflib.
- `srl_eval`: rdflib `Variable` / `BNode` / `algebra.traverse` / `CompValue` replaced by pyoxigraph and `expr_nodes`. Solutions
  are keyed by `pyoxigraph.Variable`. A foreign (rdflib) base graph is still accepted: copied in and the result converted
  back by the bridge, each import guarded by `require_rdflib` (the clear ImportError).
- `parse_srl` no longer calls `reject_surrogate_escapes`: the owned tokenizer rejects a surrogate escape itself.

`sqe:` / `srl:` trees hold literals as the Oxigraph store keeps them, so a rule set read back from its tree has `"9"^^xsd:decimal`
where the text said `9.0`. The round-trip tests were changed from `9.0` to `9.5` (a form the store keeps); the evaluation
tests are not affected (values compare by value).

### Salg (stage 2) and the encoder

Steps 1 to 3 of `salg-retirement-analysis.md`, then step 5 (step 4, the lowering path, had been done at D1):

- Step 1 (separate the generic codec): not needed in the end. With SRL on the `sqe:` encoder nothing used `spexpr_codec` /
  `to_rdf` / `from_rdf` except salg and `sqe_tree_to_query`.
- Step 2 (port the checks): the `sqe:` shapes already carry the unbound-projected-variable and unbound-expression-variable
  checks. The SHACL pre-bound exemption (`$this`, `$value`, `$PATH`) is re-done on the sqe report in `meta_shapes`
  (`_is_prebound_variable_only_report` reads the variable from the result message the shapes write; a target query is still not
  exempt). The salg tests of the check moved to `tests/sparql/unit/test_sqe_unbound_variables.py` (queries; VALUES-bound and
  sub-select-projected variables added as the analysis asked; the salg `Update` sub-select case has no sqe counterpart, see below).
- Step 3: `shacl/meta_shapes.py` (`sparql_query_problems`, `_template_unbound_variables`) parses with `parse_sparql(text, None,
  prefixes)` (a new `prefixes` argument) and validates the `sqe:` tree with `sqe_validate`. The engine component
  `salg:noUnboundProjectedVariables` (`shacl_engine/components/extensions.py`, its `legacy_adapter`, and its row in
  `component_table.py`) is deleted.
- Deleted: `sparql/salg/` (7 files), `to_rdf.py`, `from_rdf.py`, `spexpr_codec.py`, `_vocab_rdflib.py`, `_sqe_rdflib.py`,
  `sqe/_vocab_rdflib.py`, `sqe/from_rdf.py` (`sqe_tree_to_query`), `serialize12.py`, `_translate_patches.py`, `_grammar12.py`,
  `parse12.py`, `_syntax_checks.py`; the starontology files `salg-ontology.ttl` and `sparql_shapes.ttl` and their registry
  entries (`sparql_owl`, `sparql_shacl`, the `salg` prefix, `_EXCLUDED_FROM_ONTOLOGY_LIST`); `starontology.trig` was rebuilt.
- `StarQuery` checks syntax with the owned parser at construction and always runs the text on Oxigraph (an rdflib graph
  argument is copied in by the bridge). `check_query` uses `parse_sparql` / `parse_sparql_update`.
- Curated KG: the six upstream-issue entries (rdflib 13, 14, 32, 40, 41, 42) whose `workedAroundByIdentifier` named the deleted
  `_syntax_checks` / `parse12` / `_grammar12` functions are now `documented-only`; the `upstream-workarounds` query's example
  symbol was repointed.

## Public surfaces dropped or changed

Dropped (no native replacement; the simplest option that keeps behaviour was to remove them):

| Surface | Why | Replacement |
|---|---|---|
| `starlayer.sparql.prepare_query_12`, `prepare_update_12`, `parse12.*` | an rdflib algebra `Query` | `parse_sparql` / `parse_sparql_update` (syntax tree), `StarLayerGraph.query()` (execution) |
| `query_to_rdf`, `rdf_to_query`, `update_to_rdf`, `rdf_to_update`, `queries_to_collection`, `rdf_to_collection`, `SALG` | the salg export, as decided | `sqe_parse_to_tree` / `sqe_tree_to_text` |
| `starlayer.sparql.salg.*` (`validate_query`, `find_unbound_projected_variables`, ...) | salg retired | `sqe_validate` |
| `sqe_tree_to_query` | it decoded to an rdflib `Query`; no live caller (library, scripts, `tools/kg`, tests all use the text) | `sqe_tree_to_text` then `query()` |
| `starontology` entries `sparql_owl`, `sparql_shacl` | salg retired | none |
| `serialize12._translate_algebra_12` | rdflib algebra to text | `sqe_tree_to_text` |

Changed:

- SRL AST terms are pyoxigraph terms (were rdflib); `RuleSet.query` on an Oxigraph graph returned pyoxigraph keys already and
  still does; on an rdflib graph it still returns rdflib keys and terms (rdflib needed).
- `ruleset_to_tree` / `srl_parse_to_tree` return a `StarLayerGraph` when no graph is given (was `rdflib.Graph`).
- `srl.SRL` is a pyoxigraph namespace (was an rdflib `Namespace`).
- `sparql/__init__` exports `check_query` and `StarQuery` only.
- The seven W3C subject-position triple-term syntax fixtures are no longer strict xfails: the owned parser accepts them (as the
  suite says), and rejects the two codepoint-escape fixtures rdflib's grammar let through (`codepoint-esc-01-bad`, `-03-bad`).
  A triple term in subject position is still refused by the SRL well-formedness check.

## Tests

Deleted, each because it tested deleted machinery (algebra encode / decode / regenerate on rdflib):
`test_shacl_shapes` (77 defs, the salg shapes), `test_semantic_checks`, `test_native_components_unbound_pv`,
`test_salg_components`, `test_query_collection`, `test_phase2_{aggregates,forms,paths,update,values_subquery}`,
`test_phase4_prologue`, `test_phase6_rdf12_native`, `test_phase6_serialize12`, `test_rdf_nil_roundtrip`, `test_roundtrip`,
`integration/test_adversarial_roundtrip`, `w3c_sparql12/test_w3c_sparql12_oxigraph_roundtrip`,
`graph/w3c_sparql12/test_algebra_regenerated_queries`; inside `test_w3c_sparql12` the evaluation tests of the regenerated text
(the same fixtures run on the original text in `tests/graph/w3c_sparql12`); `test_rdf_roundtrip` of `test_sqe_ontology` and the
`sqe_tree_to_query` calls of the sqe coverage tests; `test_plain_sparql_gets_the_same_fixes` (rdflib's grammar patch);
`test_sparql_shacl_is_registered_but_in_no_profile`.

Ported (same meaning, native parser): `test_remainders_93`, `test_syntax_checks`, `test_fixture_sparql_syntax`, the syntax half of
`test_w3c_sparql12`, `test_star_query`, the `TestSparqlQueryStructureValidation` class of `test_meta_shapes_extensions`, the SRL
unit tests (terms compared as pyoxigraph terms). `srl_conformance/helpers.expression_results` evaluated expressions with
rdflib's `FrozenBindings`; it now evaluates them through the evaluator's own `_eval_expr`.

Weakened (stated): `test_the_registry_has_shapes_graphs_to_check` expects 6 shapes graphs (7 before `sparql_shacl` went).
`test_srl_to_rdf` round trips use `9.5` where they used `9.0` (the Oxigraph lexical form, see above).

Added: `test_core_without_rdflib.py` (SRL parse, evaluate, query, plan, encode, validate, decode and render with rdflib
blocked; that SRL, `sparql_query_problems` and `StarQuery` load no rdflib module; that a foreign graph gives the clear
ImportError); `test_sqe_unbound_variables.py`.

## Decisions for the owner

1. **Notebooks name the dropped surfaces.** `docs/guides/05b-sparql-query-as-rdf.ipynb`, `appendix-b1-sqe-shared-parts.ipynb`
   (`sqe_tree_to_query`), `05-starlayer-schemas-and-ontologies.ipynb`, `05d-shacl-library-registry.ipynb` and
   `appendix-a-public-resources.ipynb` (the salg ontology and shapes links) still do. Per the working agreement no notebook was
   edited; they need a pass before they are run.
2. **`starontology/` was edited** (two files deleted, the registry and `starontology.trig` regenerated): the owner direction
   said to retire the salg machinery, and the files serve only it. The cosmetic `salg:` mentions in `spexpr_shapes.ttl` /
   `spexpr-ontology.ttl` `sh:message` and comment text and the stale `@prefix salg:` lines in four other `.ttl` files were left
   (each is a starontology edit).
3. **A SPARQL Update sub-select with an unbound projected variable** was a salg check (`update_to_rdf`); `sqe:` has no
   Update shape for it. Not ported.
4. **`ExprNode` equality** is structural and ignores the source offset; `TripleTermNode` keeps its `get` accessor. If the AST
   should become a public, documented type, it deserves its own page.
5. `srl_validate`'s closure is now `rdfs_entailed_copy`, which implements rdfs2, 3, 7 and 9 (and the closures of 5 and 11) for the
   shipped ontologies only; `RuleSet.infer(inference=...)` still runs owlrl through the bridge (an rdflib copy).
