"""Registry of W3C SHACL 1.2 suite entries with a known, reasoned disposition.

Per CLAUDE.md's testing-coverage discipline, a failing conformance test is
never silently skipped - every entry here names *why* (a specific
docs/shacl12-gap-matrix.md "Not Covered / Deferred" row, a specific
docs/upstream-issues/pyshacl-upstream-issues.md entry, or a concrete Working-Draft-churn
explanation) and is applied as ``pytest.xfail(strict=True)``, so it breaks
loudly (as an unexpected XPASS) the moment the underlying gap is closed
instead of silently going stale.

Review this file the same way the gap matrix's own tables are reviewed:
every entry is a claim that should still be true, not a historical record.

Keyed by ids.portable_id(entry, VENDOR_ROOT) - a path-relative id, *not*
str(entry.iri) (which is an absolute file:// path that differs across
machines/checkouts, unsuitable for a committed file). This is also the
pytest parametrize id, so a failing test's node id can be pasted directly
in as a key here.
"""

from __future__ import annotations

# The 4 starlayer.graph StarLayerTurtleParser bugs that used to block 13
# files here (bare numeric/boolean literals, mid-line comments, blank-node
# RDF-list members, publicID/base not threaded through) were fixed upstream
# 2026-07-30 - see docs/starlayergraph-upstream-change-log.md's now-"implemented"
# entries. All 13 previously-blocked files parse correctly now; two of them
# turned out to have real, independent findings once they could finally run
# (reifierShape-001/-002, property-sparqlExpr-001, all since fixed - see
# docs/shacl12-gap-matrix.md) - the rest pass cleanly.
#
# 5 confirmed plain-rdflib SPARQL-evaluation bugs (multiply-example,
# divide-example, ceil-example, floor-example, round-example, and 4
# rectangle-* sh:SPARQLRule fixtures depending on the same integer*integer
# arithmetic quirk) were fixed via import-time monkeypatches added to
# starlayer.graph itself 2026-08-01 - see
# docs/starlayergraph-upstream-change-log.md's "Fixed:" entries for
# MultiplicativeExpression type promotion and CEIL/FLOOR/ROUND/division
# decimal lexical-form canonicalization.
#
# subsetOf-002 (compound sequence-path comparison) and instancesOf-base-class
# (rdfs:subClassOf-aware shnex:instancesOf matching) were also fixed
# 2026-08-01 - sh:subsetOf now converts its comparison path via pySHACL's
# own shacl_path_to_sparql_path instead of requiring a simple IRI
# (native_components.py::_build_subset_of_component), and
# shnex:instancesOf now walks rdfs:subClassOf via the same
# _transitive_subclasses helper sh:ShapeClass's implicit-target discovery
# uses (node_expressions.py). Neither was structurally blocked - both were
# narrower "do the minimal thing" scoping choices from the original pass.
#
# seconds-example is the one remaining entry - a fixture-formatting
# expectation with no basis in SECONDS()'s own spec, left unpatched
# deliberately (see its own entry below for why).

# Entries that fail only because of an Oxigraph bug (minimal pyoxigraph reproduction and write-up: docs/working/oxigraph-upstream-issues.md,
# issue 1). They are strict xfails: the test runs, a failure is expected, and a pass (the bug fixed upstream) fails the run
# so the entry is removed. Applied to the stores that run queries on Oxigraph.
OXIGRAPH_ZERO_LENGTH_PATH = (
    "Oxigraph returns no solution for a zero-length property path (`*` or `?`) whose end is a constant that is not a node of "
    "the graph, e.g. `?p rdfs:subPropertyOf* rdfs:label`; SPARQL 1.1 (18.5, ZeroLengthPath) requires it to match the constant. "
    "The function body of this fixture runs exactly that query, so the label count is 0 instead of 2. "
    "docs/working/oxigraph-upstream-issues.md, issue 1."
)
OXIGRAPH_QUERY_BUGS: dict[str, str] = {
    "tests/sparql/functions/langLabelCount-example::langLabelCount-example": OXIGRAPH_ZERO_LENGTH_PATH,
}

KNOWN_FAILURES: dict[str, str] = {
    "tests/sparql/scope-interactions/quoted-focus-optional/manifest::quoted-focus-optional": (
        "closure.py::node_closure copies the expected report into an rdflib Graph, which cannot hold a triple term (the focus node "
        "is `<<( ex:s ex:r ex:bad )>>`). A harness limit, not an engine one: test_w3c_engine_sparql passes this entry."
    ),
    "tests/node-expr/shnex-sparql/seconds::seconds-example": (
        "confirmed to be a fixture-formatting expectation with no basis in "
        "SECONDS()'s own specification, not a canonical-form bug: "
        "Builtin_SECONDS() constructs `Decimal(0)` for a zero-seconds "
        "dateTime, lexical form '0' - but this fixture's mf:result expects "
        "the zero-padded '00'. Note '0' is *not* actually XSD decimal's "
        "true canonical form either (that's '0.0' - a decimal point with a "
        "digit on each side, the same rule the 2026-08-01 "
        "MultiplicativeExpression/CEIL/FLOOR/ROUND fix in starlayer.graph "
        "enforces elsewhere - see docs/starlayergraph-upstream-change-log.md); "
        "SECONDS() simply hasn't been patched for that. But zero-padding to "
        "two digits ('00') isn't XSD canonicalization at all - it's "
        "ISO-8601-style time formatting the function's own spec doesn't "
        "require (SPARQL/XPath's SECONDS() returns a numeric xsd:decimal "
        "*value*, not a substring lifted from the input's own lexical "
        "form) - so this looks like a fixture-authoring artifact, not a "
        "genuine interoperability requirement. Corroborated empirically "
        "2026-08-01: checked SECONDS() against real Fuseki (Jena/ARQ) and "
        "Oxigraph instances too, not just rdflib - both independently "
        "produce '0', matching rdflib and disagreeing with the fixture, "
        "which is strong cross-engine evidence this is a fixture quirk, "
        "not a real interoperability requirement any engine implements. "
        "Left unpatched: even a correct canonical-form fix would produce "
        "'0.0', not '00'. Write-up for reporting upstream to w3c/data-shapes: "
        "docs/w3c-shacl12-test-suite-issues.md."
    ),
}



# Entries that fail on any Oxigraph-backed graph (every graph the engine and the public API use) because the store rewrites a literal
# on insert (starlayer #190; upstream oxigraph#526, #1989, PR #2010). STRICT xfails where they are used: they XPASS, and fail, once a
# pyoxigraph with the fix is installed, which is the signal to delete them.
STORE_NORMALIZATION: dict[str, str] = {
    "tests/core/node/in-004::in-004": '"4"^^xsd:byte (the focus node) is stored as "4"^^xsd:integer, the same term as the sh:in member 4: it conforms, and the fixture expects a violation',
    "tests/node-expr/shnex/intersection::intersection-termEquality": '"01"^^xsd:integer is stored as "1", the same term as 1: the intersection keeps it',
    "tests/node-expr/shnex/remove::remove-list-from-list": '"01"^^xsd:integer is stored as "1", so the list no longer holds a term to remove',
    "tests/node-expr/shnex/distinct::distinct-termEquality": '"04"^^xsd:integer is stored as "4", the same term as "4": distinct merges them',
    "tests/core/node/maxExclusive-001::maxExclusive-001": '"4.0"^^xsd:decimal is stored as "4"; the report echoes the value',
    "tests/core/node/minExclusive-001::minExclusive-001": '"4.0"^^xsd:decimal is stored as "4"; the report echoes the value',
    "tests/core/property/datatype-ill-formed::datatype-ill-formed": '"300"^^xsd:byte (out of range) is rewritten to "300"^^xsd:integer',
    "tests/core/property/uniqueLang-002::uniqueLang-002": '"1"^^xsd:boolean becomes "true", so sh:uniqueLang is wrongly activated',
}




# Engine gaps the 2026-11-11 suite re-sync found (docs/working/spec-delta-2026-11-11.md, phase 1). Each is applied as a strict xfail,
# so fixing one fails loudly until its entry is removed.
ENGINE_GAPS: dict[str, str] = {
    "tests/node-expr/shnex-sparql/abs::abs-single-argument-shorthand": "a list-parameter function takes a single argument without a list (`sparql:abs -42`): Node Expressions, ListParameterFunctions; shacl_engine/expressions.py demands an RDF list",
    "tests/node-expr/shnex-sparql/abs::abs-single-argument-expression": "the same shorthand with a node expression as the argument",
    "tests/node-expr/custom/listParameter::listParameter-single-argument-shorthand": "the same shorthand for a custom list-parameter function (`ex:twice 21`)",
    "tests/inference-rules/condition-shape-class-superclass::condition-shape-class-superclass": "a sh:condition that is a node shape and a class must also conform to the shapes of its superclasses; the engine checks only the shape itself",
    "tests/inference-rules/ruleProcessor-unknown-at-ruleset::ruleProcessor-unknown-at-ruleset": "an unknown sh:ruleProcessor named on a rule set must fail; only one on a rule does (rules.py)",
    "tests/inference-rules/SPARQLRuleTemplate-optional-param::SPARQLRuleTemplate-optional-param": "a rule template whose parameters are all optional is valid; the check that a component needs one non-optional parameter is for constraint components (components/sparql_components.py)",
}
