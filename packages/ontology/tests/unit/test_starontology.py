"""tests/unit/test_starontology.py

starontology is pure data (eight .ttl files) plus thin loaders - this suite
just confirms every file parses as valid Turtle and every path constant
points at a real file, not that any vocabulary's own content is correct
(that's each consuming package's own test suite's job:
packages/graph/tests/unit/test_manchester_ast_shapes.py,
test_skos_shapes.py; packages/sparql/tests/unit/test_shacl_shapes.py,
test_srl_shapes.py).
"""

import starontology


class TestPathsExist:
    def test_manchester_ontology_path_exists(self):
        assert starontology.MANCHESTER_ONTOLOGY_TTL_PATH.is_file()

    def test_manchester_shapes_path_exists(self):
        assert starontology.MANCHESTER_SHAPES_TTL_PATH.is_file()

    def test_skos_ontology_path_exists(self):
        assert starontology.SKOS_ONTOLOGY_TTL_PATH.is_file()

    def test_skos_shapes_path_exists(self):
        assert starontology.SKOS_SHAPES_TTL_PATH.is_file()

    def test_sparql_ontology_path_exists(self):
        assert starontology.SPARQL_ONTOLOGY_TTL_PATH.is_file()

    def test_sparql_shapes_path_exists(self):
        assert starontology.SPARQL_SHAPES_TTL_PATH.is_file()

    def test_srl_ontology_path_exists(self):
        assert starontology.SRL_ONTOLOGY_TTL_PATH.is_file()

    def test_srl_shapes_path_exists(self):
        assert starontology.SRL_SHAPES_TTL_PATH.is_file()


class TestLoadersParse:
    def test_manchester_ontology_graph_parses(self):
        g = starontology.manchester_ontology_graph()
        assert len(g) > 0

    def test_manchester_shapes_graph_parses(self):
        g = starontology.manchester_shapes_graph()
        assert len(g) > 0

    def test_skos_ontology_graph_parses(self):
        g = starontology.skos_ontology_graph()
        assert len(g) > 0

    def test_skos_shapes_graph_parses(self):
        g = starontology.skos_shapes_graph()
        assert len(g) > 0

    def test_sparql_ontology_graph_parses(self):
        g = starontology.sparql_ontology_graph()
        assert len(g) > 0

    def test_sparql_shapes_graph_parses(self):
        g = starontology.sparql_shapes_graph()
        assert len(g) > 0

    def test_srl_ontology_graph_parses(self):
        g = starontology.srl_ontology_graph()
        assert len(g) > 0

    def test_srl_shapes_graph_parses(self):
        g = starontology.srl_shapes_graph()
        assert len(g) > 0

    def test_loaders_return_fresh_graphs_each_call(self):
        g1 = starontology.manchester_ontology_graph()
        g2 = starontology.manchester_ontology_graph()
        assert g1 is not g2
