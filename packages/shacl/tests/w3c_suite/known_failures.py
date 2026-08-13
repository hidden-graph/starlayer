"""Registry of W3C SHACL 1.2 suite entries with a known, reasoned disposition.

Per CLAUDE.md's testing-coverage discipline, a failing conformance test is
never silently skipped - every entry here names *why* (a specific
docs/shacl12-gap-matrix.md "Not Covered / Deferred" row, a specific
docs/pyshacl-upstream-issues.md entry, or a concrete Working-Draft-churn
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

# The 4 starlayergraph StarLayerTurtleParser bugs that used to block 13
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
# starlayergraph itself 2026-08-01 - see
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

KNOWN_FAILURES: dict[str, str] = {
    "tests/node-expr/shnex-sparql/seconds::seconds-example": (
        "confirmed to be a fixture-formatting expectation with no basis in "
        "SECONDS()'s own specification, not a canonical-form bug: "
        "Builtin_SECONDS() constructs `Decimal(0)` for a zero-seconds "
        "dateTime, lexical form '0' - but this fixture's mf:result expects "
        "the zero-padded '00'. Note '0' is *not* actually XSD decimal's "
        "true canonical form either (that's '0.0' - a decimal point with a "
        "digit on each side, the same rule the 2026-08-01 "
        "MultiplicativeExpression/CEIL/FLOOR/ROUND fix in starlayergraph "
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
