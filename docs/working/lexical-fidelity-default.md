# Lexical fidelity as the parse default (Stage 0.4a)

Branch `mig-stage0`, 2026-10-31. Decision (owner, migration plan section 5 item 6): in StarLayer the format name `turtle` means Turtle 1.2 and is the
faithful parser; `turtle12` stays as an alias.

## What each format did before, and does now

Probe: one document per syntax with `"04"^^xsd:integer`, `"1"^^xsd:boolean`, `"none"^^xsd:boolean`, `"4.0"^^xsd:decimal`,
`"+1.50"^^xsd:double`, `"2020-01-01T00:00:00Z"^^xsd:dateTime`, read back from a `StarLayerGraph` and a `StarLayerDataset`.

| Format name | Parser before | Lexical forms before | Now |
| --- | --- | --- | --- |
| `turtle`, `ttl`, `text/turtle` | rdflib | normalised ("04" to "4", "1" to "true", "none" to "false", "+1.50" to "1.5", dateTime to "+00:00") | `turtle12` parser, faithful |
| `turtle12`, `n3`, `n3-12` | StarLayer | faithful | unchanged |
| `nt`, `ntriples`, `application/n-triples` | rdflib | normalised | `nt12` parser |
| `nt12` | StarLayer | **normalised** (`Literal(value, datatype=...)` without `normalize=False`) | faithful (fixed) |
| `nquads`, `nq`, `application/n-quads` | rdflib (graph), `nq12` (dataset) | normalised | `nq12`, faithful after the `nt12` fix |
| `trig`, `application/trig` | rdflib (graph), `trig12` (dataset) | graph: normalised; dataset: faithful | `trig12`, faithful |
| `xml`, `application/rdf+xml` | rdflib | normalised | still rdflib's parser, lexical forms kept (see below) |
| `rdfxml12` | StarLayer preprocessing, then rdflib's parser | **normalised** | faithful (fixed) |
| `trix` | rdflib (graph) / `trix12` (dataset, being dropped) | normalised / not checked | unchanged; still rdflib for the graph |
| `json-ld`, `hext`, `rdfa`, `html` | rdflib | normalised | unchanged (not covered; rdflib's parsers) |
| `rdf-xml` | (not a registered rdflib name) | error | unchanged |

How the RDF/XML case was made faithful without touching rdflib's global `NORMALIZE_LITERALS`: rdflib's RDF/XML parser has no option, so
`parsers/faithful.py::faithful_rdfxml_literals` swaps the `Literal` name inside `rdflib.plugins.parsers.rdfxml` for a wrapper that passes
`normalize=False` only while a thread-local depth counter is above zero. Outside the `with` block, and on other threads, the wrapper is
exactly `Literal`. A test (`test_plain_rdflib_in_the_same_process_still_normalises`) checks plain rdflib still normalises afterwards.

Routing rules (`starlayer_graph.py::_faithful_parse_format`, used by `StarLayerGraph.parse` and `StarLayerDataset.parse`):
- A URL source or location is left to rdflib's fetcher (we do not fetch), so it still normalises. Documented in the docstring.
- `format=None` with an existing local file: the format is guessed from the extension with `rdflib.util.guess_format`, then routed.
- A document read by the plain `turtle`/`nt` name still adopts the RDF 1.2 basic encoding (`rdf:reifies` + `rdf:PropositionForm`)
  as real triple terms, as it did when rdflib parsed it (`_adopt_basic_encoding`). See test 1 below.

## Copy paths

- `add`, `addN`, `+ - & ^`, serialization round trips (`turtle12`, `nt12` writers then parse): none of them rebuilds a literal; the same
  `Literal` object is stored and written (`test_nothing_is_renormalised_on_copy_or_serialization_round_trip`).
- Query result restoration for native stores (`backends/native.py::_parse_json_term`, `backends/native_oxigraph.py`) built literals with
  rdflib's default normalisation; they now pass `normalize=False`, so a result is the engine's lexical form as given. (An Oxigraph store has
  already normalised on storage; this only stops a second rewrite for remote engines that do not.)
- Left alone on purpose: `model/encoding.py::canonicalize_query_result_value` and `canonicalize_numeric_literal` (a deliberate SPARQL-result
  canonical form for decimal and double, with their own tests), `custom_functions.py` (function results), `compare.py` (builds comparison keys).

## Tests whose expectations changed

Whole `graph`, `sparql` and `shacl` default tiers (`-m "<area> and not integration"`), baseline copy of the branch before Task B against the
branch after. The baseline was taken from a `git archive` of the commit before the change so edits could not leak into it.

| Tier | Before | After |
| --- | --- | --- |
| graph | 2556 passed, 1 failed (`test_timeout.py::test_grandchild_process_does_not_survive_the_timeout_kill`, a timing test that fails under machine load; passes in the after run), 159 skipped | 2555 passed, 2 failed (below, fixed afterwards), 159 skipped |
| sparql | 1501 passed, 171 skipped, 11 xfailed | 1501 passed, 171 skipped, 11 xfailed |
| shacl | SHACL_BASE | SHACL_AFTER |

Tests that depended on the old behaviour:

1. `tests/graph/unit/test_proposition_form_encoding.py::TestBasicEncodingExchange::test_parse_of_the_basic_encoding_gives_real_triple_terms`
   and `::test_a_nested_encoding_round_trips`. They parse a basic-encoding document with `format="turtle"` and expect real triple terms. That
   worked only because the rdflib path ended in `_adopt_basic_encoding()`; the `turtle12` path never did. **Behaviour kept, test unchanged:**
   the plain `turtle`/`nt` names adopt the basic encoding as before (the feature is the documented exchange format), so the code was changed,
   not the tests. `turtle12` itself still does not adopt; that is a separate question for the owner (the same document under `turtle12` gives
   encoding triples).
2. No test expected a normalised lexical form from a parse. Test files that parse numerics with `format="turtle"` (SHACL, SRL and sqe
   suites) did not change result.

New tests: `tests/graph/unit/test_parse_fidelity.py` (26: every routed name for a graph and a dataset, extension guess, rdflib untouched,
round trips, query results).

## Not done

- No change to rdflib's `NORMALIZE_LITERALS`.
- Formats still on rdflib and still normalising: `trix` (graph), `json-ld`, `hext`, `rdfa`, `html`, and any URL source.
- `xml` still goes through rdflib's RDF/XML parser, so it keeps rdflib's RDF/XML 1.1 behaviour apart from the literals; it does not get the
  RDF 1.2 additions (that is `rdfxml12`).
- An Oxigraph-backed graph still normalises on storage (starlayer #190; oxigraph#526, #1989, PR #2010); the engine now warns about it
  (`StarLayerFidelityWarning`, Stage 0.4b).
