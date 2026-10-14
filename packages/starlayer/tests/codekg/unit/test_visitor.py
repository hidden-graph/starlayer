"""Unit tests for starlayer.codekg.extractor.visitor.extract_module().

Every fixture is written to a small synthetic .py file under tmp_path -
never a real project file - so each test is independent of whatever the
rest of the project's own source happens to look like.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS

from starlayer.codekg import CODEKG_NS, EXTERNALTYPE_NS
from starlayer.codekg.extractor.symbol_index import build_symbol_index, module_identity
from starlayer.codekg.extractor.visitor import extract_module

SLKG = CODEKG_NS
EXT = EXTERNALTYPE_NS

MODULE_IRI = URIRef("https://example.org/blob/main/fixture.py")
MODULE_DOTTED = "starlayer.fixture"


def _extract(tmp_path: Path, source: str) -> list[tuple]:
    path = tmp_path / "fixture.py"
    path.write_text(source, encoding="utf-8")
    return extract_module(path, MODULE_IRI, MODULE_DOTTED)


def _extract_multi(tmp_path: Path, sources: dict[str, str]) -> dict[str, list[tuple]]:
    """Write several fixture files under tmp_path's own
    packages/starlayer/starlayer/ tree (the real root-relative convention
    - see symbol_index.module_identity()), build one real project-wide
    symbol index across all of them, then extract each with that index
    available - the only way to test cross-file call/override resolution
    faithfully, since that's exactly what a real multi-file extraction
    run does. Returns ``{relative_filename: triples}``.
    """
    src_root = tmp_path / "packages" / "starlayer" / "starlayer"
    paths = {}
    for rel_name, source in sources.items():
        path = src_root / rel_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        paths[rel_name] = path

    index = build_symbol_index(list(paths.values()), tmp_path)

    result = {}
    for rel_name, path in paths.items():
        module_iri, module_dotted = module_identity(path, src_root)
        result[rel_name] = extract_module(path, module_iri, module_dotted, index)
    return result


def _subjects_of_type(triples: list[tuple], rdf_type) -> set:
    return {s for s, p, o in triples if p == RDF.type and o == rdf_type}


def _objects(triples: list[tuple], subj, pred) -> list:
    return [o for s, p, o in triples if s == subj and p == pred]


class TestModuleNode:
    def test_module_triples_present(self, tmp_path):
        triples = _extract(tmp_path, "x = 1\n")
        assert (MODULE_IRI, RDF.type, SLKG.Module) in triples
        assert (MODULE_IRI, RDFS.label, Literal("fixture")) in triples
        assert (MODULE_IRI, DCTERMS.identifier, Literal(MODULE_DOTTED)) in triples
        assert any(p == SLKG.filePath for s, p, o in triples if s == MODULE_IRI)


class TestSimpleFunctionWithTypedParamsAndReturn:
    SOURCE = '''\
def greet(name: str, times: int = 1) -> str:
    """Build a greeting.

    Args:
        name: Who to greet.
        times: How many times to repeat it.

    Returns:
        The assembled greeting string.
    """
    return (name + " ") * times
'''

    def test_function_not_method(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#greet")
        assert (fn_iri, RDF.type, SLKG.Function) in triples
        assert (fn_iri, RDF.type, SLKG.Method) not in triples
        assert (MODULE_IRI, SLKG.declares, fn_iri) in triples

    def test_label_identifier_signature(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#greet")
        assert (fn_iri, RDFS.label, Literal("greet")) in triples
        assert (fn_iri, DCTERMS.identifier, Literal(f"{MODULE_DOTTED}.greet")) in triples
        sigs = _objects(triples, fn_iri, SLKG.signature)
        assert len(sigs) == 1
        assert "def greet(" in str(sigs[0])
        assert "-> str" in str(sigs[0])

    def test_summary_comment(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#greet")
        comments = _objects(triples, fn_iri, RDFS.comment)
        assert comments == [Literal("Build a greeting.")]

    def test_params_with_descriptions_and_types(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#greet")
        name_param = URIRef(f"{fn_iri}.param.name")
        times_param = URIRef(f"{fn_iri}.param.times")

        assert (fn_iri, SLKG.hasParameter, name_param) in triples
        assert (fn_iri, SLKG.hasParameter, times_param) in triples
        assert (name_param, RDFS.label, Literal("name")) in triples
        assert (name_param, SLKG.parameterKind, Literal("positional")) in triples
        assert (name_param, SLKG.position, Literal(0)) in triples
        assert (name_param, RDFS.comment, Literal("Who to greet.")) in triples

        assert (times_param, SLKG.position, Literal(1)) in triples
        assert (times_param, SLKG.defaultValue, Literal("1")) in triples
        assert (times_param, RDFS.comment, Literal("How many times to repeat it.")) in triples

        str_type = EXT["builtins.str"]
        int_type = EXT["builtins.int"]
        assert (name_param, SLKG.hasType, str_type) in triples
        assert (times_param, SLKG.hasType, int_type) in triples
        assert (str_type, RDF.type, SLKG.ExternalType) in triples
        assert (str_type, DCTERMS.identifier, Literal("builtins.str")) in triples

    def test_return_value(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#greet")
        ret_iri = URIRef(f"{fn_iri}.returns")
        assert (fn_iri, SLKG.hasReturnValue, ret_iri) in triples
        assert (ret_iri, RDF.type, SLKG.ReturnValue) in triples
        assert (ret_iri, SLKG.hasType, EXT["builtins.str"]) in triples
        assert (ret_iri, RDFS.comment, Literal("The assembled greeting string.")) in triples


class TestClassWithMethod:
    SOURCE = '''\
class Greeter:
    """Says hello."""

    def say(self, name: str) -> None:
        """Say hello to someone."""
        print(name)
'''

    def test_class_emitted(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        class_iri = URIRef(f"{MODULE_IRI}#Greeter")
        assert (class_iri, RDF.type, SLKG.Class) in triples
        assert (class_iri, RDFS.label, Literal("Greeter")) in triples
        assert (class_iri, RDFS.comment, Literal("Says hello.")) in triples
        assert (MODULE_IRI, SLKG.declares, class_iri) in triples

    def test_method_not_function(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        class_iri = URIRef(f"{MODULE_IRI}#Greeter")
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.say")
        assert (method_iri, RDF.type, SLKG.Method) in triples
        assert (method_iri, RDF.type, SLKG.Function) not in triples
        assert (class_iri, SLKG.declares, method_iri) in triples

    def test_unannotated_self_is_skipped_and_real_param_renumbered(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.say")
        self_param = URIRef(f"{method_iri}.param.self")
        name_param = URIRef(f"{method_iri}.param.name")

        assert not any(s == self_param for s, p, o in triples)
        assert (method_iri, SLKG.hasParameter, self_param) not in triples

        assert (method_iri, SLKG.hasParameter, name_param) in triples
        assert (name_param, SLKG.position, Literal(0)) in triples


class TestClassMethodSkipsCls:
    SOURCE = '''\
class Greeter:
    @classmethod
    def make(cls, name: str) -> "Greeter":
        """Build a Greeter."""
        return cls()
'''

    def test_cls_skipped_and_real_param_at_position_zero(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.make")
        cls_param = URIRef(f"{method_iri}.param.cls")
        name_param = URIRef(f"{method_iri}.param.name")

        assert not any(s == cls_param for s, p, o in triples)
        assert (method_iri, SLKG.hasParameter, name_param) in triples
        assert (name_param, SLKG.position, Literal(0)) in triples


class TestAnnotatedSelfIsKept:
    SOURCE = '''\
class Greeter:
    def say(self: "Greeter", name: str) -> None:
        """Say hello to someone."""
        print(name)
'''

    def test_annotated_self_emitted(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.say")
        self_param = URIRef(f"{method_iri}.param.self")
        name_param = URIRef(f"{method_iri}.param.name")

        assert (method_iri, SLKG.hasParameter, self_param) in triples
        assert (self_param, SLKG.position, Literal(0)) in triples
        assert (self_param, SLKG.annotationText, Literal("'Greeter'")) in triples

        assert (method_iri, SLKG.hasParameter, name_param) in triples
        assert (name_param, SLKG.position, Literal(1)) in triples


class TestModuleLevelFunctionNamedSelfParamNotSkipped:
    SOURCE = '''\
def f(self, x):
    pass
'''

    def test_self_emitted_at_position_zero_outside_class(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        self_param = URIRef(f"{fn_iri}.param.self")
        x_param = URIRef(f"{fn_iri}.param.x")

        assert (fn_iri, SLKG.hasParameter, self_param) in triples
        assert (self_param, SLKG.position, Literal(0)) in triples
        assert (x_param, SLKG.position, Literal(1)) in triples


class TestMethodWithOnlySelfHasNoParameters:
    SOURCE = '''\
class Greeter:
    def noop(self):
        pass
'''

    def test_zero_parameter_triples(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.noop")

        assert not _objects(triples, method_iri, SLKG.hasParameter)
        assert not _subjects_of_type(triples, SLKG.Parameter)


class TestNestedFunctionInsideFunction:
    SOURCE = '''\
def outer():
    def inner():
        pass
    return inner
'''

    def test_inner_declared_by_outer_as_function_not_method(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        outer_iri = URIRef(f"{MODULE_IRI}#outer")
        inner_iri = URIRef(f"{MODULE_IRI}#outer.inner")
        assert (outer_iri, SLKG.declares, inner_iri) in triples
        assert (inner_iri, RDF.type, SLKG.Function) in triples
        assert (inner_iri, RDF.type, SLKG.Method) not in triples
        # inner is declared by outer (a Function), not by the module
        assert (MODULE_IRI, SLKG.declares, inner_iri) not in triples


class TestNestedClassInsideClass:
    SOURCE = '''\
class Outer:
    class Inner:
        pass
'''

    def test_inner_class_nesting_path(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        outer_iri = URIRef(f"{MODULE_IRI}#Outer")
        inner_iri = URIRef(f"{MODULE_IRI}#Outer.Inner")
        assert (inner_iri, RDF.type, SLKG.Class) in triples
        assert (outer_iri, SLKG.declares, inner_iri) in triples
        assert (inner_iri, DCTERMS.identifier, Literal(f"{MODULE_DOTTED}.Outer.Inner")) in triples


class TestDecorator:
    SOURCE = '''\
def deco(f):
    return f


@deco
def decorated():
    pass
'''

    def test_decorator_node_and_edge(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#decorated")
        dec_iri = URIRef(f"{fn_iri}.decorator.0")
        assert (fn_iri, SLKG.hasDecorator, dec_iri) in triples
        assert (dec_iri, RDF.type, SLKG.Decorator) in triples
        assert (dec_iri, SLKG.decoratorText, Literal("deco")) in triples
        assert (dec_iri, SLKG.position, Literal(0)) in triples


class TestExternalTypeReference:
    SOURCE = '''\
import rdflib


def f(g: rdflib.Graph):
    pass
'''

    def test_external_type_minted_with_canonical_path(self, tmp_path):
        import rdflib

        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        param_iri = URIRef(f"{fn_iri}.param.g")
        canonical = f"{rdflib.Graph.__module__}.{rdflib.Graph.__qualname__}"
        ext_iri = EXT[canonical]
        assert (param_iri, SLKG.hasType, ext_iri) in triples
        assert (ext_iri, RDF.type, SLKG.ExternalType) in triples
        assert (ext_iri, RDFS.subClassOf, SLKG.Type) in triples
        assert (ext_iri, DCTERMS.identifier, Literal(canonical)) in triples
        assert (ext_iri, RDFS.label, Literal(canonical.rsplit(".", 1)[-1])) in triples

    def test_external_type_descriptive_triples_emitted_once(self, tmp_path):
        source = '''\
import rdflib


def f(g: rdflib.Graph):
    pass


def h(g2: rdflib.Graph) -> rdflib.Graph:
    pass
'''
        triples = _extract(tmp_path, source)
        import rdflib

        canonical = f"{rdflib.Graph.__module__}.{rdflib.Graph.__qualname__}"
        ext_iri = EXT[canonical]
        type_decls = [t for t in triples if t == (ext_iri, RDF.type, SLKG.ExternalType)]
        assert len(type_decls) == 1


class TestParameterWithNoAnnotation:
    SOURCE = '''\
def f(x):
    pass
'''

    def test_no_type_or_annotation_text(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        param_iri = URIRef(f"{fn_iri}.param.x")
        assert (param_iri, RDF.type, SLKG.Parameter) in triples
        assert not _objects(triples, param_iri, SLKG.hasType)
        assert not _objects(triples, param_iri, SLKG.annotationText)
        assert not _objects(triples, param_iri, SLKG.optional)


class TestInheritanceLocal:
    SOURCE = '''\
class Bar:
    pass


class Foo(Bar):
    pass
'''

    def test_subclass_of_local_class(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        bar_iri = URIRef(f"{MODULE_IRI}#Bar")
        foo_iri = URIRef(f"{MODULE_IRI}#Foo")
        assert (foo_iri, RDFS.subClassOf, bar_iri) in triples


class TestInheritanceExternal:
    SOURCE = '''\
import collections


class Foo(collections.OrderedDict):
    pass
'''

    def test_subclass_of_external_type(self, tmp_path):
        import collections

        triples = _extract(tmp_path, self.SOURCE)
        foo_iri = URIRef(f"{MODULE_IRI}#Foo")
        canonical = f"{collections.OrderedDict.__module__}.{collections.OrderedDict.__qualname__}"
        ext_iri = EXT[canonical]
        assert (foo_iri, RDFS.subClassOf, ext_iri) in triples
        assert (ext_iri, RDF.type, SLKG.ExternalType) in triples


class TestAsyncFunction:
    SOURCE = '''\
async def f():
    pass
'''

    def test_is_async_true(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        assert (fn_iri, SLKG.isAsync, Literal(True)) in triples


class TestSyncFunctionOmitsIsAsync:
    SOURCE = '''\
def f():
    pass
'''

    def test_is_async_omitted(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        assert not _objects(triples, fn_iri, SLKG.isAsync)


class TestOptionalParameter:
    SOURCE = '''\
def f(x: str | None = None):
    pass
'''

    def test_optional_flag_set(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        param_iri = URIRef(f"{fn_iri}.param.x")
        assert (param_iri, SLKG.optional, Literal(True)) in triples
        assert (param_iri, SLKG.hasType, EXT["builtins.str"]) in triples


class TestVarargsAndKwargs:
    SOURCE = '''\
def f(a, *args, b, **kwargs):
    pass
'''

    def test_vararg_and_varkw_kinds_and_no_position(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        a_param = URIRef(f"{fn_iri}.param.a")
        args_param = URIRef(f"{fn_iri}.param.args")
        b_param = URIRef(f"{fn_iri}.param.b")
        kwargs_param = URIRef(f"{fn_iri}.param.kwargs")

        assert (a_param, SLKG.parameterKind, Literal("positional")) in triples
        assert (a_param, SLKG.position, Literal(0)) in triples

        assert (args_param, SLKG.parameterKind, Literal("vararg")) in triples
        assert not _objects(triples, args_param, SLKG.position)

        assert (b_param, SLKG.parameterKind, Literal("kwonly")) in triples
        assert (b_param, SLKG.position, Literal(1)) in triples

        assert (kwargs_param, SLKG.parameterKind, Literal("varkw")) in triples
        assert not _objects(triples, kwargs_param, SLKG.position)


class TestDocstringMentionsNonexistentParam:
    SOURCE = '''\
def f(x):
    """Do a thing.

    Args:
        x: The real param.
        y: This parameter does not exist.

    Returns:
        Nothing.
    """
    pass
'''

    def test_does_not_crash_and_emits_nothing_for_phantom_param(self, tmp_path, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="starlayer.codekg.extractor.visitor"):
            triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        phantom_param = URIRef(f"{fn_iri}.param.y")
        assert not any(s == phantom_param for s, p, o in triples)
        assert any("y" in record.message for record in caplog.records)


class TestGracefulDegradationOnSyntaxError:
    def test_unparseable_file_returns_empty_list_without_raising(self, tmp_path):
        path = tmp_path / "broken.py"
        path.write_text("def f(:\n    pass\n", encoding="utf-8")
        triples = extract_module(path, MODULE_IRI, MODULE_DOTTED)
        assert triples == []


class TestPosonlyParameters:
    SOURCE = '''\
def f(a, b, /, c):
    pass
'''

    def test_posonly_kind_and_positions(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        fn_iri = URIRef(f"{MODULE_IRI}#f")
        a_param = URIRef(f"{fn_iri}.param.a")
        c_param = URIRef(f"{fn_iri}.param.c")
        assert (a_param, SLKG.parameterKind, Literal("posonly")) in triples
        assert (a_param, SLKG.position, Literal(0)) in triples
        assert (c_param, SLKG.parameterKind, Literal("positional")) in triples
        assert (c_param, SLKG.position, Literal(2)) in triples


class TestModuleLevelImportsOnly:
    SOURCE = '''\
import json


def f():
    import os
    return os, json
'''

    def test_only_module_level_import_gets_edge(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        import_edges = [o for s, p, o in triples if s == MODULE_IRI and p == SLKG.importsModule]
        assert import_edges == [EXT["json"]]


class TestTypeCheckingGuardedImportGetsEdge:
    SOURCE = '''\
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy


def f():
    pass
'''

    def test_import_nested_in_type_checking_block_gets_edge(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        assert (MODULE_IRI, SLKG.importsModule, EXT["numpy"]) in triples


class TestTryExceptFallbackImportBothGetEdges:
    SOURCE = '''\
try:
    import ujson as json
except ImportError:
    import json
'''

    def test_both_try_and_except_imports_get_edges(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        import_edges = {o for s, p, o in triples if s == MODULE_IRI and p == SLKG.importsModule}
        assert EXT["ujson"] in import_edges
        assert EXT["json"] in import_edges


class TestDataclassAttributes:
    SOURCE = '''\
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: int
    y: int = 0
'''

    def test_attributes_emitted_with_position_and_type(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        class_iri = URIRef(f"{MODULE_IRI}#Point")
        x_attr = URIRef(f"{class_iri}.attr.x")
        y_attr = URIRef(f"{class_iri}.attr.y")

        assert (class_iri, SLKG.hasAttribute, x_attr) in triples
        assert (class_iri, SLKG.hasAttribute, y_attr) in triples

        assert (x_attr, RDF.type, SLKG.Attribute) in triples
        assert (x_attr, RDFS.label, Literal("x")) in triples
        assert (x_attr, SLKG.position, Literal(0)) in triples
        assert (x_attr, SLKG.hasType, EXT["builtins.int"]) in triples
        assert not _objects(triples, x_attr, SLKG.defaultValue)

        assert (y_attr, RDF.type, SLKG.Attribute) in triples
        assert (y_attr, RDFS.label, Literal("y")) in triples
        assert (y_attr, SLKG.position, Literal(1)) in triples
        assert (y_attr, SLKG.hasType, EXT["builtins.int"]) in triples
        assert (y_attr, SLKG.defaultValue, Literal("0")) in triples


class TestPropertyMethod:
    SOURCE = '''\
class Thing:
    @property
    def value(self) -> int:
        return 1
'''

    def test_is_property_true_others_absent(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Thing.value")
        assert (method_iri, SLKG.isProperty, Literal(True)) in triples
        assert not _objects(triples, method_iri, SLKG.isClassmethod)
        assert not _objects(triples, method_iri, SLKG.isStaticmethod)


class TestClassmethodAndStaticmethod:
    SOURCE = '''\
class Thing:
    @classmethod
    def make(cls) -> "Thing":
        return cls()

    @staticmethod
    def helper() -> int:
        return 1
'''

    def test_classmethod_flag(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Thing.make")
        assert (method_iri, SLKG.isClassmethod, Literal(True)) in triples
        assert not _objects(triples, method_iri, SLKG.isProperty)
        assert not _objects(triples, method_iri, SLKG.isStaticmethod)

    def test_staticmethod_flag(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Thing.helper")
        assert (method_iri, SLKG.isStaticmethod, Literal(True)) in triples
        assert not _objects(triples, method_iri, SLKG.isProperty)
        assert not _objects(triples, method_iri, SLKG.isClassmethod)


class TestOrdinaryMethodHasNoDecoratorFlags:
    SOURCE = '''\
class Thing:
    def ordinary(self) -> int:
        return 1
'''

    def test_no_flags_asserted(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Thing.ordinary")
        assert not _objects(triples, method_iri, SLKG.isProperty)
        assert not _objects(triples, method_iri, SLKG.isClassmethod)
        assert not _objects(triples, method_iri, SLKG.isStaticmethod)


class TestNestedClassInsideFunctionWithLocalBase:
    SOURCE = '''\
class Base:
    pass


def make_subclass():
    class Sub(Base):
        pass
    return Sub
'''

    def test_declares_edge_and_local_subclass_of(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        base_iri = URIRef(f"{MODULE_IRI}#Base")
        fn_iri = URIRef(f"{MODULE_IRI}#make_subclass")
        sub_iri = URIRef(f"{MODULE_IRI}#make_subclass.Sub")

        assert (fn_iri, SLKG.declares, sub_iri) in triples
        assert (sub_iri, RDF.type, SLKG.Class) in triples
        assert (sub_iri, RDFS.subClassOf, base_iri) in triples


class TestVisibilityFlags:
    SOURCE = '''\
class _PrivateClass:
    pass


class PublicClass:
    def public_method(self):
        pass

    def _private_method(self):
        pass

    def __dunder_method__(self):
        pass


def public_fn():
    pass


def _private_fn():
    pass
'''

    def test_private_class_flagged(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        iri = URIRef(f"{MODULE_IRI}#_PrivateClass")
        assert (iri, SLKG.isPrivate, Literal(True)) in triples
        assert not _objects(triples, iri, SLKG.isDunder)

    def test_public_class_not_flagged(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        iri = URIRef(f"{MODULE_IRI}#PublicClass")
        assert not _objects(triples, iri, SLKG.isPrivate)
        assert not _objects(triples, iri, SLKG.isDunder)

    def test_public_method_not_flagged(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        iri = URIRef(f"{MODULE_IRI}#PublicClass.public_method")
        assert not _objects(triples, iri, SLKG.isPrivate)
        assert not _objects(triples, iri, SLKG.isDunder)

    def test_private_method_flagged(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        iri = URIRef(f"{MODULE_IRI}#PublicClass._private_method")
        assert (iri, SLKG.isPrivate, Literal(True)) in triples
        assert not _objects(triples, iri, SLKG.isDunder)

    def test_dunder_method_flagged_dunder_not_private(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        iri = URIRef(f"{MODULE_IRI}#PublicClass.__dunder_method__")
        assert (iri, SLKG.isDunder, Literal(True)) in triples
        assert not _objects(triples, iri, SLKG.isPrivate)

    def test_module_level_functions(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        public_iri = URIRef(f"{MODULE_IRI}#public_fn")
        private_iri = URIRef(f"{MODULE_IRI}#_private_fn")
        assert not _objects(triples, public_iri, SLKG.isPrivate)
        assert (private_iri, SLKG.isPrivate, Literal(True)) in triples


class TestMethodOverrideSameFile:
    SOURCE = '''\
class Base:
    def greet(self):
        return "base"

    def only_on_base(self):
        return "ok"


class Child(Base):
    def greet(self):
        return "child"
'''

    def test_overriding_method_gets_overrides_edge(self, tmp_path):
        triples = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})["fixture.py"]
        child_greet = [s for s, p, o in triples if p == DCTERMS.identifier and o == Literal("starlayer.fixture.Child.greet")][0]
        base_greet = [s for s, p, o in triples if p == DCTERMS.identifier and o == Literal("starlayer.fixture.Base.greet")][0]
        assert (child_greet, SLKG.overrides, base_greet) in triples

    def test_non_overriding_method_gets_no_edge(self, tmp_path):
        triples = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})["fixture.py"]
        base_only = [s for s, p, o in triples if p == DCTERMS.identifier and o == Literal("starlayer.fixture.Base.only_on_base")][0]
        assert not _objects(triples, base_only, SLKG.overrides)


class TestMethodOverrideCrossFileNotDetected:
    """Override detection is deliberately scoped to same-file base classes
    only (approved scope, narrower than call resolution) - a real
    override of a cross-file base method must get no edge in this
    version, not a best-effort guess."""

    def test_cross_file_override_gets_no_edge(self, tmp_path):
        results = _extract_multi(
            tmp_path,
            {
                "mod_a.py": "class Base:\n    def greet(self):\n        return 'base'\n",
                "mod_b.py": (
                    "from .mod_a import Base\n\n\n"
                    "class Child(Base):\n"
                    "    def greet(self):\n"
                    "        return 'child'\n"
                ),
            },
        )
        b_triples = results["mod_b.py"]
        # Find Child.greet's own IRI directly rather than hardcoding it.
        greet_iris = [s for s, p, o in b_triples if p == RDFS.label and o == Literal("greet")]
        assert len(greet_iris) == 1
        assert not _objects(b_triples, greet_iris[0], SLKG.overrides)


class TestCallResolutionSameFile:
    SOURCE = '''\
def helper_fn():
    return 42


def module_fn():
    return helper_fn()


class Thing:
    def a(self):
        return self.b()

    def b(self):
        return 1

    def unresolved_call(self):
        x = Thing()
        return x.a()
'''

    def _id(self, triples, dotted_suffix):
        matches = [s for s, p, o in triples if p == DCTERMS.identifier and o == Literal(f"starlayer.fixture.{dotted_suffix}")]
        assert len(matches) == 1, f"expected exactly one {dotted_suffix!r}, found {len(matches)}"
        return matches[0]

    def test_bare_name_call_to_function_declared_later(self, tmp_path):
        triples = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})["fixture.py"]
        caller = self._id(triples, "module_fn")
        callee = self._id(triples, "helper_fn")
        assert (caller, SLKG.calls, callee) in triples

    def test_self_call_to_sibling_method(self, tmp_path):
        triples = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})["fixture.py"]
        caller = self._id(triples, "Thing.a")
        callee = self._id(triples, "Thing.b")
        assert (caller, SLKG.calls, callee) in triples

    def test_call_through_local_variable_is_not_resolved(self, tmp_path):
        """x.a() where x is a local variable, not self/cls/a known module
        alias/local class name - no type inference here, so this must get
        no edge at all rather than a guessed one."""
        triples = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})["fixture.py"]
        caller = self._id(triples, "Thing.unresolved_call")
        calls = _objects(triples, caller, SLKG.calls)
        a_method = self._id(triples, "Thing.a")
        assert a_method not in calls


class TestCallResolutionCrossFile:
    def test_bare_import_call_resolves_across_files(self, tmp_path):
        results = _extract_multi(
            tmp_path,
            {
                "mod_a.py": "def shared():\n    return 1\n",
                "mod_b.py": "from .mod_a import shared\n\n\ndef caller():\n    return shared()\n",
            },
        )
        b_triples = results["mod_b.py"]
        caller_iris = [s for s, p, o in b_triples if p == RDFS.label and o == Literal("caller")]
        assert len(caller_iris) == 1
        calls = _objects(b_triples, caller_iris[0], SLKG.calls)
        assert len(calls) == 1
        assert str(calls[0]).endswith("mod_a.py#shared")

    def test_module_alias_call_resolves_across_files(self, tmp_path):
        results = _extract_multi(
            tmp_path,
            {
                "mod_a.py": "def shared():\n    return 1\n",
                "mod_b.py": "from . import mod_a\n\n\ndef caller():\n    return mod_a.shared()\n",
            },
        )
        b_triples = results["mod_b.py"]
        caller_iris = [s for s, p, o in b_triples if p == RDFS.label and o == Literal("caller")]
        assert len(caller_iris) == 1
        calls = _objects(b_triples, caller_iris[0], SLKG.calls)
        assert any(str(c).endswith("mod_a.py#shared") for c in calls)

    def test_inherited_self_call_resolves_across_files(self, tmp_path):
        results = _extract_multi(
            tmp_path,
            {
                "mod_a.py": "class Base:\n    def helper(self):\n        return 1\n",
                "mod_b.py": (
                    "from .mod_a import Base\n\n\n"
                    "class Child(Base):\n"
                    "    def uses_inherited(self):\n"
                    "        return self.helper()\n"
                ),
            },
        )
        b_triples = results["mod_b.py"]
        caller_iris = [s for s, p, o in b_triples if p == RDFS.label and o == Literal("uses_inherited")]
        assert len(caller_iris) == 1
        calls = _objects(b_triples, caller_iris[0], SLKG.calls)
        assert any(str(c).endswith("mod_a.py#Base.helper") for c in calls)


class TestCallResolutionLocalImportShadowing:
    """Regression coverage for a real case found in this project's own
    shacl/validator.py: a function-local lazy import of a same-named
    symbol must shadow a same-file module-level function of that name,
    not be bypassed in favor of it."""

    SOURCE = '''\
def validate(x):
    return "local " + str(x)


def wraps_external():
    from fixture_other import validate

    return validate(1)
'''

    def test_local_import_shadows_same_file_function(self, tmp_path):
        results = _extract_multi(tmp_path, {"fixture.py": self.SOURCE})
        triples = results["fixture.py"]
        caller_iris = [s for s, p, o in triples if p == RDFS.label and o == Literal("wraps_external")]
        assert len(caller_iris) == 1
        calls = _objects(triples, caller_iris[0], SLKG.calls)
        local_validate_iris = [
            s for s, p, o in triples if p == DCTERMS.identifier and o == Literal("starlayer.fixture.validate")
        ]
        assert len(local_validate_iris) == 1
        # The call must NOT resolve to this file's own module-level
        # validate() - fixture_other.validate isn't a real project module,
        # so it must resolve to nothing at all, not fall back to the
        # wrong, merely-same-named local function.
        assert local_validate_iris[0] not in calls


class TestCallResolutionWithoutSymbolIndex:
    def test_no_symbol_index_degrades_gracefully_no_calls_edges(self, tmp_path):
        """extract_module() with no symbol_index argument (the default,
        None) must still extract everything else correctly - it just
        can't resolve any calls, since there's no project-wide data to
        resolve against."""
        triples = _extract(
            tmp_path,
            "def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n",
        )
        caller = URIRef(f"{MODULE_IRI}#caller")
        assert not _objects(triples, caller, SLKG.calls)
        # Everything else about caller is still extracted normally.
        assert (caller, RDF.type, SLKG.Function) in triples
