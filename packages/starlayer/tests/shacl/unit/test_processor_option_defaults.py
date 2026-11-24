"""``StarShaclProcessor`` constructor defaults for the options that describe the shapes graph or are safety limits:
``meta_shacl``, ``meta_shapes_extra``, ``ignore_imports``, ``shapes_graph_loader``, ``max_validation_depth``, ``max_iterations``,
``max_triples``. Precedence, lowest first: built-in default, constructor, ``mode=`` preset, call keyword."""

from __future__ import annotations

import inspect

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import MetaShaclError, RuleError, ShapeError, StarShaclProcessor
from tests.shacl.integration._shape_loader import load_shape
from tests.support.terms import Namespace

EX = Namespace("http://example.org/")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


DATA = "ex:a a ex:T ."
PLAIN_SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:T ."
# every sh:NodeShape must carry rdfs:label: a meta-shape the plain shapes break
LABEL_RULE = "[] a sh:NodeShape ; sh:targetClass sh:NodeShape ; sh:property [ sh:path rdfs:label ; sh:minCount 1 ] ."


def meta_fails(p: StarShaclProcessor, **kw) -> bool:
    try:
        p.validate(g(DATA), **kw)
    except MetaShaclError:
        return True
    return False


# --- meta_shacl, meta_shapes_extra ------------------------------------------------------------------------------------------


def test_meta_shacl_constructor_and_call() -> None:
    extra = [g(LABEL_RULE)]
    assert not meta_fails(StarShaclProcessor(g(PLAIN_SHAPES)), meta_shapes_extra=extra)  # off by default: the extra is not applied
    with pytest.raises(MetaShaclError):  # meta_shacl bound at construction checks the shapes there
        StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=True, meta_shapes_extra=extra)
    p = StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=True)  # passes; the extras are bound afterwards, as a default of the calls
    p.meta_shapes_extra = tuple(extra)
    assert meta_fails(p)
    assert not meta_fails(p, meta_shacl=False)  # the call beats the constructor
    assert meta_fails(StarShaclProcessor(g(PLAIN_SHAPES), meta_shapes_extra=extra), meta_shacl=True)
    assert not meta_fails(StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=False), meta_shacl=False)


def test_meta_shapes_extra_constructor_and_call() -> None:
    p = StarShaclProcessor(g(PLAIN_SHAPES), meta_shapes_extra=[g(LABEL_RULE)])
    assert meta_fails(p, meta_shacl=True)
    assert not meta_fails(p, meta_shacl=True, meta_shapes_extra=())  # () is a value: it drops the constructor's extras
    assert meta_fails(StarShaclProcessor(g(PLAIN_SHAPES)), meta_shacl=True, meta_shapes_extra=[g(LABEL_RULE)])
    assert not meta_fails(StarShaclProcessor(g(PLAIN_SHAPES)), meta_shacl=True)


def test_meta_shapes_extra_generator_is_read_once() -> None:
    with pytest.raises(MetaShaclError):  # the constructor reads the generator once, and checks with it
        StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=True, meta_shapes_extra=(x for x in [g(LABEL_RULE)]))
    p = StarShaclProcessor(g(PLAIN_SHAPES), meta_shapes_extra=(x for x in [g(LABEL_RULE)]))
    assert meta_fails(p, meta_shacl=True)
    assert meta_fails(p, meta_shacl=True)  # a second call still has the extras


@pytest.mark.parametrize("mode", ["validation", "rules", "debug"])
def test_mode_preset_does_not_reset_meta_shacl(mode: str) -> None:
    p = StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=True)  # passes at construction; the extras are bound afterwards
    p.meta_shapes_extra = (g(LABEL_RULE),)
    assert meta_fails(p, mode=mode)
    assert not meta_fails(p, mode=mode, meta_shacl=False)


def test_presets_name_only_what_they_change() -> None:
    from starlayer.shacl.validation_modes import get_mode

    assert get_mode("validation").options == {}
    assert get_mode("rules").options == {"rules": True, "inplace": True}
    assert get_mode("debug").options == {"debug": True}


def test_meta_shacl_in_apply_rules() -> None:
    p = StarShaclProcessor(g(PLAIN_SHAPES), meta_shacl=True)  # passes at construction; the extras are bound afterwards
    p.meta_shapes_extra = (g(LABEL_RULE),)
    with pytest.raises(MetaShaclError):
        p.apply_rules(g(DATA))
    p.apply_rules(g(DATA), meta_shacl=False)
    p.apply_rules(g(DATA), meta_shapes_extra=())  # () beats the constructor's extras: the check passes
    StarShaclProcessor(g(PLAIN_SHAPES)).apply_rules(g(DATA))


# --- ignore_imports, shapes_graph_loader ------------------------------------------------------------------------------------

IMPORTED = "http://example.org/imported"
IMPORTING = "<http://example.org/importing> owl:imports <http://example.org/imported> . ex:S a sh:NodeShape ; sh:targetClass ex:T ."
IMPORTED_SHAPES = "ex:Strict a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."


def loader(iri):
    return g(IMPORTED_SHAPES) if str(iri.value) == IMPORTED else None


def importing(**kw) -> StarShaclProcessor:
    return StarShaclProcessor(g(IMPORTING), **kw)


def test_unset_imports_behaviour_is_unchanged() -> None:
    with pytest.raises(ValueError, match="owl:imports"):
        importing().validate(g(DATA))
    assert importing().validate(g(DATA), ignore_imports=True).conforms
    assert not importing().validate(g(DATA), shapes_graph_loader=loader).conforms


def test_constructor_ignore_imports() -> None:
    p = importing(ignore_imports=True)
    assert p.validate(g(DATA)).conforms
    with pytest.raises(ValueError, match="owl:imports"):
        p.validate(g(DATA), ignore_imports=False)  # the default-looking value on the call wins
    assert p.apply_rules(g(DATA)).validation.conforms
    with pytest.raises(ValueError, match="owl:imports"):
        p.apply_rules(g(DATA), ignore_imports=False)


def test_constructor_loader() -> None:
    p = importing(shapes_graph_loader=loader)
    assert not p.validate(g(DATA)).conforms  # the imported shape applies
    assert not p.apply_rules(g(DATA)).validation.conforms
    with pytest.raises(ValueError, match="owl:imports"):
        p.validate(g(DATA), shapes_graph_loader=None)  # None on the call drops the constructor's loader
    assert p.validate(g(DATA), shapes_graph_loader=lambda iri: None).conforms  # another loader replaces it
    assert p.validate(g(DATA), ignore_imports=True, shapes_graph_loader=None).conforms


def test_constructor_loader_and_ignore_imports_in_validate_each() -> None:
    results = importing(shapes_graph_loader=loader).validate_each([g(DATA), g(DATA)])
    assert [r.conforms for r in results.values()] == [False, False]
    assert all(r.conforms for r in importing(ignore_imports=True).validate_each([g(DATA)]).values())


# --- max_validation_depth ---------------------------------------------------------------------------------------------------


def chain(n: int) -> StarLayerGraph:
    return g(
        "ex:S0 a sh:NodeShape ; sh:targetNode ex:a ; sh:node ex:S1 .\n"
        + "".join(f"ex:S{i} a sh:NodeShape ; sh:node ex:S{i + 1} .\n" for i in range(1, n))
        + f"ex:S{n} a sh:NodeShape ; sh:nodeKind sh:IRI ."
    )


def test_max_validation_depth_unset_is_the_engine_default() -> None:
    data = g("ex:a ex:p 1 .")
    assert StarShaclProcessor(chain(300)).validate(data).conforms
    with pytest.raises(ShapeError):
        StarShaclProcessor(chain(600)).validate(data)


def test_max_validation_depth_none_at_construction_removes_the_bound() -> None:
    data = g("ex:a ex:p 1 .")
    p = StarShaclProcessor(chain(600), max_validation_depth=None)
    assert p.validate(data).conforms
    with pytest.raises(ShapeError):
        p.validate(data, max_validation_depth=20)  # a call can set a number
    assert p.apply_rules(data).validation.conforms
    with pytest.raises(ShapeError):
        p.apply_rules(data, max_validation_depth=20)


def test_max_validation_depth_number_at_construction_and_call_none() -> None:
    data = g("ex:a ex:p 1 .")
    p = StarShaclProcessor(chain(60), max_validation_depth=20)
    with pytest.raises(ShapeError):
        p.validate(data)
    with pytest.raises(ShapeError):
        p.apply_rules(data)
    assert p.validate(data, max_validation_depth=None).conforms  # None on the call beats the constructor's number
    assert p.validate(data, max_validation_depth=200).conforms
    assert p.apply_rules(data, max_validation_depth=None).validation.conforms


@pytest.mark.parametrize("mode", ["validation", "rules", "debug"])
def test_mode_preset_does_not_reset_max_validation_depth(mode: str) -> None:
    with pytest.raises(ShapeError):
        StarShaclProcessor(chain(60), max_validation_depth=20).validate(g("ex:a ex:p 1 ."), mode=mode)


# --- max_iterations, max_triples (apply_rules only) -------------------------------------------------------------------------


def linear_chain(length: int) -> StarLayerGraph:
    graph = StarLayerGraph()
    for i in range(length):
        graph.add((EX[f"n{i}"], EX.base, EX[f"n{i + 1}"]))
        graph.add((EX[f"n{i}"], EX.reach, EX[f"n{i + 1}"]))
    return graph


def linear_shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reach_linear_sparql.ttl"), format="turtle")
    return shapes


def test_max_iterations_constructor_and_call() -> None:
    data = linear_chain(10)  # one hop per iteration
    assert linear_shapes() is not None
    StarShaclProcessor(linear_shapes()).apply_rules(data)  # built-in 1000
    p = StarShaclProcessor(linear_shapes(), max_iterations=3)
    with pytest.raises(RuleError, match="fixpoint"):
        p.apply_rules(data)
    p.apply_rules(data, max_iterations=50)  # the call beats the constructor
    with pytest.raises(RuleError, match="fixpoint"):
        StarShaclProcessor(linear_shapes()).apply_rules(data, max_iterations=3)


def test_max_triples_constructor_and_call() -> None:
    data = linear_chain(10)
    p = StarShaclProcessor(linear_shapes(), max_triples=5)
    with pytest.raises(RuleError, match="triples inferred"):
        p.apply_rules(data)
    assert len(list(p.apply_rules(data, max_triples=None).inferred_graph)) > 5  # None on the call removes the cap
    p.apply_rules(data, max_triples=1000)
    StarShaclProcessor(linear_shapes()).apply_rules(data)  # unset: no cap
    with pytest.raises(RuleError, match="triples inferred"):
        StarShaclProcessor(linear_shapes(), max_triples=None).apply_rules(data, max_triples=5)


def test_rule_limits_are_not_validate_options() -> None:
    p = StarShaclProcessor(linear_shapes(), max_iterations=3, max_triples=5)
    assert p.validate(linear_chain(2)).conforms  # bound limits do not reach validate(), which has no rules to cap
    with pytest.raises(TypeError):
        p.validate(linear_chain(2), max_iterations=3)


# --- the closed set ---------------------------------------------------------------------------------------------------------


def test_unknown_names_are_still_type_errors() -> None:
    for name in ("meta_shacls", "max_iteration", "ignore_import"):
        with pytest.raises(TypeError):
            StarShaclProcessor(g(PLAIN_SHAPES), **{name: True})  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            StarShaclProcessor(g(PLAIN_SHAPES)).apply_rules(g(DATA), **{name: True})
    with pytest.raises(TypeError):
        StarShaclProcessor(g(PLAIN_SHAPES)).validate(g(DATA), meta_shacls=True)


def test_other_options_are_not_constructor_options() -> None:
    for name in ("rules", "inplace", "abort_on_first", "debug", "mode", "data_graph_iri", "shapes_graph_iri", "include_used_configuration"):
        with pytest.raises(TypeError):
            StarShaclProcessor(g(PLAIN_SHAPES), **{name: True})  # type: ignore[arg-type]


def test_signature_stays_readable() -> None:
    params = inspect.signature(StarShaclProcessor.validate).parameters
    assert repr(params["ignore_imports"].default) == "<not set>"
    assert repr(inspect.signature(StarShaclProcessor).parameters["max_triples"].default) == "<not set>"
