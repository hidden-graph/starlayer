# The SPARQL layers (srl, sqe, spexpr, salg) with Oxigraph as the baseline

Exploration, read-only. Branch `shacl-engine`, worktree `/Users/johnclements/Documents/GitHub/starlight/shacl-engine`.
Everything below is from reading the code and from grep/wc counts taken in this worktree; I ran no tests, so
anything about behaviour is marked "unverified". Paths are relative to `packages/starlayer/` unless they start with
`tools/`, `scripts/` or `docs/`. Line counts are `wc -l`.

## 0. SUMMARY (one page)

**The hypothesis is partly right and partly wrong, and the wrong part decides the plan.**

| Claim | Verdict | Deciding facts |
|---|---|---|
| salg is all ours and independent of rdflib | **Refuted** | salg is a literal RDF encoding of rdflib's `CompValue` algebra. `sparql/to_rdf.py` (508) and `sparql/from_rdf.py` (599) import `rdflib.plugins.sparql.{algebra,parserutils,sparql}`; the decoder rebuilds executable rdflib `Query`/`Update` objects and finds the expression evaluators by walking rdflib's live pyparsing grammar (`from_rdf._discover_expr_evalfns`). Its class names are rdflib's node names (`Builtin_STRENDS`, `BGP`, `LeftJoin`). The `salg/` subpackage (812 lines) imports `_addVars`, `_traverseAgg`, `analyse` from rdflib's algebra. |
| sqe and spexpr are what tie into rdflib's algebra | **Partly** | sqe is built *from* rdflib's raw parse tree (encode) and decodes *back to* a `CompValue` tree that rdflib's `translateQuery` turns into a runnable `Query`. But sqe's text rendering (`sqe/to_text.py` 339 + `sqe/expr_text.py` 217) works straight from the RDF and is already differential-tested against Oxigraph. spexpr is not a layer: it is a namespace (`SPEXPR` in `sparql/vocab.py`), 62 `Builtin_*` class names that are rdflib's, three small helpers (227 lines) and two Turtle files (690 lines). The rdflib coupling is the same in all four; it is not specific to sqe/spexpr. |
| we may have to give up sqe/spexpr because they are patched for 1.2 | **Not supported** | The 1.2 patching is in the shared core (`_grammar12.py` 932, `parse12.py` 341, `triple_term.py` 249, `lower_rdf11.py` 1,971, `serialize12.py` 542), not in sqe/spexpr. Dropping sqe/spexpr removes none of it, and breaks SRL (srl.py imports `sqe.expr_text`, `sqe.to_rdf._encode_expr`, `sqe.vocab`, lines 147-149) and the code KG's 24 named queries. |
| the others (srl, salg) we need to keep | **Mostly right, for different reasons** | srl is a user feature (rules language) and must stay. "salg" is two things: the shared encoder (`to_rdf.py`/`from_rdf.py`/`vocab.py`, 1,451 lines), which sqe, srl and the query-compile step all import, and the `salg/` subpackage (validation shapes, ontology, one semantic check), which only a SHACL meta-check, a SHACL-engine extension and tests import. |
| rule: srl and sqe must not depend on salg | **Holds for the `salg/` package and for emitted terms; not for code** | No file in `sparql/` outside `salg/` imports `salg/` (grep: zero). sqe emits no `salg:` terms (enforced by `test_no_salg_terms_in_any_tree`, per CLAUDE.md). But sqe and srl do import the shared encoder whose vocabulary *is* salg (`SALG` appears 66 times in `vocab.py`, 38 in `to_rdf.py`, 30 in `from_rdf.py`). The reverse half ("salg uses sqe's terms") is not true in code: `salg/` imports nothing from sqe or srl. |

**Do we need salg?** Split the question.
- The `salg/` package (ontology `salg-ontology.ttl` 331 + `sparql_shapes.ttl` 1,013 lines, 812 Python lines): used by
  `shacl/meta_shapes.py:500` (structure check of `sh:select` text), `shacl_engine/components/extensions.py:27` (lazy
  `noUnboundProjectedVariables`), 5 test files outside `tests/sparql/`, 15 inside. Nothing in srl, sqe, tools/ or scripts/
  needs it. Cost to drop: those two call sites and about 400 test defs. Unique content: the only validation of a full
  algebra tree, and `find_unbound_projected_variables`. Dropping it is cheap and local.
- The salg *encoder* (`to_rdf.py`, `from_rdf.py`): not droppable by itself. It is on the hot path of **every query on a
  `StarLayerGraph`**: `prepareQuery` and `query_cache.prepare_query_cached` run `prepare_query_12 -> query_to_rdf11 ->
  rdf11_to_query` (`graph/query/sparql_api.py:116-117`, `graph/query/query_cache.py:162-163`), i.e. lower, encode to RDF,
  decode back. That round trip disappears if Oxigraph executes text (no lowering, no rdflib `Query`). sqe and srl use
  the same machinery for expressions.

**Biggest finding for the Oxigraph decision:** what rdflib is needed for, after the move, is **parsing and inspecting
queries** (SPARQL 1.2 grammar splice, KG/SRL/sqe trees, the SHACL-engine query checks), not evaluating them. That is
option (a) in section 5; it keeps all four layers and removes the lowering/evaluator coupling. Giving up sqe/spexpr does
not remove the parser dependency and costs the most features.

**Suggested spikes (not a decision):** S1 run the 24 KG queries through `sqe_tree_to_text` into pyoxigraph; S2 take the
salg round trip out of `prepareQuery` and see what fails; S3 evaluate one SRL rule body as a SELECT in Oxigraph;
S4 sizing spike for a standalone parser or a `spargebra` binding; S5 retire the orphan `ssyn`/`sast` files.
Details in section 6.

---

## 1. WHAT each layer is, and the real dependency graph

Directory `starlayer/sparql/` (called `sparql/` below) has 41 `.py` files, 12,646 lines, plus 8 Turtle files in
`starlayer/starontology/` (3,277 lines). There is **no `spexpr/` directory**; this matches
`docs/working/graph-rdflib-compat-inventory.md` section 2.3 item 3.

### 1.1 The layers by file

| Layer | Files (lines) | Python total | Turtle | Purpose and public API |
|---|---|---|---|---|
| **salg** (shared encoder) | `vocab.py` 344, `to_rdf.py` 508, `from_rdf.py` 599 | 1,451 | `salg-ontology.ttl` 331 | `query_to_rdf`, `rdf_to_query`, `update_to_rdf`, `rdf_to_update`, `queries_to_collection`, `rdf_to_collection`, `SALG`. One generic recursive encoder of rdflib's resolved algebra (`translateQuery` output) into RDF: `node.name` becomes `rdf:type salg:<name>`, each key a predicate. |
| **salg** (`salg/` subpackage) | `__init__` 32, `engine_components` 54, `expr_families` 6, `native_components` 148, `semantic_checks` 203, `sparql_ontology` 142, `sparql_shapes` 227 | 812 | `sparql_shapes.ttl` 1,013 | `ontology_graph`, `shapes_graph`, `validate_query` (pyshacl over the algebra graph), `find_unbound_projected_variables`, a pySHACL native component and a `shacl_engine` component. |
| **spexpr** (not a layer) | `expr_text.py` 105, `expr_families.py` 63, `expr_validation.py` 59, plus `SPEXPR` and `PY_STR_DATATYPE`/`VARIABLE_DATATYPE` in `vocab.py` | 227 | `spexpr-ontology.ttl` 233, `spexpr_shapes.ttl` 457 | The shared expression, variable and property-path vocabulary: 62 `Builtin_*` classes plus operators, shapes generated from `_EXPR_NODE_FAMILY` (rdflib's 63 builtins, keyed by rdflib's names). `expr_text` renders an rdflib `Expr`/`CompValue` expression back to text. |
| **sqe** | `sqe/__init__` 57, `vocab` 178, `to_rdf` 523, `from_rdf` 298, `to_text` 339, `expr_text` 217, `shapes` 80 | 1,692 | `sqe-ontology.ttl` 130, `sqe_shapes.ttl` 810 | "SPARQL query as editable RDF". `sqe_parse_to_tree(text)`, `sqe_tree_to_text`, `sqe_tree_to_query`, `sqe_validate`. A flat tree from the raw parse tree (before `translateQuery`); SELECT/ASK/CONSTRUCT and clauses, not DESCRIBE or Update (`sparql/CLAUDE.md`). |
| **srl** | `srl.py` 1,073, `srl_eval.py` 859, `_srl_ast.py` 477, `srl_semantic_checks.py` 219 | 2,628 | `srl-ontology.ttl` 33, `srl_shapes.ttl` 270 | SPARQL Rules (W3C WD sparql12-rl). `srl.parse_ruleset`, `RuleSet.infer()/.query()/.plan()`, `ruleset_to_tree`/`tree_to_ruleset`, `ruleset_to_text`, `srl_validate`; stratification and rule-order logic in `srl_eval.py`. |
| shared 1.2 core | `_grammar12` 932, `parse12` 341, `_syntax_checks` 199, `triple_term` 249, `lower_rdf11` 1,971, `serialize12` 542, `star_query` 155, `entailment_rdf` 151, `entailment_rdfs` 289 | 4,829 | none | The SPARQL 1.2 parser (rdflib grammar patched in place), the 1.2-to-1.1 lowering, the 1.2 text serializer, RDF/RDFS entailment by algebra rewriting. Used by all layers and by `graph/`. |
| orphan | `ast_vocab` 66, `from_ast_rdf` 118, `to_ast_rdf` 132, `to_ssyn_rdf` 282, `ssyn_to_text` 268, `ssyn_vocab` 80 | 946 | (none dedicated) | The `ssyn:`/`sast:` layers. Imported by no file in `starlayer/` outside these six; used only by 4 test files (`test_ssyn_ontology`, `test_ast_ontology`, `test_srl_to_text`, `srl_conformance/README`). |

### 1.2 Real import graph (grep of `import`/`from` lines)

```
salg/ (subpackage)  ->  ..from_rdf, ..vocab, ..expr_families, ..expr_validation, rdflib.algebra
                        (imports NOTHING from sqe/ or srl*)
sqe/                ->  ..from_rdf (_decode, _DECODE_HOOK, _EXPR_EVALFNS), ..to_rdf (_encode, hooks, _encode_path),
                        ..vocab (SPEXPR, PY_STR_DATATYPE), ..serialize12 (_dirlang_n3), ..parse12, ..expr_validation
srl.py              ->  .sqe.expr_text, .sqe.to_rdf._encode_expr, .sqe.vocab, .from_rdf._decode, .to_rdf,
                        .expr_validation, rdflib pyparsing productions (see 3.4)
srl_eval.py         ->  .srl, ._srl_ast, .lower_rdf11 (lazily), .from_rdf (_EXPR_EVALFNS), graph.model.*
lower_rdf11.py      ->  .from_rdf, .to_rdf, graph.query.algebra_translator_patches, graph.model.encoding
shared 1.2 core     ->  rdflib parser/algebra; star_query/entailment -> graph.graph.entailment_regimes
```

Evidence that **nothing imports `salg/`** inside `sparql/`: `grep -rnE "sparql\.salg|from \.salg|from \.\.salg|import salg"`
over `starlayer/` returns only `salg/`'s own docstrings, `sparql/__init__.py` comments, and these external call sites:
`shacl/meta_shapes.py:500`, `shacl_engine/components/extensions.py:27` (lazy), `shacl_engine/component_table.py:116-117`
(text only), `starontology/__init__.py:33` (docstring).

The rule check, in four parts:
1. srl and sqe do not import `salg/`. **True** (zero hits). `sqe/shapes.py:7` says so explicitly.
2. sqe emits no `salg:` terms. **True by test** (`test_no_salg_terms_in_any_tree`, named in `sparql/CLAUDE.md`; unverified here, I did not run it).
3. srl and sqe do not depend on salg *code*. **False**: both import `to_rdf.py`/`from_rdf.py`, which are the salg encoder, through the hooks `_NS_OVERRIDES`/`_ENCODE_HOOK`/`_DECODE_HOOK` (`to_rdf.py:76-89,267`, `from_rdf.py:256-263`). The hooks exist to keep `salg:` terms out of the output while reusing the machinery.
4. "Shared terms live in sqe/spexpr and salg uses them." **Half true**: the shared expression table lives in `sparql/expr_families.py` (its docstring says "none of them should import salg"), and `salg/` imports it (`salg/expr_families.py`, `salg/sparql_ontology.py:90`). `salg/` does not import anything from `sqe/`.

The `sparql/CLAUDE.md` file map still names `starsparql/...` paths and `packages/sparql`, so parts of it predate the layout (stale; I used the code, not those paths).

### 1.3 Dependency on the rest of the package

- `sparql/` -> `graph/`: `star_query.py:46`, `srl.py:1061`, `sqe/shapes.py:68` (`ENTAILMENT`), `lower_rdf11.py` (`algebra_translator_patches`, `model.encoding` TT hashes, 7 imports), `srl_eval.py` (`StarLayerGraph`, `StarLayerDataset`, `TripleTerm`, `sparql_term`), `sqe/expr_text.py:72` and `sqe/to_text.py:331` (`serializers.turtle12._PN_LOCAL`).
- `sparql/` -> `starontology/` (eager, loads the ontology and shapes Turtle: `starontology/__init__.py:16` says a hard runtime dependency), `shacl/` (lazy, `srl`/`sqe_validate` via pyshacl, `_srl_ast.py:433`).
- `graph/` -> `sparql/`: both directions exist and CLAUDE.md calls the two-way dependency deliberate. 45 lines in `graph/` name `starlayer.sparql`; the real imports are `parse12` (`prepare_query_12`, `prepare_update_12`, `parse_query_12`), `lower_rdf11` (`query_to_rdf11`, `rdf11_to_query`, `update_to_rdf11`, `rdf11_to_update`, `_AlgebraTranslator11`, `rdf11_to_query`), `entailment_rdf(s)`, `triple_term`. Files: `graph/query/{sparql_api,query_cache,version_directive}.py`, `graph/graph/{starlayer_graph,starlayer_dataset}.py`, `graph/backends/native.py`.

---

## 2. WHO uses each layer

### 2.1 Consumers outside `sparql/` (src, tools, scripts)

| Layer | Source consumers | tools/, scripts/ | Docs and notebooks |
|---|---|---|---|
| srl | None imports it. Docstring mentions only (`starlayer/__init__.py:19`, `starontology/{manchester,skos,__init__}.py`). It is a user API reached as `starlayer.sparql.srl`. | `scripts/generate_api_docs.py` (API reference) | 23 `.md` files mention it; notebooks `03b-srl-sparql-rules` (46 cells), `05c-srl-sparql-rules-as-rdf` (19), plus 7 more mention it |
| sqe | `tools/kg/codekg/queries.py` (3 import sites) | `scripts/build_kg.py`, `build_query_catalogue.py`, `build.py`, `generate_api_docs.py`, `build_kg` prefixes | 15 `.md`; notebooks `05b-sparql-query-as-rdf` (21), `appendix-b1-sqe-shared-parts` (15), +7 |
| spexpr | none directly (only via sqe/srl/salg) | `scripts/build_kg.py:46` (prefix) | 6 `.md`, 7 notebooks mention it |
| salg (`salg/`) | `shacl/meta_shapes.py:500`, `shacl_engine/components/extensions.py:27` | `generate_api_docs.py` | 13 `.md`, 3 notebooks |
| salg (encoder) | `graph/query/sparql_api.py`, `graph/query/query_cache.py` (compile step); `shacl/meta_shapes.py:525` (`query_to_rdf`) | none | notebook `05b` |
| core (parse12, lowering) | `graph/` (45 lines, section 1.3), `shacl/validator.py:5335`, `shacl/meta_shapes.py:508`, `shacl_engine/sparql_support.py` (via `prepareQuery`), `tools/kg` `run_sparql` | | |

### 2.2 User-facing features that exist only because of a layer

- **srl**: the SPARQL Rules language: parse (`parse_ruleset`, validated against `srl:` shapes by default, about 140 ms),
  evaluate (`RuleSet.infer`, `.query`, stratification, `.plan()`), rule sets as RDF (`ruleset_to_tree`) and back to text.
- **sqe**: query as editable RDF; `sqe` -> SPARQL text (`sqe_tree_to_text`); field-level validation of a query tree
  (`sqe_validate`, 810 lines of shapes, designed for UI editing); parsing text into a tree; running a tree
  (`sqe_tree_to_query`). The **code KG's query library**: `tools/kg/codekg/curated/query-library.ttl` (1,633 lines) holds
  **24** `slkg:NamedQuery` entries as `sqe:` trees; `queries.py` (496 lines) renders text (`get_query` -> `sqe_tree_to_text`),
  validates (`sqe_validate`), and runs (`run_query` -> `sqe_tree_to_query` then `_kg().query(query, initBindings=...)`).
  `run_sparql` (user text) uses `prepare_query_12`, not sqe.
- **salg**: store a *set* of resolved queries as one Turtle file (`queries_to_collection`); validate algebra structure
  (`validate_query`); catch an unbound projected variable (`find_unbound_projected_variables`, also a SHACL-engine
  extension component); structure check for `sh:select` text in shapes graphs (`shacl/meta_shapes.py`).
- **spexpr**: nothing a user sees alone; it is the expression vocabulary and shapes that sqe, srl and salg share.
- Text round trip `sqe` -> SPARQL: `sqe/to_text.py` + `sqe/expr_text.py` (556 lines). Query editing: sqe only.

### 2.3 Tests (my scan: every `.py` under `tests/` that mentions the layer; "defs" = `def test_` in those files, an
upper bound because a mentioning file may test other things, and parametrization multiplies runs)

| Layer (pattern) | Files | Test defs | Where |
|---|---|---|---|
| srl | 25 | 253 | `tests/sparql` 22, `graph` 1, `starontology` 1, `tests/` 1 |
| sqe | 16 | 144 | `tests/sparql` 12, `kg` 1 (`tests/kg/unit/test_queries.py`), `graph` 1, `starontology` 1, `tests/conftest.py` |
| salg (word `salg`/`SALG`) | 19 | 402 | `tests/sparql` 15; outside: `test_skos_shapes`, `test_starontology`, `shacl/integration/test_meta_shapes_extensions`, `shacl_engine/test_salg_components`, `tests/conftest.py` |
| spexpr | 7 | 174 | `tests/sparql` 6, `starontology` 1 |
| ssyn/sast | 4 | 53 | `tests/sparql` only |
| salg encoder calls (`query_to_rdf` family) | 26 | 302 | includes `graph` 2, `shacl_engine` 1 |
| parse12 / `prepare_query_12` | 25 | 514 | `graph` 6, `shacl` 2, `shacl_engine` 1 |
| lower_rdf11 | 7 | 137 | `graph` 3 |
| serialize12 | 9 | 144 | `graph` 2 |

Two large opt-in suites sit on top: `tests/sparql/sqe_coverage/` (7 test files, 18 defs; runs every W3C 1.2 query fixture and
90+ feature queries, hypothesis suites, a differential suite against Oxigraph, `--sqe-coverage`, about 4 minutes; 9 lines
in `sqe_known_gaps.txt`) and `tests/sparql/srl_conformance/` (7 test files, 31 defs, corpus-driven).

---

## 3. HOW each layer ties to rdflib

### 3.1 Symbols, per layer

| File(s) | rdflib symbols | Nature |
|---|---|---|
| `_grammar12.py` 932 | `rdflib.plugins.sparql.parser` (grammar productions `GraphTerm`, `VarOrTerm`, `GraphNode`, `GraphNodePath`, `TriplesSameSubject*`, `BlankNodePropertyList*`), `parserutils.{Comp,CompValue,Param}` | **Splices into rdflib's live global pyparsing grammar in place** (`install()` mutates `MatchFirst` objects). Import order matters (`sparql/__init__.py:10`). |
| `parse12.py` 341 | `parseQuery`, `parseUpdate`, `translateQuery`, `translateUpdate`, `Prologue`, `Query`, `Update` | Parses with the patched grammar, then rdflib's `translateQuery` builds the algebra. |
| `triple_term.py`, `_syntax_checks.py` | `CompValue` | `TripleTermNode` is a `CompValue` subclass (needed for rdflib's `reorderTriples`/`_addVars` machinery, per CLAUDE.md). |
| `to_rdf.py`/`from_rdf.py` (salg) | `CompValue`, `Expr`, `Prologue/Query/Update`, `rdflib.paths.*`, `_addVars`, `_traverseAgg`, `analyse`, `simplify`, `TrueFilter`, `Comp` and the `parser` module (introspected) | **Representation**: the RDF form is a serialization of rdflib's `CompValue` trees; the decoder reconstructs them and re-runs rdflib's post-translate passes. |
| `lower_rdf11.py` 1,971, `serialize12.py` 542 | `_AlgebraTranslator` (subclassed at `lower_rdf11.py:1689`, `serialize12.py:153`), `algebra`, `CompValue` | Tree-to-tree lowering (1.2 -> 1.1) and tree-to-text, both subclassing rdflib's translator. |
| `sqe/to_rdf.py` | `algebra` (`triples`, `translatePath` and friends), `CompValue`, `ParseResults`, `IdentifiedNode` | Encodes rdflib's **raw parse tree** (not the algebra) into the flat sqe vocabulary. Expressions go through the shared generic `_encode` (an rdflib `Expr` tree). |
| `sqe/from_rdf.py` | `translateQuery`, `CompValue`, `Expr`, `Query` | Rebuilds the raw-parse-tree `CompValue`s and hands them to **unmodified** `translateQuery`. |
| `sqe/to_text.py`, `sqe/expr_text.py` | `rdflib.paths` (`Path`, `AlternativePath`, `SequencePath`, `InvPath`, `MulPath`), `Graph`, `Collection`, terms; `to_text._predicate_text` calls the salg `_decode` for property paths (`to_text.py:255`) | RDF-to-text. No `CompValue` walk for patterns or expressions; only property paths are decoded into rdflib `Path` objects first. |
| `srl.py` 1,073 | `parser.{BaseDecl, Constraint, Expression, PrefixDecl, String, TriplesSameSubject, TriplesSameSubjectPath, Var, iri, expandUnicodeEscapes}`, `parserutils.{Comp, CompValue, Param}`, `pyparsing_compat.rest_of_line`, `algebra`, `Prologue` | SRL grammar is **written in rdflib's pyparsing**, reusing its productions for expressions and triple blocks. The AST holds rdflib `Expr` trees for `FILTER`/`SET`. |
| `srl_eval.py` 859 | `evaluate.{_ebv, evalBGP}`, `sparql.{QueryContext, SPARQLError}`, `algebra.traverse` | **Runs rule bodies through rdflib's evaluator** (see 3.4). |
| `entailment_rdf(s).py` | `algebra.traverse`, `CompValue`, `rdflib.paths` | Rewrites a prepared algebra for entailment regimes. |
| `salg/semantic_checks.py` | `_addVars`, `_traverseAgg`, `analyse` | Reuses rdflib's variable-scope bookkeeping. |

### 3.2 Is rdflib's algebra the REPRESENTATION, or only a source/target?

- **salg: the representation.** Encode = walk `CompValue`; decode = rebuild `CompValue` and run rdflib's passes. Changing the
  algebra (a different parser, different node names) would change the vocabulary and the 1,013-line shapes. This is a
  rewrite of the layer, not of a converter.
- **sqe: source and target, not representation.** The tree is its own flat vocabulary (own classes, own shapes). rdflib
  appears in exactly two edges: **in** (`sqe/to_rdf.py` consumes `parseQuery` output) and **out to execution**
  (`sqe/from_rdf.py` -> `translateQuery` -> `Query`). The third edge, **out to text** (`to_text.py`, `expr_text.py`), needs
  rdflib only for terms and property paths. Evidence for how detached the text edge is: its own docstring ("working
  straight from the RDF tree. Replaces the earlier route through rdflib's `translateAlgebra`") and the Oxigraph
  differential test `test_sqe_text_agrees_with_oxigraph` (`tests/sparql/sqe_coverage/test_oxigraph_differential.py`, which
  runs the text sqe renders against the original query on Oxigraph; unverified here, I did not run it).
  **One exception on the representation side:** the *expression* subtree of an sqe tree is the shared generic encoding of an
  rdflib `Expr` (`sqe/to_rdf.py:131 _encode_expr` -> `..to_rdf._encode`). So sqe expressions carry rdflib's node names. That
  is the part of sqe that is spexpr, and what makes "give up sqe/spexpr" overlap with salg and srl.
  Giving sqe up is therefore a rewrite of `sqe/to_rdf.py` (523) and `sqe/from_rdf.py` (298), not of `to_text.py`/shapes,
  *if* the input source changes.
- **spexpr: representation by name.** Its classes are rdflib's builtin names, generated from `_EXPR_NODE_FAMILY`, which is
  validated against rdflib's grammar at import (`from_rdf._discover_expr_evalfns`). A non-rdflib parser would have to emit
  the same names or the vocabulary changes.

### 3.3 Where rdflib's evaluator is used

Production query path (all `StarLayerGraph`/`StarLayerDataset` queries on the default `rdf-1.1` backend):
`query text -> parse12 -> 1.2 algebra -> lower_rdf11 -> (query_to_rdf, rdf_to_query) -> rdflib Query -> rdflib evaluator`.
`lower_rdf11.py:537` comments on why the encode/decode round trip matters (it also exposed an
empty-list-field gap). The `graph/query/` patch files (`evaluate_patches.py`, 564 lines) patch that evaluator; the inventory
doc (section 2.3 item 4) counts them. The native Oxigraph backend (`graph/backends/native_oxigraph.py`, 135 lines) takes SPARQL
text directly (`_query`, `ox_select`, `ox_ask`, `ox_update`).

### 3.4 SRL specifically

- **Parse**: tied to rdflib's grammar (table above). Would still need rdflib (or a replacement parser) for `Expression`,
  `Constraint`, `TriplesSameSubject`.
- **Evaluate**: `srl_eval.py` lines 441-464 call `evalBGP(ctx, bgp)` once per incoming solution per run of triple patterns;
  `_eval_ebv` calls `_ebv(_runnable(expr), ctx)`; `_eval_expr` evaluates `Expr` for `SET`; `_match_with_query` (line 332-341)
  calls `g.query("SELECT * WHERE { ... }")` for runs with triple terms, i.e. `StarLayerGraph.query` and so the rdflib path
  of 3.3. Stratification and dependency graph (`_build_dependency_graph` line 138, `_stratify` line 186, about 110 lines)
  are plain Python over the AST and do not touch rdflib.
- **If bodies ran in Oxigraph** (design sketch, unverified): the per-solution Python loop becomes one SELECT per rule per
  stratum iteration (body to text: triple patterns, `FILTER`, `NOT`-as-`FILTER NOT EXISTS`, `SET` as `BIND`); stratification
  and head instantiation (fresh blank node per solution, `_subst_head_triple`) stay; the AST's rdflib `Expr` trees would be
  replaced by text or by sqe-style trees (which already render text). Things to check: `NOT DATA`/`WHERE DATA` match the *base*
  graph, so two graphs or named graphs are needed; one `NOW()` instant per evaluation (`_context`, line 704) has no Oxigraph
  equivalent known to me; builtin differences (capability matrix section 4: 34 of 40 sampled expressions agree between
  rdflib and Oxigraph); triple terms are native in Oxigraph, so `_graph_term`/`TT` handling (about 60 lines) would vanish.
  Estimated: `srl_eval.py` evaluation half (about 400 of 859 lines) rewritten; `srl.py` parse half unchanged.

---

## 4. WHAT DEPENDS on each layer if removed or replaced

| If you remove... | Features lost | Tests | KG | Docs and notebooks | Other code |
|---|---|---|---|---|---|
| `salg/` package only | structure shapes for algebra graphs; `find_unbound_projected_variables`; the engine's `noUnboundProjectedVariables` extension; `meta_shapes` structure check for `sh:select` | `tests/sparql` 15 files; outside: `test_meta_shapes_extensions`, `test_salg_components`, `test_skos_shapes`, `test_starontology`; ~400 defs (upper bound) | none | 13 md, 3 notebooks; `docs/generated` API reference bucket | 2 call sites; 4 Turtle/ontology registry entries in `starontology/__init__.py` |
| salg encoder (`to_rdf`/`from_rdf`/`vocab`) | the query-compile step; `query_to_rdf` family; sqe's expression encoding; srl's use of `_decode`; sqe execution | 26 files, ~300 defs plus sqe and srl suites | `sqe_tree_to_query` (run) | notebook `05b` | `lower_rdf11.py`, `graph/query/{sparql_api,query_cache}` |
| `sqe/` + spexpr helpers | query-as-RDF editing, text round trip, field validation, KG library, srl's expression RDF encoding and validation | 16 sqe files (~144 defs) + `sqe_coverage` (7 files, opt-in) + 7 spexpr files (~174) | all 24 named queries (1,633-line library), `queries.py` (496), `build_kg.py`, `build_query_catalogue.py`, `docs/generated/query-library.generated.md` | `05b`, `appendix-b1`, `05c`, `03b` and 9 notebooks mention srl/sqe | srl: `srl.py:147-149`, `srl_validate` (lines 985-1006) |
| `srl*` | rules language | 25 files, ~253 defs, `srl_conformance` (7 files) | none | `03b` (46 cells), `05c` (19), 23 md | `starlayer/__init__.py` docstring only |
| `ssyn`/`sast` files | nothing user-visible | 4 files, 53 defs | none | none found | none |
| rdflib's parser (not a layer) | everything above, plus `graph/` query path, `shacl_engine/sparql_support.check_query`, `shacl/meta_shapes`, `tools/kg run_sparql` | most of the 514 parse12 defs | all | all | |

### 4.1 The SHACL engine's SPARQL handling (`shacl_engine/`)

`shacl_engine/sparql_support.py` is 389 lines. Parts that touch rdflib's parser/algebra:
- `_prepare` (line 89) = `prepareQuery` from `graph/query/sparql_api.py` (lines 110-117: parse12 + lower + salg round trip), cached
  by `lru_cache`, 512 entries.
- `_walk` / `check_query` (lines 95-143, about 50 lines) walk `query.algebra` for `CompValue` nodes named `Minus`,
  `ServiceGraphPattern`, `values`, `Extend` and read `PV`. This is the only place the engine needs a *parsed tree*.
  Everything else (`run_select`, `run_ask`, `violations_from_solutions`, `path_to_sparql`, `fill_template`,
  `eval_node_expression`) works on text and rows.
- Execution already has an Oxigraph route: `OxigraphGraph.sparql_query` (`shacl_engine/oxigraph_view.py:222`) runs text natively
  with `substitutions`, and falls back to `starlayer_sparql_query` on `RuntimeError` (the substituted variable must be projected).
  The engine design (`docs/working/shacl-engine-design.md`) says "no rdflib object model inside the engine core".
- `shacl_engine/sparql_support.py` imports `CompValue` and `rdflib.plugins.sparql.operators`/`SPARQLError` (lines 20, 169-173) for
  custom SHACL functions registered into rdflib's global registry (`_shacl_functions`); that part is rdflib-evaluator coupling.
- So the engine needs from the SPARQL layers: **a parser that returns a walkable tree** (50 lines of `check_query`) and, for
  the rdflib route, the compile step. Under option (a) it keeps working unchanged.

---

## 5. OPTIONS for an Oxigraph-baseline world

All estimates are mine, from the line counts above; marked "(est)". No spike run.

### (a) rdflib only as SPARQL parser/algebra library; Oxigraph executes text

- **What it means**: keep `_grammar12`, `parse12`, `_syntax_checks`, `triple_term`, and rdflib's `parser.py` (1,567) +
  `algebra.py` (1,688) + `parserutils.py` (313) for parsing and inspecting. Execution = send the *original text* (with the
  prologue/`initNs` prepended) to `pyoxigraph.Store.query`. No lowering, no custom `tt:` functions, no evaluator. The text-regeneration
  question: regeneration is not needed for execution; it is needed only where the text is produced from a tree (sqe -> text,
  already rdflib-free in structure).
- **Evidence this path exists in part**: `serialize12.py` (algebra -> 1.2 text) is used in production nowhere in `starlayer/`
  (only `sqe` imports its `_dirlang_n3` helper); it is test infrastructure (`test_w3c_sparql12_oxigraph_roundtrip.py`: run original and
  regenerated text on Oxigraph, compare), and sqe's own text path is separately Oxigraph-tested. Production remote-store
  serialization uses `_AlgebraTranslator11` over the *lowered* algebra (`graph/graph/starlayer_graph.py:2626`).
- **Stays**: all four layers' features, the KG library, SRL parse, sqe, validation, `check_query`, W3C syntax tests.
- **Lost**: nothing from layers. Retires (est): `lower_rdf11.py` 1,971, most of `serialize12.py` 542 (keep `_dirlang_n3`), the encode/decode
  compile step (~15 lines of glue), parts of `graph/query/` patches (not sized here; `graph` inventory 4,983 lines under `query/`).
  SRL and `sqe_tree_to_query` still run in rdflib unless converted (S3, S1).
- **Effort (est)**: wiring is small (tens of lines per call site); the work is semantic validation: rdflib vs Oxigraph builtin
  differences (6 of 40 sampled differ), `substitutions` projection rule, per-call custom functions, and the 7 xfail W3C fixtures.
- **Risk**: rdflib stays a hard dependency (pyparsing grammar, import-order rule, global mutation). The patches applied by
  `import starlayer.graph` ("all 35 patches ... as a side effect") would no longer be needed by the parse path, but the
  grammar mutation remains. Every algebra-dependent feature depends on rdflib's algebra staying stable (pinned `rdflib==7.6.0` in `uv.lock`).

### (b) StarLayer-owned tree instead of rdflib's algebra

- **What sqe already gives**: a flat, editable tree with shapes and a text renderer; but it is produced from rdflib's
  parse tree and its decode needs `translateQuery`. It covers SELECT/ASK/CONSTRUCT, not DESCRIBE or Update.
- **How much of the parser is needed**: the splice is `_grammar12.py` 932 lines on top of rdflib's 1,567-line `parser.py` and
  313-line `parserutils.py`, about 2.8k lines of pyparsing in total, plus `algebra.py` 1,688 if resolved algebra is kept. A
  sqe-style IR needs no `translateQuery` for text round trip or editing, only for execution in rdflib (which option (a)
  removes).
- **Standalone SPARQL 1.2 parser in Python (est, unverified)**: a hand-written lexer and recursive-descent parser for the
  full query + update grammar with 1.2 additions is of the order of 1.5k-2.5k lines, plus an AST (or reuse sqe's vocabulary), with the
  pinned W3C 1.2 syntax suite (positive and negative) as oracle. It would drop the rdflib global-grammar problem and
  `CompValue`, but takes sqe's `to_rdf` (523) and srl's grammar (about 330 lines of pyparsing, lines 204-314 of `srl.py`) with it.
- **`spargebra` (Rust)**: Oxigraph's parser crate, ships inside pyoxigraph, but pyoxigraph exposes no parse or algebra
  (`docs/working/oxigraph-capability-matrix.md` section 4: "Parsed algebra tree / EXPLAIN: no"; `QuerySolutions` has only
  `serialize` and `variables`). Exposing it would be a separate PyO3 wheel (est 300-600 lines Rust/Python plus CI for platform
  wheels; unverified, and I did not check spargebra's 1.2 coverage or whether its structures keep prefixes and
  original spellings; its output is the spec algebra, closer to salg than to sqe's raw tree).
- **Risk**: sqe's value is the raw-tree fidelity (prefixes, order), which a resolved algebra would lose. A new parser has to
  re-earn the existing 7 xfail fixtures and the `sqe_known_gaps` set. Largest line-count and test churn of the options.

### (c) Give up sqe/spexpr

- **What breaks**: KG library (24 queries; 1,633 lines Turtle; `queries.py` 3 import sites; `build_kg.py`, `build_query_catalogue.py`,
  `docs/generated/query-library.generated.md`, `tests/kg/unit/test_queries.py`); SRL (`srl.py:147-149`, `srl_validate`, its RDF
  tree of expressions, `srl:` shapes referencing `spexpr`/`sqe` shapes via `starontology` loaders, `srl_conformance` and 25 srl
  test files); `salg/` validation (`expr_validation`, `expr_families`) which shares spexpr; 4 Turtle files (1,630 lines); 4+ notebooks;
  `sqe_coverage` suites and the sqe Oxigraph differential test.
- **Does not break**: the 1.2 parser/lowering (not in sqe), shacl_engine.
- **Minimal replacement that keeps KG + SRL working (est)**: (i) KG: store each named query as text (`sh:select`-style
  literal) plus parameter metadata; run with `prepare_query_12` + Oxigraph. Loses structured editing and the sqe shapes; the
  library file is regenerated once from `sqe_tree_to_text`. About 300 lines in `queries.py` and `build_*` scripts. (ii) SRL:
  needs its own expression encoding (replace `sqe.expr_text`/`_encode_expr`/`sqe.vocab`, about 400 lines of sqe reused by
  srl.py) or store expressions as text. Total est: 700-1,200 lines changed plus deleting about 4,000 lines (sqe 1,692 +
  spexpr helpers 227 + their Turtle 2,300 minus whatever srl keeps).
- **Risk/gain**: gives up the one layer that already renders text without rdflib; the gain is only fewer lines to maintain.
  rdflib's grammar remains needed for srl and `check_query`.

### (d) Other findings

1. **The compile step does real work, but it goes away with lowering.** `rdf11_to_query` says it "promotes `Function` nodes to
   real evaluable `Expr`s" and recomputes `_vars`/`lazy` (`lower_rdf11.py:1795-1800`). So replacing it inside the rdflib route
   needs care. Under Oxigraph execution it is moot (S2).
2. **Orphan layers**: `ssyn`/`sast` (6 files, 946 lines, 53 test defs) are imported by nothing in `starlayer/`; candidates to
   retire regardless of the Oxigraph decision (S5).
3. **`check_query` is the sole tree consumer in the SHACL engine** (50 lines). If a standalone parser or Oxigraph error
   messages replace rdflib there, it needs a tiny scope-aware walk, not the algebra.
4. **Update**: sqe, salg-encoder and `serialize12` do not render Update to text ("this project doesn't attempt to serialize
   Update algebra back to text", `serialize12.py` docstring). Oxigraph would execute original Update text; no layer
   needs to produce it.
5. **Documentation is partly stale**: `sparql/CLAUDE.md` has `starsparql/` file-map paths and a "Not implemented" line on ASK/DESCRIBE
   text that conflicts with later entries; trust the code. Its "Remainders of #93" calls patching rdflib something "this repo is
   removing", which matches the Oxigraph direction (unverified how far that has gone).
6. **Lowering solves a problem Oxigraph does not have**: triple terms, `isTRIPLE`, annotations, `LANGDIR` and `{| |}` in Update
   are native in Oxigraph (capability matrix section 4). So `lower_rdf11`'s 1,971 lines and `tt:` custom functions
   (`graph/query/custom_functions.py`) are the cost of the rdflib route only.

---

## 6. Suggested spikes (no decision)

| # | Question | Method | Size (est) | Verifies |
|---|---|---|---|---|
| S1 | Can the KG query library run on Oxigraph? | `sqe_tree_to_text` for each of the 24 named queries, load the KG into a `pyoxigraph.Store`, run, compare rows with `sqe_tree_to_query` on rdflib; try parameters via `substitutions` and via `VALUES` | 1 day | whether sqe survives as editor+text-renderer with Oxigraph execution (option (a)/(c)) |
| S2 | What breaks if the salg round trip leaves `prepareQuery`? | Replace `query_to_rdf11`/`rdf11_to_query` by building `Query(prologue, lowered)` directly plus `_addVars`/`analyse`, run `tests/sparql` and `tests/graph` | 1 day | the real role of the compile step; whether `to_rdf`/`from_rdf` can become a pure persistence layer |
| S3 | SRL bodies in Oxigraph | Translate one rule body to a SELECT, run `tests/sparql/srl_conformance` through an Oxigraph evaluator for stratified, `NOT DATA`, `NOW()` cases | 2-3 days | feasibility and semantic differences |
| S4 | Standalone parser or `spargebra` binding | (i) lexer + parser skeleton against the pinned W3C 1.2 syntax manifests, measure lines and pass rate; (ii) PyO3 binding exposing parse -> JSON, check 1.2 coverage and prefix retention | 3-5 days each | the line estimate in (b); whether the grammar splice can go |
| S5 | Retire `ssyn`/`sast` | Delete the six files and 4 tests, run the suite | hours | confirms they are orphans |
| S6 | Parse-only import profile | Import `starlayer.sparql` without `starlayer.graph` backends, check which patches (35) still apply and whether the grammar is safe | 1 day | the risk in option (a) |

## 7. Unverified list

- Whether `test_no_salg_terms_in_any_tree`, the Oxigraph differential suites and `sqe_known_gaps` currently pass (not run).
- The cost of the stratification and `NOW()` handling for SRL under Oxigraph.
- `spargebra`'s SPARQL 1.2 coverage and anything about wheel packaging.
- Sizes marked "(est)" for rewrites and new parsers.
- Test-def counts are per file mentioning the layer (upper bounds).
- The `rdflib` used for line counts of its `parser.py`/`algebra.py` is 7.6.0 from another venv in the checkout (`sparqModel/.venv`); the lock pins 7.6.0.
