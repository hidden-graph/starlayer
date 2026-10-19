"""scripts/check_docs.py - checks the hand-written documentation for rot.

1. Every relative link in a Markdown file or a notebook's Markdown cell points at a
   file that exists, and a ``#anchor`` on a ``.md`` target names a real heading
   (or an explicit ``<a id="...">``).
2. Every notebook in ``docs/guides/`` appears in ``docs/guides/README.md`` and in
   ``docs/user-guide-version.json``, and neither lists one that does not exist.
3. Every file path named in a ``Rules that bite`` block (the ``CLAUDE.md`` files) exists.
4. Every cell of a notebook in ``docs/guides/`` has an ``id``, unique within the notebook. Links from the curated
   knowledge graph to notebook cells use those ids.

Build-time only. Run through ``python scripts/build.py`` (step ``docs``) or alone:

    python scripts/check_docs.py        # exit 1 and list the problems
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "starlayer" / "starlayer"

# Directories whose Markdown is vendored or archived, not ours to check.
_SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "build", "dist", "vendor", "__pycache__", "archive"}
_LINK = re.compile(r"(?<!!)\[(?:[^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^(```|~~~)")


def _markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not _SKIP_PARTS & set(p.relative_to(ROOT).parts))


def _notebooks() -> list[Path]:
    return sorted(p for p in (ROOT / "docs").rglob("*.ipynb") if not _SKIP_PARTS & set(p.relative_to(ROOT).parts))


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_~]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        if in_fence:
            continue
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            slug = _slug(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1)))
            n = seen.get(slug, 0)
            found.add(slug if n == 0 else f"{slug}-{n}")
            seen[slug] = n + 1
        found.update(re.findall(r'<a\s+id="([^"]+)"', line))
    return found


def _links(text: str):
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`", "", line)  # code spans are not links
        yield from _LINK.findall(line)


def _check_links(source: Path, text: str, problems: list[str]) -> None:
    for url in _links(text):
        if url.startswith(("http://", "https://", "mailto:", "#")) or "<" in url:
            if url.startswith("#") and source.suffix == ".md" and url[1:] not in _anchors(source):
                problems.append(f"{source.relative_to(ROOT)}: no heading for {url}")
            continue
        target, _, anchor = url.partition("#")
        resolved = (source.parent / target).resolve()
        if not resolved.exists():
            problems.append(f"{source.relative_to(ROOT)}: broken link {url}")
        elif anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved):
            problems.append(f"{source.relative_to(ROOT)}: {target} has no heading for #{anchor}")


def check_links() -> list[str]:
    problems: list[str] = []
    for path in _markdown_files():
        _check_links(path, path.read_text(encoding="utf-8"), problems)
    for path in _notebooks():
        try:
            cells = json.loads(path.read_text(encoding="utf-8")).get("cells", [])
        except json.JSONDecodeError as exc:
            problems.append(f"{path.relative_to(ROOT)}: not valid notebook JSON ({exc.msg})")
            continue
        text = "\n".join("".join(c["source"]) for c in cells if c.get("cell_type") == "markdown")
        _check_links(path, text, problems)
    return problems


# Guides that are deliberately not indexed, with the reason. Empty now; add an entry only with a stated reason.
_UNINDEXED: dict[str, str] = {}


def check_guide_index() -> list[str]:
    guides = ROOT / "docs" / "guides"
    on_disk = {p.name for p in guides.glob("*.ipynb")} - set(_UNINDEXED)
    problems: list[str] = []
    readme = (guides / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "docs" / "user-guide-version.json").read_text(encoding="utf-8"))
    listed_in_manifest = {Path(p).name for p in manifest.get("artifacts", {}).get("notebook", [])}
    listed_in_readme = set(re.findall(r"\(([\w.-]+\.ipynb)\)", readme))
    for name in sorted(on_disk - listed_in_readme):
        problems.append(f"docs/guides/{name} is not linked from docs/guides/README.md")
    for name in sorted(listed_in_readme - on_disk):
        problems.append(f"docs/guides/README.md links {name}, which does not exist")
    for name in sorted(on_disk - listed_in_manifest):
        problems.append(f"docs/guides/{name} is not in docs/user-guide-version.json")
    for name in sorted(listed_in_manifest - on_disk):
        problems.append(f"docs/user-guide-version.json lists {name}, which does not exist")
    return problems


def check_rule_paths() -> list[str]:
    problems: list[str] = []
    bases = [ROOT, PACKAGE, ROOT / "packages" / "starlayer", ROOT / "packages" / "starlayer" / "docs"]
    for claude in sorted(PACKAGE.glob("*/CLAUDE.md")):
        text = claude.read_text(encoding="utf-8")
        if "## Rules that bite" not in text:
            continue
        block = text[text.index("## Rules that bite") :]
        block = block[: block.index("\n## ", 5)]
        for token in re.findall(r"`([^`\n]+)`", block):
            token = token.strip().rstrip(",.;:")
            if " " in token or any(c in token for c in "*{}<>=()$:\"'"):
                continue
            if "/" in token or re.fullmatch(r"[\w.-]+\.(?:md|py|ttl|trig|toml)", token):
                if not any((b / token).exists() for b in [*bases, claude.parent]):
                    problems.append(f"{claude.relative_to(ROOT)}: Rules-that-bite names a missing path {token}")
    return problems


def check_cell_ids() -> list[str]:
    problems: list[str] = []
    for path in sorted((ROOT / "docs" / "guides").glob("*.ipynb")):
        ids = [cell.get("id") for cell in json.loads(path.read_text(encoding="utf-8")).get("cells", [])]
        name = path.relative_to(ROOT)
        if not all(ids):
            problems.append(f"{name}: {ids.count(None)} cell(s) have no id")
        seen = [i for i in ids if i]
        if len(set(seen)) != len(seen):
            problems.append(f"{name}: cell ids are not unique")
    return problems


def main() -> int:
    # `--check` is accepted so build.py can pass it to every step; this script only ever checks.
    problems = [*check_links(), *check_guide_index(), *check_rule_paths(), *check_cell_ids()]
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)" if problems else "docs check passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
