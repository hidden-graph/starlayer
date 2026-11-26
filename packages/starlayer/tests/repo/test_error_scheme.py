"""The library's error scheme (step A, stages 0 and 0b): ``starlayer/errors.py`` is a leaf module with the base ``StarLayerError``, the
SHACL errors live there and are re-exported as the same objects, and a shapes-graph error is not a ``ValueError``."""

from __future__ import annotations

import ast
import copy
import pickle
import re
import sys
from pathlib import Path

import pytest
import starlayer.errors as errors
import starlayer.shacl as shacl
import starlayer.shacl.errors as shacl_errors
from starlayer.errors import (
    ExecutionError,
    FormatError,
    MetaShaclError,
    ShapeCompileError,
    ShapeError,
    StarLayerError,
    only_kind,
)

PACKAGE = Path(errors.__file__).resolve().parent
ERRORS_PY = PACKAGE / "errors.py"
NAMES = ("StarLayerError", "ShapeError", "ShapeCompileError", "MetaShaclError", "ExecutionError", "FormatError")


def test_the_class_tree():
    assert StarLayerError.__bases__ == (Exception,)
    assert ShapeError.__bases__ == (StarLayerError,)
    assert ShapeCompileError.__bases__ == (ShapeError,)
    assert MetaShaclError.__bases__ == (ShapeError,)
    assert ExecutionError.__bases__ == (StarLayerError,)
    assert FormatError.__bases__ == (StarLayerError,)
    assert not issubclass(FormatError, ExecutionError) and not issubclass(FormatError, ShapeError)
    assert not issubclass(ExecutionError, ShapeError)
    assert not issubclass(ShapeCompileError, MetaShaclError) and not issubclass(MetaShaclError, ShapeCompileError)


@pytest.mark.parametrize("cls", [getattr(errors, name) for name in NAMES])
def test_every_class_derives_from_the_library_base_and_no_builtin_but_exception(cls):
    assert issubclass(cls, StarLayerError)
    for builtin in (ValueError, TypeError, SyntaxError, RuntimeError, OSError, LookupError, AssertionError):
        assert not issubclass(cls, builtin), (cls, builtin)


def test_a_shape_error_is_not_a_value_error_so_an_except_value_error_misses_it():
    with pytest.raises(ShapeCompileError):
        try:
            raise ShapeCompileError("bad shape")
        except ValueError:  # pragma: no cover - must not catch it
            pytest.fail("ShapeCompileError was caught as a ValueError")


def test_the_execution_kinds_are_the_six_of_step_c_and_the_three_of_owl_dl_reasoning():
    assert "nesting" not in ExecutionError.KINDS  # merged into "limit" (2026-11-26)
    assert tuple(ExecutionError.KINDS) == ("rule", "expression", "recursion", "constraint-query", "internal",
                                           "timeout", "inconsistent", "inference", "query", "import", "unsupported", "limit")
    with pytest.raises(ValueError, match="unknown ExecutionError kind"):
        ExecutionError("x", kind="nope")


def test_only_kind_returns_for_a_listed_kind_and_reraises_otherwise():
    error = ExecutionError("x", kind="rule")
    only_kind(error, "rule", "expression")
    with pytest.raises(ExecutionError) as caught:
        only_kind(error, "expression")
    assert caught.value is error


def test_errors_py_imports_only_the_standard_library():
    """The module is a leaf, so importing it can never be part of an import cycle."""
    tree = ast.parse(ERRORS_PY.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative import"
            roots.add((node.module or "").split(".")[0])
    assert roots, "expected at least the __future__ and typing imports"
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    assert roots <= stdlib, sorted(roots - stdlib)


@pytest.mark.parametrize("name", NAMES[1:])
def test_the_public_names_are_the_same_objects_everywhere(name):
    assert getattr(shacl, name) is getattr(errors, name)
    assert getattr(shacl_errors, name) is getattr(errors, name)


def test_the_old_homes_leave_no_shim_behind():
    from starlayer.shacl.engine import meta, plan

    for module in (plan, meta):
        for name in ("ExecutionError", "only_kind", "_rebuild_execution_error"):
            assert not hasattr(module, name), (module.__name__, name)
        assert not set(getattr(module, "__all__", ())) & set(NAMES)


def test_no_class_is_defined_twice_in_the_package():
    defined = []
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and node.name in NAMES:
                defined.append((path.relative_to(PACKAGE).as_posix(), node.name))
    assert sorted(defined) == sorted(("errors.py", name) for name in NAMES)


def _roundtrips(error):
    return [pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)]


@pytest.mark.parametrize("kind", ExecutionError.KINDS)
def test_an_execution_error_survives_pickle_and_copy(kind):
    error = ExecutionError("it failed", kind=kind, context="sh:rule ex:R1")
    for again in _roundtrips(error):
        assert type(again) is ExecutionError
        assert (str(again), again.kind, again.context) == (str(error), kind, "sh:rule ex:R1")
        assert again.args == error.args and again.report_url == error.report_url
    assert _roundtrips(ExecutionError("no place", kind=kind))[0].context is None
    assert _roundtrips(ExecutionError("no place", kind=kind))[0].unresolved == ()


def test_an_import_error_keeps_its_unresolved_iris_through_pickle_and_copy():
    import pyoxigraph as ox

    iris = (ox.NamedNode("http://example.org/a"), ox.NamedNode("http://example.org/b"))
    error = ExecutionError("not resolved", kind="import", context="owl:imports <a>, <b>", unresolved=iris)
    assert error.unresolved == iris and ExecutionError("x", kind="import", unresolved=list(iris)).unresolved == iris  # always a tuple
    for again in _roundtrips(error):
        assert type(again) is ExecutionError and again.unresolved == iris
        assert (again.kind, again.context, str(again)) == ("import", "owl:imports <a>, <b>", "not resolved")


@pytest.mark.parametrize("cls", [ShapeError, ShapeCompileError])
def test_a_shape_error_survives_pickle_and_copy(cls):
    error = cls("bad", context="sh:path")
    for again in _roundtrips(error):
        assert type(again) is cls
        assert (str(again), again.context) == ("bad", "sh:path")
    assert _roundtrips(cls("bad"))[0].context is None


def test_a_meta_error_keeps_its_attributes_through_pickle_and_copy():
    error = MetaShaclError("not valid", ("p1", "p2"), "report text", None, None, context="meta")
    for again in _roundtrips(error):
        assert type(again) is MetaShaclError
        assert str(again) == "not valid"
        assert again.problems == ("p1", "p2") and again.report_text == "report text"
        assert again.report_graph is None and again.scope is None and again.context == "meta"
    plain = _roundtrips(MetaShaclError("m"))[0]
    assert plain.problems == () and plain.report_text == "" and plain.context is None


def test_the_format_kinds_and_the_required_valid_kind():
    assert tuple(FormatError.KINDS) == ("sparql", "srl", "rdf", "manchester", "owl")
    with pytest.raises(TypeError):
        FormatError("no kind")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="unknown FormatError kind"):
        FormatError("x", kind="nope")


def test_a_format_error_defaults():
    error = FormatError("the message", kind="sparql")
    assert str(error) == "the message" and error.why == "the message"
    assert (error.line, error.col, error.pos, error.context) == (None, None, None, None)
    assert str(FormatError(kind="sparql", why="only the reason")) == "only the reason"


@pytest.mark.parametrize("kind", FormatError.KINDS)
def test_a_format_error_survives_pickle_and_copy(kind):
    error = FormatError("at 2:3: bad", kind=kind, context="query", why="bad", line=2, col=3, pos=9)
    for again in _roundtrips(error):
        assert type(again) is FormatError
        assert (str(again), again.kind, again.context, again.why, again.line, again.col, again.pos) == ("at 2:3: bad", kind, "query", "bad", 2, 3, 9)


# ---- the classes the scheme removed, and the kinds in use --------------------------------------------------------------------------

REPO = PACKAGE.parents[2]
SOURCE_ROOTS = [PACKAGE, REPO / "packages" / "starlayer-reasoning" / "starlayer_reasoning", REPO / "tools"]

#: every error class removed across stages 1 to 6 of the scheme (no alias is left for any); a name here must not come back.
REMOVED_CLASSES = (
    "ReasoningTimeoutError", "InconsistentOntologyError",  # stage 1: OWL-DL reasoning
    "SparqlSyntaxError", "SQEError", "SQEValidationError", "SPARQL12ConformanceError",  # stage 2: SPARQL (SQEValidationError left with validate_sparql_tree)
    "SRLError", "SRLParseError", "SRLDecodeError", "SRLImportError", "SRLEvalError", "StratificationError", "SRLImportsNotSupportedError",  # stage 3
    "BasicEncodingError", "InvalidTripleTermError",  # stage 4: RDF documents and terms
    "ManchesterSyntaxError",  # stage 5
    "SRLUnresolvedImportsWarning",  # removed with the parse that validates (a sh:Warning of validate_sparql_tree says it now)
    "CanonicalizationComplexityError", "EntailmentRewriteError", "SqeTextTooDeepError",  # stage 6
)


def _source_files(suffixes=(".py", ".ttl")):
    for root in SOURCE_ROOTS:
        if root.is_dir():
            yield from (p for p in sorted(root.rglob("*")) if p.suffix in suffixes and "__pycache__" not in p.parts and ".venv" not in p.parts)


def test_a_removed_error_class_does_not_come_back_in_the_package_source():
    pattern = re.compile(r"\b(" + "|".join(REMOVED_CLASSES) + r")\b")
    found = [f"{path.relative_to(REPO)}:{number}: {match.group(1)}"
             for path in _source_files() for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             for match in pattern.finditer(line)]
    assert not found, "\n".join(found)


def _error_call_kinds():
    """(file, line, class name, kind literal or None) for each ``ExecutionError(...)`` / ``FormatError(...)`` call, and
    ``(file, line, "only_kind", literal)`` for each kind name given to ``only_kind``."""
    for path in _source_files((".py",)):
        if path == ERRORS_PY:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name in ("ExecutionError", "FormatError"):
                kind = next((k.value for k in node.keywords if k.arg == "kind"), None)
                literal = kind.value if isinstance(kind, ast.Constant) and isinstance(kind.value, str) else None
                yield path.relative_to(REPO).as_posix(), node.lineno, name, literal
            elif name == "only_kind":
                for arg in node.args[1:]:
                    yield path.relative_to(REPO).as_posix(), node.lineno, "only_kind", arg.value if isinstance(arg, ast.Constant) else None


@pytest.mark.parametrize("registry", [ExecutionError.KINDS, FormatError.KINDS], ids=["ExecutionError", "FormatError"])
def test_every_kind_has_a_one_line_meaning(registry):
    """``KINDS`` is the one registry: kind -> meaning, plain strings, so iteration, ``in`` and ``', '.join`` read the names."""
    assert isinstance(registry, dict) and registry
    for kind, meaning in registry.items():
        assert isinstance(kind, str) and isinstance(meaning, str) and meaning.strip() and "\n" not in meaning, kind
    assert ", ".join(registry) == ", ".join(list(registry))
    assert all(k in registry for k in registry)


def test_a_kind_stays_a_plain_string_and_the_error_round_trips():
    for cls in (ExecutionError, FormatError):
        for kind in cls.KINDS:
            error = cls("m", kind=kind)
            assert type(error.kind) is str and error.kind == kind
            assert all(again.kind == kind for again in _roundtrips(error))


def test_every_kind_in_use_at_a_raise_site_is_declared():
    declared = {"ExecutionError": ExecutionError.KINDS, "FormatError": FormatError.KINDS, "only_kind": ExecutionError.KINDS}
    bad = [f"{path}:{line}: {name} kind {kind!r}" for path, line, name, kind in _error_call_kinds() if kind not in declared[name]]
    assert not bad, "\n".join(bad)


def test_every_declared_kind_is_used_somewhere():
    used = {(name, kind) for _path, _line, name, kind in _error_call_kinds() if name != "only_kind"}
    unused = [(name, kind) for name, kinds in (("ExecutionError", ExecutionError.KINDS), ("FormatError", FormatError.KINDS))
              for kind in kinds if (name, kind) not in used]
    assert not unused, f"declared but never raised: {unused}"


def test_endpoint_error_is_the_one_library_error_that_stays_an_os_error():
    from starlayer.graph import EndpointError

    assert EndpointError.__bases__ == (StarLayerError, OSError)
    assert EndpointError("down", 503).status == 503


def test_an_internal_error_says_it_is_a_bug_and_where_to_report_it_once():
    from starlayer.errors import ISSUES_URL

    assert ISSUES_URL == "https://github.com/hidden-graph/starlayer/issues"
    error = ExecutionError("the invariant broke", kind="internal", context="x")
    assert str(error) == f"internal error (a bug in StarLayer, please report it at {ISSUES_URL}): the invariant broke"
    assert error.args == (str(error),) and error.report_url == ISSUES_URL
    assert str(ExecutionError(str(error), kind="internal")) == str(error)  # no double prefix when wrapped or rebuilt
    for again in _roundtrips(error):
        assert str(again) == str(error) and again.report_url == ISSUES_URL
    other = ExecutionError("a rule failed", kind="rule")
    assert str(other) == "a rule failed" and other.report_url is None
    assert all(ExecutionError("m", kind=k).report_url is None for k in ExecutionError.KINDS if k != "internal")
