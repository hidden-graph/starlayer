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
from starlayer.codekg.extractor.visitor import extract_module

SLKG = CODEKG_NS
EXT = EXTERNALTYPE_NS

MODULE_IRI = URIRef("https://example.org/blob/main/fixture.py")
MODULE_DOTTED = "starlayer.fixture"


def _extract(tmp_path: Path, source: str) -> list[tuple]:
    path = tmp_path / "fixture.py"
    path.write_text(source, encoding="utf-8")
    return extract_module(path, MODULE_IRI, MODULE_DOTTED)


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

    def test_self_param_has_no_annotation_type(self, tmp_path):
        triples = _extract(tmp_path, self.SOURCE)
        method_iri = URIRef(f"{MODULE_IRI}#Greeter.say")
        self_param = URIRef(f"{method_iri}.param.self")
        assert (method_iri, SLKG.hasParameter, self_param) in triples
        assert not _objects(triples, self_param, SLKG.hasType)
        assert not _objects(triples, self_param, SLKG.annotationText)


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
