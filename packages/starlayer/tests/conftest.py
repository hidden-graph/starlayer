"""Suite-wide pytest options: opt-in test groups.

Some groups are thorough and slow, or are deep checks of one algorithm that an
ordinary run does not need every time. Each is left out of an ordinary run -
including a bare ``pytest`` and ``pytest -m "not integration"`` - entirely
(they are *deselected*, not skipped, so they don't clutter the summary). Opt in
to a group with its flag, its environment variable, or its marker:

``store_matrix``: the W3C conformance suites run through every store (the
in-process, on-disk and server-backed Oxigraph, and Fuseki); the server-backed
ones make real HTTP calls.

    pytest --store-matrix                 # everything, plus the store matrix
    STARLAYER_STORE_MATRIX=1 pytest       # same, via the environment
    pytest -m store_matrix                # only the store matrix

``srl_stratification``: extended checks of SRL's stratification algorithm
(indirect negation cycles, long chains, edge cases of the dependency graph).

    pytest --srl-stratification
    STARLAYER_SRL_STRATIFICATION=1 pytest
    pytest -m srl_stratification

Done at collection time rather than with a default ``-m`` in ``addopts``
because a ``-m`` given on the command line (``-m "not integration"`` is the
repo's usual fast tier) would replace an ``addopts`` one and silently bring
these tests back.
"""

from __future__ import annotations

import os

# marker -> (command-line flag, environment variable, --help text)
OPT_IN_GROUPS = {
    "store_matrix": (
        "--store-matrix",
        "STARLAYER_STORE_MATRIX",
        "also run the W3C suites through every store (slow; makes real HTTP calls to Oxigraph/Fuseki)",
    ),
    "srl_stratification": (
        "--srl-stratification",
        "STARLAYER_SRL_STRATIFICATION",
        "also run the extended SRL stratification checks",
    ),
    "sqe_coverage": (
        "--sqe-coverage",
        "STARLAYER_SQE_COVERAGE",
        "also run the sqe query-coverage set (every SPARQL feature round-tripped through sqe)",
    ),
}


def pytest_addoption(parser):
    for _marker, (flag, _env, help_text) in OPT_IN_GROUPS.items():
        parser.addoption(flag, action="store_true", default=False, help=help_text)


def _requested(config, marker: str) -> bool:
    flag, env, _help = OPT_IN_GROUPS[marker]
    if config.getoption(flag) or os.environ.get(env):
        return True
    expr = config.getoption("markexpr", default="") or ""
    # an explicit `-m <marker>` (not `-m "not <marker>"`) means "run them"
    return marker in expr and f"not {marker}" not in expr


def pytest_collection_modifyitems(config, items):
    left_out = [marker for marker in OPT_IN_GROUPS if not _requested(config, marker)]
    if not left_out:
        return
    kept, deselected = [], []
    for item in items:
        (deselected if any(item.get_closest_marker(m) for m in left_out) else kept).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
