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
- ``rename OLD NEW``: move one guide to a new name in the working guides (``git mv`` when Git tracks it), the staging copy and the
  base together. Refused when the working file has edits that are not in the base (the maintainer edited it since the last
  ``pull``), unless ``--force-working-edited`` says to carry those edits along. A rename is made only this way: a file deleted
  in the staging copy and created under another name is still a delete plus a create, and ``push`` refuses to write the new
  name when it shares at least 80% of its cell ids with a deleted notebook whose working copy was edited.

``--only PATH...`` (on ``status``, ``diff``, ``pull`` and ``push``) limits the command to those tracked files; a path is the
repo-relative path, the path under ``docs/guides``, or a bare file name. Everything else in the stage, base and working trees is
left untouched, and a push saves backups only for the files it writes. An unknown path is an error that lists the known notebooks.
``push --only NOTEBOOK --cells ID... --yes`` pushes only the named cells of that one notebook: the other cells keep the working
copy's text, the staging copy keeps its other pending cells, and the base advances only for the pushed cells.

A notebook is compared cell by cell, by cell id, on the cell type and source. Outputs follow their cell: a changed output
is taken from the staging copy unless the working cell's output also changed. Every other file is compared as a whole.
Only the guides (``docs/guides``) and the files that list them (``COMPANIONS``) are tracked.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
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


def known(trees: Trees) -> set[str]:
    return tracked(trees.work) | tracked(trees.stage) | tracked(trees.base)


def resolve_only(trees: Trees, paths: list[str] | None) -> list[str] | None:
    """The tracked files that ``--only`` names (None when it is absent). An unknown or ambiguous path is an error."""
    if not paths:
        return None
    names = known(trees)
    chosen: list[str] = []
    for given in paths:
        text = given[2:] if given.startswith("./") else given
        matches = [text] if text in names else [f"{GUIDES}/{text}"] if f"{GUIDES}/{text}" in names else sorted(n for n in names if Path(n).name == text)
        if len(matches) != 1:
            notebooks = sorted(n for n in names if n.endswith(".ipynb"))
            others = sorted(names - set(notebooks))
            why = "is ambiguous" if matches else "is not a tracked file"
            sys.exit(f"{given!r} {why}. Known notebooks:\n  " + "\n  ".join(notebooks) + "\nOther tracked files:\n  " + "\n  ".join(others))
        if matches[0] not in chosen:
            chosen.append(matches[0])
    return chosen


def plan(trees: Trees, only: list[str] | None = None) -> list[Merged]:
    names = sorted(known(trees) if only is None else only)
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


def status(trees: Trees, only: list[str] | None = None) -> None:
    _report(plan(trees, only))


def show_diff(trees: Trees, only: str | None, files: list[str] | None = None) -> None:
    for m in plan(trees, files):
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


def pull(trees: Trees, only: list[str] | None = None) -> None:
    merged = plan(trees, only)
    for m in merged:
        if m.content != read(trees.stage, m.relative):
            write(trees.stage, m.relative, m.content)
            print(f"pulled {m.relative}")
    for m in merged:
        advance_base(trees, m.relative)
        for conflict in m.conflicts:
            print(f"CONFLICT {m.relative}: {conflict} (staging kept)")


def _is_new_notebook(trees: Trees, relative: str) -> bool:
    return relative.endswith(".ipynb") and read(trees.base, relative) is None and read(trees.work, relative) is None and read(trees.stage, relative) is not None


def paired_rename(trees: Trees, relative: str) -> tuple[str, Merged] | None:
    """The notebook that a new staged notebook looks like a rename of: one deleted in the staging copy that shares at least 80% of its cell ids."""
    if not _is_new_notebook(trees, relative):
        return None
    new_ids = set(_cells(_notebook(read(trees.stage, relative))))
    for old in sorted(tracked(trees.base) - tracked(trees.stage)):
        base = read(trees.base, old)
        if not old.endswith(".ipynb") or base is None:
            continue
        old_ids = set(_cells(_notebook(base)))
        if old_ids and len(old_ids & new_ids) >= 0.8 * len(old_ids):
            return old, merge_file(old, base, None, read(trees.work, old))
    return None


def push(trees: Trees, yes: bool, only: list[str] | None = None) -> int:
    merged = plan(trees, only)
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
        pair = paired_rename(trees, m.relative)
        if pair is not None:
            if pair[1].conflicts:
                skipped += 1
                print(f"SKIPPED {m.relative}: looks like a rename of {pair[0]}, which was edited in the working guides ({'; '.join(pair[1].conflicts)}); use `rename`")
                continue
            print(f"renamed {pair[0]} -> {m.relative}")
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


def _apply_cells(target: dict, source: dict, ids: list[str]) -> dict:
    """``target`` with the named cells set to their state in ``source`` (replaced, inserted after their predecessor, or removed)."""
    cells = [json.loads(json.dumps(c)) for c in target["cells"]]
    src = _cells(source)
    order = _order(source)
    for cell_id in sorted(ids, key=lambda i: order.index(i) if i in order else len(order)):
        at = next((n for n, c in enumerate(cells) if c["id"] == cell_id), None)
        if cell_id not in src:
            if at is not None:
                del cells[at]
        elif at is not None:
            cells[at] = json.loads(json.dumps(src[cell_id]))
        else:
            earlier = [c for c in order[: order.index(cell_id)]]
            where = next((n + 1 for p in reversed(earlier) for n, c in enumerate(cells) if c["id"] == p), 0)
            cells.insert(where, json.loads(json.dumps(src[cell_id])))
    return {key: (cells if key == "cells" else value) for key, value in target.items()}


def push_cells(trees: Trees, relative: str, ids: list[str], yes: bool) -> int:
    """Push only the named cells of one notebook."""
    stage, work, base = read(trees.stage, relative), read(trees.work, relative), read(trees.base, relative)
    if not relative.endswith(".ipynb") or stage is None or work is None:
        sys.exit("--cells needs a notebook that exists in both the staging copy and the working guides")
    nb_s, nb_w = _notebook(stage), _notebook(work)
    nb_b = _notebook(base) if base is not None else {key: ([] if key == "cells" else value) for key, value in nb_w.items()}
    present = set(_cells(nb_s)) | set(_cells(nb_w)) | set(_cells(nb_b))
    unknown = [i for i in ids if i not in present]
    if unknown:
        sys.exit(f"no such cell id in {relative}: {', '.join(unknown)}")
    merged, conflicts = merge_notebook(nb_b, nb_s, nb_w)
    conflicts = [c for c in conflicts if any(c.startswith(f"cell {i}:") for i in ids)]
    chosen = set(ids)
    mine = [n for n in _cell_changes(nb_b, nb_s) if n.rsplit(" ", 1)[-1] in chosen]
    result = _apply_cells(nb_w, merged, ids)
    content = work if result == nb_w else _dump(result)
    print(relative)
    if mine:
        print(f"   mine (pending, named cells only): {', '.join(mine)}")
    for conflict in conflicts:
        print(f"   CONFLICT {conflict}")
    if not yes:
        print("dry run: nothing written (use push --yes after approval)")
        return 0
    if conflicts:
        print(f"SKIPPED {relative}: {'; '.join(conflicts)}")
        return 1
    if content != work:
        write(trees.stage.parent / ".backup" / time.strftime("%Y%m%d-%H%M%S"), relative, work)
        write(trees.work, relative, content)
        print(f"pushed {relative} (cells {', '.join(ids)})")
    write(trees.stage, relative, _dump(_apply_cells(nb_s, merged, ids)))
    write(trees.base, relative, _dump(_apply_cells(nb_b, merged, ids)))
    print("reload any notebook that is open in the IDE")
    return 0


def rename(trees: Trees, root: Path, old: str, new: str, force_working_edited: bool = False) -> None:
    """Move one guide to a new name in the working, staging and base trees together, refusing to carry along unseen edits."""
    (old,) = resolve_only(trees, [old])
    new = new[2:] if new.startswith("./") else new
    if "/" not in new:
        new = f"{Path(old).parent.as_posix()}/{new}"
    elif new not in known(trees) and not new.startswith(("docs/", "tools/")):
        new = f"{GUIDES}/{new}"
    if Path(new).suffix != Path(old).suffix:
        sys.exit(f"{new}: a rename keeps the file type ({Path(old).suffix})")
    if any((tree / new).exists() for tree in (trees.work, trees.stage, trees.base)):
        sys.exit(f"cannot rename to {new}: it already exists in the working, staging or base tree")
    work, base = read(trees.work, old), read(trees.base, old)
    if work is None:
        sys.exit(f"cannot rename {old}: it is not in the working guides")
    if work != base and not force_working_edited:
        sys.exit(
            f"refused: {old} has edits in the working guides that are not in the base (it was edited since the last pull).\n"
            f"Run `pull --only {old}` first, or pass --force-working-edited to carry those edits to {new}."
        )
    (trees.work / new).parent.mkdir(parents=True, exist_ok=True)
    moved = False
    if (root / ".git").exists():
        done = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", old], capture_output=True)
        if done.returncode == 0:
            moved = subprocess.run(["git", "-C", str(root), "mv", old, new], capture_output=True).returncode == 0
    if not moved:
        (trees.work / old).rename(trees.work / new)
    for tree in (trees.stage, trees.base):
        if (tree / old).exists():
            (tree / new).parent.mkdir(parents=True, exist_ok=True)
            (tree / old).rename(tree / new)
    print(f"renamed {old} -> {new}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    scoped = argparse.ArgumentParser(add_help=False)
    scoped.add_argument("--only", nargs="+", metavar="PATH", help="limit the command to these tracked files (repo-relative path, path under docs/guides, or bare file name)")
    p = sub.add_parser("init")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status", parents=[scoped])
    p = sub.add_parser("diff", parents=[scoped])
    p.add_argument("path", nargs="?")
    sub.add_parser("pull", parents=[scoped])
    p = sub.add_parser("push", parents=[scoped])
    p.add_argument("--yes", action="store_true", help="write the pending batch to the working guides")
    p.add_argument("--cells", nargs="+", metavar="ID", help="with --only NOTEBOOK: push only these cell ids of that notebook")
    p = sub.add_parser("rename")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--force-working-edited", action="store_true", help="carry edits that the working file has and the base lacks to the new name")
    args = parser.parse_args(argv)
    trees = Trees.at(args.root)
    if args.command != "init" and not trees.stage.exists():
        sys.exit("no staging copy: run `python scripts/guide_staging.py init` first")
    only = resolve_only(trees, getattr(args, "only", None)) if args.command != "init" else None
    if args.command == "init":
        init(trees, args.root, args.force)
    elif args.command == "status":
        status(trees, only)
    elif args.command == "diff":
        show_diff(trees, args.path, only)
    elif args.command == "pull":
        pull(trees, only)
    elif args.command == "rename":
        rename(trees, args.root, args.old, args.new, args.force_working_edited)
    elif args.cells:
        if only is None or len(only) != 1:
            sys.exit("--cells needs --only with exactly one notebook")
        return push_cells(trees, only[0], args.cells, args.yes)
    else:
        return push(trees, args.yes, only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
