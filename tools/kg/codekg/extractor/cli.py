"""codekg.extractor.cli - the extractor's command-line entry
point, wrapped by the thin ``scripts/build_codekg.py`` launcher at the
repo root.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Four parents up from this file (tools/kg/codekg/extractor/cli.py): extractor -> codekg -> kg -> tools -> <repo root>.
_REPO_ROOT = Path(__file__).resolve().parents[4]

# What `python scripts/build_codekg.py` (no --paths) and `codekg.ensure_built()` extract: the library and its tests.
_DEFAULT_TARGETS = ["packages/starlayer/starlayer", "packages/starlayer/tests"]


def _collect_py_files(raw_paths: list[str], repo_root: Path) -> list[Path]:
    """Resolve each ``--paths`` entry to one or more concrete ``.py``
    files - a directory is globbed for every ``**/*.py`` under it, a file
    is used as-is. Relative paths are resolved against ``repo_root``."""
    files: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = repo_root / path
        if path.is_dir():
            files.extend(sorted(p for p in path.glob("**/*.py")))
        else:
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    """Run the extractor and print a short summary. Returns 0 on success
    (the extractor itself is defensive - a malformed individual file is
    logged and skipped, not a reason for this to return nonzero)."""
    parser = argparse.ArgumentParser(description="Extract the StarLayer code knowledge graph.")
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help=(
            "One or more file/directory paths to extract (relative paths are "
            "resolved against the repo root). A directory is extracted "
            "recursively (**/*.py). Defaults to the library "
            "and its tests (packages/starlayer/starlayer and packages/starlayer/tests)."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = _REPO_ROOT
    raw_paths = args.paths if args.paths is not None else _DEFAULT_TARGETS
    target_paths = _collect_py_files(raw_paths, repo_root)

    from codekg.extractor import build

    dataset, tests_dataset = build.refresh(target_paths, repo_root)

    print(f"Extracted {len(target_paths)} file(s).")
    print(f"codekg.trig now contains {len(dataset)} triple(s) across {len(list(dataset.contexts()))} named graph(s).")
    if len(tests_dataset):
        print(f"testskg.trig now contains {len(tests_dataset)} triple(s) across {len(list(tests_dataset.contexts()))} named graph(s).")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
