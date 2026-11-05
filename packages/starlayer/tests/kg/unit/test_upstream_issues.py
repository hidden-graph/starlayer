"""The curated list of upstream bugs and the code that works around each (``curated/upstream-issues.ttl``)."""

from __future__ import annotations

import re
from pathlib import Path

import codekg
import pytest
from codekg import (
    CODEKG_NS,
    CURATED_DIR,
    CURATED_GRAPH_IRI,
    get_codekg_dataset,
)
from rdflib import RDF, Graph, Literal
from rdflib.namespace import DCTERMS

ISSUES_TTL = CURATED_DIR / "upstream-issues.ttl"
SHAPES_TTL = CURATED_DIR.parent / "upstream-issues-shapes.ttl"
REPO_ROOT = Path(__file__).resolve().parents[5]

@pytest.fixture(scope="module")
def graph():
    return Graph().parse(ISSUES_TTL, format="turtle")


def _conforms(g: Graph) -> bool:
    import starlayer.shacl

    return starlayer.shacl.validate(g, shacl_graph=Graph().parse(SHAPES_TTL, format="turtle")).conforms


def test_the_issues_conform_to_their_shapes(graph):
    assert _conforms(graph)
    assert len(list(graph.subjects(RDF.type, CODEKG_NS.UpstreamIssue))) >= 25


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda g, n: g.remove((n, CODEKG_NS.issueStatus, None)),
        lambda g, n: g.set((n, CODEKG_NS.issueStatus, Literal("shrug"))),
        lambda g, n: g.set((n, CODEKG_NS.upstreamProject, Literal("numpy"))),
        lambda g, n: g.remove((n, CODEKG_NS.workedAroundByIdentifier, None)),
        lambda g, n: g.set((n, CODEKG_NS.issueDocPath, Literal("elsewhere/notes.md"))),
    ],
    ids=["no-status", "unknown-status", "unknown-project", "worked-around-but-no-code", "bad-doc-path"],
)
def test_the_shapes_notice_a_damaged_issue(graph, corrupt):
    copy = Graph()
    for triple in graph:
        copy.add(triple)
    node = next(copy.subjects(CODEKG_NS.issueStatus, Literal("worked-around")))
    assert _conforms(copy)
    corrupt(copy, node)
    assert not _conforms(copy)


def test_every_write_up_has_the_entry_the_issue_names(graph):
    """The document exists and has a heading for that number, so the link is to something real."""
    for issue in graph.subjects(RDF.type, CODEKG_NS.UpstreamIssue):
        number = graph.value(issue, CODEKG_NS.issueNumber)
        if number is None:
            continue
        text = (REPO_ROOT / str(graph.value(issue, CODEKG_NS.issueDocPath))).read_text(encoding="utf-8")
        assert re.search(rf"^## (?:Issue )?{number}\b", text, re.M), f"{issue}: no entry {number} in its write-up"


def test_every_write_up_entry_is_in_the_list(graph):
    """The other direction: an entry added to a write-up is not forgotten here."""
    listed = {(str(graph.value(i, CODEKG_NS.issueDocPath)), int(n)) for i in graph.subjects(RDF.type, CODEKG_NS.UpstreamIssue) if (n := graph.value(i, CODEKG_NS.issueNumber)) is not None}
    for path in sorted((REPO_ROOT / "docs" / "upstream-issues").glob("*-upstream-issues.md")):
        relative = str(path.relative_to(REPO_ROOT))
        found = {int(m) for m in re.findall(r"^## (?:Issue )?(\d+)\b", path.read_text(encoding="utf-8"), re.M)}
        assert found == {n for p, n in listed if p == relative}, f"{relative}: entries {sorted(found)} vs listed"


@pytest.mark.deferred
def test_every_workaround_exists_in_the_code_graph(graph, codekg_dataset):
    dataset = codekg_dataset
    known = {o.value for n in dataset.graph_names() for o in dataset.graph(n).objects(None, DCTERMS.identifier)}
    cited = {str(o) for o in graph.objects(None, CODEKG_NS.workedAroundByIdentifier)}
    assert len(cited) >= 5
    assert not sorted(cited - known), f"workarounds the code KG does not have: {sorted(cited - known)}"


def test_the_curated_graph_carries_the_issues(monkeypatch, tmp_path):
    monkeypatch.setattr(codekg, "TESTSKG_TRIG_PATH", tmp_path / "absent-tests.trig")
    monkeypatch.setattr(codekg, "CODEKG_TRIG_PATH", tmp_path / "absent.trig")  # the curated files do not need the 15 s parse
    curated = get_codekg_dataset(include_curated=True).graph(CURATED_GRAPH_IRI)
    assert next(curated.subjects(RDF.type, CODEKG_NS.UpstreamIssue), None) is not None
