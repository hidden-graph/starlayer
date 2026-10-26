"""Call-graph scoping and repeated definitions in visitor.extract_module() (GitHub issues #102 and #84).

Python scoping: a class body is not an enclosing scope for its methods, a parameter or local variable hides a module
function of the same name, and a nested function's calls belong to the nested function. One IRI per name, so a property's
setter and an ``@overload`` series must not write conflicting facts about it.
"""

from __future__ import annotations

from collections import Counter

from rdflib import Literal
from rdflib.namespace import DCTERMS, RDF, RDFS
from starlayer.codekg import CODEKG_NS

from .test_visitor import _extract, _extract_multi, _objects

SLKG = CODEKG_NS


def _iri(triples, dotted_suffix):
    matches = {s for s, p, o in triples if p == DCTERMS.identifier and o == Literal(f"starlayer.fixture.{dotted_suffix}")}
    assert len(matches) == 1, f"expected exactly one {dotted_suffix!r}, found {len(matches)}"
    return next(iter(matches))


def _called(triples, caller: str) -> set[str]:
    names = {s: str(o) for s, p, o in triples if p == DCTERMS.identifier}
    return {names[o].removeprefix("starlayer.fixture.") for o in _objects(triples, _iri(triples, caller), SLKG.calls)}


def _run(tmp_path, source):
    return _extract_multi(tmp_path, {"fixture.py": source})["fixture.py"]


def test_a_bare_call_in_a_method_is_the_module_function_not_the_sibling_method(tmp_path) -> None:
    triples = _run(tmp_path, "def bar():\n    pass\n\nclass C:\n    def bar(self):\n        pass\n\n    def foo(self):\n        bar()\n")
    assert _called(triples, "C.foo") == {"bar"}


def test_a_bare_call_in_a_method_with_no_module_function_resolves_to_nothing(tmp_path) -> None:
    triples = _run(tmp_path, "class C:\n    def bar(self):\n        pass\n\n    def foo(self):\n        bar()\n")
    assert _called(triples, "C.foo") == set()


def test_self_calls_still_resolve_to_the_sibling_method(tmp_path) -> None:
    triples = _run(tmp_path, "class C:\n    def bar(self):\n        pass\n\n    def foo(self):\n        self.bar()\n")
    assert _called(triples, "C.foo") == {"C.bar"}


def test_a_nested_function_is_still_visible_to_its_siblings_and_to_the_enclosing_function(tmp_path) -> None:
    source = "def outer():\n    def a():\n        pass\n\n    def b():\n        a()\n\n    a()\n    b()\n"
    triples = _run(tmp_path, source)
    assert _called(triples, "outer") == {"outer.a", "outer.b"}
    assert _called(triples, "outer.b") == {"outer.a"}


def test_a_parameter_shadows_a_module_function(tmp_path) -> None:
    triples = _run(tmp_path, "def helper():\n    pass\n\ndef shadow(helper):\n    helper()\n")
    assert _called(triples, "shadow") == set()


def test_a_local_variable_shadows_a_module_function(tmp_path) -> None:
    source = "def helper():\n    pass\n\ndef shadow2():\n    helper = lambda: 1\n    helper()\n\ndef plain():\n    helper()\n"
    triples = _run(tmp_path, source)
    assert _called(triples, "shadow2") == set()
    assert _called(triples, "plain") == {"helper"}


def test_a_name_bound_in_an_enclosing_function_shadows_for_the_nested_function(tmp_path) -> None:
    source = "def helper():\n    pass\n\ndef outer(helper):\n    def inner():\n        helper()\n"
    assert _called(_run(tmp_path, source), "outer.inner") == set()


def test_a_global_declaration_keeps_the_module_function(tmp_path) -> None:
    source = "def helper():\n    pass\n\ndef f():\n    global helper\n    helper()\n"
    assert _called(_run(tmp_path, source), "f") == {"helper"}


def test_a_nested_functions_calls_are_not_attributed_to_the_enclosing_function(tmp_path) -> None:
    source = "def inner_only():\n    pass\n\nclass A:\n    def k(self):\n        def nested():\n            inner_only()\n\n        return nested\n"
    triples = _run(tmp_path, source)
    assert _called(triples, "A.k") == set()
    assert _called(triples, "A.k.nested") == {"inner_only"}


def test_what_a_nested_def_evaluates_in_the_enclosing_scope_is_the_enclosing_functions_call(tmp_path) -> None:
    source = "def deco():\n    return lambda f: f\n\ndef default():\n    return 1\n\ndef outer():\n    @deco()\n    def inner(x=default()):\n        pass\n"
    assert _called(_run(tmp_path, source), "outer") == {"deco", "default"}


def test_a_function_local_import_of_a_nested_def_does_not_leak_to_the_enclosing_function(tmp_path) -> None:
    source = "def validate():\n    pass\n\ndef outer():\n    def inner():\n        from other import validate\n\n    validate()\n"
    assert _called(_run(tmp_path, source), "outer") == {"validate"}


PROPERTY = '''
class C:
    @property
    def x(self):
        """The value."""
        return self._get()

    @x.setter
    def x(self, value):
        """Set it."""
        self._set(value)

    def _get(self):
        return 1

    def _set(self, value):
        pass
'''


def _facts(triples, suffix):
    iri = _iri(triples, suffix)
    return iri, [(p, o) for s, p, o in triples if s == iri]


def test_a_property_and_its_setter_share_one_iri_without_conflicting_facts(tmp_path) -> None:
    triples = _extract(tmp_path, PROPERTY)
    iri, facts = _facts(triples, "C.x")
    counts = Counter(p for p, _ in set(facts))
    for single in (RDF.type, RDFS.label, RDFS.comment, SLKG.lineStart, SLKG.lineEnd, SLKG.signature, DCTERMS.identifier):
        assert counts[single] <= 1, f"{single} has conflicting values: {[o for p, o in set(facts) if p == single]}"
    assert (SLKG.isProperty, Literal(True)) in facts
    assert (RDFS.comment, Literal("The value.")) in facts  # the getter describes the property
    assert len([1 for s, p, o in triples if s == iri and p == SLKG.hasDecorator]) == 1


def test_a_setters_calls_are_added_to_the_property(tmp_path) -> None:
    triples = _run(tmp_path, PROPERTY)
    assert _called(triples, "C.x") == {"C._get", "C._set"}


OVERLOAD = '''
from typing import overload

@overload
def f(x: int) -> int: ...
@overload
def f(x: str) -> str: ...
def f(x):
    """Implementation."""
    return helper(x)

def helper(x):
    return x
'''


def test_overload_stubs_do_not_write_facts_about_the_implementation(tmp_path) -> None:
    triples = _run(tmp_path, OVERLOAD)
    iri, facts = _facts(triples, "f")
    counts = Counter(p for p, _ in set(facts))
    for single in (SLKG.lineStart, SLKG.signature, RDFS.comment):
        assert counts[single] <= 1, f"{single} has conflicting values"
    assert (RDFS.comment, Literal("Implementation.")) in facts
    assert (SLKG.signature, Literal("def f(x)")) in facts
    assert _called(triples, "f") == {"helper"}


def test_a_series_of_only_overload_stubs_is_described_by_the_last_one(tmp_path) -> None:
    source = "from typing import overload\n\n@overload\ndef f(x: int) -> int: ...\n@overload\ndef f(x: str) -> str: ...\n"
    iri, facts = _facts(_extract(tmp_path, source), "f")
    assert (SLKG.signature, Literal("def f(x: str) -> str")) in facts
    assert Counter(p for p, _ in set(facts))[SLKG.signature] == 1
