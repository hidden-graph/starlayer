"""codekg.extractor.stamp - the build stamp, and the freshness of the graph against the source.

``write_stamp()`` records one ``slkg:KGBuild`` node (time, git commit, whether the working tree had uncommitted Python
changes, file count) in its own named graph of ``codekg.trig``. ``freshness()`` compares a stamp with the repository
as it is now.

All the git calls are best effort: no git, no repository or a shallow clone just leaves the commit out.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from codekg import BUILD_GRAPH_IRI, BUILD_NODE_IRI, CODEKG_NS
from rdflib import RDF, Literal
from rdflib.namespace import XSD

# The Python files the extractor reads. Pathspecs, relative to the repository root.
SOURCE_PATHSPECS = ["packages/starlayer/starlayer/*.py", "packages/starlayer/tests/*.py"]


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=30, check=False)  # noqa: S603, S607
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def head_commit(repo_root: Path) -> str | None:
    return _git(repo_root, "rev-parse", "HEAD")


def uncommitted_python_changes(repo_root: Path) -> int | None:
    """How many extracted Python files differ from HEAD in the working tree (including untracked ones)."""
    out = _git(repo_root, "status", "--porcelain", "--", *SOURCE_PATHSPECS)
    return None if out is None else len([line for line in out.splitlines() if line.strip()])


def write_stamp(dataset, repo_root: Path, file_count: int, now: datetime | None = None) -> None:
    """Replace the build stamp in ``dataset`` (its own named graph) with one for a run that just extracted ``file_count`` files."""
    graph = dataset.graph(BUILD_GRAPH_IRI)
    graph.remove((None, None, None))
    node = BUILD_NODE_IRI
    graph.add((node, RDF.type, CODEKG_NS.KGBuild))
    graph.add((node, CODEKG_NS.builtAt, Literal((now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"), datatype=XSD.dateTime)))
    graph.add((node, CODEKG_NS.sourceFileCount, Literal(file_count, datatype=XSD.integer)))
    commit = head_commit(repo_root)
    if commit:
        graph.add((node, CODEKG_NS.builtFromCommit, Literal(commit)))
        changes = uncommitted_python_changes(repo_root)
        if changes is not None:
            graph.add((node, CODEKG_NS.hadUncommittedChanges, Literal(changes > 0, datatype=XSD.boolean)))


@dataclass(frozen=True)
class Freshness:
    """A stamp compared with the repository now. ``commits_since`` and ``uncommitted`` are ``None`` when unknown."""

    built_at: str
    commit: str | None
    commits_since: int | None
    uncommitted: int | None

    @property
    def current(self) -> bool:
        return self.commits_since == 0 and self.uncommitted == 0

    def sentence(self) -> str:
        built = self.built_at[:10]
        if self.commit is None:
            return f"KG built {built} (commit unknown)."
        text = f"KG built {built} from commit {self.commit[:7]}"
        if self.commits_since is None or self.uncommitted is None:
            return text + "."
        if self.current:
            return text + "; the source has not changed since."
        return text + f"; since then {self.commits_since} commit(s) and {self.uncommitted} uncommitted file(s) changed the source."


def freshness(graph, repo_root: Path) -> Freshness | None:
    """Compare the stamp found in ``graph`` (any graph holding the ``slkg:KGBuild`` triples) with the repository now."""
    node = next(graph.subjects(RDF.type, CODEKG_NS.KGBuild), None)
    if node is None:
        return None
    built_at = str(graph.value(node, CODEKG_NS.builtAt) or "")
    commit_value = graph.value(node, CODEKG_NS.builtFromCommit)
    commit = str(commit_value) if commit_value is not None else None
    since = uncommitted = None
    if commit:
        counted = _git(repo_root, "rev-list", "--count", f"{commit}..HEAD", "--", *SOURCE_PATHSPECS)
        since = int(counted) if counted and counted.isdigit() else None
        uncommitted = uncommitted_python_changes(repo_root)
    return Freshness(built_at, commit, since, uncommitted)
