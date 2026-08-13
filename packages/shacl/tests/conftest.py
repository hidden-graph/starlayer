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
