"""Hand-made links from guide notebook cells to code: the vocabulary, the checker, and its four outcomes."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from rdflib import RDF, Graph, Literal
from starlayer.codekg import CODEKG_NS, CURATED_DIR, notebook_links

SHAPES_TTL = CURATED_DIR.parent / "notebook-links-shapes.ttl"


# ---------------------------------------------------------------------------
# the committed links


def test_every_committed_link_is_current():
    """What ``build.py`` enforces: no cell has changed, moved or lost its symbol since its link was reviewed."""
    stale = [(f.link.name, f.status, f.detail) for f in notebook_links.check() if f.status != notebook_links.UNCHANGED]
    assert not stale, stale
    assert len(notebook_links.load_links()) >= 20


def _conforms(graph: Graph) -> bool:
    import starlayer.shacl

    return starlayer.shacl.validate(graph, shacl_graph=Graph().parse(SHAPES_TTL, format="turtle")).conforms


def test_the_links_conform_to_their_shapes():
    assert _conforms(Graph().parse(notebook_links.LINKS_TTL, format="turtle"))


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda g, n: g.remove((n, CODEKG_NS.cellId, None)),
        lambda g, n: g.set((n, CODEKG_NS.cellHash, Literal("not-a-hash"))),
        lambda g, n: g.set((n, CODEKG_NS.notebookPath, Literal("somewhere/else.ipynb"))),
        lambda g, n: g.remove((n, CODEKG_NS.demonstratesIdentifier, None)),
        lambda g, n: g.remove((n, CODEKG_NS.reviewedOn, None)),
    ],
    ids=["no-cell-id", "bad-hash", "bad-path", "no-symbol", "no-date"],
)
def test_the_shapes_notice_a_damaged_link(corrupt):
    graph = Graph().parse(notebook_links.LINKS_TTL, format="turtle")
    node = next(graph.subjects(RDF.type, CODEKG_NS.NotebookExample))
    assert _conforms(graph)
    corrupt(graph, node)
    assert not _conforms(graph)


# ---------------------------------------------------------------------------
# the four outcomes, on a small repository built in a temporary directory

NOTEBOOK = "docs/guides/a.ipynb"


def _write_notebook(root: Path, name: str, cells: dict[str, str]) -> None:
    body = {
        "cells": [
            {"cell_type": "code", "id": cid, "metadata": {}, "source": src.splitlines(keepends=True), "outputs": [], "execution_count": None}
            for cid, src in cells.items()
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path = root / "docs" / "guides" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _links_file(root: Path, source: str) -> Path:
    path = root / "links.ttl"
    path.write_text(
        f"""@prefix nl: <https://github.com/hidden-graph/starlayer/ns/codekg/curated/notebook-links#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix slkg: <https://github.com/hidden-graph/starlayer/ns/codekg#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

nl:one a slkg:NotebookExample ;
    slkg:notebookPath "{NOTEBOOK}" ;
    slkg:cellId "c1" ;
    slkg:cellHash "{notebook_links.cell_hash(source)}" ;
    slkg:reviewedOn "2026-01-01"^^xsd:date ;
    rdfs:comment "calls parse_thing" ;
    slkg:demonstratesIdentifier "pkg.mod.parse_thing" .
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def repo(tmp_path):
    source = "x = parse_thing(data)\nprint(x)\n"
    _write_notebook(tmp_path, "a.ipynb", {"c0": "intro = 1\n", "c1": source})
    return tmp_path, _links_file(tmp_path, source), source


def _status(repo_tuple) -> list[str]:
    root, links, _ = repo_tuple
    return [f.status for f in notebook_links.check(notebook_links.load_links(links), root)]


def test_an_untouched_cell_is_unchanged(repo):
    assert _status(repo) == ["unchanged"]


def test_whitespace_and_reordering_are_not_edits(repo):
    root, _links, source = repo
    _write_notebook(root, "a.ipynb", {"c1": source.replace("\n", "   \n") + "\n\n", "c0": "intro = 1\n"})
    assert _status(repo) == ["unchanged"]


def test_an_edited_cell_is_reported(repo):
    root, _links, _source = repo
    _write_notebook(root, "a.ipynb", {"c0": "intro = 1\n", "c1": "x = parse_thing(data, strict=True)\nprint(x)\n"})
    assert _status(repo) == ["edited"]


def test_a_cell_that_lost_its_symbol_is_broken(repo):
    root, _links, _source = repo
    _write_notebook(root, "a.ipynb", {"c0": "intro = 1\n", "c1": "x = something_else(data)\n"})
    findings = notebook_links.check(notebook_links.load_links(repo[1]), root)
    assert [f.status for f in findings] == ["broken"] and "parse_thing" in findings[0].detail


def test_a_removed_cell_is_broken_and_a_cell_moved_to_another_notebook_is_found(repo):
    root, _links, source = repo
    _write_notebook(root, "a.ipynb", {"c0": "intro = 1\n"})
    assert _status(repo) == ["broken"]
    _write_notebook(root, "b.ipynb", {"zz": source})
    findings = notebook_links.check(notebook_links.load_links(repo[1]), root)
    assert [f.status for f in findings] == ["moved"] and "b.ipynb#zz" in findings[0].detail


def test_restamp_records_a_review_and_changes_nothing_else(repo):
    root, links, _source = repo
    edited = "x = parse_thing(data, strict=True)\nprint(x)\n"
    _write_notebook(root, "a.ipynb", {"c0": "intro = 1\n", "c1": edited})
    before = links.read_text(encoding="utf-8")
    assert notebook_links.restamp(["one"], today=date(2026, 6, 1), root=root, path=links) == ["one"]
    after = links.read_text(encoding="utf-8")
    assert _status(repo) == ["unchanged"]
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b]
    assert len(changed) == 2 and {a.split()[0] for a, _ in changed} == {"slkg:cellHash", "slkg:reviewedOn"}
    assert 'slkg:reviewedOn "2026-06-01"^^xsd:date' in after
    with pytest.raises(KeyError):
        notebook_links.restamp(["nope"], root=root, path=links)


def test_the_hash_ignores_trailing_whitespace_but_not_content():
    assert notebook_links.cell_hash("a = 1  \n\n") == notebook_links.cell_hash("a = 1")
    assert notebook_links.cell_hash("a = 1") != notebook_links.cell_hash("a = 2")


def test_the_checker_script_exits_nonzero_for_a_stale_link(tmp_path):
    """The build step must fail, not just report: copy the real links, edit a real cell, run the script's check."""
    links = notebook_links.load_links()
    victim = links[0]
    path = notebook_links.REPO_ROOT / victim.notebook
    original = path.read_text(encoding="utf-8")
    scratch = tmp_path / "docs" / "guides"
    scratch.mkdir(parents=True)
    shutil.copytree(notebook_links.GUIDES, scratch, dirs_exist_ok=True)
    notebook = json.loads((tmp_path / victim.notebook).read_text(encoding="utf-8"))
    cell = next(c for c in notebook["cells"] if c["id"] == victim.cell_id)
    cell["source"] = [*cell["source"], "\n# a new comment"]
    (tmp_path / victim.notebook).write_text(json.dumps(notebook, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    findings = notebook_links.check(links, tmp_path)
    assert any(f.link.name == victim.name and f.status == notebook_links.EDITED for f in findings)
    assert path.read_text(encoding="utf-8") == original  # the real notebook was never touched
