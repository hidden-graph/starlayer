"""``scripts/guide_staging.py``: edits are staged, and pushed to the working guides only as a batch that does not overwrite the
maintainer's own changes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "guide_staging.py"
spec = importlib.util.spec_from_file_location("guide_staging", SCRIPT)
gs = importlib.util.module_from_spec(spec)
sys.modules["guide_staging"] = gs  # a dataclass looks its module up
spec.loader.exec_module(gs)


def _cell(cell_id, text, kind="markdown", outputs=None):
    cell = {"cell_type": kind, "id": cell_id, "metadata": {}, "source": text.splitlines(True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=outputs or [])
    return cell


def _write(root: Path, relative: str, cells) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")


def _read(root: Path, relative: str) -> list[dict]:
    return json.loads((root / relative).read_text())["cells"]


def _texts(root: Path, relative: str) -> dict[str, str]:
    return {c["id"]: "".join(c["source"]) for c in _read(root, relative)}


@pytest.fixture
def tree(tmp_path):
    nb = "docs/guides/a.ipynb"
    _write(tmp_path, nb, [_cell("c1", "one"), _cell("c2", "two"), _cell("c3", "three", "code", [{"name": "stdout", "output_type": "stream", "text": ["old"]}])])
    (tmp_path / "docs/guides/README.md").write_text("index\n")
    (tmp_path / "docs/user-guide-version.json").write_text("{}\n")
    gs.main(["--root", str(tmp_path), "init"])
    return tmp_path, nb


def run(root, *args):
    return gs.main(["--root", str(root), *args])


def test_an_edit_in_staging_does_not_reach_the_working_guide_until_pushed(tree):
    root, nb = tree
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "ONE"), _cell("c2", "two"), _cell("c3", "three", "code")])
    assert _texts(root, nb)["c1"] == "one"
    assert run(root, "push") == 0  # a dry run
    assert _texts(root, nb)["c1"] == "one"
    assert run(root, "push", "--yes") == 0
    assert _texts(root, nb)["c1"] == "ONE"


def test_the_maintainers_edit_to_another_cell_is_kept(tree):
    root, nb = tree
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "ONE"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO by the maintainer"), _cell("c3", "three", "code")])
    run(root, "push", "--yes")
    assert _texts(root, nb) == {"c1": "ONE", "c2": "TWO by the maintainer", "c3": "three"}


def test_a_cell_changed_on_both_sides_is_a_conflict_and_the_file_is_not_written(tree):
    root, nb = tree
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "mine"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "yours"), _cell("c2", "two"), _cell("c3", "three", "code")])
    assert run(root, "push", "--yes") == 1
    assert _texts(root, nb)["c1"] == "yours"


def test_new_cells_are_inserted_after_their_predecessor(tree):
    root, nb = tree
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "one"), _cell("n1", "new"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "two"), _cell("w1", "yours new"), _cell("c3", "three", "code")])
    run(root, "push", "--yes")
    assert [c["id"] for c in _read(root, nb)] == ["c1", "n1", "c2", "w1", "c3"]


def test_a_removed_cell_is_removed_unless_the_maintainer_changed_it(tree):
    root, nb = tree
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "one"), _cell("c3", "three", "code")])
    run(root, "push", "--yes")
    assert [c["id"] for c in _read(root, nb)] == ["c1", "c3"]


def test_regenerated_output_travels_unless_the_maintainer_also_ran_the_cell(tree):
    root, nb = tree
    new = [{"name": "stdout", "output_type": "stream", "text": ["new"]}]
    _write(root / "docs/guides-staging/stage", nb, [_cell("c1", "one"), _cell("c2", "two"), _cell("c3", "three", "code", new)])
    run(root, "push", "--yes")
    assert _read(root, nb)[2]["outputs"] == new


def test_pull_brings_the_maintainers_edit_into_staging(tree):
    root, nb = tree
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO"), _cell("c3", "three", "code")])
    run(root, "pull")
    assert _texts(root / "docs/guides-staging/stage", nb)["c2"] == "TWO"


def test_a_pushed_file_is_backed_up_and_other_files_are_compared_whole(tree):
    root, nb = tree
    (root / "docs/guides-staging/stage/docs/guides/README.md").write_text("index 2\n")
    run(root, "push", "--yes")
    assert (root / "docs/guides/README.md").read_text() == "index 2\n"
    backups = list((root / "docs/guides-staging/.backup").rglob("README.md"))
    assert backups and backups[0].read_text() == "index\n"


def test_a_guide_renamed_in_staging_is_moved_in_the_working_guides(tree):
    root, nb = tree
    stage = root / "docs/guides-staging/stage"
    (stage / nb).rename(stage / "docs/guides/b.ipynb")
    run(root, "push", "--yes")
    assert not (root / nb).exists() and (root / "docs/guides/b.ipynb").exists()


def test_a_pushed_notebook_keeps_its_key_order_and_an_unchanged_notebook_is_not_rewritten(tree):
    root, nb = tree
    other = "docs/guides/b.ipynb"
    _write(root, other, [_cell("x1", "x")])
    _write(root / "docs/guides-staging/stage", other, [_cell("x1", "x")])
    _write(root / "docs/guides-staging/base", other, [_cell("x1", "x")])
    stage = root / "docs/guides-staging/stage"
    _write(stage, nb, [_cell("c1", "ONE"), _cell("c2", "two"), _cell("c3", "three", "code")])
    before = (root / other).read_bytes()
    run(root, "push", "--yes")
    assert list(json.loads((root / nb).read_text())) == ["cells", "metadata", "nbformat", "nbformat_minor"]
    assert (root / other).read_bytes() == before
    assert not list((root / "docs/guides-staging/.backup").rglob("b.ipynb"))


def test_editing_a_cell_after_pulling_the_maintainers_change_to_it_is_not_a_conflict(tree):
    root, nb = tree
    stage = root / "docs/guides-staging/stage"
    _write(root, nb, [_cell("c1", "one by the maintainer"), _cell("c2", "two"), _cell("c3", "three", "code")])
    run(root, "pull")
    _write(stage, nb, [_cell("c1", "one by the maintainer, then mine"), _cell("c2", "two"), _cell("c3", "three", "code")])
    assert run(root, "push", "--yes") == 0
    assert _texts(root, nb)["c1"] == "one by the maintainer, then mine"


# ---- --only, --cells and rename ----------------------------------------------------------------------------------------------
STAGE = "docs/guides-staging/stage"
BASE = "docs/guides-staging/base"
NB_B = "docs/guides/b.ipynb"


@pytest.fixture
def two(tree):
    root, nb = tree
    _write(root, NB_B, [_cell("x1", "x one"), _cell("x2", "x two")])
    gs.main(["--root", str(root), "init", "--force"])
    return root, nb, NB_B


def _stage_both(root, nb, other):
    _write(root / STAGE, nb, [_cell("c1", "ONE"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root / STAGE, other, [_cell("x1", "X ONE"), _cell("x2", "x two")])


def test_only_pushes_one_notebook_and_leaves_the_other_pending_and_untouched(two):
    root, nb, other = two
    _stage_both(root, nb, other)
    before = {t: {n: (root / t / n).read_bytes() for n in (nb, other)} for t in ("", STAGE, BASE)}
    assert run(root, "push", "--only", "a.ipynb", "--yes") == 0
    assert _texts(root, nb)["c1"] == "ONE"
    assert (root / other).read_bytes() == before[""][other]
    assert (root / STAGE / other).read_bytes() == before[STAGE][other]
    assert (root / BASE / other).read_bytes() == before[BASE][other]
    assert not list((root / "docs/guides-staging/.backup").rglob("b.ipynb"))
    assert list((root / "docs/guides-staging/.backup").rglob("a.ipynb"))
    assert run(root, "push", "--yes") == 0  # the other one is still pending
    assert _texts(root, other)["x1"] == "X ONE"


def test_only_accepts_repo_relative_and_guide_relative_paths_and_scopes_status_and_diff(two, capsys):
    root, nb, other = two
    _stage_both(root, nb, other)
    capsys.readouterr()
    run(root, "status", "--only", nb)
    out = capsys.readouterr().out
    assert nb in out and other not in out
    run(root, "diff", "--only", "b.ipynb")
    out = capsys.readouterr().out
    assert "==== " + other in out and nb not in out
    run(root, "status", "--only", "docs/guides/a.ipynb", "b.ipynb")
    out = capsys.readouterr().out
    assert nb in out and other in out


def test_only_pull_leaves_the_other_notebook_alone(two):
    root, nb, other = two
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO"), _cell("c3", "three", "code")])
    _write(root, other, [_cell("x1", "x one"), _cell("x2", "X TWO")])
    run(root, "pull", "--only", "b.ipynb")
    assert _texts(root / STAGE, other)["x2"] == "X TWO"
    assert _texts(root / STAGE, nb)["c2"] == "two"


def test_an_unknown_only_path_is_an_error_that_lists_the_notebooks(two, capsys):
    root, nb, other = two
    with pytest.raises(SystemExit) as error:
        run(root, "status", "--only", "nope.ipynb")
    assert "nope.ipynb" in str(error.value) and nb in str(error.value) and other in str(error.value)


def test_a_conflict_is_still_reported_and_skipped_under_only(two, capsys):
    root, nb, other = two
    _write(root / STAGE, nb, [_cell("c1", "mine"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "yours"), _cell("c2", "two"), _cell("c3", "three", "code")])
    capsys.readouterr()
    assert run(root, "push", "--only", nb, "--yes") == 1
    out = capsys.readouterr().out
    assert "CONFLICT" not in out or "SKIPPED" in out
    assert f"SKIPPED {nb}" in out and "changed in both" in out
    assert _texts(root, nb)["c1"] == "yours"


def test_cells_pushes_only_the_named_cells(tree):
    root, nb = tree
    _write(root / STAGE, nb, [_cell("c1", "ONE"), _cell("c2", "TWO"), _cell("c3", "three", "code"), _cell("n1", "new")])
    assert run(root, "push", "--only", nb, "--cells", "c2", "--yes") == 0
    assert _texts(root, nb) == {"c1": "one", "c2": "TWO", "c3": "three"}
    assert _texts(root / STAGE, nb)["c1"] == "ONE"  # still pending in staging
    assert _texts(root / BASE, nb) == {"c1": "one", "c2": "TWO", "c3": "three"}
    assert run(root, "push", "--only", nb, "--cells", "n1", "--yes") == 0
    assert [c["id"] for c in _read(root, nb)] == ["c1", "c2", "c3", "n1"]
    assert run(root, "push", "--yes") == 0
    assert _texts(root, nb)["c1"] == "ONE"


def test_cells_keeps_the_maintainers_other_edits_and_needs_one_notebook(two):
    root, nb, other = two
    _write(root / STAGE, nb, [_cell("c1", "ONE"), _cell("c2", "TWO"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "one by you"), _cell("c2", "two"), _cell("c3", "three", "code")])
    assert run(root, "push", "--only", nb, "--cells", "c2", "--yes") == 0
    assert _texts(root, nb) == {"c1": "one by you", "c2": "TWO", "c3": "three"}
    with pytest.raises(SystemExit):
        run(root, "push", "--only", nb, other, "--cells", "c2", "--yes")
    with pytest.raises(SystemExit):
        run(root, "push", "--cells", "c2", "--yes")


def test_cells_conflict_on_a_named_cell_is_skipped(tree):
    root, nb = tree
    _write(root / STAGE, nb, [_cell("c1", "mine"), _cell("c2", "two"), _cell("c3", "three", "code")])
    _write(root, nb, [_cell("c1", "yours"), _cell("c2", "two"), _cell("c3", "three", "code")])
    assert run(root, "push", "--only", nb, "--cells", "c1", "--yes") == 1
    assert _texts(root, nb)["c1"] == "yours"


def test_rename_is_refused_when_the_working_file_has_edits(two):
    root, nb, other = two
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO in the IDE"), _cell("c3", "three", "code")])
    edited = (root / nb).read_bytes()
    with pytest.raises(SystemExit) as error:
        run(root, "rename", "a.ipynb", "a2.ipynb")
    assert "refused" in str(error.value)
    assert (root / nb).read_bytes() == edited
    assert not (root / "docs/guides/a2.ipynb").exists() and (root / STAGE / nb).exists() and (root / BASE / nb).exists()


def test_rename_with_force_carries_the_edits_along(two):
    root, nb, other = two
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO in the IDE"), _cell("c3", "three", "code")])
    run(root, "rename", "a.ipynb", "a2.ipynb", "--force-working-edited")
    assert _texts(root, "docs/guides/a2.ipynb")["c2"] == "TWO in the IDE"
    assert not (root / nb).exists()


def test_rename_moves_working_stage_and_base_together_and_keeps_pending_cells(two, capsys):
    root, nb, other = two
    _write(root / STAGE, nb, [_cell("c1", "ONE"), _cell("c2", "two"), _cell("c3", "three", "code")])
    new = "docs/guides/a2.ipynb"
    run(root, "rename", nb, "a2.ipynb")
    for tree in ("", STAGE, BASE):
        assert not (root / tree / nb).exists() and (root / tree / new).exists()
    assert _texts(root / STAGE, new)["c1"] == "ONE"
    assert _texts(root / BASE, new)["c1"] == "one"
    assert run(root, "push", "--only", new, "--yes") == 0
    assert _texts(root, new)["c1"] == "ONE" and not (root / nb).exists()
    assert _texts(root, other)["x1"] == "x one"
    with pytest.raises(SystemExit):
        run(root, "rename", "a2.ipynb", "b.ipynb")  # the target exists


def test_rename_uses_git_mv_when_git_tracks_the_file(two):
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("no git")
    root, nb, other = two
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", nb], check=True)
    run(root, "rename", "a.ipynb", "a2.ipynb")
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert "A  docs/guides/a2.ipynb" in status and "docs/guides/a.ipynb" not in status.replace("a2.ipynb", "")


def test_a_staged_delete_and_create_of_an_edited_guide_is_not_pushed_as_a_rename(two, capsys):
    root, nb, other = two
    _write(root, nb, [_cell("c1", "one"), _cell("c2", "TWO in the IDE"), _cell("c3", "three", "code")])
    (root / STAGE / nb).rename(root / STAGE / "docs/guides/a2.ipynb")
    capsys.readouterr()
    assert run(root, "push", "--yes") == 1
    out = capsys.readouterr().out
    assert "looks like a rename of" in out
    assert not (root / "docs/guides/a2.ipynb").exists()
    assert _texts(root, nb)["c2"] == "TWO in the IDE"
