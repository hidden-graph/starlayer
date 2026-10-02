"""
jsonld12 was removed as a recognized format (2026-10-02), not restricted to
plain RDF 1.1 content - it previously delegated straight to rdflib's own
JSON-LD writer for ordinary content and raised ValueError for a triple term
or direction-tagged literal (matching Fuseki/Oxigraph's own refusal
behavior - see packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md
§6 for that design's own history). The concern that motivated full removal:
JSON-LD has no published RDF 1.2 companion spec at all - even the
"plain content only" compromise meant this project was the one deciding
what a name containing "12" promises, with nothing authoritative to
converge on. Removed outright rather than kept as a partial format, so
'jsonld12' is now just an unrecognized format string like any other typo -
this suite confirms that rejection is real and consistent, not a different
silent failure mode.
"""

import pytest
from rdflib import URIRef
from rdflib.plugin import PluginException
from starlayer import StarLayerDataset, StarLayerGraph

EX = 'http://example.org/'


def ex(local):
    return URIRef(EX + local)


class TestJsonld12IsRejectedAsUnrecognized:
    def test_graph_serialize_rejects(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        with pytest.raises(PluginException):
            g.serialize(format='jsonld12')

    def test_graph_parse_rejects(self):
        g = StarLayerGraph()
        with pytest.raises(PluginException):
            g.parse(data='{}', format='jsonld12')

    def test_dataset_serialize_rejects(self):
        ds = StarLayerDataset()
        ds.default_graph.add((ex('s'), ex('p'), ex('o')))
        with pytest.raises(PluginException):
            ds.serialize(format='jsonld12')

    def test_dataset_parse_rejects(self):
        ds = StarLayerDataset()
        with pytest.raises(PluginException):
            ds.parse(data='{}', format='jsonld12')
