"""scripts/publish_kg.py - build the ``starlayer-kg`` data package from the current source, on request.

Run when the documentation is regenerated for a release, not on every change:

    python scripts/publish_kg.py                  # rebuild the graph, stamp it, build the wheel into dist/kg/
    python scripts/publish_kg.py --release v0.1.0 # also create a GitHub release with the wheel and the TriG attached

Steps: refuse a dirty or mismatched tree, run ``scripts/build.py --only codekg kg`` so the graph matches the source, copy
``starlayer-kg.trig`` into ``packages/starlayer-kg/starlayer_kg/`` with a ``BUILD.json`` (starlayer version, commit, time,
triple count), then build the wheel and sdist. ``--release`` uses ``gh`` and publishes outward: it runs only when asked.
Build-time only, like the other scripts here.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages/starlayer-kg"
DATA = PKG / "starlayer_kg"
TRIG = ROOT / "tools/kg/codekg/starlayer-kg.trig"
DIST = ROOT / "dist/kg"


def _version(pyproject: Path) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"no version in {pyproject}")
    return m.group(1)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--allow-dirty", action="store_true", help="build from a tree with uncommitted changes (the commit in BUILD.json will not describe it)")
    parser.add_argument("--release", metavar="TAG", help="create a GitHub release TAG with the wheel and the TriG attached (uses gh)")
    args = parser.parse_args()

    version = _version(PKG / "pyproject.toml")
    lib_version = _version(ROOT / "pyproject.toml")
    if version != lib_version:
        print(f"starlayer-kg is {version} but starlayer is {lib_version}: make them equal first", file=sys.stderr)
        return 1
    if _git("status", "--porcelain", "--untracked-files=no") and not args.allow_dirty:
        print("the tree has uncommitted changes, so the commit stamp would not describe the graph; commit or pass --allow-dirty", file=sys.stderr)
        return 1

    subprocess.run([sys.executable, str(ROOT / "scripts/build.py"), "--only", "codekg", "kg"], cwd=ROOT, check=True)

    sys.path.insert(0, str(ROOT / "packages/starlayer"))
    from starlayer import StarLayerDataset

    kg = StarLayerDataset()
    kg.parse(str(TRIG), format="trig12")
    graphs = [g for g in kg.contexts() if len(g)]
    info = {
        "starlayer_version": lib_version,
        "commit": _git("rev-parse", "HEAD"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "triples": sum(len(g) for g in graphs),
        "named_graphs": len(graphs),
    }
    shutil.copyfile(TRIG, DATA / "starlayer-kg.trig")
    (DATA / "BUILD.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")

    shutil.rmtree(DIST, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(DIST), str(PKG)], check=True)
    artifacts = sorted(DIST.glob("*"))
    print(f"built {', '.join(a.name for a in artifacts)} from {info['commit'][:10]} ({info['triples']:,} triples)")

    if args.release:
        wheel = next(DIST.glob("*.whl"))
        subprocess.run(
            ["gh", "release", "create", args.release, str(wheel), str(TRIG), "--title", f"starlayer-kg {args.release}",
             "--notes", f"Code knowledge graph built from starlayer {lib_version} at {info['commit'][:10]}. "
                        f"`pip install` the wheel; the TriG is the same file for other RDF tools."],
            cwd=ROOT, check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
