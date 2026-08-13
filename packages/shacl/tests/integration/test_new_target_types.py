import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# Mirrors the SHACL 1.2 Core spec's own examples for the two new target
# types (sh:shape, sh:targetWhere) and implicit class targets/sh:ShapeClass.
#
# These are implemented differently from the constraint components above:
# rather than a native pass merged into the report afterward, the extra
# target nodes are computed natively and injected as ordinary sh:targetNode
# triples before the shapes graph reaches pySHACL - so a shape's *other*
# constraints (not just these target mechanisms) validate correctly through
# the normal pySHACL path too, not just a narrow bolt-on check.


def _violating_focus_nodes(result) -> set:
    return {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}


def test_shape_target_only_targets_nodes_with_explicit_sh_shape_triple() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_shape_target.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Alice a ex:Person ; sh:shape ex:PersonShape .
            ex:Bob a ex:Person .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    # Only Alice was targeted (via sh:shape) - Bob, despite also being an
    # ex:Person, was never a candidate at all since he has no sh:shape triple.
    assert _violating_focus_nodes(result) == {EX.Alice}


def test_shape_target_conforms_when_target_node_has_required_property() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_shape_target.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Alice a ex:Person ; sh:shape ex:PersonShape ; ex:age 30 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_implicit_class_target_validates_shapes_own_instances() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_implicit_class_target.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person .
            ex:NewYork a ex:Place .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert _violating_focus_nodes(result) == {EX.Alice}


def test_shape_class_implicit_target_validates_shapes_own_instances() -> None:
    # Unlike the plain-rdfs:Class case above (which pySHACL already resolves
    # natively via Shape.implicit_class_targets()), sh:ShapeClass is a
    # brand-new SHACL 1.2 predicate pySHACL has no knowledge of at all - so
    # this exercises starShacl's own injected-target-node mechanism
    # specifically, not pySHACL's native behavior.
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_shape_class_implicit_target.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person .
            ex:NewYork a ex:Place .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert _violating_focus_nodes(result) == {EX.Alice}


def test_shape_class_implicit_target_follows_rdfs_subclassof_and_needs_no_separate_nodeshape_typing() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's
    targetClassImplicit-002 fixture: two distinct bugs in one fixture.

    (1) The implicit-class-target loop only considered nodes explicitly
    typed sh:NodeShape - the existing
    shacl12_shape_class_implicit_target.ttl fixture (see
    test_shape_class_implicit_target_validates_shapes_own_instances above)
    happens to declare its class `a sh:ShapeClass, sh:NodeShape` (both),
    masking that sh:ShapeClass alone - the spec's own "shortcut" framing,
    with no separate sh:NodeShape typing at all, exactly like ex:SuperClass
    here - was never picked up.

    (2) Even once picked up, only exact rdf:type matches against the
    class itself were targeted, not instances of rdfs:subClassOf
    descendants - same underlying gap sh:targetClass already handles
    correctly for ordinary (non-implicit) class targets.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:SuperClass a sh:ShapeClass ;
              sh:in ( ex:ValidInstance ) .
            ex:SubClass a rdfs:Class ;
              rdfs:subClassOf ex:SuperClass .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:ValidInstance a ex:SubClass .
            ex:InvalidInstance a ex:SubClass .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert _violating_focus_nodes(result) == {EX.InvalidInstance}


def test_select_based_target_node_targets_query_results() -> None:
    """sh:targetNode [ sh:select "..." ] (SHACL 1.2 Core): a SPARQL-computed
    target node set given directly as sh:targetNode's own value - a blank
    node carrying sh:select, distinct from sh:targetWhere (whose value is a
    whole shape, matched via conformance) and from pySHACL's own existing
    sh:target [ sh:select ... ] (a different predicate, SHACL-AF's
    SPARQLTarget, already natively supported). Found missing entirely via
    the W3C SHACL 1.2 test suite's targetNode-select-001 fixture.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:ChildShape a sh:NodeShape ;
              sh:targetNode [
                sh:select \"\"\"
                    PREFIX ex: <http://example.org/>
                    SELECT ?person WHERE { ?person a ex:Person ; ex:age ?age . FILTER (?age < 18) . }
                \"\"\"
              ] ;
              sh:property [ sh:path ex:driversLicense ; sh:maxCount 0 ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Minor a ex:Person ; ex:age 16 ; ex:driversLicense "123" .
            ex:Adult a ex:Person ; ex:age 40 ; ex:driversLicense "456" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    # ex:Adult is never a candidate at all (the SELECT excludes her); only
    # ex:Minor is targeted, and violates the outer shape's own
    # sh:driversLicense maxCount.
    assert _violating_focus_nodes(result) == {EX.Minor}


def test_target_where_only_targets_conforming_nodes() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_target_where.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person .
            ex:Bob a ex:Person ; ex:age 21 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    # Alice never becomes a candidate at all (she doesn't conform to the
    # targetWhere filter shape - no ex:age). Only Bob is targeted, and Bob
    # violates the outer shape's own sh:votedFor requirement.
    assert _violating_focus_nodes(result) == {EX.Bob}


def test_target_where_candidate_not_excluded_by_unrelated_focus_node_data() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's targetWhere-001
    fixture: _nodes_conforming_to's "did this candidate violate where_shape"
    check scanned for *any* sh:focusNode triple anywhere in the nested
    validate() call's report graph - not just genuine top-level results.
    A data graph can legitimately contain its own sh:focusNode triples as
    ordinary content unrelated to the where_shape check itself (here,
    ex:Carol's own ex:priorReport blank-node value happens to describe some
    other report, coincidentally naming ex:Carol as its own sh:focusNode) -
    pySHACL's report-graph construction can copy that pre-existing triple
    into the nested report as part of representing some unrelated violation
    value, and the old blanket scan wrongly treated that as proof ex:Carol
    itself violated where_shape, excluding a genuinely-conforming candidate
    from the target set entirely (a false negative, the opposite of
    test_target_where_only_targets_conforming_nodes's already-covered false
    positive direction).
    """
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_target_where.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ; ex:age 21 ; ex:votedFor ex:Alice .
            ex:Alice a ex:Person .
            ex:Carol a ex:Person ; ex:age 25 ;
              ex:priorReport [
                a <http://www.w3.org/ns/shacl#ValidationReport> ;
                <http://www.w3.org/ns/shacl#conforms> false ;
                <http://www.w3.org/ns/shacl#result> [
                  a <http://www.w3.org/ns/shacl#ValidationResult> ;
                  <http://www.w3.org/ns/shacl#focusNode> ex:Carol ;
                ]
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    # ex:Carol (Person, age 25) genuinely conforms to where_shape and must
    # become a target of the outer shape - which she then violates (no
    # ex:votedFor), same as ex:Bob would if he had none.
    assert EX.Carol in _violating_focus_nodes(result)


def test_target_where_conforms_when_targeted_node_satisfies_outer_shape() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_target_where.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person .
            ex:Bob a ex:Person ; ex:age 21 ; ex:votedFor ex:Alice .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
