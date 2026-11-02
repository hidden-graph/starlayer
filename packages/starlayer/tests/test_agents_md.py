"""AGENTS.md is the agent entry point: it must stay short and every file path it
names must exist. A long or stale entry file defeats its purpose."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "starlayer" / "starlayer"
MAX_LINES = 120
# build products, not committed (.gitignore): they exist only after the first query or KG test has built them
BUILT = ("codekg.trig", "testskg.trig", "starlayer-kg.trig")

_NOT_PATHS = ("from ", "pip ", "pytest", "python ", "ruff ", "cd ", "STARLAYER_", "--", "slkg:", "http")


def _paths(text):
    for token in re.findall(r"`([^`\n]+)`", text):
        token = token.strip().rstrip(",.;:")
        if token.startswith(_NOT_PATHS) or any(c in token for c in "*{}<> ="):
            continue
        if "/" in token or re.fullmatch(r"[\w.-]+\.(?:md|py|ttl|trig|toml|ya?ml)", token):
            yield token


def test_agents_md_stays_short():
    assert len((ROOT / "AGENTS.md").read_text().splitlines()) <= MAX_LINES


def test_claude_md_only_points_to_agents_md():
    text = (ROOT / "CLAUDE.md").read_text()
    assert "AGENTS.md" in text and len(text.splitlines()) <= 10


def test_every_path_in_agents_md_exists():
    # Paths are written relative to the repo root, the package directory (packages/starlayer/starlayer/), the tests
    # directory, or the code-KG tooling (tools/kg/).
    bases = [ROOT, PACKAGE, ROOT / "packages" / "starlayer", ROOT / "tools" / "kg"]
    paths = [p for p in _paths((ROOT / "AGENTS.md").read_text()) if p.rsplit("/", 1)[-1] not in BUILT]
    missing = [p for p in paths if not any((b / p).exists() for b in bases)]
    assert not missing, f"AGENTS.md names paths that do not exist: {missing}"
