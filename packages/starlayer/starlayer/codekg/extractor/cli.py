"""starlayer.codekg.extractor.cli - the extractor's command-line entry
point, wrapped by the thin ``scripts/build_codekg.py`` launcher at the
repo root.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Five parents up from this file (packages/starlayer/starlayer/codekg/
# extractor/cli.py) lands on the repo root - Path.parents[0] is already
# this file's immediate containing directory (extractor/), so reaching
# the repo root crosses: extractor -> codekg -> starlayer(inner pkg) ->
# starlayer (packages/starlayer) -> packages -> <repo root>.
_REPO_ROOT = Path(__file__).resolve().parents[5]

_DEFAULT_TARGET = Path("packages/starlayer/starlayer/graph/model")


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
            "recursively (**/*.py). Defaults to "
            "packages/starlayer/starlayer/graph/model/ if omitted."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = _REPO_ROOT
    raw_paths = args.paths if args.paths is not None else [str(_DEFAULT_TARGET)]
    target_paths = _collect_py_files(raw_paths, repo_root)

    from starlayer.codekg.extractor import build

    dataset = build.refresh(target_paths, repo_root)
    total_triples = len(dataset)

    from starlayer.codekg.extractor import stamp

    stamp.append_changelog_entry(Path(__file__).resolve().parents[1] / "CHANGELOG.md", repo_root, len(target_paths), total_triples)

    print(f"Extracted {len(target_paths)} file(s).")
    print(f"codekg.trig now contains {total_triples} triple(s) across {len(list(dataset.contexts()))} named graph(s).")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
