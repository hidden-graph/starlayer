"""Unit tests for codekg.extractor.imports.build_import_table().

All fixtures are small synthetic source snippets, parsed fresh via
ast.parse() - never a real project file.
"""

import ast

from codekg.extractor.imports import build_import_table


def _table(source: str, module_dotted_path: str = "pkg.sub.mod") -> dict[str, str]:
    tree = ast.parse(source)
    return build_import_table(tree, module_dotted_path)


class TestPlainImport:
    def test_simple_import(self):
        table = _table("import os\n")
        assert table == {"os": "os"}

    def test_dotted_import_binds_top_level_name_only(self):
        # `import a.b.c` binds just `a` in the namespace, mapped to the
        # dotted path "a" (not the full "a.b.c") - accessing a.b.c works
        # through attribute chaining off the bound `a`.
        table = _table("import a.b.c\n")
        assert table == {"a": "a"}

    def test_dotted_import_with_asname_maps_full_path(self):
        # `import a.b.c as x` binds `x` to the FULL dotted path "a.b.c".
        table = _table("import a.b.c as z\n")
        assert table == {"z": "a.b.c"}

    def test_simple_import_with_asname(self):
        table = _table("import os as operating_system\n")
        assert table == {"operating_system": "os"}

    def test_multiple_names_one_statement(self):
        table = _table("import os, sys as system\n")
        assert table == {"os": "os", "system": "sys"}


class TestImportFrom:
    def test_absolute_from_import(self):
        table = _table("from rdflib import URIRef\n")
        assert table == {"URIRef": "rdflib.URIRef"}

    def test_absolute_from_import_with_asname(self):
        table = _table("from rdflib import URIRef as Ref\n")
        assert table == {"Ref": "rdflib.URIRef"}

    def test_absolute_from_import_submodule(self):
        table = _table("from rdflib.term import Node\n")
        assert table == {"Node": "rdflib.term.Node"}

    def test_star_import_adds_no_binding(self):
        table = _table("from rdflib import *\n")
        assert table == {}

    def test_star_import_does_not_crash_alongside_others(self):
        table = _table("from rdflib import *\nfrom rdflib import URIRef\n")
        assert table == {"URIRef": "rdflib.URIRef"}


class TestRelativeImportFrom:
    def test_relative_import_from_x_import_y_level1(self):
        # module_dotted_path = "starlayer.graph.model.encoding", level=1 ->
        # base package "starlayer.graph.model" (strip 1 trailing
        # component), so `from .triple import TripleTerm` binds
        # TripleTerm -> "starlayer.graph.model.triple.TripleTerm".
        table = _table(
            "from .triple import TripleTerm\n",
            module_dotted_path="starlayer.graph.model.encoding",
        )
        assert table == {"TripleTerm": "starlayer.graph.model.triple.TripleTerm"}

    def test_relative_from_import_level2_strips_two_components(self):
        # module_dotted_path = "starlayer.graph.model.encoding", level=2 ->
        # strip 2 trailing components -> base package "starlayer.graph",
        # then node.module "other" appended -> "starlayer.graph.other".
        table = _table(
            "from ..other import Thing\n",
            module_dotted_path="starlayer.graph.model.encoding",
        )
        assert table == {"Thing": "starlayer.graph.other.Thing"}

        # distinct from the level=1 result for the same alias name
        table_level1 = _table(
            "from .other import Thing\n",
            module_dotted_path="starlayer.graph.model.encoding",
        )
        assert table_level1 == {"Thing": "starlayer.graph.model.other.Thing"}
        assert table != table_level1

    def test_bare_dot_import_level1(self):
        # `from . import x` at level=1: base package is module_dotted_path
        # ("pkg.sub.mod") with 1 trailing component stripped ("mod"), so
        # base package is "pkg.sub"; node.module is None, so x binds
        # directly under that base package.
        table = _table(
            "from . import x\n",
            module_dotted_path="pkg.sub.mod",
        )
        assert table == {"x": "pkg.sub.x"}

    def test_bare_dot_import_level2(self):
        # level=2 strips 2 trailing components ("sub", "mod"), leaving
        # just "pkg" as the base package.
        table = _table(
            "from .. import y\n",
            module_dotted_path="pkg.sub.mod",
        )
        assert table == {"y": "pkg.y"}

    def test_relative_import_with_asname(self):
        table = _table(
            "from .triple import TripleTerm as TT\n",
            module_dotted_path="starlayer.graph.model.encoding",
        )
        assert table == {"TT": "starlayer.graph.model.triple.TripleTerm"}


class TestFunctionBodyLocalImports:
    def test_import_nested_in_function_body_is_found(self):
        source = (
            "def term_key(term):\n"
            "    from rdflib.term import Node\n"
            "    return Node\n"
        )
        table = _table(source)
        assert table == {"Node": "rdflib.term.Node"}

    def test_mix_of_module_level_and_function_level_imports(self):
        source = (
            "import os\n"
            "\n"
            "def f():\n"
            "    from rdflib import URIRef\n"
            "    return URIRef\n"
        )
        table = _table(source)
        assert table == {"os": "os", "URIRef": "rdflib.URIRef"}

    def test_import_nested_in_method_body_is_found(self):
        source = (
            "class C:\n"
            "    def m(self):\n"
            "        import json\n"
            "        return json\n"
        )
        table = _table(source)
        assert table == {"json": "json"}


class TestShadowing:
    def test_later_module_level_import_overrides_earlier(self):
        source = "import os as x\nimport sys as x\n"
        table = _table(source)
        assert table == {"x": "sys"}

    def test_empty_module_returns_empty_table(self):
        table = _table("x = 1\n")
        assert table == {}
