#!/usr/bin/env python
"""Stage edits to the user guides, and push them to the working guides only after approval.

The working guides (``docs/guides``) are the ones the maintainer edits in the IDE. A staging copy (``docs/guides-staging/stage``)
is where an assistant makes its edits, so the IDE never sees a half-made change and never overwrites one. ``docs/guides-staging/base``
is the working guides as they were at the last sync: with it, a change can be told apart from a stale copy.

Commands (``--root`` is for tests):

- ``init``: copy the working guides to the staging copy and the base. Adds the staging folder to ``.git/info/exclude``.
- ``status``: what the staging copy would change in the working guides (the pending batch), and what the maintainer has
  changed in the working guides that the staging copy does not have yet. A conflict is a cell, or a file, changed on both sides.
- ``diff [path]``: the pending batch, cell by cell.
- ``pull``: bring the maintainer's changes into the staging copy, so edits are made on the latest text. Staging wins a conflict.
- ``push --yes``: write the pending batch to the working guides, after saving a backup of each file it replaces. A conflict is
  never written: that file is skipped and reported. Without ``--yes`` this is a dry run, the same as ``status``.

A notebook is compared cell by cell, by cell id, on the cell type and source. Outputs follow their cell: a changed output
is taken from the staging copy unless the working cell's output also changed. Every other file is compared as a whole.
Only the guides (``docs/guides``) and the files that list them (``COMPANIONS``) are tracked.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
GUIDES = "docs/guides"
COMPANIONS = ("docs/user-guide-version.json", "tools/kg/codekg/curated/notebook-links.ttl")
STAGING = "docs/guides-staging"


# ---- trees -------------------------------------------------------------------------------------------------------------------
@dataclass
class Trees:
    work: Path
    stage: Path
    base: Path

    @classmethod
    def at(cls, root: Path) -> Trees:
        return cls(root, root / STAGING / "stage", root / STAGING / "base")


def tracked(tree: Path) -> set[str]:
    """The tracked files of one tree, as paths relative to its root."""
    found: set[str] = set()
    guides = tree / GUIDES
    if guides.is_dir():
        for path in guides.rglob("*"):
            relative = path.relative_to(tree).as_posix()
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(guides).parts):
                found.add(relative)
    found.update(name for name in COMPANIONS if (tree / name).is_file())
    return found


def read(tree: Path, relative: str) -> bytes | None:
    path = tree / relative
    return path.read_bytes() if path.is_file() else None


def write(tree: Path, relative: str, content: bytes | None) -> None:
    path = tree / relative
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---- merging -----------------------------------------------------------------------------------------------------------------
def _notebook(content: bytes | None) -> dict | None:
    return None if content is None else json.loads(content)


def _dump(notebook: dict) -> bytes:
    return (json.dumps(notebook, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def _source(cell: dict | None) -> tuple | None:
    """What identifies a cell's content for a merge: its type and its source (outputs and metadata are not compared)."""
    return None if cell is None else (cell["cell_type"], "".join(cell["source"]))


def _output(cell: dict | None) -> str | None:
    if cell is None or cell["cell_type"] != "code":
        return None
    return json.dumps(cell.get("outputs", []), sort_keys=True)


def _cells(notebook: dict | None) -> dict[str, dict]:
    if notebook is None:
        return {}
    cells = {}
    for cell in notebook["cells"]:
        if "id" not in cell:
            raise ValueError("a notebook cell has no id; guide staging merges by cell id")
        cells[cell["id"]] = cell
    return cells


def _order(notebook: dict | None) -> list[str]:
    return [] if notebook is None else [cell["id"] for cell in notebook["cells"]]


def _restricted(order: list[str], keep: set[str]) -> list[str]:
    return [i for i in order if i in keep]


def merge_notebook(base: dict | None, stage: dict | None, work: dict | None) -> tuple[dict, list[str]]:
    """The three-way merge of a notebook by cell id. Returns the merged notebook and the conflicts (each a short sentence)."""
    b, s, w = _cells(base), _cells(stage), _cells(work)
    conflicts: list[str] = []
    chosen: dict[str, dict] = {}
    for cell_id in dict.fromkeys([*_order(work), *_order(stage), *_order(base)]):
        sb, ss, sw = _source(b.get(cell_id)), _source(s.get(cell_id)), _source(w.get(cell_id))
        if ss == sw:
            pick = w.get(cell_id)
        elif ss == sb:
            pick = w.get(cell_id)
        elif sw == sb:
            pick = s.get(cell_id)
        else:
            conflicts.append(f"cell {cell_id}: changed in both")
            pick = s.get(cell_id)
        if pick is None:
            continue
        pick = json.loads(json.dumps(pick))
        if pick["cell_type"] == "code":  # outputs: the staging copy's when it changed them and the working copy did not
            ob, os_, ow = _output(b.get(cell_id)), _output(s.get(cell_id)), _output(w.get(cell_id))
            source_cell = s.get(cell_id) if (os_ != ob and ow == ob) else (w.get(cell_id) or s.get(cell_id))
            if source_cell is not None and source_cell["cell_type"] == "code":
                pick["outputs"] = json.loads(json.dumps(source_cell.get("outputs", [])))
                pick["execution_count"] = source_cell.get("execution_count")
        chosen[cell_id] = pick
    keep = set(chosen)
    order_b, order_s, order_w = (_restricted(o, keep) for o in (_order(base), _order(stage), _order(work)))
    common = [i for i in order_b if i in set(order_s) & set(order_w)]
    if _restricted(order_s, set(common)) == common and _restricted(order_w, set(common)) == common:
        arranged = [i for i in order_w]
    elif _restricted(order_w, set(common)) == common:
        arranged = [i for i in order_s]  # the staging copy moved cells, the working copy did not
    elif _restricted(order_s, set(common)) == common:
        arranged = [i for i in order_w]  # the working copy moved cells, the staging copy did not
    else:
        conflicts.append("cell order: moved in both")
        arranged = [i for i in order_s]
    placed = set(arranged)
    for order in (order_s, order_w):  # a cell the arrangement lacks goes after its predecessor in the copy that has it
        for index, cell_id in enumerate(order):
            if cell_id in placed or cell_id not in keep:
                continue
            predecessor = next((p for p in reversed(order[:index]) if p in placed), None)
            arranged.insert(arranged.index(predecessor) + 1 if predecessor else 0, cell_id)
            placed.add(cell_id)
    for cell_id in chosen:
        if cell_id not in placed:
            arranged.append(cell_id)
    frame = work if work is not None else stage
    merged = {key: ([chosen[i] for i in arranged] if key == "cells" else value) for key, value in frame.items()}  # the key order is kept
    return merged, conflicts


@dataclass
class Merged:
    relative: str
    content: bytes | None
    conflicts: list[str] = field(default_factory=list)
    mine: list[str] = field(default_factory=list)  # what the staging copy changed since the base
    yours: list[str] = field(default_factory=list)  # what the working copy changed since the base


def _cell_changes(left: dict | None, right: dict | None) -> list[str]:
    a, b = _cells(left), _cells(right)
    notes = []
    for cell_id in dict.fromkeys([*_order(right), *_order(left)]):
        if cell_id not in a:
            notes.append(f"added {cell_id}")
        elif cell_id not in b:
            notes.append(f"removed {cell_id}")
        elif _source(a[cell_id]) != _source(b[cell_id]):
            notes.append(f"changed {cell_id}")
        elif _output(a[cell_id]) != _output(b[cell_id]):
            notes.append(f"output of {cell_id}")
    if _restricted(_order(left), set(a) & set(b)) != _restricted(_order(right), set(a) & set(b)):
        notes.append("cell order")
    return notes


def merge_file(relative: str, base: bytes | None, stage: bytes | None, work: bytes | None) -> Merged:
    """The three-way merge of one tracked file."""
    notebook = relative.endswith(".ipynb")
    result = Merged(relative, work)
    if notebook and stage is not None and work is not None:
        nb_b, nb_s, nb_w = _notebook(base), _notebook(stage), _notebook(work)
        merged, conflicts = merge_notebook(nb_b, nb_s, nb_w)
        content = work if merged == nb_w and list(merged) == list(nb_w) else _dump(merged)  # a notebook that did not change is not rewritten
        result.content, result.conflicts = content, conflicts
        result.mine = _cell_changes(nb_b, nb_s) if nb_b is not None else ["new notebook"]
        result.yours = _cell_changes(nb_b, nb_w) if nb_b is not None else ["new notebook"]
        return result
    if stage == work:
        result.content = work
    elif stage == base:
        result.content = work
        result.yours = ["deleted" if work is None else "new" if base is None else "changed"]
    elif work == base:
        result.content = stage
        result.mine = ["deleted" if stage is None else "new" if base is None else "changed"]
    else:
        result.content = stage
        result.mine = ["deleted" if stage is None else "changed"]
        result.yours = ["deleted" if work is None else "changed"]
        result.conflicts = ["changed in both" if stage is not None and work is not None else "deleted on one side, changed on the other"]
    return result


def plan(trees: Trees) -> list[Merged]:
    names = sorted(tracked(trees.work) | tracked(trees.stage) | tracked(trees.base))
    return [merge_file(n, read(trees.base, n), read(trees.stage, n), read(trees.work, n)) for n in names]


# ---- commands ----------------------------------------------------------------------------------------------------------------
def _exclude(root: Path) -> None:
    exclude = root / ".git" / "info" / "exclude"
    if not exclude.parent.is_dir():
        return
    line = f"{STAGING}/"
    text = exclude.read_text() if exclude.exists() else ""
    if line not in text.splitlines():
        exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + line + "\n")


def init(trees: Trees, root: Path, force: bool = False) -> None:
    if trees.stage.exists() and not force:
        sys.exit(f"{trees.stage} exists; use --force to start again (it discards unpushed staging edits)")
    for tree in (trees.stage, trees.base):
        shutil.rmtree(tree, ignore_errors=True)
        for name in tracked(trees.work):
            write(tree, name, read(trees.work, name))
    _exclude(root)
    print(f"staging copy made: {len(tracked(trees.work))} files")


def _report(merged: list[Merged]) -> bool:
    pending = False
    for m in merged:
        if not (m.mine or m.yours or m.conflicts):
            continue
        pending = pending or bool(m.mine)
        print(f"{m.relative}")
        if m.mine:
            print(f"   mine (pending): {', '.join(m.mine)}")
        if m.yours:
            print(f"   yours (not in staging yet): {', '.join(m.yours)}")
        for conflict in m.conflicts:
            print(f"   CONFLICT {conflict}")
    if not pending and not any(m.yours or m.conflicts for m in merged):
        print("staging and working guides are in step")
    return pending


def status(trees: Trees) -> None:
    _report(plan(trees))


def show_diff(trees: Trees, only: str | None) -> None:
    for m in plan(trees):
        if not m.mine or (only and only not in m.relative):
            continue
        before, after = read(trees.work, m.relative), m.content
        print(f"==== {m.relative}")
        if m.relative.endswith(".ipynb") and before is not None and after is not None:
            old, new = _cells(_notebook(before)), _cells(_notebook(after))
            for cell_id in dict.fromkeys([*new, *old]):
                a = "".join(old[cell_id]["source"]) if cell_id in old else ""
                b = "".join(new[cell_id]["source"]) if cell_id in new else ""
                if a != b:
                    print(f"-- cell {cell_id}")
                    print("".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), "working", "pending", n=1)))
        else:
            a = (before or b"").decode("utf-8", "replace")
            b = (after or b"").decode("utf-8", "replace")
            print("".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), "working", "pending", n=1)))


def advance_base(trees: Trees, relative: str) -> None:
    """After a pull, what the staging and working copies agree on is the new base, so a later edit of a pulled cell is not a conflict."""
    stage, work, base = read(trees.stage, relative), read(trees.work, relative), read(trees.base, relative)
    if stage == work:
        if base != work:
            write(trees.base, relative, work)
        return
    if not relative.endswith(".ipynb") or stage is None or work is None:
        return
    nb_s, nb_w = _notebook(stage), _notebook(work)
    nb_b = _notebook(base) if base is not None else {key: ([] if key == "cells" else value) for key, value in nb_w.items()}
    s, w, b = _cells(nb_s), _cells(nb_w), _cells(nb_b)
    cells = dict(b)
    for cell_id in set(s) | set(w) | set(b):
        if _source(s.get(cell_id)) == _source(w.get(cell_id)):
            if cell_id in w:
                cells[cell_id] = w[cell_id]
            else:
                cells.pop(cell_id, None)
    order = [i for i in _order(nb_w) if i in cells] + [i for i in _order(nb_b) if i in cells and i not in set(_order(nb_w))]
    if _restricted(_order(nb_s), set(w) & set(s)) == _restricted(_order(nb_w), set(w) & set(s)):
        nb_b = {key: ([cells[i] for i in order] if key == "cells" else value) for key, value in nb_b.items()}
        write(trees.base, relative, _dump(nb_b))


def pull(trees: Trees) -> None:
    merged = plan(trees)
    for m in merged:
        if m.content != read(trees.stage, m.relative):
            write(trees.stage, m.relative, m.content)
            print(f"pulled {m.relative}")
    for m in merged:
        advance_base(trees, m.relative)
        for conflict in m.conflicts:
            print(f"CONFLICT {m.relative}: {conflict} (staging kept)")


def push(trees: Trees, yes: bool) -> int:
    merged = plan(trees)
    if not yes:
        _report(merged)
        print("dry run: nothing written (use push --yes after approval)")
        return 0
    backup = trees.stage.parent / ".backup" / time.strftime("%Y%m%d-%H%M%S")
    skipped = 0
    for m in merged:
        if m.conflicts:
            skipped += 1
            print(f"SKIPPED {m.relative}: {'; '.join(m.conflicts)}")
            continue
        current = read(trees.work, m.relative)
        if m.content != current:
            if current is not None:
                write(backup, m.relative, current)
            write(trees.work, m.relative, m.content)
            print(f"pushed {m.relative}")
        write(trees.stage, m.relative, m.content)
        write(trees.base, m.relative, m.content)
    if skipped:
        print(f"{skipped} file(s) skipped for conflicts; resolve them in the staging copy, then push again")
    print("reload any notebook that is open in the IDE")
    return 1 if skipped else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("diff")
    p.add_argument("path", nargs="?")
    sub.add_parser("pull")
    p = sub.add_parser("push")
    p.add_argument("--yes", action="store_true", help="write the pending batch to the working guides")
    args = parser.parse_args(argv)
    trees = Trees.at(args.root)
    if args.command != "init" and not trees.stage.exists():
        sys.exit("no staging copy: run `python scripts/guide_staging.py init` first")
    if args.command == "init":
        init(trees, args.root, args.force)
    elif args.command == "status":
        status(trees)
    elif args.command == "diff":
        show_diff(trees, args.path)
    elif args.command == "pull":
        pull(trees)
    else:
        return push(trees, args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
