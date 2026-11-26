"""The library's error scheme (step A, stages 0 and 0b): ``starlayer/errors.py`` is a leaf module with the base ``StarLayerError``, the
SHACL errors live there and are re-exported as the same objects, and a shapes-graph error is not a ``ValueError``."""

from __future__ import annotations

import ast
import copy
import pickle
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
    assert ExecutionError.KINDS == ("rule", "expression", "nesting", "recursion", "constraint-query", "internal",
                                    "timeout", "inconsistent", "inference", "query", "import")
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
        assert (str(again), again.kind, again.context) == ("it failed", kind, "sh:rule ex:R1")
    assert _roundtrips(ExecutionError("no place", kind=kind))[0].context is None


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
    assert FormatError.KINDS == ("sparql", "srl", "rdf", "term", "manchester", "owl")
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
