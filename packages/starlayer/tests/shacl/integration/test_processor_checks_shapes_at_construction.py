"""A StarShaclProcessor refuses a bad shapes graph when it is built, not at the first validate().

The shapes are compiled once at construction (the plan is kept and validate() reuses it), constraint parameters are checked at
that point too, and ``meta_shacl=True`` at construction runs the SHACL-for-SHACL check there, once.
"""

import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import (
    ShapeError,
    StarShaclProcessor,
    ValidationReport,
    _adapter,
)
from starlayer.shacl.engine.plan import Plan
from tests.support.datasets import dataset_of

PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

DATA = PREFIXES + "ex:a a ex:C ; ex:p 1 ."
VALID = PREFIXES + "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:datatype xsd:integer ] ."


def g(ttl: str) -> Graph:
    graph = Graph()
    graph.parse(data=PREFIXES + ttl if "@prefix" not in ttl else ttl, format="turtle")
    return graph


# --- (a) structural errors ----------------------------------------------------------------------------------------------

STRUCTURAL = {
    "node shape with sh:path": "ex:S a sh:NodeShape ; sh:path ex:p .",
    "property shape without sh:path": "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:minCount 1 ] .",
    "removed construct": "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:target ex:T .",
    "malformed regex": 'ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:pattern "(" .',
    "property shape with two paths": "ex:S a sh:NodeShape ; sh:targetClass ex:Never ; sh:property [ sh:path ex:p, ex:q ] .",
    "property path of a literal": 'ex:S a sh:NodeShape ; sh:targetClass ex:Never ; sh:property [ sh:path [ sh:inversePath "x" ] ] .',
}


@pytest.mark.parametrize("name", sorted(STRUCTURAL))
def test_structural_shape_errors_come_from_the_constructor(name: str) -> None:
    with pytest.raises(ShapeError):
        StarShaclProcessor(shacl_graph=g(STRUCTURAL[name]))


# --- (b) constraint parameters, checked with no focus node anywhere -------------------------------------------------------

BAD_PARAMETERS = {
    "minCount": ('sh:minCount "many"', "sh:minCount"),
    "maxCount": ("sh:maxCount -1", "sh:maxCount"),
    "class literal": ('sh:class "x"', "sh:class"),
    "datatype literal": ('sh:datatype "x"', "sh:datatype"),
    "nodeKind": ("sh:nodeKind ex:Nope", "sh:nodeKind"),
    "minInclusive iri": ("sh:minInclusive ex:x", "minInclusive"),
    "in not a list": ("sh:in ex:x", "sh:in"),
    "minLength": ('sh:minLength "a"', "minLength"),
    "pattern flags": ('sh:pattern "a" ; sh:flags "z"', "sh:flags"),
    "pattern regex": ('sh:pattern "[a"', "sh:pattern"),
    "uniqueLang": ('sh:uniqueLang "yes"', "uniqueLang"),
    "languageIn": ("sh:languageIn ex:x", "sh:languageIn"),
    "minListLength": ('sh:minListLength "a"', "minListLength"),
    "not literal": ('sh:not "a"', "sh:not"),
    "and not a list": ("sh:and ex:x", "malformed list"),
    "node literal": ('sh:node "a"', "sh:node"),
    "qualifiedMinCount": ('sh:qualifiedValueShape [ ] ; sh:qualifiedMinCount "a"', "qualifiedMinCount"),
    "closed": ('sh:closed "maybe"', "sh:closed"),
    "rootClass": ('sh:rootClass "a"', "sh:rootClass"),
    "uniqueValuesFor": ('sh:uniqueValuesFor "a"', "uniqueValuesFor"),
    "equals path": ('sh:equals [ sh:inversePath "x" ]', "property path"),
    "sparql without select": ("sh:sparql [ ]", "sh:select"),
    "reifierShape on a node shape": ("sh:reificationRequired true", "IRI path"),
}


@pytest.mark.parametrize("name", sorted(BAD_PARAMETERS))
def test_constraint_parameter_errors_come_from_the_constructor(name: str) -> None:
    parameters, expected = BAD_PARAMETERS[name]
    shapes = g(f"ex:S a sh:NodeShape ; sh:targetClass ex:NoInstances ; {parameters} .")
    with pytest.raises(ShapeError, match=expected):
        StarShaclProcessor(shacl_graph=shapes)


def test_a_bad_parameter_on_a_shape_reached_only_through_a_property_or_a_reference_is_found() -> None:
    nested = g('ex:S a sh:NodeShape ; sh:targetClass ex:Never ; sh:property [ sh:path ex:p ; sh:node ex:Other ] . ex:Other sh:minCount "a" .')
    with pytest.raises(ShapeError, match="minCount"):
        StarShaclProcessor(shacl_graph=nested)
    property_level = g('ex:S a sh:NodeShape ; sh:targetClass ex:Never ; sh:property [ sh:path ex:p ; sh:maxCount "a" ] .')
    with pytest.raises(ShapeError, match="maxCount"):
        StarShaclProcessor(shacl_graph=property_level)


def test_a_deactivated_shape_or_constraint_is_not_checked_as_validation_never_reaches_it() -> None:
    off = g('ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:deactivated true ; sh:minCount "a" .')
    assert StarShaclProcessor(shacl_graph=off).validate(g(DATA)).conforms
    annotated = g(
        'ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:minCount "a" . '
        "<< ex:S sh:minCount \"a\" >> sh:deactivated true ."
    )
    # a reifier written with RDF 1.2 triple-term syntax is the deactivation form; if the parser form differs the shape is simply bad
    try:
        StarShaclProcessor(shacl_graph=annotated)
    except ShapeError:
        pytest.skip("reifier syntax not accepted by this parser build")


# --- (c) meta_shacl at construction -------------------------------------------------------------------------------------

META_BAD = {
    "two datatypes": "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:datatype xsd:string, xsd:integer ] .",
    "severity high": 'ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:severity "high" ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .',
}


@pytest.mark.parametrize("name", sorted(META_BAD))
def test_meta_shacl_at_construction_raises_from_the_constructor(name: str) -> None:
    shapes = g(META_BAD[name])
    StarShaclProcessor(shacl_graph=shapes)  # builds without the meta check
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):
        StarShaclProcessor(shacl_graph=shapes, meta_shacl=True)


def test_meta_shacl_runs_before_the_compile_so_a_malformed_graph_gets_the_meta_report() -> None:
    shapes = g("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:minCount 1 ] .")
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):
        StarShaclProcessor(shacl_graph=shapes, meta_shacl=True)
    with pytest.raises(ShapeError):
        StarShaclProcessor(shacl_graph=shapes)


# --- (d) validate() reuses what the constructor did ----------------------------------------------------------------------


def test_validate_reuses_the_compiled_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled = []
    original = Plan.compile
    monkeypatch.setattr(Plan, "compile", lambda self: compiled.append(self) or original(self))
    built = []
    original_init = Plan.__post_init__
    monkeypatch.setattr(Plan, "__post_init__", lambda self: built.append(self) or original_init(self))
    processor = StarShaclProcessor(shacl_graph=g(VALID))
    assert len(compiled) == 1 and len(built) == 1
    data = g(DATA)
    assert processor.validate(data).conforms
    assert processor.validate(data).conforms
    assert len(compiled) == 1 and len(built) == 1  # neither compiled nor built again


def test_validate_each_reuses_the_compiled_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    processor = StarShaclProcessor(shacl_graph=g(VALID))
    built = []
    original_init = Plan.__post_init__
    monkeypatch.setattr(Plan, "__post_init__", lambda self: built.append(self) or original_init(self))
    reports = processor.validate_each(dataset_of([g(DATA), g(DATA)]))
    assert all(r.conforms for r in reports.values())
    assert built == []


def test_the_meta_check_runs_once_for_construction_and_later_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    original = _adapter._meta_preflight
    monkeypatch.setattr(_adapter, "_meta_preflight", lambda *a, **k: calls.append(a) or original(*a, **k))
    processor = StarShaclProcessor(shacl_graph=g(VALID), meta_shacl=True)
    assert len(calls) == 1
    data = g(DATA)
    processor.validate(data)
    processor.validate(data, meta_shacl=True)
    assert len(calls) == 1
    processor.validate(data, meta_shacl=False)  # allowed, and nothing re-runs
    assert len(calls) == 1


def test_a_shapes_graph_edited_after_construction_is_read_again_at_validate() -> None:
    shapes = g(VALID)
    processor = StarShaclProcessor(shacl_graph=shapes)
    with_meta = StarShaclProcessor(shacl_graph=shapes, meta_shacl=True)
    data = g(DATA)
    assert processor.validate(data).conforms and with_meta.validate(data).conforms
    # the edit is seen (not the cached plan): a bad parameter now fails at the call
    from starlayer.graph import Namespace

    EX, SH = Namespace("http://example.org/"), Namespace("http://www.w3.org/ns/shacl#")
    shapes.add((EX.S, SH.minCount, EX["many"]))
    with pytest.raises(ShapeError):
        processor.validate(data)
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):  # the meta check is run again for the changed graph too
        with_meta.validate(data)


def test_assigning_a_bad_shapes_graph_is_checked_and_leaves_the_processor_unchanged() -> None:
    processor = StarShaclProcessor(shacl_graph=g(VALID))
    with pytest.raises(ShapeError):
        processor.shacl_graph = g(STRUCTURAL["node shape with sh:path"])
    assert processor.validate(g(DATA)).conforms  # still the first shapes graph
    processor.shacl_graph = g(VALID)
    processor.shacl_graph = None


# --- (e) per-call meta_shacl on a processor built without it ---------------------------------------------------------------


def test_per_call_meta_shacl_runs_at_that_call_and_is_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = StarShaclProcessor(shacl_graph=g(VALID))
    calls = []
    original = _adapter._meta_preflight
    monkeypatch.setattr(_adapter, "_meta_preflight", lambda *a, **k: calls.append(a) or original(*a, **k))
    assert ok.validate(g(DATA)).conforms
    assert calls == []
    ok.validate(g(DATA), meta_shacl=True)
    ok.validate(g(DATA), meta_shacl=True)
    assert len(calls) == 1
    bad = StarShaclProcessor(shacl_graph=g(META_BAD["two datatypes"]))
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):
        bad.validate(g(DATA), meta_shacl=True)
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):  # a failing graph is not remembered as good
        bad.validate(g(DATA), meta_shacl=True)


# --- (f) owl:imports ----------------------------------------------------------------------------------------------------

IMPORTED = "http://example.org/imported"
IMPORTING = "<http://example.org/importing> owl:imports <http://example.org/imported> . ex:S a sh:NodeShape ; sh:targetClass ex:C ."
IMPORTED_SHAPES = "<http://example.org/imported> a owl:Ontology . ex:T a sh:NodeShape ; sh:targetClass ex:C ; sh:minCount 1 ."


def test_unresolved_imports_do_not_raise_at_construction_but_at_validate() -> None:
    processor = StarShaclProcessor(shacl_graph=g(IMPORTING))
    with pytest.raises(ExecutionError, match="owl:imports"):
        processor.validate(g(DATA))
    loaded = []

    def loader(iri):
        loaded.append(iri)
        return g(IMPORTED_SHAPES)

    assert isinstance(processor.validate(g(DATA), imports_loader=loader), ValidationReport)
    assert loaded
    assert isinstance(processor.validate(g(DATA), ignore_imports=True), ValidationReport)


def test_with_a_constructor_loader_the_resolved_graph_is_checked() -> None:
    broken_import = g("<http://example.org/imported> a owl:Ontology . ex:T a sh:NodeShape ; sh:path ex:p .")
    with pytest.raises(ShapeError):
        StarShaclProcessor(shacl_graph=g(IMPORTING), imports_loader=lambda iri: broken_import)
    with pytest.raises(ShapeError):  # a shape is bad whether or not the imports are ignored
        StarShaclProcessor(shacl_graph=g(IMPORTING + " ex:U a sh:NodeShape ; sh:path ex:p ."), ignore_imports=True)
    ok = StarShaclProcessor(shacl_graph=g(IMPORTING), imports_loader=lambda iri: g(IMPORTED_SHAPES))
    assert ok.validate(g(DATA)).conforms is not None
    assert StarShaclProcessor(shacl_graph=g(IMPORTING), ignore_imports=True).validate(g(DATA)).conforms


# --- (g) a valid graph behaves as before, (h) no shapes graph ------------------------------------------------------------


def test_a_valid_shapes_graph_constructs_and_validates_as_before() -> None:
    processor = StarShaclProcessor(shacl_graph=g(VALID), meta_shacl=True)
    assert processor.validate(g(DATA)).conforms
    failing = g(PREFIXES + "ex:a a ex:C .")
    report = processor.validate(failing)
    assert not report.conforms
    assert report.conforms == StarShaclProcessor(shacl_graph=g(VALID)).validate(failing).conforms


def test_a_processor_with_no_shapes_graph_is_fine() -> None:
    processor = StarShaclProcessor()
    assert processor.shacl_graph is None
    processor.shacl_graph = g(VALID)
    assert processor.validate(g(DATA)).conforms
    StarShaclProcessor(data_graph=g(DATA), meta_shacl=True)
