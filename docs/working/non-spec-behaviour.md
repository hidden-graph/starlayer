# Non-spec and non-fidelity behaviour after the move to Oxigraph (running list)

Started 2026-11-06. Owner decision: fidelity to how the old rdflib-based StarLayerGraph behaved is not a goal. When the migration
is complete, this list is summarised and each item is either **addressed** (a fix in StarLayer, or upstream) or **documented** as a
known limit. Nothing here is posted to any outside forum. Add items as they are found; say where each comes from.

| # | Behaviour | Spec says | Source | Today | Disposition (decide at the end) |
|---|---|---|---|---|---|
| 1 | Store rewrites literals on insert: `+1.50` double to `1.5`, `04` to `4`, `"1"^^xsd:boolean` to `true`, decimal `4.0` to `4` | RDF 1.2 Concepts: a literal's lexical form is part of the term | oxigraph-upstream-issues.md section 3; issue #190, PR #2010 pending | accepted; `StarLayerFidelityWarning` when a constraint depends on the form | revisit when a release has the fix (check #2010 status) |
| 2 | Derived numeric datatypes stored as `xsd:integer` | the datatype is part of the term | same | Manchester shapes use `xsd:integer` plus `sh:minInclusive 0` | restore `xsd:nonNegativeInteger` after the fix |
| 3 | A default graph built from several graphs counts a triple once per graph | several `FROM` graphs form the RDF merge, a set (SPARQL 1.1, 13.2) | upstream-issues section 5 | wrapper keeps a deduplicated copy for `default_union` datasets; a query with its own `FROM g1 FROM g2` still double-counts; the SHACL engine's own union view counts a repeated triple once (tested for `sh:maxCount`) | decide whether to report upstream; consider query-shape check (skip the copy for duplicate-insensitive queries) |
| 4 | Zero-length property path to a constant not in the data matches nothing | a zero-length path always matches the constant | upstream-issues section 1 | strict xfail in the W3C suite; the entailment rewrite avoids `*` on constants | report or wait for upstream |
| 5 | `REPLACE` / `REGEX` do not follow the XPath rules (`REPLACE('abc','x*','-')` gives `-a-b-c-`; invalid `$` replacement accepted) | F&O: error | b1-classification.md class B3; upstream-issues section 6 | strict xfail `test_replace_and_regex_follow_xpath` (`tests/graph/oxgraph/test_oxigraph_deviations.py`); also `\b` accepted, `\p{Is...}` rejected | decide at the end |
| 6 | `false < true` unbound | boolean ordering is defined | b1-classification.md B4; upstream-issues section 7 | strict xfail `test_boolean_ordering_false_before_true` | decide at the end |
| 7 | `!(:p\|^:q)` (forward and inverse members) returns a set where the spec gives a bag | bag semantics (18.2: a UNION) | b1-classification.md B5; upstream-issues section 8 | strict xfail `test_negated_property_set_with_both_directions_is_a_bag` | decide at the end |
| 8 | `COPY` / `ADD` from an absent graph does not raise without `SILENT` | error | b1-classification.md B6; upstream-issues section 9 | strict xfail `test_copy_and_add_of_an_absent_graph_fail_without_silent`; an unchecked `COPY` from a mistyped name empties the target | decide at the end |
| 9 | `FILTER EXISTS` with an inner FILTER on an outer variable is evaluated per outer row (6x to 400x slower) | performance, not semantics | upstream-issues section 2 | sqe-tree rewrite on by default (`STARLAYER_EXISTS_REWRITE=0` to turn off) | keep the rewrite; maybe report |
| 10 | N-Triples / N-Quads `VERSION` directive rejected | RDF 1.2 syntax | phase-c-parser-measurement.md | handled in the wrapper (`oxgraph/ntversion.py`) | wrapper fix stays |
| 11 | XMLLiteral canonicalisation keeps in-scope namespaces | exclusive canonical form | upstream-issues section 4 | pinned known gaps | report or accept |
| 12 | Language tags lowercased (`EN-us` to `en-us`) | tags compare case-insensitively; the written form may be kept | graph-oxigraph-migration-plan.md section 4 | accepted | document |
| 13 | `sameTerm("1"^^xsd:integer, "01"^^xsd:integer)` true | false | same | accepted | document |
| 14 | Integer constants beyond i64 are unbound | unbounded integers | oxgraph-wrapper.md | accepted | document |
| 15 | Numeric formatting in results: `1/3` has 18 digits, `xsd:decimal(3)` is `3` | implementation-defined | oxgraph-wrapper.md | accepted | document |
| 16 | `SELECT *` column order is alphabetical | order of appearance | oxgraph-wrapper.md | accepted (deterministic) | document |
| 17 | Error types: `SyntaxError` with a position, `TypeError`/`ValueError` | not specified | oxgraph-wrapper.md, b1-classification.md O5 | accepted | document |
| 18 | Blank-node labels from the source are lost on parse | labels are scoped to a document | b1-classification.md | accepted | document |
| 19 | Browser/Pyodide deployment and a pure-Python install are not possible (native wheels) | - | migration plan section 4 | accepted | document |
| 20 | `LOAD <file://...>` in UPDATE not supported | optional | migration plan section 4 | use `Store.load(path=...)` | document |
| 21 | rdflib stores, `Resource`, the prefix manager with 29 default bindings, TriX are gone | - | migration plan section 4 | decided | document |
| 22 | Oxigraph has no reasoner; OWL-RL runs through `owlrl` on an rdflib copy, RDFS by query rewrite | - | inference-on-oxigraph.md | decided (2026-11-05): keep owlrl; Rust reasoner later | revisit |
| 23 | RDF 1.2 triple terms handed to plain rdflib (`to_rdflib`) are the basic encoding (`rdf:PropositionForm` blank nodes) and directional literals a datatype IRI; `from_rdflib` restores the literals, not the triple terms | RDF 1.2 Interoperability (draft, non-normative): the encoding is not semantically equivalent | oxgraph-wrapper.md | decided (2026-11-06) | document |
| 24 | A plain `turtle` parse does not read the basic encoding as triple terms (`interop.from_basic` does) | the encoding is ordinary RDF 1.1 triples | b1-classification.md O4 | decided (2026-11-06) | document |
| 25 | A graph opened with `path=` cannot be pickled (`TypeError`); `copy.copy` / `deepcopy` of it is an in-memory copy | - | oxgraph-wrapper.md | decided (2026-11-06) | document |
| 26 | The `VERSION "1.2"` line is written only when the data uses a 1.2 feature or `rdf_version="1.2"` is given; a document's own label is never checked (`RDF12ConformanceWarning` dropped) | the label is a hint (RDF 1.2 Concepts 2.1) | oxgraph-wrapper.md | decided (2026-11-06) | document |

## Process

1. Keep adding rows while the migration proceeds (D1 to D4).
2. After D4, summarise: for each row choose **address** (fix here, report upstream, or wait for a release) or **document** (user guide).
3. Record the result next to each row and link from the user-facing limits page.
