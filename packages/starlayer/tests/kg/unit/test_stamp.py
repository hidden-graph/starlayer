"""The code KG's build stamp, how it compares with the repository, and the automatic changelog entry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from codekg import BUILD_GRAPH_IRI, CODEKG_NS
from codekg.extractor import stamp
from codekg.extractor.build import refresh
from rdflib import RDF
from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

PKG = Path("packages/starlayer/starlayer/widgets")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / PKG).mkdir(parents=True)
    module = root / PKG / "thing.py"
    module.write_text("def f():\n    pass\n", encoding="utf-8")
    return root, module


def _build(root: Path, module: Path, tmp_path: Path) -> tuple[StarLayerDataset, Path]:
    trig = tmp_path / "codekg.trig"
    refresh([module], root, trig_path=trig)
    dataset = StarLayerDataset()
    dataset.parse(str(trig), format="trig12")
    return dataset, trig


def _freshness(dataset, root):
    return stamp.freshness(dataset.get_context(BUILD_GRAPH_IRI), root)


def test_a_build_outside_git_is_stamped_without_a_commit(repo, tmp_path):
    root, module = repo
    dataset, _ = _build(root, module, tmp_path)
    graph = dataset.get_context(BUILD_GRAPH_IRI)
    node = next(graph.subjects(RDF.type, CODEKG_NS.KGBuild))
    assert graph.value(node, CODEKG_NS.sourceFileCount).toPython() == 1
    assert graph.value(node, CODEKG_NS.builtAt) is not None
    assert graph.value(node, CODEKG_NS.builtFromCommit) is None
    assert "commit unknown" in _freshness(dataset, root).sentence()


def test_a_second_build_replaces_the_stamp(repo, tmp_path):
    root, module = repo
    _, trig = _build(root, module, tmp_path)
    refresh([module], root, trig_path=trig)
    dataset = StarLayerDataset()
    dataset.parse(str(trig), format="trig12")
    assert len(list(dataset.get_context(BUILD_GRAPH_IRI).subjects(RDF.type, CODEKG_NS.KGBuild))) == 1
    assert len(list(dataset.get_context(BUILD_GRAPH_IRI).objects(None, CODEKG_NS.builtAt))) == 1


def test_freshness_follows_the_repository(repo, tmp_path):
    root, module = repo
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")

    dataset, _ = _build(root, module, tmp_path)
    found = _freshness(dataset, root)
    assert found.current and "has not changed since" in found.sentence()

    module.write_text("def f():\n    return 1\n", encoding="utf-8")
    found = _freshness(dataset, root)
    assert not found.current and found.uncommitted == 1 and "1 uncommitted" in found.sentence()

    _git(root, "commit", "-q", "-am", "change f")
    found = _freshness(dataset, root)
    assert found.commits_since == 1 and found.uncommitted == 0 and not found.current

    (root / "README.md").write_text("not python\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs only")
    assert _freshness(dataset, root).commits_since == 1, "a commit that changes no Python file does not make the KG stale"


def test_a_build_from_a_dirty_tree_says_so(repo, tmp_path):
    root, module = repo
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    module.write_text("def f():\n    return 2\n", encoding="utf-8")
    dataset, _ = _build(root, module, tmp_path)
    graph = dataset.get_context(BUILD_GRAPH_IRI)
    node = next(graph.subjects(RDF.type, CODEKG_NS.KGBuild))
    assert graph.value(node, CODEKG_NS.hadUncommittedChanges).toPython() is True


@pytest.mark.deferred
def test_the_built_graph_carries_a_stamp(built_kg_files):
    """The stamp is in the graph file the extractor writes, not only in fresh builds."""
    from codekg import CODEKG_TRIG_PATH

    text = CODEKG_TRIG_PATH.read_text(encoding="utf-8")
    assert "KGBuild" in text and "builtAt" in text
