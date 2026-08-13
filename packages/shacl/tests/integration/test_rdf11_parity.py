import pytest
from rdflib import BNode, Graph, Literal, Namespace
from rdflib.namespace import RDF

from starshacl import StarShaclValidator

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")


pyshacl = pytest.importorskip("pyshacl")


def _normalized_validation_results(
    report_graph: Graph,
) -> tuple[tuple[str | None, str | None, str | None, str | None], ...]:
    # NOTE: this previously matched (None, SH.type, SH.ValidationResult) -
    # sh:type, not rdf:type - which no real triple ever uses, so this always
    # returned an empty tuple and every parity assertion below was
    # vacuously true regardless of actual report content. Fixed to RDF.type;
    # re-running with the real comparison enabled surfaced nothing - every
    # existing case turned out to already match once actually compared.
    # Also broadened to include sh:value, which the original version omitted
    # entirely regardless of the RDF.type bug.
    #
    # str()-based comparison relies on blank-node *identity* (not just
    # structural equivalence) matching between the two independently-run
    # validate() calls below - confirmed this holds via direct
    # investigation: starShacl's TripleTermAdapter passes plain (non-triple-
    # term) blank nodes through completely unchanged (no re-blanking) for
    # both focus nodes and complex-path structures, so the same Python BNode
    # objects (same internal ID) flow through both sides. See
    # test_rdf11_report_parity_with_blank_node_focus_and_complex_path below.
    rows: list[tuple[str | None, str | None, str | None, str | None]] = []

    for result_node, _, _ in report_graph.triples((None, RDF.type, SH.ValidationResult)):
        focus = next((str(o) for _, _, o in report_graph.triples((result_node, SH.focusNode, None))), None)
        path = next((str(o) for _, _, o in report_graph.triples((result_node, SH.resultPath, None))), None)
        component = next(
            (str(o) for _, _, o in report_graph.triples((result_node, SH.sourceConstraintComponent, None))),
            None,
        )
        value = next((str(o) for _, _, o in report_graph.triples((result_node, SH.value, None))), None)
        rows.append((focus, path, component, value))

    return tuple(sorted(rows, key=lambda row: tuple(x or "" for x in row)))


def test_rdf11_conforms_parity_for_passing_case() -> None:
    data = Graph()
    data.add((EX.alice, EX.age, Literal(30)))

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_age_datatype.ttl"), format="turtle")

    py_conforms, _, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms


def test_rdf11_report_field_parity_for_failing_case() -> None:
    data = Graph()
    data.add((EX.alice, EX.age, Literal("thirty")))

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_age_datatype.ttl"), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


@pytest.mark.parametrize(
    "shape_file,data_ttl",
    [
        (
            "rdf11_mincount_knows.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:bob .
            """,
        ),
        (
            "rdf11_in_color.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:color ex:blue .
            """,
        ),
        (
            "rdf11_equals_names.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:firstName "Alice" ;
                    ex:nickname "Al" .
            """,
        ),
        (
            "rdf11_disjoint_names.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:firstName "Alice" ;
                    ex:nickname "Alice" .
            """,
        ),
    ],
)
def test_rdf11_parity_matrix_for_core_components(shape_file: str, data_ttl: str) -> None:
    data = Graph()
    data.parse(data=data_ttl, format="turtle")

    shapes = Graph()
    shapes.parse(data=load_shape(shape_file), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_target_class_parity() -> None:
    data = Graph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice a ex:Person ; ex:age "thirty" .
        """,
        format="turtle",
    )

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_target_class_age.ttl"), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_target_subjects_of_parity() -> None:
    data = Graph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:flag ex:on ; ex:age "thirty" .
        """,
        format="turtle",
    )

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_target_subjects_flag_age.ttl"), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_target_objects_of_parity() -> None:
    data = Graph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:source ex:about ex:alice .
            ex:alice ex:age "thirty" .
        """,
        format="turtle",
    )

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_target_objects_about_age.ttl"), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_max_count_parity() -> None:
    data = Graph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:tag ex:t1, ex:t2 .
        """,
        format="turtle",
    )

    shapes = Graph()
    shapes.parse(data=load_shape("rdf11_maxcount_tag.ttl"), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


@pytest.mark.parametrize(
    "shape_file,data_ttl",
    [
        (
            "rdf11_logical_or.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:age "thirty" .
            """,
        ),
        (
            "rdf11_logical_not.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:status ex:inactive .
            """,
        ),
        (
            "rdf11_logical_xone.ttl",
            """
            @prefix ex: <http://example.org/> .
            ex:alice ex:p ex:v1, ex:v2 .
            """,
        ),
    ],
)
def test_rdf11_logical_constraints_parity(shape_file: str, data_ttl: str) -> None:
    data = Graph()
    data.parse(data=data_ttl, format="turtle")

    shapes = Graph()
    shapes.parse(data=load_shape(shape_file), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


@pytest.mark.parametrize(
    "shape_file",
    [
        "rdf11_literal_only_pattern.ttl",
        "rdf11_literal_only_datatype.ttl",
        "rdf11_literal_only_language_in.ttl",
        "rdf11_literal_only_min_length.ttl",
        "rdf11_literal_only_max_length.ttl",
    ],
)
def test_rdf11_literal_only_component_parity_on_non_literal_values(shape_file: str) -> None:
    data = Graph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value ex:notLiteral .
        """,
        format="turtle",
    )

    shapes = Graph()
    shapes.parse(data=load_shape(shape_file), format="turtle")

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_report_parity_with_blank_node_focus_node() -> None:
    # The "ordering normalization for report-level parity" gap previously
    # flagged as open turned out, on investigation, to already work
    # correctly: starShacl's TripleTermAdapter passes plain (non-triple-term)
    # blank nodes through completely unchanged, so a blank-node focus node
    # keeps the exact same identity (not just structural equivalence)
    # between starShacl's report and pySHACL's own - confirmed here with a
    # blank-node-valued sh:targetClass instance.
    data = Graph()
    addr = BNode()
    data.add((EX.alice, EX.address, addr))
    data.add((addr, RDF.type, EX.PostalAddress))

    shapes = Graph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:AddrShape a sh:NodeShape ; sh:targetClass ex:PostalAddress ;
              sh:property [ sh:path ex:city ; sh:minCount 1 ] .
        """,
        format="turtle",
    )

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms is False
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)


def test_rdf11_report_parity_with_complex_blank_node_path() -> None:
    # Same finding as above, for a complex (blank-node-structured) SHACL
    # property path used as sh:resultPath (sh:inversePath) - the path
    # blank node comes from the shapes graph itself and is never re-minted,
    # so it also matches by identity between the two sides.
    data = Graph()
    data.parse(data="@prefix ex: <http://example.org/> .\nex:alice ex:parentOf ex:bob .", format="turtle")

    shapes = Graph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
              sh:property [ sh:path [ sh:inversePath ex:parentOf ] ; sh:minCount 5 ] .
        """,
        format="turtle",
    )

    py_conforms, py_report, _ = pyshacl.validate(data_graph=data, shacl_graph=shapes)
    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert result.conforms is py_conforms is False
    assert _normalized_validation_results(result.report_graph) == _normalized_validation_results(py_report)
