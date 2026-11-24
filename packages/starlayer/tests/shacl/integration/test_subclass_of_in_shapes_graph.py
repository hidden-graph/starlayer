"""SHACL 1.2 Core, "Graph for rdfs:subClassOf Triples": the ``subclass_of_in_shapes_graph`` option. When true, ``rdfs:subClassOf``
triples for ``sh:class``, ``sh:targetClass``, implicit class targets and ``sh:rootClass`` come from the data graph and the shapes
graph; ``rdf:type`` triples only from the data graph. Default off: the data graph alone."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph.entailment import ENTAILMENT
from starlayer.shacl import StarShaclProcessor, apply_rules, target_nodes, validate
from tests.support.terms import Namespace

EX = Namespace("http://example.org/")
PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)
SUBCLASS = "ex:Dog rdfs:subClassOf ex:Animal ."
TYPE = "ex:rex a ex:Dog ."


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


# (feature, shapes without the subClassOf triple, data without the instance triples). Each feature violates its shape exactly when
# ex:Dog counts as a subclass of ex:Animal.
_NAME_RULE = "sh:property [ sh:path ex:name ; sh:minCount 1 ]"
CASES = {
    "sh:class": (
        "ex:S a sh:NodeShape ; sh:targetNode ex:owner ; sh:property [ sh:path ex:pet ; sh:class ex:Animal ] .",
        "ex:owner ex:pet ex:rex .",
        True,  # the shape conforms when the subclass triple is visible
    ),
    "sh:targetClass": (
        f"ex:S a sh:NodeShape ; sh:targetClass ex:Animal ; {_NAME_RULE} .",
        "",
        False,  # rex is targeted (and has no name) when the subclass triple is visible
    ),
    "implicit class target": (
        f"ex:Animal a sh:NodeShape , rdfs:Class ; {_NAME_RULE} .",
        "",
        False,
    ),
    "sh:rootClass": (
        "ex:S a sh:NodeShape ; sh:targetNode ex:zoo ; sh:property [ sh:path ex:kind ; sh:rootClass ex:Animal ] .",
        "ex:zoo ex:kind ex:Dog .",
        True,
    ),
}
FEATURES = list(CASES)


def build(feature: str, *, subclass_in: str = "shapes", extra_shapes: str = "", extra_data: str = ""):
    """The shapes and data graphs of ``feature``; ``subclass_in`` is where ``ex:Dog rdfs:subClassOf ex:Animal`` is asserted."""
    shapes_ttl, data_ttl, _ = CASES[feature]
    shapes = shapes_ttl + extra_shapes + (SUBCLASS if subclass_in in ("shapes", "both") else "")
    data = TYPE + data_ttl + extra_data + (SUBCLASS if subclass_in in ("data", "both") else "")
    return g(shapes), g(data)


def conforms_when_subclass_visible(feature: str) -> bool:
    return CASES[feature][2]


def snapshot(graph: StarLayerGraph) -> frozenset:
    return frozenset(graph.triples((None, None, None)))


@pytest.mark.parametrize("feature", FEATURES)
def test_default_ignores_shapes_graph_subclass_triples(feature: str) -> None:
    shapes, data = build(feature)
    # sh:class and sh:rootClass fail without the triple; the targets find nothing and so conform
    assert validate(data, shapes).conforms is (not conforms_when_subclass_visible(feature))
    assert validate(data, shapes, subclass_of_in_shapes_graph=False).conforms is (not conforms_when_subclass_visible(feature))


@pytest.mark.parametrize("feature", FEATURES)
def test_option_reads_subclass_of_from_the_shapes_graph(feature: str) -> None:
    shapes, data = build(feature)
    assert validate(data, shapes, subclass_of_in_shapes_graph=True).conforms is conforms_when_subclass_visible(feature)


@pytest.mark.parametrize("feature", FEATURES)
def test_module_validate_and_processor_agree(feature: str) -> None:
    shapes, data = build(feature)
    expected = conforms_when_subclass_visible(feature)
    assert StarShaclProcessor(shapes).validate(data, subclass_of_in_shapes_graph=True).conforms is expected
    assert StarShaclProcessor(shapes, subclass_of_in_shapes_graph=True).validate(data).conforms is expected


@pytest.mark.parametrize("feature", FEATURES)
def test_call_keyword_beats_constructor_value_both_ways(feature: str) -> None:
    shapes, data = build(feature)
    visible = conforms_when_subclass_visible(feature)
    on = StarShaclProcessor(shapes, subclass_of_in_shapes_graph=True)
    off = StarShaclProcessor(shapes, subclass_of_in_shapes_graph=False)
    assert on.validate(data).conforms is visible
    assert on.validate(data, subclass_of_in_shapes_graph=False).conforms is not visible
    assert off.validate(data).conforms is not visible
    assert off.validate(data, subclass_of_in_shapes_graph=True).conforms is visible


def test_constructor_none_is_not_set() -> None:
    shapes, data = build("sh:class")
    assert StarShaclProcessor(shapes, subclass_of_in_shapes_graph=None).validate(data).conforms is False


@pytest.mark.parametrize("feature", FEATURES)
def test_rdf_type_triples_in_the_shapes_graph_are_not_used(feature: str) -> None:
    # the instance triple is in the shapes graph only, the subclass triple in both: with no rdf:type in the data there is no instance
    shapes_ttl, data_ttl, _ = CASES[feature]
    shapes = g(shapes_ttl + TYPE + SUBCLASS)
    data = g(data_ttl + SUBCLASS)
    result = validate(data, shapes, subclass_of_in_shapes_graph=True)
    if feature in ("sh:targetClass", "implicit class target"):
        assert result.conforms is True  # no instance in the data graph: nothing is targeted
    elif feature == "sh:class":
        assert result.conforms is False  # ex:rex is not an Animal as far as the data graph says
    else:
        assert result.conforms is True  # sh:rootClass reads no rdf:type: the shapes graph's rdf:type does not matter


def test_rdf_type_in_shapes_graph_only_does_not_make_an_instance() -> None:
    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:owner ; sh:property [ sh:path ex:pet ; sh:class ex:Animal ] . ex:rex a ex:Dog . " + SUBCLASS)
    data = g("ex:owner ex:pet ex:rex .")
    assert validate(data, shapes, subclass_of_in_shapes_graph=True).conforms is False


@pytest.mark.parametrize("feature", FEATURES)
def test_callers_graphs_are_unchanged(feature: str) -> None:
    shapes, data = build(feature)
    before = snapshot(shapes), snapshot(data)
    validate(data, shapes, subclass_of_in_shapes_graph=True)
    validate(data, shapes, subclass_of_in_shapes_graph=True, inference=ENTAILMENT.RDFS)
    assert (snapshot(shapes), snapshot(data)) == before


@pytest.mark.parametrize("feature", FEATURES)
@pytest.mark.parametrize("where", ["data", "both"])
def test_subclass_triple_in_the_data_graph_gives_the_same_result_either_way(feature: str, where: str) -> None:
    shapes, data = build(feature, subclass_in=where)
    visible = conforms_when_subclass_visible(feature)
    assert validate(data, shapes).conforms is visible
    assert validate(data, shapes, subclass_of_in_shapes_graph=True).conforms is visible


@pytest.mark.parametrize("feature", FEATURES)
def test_with_rdfs_entailment(feature: str) -> None:
    shapes, data = build(feature)
    visible = conforms_when_subclass_visible(feature)
    assert validate(data, shapes, inference=ENTAILMENT.RDFS).conforms is not visible  # entailment reads the data graph only
    assert validate(data, shapes, inference=ENTAILMENT.RDFS, subclass_of_in_shapes_graph=True).conforms is visible


def test_with_rdfs_entailment_and_the_subclass_triple_in_both_graphs() -> None:
    shapes, data = build("sh:class", subclass_in="both")
    assert validate(data, shapes, inference=ENTAILMENT.RDFS, subclass_of_in_shapes_graph=True).conforms is True
    assert validate(data, shapes, inference=ENTAILMENT.RDFS).conforms is True


def test_a_chain_split_between_the_graphs() -> None:
    # Puppy < Dog in the data graph, Dog < Animal in the shapes graph
    shapes = g(
        "ex:S a sh:NodeShape ; sh:targetNode ex:owner ; sh:property [ sh:path ex:pet ; sh:class ex:Animal ] . " + SUBCLASS
    )
    data = g("ex:owner ex:pet ex:rex . ex:rex a ex:Puppy . ex:Puppy rdfs:subClassOf ex:Dog .")
    assert validate(data, shapes).conforms is False
    assert validate(data, shapes, subclass_of_in_shapes_graph=True).conforms is True


def test_with_an_ontology_graph_that_has_the_subclass_triple() -> None:
    shapes, data = build("sh:class", subclass_in="data")
    ont = g(SUBCLASS)
    shapes_only, data_only = build("sh:class")
    p = StarShaclProcessor(shapes_only, ont_graph=ont, inference=ENTAILMENT.RDFS)
    assert p.validate(data_only).conforms is True  # the ontology graph already contributes (to entailment)
    assert p.validate(data_only, subclass_of_in_shapes_graph=True).conforms is True  # nothing breaks, nothing is counted twice
    p2 = StarShaclProcessor(shapes_only, ont_graph=g("ex:Cat rdfs:subClassOf ex:Animal ."))
    assert p2.validate(data_only, subclass_of_in_shapes_graph=True).conforms is True
    assert shapes is not None and data is not None


def test_target_nodes() -> None:
    shapes, data = build("sh:targetClass")
    kwargs = dict(data_graph=data, shacl_graph=shapes, shape_node=EX.S)
    assert target_nodes(**kwargs) == ()
    assert target_nodes(**kwargs, subclass_of_in_shapes_graph=True) == (EX.rex,)
    p = StarShaclProcessor(shapes, data_graph=data)
    assert p.target_nodes(shape_node=EX.S) == ()
    assert p.target_nodes(shape_node=EX.S, subclass_of_in_shapes_graph=True) == (EX.rex,)
    on = StarShaclProcessor(shapes, data_graph=data, subclass_of_in_shapes_graph=True)
    assert on.target_nodes(shape_node=EX.S) == (EX.rex,)  # the constructor value is the default
    assert on.target_nodes(shape_node=EX.S, subclass_of_in_shapes_graph=False) == ()


def test_implicit_class_target_nodes() -> None:
    shapes, data = build("implicit class target")
    assert target_nodes(data_graph=data, shacl_graph=shapes, shape_node=EX.Animal) == ()
    assert target_nodes(data_graph=data, shacl_graph=shapes, shape_node=EX.Animal, subclass_of_in_shapes_graph=True) == (EX.rex,)


RULE_SHAPES = (
    "ex:R a sh:NodeShape ; sh:targetClass ex:Animal ; sh:rule [ a sh:TripleRule ; sh:subject sh:this ; "
    "sh:predicate ex:seen ; sh:object ex:yes ] . "
)


def test_apply_rules_honours_the_option_for_class_targets() -> None:
    shapes, data = g(RULE_SHAPES + SUBCLASS), g(TYPE)
    assert len(apply_rules(data, shapes).inferred_graph) == 0
    assert len(apply_rules(data, shapes, subclass_of_in_shapes_graph=True).inferred_graph) == 1
    p = StarShaclProcessor(shapes, subclass_of_in_shapes_graph=True)
    assert len(p.apply_rules(data).inferred_graph) == 1
    assert len(p.apply_rules(data, subclass_of_in_shapes_graph=False).inferred_graph) == 0


def test_validate_with_rules_uses_the_option_after_the_rules() -> None:
    shapes = g(RULE_SHAPES + "ex:S a sh:NodeShape ; sh:targetNode ex:owner ; sh:property [ sh:path ex:pet ; sh:class ex:Animal ] . " + SUBCLASS)
    data = g(TYPE + "ex:owner ex:pet ex:rex .")
    assert validate(data, shapes, rules=True).conforms is False
    assert validate(data, shapes, rules=True, subclass_of_in_shapes_graph=True).conforms is True


def test_unknown_options_are_still_rejected() -> None:
    shapes, data = build("sh:class")
    with pytest.raises(TypeError, match="subclass_of_in_shapes_graph"):  # the message lists the known options
        validate(data, shapes, subclass_of_in_shapes_graf=True)
    with pytest.raises(TypeError, match="unknown option"):
        StarShaclProcessor(shapes).validate(data, rdfs_subclass_reasoning_includes_shapes_graph=True)
    with pytest.raises(TypeError, match="unknown option"):
        apply_rules(data, shapes, nonsense=True)
