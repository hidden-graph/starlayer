"""``scripts/renumber_guides.py``: the mechanical rewrites of the guide renumbering (plan: docs/working/guide-renumbering-plan-2026-11-25.md).

The notebooks here are small synthetic ones in ``tmp_path``; the real guides are only read (the mapping table, the dry run)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "renumber_guides.py"
spec = importlib.util.spec_from_file_location("renumber_guides", SCRIPT)
rg = importlib.util.module_from_spec(spec)
sys.modules["renumber_guides"] = rg  # a dataclass looks its module up
spec.loader.exec_module(rg)

A, B, C = "05a-shacl-node-expressions.ipynb", "05b-shacl-and-sparql.ipynb", "05c-shacl-inference-rules.ipynb"
N1 = "05.01-validating-with-shacl-1.2.ipynb"
REF = "06-starlayer-schemas-and-ontologies.ipynb"


def md(cell_id, text):
    return {"cell_type": "markdown", "id": cell_id, "metadata": {"tags": ["keep"]}, "source": text.splitlines(True)}


def code(cell_id, text):
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "source": text.splitlines(True),
        "execution_count": 3,
        "outputs": [{"name": "stdout", "output_type": "stream", "text": ["section 1\n"]}],
    }


def write_nb(folder: Path, name: str, cells) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    nb = {"cells": cells, "metadata": {"kernelspec": {"name": "python3"}}, "nbformat": 4, "nbformat_minor": 5}
    path = folder / name
    path.write_bytes(rg.dump(nb))
    return path


def texts(path: Path) -> dict[str, str]:
    return {c["id"]: "".join(c["source"]) for c in json.loads(path.read_text(encoding="utf-8"))["cells"]}


def result_for(name, cells, others=None, chapter="05", scope="primary", proposals=False):
    """Run the rules on one synthetic notebook; ``others`` are more guides (name -> cells) the links may point at."""
    nb = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    guides = {name: nb}
    for other, other_cells in (others or {}).items():
        guides[other] = {"cells": other_cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    return rg.rewrite_notebook(name, nb, guides, chapter, scope, proposals)


def new_texts(res):
    return {c["id"]: "".join(c["source"]) for c in res.notebook["cells"]}


def flags(res, category=None):
    return [(f.rule, f.cell, f.text) for f in res.flags if category in (None, f.category)]


# ---- the mapping table -------------------------------------------------------------------------------------------------------
def test_every_guide_of_the_mapping_exists_under_its_old_or_new_name():
    on_disk = {p.name for p in (ROOT / "docs/guides").glob("*.ipynb")}
    for row in rg.ROWS:
        assert row.old in on_disk or row.new in on_disk, row
    assert on_disk <= {n for row in rg.ROWS for n in (row.old, row.new)}  # no guide without a row


def test_the_mapping_names_are_unique_and_follow_the_pattern_without_a_clash():
    assert len(rg.ROWS) == 39
    news = [r.new for r in rg.ROWS]
    olds = [r.old for r in rg.ROWS]
    assert len(set(news)) == len(news) and len(set(olds)) == len(olds)
    for row in rg.ROWS:
        if row.renamed:
            assert re.match(r"^\d\d\.\d\d-", row.new), row
            assert row.new[6:] == row.old.split("-", 1)[1], "the title part of the name is kept"
            assert row.new not in olds, "a new name must not be the old name of another guide"
            assert row.old not in news
        else:
            assert row.old.startswith(("05.0", "appendix")), row
    assert sum(r.renamed for r in rg.ROWS) == 32
    assert len(rg.ID_MAP) == 32 and len(set(rg.ID_MAP.values())) == 32


def test_new_ids_run_without_a_gap_inside_each_chapter():
    for chapter in rg.STAGES:
        numbers = sorted(int(r.new_id[3:]) for r in rg.ROWS if r.chapter == chapter)
        assert numbers == list(range(1, len(numbers) + 1)), chapter
    assert rg.ID_MAP["05a"] == "05.04" and rg.ID_MAP["05h"] == "05.11" and rg.ID_MAP["07a"] == "07.01" and rg.ID_MAP["01"] == "01.01"
    assert {n for _o, n in rg.PARKED_MAP} == {"parked-02.03-oxigraph-wrapper.md", "parked-02.05-combining-comparing-graphs.md", "parked-02.07-owl-dl-reasoning.md"}


def test_the_stages_follow_the_users_order():
    assert rg.STAGES == ("05", "07", "06", "04", "03", "02", "01")
    assert rg.chapters_done("05") == {"05"} and rg.chapters_done("06") == {"05", "07", "06"}


# ---- headings ----------------------------------------------------------------------------------------------------------------
def test_each_heading_rule_fires_on_a_synthetic_notebook():
    cells = [
        md("t", "# 05a Title\n\nTagline."),
        md("r", "## How to run this notebook\n\nRun it."),
        md("s1", "## 1. First\n\ntext"),
        md("s11", "### 1.1 Sub\n\ntext"),
        md("s2", "## 2. Second\n\ntext\n\n#### 2.1.1 deep\n\n"),
        md("s21", "### 2.1 Sub two\n"),
        md("k", "## Known limitations\n"),
    ]
    # '#### 2.1.1' precedes '### 2.1' above on purpose: the order check must object, so build the valid order below instead
    cells[4] = md("s2", "## 2. Second\n\ntext\n")
    cells[5] = md("s21", "### 2.1 Sub two\n\n#### 2.1.1 deep four\n")
    res = result_for(A, cells)
    assert not res.problems
    out = new_texts(res)
    assert out["t"].startswith("# 05.04 Title\n")
    assert out["r"] == "## How to run this notebook\n\nRun it."  # unnumbered stays
    assert out["s1"].startswith("## 05.04.1 First\n")
    assert out["s11"].startswith("### 05.04.1.1 Sub\n")
    assert out["s2"].startswith("## 05.04.2 Second\n")
    assert out["s21"] == "### 05.04.2.1 Sub two\n\n#### 05.04.2.1.1 deep four\n"
    assert out["k"] == "## Known limitations\n"
    rules = sorted(rule for _c, rule, _o, _n in res.heading_changes)
    assert rules == ["H1", "H2", "H2", "H3", "H3", "H4"]


def test_relative_headings_and_overview_bullets_are_made_fully_qualified():
    cells = [
        md("t", "# 05.01 Validating\n"),
        md("s3", "## 05.01.3 Validate\n\n- **.3.1 First**: text\n- **.3.2 Second**: text\n"),
        md("h31", "### .3.1 First\n"),
        md("h311", "#### .3.1.1 Deeper\n"),
        md("h32", "### .3.2 Second\n"),
    ]
    cells.insert(1, md("s1", "## 05.01.1 One\n"))
    cells.insert(2, md("s2", "## 05.01.2 Two\n"))
    res = result_for(N1, cells, chapter="05")
    assert not res.problems
    out = new_texts(res)
    assert out["h31"] == "### 05.01.3.1 First\n" and out["h311"] == "#### 05.01.3.1.1 Deeper\n" and out["h32"] == "### 05.01.3.2 Second\n"
    assert out["s3"] == "## 05.01.3 Validate\n\n- **05.01.3.1 First**: text\n- **05.01.3.2 Second**: text\n"
    assert {r for _c, r, _o, _n in res.heading_changes} == {"H3-relative", "H4-relative"}
    assert [c.rule for c in res.changes] == ["bullet-relative", "bullet-relative"]
    assert out["t"] == "# 05.01 Validating\n" and out["s1"] == "## 05.01.1 One\n"  # already qualified: untouched


def test_a_heading_keeps_its_trailing_space_and_a_hash_line_in_code_or_a_fence_is_not_a_heading():
    cells = [
        md("t", "# 05a Title\n"),
        md("s1", "## 1. First \n\n```\n## 7. not a heading\n```\n\n"),
        code("c1", "# 9. comment line\nx = 1\n"),
    ]
    res = result_for(A, cells)
    out = new_texts(res)
    assert out["s1"] == "## 05.04.1 First \n\n```\n## 7. not a heading\n```\n\n"
    assert out["c1"] == "# 9. comment line\nx = 1\n"


def test_duplicate_gap_and_wrong_prefix_numbers_stop_the_notebook():
    dup = result_for(A, [md("t", "# 05a T\n"), md("a", "## 1. A\n"), md("b", "## 1. B\n")])
    assert any("duplicate" in p or "gap" in p for p in dup.problems)
    gap = result_for(A, [md("t", "# 05a T\n"), md("a", "## 1. A\n"), md("b", "## 3. C\n")])
    assert any("gap" in p for p in gap.problems)
    prefix = result_for(A, [md("t", "# 05a T\n"), md("a", "## 1. A\n"), md("b", "### 2.1 B\n")])
    assert any("extend" in p for p in prefix.problems)
    wrong_h1 = result_for(A, [md("t", "# 05c Wrong\n")])
    assert any("H1" in p for p in wrong_h1.problems)


def test_the_appendix_headings_and_an_unnumbered_h3_are_left_alone():
    res = result_for("appendix-b1-sqe-shared-parts.ipynb", [md("t", "# Appendix B1: x\n"), md("a", "## 1. Two queries\n")])
    assert new_texts(res)["a"] == "## 1. Two queries\n" and not res.heading_changes
    res = result_for(A, [md("t", "# 05a T\n"), md("a", "## 1. A\n"), md("u", "### How a list is stored\n")])
    assert new_texts(res)["u"] == "### How a list is stored\n" and not res.problems


def test_a_spec_citation_in_a_heading_is_kept():
    res = result_for(A, [md("t", "# 05a T\n"), md("a", '## 1. Declaring (§3, "Profiles of SHACL")\n')])
    assert new_texts(res)["a"] == '## 05.04.1 Declaring (§3, "Profiles of SHACL")\n'


# ---- links -------------------------------------------------------------------------------------------------------------------
def test_links_follow_the_mapping_with_anchors_and_text_equal_to_an_old_id():
    target = [md("t", "# 05a T\n"), md("h", "## 1. Selecting targets\n"), md("h7", "## 7. Extending the vocabulary: custom functions\n")]
    cells = [
        md("t", "# 05b T\n"),
        md("l", "See [05a](05a-shacl-node-expressions.ipynb), the [node guide](05a-shacl-node-expressions.ipynb#7.-Extending-the-vocabulary:-custom-functions) and [05a-shacl-node-expressions.ipynb](05a-shacl-node-expressions.ipynb)."),
    ]
    # the target holds ## 1 to ## 7: give it the headings it needs for the anchor to be real
    target = [md("t", "# 05a T\n")] + [md(f"h{i}", f"## {i}. H{i}\n") for i in range(1, 7)] + [md("h7", "## 7. Extending the vocabulary: custom functions\n")]
    res = result_for(B, cells, {A: target})
    out = new_texts(res)["l"]
    assert out == (
        "See [05.04](05.04-shacl-node-expressions.ipynb), the [node guide](05.04-shacl-node-expressions.ipynb#05.04.7-Extending-the-vocabulary:-custom-functions)"
        " and [05.04-shacl-node-expressions.ipynb](05.04-shacl-node-expressions.ipynb)."
    )
    rules = {c.rule for c in res.changes}
    assert {"link-target", "link-anchor", "link-text"} <= rules


def test_a_link_into_a_chapter_that_is_not_renamed_yet_is_left_alone_and_an_unknown_target_is_unmapped():
    cells = [md("t", "# 05b T\n"), md("l", "[x](02e-graphs-inferencing.ipynb) and [y](05e-owl-dl-reasoning.ipynb)")]
    res = result_for(B, cells)
    assert new_texts(res)["l"] == "[x](02e-graphs-inferencing.ipynb) and [y](05e-owl-dl-reasoning.ipynb)"
    assert [(f.category, f.rule) for f in res.flags] == [("unmapped", "link-target")]


def test_a_link_with_a_dotted_letter_text_is_a_decision_with_a_proposal_that_is_written_only_on_request():
    cells = [md("t", "# 05b T\n"), md("l", "see ([4.e](05e-shacl-profiling.ipynb)) for it")]
    res = result_for(B, cells)
    assert new_texts(res)["l"] == "see ([4.e](05.08-shacl-profiling.ipynb)) for it"
    assert flags(res, "decision") == [("dotted-id", "l", "[4.e](05e-shacl-profiling.ipynb)")]
    assert res.flags[0].proposal == "05.08"
    asked = result_for(B, cells, proposals=True)
    assert new_texts(asked)["l"] == "see ([05.08](05.08-shacl-profiling.ipynb)) for it"


def test_an_anchor_that_names_no_heading_is_a_decision_and_the_anchor_is_kept():
    target = [md("t", "# 05.01 V\n")]
    cells = [md("t", "# 05b T\n"), md("l", "[g](05.01-validating-with-shacl-1.2.ipynb#Known-limitations)")]
    res = result_for(B, cells, {N1: target})
    assert flags(res, "decision")[0][0] == "link-anchor"
    assert new_texts(res)["l"] == "[g](05.01-validating-with-shacl-1.2.ipynb#Known-limitations)"


def test_links_in_code_spans_and_fences_are_not_rewritten():
    cells = [md("t", "# 05b T\n"), md("l", "`[x](05a-shacl-node-expressions.ipynb)`\n\n```\n[x](05a-shacl-node-expressions.ipynb)\n```\n")]
    assert "".join(result_for(B, cells).notebook["cells"][1]["source"]) == "".join(cells[1]["source"])


# ---- in-text references ------------------------------------------------------------------------------------------------------
def test_a_section_reference_to_the_guides_own_heading_is_rewritten():
    cells = [
        md("t", "# 05b T\n"),
        md("a", "## 1. A\n"),
        md("b", "## 2. B\n\nSee section 1 and Section 2.\n\nThis section 2 is short; later sections 1 and 2 agree.\n"),
    ]
    out = new_texts(result_for(B, cells))["b"]
    assert out == "## 05.05.2 B\n\nSee section 05.05.1 and Section 05.05.2.\n\nThis section 05.05.2 is short; later sections 05.05.1 and 05.05.2 agree.\n"


def test_spec_sections_and_unresolved_numbers_are_not_rewritten_but_listed():
    cells = [
        md("t", "# 05b T\n"),
        md("a", "## 1. A\n\nThe draft says §4.2 and `section 1` stays in a code span.\n\nHints (its section 8.4) are open; section 9 of the [specification](https://www.w3.org/TR/x/).\n"),
    ]
    res = result_for(B, cells)
    out = new_texts(res)["a"]
    assert "§4.2" in out and "section 8.4" in out and "section 9 of" in out and "`section 1`" in out
    assert [r for r, _c, _t in flags(res, "left")] == ["spec-sign", "section-unresolved", "section-unresolved"]
    assert not [c for c in res.changes if c.rule == "section-ref"]


def test_a_section_next_to_another_guide_or_a_spec_marker_is_a_decision_not_a_rewrite():
    cells = [
        md("t", "# 05b T\n"),
        md("a", "## 1. A\n"),
        md("b", "## 2. B\n\nSee section 1 of the [rules guide](05c-shacl-inference-rules.ipynb).\n\nThe specification defines section 2 too.\n\n[05c](05c-shacl-inference-rules.ipynb), section 2, is next.\n"),
    ]
    other = {C: [md("t", "# 05c T\n")] + [md(f"c{i}", f"## {i}. C{i}\n") for i in (1, 2)]}
    res = result_for(B, cells, other)
    out = new_texts(res)["b"]
    assert "section 1 of the [rules guide](05.06-" in out and "specification defines section 2 too" in out and "), section 2, is next" in out
    assert sorted(r for r, _c, _t in flags(res, "decision")) == ["section-other-guide", "section-other-guide", "section-with-marker"]
    props = {f.text: f.proposal for f in res.flags if f.rule == "section-other-guide"}
    assert set(props.values()) == {"05.06.1", "05.06.2"}
    asked = result_for(B, cells, other, proposals=True)
    assert "section 05.06.1 of the [rules guide]" in new_texts(asked)["b"] and "), section 05.06.2, is next" in new_texts(asked)["b"]


def test_a_section_naming_a_guide_of_a_chapter_not_renamed_yet_is_deferred():
    cells = [md("t", "# 05b T\n"), md("a", "## 1. A\n\nSee [section 1 of the inferencing guide](02e-graphs-inferencing.ipynb).\n")]
    other = {"02e-graphs-inferencing.ipynb": [md("t", "# 02e T\n"), md("h", "## 1. X\n")]}
    res = result_for(B, cells, other)
    assert [(f.category, f.rule) for f in res.flags] == [("deferred", "section-other-guide")]
    assert "[section 1 of the inferencing guide](02e-graphs-inferencing.ipynb)" in new_texts(res)["a"]


def test_an_already_qualified_reference_is_left_alone():
    cells = [md("t", "# 05b T\n"), md("a", "## 1. A\n\nSee section 05.01.4.2 and section 05.05.1.\n")]
    res = result_for(B, cells)
    assert new_texts(res)["a"] == "## 05.05.1 A\n\nSee section 05.01.4.2 and section 05.05.1.\n" and not res.flags


def test_a_relative_number_in_prose_and_a_range_are_proposals():
    cells = [
        md("t", "# 05.01 V\n"),
        md("s1", "## 05.01.1 One\n"),
        md("s2", "## 05.01.2 Two\n"),
        md("s3", "## 05.01.3 Three\n"),
        md("s4", "## 05.01.4 Four\n"),
        md("h", "### .4.1 Sub\n"),
        md("p", "Entailment (see section .4.1) and sections 1-3 of this guide.\n"),
    ]
    res = result_for(N1, cells)
    assert new_texts(res)["p"] == "Entailment (see section .4.1) and sections 1-3 of this guide.\n"
    assert {(r, f.proposal) for (r, _c, _t), f in zip(flags(res), res.flags, strict=True)} == {
        ("section-relative", "05.01.4.1"),
        ("section-range", "05.01.1 to 05.01.3"),
    }
    asked = result_for(N1, cells, proposals=True)
    assert new_texts(asked)["p"] == "Entailment (see section 05.01.4.1) and sections 05.01.1 to 05.01.3 of this guide.\n"


def test_a_bare_old_id_in_prose_is_rewritten_and_a_bare_chapter_id_or_dotted_id_is_flagged():
    cells = [md("t", "# 05b T\n"), md("a", "Compare 05c, `05a` and 05.01. Also 4.a and the 04 guide; not 2026-05-26 or 05c-name.\n")]
    res = result_for(B, cells)
    out = new_texts(res)["a"]
    assert out.startswith("Compare 05.06, `05a` and 05.01. ")
    assert "not 2026-05-26 or 05c-name" in out
    assert sorted(r for r, _c, _t in flags(res, "decision")) == ["chapter-id", "dotted-id"]


def test_a_known_correction_is_a_decision_with_its_text():
    cells = [md("t", "# 05h T\n"), code("f5a00004", "# (StarLayerGraphs, see section 2.1); built by parsing Turtle.\nx = 1\n")]
    res = result_for("05h-shacl-evaluate.ipynb", cells)
    assert new_texts(res)["f5a00004"].startswith("# (StarLayerGraphs, see section 2.1);")
    assert flags(res, "decision") == [("known-fix", "f5a00004", "see section 2.1)")]
    asked = result_for("05h-shacl-evaluate.ipynb", cells, proposals=True)
    assert new_texts(asked)["f5a00004"].startswith("# (StarLayerGraphs, see section 05.01.2);")


# ---- code cells --------------------------------------------------------------------------------------------------------------
def test_a_code_cell_changes_only_on_a_comment_line_that_cites_a_section():
    source = 'g = "section 1"\n# `base` is the graph from section 1 (see below)\nrule = "stays safe in section 1"  # no match in a string\nx = 1  # see section 2\n'
    cells = [md("t", "# 05c T\n"), md("a", "## 1. A\n"), md("b", "## 2. B\n"), code("k", source)]
    res = result_for(C, cells)
    assert new_texts(res)["k"] == (
        'g = "section 1"\n# `base` is the graph from section 05.06.1 (see below)\nrule = "stays safe in section 1"  # no match in a string\n'
        "x = 1  # see section 05.06.2\n"
    )
    assert [c.rule for c in res.changes] == ["code-comment", "code-comment"]
    assert rg.verify_pair({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}, res.notebook) == []


def test_verify_pair_rejects_a_changed_id_a_changed_output_and_a_non_comment_code_change():
    cells = [md("t", "# 05c T\n"), code("k", "x = 1\n")]
    old = {"cells": cells, "metadata": {}}
    import copy

    bad = copy.deepcopy(old)
    bad["cells"][1]["outputs"] = []
    assert rg.verify_pair(old, bad)
    bad = copy.deepcopy(old)
    bad["cells"][1]["id"] = "other"
    assert rg.verify_pair(old, bad)
    bad = copy.deepcopy(old)
    bad["cells"][1]["source"] = ["x = 2\n"]
    assert rg.verify_pair(old, bad)


# ---- whole chapter: apply, formatting, idempotence ---------------------------------------------------------------------------
def make_tree(tmp_path: Path) -> Path:
    guides = tmp_path / "src" / "docs" / "guides"
    write_nb(guides, A, [
        md("t1", "[Guide Index](README.md)"),
        md("t", "# 05a Node expressions\n\nSee [05c](05c-shacl-inference-rules.ipynb), section 2 of it, and [05.01](05.01-validating-with-shacl-1.2.ipynb)."),
        md("h1", "## 1. One\n\nSee section 2 below.\n"),
        md("h2", "## 2. Two — ünïcode ✓\n"),
        code("k", "x = 1  # see section 1\n"),
    ])
    write_nb(guides, C, [
        md("t", "# 05c Rules\n\nBack to [05a](05a-shacl-node-expressions.ipynb#2.-Two-—-ünïcode-✓)."),
        md("h1", "## 1. One\n"),
        md("h2", "## 2. Two\n"),
    ])
    write_nb(guides, N1, [
        md("t", "# 05.01 Validating\n\n- **[node](05a-shacl-node-expressions.ipynb)**"),
        md("h3", "## 05.01.1 First\n"),
        md("h31", "### .1.1 Sub\n"),
    ])
    write_nb(guides, REF, [md("t", "# 06 Schemas\n\nSee [the rules](05c-shacl-inference-rules.ipynb) and section 2 here and [other](05a-shacl-node-expressions.ipynb).\n"), md("o", "unrelated text")])
    return guides


def test_apply_writes_the_new_names_with_ids_metadata_and_formatting_kept(tmp_path):
    guides = make_tree(tmp_path)
    target = tmp_path / "stage"
    written, problems = rg.apply_plan(guides, "05", target, None, False, False)
    assert problems == []
    out = target / "docs" / "guides"
    assert sorted(written) == sorted(["05.04-shacl-node-expressions.ipynb", "05.06-shacl-inference-rules.ipynb", N1, REF])
    assert not (out / A).exists() and not (out / C).exists()
    for name in written:
        old = guides / (rg.BY_FILE[name].old)
        new = out / name
        old_nb, new_nb = json.loads(old.read_text(encoding="utf-8")), json.loads(new.read_text(encoding="utf-8"))
        assert [c["id"] for c in old_nb["cells"]] == [c["id"] for c in new_nb["cells"]]
        assert [{k: v for k, v in c.items() if k != "source"} for c in old_nb["cells"]] == [{k: v for k, v in c.items() if k != "source"} for c in new_nb["cells"]]
        assert old_nb["metadata"] == new_nb["metadata"]
        assert new.read_bytes() == rg.dump(new_nb)  # indent=1, ensure_ascii=False, trailing newline
    a = texts(out / "05.04-shacl-node-expressions.ipynb")
    assert a["t"].startswith("# 05.04 Node expressions") and "[05.06](05.06-shacl-inference-rules.ipynb)" in a["t"]
    assert "[05.01](05.01-validating-with-shacl-1.2.ipynb)" in a["t"]
    assert a["h1"] == "## 05.04.1 One\n\nSee section 05.04.2 below.\n" and a["h2"] == "## 05.04.2 Two — ünïcode ✓\n"
    assert texts(out / "05.06-shacl-inference-rules.ipynb")["t"].endswith("(05.04-shacl-node-expressions.ipynb#05.04.2-Two-—-ünïcode-✓).")
    assert texts(out / N1)["h31"] == "### 05.01.1.1 Sub\n"
    # a referrer changes its link cell only; "section 2 here" in a guide of another chapter stays
    r = texts(out / REF)
    assert "(05.06-shacl-inference-rules.ipynb)" in r["t"] and "[other](05.04-shacl-node-expressions.ipynb)" in r["t"] and "section 2 here" in r["t"]
    assert r["o"] == "unrelated text"


def test_apply_is_idempotent_and_a_second_run_over_the_result_changes_nothing(tmp_path):
    guides = make_tree(tmp_path)
    first = tmp_path / "one"
    rg.apply_plan(guides, "05", first, None, False, False)
    again = tmp_path / "two"
    rg.apply_plan(guides, "05", again, None, False, False)
    for p in (first / "docs/guides").iterdir():
        assert p.read_bytes() == (again / "docs/guides" / p.name).read_bytes()
    # now take the result as the working guides (old names gone) and run again
    work = tmp_path / "work" / "docs" / "guides"
    work.mkdir(parents=True)
    for p in guides.iterdir():
        if p.name not in (A, C):
            (work / p.name).write_bytes(p.read_bytes())
    for p in (first / "docs/guides").iterdir():
        (work / p.name).write_bytes(p.read_bytes())
    third = tmp_path / "three"
    written, problems = rg.apply_plan(work, "05", third, None, False, False)
    assert problems == []
    for name in written:
        assert (third / "docs/guides" / name).read_bytes() == (work / name).read_bytes()
    plan = rg.make_plan(work, "05")
    assert not plan.referrers and all(not r.cells_changed for _n, r in plan.results)


def test_apply_refuses_to_write_anything_when_a_check_fails(tmp_path):
    guides = make_tree(tmp_path)
    write_nb(guides, B, [md("t", "# 05b T\n"), md("a", "## 1. A\n"), md("b", "## 1. B\n"), md("l", "[x](05z-nothing.ipynb)")])
    target = tmp_path / "stage"
    written, problems = rg.apply_plan(guides, "05", target, None, False, False)
    assert written == [] and problems and not target.exists()


def test_apply_with_only_writes_one_guide_and_remove_old_deletes_the_old_name_in_the_target(tmp_path):
    guides = make_tree(tmp_path)
    target = tmp_path / "stage"
    (target / "docs/guides").mkdir(parents=True)
    (target / "docs/guides" / C).write_text("old copy")
    written, problems = rg.apply_plan(guides, "05", target, C, False, True)
    assert problems == [] and "05.06-shacl-inference-rules.ipynb" in written
    assert not (target / "docs/guides" / C).exists()
    assert not (target / "docs/guides" / "05.04-shacl-node-expressions.ipynb").exists()


def test_a_notebook_not_in_the_repo_json_format_is_reported(tmp_path):
    guides = make_tree(tmp_path)
    path = guides / A
    path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2))
    plan = rg.make_plan(guides, "05")
    assert any("not in the repo's JSON format" in p for p in plan.problems)


def test_verify_tree_passes_on_a_renumbered_chapter_and_fails_before(tmp_path):
    guides = make_tree(tmp_path)
    root = tmp_path / "src"
    assert rg.verify_tree(root, "05")  # not renamed yet
    target = tmp_path / "stage"
    rg.apply_plan(guides, "05", target, None, False, True)
    done = tmp_path / "done" / "docs" / "guides"
    done.mkdir(parents=True)
    for p in (target / "docs/guides").iterdir():
        (done / p.name).write_bytes(p.read_bytes())
    problems = rg.verify_tree(tmp_path / "done", "05")
    assert [p for p in problems if "do not have" not in p] == []  # the synthetic tree holds only some of the chapter's guides
    assert any("do not have 05.02" in p for p in problems)


# ---- the other files, check and leftovers ------------------------------------------------------------------------------------
def make_files(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs/guides").mkdir(parents=True)
    (root / "docs/guides/README.md").write_text(
        "5. **[Validating](05.01-validating-with-shacl-1.2.ipynb)** - x\n"
        "   - **5.2 [Engine](05.02-starlayer-shacl-engine.ipynb)** - y\n"
        "   - **5.a [Node expressions](05a-shacl-node-expressions.ipynb)** - z; see 5.c\n"
        "   - **2.e [Inferencing](02e-graphs-inferencing.ipynb)** - w\n",
        encoding="utf-8",
    )
    (root / "docs/user-guide-version.json").write_text('{\n  "n": [\n      "docs/guides/05a-shacl-node-expressions.ipynb",\n   "docs/guides/02e-graphs-inferencing.ipynb"\n  ]\n}\n', encoding="utf-8")
    (root / "tools/kg/codekg/curated").mkdir(parents=True)
    (root / "tools/kg/codekg/curated/notebook-links.ttl").write_text(
        "nl:05a-abc123 a slkg:NotebookExample ;\n    slkg:notebookPath \"docs/guides/05a-shacl-node-expressions.ipynb\" ;\n    slkg:cellId \"abc123\" .\n\n"
        "nl:04d-n13-editors a slkg:NotebookExample ;\n    slkg:notebookPath \"docs/guides/05d-shacl-ui.ipynb\" ;\n    slkg:cellId \"n13-editors\" .\n\n"
        "nl:02e-x a slkg:NotebookExample ;\n    slkg:notebookPath \"docs/guides/02e-graphs-inferencing.ipynb\" ;\n    slkg:cellId \"x\" .\n",
        encoding="utf-8",
    )
    (root / "packages/starlayer/tests/repo").mkdir(parents=True)
    (root / "packages/starlayer/tests/repo/test_hunt_docs_notebooks.py").write_text(
        'def test_guide_04f_section_references_point_at_the_right_sections():\n    nb = _text("05f-shacl-subgraph-extraction.ipynb")\n    heads = dict(re.findall(r"^## (\\d+)\\. (.*)$", nb, re.M))\n',
        encoding="utf-8",
    )
    (root / "docs/design").mkdir(parents=True)
    (root / "docs/design/note.md").write_text("see docs/guides/05d-shacl-ui.ipynb and `05d`\n", encoding="utf-8")
    (root / "docs/working/archive").mkdir(parents=True)
    (root / "docs/working/archive/old.md").write_text("05d-shacl-ui.ipynb\n", encoding="utf-8")
    return root


def test_plan_files_lists_the_edits_of_each_file_and_apply_files_makes_them(tmp_path):
    root = make_files(tmp_path)
    edits = {e.path: e for e in rg.plan_files(root, "05")}
    assert set(edits) >= {"docs/guides/README.md", "docs/user-guide-version.json", "tools/kg/codekg/curated/notebook-links.ttl", "docs/design/note.md"}
    assert "docs/working/archive/old.md" not in edits
    written = rg.apply_files(root, "05", "all")
    assert "docs/guides/README.md" in written
    readme = (root / "docs/guides/README.md").read_text(encoding="utf-8")
    assert "**05.02 [Engine](05.02-starlayer-shacl-engine.ipynb)**" in readme
    assert "**05.04 [Node expressions](05.04-shacl-node-expressions.ipynb)**" in readme
    assert "**2.e [Inferencing](02e-graphs-inferencing.ipynb)**" in readme  # another chapter: later
    assert "5. **[Validating](05.01-" in readme
    assert (root / "docs/user-guide-version.json").read_text(encoding="utf-8").count("05.04-shacl-node-expressions.ipynb") == 1
    assert "02e-graphs-inferencing.ipynb" in (root / "docs/user-guide-version.json").read_text(encoding="utf-8")
    ttl = (root / "tools/kg/codekg/curated/notebook-links.ttl").read_text(encoding="utf-8")
    assert 'nl:05.04-abc123 a slkg:NotebookExample' in ttl and 'docs/guides/05.04-shacl-node-expressions.ipynb' in ttl
    assert "nl:05.07-n13-editors a" in ttl and "docs/guides/05.07-shacl-ui.ipynb" in ttl  # a stale id follows its file
    assert "nl:02e-x a" in ttl and "docs/guides/02e-graphs-inferencing.ipynb" in ttl
    test_file = (root / "packages/starlayer/tests/repo/test_hunt_docs_notebooks.py").read_text(encoding="utf-8")
    assert "def test_guide_05_09_section_references" in test_file and '"05.09-shacl-subgraph-extraction.ipynb"' in test_file
    assert r'^## 05\.09\.(\d+) (.*)$' in test_file
    assert "05.07-shacl-ui.ipynb" in (root / "docs/design/note.md").read_text(encoding="utf-8")
    assert (root / "docs/working/archive/old.md").read_text(encoding="utf-8") == "05d-shacl-ui.ipynb\n"
    assert rg.apply_files(root, "05", "all") == []  # idempotent


def test_apply_files_leaves_the_generated_ontology_copy_unless_asked_and_renames_parked_notes(tmp_path):
    root = make_files(tmp_path)
    gen = root / "packages/starlayer/starlayer/starontology/shacl/shacl12-shacl.ttl"
    src = root / "packages/starlayer/starlayer/starontology/_sources/shacl12-validation-shapes.ttl"
    for p in (gen, src):
        p.parent.mkdir(parents=True)
        p.write_text('rdfs:comment "(see docs/guides/05d-shacl-ui.ipynb)" .\n', encoding="utf-8")
    rg.apply_files(root, "05", "all")
    assert "05.07-shacl-ui.ipynb" in src.read_text(encoding="utf-8") and "05d-shacl-ui.ipynb" in gen.read_text(encoding="utf-8")
    rg.apply_files(root, "05", "all", generated=True)
    assert "05.07-shacl-ui.ipynb" in gen.read_text(encoding="utf-8")
    (root / "docs/guides/parked-02f-owl-dl-reasoning.md").write_text("# Section 4 of 02f\n", encoding="utf-8")
    assert "docs/guides/parked-02.07-owl-dl-reasoning.md" in rg.apply_files(root, "02", "cleanup")
    assert not (root / "docs/guides/parked-02f-owl-dl-reasoning.md").exists()


def test_check_and_leftovers_report_old_names_and_ids_with_their_class(tmp_path, capsys):
    root = make_files(tmp_path)
    hits = rg.scan(root, rg.walk_files(root), "05")
    kinds = {(h.path, h.kind, h.klass) for h in hits}
    assert ("docs/design/note.md", "stem", "must-fix") in kinds and ("docs/design/note.md", "id", "must-fix") in kinds
    assert ("docs/working/archive/old.md", "stem", "allowed-historical") in kinds
    assert not [h for h in hits if "02e" in h.text]
    assert rg.main(["--root", str(root), "leftovers", "--chapter", "05"]) == 1
    rg.apply_files(root, "05", "all")
    capsys.readouterr()
    assert rg.main(["--root", str(root), "check", "--chapter", "05"]) == 1  # a prose id and a dotted id are left for a person
    left = capsys.readouterr().out
    assert " stem " not in left and "docs/design/note.md:1: 05d" in left and "README.md:3: 5.c" in left


# ---- the command line --------------------------------------------------------------------------------------------------------
def test_plan_prints_and_writes_nothing_and_apply_needs_a_target(tmp_path, capsys):
    guides = make_tree(tmp_path)
    before = {p.name: p.read_bytes() for p in guides.iterdir()}
    root = tmp_path / "src"
    assert rg.main(["--root", str(root), "plan", "--chapter", "05"]) == 0
    out = capsys.readouterr().out
    assert "05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb" in out and "Referrer guides" in out
    assert {p.name: p.read_bytes() for p in guides.iterdir()} == before
    assert "](" not in re.sub(r"\[[^\]]*\]\([^)]*\)", "", out)  # no sentence of the report is a live link
    with pytest.raises(SystemExit):
        rg.main(["--root", str(root), "apply", "--chapter", "05"])
    assert rg.main(["--root", str(root), "apply", "--chapter", "05", "--target", str(tmp_path / "t")]) == 0
    assert (tmp_path / "t/docs/guides/05.04-shacl-node-expressions.ipynb").is_file()


def test_the_report_does_not_contain_a_markdown_link(tmp_path):
    guides = make_tree(tmp_path)
    text, _totals, _problems = rg.render_plan(rg.make_plan(guides, "05"))
    assert not re.search(r"\]\([^)]*\.ipynb", text)


# ---- the real guides ---------------------------------------------------------------------------------------------------------
def test_the_real_chapter_05_dry_run_has_no_unmapped_reference_and_no_check_failure():
    plan = rg.make_plan(ROOT / "docs/guides", "05")
    assert {n for n, _r in plan.results} <= {r.old for r in rg.ROWS} | {r.new for r in rg.ROWS}
    assert len(plan.results) == 11
    for name, res in plan.results + plan.referrers:
        assert not [f for f in res.flags if f.category == "unmapped"], name
        assert not res.problems, (name, res.problems)
    assert not [p for p in plan.problems if "JSON format" not in p], plan.problems


def test_the_real_chapter_05_dry_run_counts_follow_the_plan():
    plan = rg.make_plan(ROOT / "docs/guides", "05")
    heading_rules = [rule for _n, r in plan.results for _c, rule, _o, _n2 in r.heading_changes]
    if not (ROOT / "docs/guides/05a-shacl-node-expressions.ipynb").exists():
        pytest.skip("chapter 05 is already renumbered in the working guides")
    assert heading_rules.count("H1") == 8 and heading_rules.count("H2") == 54 and heading_rules.count("H3") == 37
    assert heading_rules.count("H3-relative") == 18 and heading_rules.count("H4-relative") == 16
    assert len(plan.referrers) == 5
