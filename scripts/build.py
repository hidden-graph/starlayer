"""scripts/build.py - one entry point for the repo's generated files.

Runs the individual build scripts in dependency order:

1. ``build_starontology.py``  - ``starontology`` generated ``.ttl`` files and ``starontology.trig``
2. ``build_codekg.py``        - ``codekg.trig`` from the source and ``testskg.trig`` from the tests (not committed)
3. ``generate_api_docs.py``   - ``docs/generated/api-*.generated.md`` from the code KG
4. ``generate_functionality_overview.py`` - ``docs/generated/functionality-overview.generated.md``
   from the curated functionality graph
5. ``build_query_catalogue.py`` - validates the hand-edited ``codekg/curated/query-library.ttl`` (the named
   queries, as sqe trees) and writes ``docs/generated/query-library.generated.md`` from it
6. ``check_docs.py``          - checks links, anchors and the guide index (changes nothing)
7. ``check_notebook_links.py`` - checks the hand-made notebook-to-code links against the notebooks (changes nothing)
8. ``build_kg.py``           - ``starlayer-kg.trig``: the code graph, vocabulary, curated layer and every named
   query's SPARQL text in one plain-TriG file (not committed)

Build-time only: nothing in the library runs or imports this. Each script can
still be run on its own.

``--check`` runs each step, compares what it wrote with what is committed, then puts the committed files back.
Nothing is left changed, and the exit status is 1 if any output was stale. The graphs of steps 2 and 8 are build
products, not committed (``.gitignore``), so ``--check`` leaves those steps out; the API docs check builds the code
graph first if it is missing (``codekg.ensure_built()``, about 30 seconds).

Run:
    python scripts/build.py                    # everything
    python scripts/build.py --only codekg apidocs
    python scripts/build.py --check            # change nothing; exit 1 if anything is stale
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent


@dataclass(frozen=True)
class Step:
    script: str
    args: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)  # repo-relative; compared in --check
    own_check: bool = False  # the script has its own --check (it handles its own comparison)
    uncommitted: bool = False  # the outputs are gitignored build products: --check leaves the step out (nothing to compare)


_STEPS: dict[str, Step] = {
    "starontology": Step("build_starontology.py", own_check=True),
    "codekg": Step(
        "build_codekg.py",
        uncommitted=True,  # codekg.trig and testskg.trig; the extractor's default targets are the library and its tests
    ),
    "apidocs": Step(
        "generate_api_docs.py",
        outputs=["docs/generated/api-overview.generated.md", "docs/generated/api-reference.generated.md"],
    ),
    "overview": Step(
        "generate_functionality_overview.py",
        outputs=["docs/generated/functionality-overview.generated.md"],
    ),
    "queries": Step("build_query_catalogue.py", own_check=True),
    "kg": Step("build_kg.py", uncommitted=True),  # starlayer-kg.trig
    "docs": Step("check_docs.py", own_check=True),
    "notebooks": Step("check_notebook_links.py", own_check=True),
}


def _same(path: Path, before: bytes | None) -> bool:
    """Whether the file now holds the same content as ``before``."""
    after = path.read_bytes() if path.exists() else None
    if after == before:
        return True
    if path.suffix != ".trig" or before is None or after is None:
        return False
    return _trig_isomorphic(before, after)


def _trig_isomorphic(a: bytes, b: bytes) -> bool:
    from rdflib.compare import isomorphic
    from starlayer.graph import StarLayerDataset

    from codekg import BUILD_GRAPH_IRI

    def graphs(data: bytes) -> dict:
        ds = StarLayerDataset()
        ds.parse(data=data.decode("utf-8"), format="trig12")
        # The build stamp (time, commit) differs on every build by design; it is not part of what was extracted.
        return {str(g.identifier): g for g in ds.graphs() if len(g) and g.identifier != BUILD_GRAPH_IRI}

    ga, gb = graphs(a), graphs(b)
    return ga.keys() == gb.keys() and all(isomorphic(ga[k], gb[k]) for k in ga)


def _show_diff(path: Path, before: bytes | None, limit: int = 40) -> None:
    """Print the start of a unified diff for a stale text output, so a CI log shows what differs."""
    import difflib

    if path.suffix == ".trig" or before is None or not path.exists():
        return
    old = before.decode("utf-8", "replace").splitlines()
    new = path.read_text(encoding="utf-8", errors="replace").splitlines()
    diff = list(difflib.unified_diff(old, new, f"committed/{path.name}", f"rebuilt/{path.name}", n=1, lineterm=""))
    for line in diff[:limit]:
        print(line[:200], file=sys.stderr)
    if len(diff) > limit:
        print(f"... {len(diff) - limit} more diff lines", file=sys.stderr)


def _run(name: str, step: Step, extra: list[str]) -> bool:
    cmd = [sys.executable, str(_SCRIPTS / step.script), *step.args, *extra]
    print(f"[{name}] {step.script} {' '.join(step.args + extra)}".rstrip(), flush=True)
    return subprocess.run(cmd, cwd=_ROOT).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", choices=list(_STEPS), nargs="+", help="run just these steps")
    parser.add_argument("--skip", choices=list(_STEPS), nargs="+", default=[], help="leave these steps out")
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if anything is stale")
    args = parser.parse_args()
    names = [n for n in (args.only or list(_STEPS)) if n not in args.skip]
    if args.check:
        names = [n for n in names if not _STEPS[n].uncommitted]

    if not args.check:
        for name in names:
            if not _run(name, _STEPS[name], []):
                print(f"failed: {name}", file=sys.stderr)
                return 1
        return 0

    # Check: snapshot every output, run each step, compare, then restore everything.
    snapshots = {
        _ROOT / out: ((_ROOT / out).read_bytes() if (_ROOT / out).exists() else None)
        for name in names
        for out in _STEPS[name].outputs
    }
    stale: list[str] = []
    try:
        for name in names:
            step = _STEPS[name]
            if not _run(name, step, ["--check"] if step.own_check else []):
                stale.append(name)
                continue
            if step.own_check:
                continue
            changed = [out for out in step.outputs if not _same(_ROOT / out, snapshots[_ROOT / out])]
            if changed:
                stale.append(name)
                for out in changed:
                    _show_diff(_ROOT / out, snapshots[_ROOT / out])
    finally:
        for path, content in snapshots.items():
            if content is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != content:
                path.write_bytes(content)
    if stale:
        print(f"stale: {', '.join(stale)} - run `python scripts/build.py --only {' '.join(stale)}` and commit", file=sys.stderr)
        return 1
    print("all generated files are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
