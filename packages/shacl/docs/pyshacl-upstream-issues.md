# pySHACL Upstream Issues

*Last reviewed: 2026-07-27*

Bugs found in `pyshacl` (https://github.com/RDFLib/pySHACL) while using it as a SHACL validation engine. Every reproduction below uses only plain `rdflib` and `pyshacl` - no third-party wrapper or extension is involved, so each is reproducible standalone against a stock pySHACL install. All 4 entries below were re-run on 2026-07-20 against pySHACL installed directly from the `RDFLib/pySHACL` GitHub repository's default branch tip (commit `9eeb9bf`) - at that time identical to the `v0.40.0` release tag (zero commits past it), so this confirms the bugs as of the latest available code, not just the last tagged release.

## Status Summary

**Issues 1 and 5** are planned to be reported upstream - each a clean, unambiguous, genuinely-worth-fixing bug (confirmed no existing GitHub issue/PR matches either, via both a tracker keyword search and a full-history `git log` search of the pySHACL repo). The other three are not being reported, each for a different, specific reason - see each entry's own `### Status` section for the reasoning and exactly how (or how much) it's handled independently in `starshacl`, the project this investigation was originally done for:

| # | Issue | Reporting upstream? | Handled in starshacl? |
| --- | --- | --- | --- |
| 1 | `sh:intersection` silently evaluates empty | **Yes** | **Fixed upstream in v0.40.1**; `starshacl`'s workaround (`_inject_intersection_list_triples`) has been removed |
| 2 | `ValidationFailure` returned as `report_graph` instead of raised | No - low severity, easy caller-side guard | Yes, fully (re-raised instead of returned) |
| 3 | Malformed `sh:closed` value crashes or is silently misinterpreted | No - see below | Yes, fully (as of 2026-07-20, see below) |
| 4 | `sh:filterShape` crashes | No - dead code, see below | Yes, fully (`_patch_shape_validate_for_filter_shape`) |
| 5 | `RdfLibDataGraph.clone()` drops a caller `Graph` subclass's identity/state under `advanced=True` | **Yes** (not yet filed) | Yes, fully (`_patch_rdflib_data_graph_clone_preserves_tt_adapter`) |
| 6 | `sh:sparql`'s own constraint node ignores its own `sh:severity` | Pending triage | Yes, fully (`_build_sparql_constraint_component`) |

A fifth candidate (`sh:equals`/`sh:disjoint`/`sh:lessThan`/`sh:lessThanOrEquals` "not evaluating complex property paths") was investigated, retracted on 2026-07-20, then **un-retracted** the same day once the retraction itself turned out to be based on an incomplete check. The retraction tested plain, unmodified `pyshacl.validate(..., meta_shacl=True)` - which checks against pySHACL's own *stale, pre-1.2* bundled meta-shapes (`pyshacl/assets/shacl-shacl.ttl`), correctly declaring all four predicates `sh:nodeKind sh:IRI` per the *original* SHACL Core - and concluded the complex-path form was never valid input at all. But `starshacl`'s own corrected meta-shapes (`meta_validate()`) - which specifically exist to fix exactly this staleness for these 8 predicates, see `meta_shapes.py`'s own module docstring - accept the identical shape cleanly, confirming the SHACL 1.2 widening is real (corroborated externally too: W3C `data-shapes` issue #119, labeled "Core" for the SHACL 1.2 Core milestone, requests exactly this generalization). So the correct conclusion is closer to the original claim: plain pySHACL doesn't know about the SHACL 1.2 widening at all, both in its meta-shapes *and* in its runtime `EqualsConstraintComponent`/etc., which silently mistreat a valid path value as an empty comparison set. This entry needs to be rewritten as a real issue again (full `### Description`/`### Reproduction`/etc. write-up not yet redone) before deciding whether to add it to the reporting queue alongside Issue 1.

## How To Use

Each entry uses this structure - the `##` heading plus `###` subheadings - so it can be pasted directly into a GitHub issue with minimal editing (title = the `##` heading text, body = everything from "pySHACL version" through "Suggested fix"; "Status" is doc-only tracking, not part of the issue body):

- `## Issue N - <title> (found <date>)`
- `**pySHACL version:** <version> (<file/function>)`
- Confirmation note (which pySHACL build/commit this was last checked against)
- `### Description`
- `### Reproduction` (minimal, plain RDF 1.1)
- `### Expected behavior`
- `### Actual behavior`
- `### Suspected root cause`
- `### Impact`
- `### Suggested fix` (and/or possible workaround)
- `### Status` (`found`, `reported` + issue link, `fixed upstream`)

All 4 entries use this structure.

## Entries

| # | Title | Found |
| --- | --- | --- |
| 1 | `sh:intersection` node expression silently evaluates empty, producing an incorrect SHACL validation result | 2026-07-15 |
| 2 | `pyshacl.validate()` returns a `ValidationFailure` exception object as `report_graph` instead of raising it | 2026-07-19 |
| 3 | A malformed `sh:closed` value either crashes the run or is silently misinterpreted, depending on its RDF term type | 2026-07-16 |
| 4 | `sh:filterShape` node expression crashes with an `AttributeError` | 2026-07-17 |
| 5 | `RdfLibDataGraph.clone()` silently discards a caller-supplied `Graph` subclass's identity and extra state | 2026-07-31 |
| 6 | `sh:sparql`'s own constraint node ignores its own `sh:severity` | 2026-07-31 |

See the Status Summary above for which of these is planned to be reported.

## Issue 1 - `sh:intersection` node expression silently evaluates empty, producing an incorrect SHACL validation result (found 2026-07-15)

**pySHACL version:** 0.40.0 (`pyshacl/helper/expression_helper.py::nodes_from_node_expression`)

Confirmed against pySHACL installed directly from the `RDFLib/pySHACL` GitHub repository's default branch tip (`9eeb9bf`), currently identical to the `v0.40.0` release tag (zero commits past it), as of 2026-07-20.

### Description

This is a pure validation-correctness bug, reproducible with `sh:expression` alone (SHACL Advanced Features, `advanced=True`) - no `sh:rule` needed. `sh:expression`'s node expression is evaluated directly during validation and must evaluate to exactly the singleton set `{true}` to conform.

The reproduction below isolates the bug in a single `validate()` call: the focus node has the identical value `true` on both properties being combined, so both `sh:intersection` and `sh:union` of the two paths are mathematically identical - each correctly equals `{true}`. The shape checks both, as two separate `sh:expression` values with distinct `sh:message`s. `sh:union` isn't affected by this bug and passes; `sh:intersection`, evaluated on the exact same data through the same code path, should also pass but doesn't - producing exactly one violation and pinpointing which of the two is broken, without depending on any behavioral difference in the input data itself.

### Reproduction

```python
import pyshacl
from rdflib import Graph

data = Graph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice ex:says true ;
             ex:notes true .
""", format="turtle")

shapes = Graph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .

    ex:CombinedShape a sh:NodeShape ;
      sh:targetNode ex:alice ;
      sh:expression [
        sh:intersection ( [ sh:path ex:says ] [ sh:path ex:notes ] ) ;
        sh:message "sh:intersection did not evaluate to true" ;
      ] ;
      sh:expression [
        sh:union ( [ sh:path ex:says ] [ sh:path ex:notes ] ) ;
        sh:message "sh:union did not evaluate to true" ;
      ] .
""", format="turtle")

conforms, report_graph, report_text = pyshacl.validate(data, shacl_graph=shapes, advanced=True, meta_shacl=False)
print("conforms:", conforms)
print(report_text)
```

### Expected behavior

`conforms == True` - both `sh:intersection` and `sh:union` of `{true}` and `{true}` correctly equal `{true}`, satisfying `sh:expression`'s requirement for both expressions on the shape.

### Actual behavior

`conforms == False`, with exactly one violation - `"sh:intersection did not evaluate to true"`. The `sh:union` expression, evaluated on identical data through the identical `sh:expression` mechanism, silently passes - confirming the bug is specific to `sh:intersection`'s own evaluation, not a general problem with node-expression handling or with the shape/data setup.

### Suspected root cause

In `nodes_from_node_expression`, the `sh:union` branch reads its argument list from the shapes graph (`sg.graph.items(union_list)`), but the `sh:intersection` branch reads its argument list from the **data graph** instead (`data_graph.items(inter_list)`). The RDF list defining the intersection's arguments is a structure in the shapes graph, not the data graph, so `data_graph.items(inter_list)` finds nothing and the whole intersection short-circuits to empty. Comparing the two branches side by side in the source looks like a copy-paste inconsistency (`sg.graph` vs `data_graph`) rather than an intentional difference.

### Impact

Any shape whose validation outcome depends on a `sh:intersection` node expression gets a wrong `sh:ValidationReport` - data that should conform is reported as a violation, since the intersection always evaluates to empty regardless of the actual data.

### Suggested fix

The one-line fix at the `sh:intersection` branch is `parts = list(sg.graph.items(inter_list))` instead of `parts = list(data_graph.items(inter_list))` - literally matching the `sh:union` branch immediately above it.

### Status

**Fixed upstream in pySHACL v0.40.1** (2026-07-27). The release changelog credits the fix to this report; the diff (`expression_helper.py`, `sh:intersection` branch) is exactly the one-line change suggested above (`parts = list(data_graph.items(inter_list))` → `parts = list(sg.graph.items(inter_list))`). Verified directly: the reproduction script above returns `conforms: False` (bug present) against pySHACL 0.40.0, and `conforms: True` (bug fixed) against 0.40.1, with no other change. `pyproject.toml` now requires `pyshacl>=0.40.1`. `starshacl`'s own workaround (`_inject_intersection_list_triples`) has been removed from `validator.py` - it's no longer needed now that the minimum pySHACL version has the fix, and `tests/integration/test_node_expressions_integration.py::test_node_expression_intersection_carries_triple_term_value`/`test_node_expression_intersection_carries_plain_rdf11_value` confirm `sh:intersection` still works correctly end to end without it.

## Issue 2 - `pyshacl.validate()` returns a `ValidationFailure` exception object as `report_graph` instead of raising it (found 2026-07-19)

**pySHACL version:** 0.40.0 (`pyshacl/entrypoints.py::validate`)

Confirmed against pySHACL installed directly from the `RDFLib/pySHACL` GitHub repository's default branch tip (`9eeb9bf`), currently identical to the `v0.40.0` release tag (zero commits past it), as of 2026-07-20.

### Description

This is an example of a **malformed shape** - here, a `sh:sparql` constraint whose query text is invalid SPARQL-SHACL (it contains a `VALUES` clause, disallowed by the spec) - being reported to the caller as if it were an ordinary **data conformance failure**. `conforms` comes back `False` and `report_text` reads like a normal violation message, with nothing to distinguish "your shapes graph is broken" from "your data doesn't conform." A caller who only checks the `conforms` flag (the standard usage pattern) cannot tell the two apart at all.

It gets worse if that caller tries to inspect the report for details, the normal next step after any conformance failure: `pyshacl.validate()`'s documented return type is `(bool, Graph, str)`, but `report_graph` here is the raw `ValidationFailure` exception object, not a `Graph`. Iterating it - the ordinary way to read a validation report - crashes with an unrelated `TypeError` instead of surfacing the real problem.

The simplest trigger is a `sh:sparql` constraint with a `VALUES` clause - disallowed per the SHACL-SPARQL spec, and checked with an ordinary regex before pySHACL ever executes the query, so no data, no custom constraint component, and no `advanced=True` are needed.

### Reproduction

```python
import pyshacl
from rdflib import Graph

data = Graph()  # empty - not needed to trigger this

shapes = Graph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .

    ex:S a sh:NodeShape ;
      sh:targetNode ex:alice ;
      sh:sparql [ sh:select "SELECT $this WHERE { VALUES ?x { 1 } }" ] .
""", format="turtle")

conforms, report_graph, report_text = pyshacl.validate(data, shacl_graph=shapes, meta_shacl=False)
print("conforms:", conforms)
print("report_text:", report_text)
print("type(report_graph):", type(report_graph))

# What a caller relying on the documented (bool, Graph, str) contract would do next:
for triple in report_graph:
    print(triple)
```

### Expected behavior

Some clear signal that the *shapes graph* is malformed - a raised exception, or at minimum a `report_text` that doesn't read like an ordinary data-conformance message. Whatever `report_graph` is, it should be consistent with the documented `(bool, Graph, str)` contract, so a caller can inspect it the same way they would any other validation report.

### Actual behavior

Running the reproduction above prints:

```
conforms: False
report_text: Validation Failure - A SPARQL Constraint must not contain a VALUES clause.
type(report_graph): <class 'pyshacl.errors.ValidationFailure'>
```

`conforms: False` plus a plausible-sounding `report_text` is indistinguishable, from the caller's side, from an ordinary conformance failure - there is no data here at all, yet the shapes-graph problem is reported exactly like a data problem would be. Then the `for triple in report_graph` loop - the normal way to inspect *any* validation report - crashes:

```
TypeError: 'ValidationFailure' object is not iterable
```

discarding pySHACL's own accurate message (`report_text`) in the process.

### Suspected root cause

The exact catch site, `pyshacl/entrypoints.py::validate` (around line 243-246):

```python
except ValidationFailure as e:
    conforms = False
    report_graph = e
    report_text = "Validation Failure - {}".format(e.message)
```

Any `ValidationFailure` propagating out of `Validator.run()` - regardless of which of the roughly dozen call sites raised it - is caught here and assigned directly to `report_graph`, without ever being converted to a `Graph` or re-raised.

### Impact

Any of the many `ValidationFailure` conditions in pySHACL (malformed custom `sh:ConstraintComponent` SPARQL validators, disallowed SPARQL clauses, malformed nested `SELECT`s, and more) crashes a caller's own report-processing code with a confusing, unrelated error instead of surfacing pySHACL's own accurate failure message.

### Suggested fix

At the catch site in `entrypoints.py`, either re-raise `ValidationFailure` directly instead of swallowing it into the return tuple, or construct a real (possibly empty, with the failure recorded as an annotation) `Graph` in `report_graph`'s place - either would bring behavior in line with the documented `(bool, Graph, str)` contract.

### Possible workaround

Immediately after calling `pyshacl.validate()`, check `isinstance(report_graph, BaseException)` and re-raise it directly if so, rather than trusting the documented `(bool, Graph, str)` contract unconditionally.

### Status

Found, confirmed against the latest pySHACL code (2026-07-20, see note at top of this document). **Not planned to be reported upstream** - low severity (a caller-side `isinstance(report_graph, BaseException)` guard fully neutralizes it), and already fully worked around in `starshacl` (`validator.py::validate()` re-raises `report_graph` directly when it's an exception, instead of returning it) - verified end-to-end via `StarShaclValidator`, which raises `ValidationFailure` cleanly rather than returning the broken tuple.

## Issue 3 - a malformed `sh:closed` value either crashes the run or is silently misinterpreted, depending on its RDF term type (found 2026-07-16)

**pySHACL version:** 0.40.0 (`pyshacl/constraints/core/other_constraints.py`, `ClosedConstraintComponent.__init__`)

Confirmed against pySHACL installed directly from the `RDFLib/pySHACL` GitHub repository's default branch tip (`9eeb9bf`), currently identical to the `v0.40.0` release tag (zero commits past it), as of 2026-07-20.

### Description

pySHACL already knows the correct way to reject a malformed `sh:closed` value - its own bundled meta-shapes (`pyshacl/assets/shacl-shacl.ttl`, used only when the caller opts into `meta_shacl=True`) declare `sh:closed`'s path with `sh:datatype xsd:boolean`, and correctly, consistently rejects any non-boolean value through that mechanism. The bug is that this correct check is never applied on the default code path (`meta_shacl=False`, `pyshacl.validate()`'s own default) - so most callers never benefit from it, and hit `ClosedConstraintComponent.__init__` instead:

```python
assert isinstance(closed_vals[0], rdflib.Literal), "sh:closed must take a xsd:boolean literal."
self.is_closed = bool(closed_vals[0].value)
```

This line is also inconsistent with its own immediate neighbors: the same `__init__` method already raises pySHACL's purpose-built `ConstraintLoadError` for three other malformed-input cases just a few lines earlier (missing `sh:closed`, more than one `sh:closed` value, misused `sh:ignoredProperties`) - only this fourth case drops to a bare `assert` instead. And unlike the meta-shacl check, which treats every malformed value the same way, this line treats different kinds of malformed value completely differently:

- **An IRI** (`sh:closed ex:NotEvenARealValue`): fails the `isinstance` check, so the `assert` fires - crashing the *entire* `pyshacl.validate()` call with a raw `AssertionError`. Under Python's `-O` (optimized) mode - a standard, supported way to run Python - the `assert` is stripped entirely, and execution falls through to `.value` on the next line, crashing anyway with an unrelated `AttributeError` (a `URIRef` has no `.value`).
- **A plain string literal** (`sh:closed "false"`): *passes* the `isinstance` check - a string literal is still a `Literal` - so the `assert` never fires, no crash at all. `Literal("false").value` is just the Python string `"false"` (rdflib only populates `.value` with a converted Python type for recognized datatypes like `xsd:boolean`), and `bool("false")` is `True` in Python regardless of what the string says. The shape silently ends up **closed**, the opposite of what `"false"` clearly means to a human reader.

### Reproduction

All four cases below use the identical shape and data, varying only the `sh:closed` value and the `meta_shacl` setting.

```python
import pyshacl
from rdflib import Graph, Namespace, Literal, RDF

EX = Namespace("http://example.org/")


def run(closed_value_ttl, meta_shacl):
    data = Graph()
    data.add((EX.dog1, RDF.type, EX.Dog))
    data.add((EX.dog1, EX.barks, Literal(True)))

    shapes = Graph()
    shapes.parse(data=f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .

        ex:Dog a sh:NodeShape ;
          sh:targetClass ex:Dog ;
          sh:closed {closed_value_ttl} ;
          sh:property [ sh:path ex:barks ] .
    """, format="turtle")

    label = f"sh:closed {closed_value_ttl}, meta_shacl={meta_shacl}"
    try:
        conforms, report_graph, report_text = pyshacl.validate(data, shacl_graph=shapes, meta_shacl=meta_shacl)
        print(f"{label} -> conforms: {conforms}")
    except Exception as e:
        print(f"{label} -> {type(e).__name__}")


# Baseline 1: correctly-typed xsd:boolean values - already works correctly either way.
run("true", meta_shacl=False)
run("false", meta_shacl=False)

# Baseline 2: malformed values, but with meta_shacl=True - already works correctly too.
run("ex:NotEvenARealValue", meta_shacl=True)
run('"false"', meta_shacl=True)

# The bug: the same two malformed values, with meta_shacl=False (pyshacl.validate()'s own default).
run("ex:NotEvenARealValue", meta_shacl=False)
run('"false"', meta_shacl=False)
```

Run the last `"false"` case (`meta_shacl=False`) once more with `python -O` to see the second crash mode.

### Expected behavior

```
sh:closed true, meta_shacl=False -> conforms: False
sh:closed false, meta_shacl=False -> conforms: True
sh:closed ex:NotEvenARealValue, meta_shacl=True -> ReportableRuntimeError
sh:closed "false", meta_shacl=True -> ReportableRuntimeError
sh:closed ex:NotEvenARealValue, meta_shacl=False -> ReportableRuntimeError (or equivalent - some consistent, scoped rejection)
sh:closed "false", meta_shacl=False -> ReportableRuntimeError (or equivalent - not the same result as sh:closed true)
```

The two `meta_shacl=True` lines already behave exactly as expected - `pyshacl.validate()` raises `ReportableRuntimeError`, both malformed values rejected identically and correctly, since `meta_shacl=True` runs the shapes graph itself through pySHACL's own bundled meta-shapes first, whose `sh:closed` rule (`sh:datatype xsd:boolean`) is already correct. The last two lines - the actual default behavior - should reject the same two malformed values the same way, since nothing about `meta_shacl` changes what a well-formed shape looks like.

### Actual behavior

The first four lines print/behave exactly as expected - both baselines are genuinely correct:

```
sh:closed true, meta_shacl=False -> conforms: False
sh:closed false, meta_shacl=False -> conforms: True
sh:closed ex:NotEvenARealValue, meta_shacl=True -> ReportableRuntimeError
sh:closed "false", meta_shacl=True -> ReportableRuntimeError
```

The last two - `meta_shacl=False`, pySHACL's own default - are where it goes wrong, and the two malformed values fail in two different bad ways instead of the consistent rejection `meta_shacl=True` already demonstrates is possible:

```
sh:closed ex:NotEvenARealValue, meta_shacl=False -> AssertionError
sh:closed "false", meta_shacl=False -> conforms: False
```

Re-running the `ex:NotEvenARealValue`/`meta_shacl=False` case with `python -O` (assertions stripped) changes `AssertionError` to `AttributeError` instead. The `"false"` case doesn't raise anything at all - and produces the exact same result as the baseline's `sh:closed true` (`conforms: False`, `ex:dog1`'s `rdf:type` rejected as an extra property), the exact opposite of the baseline's `sh:closed false` (`conforms: True`) that `"false"` was clearly meant to express. The shape was silently treated as **closed**, not open.

### Impact

Any shapes graph with a malformed `sh:closed` value fails in one of two bad ways under `pyshacl.validate()`'s own default settings, even though the exact same input is already handled correctly and consistently when `meta_shacl=True` is set: an IRI crashes the entire validation run (inconsistently, depending on Python's optimization flag); a string literal is silently coerced to `True` regardless of its actual content, producing wrong validation results with no indication anything is wrong. The second case is the more dangerous of the two, since it fails silently.

### Suggested fix

The correct check already exists - `pyshacl/assets/shacl-shacl.ttl`'s `sh:datatype xsd:boolean` rule on `sh:closed`. Port the equivalent check into `ClosedConstraintComponent.__init__` itself, replacing the bare `assert`, using the same `ConstraintLoadError` pattern already used three times earlier in this exact method:

```python
val = closed_vals[0]
if not (isinstance(val, rdflib.Literal) and val.datatype == XSD.boolean):
    raise ConstraintLoadError(
        "ClosedConstraintComponent: sh:closed value must be a xsd:boolean literal.",
        "https://www.w3.org/TR/shacl/#ClosedConstraintComponent",
    )
```

### Possible workaround

Run with `meta_shacl=True` - as shown above, that code path already rejects a malformed `sh:closed` value correctly and consistently, entirely avoiding `ClosedConstraintComponent.__init__`'s buggy check. Where `meta_shacl=True` isn't otherwise wanted (it validates the whole shapes graph, not just this one predicate, and has its own performance cost), validate `sh:closed`'s value directly before calling `pyshacl.validate()` instead.

### Status

Found, confirmed against the latest pySHACL code (2026-07-20, see note at top of this document). Deferred, not currently planned to be reported upstream. `starshacl` fully replaces pySHACL's dispatch entry for `sh:closed`/`sh:ignoredProperties` with its own component (so pySHACL's buggy code is never reached at all, regardless of `meta_shacl`). Writing this document up initially surfaced a real, live gap in that replacement: it correctly rejected the IRI case with a clean `ValueError`, but `sh:closed "false"` (a string literal) still silently produced `conforms: False` - the shape incorrectly treated as closed, the identical wrong direction as raw pySHACL's bug - because the check only verified `isinstance(closed_val, Literal)`, not the literal's actual datatype. Fixed the same day (`starshacl/native_components.py::_build_closed_component`, now checks `closed_val.datatype == XSD.boolean`), with regression coverage added (`tests/integration/test_closed_by_types.py::TestClosedMalformedValueRejectedCleanly`, confirmed to fail without the fix). `starshacl` now handles this issue fully, independent of upstream status.

## Issue 4 - `sh:filterShape` node expression crashes with an `AttributeError` (found 2026-07-17)

**pySHACL version:** 0.40.0 (`pyshacl/helper/expression_helper.py::nodes_from_node_expression`, the `sh:filterShape` branch)

Confirmed against pySHACL installed directly from the `RDFLib/pySHACL` GitHub repository's default branch tip (`9eeb9bf`), currently identical to the `v0.40.0` release tag (zero commits past it), as of 2026-07-20.

### Description

`sh:filterShape` crashes the moment it's evaluated, regardless of context - no data, no real constraint, no `sh:rule` needed. It's reproducible with `sh:expression` alone (SHACL Advanced Features, `advanced=True`), which calls the exact same underlying `nodes_from_node_expression` function `sh:rule` does - confirming this is a bug in that shared function itself, not something specific to rules.

pySHACL's own source has a comment directly above the `sh:filterShape` branch: `# Note: There's no tests for this whole filterShapes feature!` (the branch is also marked `# pragma: no cover`) - this is unmaintained, unexercised code, not a subtler logic bug.

### Reproduction

```python
import pyshacl
from rdflib import Graph

data = Graph()  # empty - not needed to trigger this

shapes = Graph()
shapes.parse(data="""
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .

    ex:F a sh:NodeShape .

    ex:S a sh:NodeShape ;
      sh:targetNode ex:alice ;
      sh:expression [ sh:filterShape ex:F ; sh:nodes ex:bob ] .
""", format="turtle")

conforms, report_graph, report_text = pyshacl.validate(data, shacl_graph=shapes, advanced=True, meta_shacl=False)
```

### Expected behavior

`ex:bob` checked against `ex:F` (a trivial shape with no constraints, so it conforms); `sh:filterShape` returns `[ex:bob]`, which is not the singleton `{true}` `sh:expression` requires, so this should produce an ordinary `ExpressionConstraintComponent` violation - not a crash.

### Actual behavior

```
AttributeError: 'RdfLibDataGraph' object has no attribute 'sparql_mode'
```

Raised from `Shape.validate()`, called as `filter_shape.validate(data_graph, n)` inside the `sh:filterShape` branch. `Shape.validate()` expects an executor-like first argument with a `.sparql_mode` attribute, not a raw data graph - a calling-convention mismatch, not a subtler logic bug.

### Impact

Any shapes graph using `sh:filterShape` anywhere - inside `sh:TripleRule`, `sh:expression`, or any other node-expression context - crashes with this `AttributeError` the instant that node expression is evaluated, regardless of the data or the filter shape's own content.

### Suggested fix

`Shape.validate()`'s real signature is `(executor: SHACLExecutor, target_graph, focus=None, _evaluation_path=None)`. The one-line fix at the `sh:filterShape` call site is `conforms, reports = filter_shape.validate(SHACLExecutor(), data_graph, focus=n)` instead of `filter_shape.validate(data_graph, n)`.

### Possible workaround

Apply a runtime patch to `pyshacl.shape.Shape.validate` that detects the broken 2-argument calling convention (a raw data graph as the first argument, rather than a `SHACLExecutor`) and adapts it to the correct one - a strict superset of the original behavior, since every correctly-formed call (a real `SHACLExecutor` as the first argument) falls through unchanged.

### Status

Found, confirmed against the latest pySHACL code (2026-07-20, see note at top of this document). **Not planned to be reported upstream**: this code has been broken since it was introduced in 2020 (commit `cc3d291`, pySHACL's own repo history), the `# Note: There's no tests for this whole filterShapes feature!` comment appears to be original to that commit, and a full-history `git log`/GitHub issue-and-PR search found zero mentions of `filterShape` anywhere except that one introducing commit - no community reports, no follow-up work, in over 5 years. pySHACL's own `FEATURES.md` already self-documents it as "status-complete" / "not tested." Reporting this would likely just restate what the maintainers already know about a feature with apparently no real-world usage. Fully worked around in `starshacl` (`validator.py::_patch_shape_validate_for_filter_shape`) regardless.

## Issue 5 - `RdfLibDataGraph.clone()` silently discards a caller-supplied `Graph` subclass's identity and extra state (found 2026-07-31)

**pySHACL version:** 0.40.1 (`pyshacl/graph_abstraction.py::RdfLibDataGraph.clone`, via `pyshacl/rdfutil/clone.py::clone_graph`)

### Description

`pyshacl.validate(..., advanced=True)` unconditionally clones the data graph before validating ("Forcing clone of DataGraph because advanced mode is enabled" - so SHACL-AF rules can't mutate the caller's original graph). The clone is built by `RdfLibDataGraph.clone()`, which calls `pyshacl.rdfutil.clone.clone_graph()` to construct the replacement `.impl`. That helper always produces a plain `rdflib.Graph`/`Dataset`, regardless of what type the original `.impl` actually was - if the caller passed a `Graph` *subclass* (adding its own attributes, custom `.query()`/`.triples()` behavior, or a back-reference some other part of the caller's code relies on), the clone silently downgrades to the plain base class, dropping all of that extra identity and state. The clone's actual *triples* are still copied correctly - only the subclass identity and any non-triple state are lost.

### Reproduction

Plain `pyshacl` and `rdflib` only - no third-party wrapper:

```python
from rdflib import Graph, Namespace, Literal
from rdflib.plugins.stores.memory import Memory
from pyshacl.graph_abstraction import RdfLibDataGraph

EX = Namespace("http://example.org/")

class CustomGraph(Graph):
    marker = "original"

data = CustomGraph()
data.add((EX.alice, EX.value, Literal("A")))

wrapped = RdfLibDataGraph(Memory(), impl=data)
cloned = wrapped.clone()

print(type(wrapped.impl))         # <class '__main__.CustomGraph'>
print(type(cloned.impl))          # <class 'rdflib.graph.Graph'>  -- subclass lost
print(hasattr(cloned.impl, "marker"))   # True before, False after
print(set(cloned.impl.triples((None, None, None))) == set(data.triples((None, None, None))))  # True - triples fine
```

### Expected behavior

`clone()` should produce a new graph of the *same* runtime type as the original `.impl` (or otherwise preserve whatever extra state/behavior the subclass adds), the same way copying a Python object doesn't normally downgrade it to its base class.

### Actual behavior

`cloned.impl` is always a plain `rdflib.Graph`/`Dataset`. Any attribute, method override, or back-reference the original subclass added is gone; only the triples survive the round-trip.

### Suspected root cause

`pyshacl/rdfutil/clone.py::clone_graph()` constructs its replacement graph as a fresh, hardcoded plain `Graph()`/`Dataset()` rather than `type(source_graph)()` (or otherwise delegating construction back to the source's own class).

### Impact

Any caller passing a custom `Graph` subclass into `pyshacl.validate()` and using `advanced=True` (needed for `sh:expression`/`sh:rule`) silently loses that subclass's identity partway through validation - with no error, warning, or other visible signal. Concretely confirmed via `starshacl`: its own `_SparqlAwareEncodedGraph` wrapper (carrying a `_tt_adapter` back-reference needed to recognize RDF 1.2 triple-term encodings) gets silently downgraded to a plain `Graph` under `advanced=True`, which made a custom `ConstraintComponent` (`ReifierShapeConstraintComponent`) unable to re-encode a lookup key correctly - it silently found zero matches and reported vacuous conformance instead of the real violation. A logic bug like this, with no crash or warning at the point of failure, is a worse failure mode than an exception would be.

### Suggested fix

Preserve the source graph's runtime type when constructing the clone - e.g. `type(source_impl)()` instead of a hardcoded `Graph()`/`Dataset()` - or, at minimum, copy over `__dict__` (or a documented extension point) from the original onto the clone so subclass-added state survives.

### Possible workaround

Patch `RdfLibDataGraph.clone()` to copy specific known custom attributes (e.g. `_tt_adapter`) from the pre-clone `.impl` onto the post-clone `.impl` after calling the original method - a strict superset of the original behavior, no-op for a plain `Graph`/`Dataset` with no such attribute.

### Status

Found 2026-07-31, confirmed against pySHACL 0.40.1 (this project's currently pinned version - see `pyproject.toml`). **Reporting upstream planned** (not yet filed): this is a plain, generically-reproducible pySHACL API gap (no custom wrapper's cooperation needed to trigger - any `Graph` subclass hits it), distinct in kind from Issues 2-4 above (which are either low-severity, effectively-dead-code, or something `starshacl` fully owns and permanently patches around regardless). Worked around in `starshacl` (`validator.py::_patch_rdflib_data_graph_clone_preserves_tt_adapter`) in the meantime.

## Issue 6 - `sh:sparql`'s own constraint node ignores its own `sh:severity` (found 2026-07-31)

**pySHACL version:** 0.40.1 (`pyshacl/constraints/sparql/sparql_based_constraints.py::SPARQLBasedConstraint`)

### Description

The SHACL Core spec's SPARQL-based Constraints section lets the object of `sh:sparql` (a constraint node distinct from the shape it's attached to) carry its own `sh:message`/`sh:deactivated` overrides, and, per the general per-constraint override pattern, its own `sh:severity` too. pySHACL's `SPARQLBasedConstraint.__init__` reads `sh:message` and `sh:deactivated` from that node correctly, but never reads `sh:severity` - confirmed via a full grep of `pyshacl/constraints/sparql/` and `pyshacl/helper/` for "severity" (zero matches). Every violation instead reports the *shape's* own severity (via `ConstraintComponent.make_v_result`'s generic `self.shape.severity` read), regardless of what the `sh:sparql` constraint node itself declares.

### Reproduction

Plain `pyshacl` only:

```python
import pyshacl
from rdflib import Graph

data = Graph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:alice rdfs:label "should not have a label" .
""", format="turtle")

shapes = Graph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
      sh:sparql [
        sh:message "Cannot have a label" ;
        sh:severity sh:Warning ;
        sh:select "SELECT $this ?value WHERE { $this <http://www.w3.org/2000/01/rdf-schema#label> ?value . }" ;
      ] .
""", format="turtle")

conforms, report_graph, report_text = pyshacl.validate(data, shacl_graph=shapes, meta_shacl=False)
print(list(report_graph.objects(None, pyshacl.consts.SH_resultSeverity)))
```

### Expected behavior

The reported `sh:resultSeverity` should be `sh:Warning`, per the `sh:sparql` constraint node's own `sh:severity` declaration.

### Actual behavior

`sh:resultSeverity` is `sh:Violation` - the shape's own default severity, since the shape itself has no `sh:severity` override and the constraint node's own `sh:severity sh:Warning` is never consulted.

### Suspected root cause

`SPARQLBasedConstraint.__init__` (`pyshacl/constraints/sparql/sparql_based_constraints.py`) builds a `query_helper` per `sh:sparql` value, reading `sh:message`/`sh:deactivated` from it, but has no equivalent read for `sh:severity`; `_evaluate_sparql_constraint` calls `self.make_v_result(...)` unconditionally, which always uses `self.shape.severity`.

### Impact

Any shapes graph using `sh:sparql` with a per-constraint `sh:severity` override (rather than relying on the shape's own severity) silently gets the wrong severity on every reported violation - no error, no warning, just an incorrect report field a caller might filter or route on.

### Suggested fix

In `SPARQLBasedConstraint.__init__`, read `sh:severity` from each `sh:sparql` value the same way `sh:message`/`sh:deactivated` are already read, store it alongside the other `query_helper` fields, and have `_evaluate_sparql_constraint` pass it through to `make_v_result` (or override the resulting `sh:resultSeverity` triple after the fact) when present.

### Possible workaround

Subclass `SPARQLBasedConstraint`, override `_evaluate_sparql_constraint` to call the original implementation and then, if the constraint node has its own `sh:severity`, replace the `sh:resultSeverity` triple in each returned report's triples - a strict superset of the original behavior, no-op when no per-constraint `sh:severity` is present.

### Status

Found 2026-07-31 via the W3C SHACL 1.2 test suite's `sparql-001` fixture, confirmed against pySHACL 0.40.1. Not yet added to the reporting queue (pending triage alongside Issue 5). Worked around in `starshacl` (`native_components.py::_build_sparql_constraint_component`, registered over pySHACL's own `SH.sparql` dispatch entry) in the meantime.
