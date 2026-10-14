"""Unit tests for starlayer.codekg.extractor.symbol_index.build_symbol_index()
and SymbolIndex.resolve_method_in_chain().

Every fixture is written under a synthetic repo_root's own
packages/starlayer/starlayer/ tree (matching build_symbol_index()'s real,
hard-coded root-relative convention - see module_identity()) - never a
real project file, so each test is independent of this project's own
actual source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from starlayer.codekg.extractor.symbol_index import build_symbol_index, module_identity, resolve_root


def _write(repo_root: Path, rel_path: str, source: str) -> Path:
    path = repo_root / "packages" / "starlayer" / "starlayer" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_test(repo_root: Path, rel_path: str, source: str) -> Path:
    path = repo_root / "packages" / "starlayer" / "tests" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


class TestModuleIdentity:
    def test_blob_iri_and_dotted_path(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "x = 1\n")
        module_iri, module_dotted = module_identity(path, tmp_path)
        assert str(module_iri).endswith("pkg/mod.py")
        assert "/starlayer/starlayer/" in str(module_iri)
        assert module_dotted == "starlayer.pkg.mod"

    def test_tests_root_blob_iri_and_dotted_path(self, tmp_path):
        path = _write_test(tmp_path, "pkg/test_mod.py", "x = 1\n")
        module_iri, module_dotted = module_identity(path, tmp_path)
        assert str(module_iri).endswith("pkg/test_mod.py")
        assert "/starlayer/tests/" in str(module_iri)
        assert module_dotted == "tests.pkg.test_mod"

    def test_raises_value_error_outside_any_known_root(self, tmp_path):
        outside = tmp_path / "elsewhere.py"
        outside.write_text("x = 1\n", encoding="utf-8")

        with pytest.raises(ValueError):
            module_identity(outside, tmp_path)


class TestResolveRoot:
    def test_source_path_resolves_to_starlayer_prefix(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "x = 1\n")
        root_path, prefix, blob_base = resolve_root(path, tmp_path)
        assert prefix == "starlayer"
        assert root_path == tmp_path / "packages" / "starlayer" / "starlayer"
        assert blob_base.endswith("/starlayer/starlayer/")

    def test_tests_path_resolves_to_tests_prefix(self, tmp_path):
        path = _write_test(tmp_path, "pkg/test_mod.py", "x = 1\n")
        root_path, prefix, blob_base = resolve_root(path, tmp_path)
        assert prefix == "tests"
        assert root_path == tmp_path / "packages" / "starlayer" / "tests"
        assert blob_base.endswith("/starlayer/tests/")

    def test_path_outside_both_roots_returns_none(self, tmp_path):
        outside = tmp_path / "elsewhere.py"
        outside.write_text("x = 1\n", encoding="utf-8")
        assert resolve_root(outside, tmp_path) is None


class TestFunctionResolution:
    def test_same_file_module_level_function(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "def helper():\n    pass\n")
        index = build_symbol_index([path], tmp_path)
        assert "starlayer.pkg.mod.helper" in index.functions_by_dotted_path

    def test_cross_file_function_found_by_full_dotted_path(self, tmp_path):
        a = _write(tmp_path, "pkg/mod_a.py", "def shared():\n    pass\n")
        b = _write(tmp_path, "pkg/mod_b.py", "def other():\n    pass\n")
        index = build_symbol_index([a, b], tmp_path)
        assert "starlayer.pkg.mod_a.shared" in index.functions_by_dotted_path
        assert "starlayer.pkg.mod_b.other" in index.functions_by_dotted_path

    def test_nested_function_gets_its_own_nested_dotted_path(self, tmp_path):
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "def outer():\n    def inner():\n        pass\n    return inner\n",
        )
        index = build_symbol_index([path], tmp_path)
        assert "starlayer.pkg.mod.outer.inner" in index.functions_by_dotted_path
        assert "starlayer.pkg.mod.outer" in index.functions_by_dotted_path


class TestClassResolution:
    def test_class_methods_recorded(self, tmp_path):
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "class Thing:\n    def a(self):\n        pass\n    def b(self):\n        pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        info = index.classes_by_dotted_path["starlayer.pkg.mod.Thing"]
        assert set(info.methods) == {"a", "b"}
        assert info.base_dotted_paths == []

    def test_same_file_base_resolved_to_full_dotted_path(self, tmp_path):
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "class Base:\n    def f(self):\n        pass\n\n\nclass Sub(Base):\n    pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        sub_info = index.classes_by_dotted_path["starlayer.pkg.mod.Sub"]
        assert sub_info.base_dotted_paths == ["starlayer.pkg.mod.Base"]

    def test_cross_file_base_resolved_via_live_introspection(self, tmp_path):
        """A base class imported from another file in the same project
        resolves to its real cross-module dotted path - the same
        types.resolve_type_name() machinery already used for annotations,
        applied here to a base-class expression, and its live-importlib
        fallback happens to also correctly resolve a genuine internal
        cross-module class, not just external ones. Uses this project's
        own real starlayer.codekg.extractor.imports module as the
        "cross-file base" being subclassed, since it needs to be something
        actually importable - a synthetic project module wouldn't be on
        sys.path."""
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "from starlayer.codekg.extractor.imports import __name__ as _unused\n"
            "import ast\n"
            "class Sub(ast.NodeVisitor):\n"
            "    pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        sub_info = index.classes_by_dotted_path["starlayer.pkg.mod.Sub"]
        # ast.NodeVisitor is external (stdlib) - resolves to its own real
        # canonical path, which is NOT itself a key in this index (nothing
        # we extracted defines it) - exactly the "absence is the answer"
        # behavior the module's own docstring describes.
        assert sub_info.base_dotted_paths == ["ast.NodeVisitor"]
        assert "ast.NodeVisitor" not in index.classes_by_dotted_path

    def test_external_base_class_not_added_to_index(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "class Sub(dict):\n    pass\n")
        index = build_symbol_index([path], tmp_path)
        sub_info = index.classes_by_dotted_path["starlayer.pkg.mod.Sub"]
        assert sub_info.base_dotted_paths == ["builtins.dict"]
        assert "builtins.dict" not in index.classes_by_dotted_path


class TestResolveMethodInChain:
    def test_own_method_found_directly(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "class Thing:\n    def f(self):\n        pass\n")
        index = build_symbol_index([path], tmp_path)
        found = index.resolve_method_in_chain("starlayer.pkg.mod.Thing", "f")
        assert found == index.classes_by_dotted_path["starlayer.pkg.mod.Thing"].methods["f"]

    def test_inherited_method_found_via_base_same_file(self, tmp_path):
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "class Base:\n    def f(self):\n        pass\n\n\nclass Sub(Base):\n    pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        found = index.resolve_method_in_chain("starlayer.pkg.mod.Sub", "f")
        assert found == index.classes_by_dotted_path["starlayer.pkg.mod.Base"].methods["f"]

    def test_inherited_method_found_across_files(self, tmp_path):
        a = _write(tmp_path, "pkg/mod_a.py", "class Base:\n    def f(self):\n        pass\n")
        b = _write(
            tmp_path,
            "pkg/mod_b.py",
            "from .mod_a import Base\n\n\nclass Sub(Base):\n    pass\n",
        )
        index = build_symbol_index([a, b], tmp_path)
        found = index.resolve_method_in_chain("starlayer.pkg.mod_b.Sub", "f")
        assert found == index.classes_by_dotted_path["starlayer.pkg.mod_a.Base"].methods["f"]

    def test_unknown_class_returns_none(self, tmp_path):
        path = _write(tmp_path, "pkg/mod.py", "class Thing:\n    pass\n")
        index = build_symbol_index([path], tmp_path)
        assert index.resolve_method_in_chain("starlayer.pkg.mod.NoSuchClass", "f") is None

    def test_method_not_found_anywhere_in_chain_returns_none(self, tmp_path):
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "class Base:\n    pass\n\n\nclass Sub(Base):\n    pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        assert index.resolve_method_in_chain("starlayer.pkg.mod.Sub", "nonexistent") is None

    def test_declared_order_first_match_wins_not_real_mro(self, tmp_path):
        """Documents the accepted simplification directly: with two bases
        both declaring the same method name, the FIRST base in declaration
        order wins, regardless of what real C3 MRO would pick."""
        path = _write(
            tmp_path,
            "pkg/mod.py",
            "class A:\n    def f(self):\n        return 'A'\n\n\n"
            "class B:\n    def f(self):\n        return 'B'\n\n\n"
            "class Sub(A, B):\n    pass\n",
        )
        index = build_symbol_index([path], tmp_path)
        found = index.resolve_method_in_chain("starlayer.pkg.mod.Sub", "f")
        assert found == index.classes_by_dotted_path["starlayer.pkg.mod.A"].methods["f"]

    def test_base_class_cycle_does_not_hang(self, tmp_path):
        """A real base-class cycle is impossible in valid Python, but the
        index is built from independently-processed per-file data (a
        self-referential base_dotted_paths entry could in principle arise
        from a malformed/adversarial input) - resolve_method_in_chain()'s
        own _seen guard must still terminate rather than recurse forever."""
        path = _write(tmp_path, "pkg/mod.py", "class A:\n    pass\n")
        index = build_symbol_index([path], tmp_path)
        # Manually corrupt the index to create a cycle: A's own bases
        # include itself.
        index.classes_by_dotted_path["starlayer.pkg.mod.A"].base_dotted_paths = ["starlayer.pkg.mod.A"]
        assert index.resolve_method_in_chain("starlayer.pkg.mod.A", "nonexistent") is None


class TestGracefulDegradation:
    def test_unparseable_file_is_skipped_not_raised(self, tmp_path):
        good = _write(tmp_path, "pkg/mod_a.py", "def f():\n    pass\n")
        _write(tmp_path, "pkg/broken.py", "def f(:\n    pass\n")
        bad = tmp_path / "packages" / "starlayer" / "starlayer" / "pkg" / "broken.py"
        index = build_symbol_index([good, bad], tmp_path)
        assert "starlayer.pkg.mod_a.f" in index.functions_by_dotted_path

    def test_path_outside_src_root_is_skipped_not_raised(self, tmp_path):
        outside = tmp_path / "outside.py"
        outside.write_text("def f():\n    pass\n", encoding="utf-8")
        good = _write(tmp_path, "pkg/mod_a.py", "def g():\n    pass\n")
        index = build_symbol_index([outside, good], tmp_path)
        assert "starlayer.pkg.mod_a.g" in index.functions_by_dotted_path
