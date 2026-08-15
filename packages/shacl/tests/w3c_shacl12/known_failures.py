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
    "tests/sparql/functions/instanceCount-example::instanceCount-example": (
        "Confirmed 2026-08-15: not the 'a few more predefined sparql: "
        "namespace functions' gap it first looked like - this and its two "
        "sibling fixtures (langLabelCount-example, spacedConcat-example) "
        "all define a shapes-graph node typed sh:ListParameterExpressionFunction "
        "with its own sh:bodyExpression (a node expression or sh:select/"
        "sh:sparqlExpr) and sh:parameter list, then call it as an ordinary "
        "SPARQL function by name from sh:select query text (e.g. "
        "`ex:instanceCount(ex:Name)`). This is SHACL 1.2 SPARQL Extensions' "
        "new *user-definable custom SPARQL function* mechanism - functions "
        "declared and registered dynamically per shapes graph, evaluated "
        "via a node-expression body - not a fixed set of built-ins this "
        "codebase's starshacl/sparql_node_expressions.py (~74 predefined "
        "sparql: functions) could just add three more entries to. Building "
        "this needs: recognizing sh:ListParameterExpressionFunction-typed "
        "shapes-graph nodes, registering each as a real rdflib SPARQL "
        "custom function (the same registration mechanism "
        "sparql_node_expressions.py itself uses for its ~74 built-ins - "
        "see that module for the pattern, but the function *set* would need "
        "to come from parsing the shapes graph, not a fixed Python table), "
        "and evaluating each call by running the declared sh:bodyExpression "
        "with the call's actual arguments bound to sh:parameter's declared "
        "names. A real, substantial feature - out of scope for the 2026-08-15 "
        "SHACL 1.2 spec-drift sync pass; see docs/shacl12-gap-matrix.md's "
        "sh:layer/sh:runOnce/sh:sourceRule/sh:expectedPredicate/"
        "sh:tempTriple rows (all closed in the same pass) for what that "
        "pass did cover."
    ),
    "tests/sparql/functions/langLabelCount-example::langLabelCount-example": (
        "Same sh:ListParameterExpressionFunction gap as instanceCount-example "
        "above - see that entry for the full reasoning."
    ),
    "tests/sparql/functions/spacedConcat-example::spacedConcat-example": (
        "Same sh:ListParameterExpressionFunction gap as instanceCount-example "
        "above - see that entry for the full reasoning."
    ),
    "tests/sparql/rules/run-once-example::run-once-example": (
        "Confirmed real architectural gap, not a small patch - 2026-08-15. "
        "This fixture's ex:RunBeforeRule (a global, sh:runOnce rule with an "
        "empty WHERE clause) CONSTRUCTs the ex:Person instances that "
        "ex:IteratingRule/ex:RunAfterRule (shape-attached to ex:Person, "
        "itself only sh:ShapeClass-typed - see the sh:NodeShape-typing fix "
        "added alongside this entry for why that part now loads at all) "
        "need as their own *implicit-class* targets. "
        "StarShaclValidator._augment_shapes_with_new_target_types computes "
        "implicit-class-target sh:targetNode triples exactly once, early in "
        "validate()'s pipeline, well before pySHACL's own advanced['rules'] "
        "stage runs any rule at all - so it only sees whatever ex:Person "
        "instances existed *before* RunBeforeRule ever executes (none). "
        "Confirmed directly: after apply_rules(), the four ex:Person "
        "instances genuinely exist in the output data graph (RunBeforeRule "
        "did fire), but zero ex:offspring triples exist anywhere - "
        "IteratingRule/RunAfterRule never fired, because pySHACL's own "
        "target resolution for ex:Person read only the (empty, stale) "
        "injected sh:targetNode set. Fixing this needs implicit-class "
        "targets to be recomputed dynamically as rule execution proceeds "
        "(interleaved with the rule loop itself, not a one-time pre-pass) - "
        "a real design/architecture change to how "
        "_augment_shapes_with_new_target_types integrates with rule "
        "execution, out of scope for the current pass. See "
        "docs/shacl12-gap-matrix.md's sh:runOnce row for the tracked status."
    ),
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
