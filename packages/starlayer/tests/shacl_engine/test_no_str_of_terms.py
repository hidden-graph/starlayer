"""No ``str(term)`` inside ``shacl_engine``.

On a pyoxigraph term ``str()`` gives ``<http://...>`` (an IRI) or the N-Triples form (a literal), not the lexical value an
rdflib term gave. Formatting one (``str(x)``, ``f"{x}"``, ``"%s" % x``, ``"{}".format(x)``) is a silent wrong string, not
an exception. This test walks the AST of every module under ``shacl_engine/`` and fails on a formatting use whose argument
is not provably a plain value:

* provably plain: a literal, an f-string, a number or length (``len``, ``int`` ...), the result of a text helper
  (``terms.text`` / ``lexical`` / ``iri_text`` / ``n3`` / ``local_name``), a string method, ``<x>.value`` (the lexical value of
  a pyoxigraph term), ``.language``, names that end in a plain suffix (``_text``, ``_name``, ``message``, ``reason`` ...), an
  exception bound by ``except ... as exc``, and arithmetic/conditionals of those;
* anything else fails, and names ending in term/node/lit/literal/value/focus/subject/predicate/object/iri/shape (or an attribute
  of such a name, or an attribute known to hold terms: ``.focus``, ``.component``, ``.severity`` ...) fail even when they sit in
  a container-looking expression.

A line that was reviewed and is right carries ``# str-ok: <reason>`` (on the line of the call, or the line the statement
starts on). Use the helpers in ``terms.py`` instead where a term is meant.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "starlayer" / "shacl_engine"
FILES = sorted(ENGINE.rglob("*.py"))

TERMISH_NAME = re.compile(
    r"(^|_)(term|node|lit|literal|value|focus|subject|predicate|object|iri|shape|dt|datatype|component|severity|"
    r"s|p|o|t|v|head|first|rest|member|item|cls|klass|prop|path|source|target|reifier|graph|path_iri)s?$",
    re.IGNORECASE,
)
TERM_ATTRS = {
    "focus", "value", "component", "shape", "severity", "source_constraint", "subject", "predicate", "object", "iri",
    "node", "datatype", "path_iri", "term", "literal", "reifier", "annotations", "messages", "details",
}  # fmt: skip
PLAIN_FUNCS = {
    "stringify_node", "_prefixed", "_var_name", "_rdflib_text", "fspath", "term_text", "text_of", "args_of", "_local", "_local_name", "_n3", "dn", "sn",
    "text", "lexical", "iri_text", "n3", "local_name", "len", "int", "float", "bool", "repr", "hex", "sorted", "min", "max",
    "sum", "abs", "round", "ord", "chr", "type_name", "_show",
}  # fmt: skip
PLAIN_METHODS = {
    "join", "format", "lower", "upper", "strip", "lstrip", "rstrip", "replace", "split", "rsplit", "title", "casefold", "hex",
    "isoformat", "encode", "decode", "getvalue", "n3", "describe", "removeprefix", "removesuffix", "ljust", "rjust", "zfill",
}  # fmt: skip
PLAIN_ATTRS = {"value", "language", "lexical", "id", "name", "__name__", "args", "kind", "reason", "message", "text", "where", "position", "pattern", "flags", "direction", "key"}  # fmt: skip
PLAIN_NAME = re.compile(
    r"(^lo$|^hi$|^n$|^version$|^word$|^tail$|^conforms$|^suffix$|^shown$|^more$|^argument$|^max_\w+$|^limit$|^where$|^mode$|_text|_name|_str|_msg|_message|_reason|_label|_prefix|_suffix|_key|_kind|_id|_count|_size|_len|_pattern|_regex|_flags|_lang|"
    r"^text|^name|^msg|^message|^reason|^label|^prefix|^key|^kind|^lang|^language|^pattern|^regex|^flags|^body|^query|^sparql|^line|"
    r"^lines|^desc|^description|^what|^why|^detail|^expected|^count|^size|^limit|^depth|^i|^j|^k|^idx|^index|^pos|^num|^total|"
    r"^exc|^err|^error|^e|^ex|^lexical|^lex|^fn_name|^method|^op|^fname|^filename|^path_text|^iri_text|^uri|^url|^ns|^base|^tag|^code|"
    r"^out|^sep|^indent|^pad|^head_text|^reason_text|^label_text|^kw|^arg_name|^var|^variable|^varname|^param|^param_name)$",
    re.IGNORECASE,
)  # fmt: skip
CONSTANT = re.compile(r"^_?[A-Z][A-Z0-9_]*$")  # case sensitive: MODULE_CONSTANTS are plain
OK_MARK = re.compile(r"#\s*str-ok:\s*\S")
OK_FILE = re.compile(r"^#\s*str-ok-file:\s*\S", re.MULTILINE)  # a module that works on rdflib terms throughout (see below)
RDFLIB_ONLY_FORBIDDEN_IMPORTS = {"SH", "RDF", "RDFS", "XSD", "OWL", "NamedNode", "BlankNode", "Literal", "Triple", "NS"}


def _ident(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _plain(node: ast.AST, exc_names: set[str]) -> bool:
    """Is ``node`` provably a plain value (a string, a number, ...), never a pyoxigraph term?"""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Name):
        if node.id in exc_names:
            return True
        if CONSTANT.match(node.id):
            return True
        return bool(PLAIN_NAME.search(node.id)) and not TERMISH_NAME.search(node.id)
    if isinstance(node, ast.Attribute):
        if node.attr in {"value"}:  # `<term>.value` is the lexical value / IRI text of a pyoxigraph term
            return True
        if node.attr in PLAIN_ATTRS:
            return True
        if node.attr in TERM_ATTRS:
            return False
        return bool(PLAIN_NAME.search(node.attr)) and not TERMISH_NAME.search(node.attr)
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id in PLAIN_FUNCS
        if isinstance(f, ast.Attribute):
            return f.attr in PLAIN_METHODS or f.attr in PLAIN_FUNCS
        return False
    if isinstance(node, ast.BinOp):
        return _plain(node.left, exc_names) and _plain(node.right, exc_names)
    if isinstance(node, ast.IfExp):
        return _plain(node.body, exc_names) and _plain(node.orelse, exc_names)
    if isinstance(node, ast.BoolOp):
        return all(_plain(v, exc_names) for v in node.values)
    if isinstance(node, ast.Subscript):  # a slice of a string / an item of a plain sequence
        return _plain(node.value, exc_names)
    if isinstance(node, ast.UnaryOp):
        return _plain(node.operand, exc_names)
    if isinstance(node, ast.Tuple | ast.List):
        return False
    return False


def _exc_names(tree: ast.AST) -> set[str]:
    return {h.name for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler) and h.name}


def violations(source: str) -> list[tuple[int, str]]:
    """``(line, description)`` of every formatting use of a not-provably-plain value in ``source``."""
    tree = ast.parse(source)
    lines = source.splitlines()
    exc = _exc_names(tree)
    found: list[tuple[int, str]] = []

    def ok(node: ast.AST, stmt_line: int) -> bool:
        for ln in {node.lineno, getattr(node, "end_lineno", node.lineno), stmt_line}:
            if 0 < ln <= len(lines) and OK_MARK.search(lines[ln - 1]):
                return True
        return False

    def report(node: ast.AST, what: str, arg: ast.AST, stmt_line: int) -> None:
        if not _plain(arg, exc) and not ok(node, stmt_line):
            found.append((node.lineno, f"{what} of {ast.unparse(arg)!r}"))

    class V(ast.NodeVisitor):
        stmt_line = 0

        def generic_visit(self, node: ast.AST) -> None:
            if isinstance(node, ast.stmt):
                previous, self.stmt_line = self.stmt_line, node.lineno
                super().generic_visit(node)
                self.stmt_line = previous
            else:
                super().generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            f = node.func
            if isinstance(f, ast.Name) and f.id == "str" and len(node.args) >= 1:
                report(node, "str()", node.args[0], self.stmt_line)
            elif isinstance(f, ast.Attribute) and f.attr == "format" and isinstance(f.value, ast.Constant):
                for a in [*node.args, *(k.value for k in node.keywords)]:
                    report(node, "str.format()", a, self.stmt_line)
            type_test = isinstance(f, ast.Name) and f.id in {"isinstance", "issubclass"}
            for passed in [] if type_test else [*node.args, *(k.value for k in node.keywords)]:
                if isinstance(passed, ast.Name) and passed.id == "str" and not ok(node, self.stmt_line):
                    found.append((node.lineno, "str passed as a function (key=str / map(str, ...))"))
            self.generic_visit(node)

        def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
            if node.conversion == ord("r"):
                self.generic_visit(node)
                return  # `!r` is repr(): an explicit developer-facing rendering, not a silent wrong string
            report(node, "f-string field", node.value, self.stmt_line)
            self.generic_visit(node)

        def visit_BinOp(self, node: ast.BinOp) -> None:
            if isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                args = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
                for a in args:
                    report(node, "% formatting", a, self.stmt_line)
            self.generic_visit(node)

    V().visit(tree)
    return found


def _rdflib_only(source: str) -> bool:
    return bool(OK_FILE.search(source))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ENGINE)))
def test_module_never_formats_a_term(path):
    source = path.read_text()
    bad = [] if _rdflib_only(source) else violations(source)
    assert not bad, (
        f"{path.name}: formatting a value that may be a pyoxigraph term (use terms.text / lexical / iri_text / n3, or "
        "mark the line `# str-ok: <reason>`):\n" + "\n".join(f"  line {ln}: {what}" for ln, what in bad)
    )


@pytest.mark.parametrize("path", [p for p in FILES if _rdflib_only(p.read_text())], ids=lambda p: p.name)
def test_str_ok_file_modules_really_are_rdflib_only(path):
    """`# str-ok-file:` exempts a module because every term in it is an rdflib term (it renders results or reads the caller's
    graphs at the boundary). Hold it to that: no pyoxigraph, no engine term constants from `terms`."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("pyoxigraph") for a in node.names), "imports pyoxigraph"
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("pyoxigraph"), "imports pyoxigraph"
            if node.module == "starlayer.shacl_engine.terms":
                assert not ({a.name for a in node.names} & RDFLIB_ONLY_FORBIDDEN_IMPORTS), "imports engine term constants"


# ---- the checker itself ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        "str(term)",
        "str(node)",
        "str(self.focus)",
        "str(lit)",
        "str(r.value)  if False else str(value)",
        "f'{subject}'",
        "f'{res.focus} is bad'",
        "'%s' % predicate",
        "'%s %s' % (a_node, 1)",
        "'{}'.format(obj_literal)",
        "str(x)",
        "f'{shape}'",
        "sorted(terms, key=str)",
        "list(map(str, terms))",
        "str(result.component)",
    ],
)
def test_checker_flags_term_formatting(snippet):
    assert violations(snippet), snippet


@pytest.mark.parametrize(
    "snippet",
    [
        "str(term.value)",
        "f'{lit.value}'",
        "f'{text(term)}'",
        "str(len(x))",
        "f'{name}: {message}'",
        "'%s' % reason_text",
        "'{}'.format(lexical(term))",
        "str(term)  # str-ok: a plain python int here",
        "try:\n    pass\nexcept ValueError as exc:\n    msg = f'{exc}'",
        "f'{n}'.join([])",
        "f'{term!r}'",
        "f'{MAX_DEPTH}'",
    ],
)
def test_checker_accepts_plain_values(snippet):
    assert not violations(snippet), snippet
