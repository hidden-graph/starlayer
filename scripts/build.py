"""scripts/build.py - one entry point for the repo's generated files.

Runs the individual build scripts in dependency order:

1. ``build_starontology.py``  - ``starontology`` generated ``.ttl`` files and ``starontology.trig``
2. ``build_codekg.py``        - ``codekg/codekg.trig`` from the source and tests
3. ``generate_api_docs.py``   - ``docs/generated/api-*.generated.md`` from the code KG

Build-time only: nothing in the library runs or imports this. Each script can
still be run on its own. A rerun on an unchanged tree rewrites nothing in step 1;
steps 2 and 3 regenerate their outputs every time, so expect a diff there.

Run:
    python scripts/build.py                    # everything
    python scripts/build.py --only starontology
    python scripts/build.py --check            # change nothing; exit 1 if starontology is stale
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent

# name -> (script, extra args, supports --check)
_STEPS: dict[str, tuple[str, list[str], bool]] = {
    "starontology": ("build_starontology.py", [], True),
    "codekg": (
        "build_codekg.py",
        ["--paths", "packages/starlayer/starlayer", "packages/starlayer/tests"],
        False,
    ),
    "apidocs": ("generate_api_docs.py", [], False),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", choices=list(_STEPS), nargs="+", help="run just these steps")
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if a checkable step is stale")
    args = parser.parse_args()

    failed = []
    for name in args.only or list(_STEPS):
        script, extra, checkable = _STEPS[name]
        if args.check and not checkable:
            print(f"[{name}] no check mode; skipped", flush=True)
            continue
        cmd = [sys.executable, str(_SCRIPTS / script), *extra, *(["--check"] if args.check else [])]
        print(f"[{name}] {' '.join(Path(c).name if c.endswith('.py') else c for c in cmd[1:])}", flush=True)
        if subprocess.run(cmd, cwd=_ROOT).returncode != 0:
            failed.append(name)
            if not args.check:
                break
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
