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

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import OxDataset, OxGraph

EX = 'http://example.org/'


def ex(local):
    return ox.NamedNode(EX + local)


class TestJsonld12IsRejectedAsUnrecognized:
    def test_graph_serialize_rejects(self):
        g = OxGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        with pytest.raises(ValueError):
            g.serialize(format='jsonld12')

    def test_graph_parse_rejects(self):
        g = OxGraph()
        with pytest.raises(ValueError):
            g.parse(data='{}', format='jsonld12')

    def test_dataset_serialize_rejects(self):
        ds = OxDataset()
        ds.default_graph.add((ex('s'), ex('p'), ex('o')))
        with pytest.raises(ValueError):
            ds.serialize(format='jsonld12')

    def test_dataset_parse_rejects(self):
        ds = OxDataset()
        with pytest.raises(ValueError):
            ds.parse(data='{}', format='jsonld12')
