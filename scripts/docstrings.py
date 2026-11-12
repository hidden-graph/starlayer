#!/usr/bin/env python3
"""scripts/docstrings.py - the mechanical half of the docstring work: what is undocumented, and whether an edit is only docstrings.

``inventory``: the public functions, classes, methods and modules of ``packages/starlayer/starlayer`` that have no docstring, as JSON
(a symbol is public when its name does not start with an underscore, dunder names count, and it is not defined inside a function). ``--files`` limits it to some files.

``check FILE [--base REV]``: compares FILE with its version at REV (default ``HEAD``) and fails when

* the code changed: the two ASTs, with every docstring removed, differ (an edit that is only docstrings cannot change behaviour);
* a docstring does not parse under the code-KG extractor's ``Args:`` / ``Returns:`` grammar, or names a parameter the function does
  not have (a stale parameter name);
* a docstring carries a scratch note (``CLAUDE:``, ``TODO``, ``XXX``), starts with an empty line or has trailing whitespace.

It warns, without failing, about a backticked identifier in a docstring that is defined nowhere in the package (the likely stale
citation) and lists the public symbols of FILE that are still undocumented. Exit status 1 on any failure.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "starlayer" / "starlayer"
sys.path.insert(0, str(ROOT / "tools" / "kg"))

_SCRATCH = re.compile(r"\b(CLAUDE:|TODO|XXX|FIXME)")
_BACKTICKED = re.compile(r"``([^`\n]+)``|(?<!`)`([^`\n]+)`(?!`)")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _is_public(name: str) -> bool:
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def _symbols(tree: ast.Module) -> list[tuple[str, str, ast.AST]]:
    """(qualified name, kind, node) for the module, and every class, function and method, nested ones included."""
    out: list[tuple[str, str, ast.AST]] = [("<module>", "module", tree)]

    def walk(node: ast.AST, prefix: str, in_function: bool = False) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(child, ast.ClassDef) else "function"
                if prefix and not kind == "class" and node.__class__ is ast.ClassDef:
                    kind = "method"
                if in_function:
                    kind = "closure"  # defined inside a function: not part of the public API
                qual = f"{prefix}.{child.name}" if prefix else child.name
                out.append((qual, kind, child))
                walk(child, qual, in_function or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)))
            else:
                walk(child, prefix, in_function)

    walk(tree, "")
    return out


def _public(qual: str) -> bool:
    return all(_is_public(part) for part in qual.split(".") if part != "<module>")


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"({ast.unparse(node.args)}){returns}"
    if isinstance(node, ast.ClassDef):
        return "(" + ", ".join(ast.unparse(b) for b in node.bases) + ")" if node.bases else ""
    return ""


def inventory(files: list[Path]) -> dict:
    result: dict[str, list[dict]] = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        rel = str(path.resolve().relative_to(ROOT))
        for qual, kind, node in _symbols(tree):
            if kind == "closure" or not _public(qual) or ast.get_docstring(node, clean=False):
                continue
            line = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", line)
            decorators = [ast.unparse(d) for d in getattr(node, "decorator_list", [])]
            result.setdefault(rel, []).append(
                {"symbol": qual, "kind": kind, "line": line, "end_line": end, "signature": _signature(node), "decorators": decorators}
            )
    return result


def _strip_docstrings(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] if isinstance(node, ast.Module) else (body[1:] or [ast.Pass()])
    return ast.dump(tree, include_attributes=False)


def _git_show(rev: str, path: Path) -> str | None:
    rel = path.resolve().relative_to(ROOT)
    done = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=ROOT, capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


_KNOWN: set[str] | None = None


def _known_identifiers() -> set[str]:
    """Every name defined anywhere in the package (functions, classes, methods, parameters, module-level and attribute assignments),
    the builtins and the names the package imports: what a docstring may sensibly name."""
    global _KNOWN
    if _KNOWN is None:
        names: set[str] = set(dir(builtins)) | {"self", "cls", "True", "False", "None"}
        for path in PACKAGE.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            names.add(path.stem)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
                    if not isinstance(node, ast.ClassDef):
                        a = node.args
                        for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg]:
                            if arg is not None:
                                names.add(arg.arg)
                elif isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        names.update((alias.asname or alias.name).split("."))
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names.update(node.module.split("."))
        _KNOWN = names
    return _KNOWN


def check(path: Path, base: str) -> int:
    new_source = path.read_text()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        new_tree = ast.parse(new_source)
    except SyntaxError as exc:
        print(f"FAIL {path}: does not parse: {exc}")
        return 1
    old_source = _git_show(base, path)
    if old_source is None:
        warnings.append(f"no version of the file at {base}: the code-unchanged check was skipped")
    elif _strip_docstrings(ast.parse(old_source)) != _strip_docstrings(ast.parse(new_source)):
        errors.append("the code changed: with the docstrings removed, the file differs from its version at " + base)

    from codekg.extractor.docstrings import parse_docstring

    known = _known_identifiers()
    old_docs = {q: ast.get_docstring(n, clean=False) for q, _k, n in _symbols(ast.parse(old_source))} if old_source else {}
    for qual, _kind, node in _symbols(new_tree):
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        changed = old_docs.get(qual) != doc  # warnings are for what this edit wrote, not for older text
        where = f"{qual}"
        if doc.lstrip(" ").startswith("\n") and not doc.strip():
            errors.append(f"{where}: an empty docstring")
        if any(line != line.rstrip() for line in doc.split("\n")[:-1]):  # the last line is the indent before the closing quotes
            errors.append(f"{where}: trailing whitespace inside the docstring")
        if _SCRATCH.search(doc):
            errors.append(f"{where}: a scratch note ({_SCRATCH.search(doc).group(1)}) in the docstring")
        parsed = parse_docstring(doc)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            real = {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg] if x is not None}
            for name in parsed["params"]:
                if name.lstrip("*") not in real:
                    errors.append(f"{where}: Args names a parameter the function does not have: {name}")
        for m in _BACKTICKED.finditer(doc):
            text = (m.group(1) or m.group(2)).strip()
            for word in re.split(r"[\s(),:;=\[\]{}<>|]+", text):
                word = word.strip("`'\".*")
                if word and _IDENT.match(word) and ("_" in word or "." in word or (word[0].isupper() and any(c.islower() for c in word))):
                    parts = word.split(".")
                    if changed and not all(p in known for p in parts[-1:]):
                        warnings.append(f"{where}: `{word}` is not defined anywhere in the package (a stale citation?)")
    leftover = [s for s in inventory([path]).get(str(path.resolve().relative_to(ROOT)), [])]
    for w in sorted(set(warnings)):
        print(f"warn {path.name}: {w}")
    for e in errors:
        print(f"FAIL {path.name}: {e}")
    print(f"{'FAIL' if errors else 'ok'} {path.name}: {len(errors)} error(s), {len(set(warnings))} warning(s), {len(leftover)} public symbol(s) still undocumented")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("inventory", help="undocumented public symbols, as JSON")
    inv.add_argument("--files", nargs="*", help="limit to these files (default: the whole package)")
    chk = sub.add_parser("check", help="is an edit only docstrings, and do they parse")
    chk.add_argument("file")
    chk.add_argument("--base", default="HEAD")
    args = parser.parse_args()
    if args.cmd == "inventory":
        files = [Path(f) for f in args.files] if args.files else sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
        print(json.dumps(inventory(files), indent=1))
        return 0
    return check(Path(args.file), args.base)


if __name__ == "__main__":
    raise SystemExit(main())
