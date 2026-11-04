# D2 gaps: what a migrated test needs that OxGraph does not have (2026-11-06)

A test blocked by one of these stayed on the old class (in a `*_oldclass.py` file, see `d2-delete-list.md`). No library code was
changed and no API was invented. Proposed fixes are for the owner to decide.

| # | Gap | Tests | Proposed |
|---|---|---|---|
| G1 | `shacl/ui_widget_selection.default_widget_score` does `float()` on a `pyoxigraph.Literal`: a configured `shui:defaultWidgetScore` is ignored (library bug) | 1 (`test_select_widgets_per_shape_oldclass`) | `float(value.value)` for pyoxigraph terms; then move the test back |
| G2 | `StarLayerGraphProtocol` / `MutableStarLayerGraphProtocol` require the rdflib attribute `namespace_manager`; `isinstance(OxGraph(), ...)` is False | 1 | redefine the protocols over `__iter__`, `prefixes`, `bind`, `add`, `remove` |
| G3 | RDF/XML writer: a character XML 1.0 cannot carry (U+0000, 0008, 000B, 000C, 001F) is written without error (old writer raised `ValueError`) | 5 | check literal values in `serialize(format="rdfxml")`, raise `ValueError` |
| G4 | `bind("xml"/"xmlns")` then `serialize(format="rdfxml")` raises `SyntaxError` from Oxigraph | 2 | drop those prefixes from the dict handed to Oxigraph for RDF/XML |
| G5 | UTF-8 BOM in bytes given to `parse` (N-Triples) is a `SyntaxError` | 1 | strip a leading BOM in `_read_input` |
| G6 | `query(x)` / `update(x)` with a non-string raise `NotImplementedError`, not `TypeError` naming the type | 12 | `TypeError` for non-str in `_Base.query` / `update` |
| G7 | `serialize(format="json-ld")` of a triple term raises `OSError` (Oxigraph has no RDF 1.2 JSON-LD) | 2 | go through `rdf_version="1.1"` (basic encoding) when the data has a triple term |
| G8 | `functions in graph/setops.py` (`union`, `intersection`, ...) reject an `OxGraph` / `OxDataset` operand; only `+ - & ^ +=` work | migrated test uses the operators | accept OxGraph / OxDataset in `setops._family` |
| G9 | `serialize12._translate_algebra_12` writes a ground triple term in a body pattern as `TRIPLE(...)`, which Oxigraph rejects | 1 (`test_execution_roundtrip_via_starlayergraph`) | emit `<<( s p o )>>` in patterns, keep `TRIPLE()` for expressions |
| G10 | `sparql/sqe_coverage/test_sqe_features.py`, `test_sqe_property_based.py`, `test_parser_differential.py` (opt-in) run a prepared rdflib `Query` from `sqe_tree_to_query` on data with triple terms; `OxGraph.query` takes text only and G9 blocks the text route | 3 files, about 40 tests | fix G9, then drop the decoded-Query variant (owner decision: weaker test) or run the decoded query through the fixed serializer |
| G11 | alias `n3-12` is not a format name | 1 | add to `formats.py` or drop |

Oxigraph limits (upstream, no wrapper fix; not yet in `oxigraph-upstream-issues.md`): the Turtle parser rejects `~ []` (ANON reifier);
the TriG parser creates no graph for `GRAPH <g> { }`, and its writer omits empty graphs; the RDF/XML parser reads
`rdf:parseType="Triple"` as an empty graph without error. By design (term policy): a blank-node label that is not a valid Oxigraph id raises
`TermError`.

# Behaviour decisions made while migrating

1. Results are pyoxigraph terms; tests compare `.value`, pyoxigraph terms, or read through `from_engine` / `to_rdflib()` (derive_shape,
   infer oracles). `str()` of a triple term is the full-IRI form.
2. `OxDataset()` defaults to `default_union=True`; tests written for the old non-union default pass `default_union=False`.
3. A graph view refuses a document with named graphs (`ValueError`, graph unchanged); tests that need graph names parse into an `OxDataset`.
   `serialize(destination=...)` returns `None`.
4. Oxigraph's TriG writer writes `<g> {`, no `GRAPH` keyword; N-Triples writes an `xsd:string` literal plain (the "datatype spelled out"
   assertion was dropped for that reason); a bound `xsd` is not "used" because the writer does not abbreviate datatype IRIs.
5. Lexical forms (O1): `test_parse_fidelity` asserts canonical forms (04 -> 4, "1" boolean -> true, 4.0 decimal -> 4, +1.50 double -> 1.5);
   an ill-formed boolean and a dateTime are kept as written. W3C op-2 and `IN (1)` compare store forms. The harness helper `_stored_form` maps only decimal and double.
6. Errors: parse and update syntax errors, STRLANGDIR arity, INSERT / DELETE DATA with variables or blank nodes are `SyntaxError`;
   illegal subject / predicate is `TypeError`.
7. `TRIPLE(s,p,o)` in a triple pattern or template is not SPARQL 1.2: rewritten as `BIND(TRIPLE(..) AS ?t)` + `?t`.
8. DELETE DATA of a reification triple: the old test asserted the encoding triples survive; now it asserts only the named triple goes and
   the other statements stay (intent changed; owner to confirm). COPY / ADD of a missing graph is no longer asserted to raise (B6 withdrawn);
   MOVE SILENT of a missing graph empties the target.
9. CONSTRUCT results compare with `starlayer.graph.isomorphic`; SELECT results by a consistent blank-node relabelling.
10. `reduce_prefixes` became a local helper (copy, `used_prefixes`, `unbind`); `isomorphic` is `starlayer.graph.isomorphic`; `longturtle12` dropped from parametrisations.
11. B4 (`false < true`) and B5 (`!(:p|^:q)` bag, zero-length path to an absent constant) are strict xfails with the reason, nothing else in those tests changed.
12. SHACL: `rd()` in `tests/shacl/integration/_rdflib_view.py` returns `RdflibView`, a plain `rdflib.Graph` subclass that can hold triple terms (not
    the old class). `w3c_shacl12/manifest.py` parses with `pyoxigraph.parse` into rdflib terms keeping lexical forms (the mechanical rename had silently
    skipped every W3C SHACL entry; only the parse-health test failed). Where a test asserts with rdflib vocabulary on a plain rdflib graph, a plain `rdflib.Graph` is used.
13. Two root tests keep the old names on purpose: `test_d1_readiness.py` (the scanner's own constants) and `test_reexports.py` (the public name D1 keeps).
    `tests/test_d1_readiness.py` scans library modules only, so no migration removed an importer; `ALLOWED` and `d1-readiness.md` are unchanged.
