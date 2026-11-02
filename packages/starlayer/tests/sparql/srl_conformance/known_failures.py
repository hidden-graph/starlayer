"""Registry of corpus cases and checks with a known, reasoned disposition.

Same discipline as the Manchester suite and tests/shacl/w3c_shacl12/known_failures.py: a failing conformance
case is never silently skipped; each entry says *why* and is applied as a strict xfail, so it breaks loudly
(as an unexpected XPASS) the moment the underlying gap is closed.

Finding codes: V* = validation. (P*, L*, S* and T were closed on 2026-10-19; see README.) (S* = the text renderer / expression encoder and T = triple terms were closed on 2026-10-19 by encoding,
rendering and validating SRL expressions the way sqe: does; see README.)
"""

from __future__ import annotations

# production name -> why no corpus case exercises it
UNCOVERED_PRODUCTIONS: dict[str, str] = {}

_CAUSES = {
    'V2': 'A function call with NO arguments (`FILTER :f()`, spec [18] ArgList NIL) does not validate: spexpr:_FunctionExprBodyShape requires every function node to carry an argument list and a `distinct` marker, which the encoder omits for a zero-argument call. This is a defect in the SHARED spexpr: shape/encoder, not in SRL: sqe: rejects `FILTER(<f>())` with an SQEValidationError too. (Parsing and rendering are fine; only validation fails.)',
}

# "case-id::check" -> reason (check is parses | fixpoint | meaning | tree | encoding)
CORPUS_FAILURES: dict[str, str] = {
    'body-filter-function-nil::encoding': _CAUSES['V2'],
    'body-filter-function-nil::tree': _CAUSES['V2'],
    'body-filter-function-nil::meaning': _CAUSES['V2'],
    'body-filter-function-nil::fixpoint': _CAUSES['V2'],
    'body-filter-function-nil::parses': _CAUSES['V2'],
}

# SPARQL functions that SRL's BuiltInCall does NOT include but the parser accepted: none since L2 was fixed.
BUILTIN_LEAKS: dict[str, str] = {}

# functions that ARE in the spec's BuiltInCall but fail to parse or to be represented as a tree.
BUILTIN_FAILURES: dict[str, str] = {}

# negative case id -> reason the parser wrongly ACCEPTS it (or fails to refuse it with an SRL error)
NEGATIVE_FAILURES: dict[str, str] = {}

# spec example block number -> reason it fails
SPEC_EXAMPLE_FAILURES: dict[int, str] = {}
