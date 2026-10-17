"""Suite-wide pytest options.

``store_matrix``: the W3C conformance suites run through every store (the
in-process, on-disk and server-backed Oxigraph, and Fuseki). They are thorough
and slow (the server-backed ones make real HTTP calls), so an ordinary run -
including a bare ``pytest`` and ``pytest -m "not integration"`` - leaves them
out entirely (they are *deselected*, not skipped, so they don't clutter the
summary). Opt in with any of:

    pytest --store-matrix                 # everything, plus the store matrix
    STARLAYER_STORE_MATRIX=1 pytest       # same, via the environment
    pytest -m store_matrix                # only the store matrix

Done at collection time rather than with a default ``-m`` in ``addopts``
because a ``-m`` given on the command line (``-m "not integration"`` is the
repo's usual fast tier) would replace an ``addopts`` one and silently bring
these tests back.
"""

from __future__ import annotations

import os

MARKER = "store_matrix"


def pytest_addoption(parser):
    parser.addoption(
        "--store-matrix",
        action="store_true",
        default=False,
        help="also run the W3C suites through every store (slow; makes real HTTP calls to Oxigraph/Fuseki)",
    )


def _store_matrix_requested(config) -> bool:
    if config.getoption("--store-matrix") or os.environ.get("STARLAYER_STORE_MATRIX"):
        return True
    expr = config.getoption("markexpr", default="") or ""
    # an explicit `-m store_matrix` (not `-m "not store_matrix"`) means "run them"
    return MARKER in expr and f"not {MARKER}" not in expr


def pytest_collection_modifyitems(config, items):
    if _store_matrix_requested(config):
        return
    kept, deselected = [], []
    for item in items:
        (deselected if item.get_closest_marker(MARKER) else kept).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
