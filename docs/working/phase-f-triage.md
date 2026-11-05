# Phase F triage of `non-spec-behaviour.md` (recommendations for the owner's decision)

Prepared 2026-11-05 on the `shacl-engine` line. These are recommendations only; the owner's rows in `non-spec-behaviour.md` are unchanged
(apart from the row 27 measurement correction). **address** = fix in StarLayer, or report upstream and track; **document** = keep and list on the
user-facing limits page. Effort: S under half a day, M one to three days, L more.

Owner decisions already made and applied below: Oxigraph literal normalisation (rows 1, 2) is accepted until upstream fixes it; `manchester_validate`
stays on owlrl through the rdflib bridge (rows 22, 32); both the old `main` line and this line ship; salg is retired (E4) and goes away.

Row numbers are those of the file (1 to 32). The task brief called REPLACE/REGEX, boolean ordering and negated property set "rows 6, 7, 8"; in the
file they are rows 5, 6, 7 (row 8 is COPY/ADD). Verification is in the next section.

## Summary

Address: 11 (rows 3, 4, 5, 6, 7, 9, 11, 27, 28, 29, 30). Document: 21 (all the others). Of the "address" rows, 5, 6, 7, 11 and 4 are upstream
reports (or waiting for a release) with the xfail kept; 3, 9, 27, 28, 29, 30 are small to medium work here. Rows 1, 2 and 22 are
"document now, revisit on a release" and are counted as document.

| # | Behaviour (short) | Rec. | Reason | Effort |
|---|---|---|---|---|
| 1 | Store normalises literal lexical forms | document | owner decision; upstream PR #2010 still open (see below); the `StarLayerFidelityWarning` already tells the user | S (limits page) |
| 2 | Derived numeric datatypes stored as `xsd:integer` | document | same cause as row 1; Manchester shapes already use the integer plus `sh:minInclusive 0` workaround; restore after the fix | S |
| 3 | Default graph from several graphs counts a triple once per graph | address | wrong answers (COUNT, bag results) for a query with its own `FROM g1 FROM g2`; report upstream, optionally skip the dedup copy for duplicate-insensitive queries | M |
| 4 | Zero-length path to a constant not in the data matches nothing | address | spec violation with a strict xfail; report upstream (small, clear repro); the rewrite already avoids it for entailment | S (report) |
| 5 | `REPLACE` / `REGEX` do not follow XPath rules | address | correct claim (verified); report upstream; only affects malformed or edge-case patterns, so keep the xfail and list on limits page until fixed | S (report) |
| 6 | `false < true` unbound | address | correct claim (verified); one-line operator gap, easy upstream report | S (report) |
| 7 | `!(p\|^q)` returns a set, spec says bag | address | correct but narrower than reality: every `p\|q` alternative is a set (verified), so report the wider bug | S (report) |
| 8 | `COPY` / `ADD` from an absent graph does not raise | document | not a deviation (spec MAY); document the empty-the-target warning | S |
| 9 | `FILTER EXISTS` with an inner FILTER on an outer variable is slow | address | rewrite already in; keep it on and file a planner report (semi-join) | S (report) |
| 10 | N-Triples `VERSION` directive rejected by the parser | document | wrapper fix stays (`ntversion.py`); nothing for users to know beyond "supported" | S |
| 11 | XMLLiteral canonicalisation keeps in-scope namespaces | address | pinned gap in a spec-defined canonical form; report upstream, accept meanwhile; only RDF/XML `parseType=Literal` users see it | S (report) |
| 12 | Language tags lowercased | document | spec allows case-insensitive comparison; not fixable here | S |
| 13 | `sameTerm("1"^^xsd:integer, "01"^^xsd:integer)` true | document | consequence of rows 1/2 | S |
| 14 | Integer constants beyond i64 unbound | document | engine limit, rare | S |
| 15 | Numeric formatting in results | document | implementation-defined | S |
| 16 | `SELECT *` column order alphabetical | document | deterministic; spec leaves it open in practice | S |
| 17 | Error types differ | document | not specified | S |
| 18 | Source blank-node labels lost on parse | document | labels are document-scoped; the move is deliberate | S |
| 19 | No Pyodide / pure-Python install | document | native wheels; hard platform limit | S |
| 20 | `LOAD <file://...>` not supported | document | optional in spec; `Store.load(path=...)` is the route | S |
| 21 | rdflib stores, `Resource`, prefix manager defaults, TriX gone | document | decided, belongs in the migration guide | S |
| 22 | No reasoner on Oxigraph; owlrl via an rdflib copy | document | owner decision; revisit when a Rust reasoner is chosen | S |
| 23 | `to_rdflib` triple terms are the basic encoding | document | non-normative interop encoding; decided | S |
| 24 | Plain `turtle` parse does not read the basic encoding | document | decided; point to `interop.from_basic` | S |
| 25 | `path=` graph cannot be pickled | document | decided | S |
| 26 | `VERSION` line written only when needed | document | decided; label is a hint | S |
| 27 | RDFC-1.0 canonicaliser has no guard against symmetric graphs | address | upstream report (a work limit); the local heuristic stays; corrected measurement: a long path is slow, not a hang | S (report) |
| 28 | (E1) sqe tree remnants | document (row rewritten) | `sqe_tree_to_query` and the rdflib encoder are gone (retired in E4; only a test comment mentions it), so that clause is moot; what remains is the opaque stand-in for ill-formed IRIs/tags and numeric-form drift on a text round trip. Rewrite the row to those two; document the numeric drift (follows from row 1) and keep the stand-in | S |
| 29 | `get_resource_iri()` returns `URIRef` or `NamedNode` by environment | resolved | already returns a `NamedNode` in every environment (E2); only the row text was stale | none |
| 30 | Manchester parse keeps literals as written, then the store normalises | document | not a defect: in RDF 1.1/1.2 a plain literal and `"x"^^xsd:string` are one term, so omitting `^^xsd:string` in the writer is correct | none |
| 31 | Manchester: relative IRI / space raises `ManchesterSyntaxError`; writer declares prefixes | document | stricter and correct; rdflib accepted garbage | S |
| 32 | `manchester_validate` needs rdflib; stale leniency list | document (the rdflib need); address the list | owner decision keeps owlrl; the stale two-input leniency list in `test_lenient_where_owlapi_is_lenient` is a test clean-up | S |

Counts: address 11 (3, 4, 5, 6, 7, 9, 11, 27, 28, 29, 30), document 21 (1, 2, 8, 10, 12 to 26, 31, 32). Row 32 is mixed and counted as document.

## Moot items (salg and the Update sub-select check)

salg and the rdflib tree encoder were retired in E4, and the owner's decision is that salg goes away. So:

- Row 28's clause "`sqe_tree_to_query` (an rdflib `Query`) needs rdflib" is moot: the function no longer exists in `packages/`.
- `handoff-next-steps.md`, "Decisions still open": "Update sub-select check for an unbound projected variable (a salg check) was not ported" is moot
  with salg. No row in `non-spec-behaviour.md` carries it, so there is nothing to disposition. I left that handoff line alone; delete it when the
  handoff is next edited.
- `docs/working/e1-notes.md` (lines 50, 51, 69) still describes `sqe_tree_to_query` as present; that file is a historical note and is left alone.

## Verification of rows 5, 6, 7 against the specs

Tested on pyoxigraph 0.5.13 (venv python, `-I`); scripts in the session scratchpad, not committed.

### Row 5: REPLACE / REGEX do not follow XPath rules. Claim is correct.

SPARQL 1.1 (https://www.w3.org/TR/sparql11-query/, 17.4.3.15): "The REPLACE function corresponds to the XPath fn:replace function." and for
REGEX (17.4.3.14): "Invokes the XPath fn:matches function ... The regular expression language is defined in XQuery 1.0 and XPath 2.0 Functions and Operators
section 7.6.1 Regular Expression Syntax". SPARQL 1.2 (https://www.w3.org/TR/sparql12-query/, Working Draft 1 November 2026) has the same wording.

F&O 3.1 (https://www.w3.org/TR/xpath-functions-31/, fn:replace): "A dynamic error is raised [err:FORX0003] if the pattern matches a zero-length
string, that is, if the expression fn:matches("", $pattern, $flags) returns true." and "In the absence of the q flag, a dynamic error is raised
[err:FORX0004] if the value of $replacement contains a dollar sign ($) character that is not immediately followed by a digit 0-9 and not immediately
preceded by a backslash (\)." An error in a SPARQL expression leaves the result unbound.

pyoxigraph 0.5.13: `REPLACE("abc","x*","-")` gives `"-a-b-c-"` (spec: error, `x*` matches the empty string); `REPLACE("abc","b","$")` gives
`"a$c"` (spec: FORX0004 error); `REGEX("a b","a\\b")` (regex `a\b`) gives true, but `\b` is not in the XSD regex language (FORX0002 expected);
`REGEX("a","\\p{IsBasicLatin}")` is an error (unbound) although `\p{IsBasicLatin}` is valid XSD regex syntax. `REPLACE("abc","(b)","$2")` gives
`"ac"`, which is correct (a reference to a missing group is replaced by the empty string). So every sub-claim in the row holds. Cause: Oxigraph uses
the Rust `regex` crate, not an XSD regex implementation.

### Row 6: `false < true` unbound. Claim is correct.

SPARQL 1.1 operator table (section 17.3): `A < B` on `xsd:boolean` x `xsd:boolean` maps to `op:boolean-less-than(A, B)`; same row in the 1.2 draft.
F&O 3.1 section 7.2: "op:boolean-less-than: Returns true if the first argument is false and the second is true." (The same section notes xs:boolean
itself is "not ordered", but the operator is defined and SPARQL maps to it.) pyoxigraph: `false < true` and `true < false` are both unbound (error);
`false < false` returns false (should be false, so fine); `ORDER BY` over booleans works (false, true). So only the `<` operator (and by the table `>`,
`<=`, `>=`) misses booleans; ORDER BY is unaffected. Not tested here: `>`, `<=`, `>=` on booleans (assumed the same gap; confirm before reporting).

### Row 7: `!(:p|^:q)` returns a set where the spec gives a bag. Claim is correct, and understated.

SPARQL 1.1 18.2.2.3 translation table: "!(:iri1|...|:irii|^:irii+1|...|^:irim) -> alt(NPS({:iri1 ...:irii}), inv(NPS({:irii+1, ..., :irim})))", and
18.5: "eval(Path(X, alt(P,Q), Y)) = Union(eval(Path(X, P, Y)), eval(Path(X, Q, Y)))  Informally, this is the same as: SELECT * { { X P Y } UNION { X Q Y } }".
UNION is a multiset union, so a pair reachable both ways appears twice. The 1.2 draft has the same text (`Alt(NPS(...), Inv(NPS(...)))`, `Union(...)`).

Test: graph `a r b . b r a`. `{?x !(p) ?y} UNION {?x !(^q) ?y}` gives 4 rows; `?x !(p|^q) ?y` gives 2. Wider finding: plain alternatives
are also collapsed: `?x r|r ?y` gives 2 rows (spec: 4) and `?x r|^r ?y` gives 2 (spec: 4). So the bug is "alternative paths deduplicate", not only
negated sets. Recommend the upstream report is retitled that way, and the test `test_negated_property_set_with_both_directions_is_a_bag` gains
an `r|r` case.

## Oxigraph PR #2010, issue #190, current release

Checked with `gh` and PyPI on 2026-11-05. "#190" is the StarLayer project note's label (`oxigraph-upstream-issues.md` section 3); in the Oxigraph
repository #190 is an unrelated merged 2022 pull request ("Adds a web build to Oxigraph JS"). The upstream issue is oxigraph/oxigraph #1989,
"Store changes literals with derived XSD datatypes (e.g. xsd:dateTimeStamp, xsd:nonNegativeInteger)", still open (updated 2026-10-28). PR #2010
("store keeps lexical forms", by fabio-rovai, opened 2026-10-28, `Fixes #1989`) is open, not draft, not merged, no review decision; last activity
2026-11-02. A maintainer (Tpt) commented with two reservations: non-canonical literals would no longer be stored inline (notably floats such as
`1.2`, since `1.2E0` is canonical), and the canonical serialisation must stay stable so storage is not broken. The CodSpeed bot reports a 6.55%
benchmark regression. So a fix is not imminent; the "accepted until upstream fixes it" decision stands. The latest pyoxigraph is 0.5.13 (PyPI
upload 2026-10-22, tag v0.5.13); earlier 0.5.12 (2026-10-18). The PR is not in 0.5.13. Recheck PR #2010 and the next release before shipping.

## Row 27 correction

Applied in `non-spec-behaviour.md` row 27, `e2-notes.md` section 2 and the matching "decisions still open" line in `handoff-next-steps.md`: a blank-node
path does not hang pyoxigraph 0.5.13. Measured here: path 500 nodes 4.0 s, 700 nodes 12.9 s, 1000 nodes 35.0 s (roughly cubic); cycle of 500 4.7 s;
8-clique 3.1 s (the earlier 13 s came from a machine about 4x slower). K(6,6) and a 6 x 6 torus were not re-measured. The upstream recommendation
(a work limit in Oxigraph's canonicaliser; RDFC-1.0 section 7.1 requires a defence) stands.
