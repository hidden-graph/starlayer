import pytest
from rdflib import Dataset, Literal, Namespace
from starshacl import StarShaclValidator

pytest.importorskip("pyshacl")
StarLayerDataset = pytest.importorskip(
    "starlayergraph.graph.starlayer_dataset"
).StarLayerDataset


EX = Namespace("http://example.org/")

_PERSON_SHAPE = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    ex:PersonShape a sh:NodeShape ;
      sh:targetClass ex:Person ;
      sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:datatype xsd:integer ] .
"""

_PERSON_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ; ex:age 30 .
    ex:bob a ex:Person .
"""


def _dataset_with_named_graph(data: str) -> "StarLayerDataset":
    ds = StarLayerDataset()
    ds.get_context(EX.g1).parse(data=data, format="turtle")
    return ds


class TestStarLayerDatasetDefaultUnion:
    def test_default_union_false_ignores_named_graph_content(self) -> None:
        # default_union=False is StarLayerDataset's default. Data placed in a
        # named context is invisible to validation unless the caller opts in
        # via default_union=True - the default graph is empty here, so no
        # ex:Person nodes are ever targeted and the result trivially conforms,
        # even though ex:bob (missing ex:age) would fail if the data were seen.
        data = _dataset_with_named_graph(_PERSON_DATA)
        shapes = _dataset_with_named_graph(_PERSON_SHAPE)

        result = StarShaclValidator().validate(
            data_graph=data, shacl_graph=shapes, meta_shacl=False
        )

        assert result.conforms is True

    def test_default_union_true_sees_named_graph_content(self) -> None:
        data = StarLayerDataset(default_union=True)
        data.get_context(EX.g1).parse(data=_PERSON_DATA, format="turtle")

        shapes = StarLayerDataset(default_union=True)
        shapes.get_context(EX.g1).parse(data=_PERSON_SHAPE, format="turtle")

        result = StarShaclValidator().validate(
            data_graph=data, shacl_graph=shapes, meta_shacl=False
        )

        assert result.conforms is False
        assert "ex:bob" in result.report_text

    def test_data_in_default_graph_validates_without_default_union(self) -> None:
        data = StarLayerDataset()
        data.default_graph.add((EX.alice, EX.age, Literal(30)))
        data.default_graph.add((EX.alice, EX.age, Literal(31)))  # extra unrelated triple

        shapes = StarLayerDataset()
        shapes.get_context(EX.shapes).parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:AgeShape a sh:NodeShape ;
                  sh:targetSubjectsOf ex:age ;
                  sh:property [ sh:path ex:age ; sh:minCount 1 ] .
            """,
            format="turtle",
        )

        result = StarShaclValidator().validate(
            data_graph=data, shacl_graph=shapes, meta_shacl=False
        )

        assert result.conforms is True


class TestOntGraphDatasetAutoUnion:
    """pySHACL's own native handling of a raw ``rdflib.Dataset`` passed as
    ``ont_graph`` forces ``default_union = True`` on it before use
    (``pyshacl/validator.py``), regardless of how the caller constructed it -
    unlike ``data_graph``/``shacl_graph``, which respect whatever
    ``default_union`` the caller set. starShacl's own normalization
    (``starshacl/engine/normalization.py``) mirrors this exactly, so an
    ``ont_graph`` Dataset's named-graph content is never silently invisible
    to inference just because the caller didn't explicitly opt into
    ``default_union=True``.
    """

    def test_ont_graph_named_graph_content_visible_without_explicit_default_union(self) -> None:
        ont = Dataset()  # default_union left at its rdflib default (False)
        ont.get_context(EX.ctx1).parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:Dog rdfs:subClassOf ex:Animal .
            """,
            format="turtle",
        )

        data = Dataset()
        data.default_graph.parse(
            data="@prefix ex: <http://example.org/> .\nex:rex a ex:Dog .",
            format="turtle",
        )

        shapes = Dataset()
        shapes.default_graph.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:AnimalShape a sh:NodeShape ;
                  sh:targetClass ex:Animal ;
                  sh:property [ sh:path ex:name ; sh:minCount 1 ] .
            """,
            format="turtle",
        )

        result = StarShaclValidator().validate(
            data_graph=data,
            shacl_graph=shapes,
            ont_graph=ont,
            inference="rdfs",
            meta_shacl=False,
        )

        # ex:rex only conforms to ex:Dog explicitly - it's only a target of
        # AnimalShape (targetClass ex:Animal) at all if rdfs:subClassOf
        # inference saw the ont_graph's subclass triple, which lives only in
        # a named context. If the ont_graph Dataset's default_union hadn't
        # been auto-forced, that triple would be invisible and this would
        # trivially conform (ex:rex never targeted).
        assert result.conforms is False
        assert "ex:rex" in result.report_text


class TestPlainRdflibDatasetInput:
    def test_plain_dataset_default_graph_normalizes_and_validates(self) -> None:
        # A plain rdflib.Dataset (not StarLayerDataset) is also a Graph
        # subclass and goes through the same normalize_to_starlayer_graph()
        # path - confirms starShacl doesn't require StarLayerDataset
        # specifically, just something Dataset-shaped with the right
        # default_union semantics.
        data = Dataset()
        data.default_graph.add((EX.bob, EX.age, Literal(30)))

        shapes = Dataset()
        shapes.default_graph.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:AgeShape a sh:NodeShape ;
                  sh:targetSubjectsOf ex:age ;
                  sh:property [ sh:path ex:age ; sh:minCount 1 ] .
            """,
            format="turtle",
        )

        result = StarShaclValidator().validate(
            data_graph=data, shacl_graph=shapes, meta_shacl=False
        )

        assert result.conforms is True
