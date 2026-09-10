from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# pyshacl is a hard, required runtime dependency (pyproject.toml), not
# optional - but ~20 integration test files individually guard themselves
# with `pytest.importorskip("pyshacl")`, a pattern borrowed from genuinely
# optional-dependency testing. In a correctly installed environment that
# guard is a no-op, but if pyshacl ever becomes unimportable (a broken
# install, a bad transitive dependency resolution, an environment problem in
# CI), the effect would be the entire pyshacl-based suite silently reporting
# as "skipped" rather than failing loudly - exactly the wrong signal for a
# required dependency. Failing collection outright here, once, up front,
# turns that into an immediate, unmissable hard failure instead (found
# during a full-repo review).
try:
    import pyshacl  # noqa: F401
except ImportError as exc:  # pragma: no cover - exercised only when pyshacl is actually broken
    raise RuntimeError(
        "pyshacl failed to import, but it is a required dependency (see pyproject.toml) - "
        "this is an environment problem, not an optional-dependency situation. Fix the "
        "install rather than letting the pyshacl-based test suite silently skip."
    ) from exc

# Eagerly import and install starsparql's grammar extension here, at
# collection time, before any test module gets a chance to trigger it
# lazily from inside a function body - the same fix the sibling `graph`
# package's own conftest.py already applies for the identical reason (see
# its comment for the full empirical write-up). Found necessary here too
# 2026-09-06, once starshacl's "validation" profile started defaulting
# `advanced=True`: pySHACL's advanced-mode machinery does enough extra
# parsing-adjacent work that it now reliably triggers pyparsing's own
# ParseExpression.streamline() resetting rdflib's PrimaryExpression grammar
# object back to its pristine, un-patched state mid-run (confirmed via the
# exact same symptom graph's own conftest.py documents - a plain rdflib
# ParseException on `sh:sparql` query text that used to parse fine),
# undoing starsparql's in-place grammar patch for every `sh:sparql`/triple-
# term-aware query evaluated afterward. A conftest.py is imported during
# collection, before pytest's assertion-rewrite import hook processes
# ordinary test modules - forcing the grammar's first install here sidesteps
# the interaction entirely.
#
# Import order matters here, confirmed live 2026-09-06: `starlayergraph`
# must be imported (triggering its own `apply_all_operator_patches()` -
# the numeric type-promotion fixes in
# `starlayergraph/query/operator_patches.py`, e.g. `xsd:integer * xsd:integer`
# staying `xsd:integer` rather than drifting to `xsd:decimal`) *before*
# `grammar12.install()` runs, not after. `operator_patches.py`'s own
# idempotency guards are plain boolean flags (unlike `grammar12.install()`'s
# own `_already_installed()`, which re-verifies live grammar state
# specifically because a flag can silently go stale) - reversing the order
# lets `grammar12.install()`'s own grammar-tree mutation invalidate whatever
# `apply_all_operator_patches()` already patched, with no flag able to
# detect it needs to re-run. Confirmed by direct A/B testing: `?w * ?h`
# with two `xsd:integer` operands returns `56^^xsd:integer` with this
# order, `56^^xsd:decimal` (silently wrong) with it reversed - reproduced
# via the W3C SHACL 1.2 suite's `rectangle-*` fixtures, which compute
# exactly this. The sibling `graph` package's own conftest.py gets this
# ordering right today only incidentally (it imports
# `starlayergraph.parsers.turtle_parser` for its own fixtures, which
# happens to come first) - importing `starlayergraph` explicitly and first
# here makes the real requirement self-documenting rather than relying on
# the same accident.
import starlayergraph  # noqa: F401
from starsparql import grammar12

grammar12.install()
