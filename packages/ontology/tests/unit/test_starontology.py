"""tests/unit/test_starontology.py

starontology is pure data (eight .ttl files, plus the generated shacl_meta
entry) behind a thin registry (get_ontology_list()/get_ontology_graph()/
get_ontology_turtle12()) - this suite confirms every registered entry
loads and parses, and the registry's own list/lookup/serialize behavior is
correct. The underlying *_TTL_PATH constants are private as of 2026-10-02
(internal to this module's own registry, not public API) - there's no
dedicated "does the file exist" test anymore, since
TestGetOntologyGraph::test_every_registered_name_loads_and_parses already
proves it implicitly (a missing file would fail to parse). Not that any
vocabulary's own content is correct - that's each consuming package's own
test suite's job (packages/starlayer/tests/graph/unit/test_manchester_ast_shapes.py,
test_skos_shapes.py; packages/starlayer/tests/sparql/unit/test_shacl_shapes.py,
test_srl_shapes.py).
"""

import pytest
import starontology
from starlayer.graph import StarLayerGraph


class TestGetOntologyList:
    def test_returns_all_nine_entries(self):
        names = {info.name for info in starontology.get_ontology_list()}
        assert names == {
            "manchester_owl", "manchester_shacl",
            "skos_owl", "skos_shacl",
            "sparql_owl", "sparql_shacl",
            "srl_owl", "srl_shacl",
            "shacl_meta",
        }

    def test_sorted_by_name(self):
        names = [info.name for info in starontology.get_ontology_list()]
        assert names == sorted(names)

    def test_every_entry_has_name_description_and_type(self):
        for info in starontology.get_ontology_list():
            assert info.name
            assert info.description
            assert info.type in ("shacl", "ast-graph", "owl")

    def test_shapes_entries_are_type_shacl(self):
        """shacl_meta is generated, not file-backed, but it's still a SHACL
        shapes graph - same type as the four file-backed shapes entries."""
        shacl_names = {info.name for info in starontology.get_ontology_list() if info.type == "shacl"}
        assert shacl_names == {"manchester_shacl", "skos_shacl", "sparql_shacl", "srl_shacl", "shacl_meta"}

    def test_skos_owl_is_type_owl_not_ast_graph(self):
        """skos: is a real semantic ontology (formal axioms about an existing
        vocabulary), not a syntax tree represented as RDF like the other
        three - so it gets "owl", not "ast-graph"."""
        [skos_entry] = [info for info in starontology.get_ontology_list() if info.name == "skos_owl"]
        assert skos_entry.type == "owl"

    def test_manchester_sparql_srl_owl_entries_are_type_ast_graph(self):
        ast_graph_names = {info.name for info in starontology.get_ontology_list() if info.type == "ast-graph"}
        assert ast_graph_names == {"manchester_owl", "sparql_owl", "srl_owl"}


class TestGetOntologyGraph:
    @pytest.mark.parametrize("name", [
        "manchester_owl", "manchester_shacl",
        "skos_owl", "skos_shacl",
        "sparql_owl", "sparql_shacl",
        "srl_owl", "srl_shacl",
        "shacl_meta",
    ])
    def test_every_registered_name_loads_and_parses(self, name):
        g = starontology.get_ontology_graph(name)
        assert isinstance(g, StarLayerGraph)
        assert len(g) > 0

    def test_unknown_name_raises_keyerror_naming_choices(self):
        with pytest.raises(KeyError, match="manchester_owl"):
            starontology.get_ontology_graph("not_a_real_name")

    def test_returns_a_fresh_graph_each_call(self):
        g1 = starontology.get_ontology_graph("manchester_owl")
        g2 = starontology.get_ontology_graph("manchester_owl")
        assert g1 is not g2

    def test_shacl_meta_is_wrapped_as_starlayergraph_not_left_plain(self):
        """build_meta_shapes_graph() (starlayer.shacl) returns a plain
        rdflib.Graph - confirmed in its own source - so this entry
        specifically needs StarLayerGraph.from_rdflib() wrapping to keep
        the same return type as every other entry. isinstance alone would
        pass on a plain Graph too (StarLayerGraph is not involved there),
        so check the exact type instead."""
        g = starontology.get_ontology_graph("shacl_meta")
        assert type(g) is StarLayerGraph


class TestGetOntologyTurtle12:
    def test_returns_turtle_text_round_trippable(self):
        text = starontology.get_ontology_turtle12("skos_shacl")
        assert isinstance(text, str)
        g = StarLayerGraph()
        g.parse(data=text, format="turtle12")
        assert len(g) == len(starontology.get_ontology_graph("skos_shacl"))

    def test_unknown_name_raises_keyerror(self):
        with pytest.raises(KeyError):
            starontology.get_ontology_turtle12("not_a_real_name")
