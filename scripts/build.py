"""scripts/build.py - one entry point for the repo's generated files.

Runs the individual build scripts in dependency order:

1. ``build_starontology.py``  - ``starontology`` generated ``.ttl`` files and ``starontology.trig``
2. ``build_codekg.py``        - ``codekg/codekg.trig`` from the source and ``codekg/testskg.trig`` from the tests
3. ``generate_api_docs.py``   - ``docs/generated/api-*.generated.md`` from the code KG
4. ``generate_functionality_overview.py`` - ``docs/generated/functionality-overview.generated.md``
   from the curated functionality graph
5. ``build_query_catalogue.py`` - validates the hand-edited ``codekg/curated/query-library.ttl`` (the named
   queries, as sqe trees) and writes ``docs/generated/query-library.generated.md`` from it
6. ``check_docs.py``          - checks links, anchors and the guide index (changes nothing)
7. ``check_notebook_links.py`` - checks the hand-made notebook-to-code links against the notebooks (changes nothing)
8. ``build_kg.py``           - ``codekg/starlayer-kg.trig``: the code graph, vocabulary, curated layer and every named
   query's SPARQL text in one plain-TriG file (checked by isomorphism, per named graph)

Build-time only: nothing in the library runs or imports this. Each script can
still be run on its own.

``--check`` treats every step the same way: it runs the step, compares what it
wrote with what is committed, then puts the committed files back. Nothing is left
changed, and the exit status is 1 if any output was stale. Outputs are compared by
graph isomorphism for the ``.trig`` files (rdflib labels blank nodes randomly, so
two correct builds differ byte for byte) and byte for byte for the markdown. The
steps run in order, so the API docs are checked against the freshly built code KG;
with ``--skip codekg`` (what CI does) they are checked against the committed one.

Run:
    python scripts/build.py                    # everything
    python scripts/build.py --only codekg apidocs
    python scripts/build.py --check            # change nothing; exit 1 if anything is stale
    python scripts/build.py --check --skip codekg   # what CI runs
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
    side_effects: list[str] = field(default_factory=list)  # also written by the step; --check restores them but does not compare them


_STEPS: dict[str, Step] = {
    "starontology": Step("build_starontology.py", own_check=True),
    "codekg": Step(
        "build_codekg.py",
        ["--paths", "packages/starlayer/starlayer", "packages/starlayer/tests"],
        ["packages/starlayer/starlayer/codekg/codekg.trig", "packages/starlayer/starlayer/codekg/testskg.trig"],
        side_effects=["packages/starlayer/starlayer/codekg/CHANGELOG.md"],  # the extractor appends its automatic entry
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
    "kg": Step("build_kg.py", own_check=True),
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

    from starlayer.codekg import BUILD_GRAPH_IRI

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
        for out in [*_STEPS[name].outputs, *_STEPS[name].side_effects]
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
