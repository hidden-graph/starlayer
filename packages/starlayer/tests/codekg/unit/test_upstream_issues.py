"""The curated list of upstream bugs and the code that works around each (``curated/upstream-issues.ttl``)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import RDF, Graph, Literal
from rdflib.namespace import DCTERMS
from starlayer.codekg import (
    CODEKG_NS,
    CURATED_DIR,
    CURATED_GRAPH_IRI,
    get_codekg_dataset,
)

ISSUES_TTL = CURATED_DIR / "upstream-issues.ttl"
SHAPES_TTL = CURATED_DIR.parent / "upstream-issues-shapes.ttl"
REPO_ROOT = Path(__file__).resolve().parents[5]

# Workarounds in the *_patches modules that are not for a bug in a library we build on.
NOT_UPSTREAM_BUGS = {
    "patch_relational_expression_tt_hash_equality": "complements StarLayer's own triple-term encoding",
    "patch_order_by_tt_hash_term_kind": "complements StarLayer's own triple-term encoding",
    "patch_bgp_skips_encoding_triples": "hides StarLayer's own triple-term encoding triples",
}
# A real rdflib bug that is worked around but has no entry in docs/upstream-issues/ yet: write it up, then link it.
WORKAROUND_WITHOUT_WRITE_UP = {"patch_evalmodify_default_graph_selection"}


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


def test_every_workaround_exists_in_the_code_graph(graph):
    dataset = get_codekg_dataset()
    known = {str(o) for ctx in dataset.contexts() for o in ctx.objects(None, DCTERMS.identifier)}
    cited = {str(o) for o in graph.objects(None, CODEKG_NS.workedAroundByIdentifier)}
    assert len(cited) >= 20
    assert not sorted(cited - known), f"workarounds the code KG does not have: {sorted(cited - known)}"


def test_every_patch_function_is_recorded_as_a_workaround_or_explained(graph):
    """A ``patch_*`` function in the query patch modules is a workaround for some bug; each must be on the list or excused."""
    cited = {str(o).rsplit(".", 1)[-1] for o in graph.objects(None, CODEKG_NS.workedAroundByIdentifier)}
    defined = set()
    for path in (REPO_ROOT / "packages/starlayer/starlayer/graph/query").glob("*_patches.py"):
        defined |= set(re.findall(r"^def (patch_\w+)\(", path.read_text(encoding="utf-8"), re.M))
    unexplained = defined - cited - set(NOT_UPSTREAM_BUGS) - WORKAROUND_WITHOUT_WRITE_UP
    assert not unexplained, f"patch functions not on the upstream list: {sorted(unexplained)}"
    assert cited & defined, "the check found no patch functions at all"
    assert set(NOT_UPSTREAM_BUGS) <= defined and WORKAROUND_WITHOUT_WRITE_UP <= defined, "an exemption names a function that is gone"


def test_the_curated_graph_carries_the_issues():
    curated = get_codekg_dataset(include_curated=True).get_context(CURATED_GRAPH_IRI)
    assert next(curated.subjects(RDF.type, CODEKG_NS.UpstreamIssue), None) is not None
