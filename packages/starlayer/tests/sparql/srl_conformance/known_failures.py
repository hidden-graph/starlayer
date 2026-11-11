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

_CAUSES: dict[str, str] = {}

# "case-id::check" -> reason (check is parses | fixpoint | meaning | tree | encoding)
CORPUS_FAILURES: dict[str, str] = {}

# SPARQL functions that SRL's BuiltInCall does NOT include but the parser accepted: none since L2 was fixed.
BUILTIN_LEAKS: dict[str, str] = {}

# functions that ARE in the spec's BuiltInCall but fail to parse or to be represented as a tree.
BUILTIN_FAILURES: dict[str, str] = {}

# negative case id -> reason the parser wrongly ACCEPTS it (or fails to refuse it with an SRL error)
NEGATIVE_FAILURES: dict[str, str] = {}

# spec example block number -> reason it fails
SPEC_EXAMPLE_FAILURES: dict[int, str] = {}
