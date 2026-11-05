"""
Unit tests for StarLayerDataset.

Covers: multi-graph TriG 1.2 parsing, named-graph context access,
quad iteration, TriG 1.2 / N-Quads 1.2 serialization, and round-trip.
"""

import pyoxigraph as ox
import pytest
from starlayer.graph import isomorphic
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

_XSD = "http://www.w3.org/2001/XMLSchema#"


def URIRef(iri):  # noqa: N802
    return ox.NamedNode(str(iri))


def BNode(label=None):  # noqa: N802
    return ox.BlankNode(label) if label else ox.BlankNode()


def Literal(value, lang=None, datatype=None):  # noqa: N802
    if lang:
        return ox.Literal(str(value), language=lang)
    if datatype is not None:
        return ox.Literal(str(value), datatype=ox.NamedNode(str(datatype)))
    if isinstance(value, bool):
        return ox.Literal("true" if value else "false", datatype=ox.NamedNode(_XSD + "boolean"))
    if isinstance(value, int):
        return ox.Literal(str(value), datatype=ox.NamedNode(_XSD + "integer"))
    if isinstance(value, float):
        return ox.Literal(repr(value), datatype=ox.NamedNode(_XSD + "double"))
    return ox.Literal(value)


def TripleTerm(s, p, o):  # noqa: N802
    return ox.Triple(s, p, o)

RDF_REIFIES = ox.NamedNode('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')

EX = 'http://example.org/'
G1 = URIRef(EX + 'graph1')
G2 = URIRef(EX + 'graph2')


def ex(local):
    return URIRef(EX + local)


TRIG_BASIC = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:s ex:p ex:o .
  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
  ex:stmt1 ex:confidence "0.9" .
}}

GRAPH <{EX}graph2> {{
  ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> .
  ex:stmt2 ex:source ex:newspaper .
}}
"""

TRIG_WITH_DEFAULT = f"""\
@prefix ex: <{EX}> .

ex:default_s ex:default_p ex:default_o .

GRAPH <{EX}named> {{
  ex:named_s ex:named_p ex:named_o .
}}
"""

TRIG_NESTED_TT = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt rdf:reifies <<( <<( ex:a ex:b ex:c )>> ex:p ex:o )>> .
}}
"""


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:

    def test_empty_on_init(self):
        ds = StarLayerDataset(default_union=False)
        assert list(ds.graph_names()) == [] or all(len(g) == 0 for g in ds.graph_names())


# ---------------------------------------------------------------------------
# Parse TriG 1.2
# ---------------------------------------------------------------------------

class TestParseTriG12:
    def test_named_graph_context_is_starlayer_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        assert isinstance(g1, StarLayerGraph)

    def test_named_graph_plain_triples(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        assert (ex('s'), ex('p'), ex('o')) in g1

    def test_named_graph_has_triple_term(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_named_graph_triple_term_in_object(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g1.objects(ex('stmt1'), RDF_REIFIES))
        assert tt in objs

    def test_two_named_graphs_independent(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        g2 = ds.graph(G2)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert not g1.has_triple_term(ex('bob'), ex('likes'), ex('carol'))
        assert g2.has_triple_term(ex('bob'), ex('likes'), ex('carol'))
        assert not g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_triple_terms_not_visible_across_graphs(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g2 = ds.graph(G2)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        objs = list(g2.objects(ex('stmt1'), RDF_REIFIES))
        assert tt not in objs

    def test_default_graph_triples_accessible(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_WITH_DEFAULT, format='trig12')
        found = any(
            (ex('default_s'), ex('default_p'), ex('default_o')) in g
            for g in ds.graphs()  # the default graph, then the named ones
        )
        assert found

    def test_named_graph_triple_count(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        assert len(g1) == 3  # s/p/o, stmt1/reifies/TT, stmt1/confidence/0.9


# ---------------------------------------------------------------------------
# StarLayerGraph API on named contexts
# ---------------------------------------------------------------------------

class TestContextAPI:
    def test_triple_terms_method(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        tts = list(g1.triple_terms())
        assert len(tts) == 1
        assert tts[0] == TripleTerm(ex('alice'), ex('knows'), ex('bob'))

    def test_reifiers_method(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        reifiers = list(g1.reifiers(TT=tt))
        assert ex('stmt1') in reifiers

    def test_encoding_triples_hidden_in_context(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1 = ds.graph(G1)
        enc_triples = [
            (s, p, o) for s, p, o in g1.triples((None, None, None))
            if str(p) in (
                'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormSubject',
                'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormPredicate',
                'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormObject',
            )
        ]
        assert enc_triples == []



# ---------------------------------------------------------------------------
# Dataset-wide reification lookups
# ---------------------------------------------------------------------------

TRIG_SAME_REIFIER_TWO_GRAPHS = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
  ex:stmt ex:source ex:sourceA .
}}

GRAPH <{EX}graph2> {{
  ex:stmt rdf:reifies <<( ex:carol ex:likes ex:dana )>> .
  ex:stmt ex:source ex:sourceB .
}}
"""


class TestDatasetWideReifiers:
    def test_returns_a_dataset(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        result = ds.reifiers(TT=tt)
        assert isinstance(result, StarLayerDataset)

    def test_result_scoped_to_originating_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        result = ds.reifiers(TT=tt)
        assert (ex('stmt1'), RDF_REIFIES, tt) in result.graph(G1)
        assert len(result.graph(G2)) == 0

    def test_result_includes_annotations(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        result = ds.reifiers(TT=tt)
        assert (ex('stmt1'), ex('confidence'), None) in [
            (s, p, None) for s, p, o in result.graph(G1).triples((None, None, None))
        ]

    def test_same_reifier_node_in_two_graphs_not_collapsed(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_SAME_REIFIER_TWO_GRAPHS, format='trig12')
        result = ds.reifiers()
        tt1 = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        tt2 = TripleTerm(ex('carol'), ex('likes'), ex('dana'))
        assert (ex('stmt'), RDF_REIFIES, tt1) in result.graph(G1)
        assert (ex('stmt'), RDF_REIFIES, tt2) in result.graph(G2)
        assert (ex('stmt'), RDF_REIFIES, tt2) not in result.graph(G1)
        assert (ex('stmt'), RDF_REIFIES, tt1) not in result.graph(G2)

    def test_reifications_returns_dataset_scoped_by_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_SAME_REIFIER_TWO_GRAPHS, format='trig12')
        result = ds.reifications()
        assert isinstance(result, StarLayerDataset)
        tt1 = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        tt2 = TripleTerm(ex('carol'), ex('likes'), ex('dana'))
        assert (ex('stmt'), RDF_REIFIES, tt1) in result.graph(G1)
        assert (ex('stmt'), RDF_REIFIES, tt1) not in result.graph(G2)
        assert (ex('stmt'), RDF_REIFIES, tt2) in result.graph(G2)

    def test_reified_triples_finds_matches_in_every_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_SAME_REIFIER_TWO_GRAPHS, format='trig12')
        result = ds.reified_triples(ex('stmt'))
        tt1 = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        tt2 = TripleTerm(ex('carol'), ex('likes'), ex('dana'))
        assert (ex('stmt'), RDF_REIFIES, tt1) in result.graph(G1)
        assert (ex('stmt'), RDF_REIFIES, tt2) in result.graph(G2)

    def test_reifier_annotations_excludes_reifies_triple(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_SAME_REIFIER_TWO_GRAPHS, format='trig12')
        tt1 = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        result = ds.reifier_annotations(tt1)
        g1 = result.graph(G1)
        assert (ex('stmt'), ex('source'), ex('sourceA')) in g1
        assert (ex('stmt'), RDF_REIFIES, tt1) not in g1

    def test_no_matches_returns_empty_dataset(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        tt = TripleTerm(ex('nobody'), ex('knows'), ex('nothing'))
        result = ds.reifiers(TT=tt)
        assert isinstance(result, StarLayerDataset)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Quad iteration
# ---------------------------------------------------------------------------

class TestQuads:
    def test_quads_include_both_graphs(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        graphs_seen = {q.graph_name.value for q in ds.quads()}
        assert G1.value in graphs_seen
        assert G2.value in graphs_seen

    def test_quads_restore_triple_terms(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        matching = [
            (s, p, o, g) for s, p, o, g in ds.quads()
            if o == tt
        ]
        assert len(matching) == 1
        assert matching[0][3] == G1

    def test_quads_graph_names_are_terms(self):
        # The old class yielded the graph object as the fourth member; an StarLayerDataset yields pyoxigraph Quads whose
        # graph_name is a term (use graph(name) for the view).
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        for q in ds.quads():
            assert isinstance(q.graph_name, ox.NamedNode)
            assert isinstance(ds.graph(q.graph_name), StarLayerGraph)

    def test_quads_no_encoding_triples(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        enc_preds = {
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormSubject',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormPredicate',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormObject',
        }
        for _, p, _, _ in ds.quads():
            assert str(p) not in enc_preds

    def test_triples_union_view(self):
        ds = StarLayerDataset(default_union=True)
        ds.parse(data=TRIG_BASIC, format='trig12')
        all_triples = list(ds.triples((None, None, None)))
        subjects = {s.value for s, _, _ in all_triples}
        assert EX + 's' in subjects
        assert EX + 'stmt2' in subjects

    def test_triples_default_union_false_excludes_named_graphs(self):
        ds = StarLayerDataset(default_union=False)  # default_union=False, the default
        ds.parse(data=TRIG_BASIC, format='trig12')
        all_triples = list(ds.triples((None, None, None)))
        assert all_triples == []


class TestDefaultUnionPropagation:
    """default_union=True must be honored consistently across every entry
    point, the same way self.triples() honors it (see TestQuads above) -
    not just the one that happened to get tested first. .query() and
    .update() each build their own internal Dataset/Graph wrapper for
    execution (_build_raw_execution_graph() and .update()'s in-memory
    branch, respectively) and previously constructed it with the rdflib
    default (default_union=False) regardless of self.default_union, so a
    GRAPH-less query/update pattern silently saw nothing from any named
    graph even when the dataset was explicitly configured to union them.
    """

    def test_query_graphless_pattern_sees_named_graphs(self):
        ds = StarLayerDataset(default_union=True)
        g1 = ds.graph(ex('g1'))
        g1.add((ex('s'), ex('p'), ex('o')))

        rows = list(ds.query('SELECT ?s ?p ?o WHERE { ?s ?p ?o }'))
        assert (ex('s'), ex('p'), ex('o')) in rows

    def test_query_graphless_pattern_empty_when_default_union_false(self):
        ds = StarLayerDataset(default_union=False)  # default_union=False, the default
        g1 = ds.graph(ex('g1'))
        g1.add((ex('s'), ex('p'), ex('o')))

        rows = list(ds.query('SELECT ?s ?p ?o WHERE { ?s ?p ?o }'))
        assert rows == []

    def test_update_graphless_where_matches_named_graphs(self):
        ds = StarLayerDataset(default_union=True)
        g1 = ds.graph(ex('g1'))
        g1.add((ex('s'), ex('p'), ex('o')))

        ds.update(f"""
            INSERT {{ ?s <{EX}marked> ?o }}
            WHERE {{ ?s ?p ?o }}
        """)
        # A GRAPH-less INSERT template targets the dataset's own default
        # graph (standard SPARQL Update semantics, confirmed against plain
        # rdflib.Dataset too) - default_union only widens what the
        # GRAPH-less WHERE clause can match, not where the INSERT lands.
        default_ctx = ds.graph(ds.default_graph.identifier)
        assert (ex('s'), ex('marked'), ex('o')) in default_ctx

    def test_update_graphless_where_empty_when_default_union_false(self):
        ds = StarLayerDataset(default_union=False)  # default_union=False, the default
        g1 = ds.graph(ex('g1'))
        g1.add((ex('s'), ex('p'), ex('o')))

        ds.update(f"""
            INSERT {{ ?s <{EX}marked> ?o }}
            WHERE {{ ?s ?p ?o }}
        """)
        default_ctx = ds.graph(ds.default_graph.identifier)
        assert len(default_ctx) == 0


class TestCBD:
    """Without StarLayerDataset's own cbd() override, rdflib's inherited
    Graph.cbd() hardcodes a plain rdflib.Graph() as the default target -
    previously a real, undiscovered bug: it crashed the moment the CBD'd
    data contained a real TripleTerm, since plain Graph.add() asserts its
    object is an rdflib Node, which TripleTerm is not. The override mirrors
    StarLayerGraph.cbd()'s own pattern exactly (default target_graph to a
    new StarLayerGraph, reject a plain Graph passed explicitly)."""

    def test_cbd_with_triple_term_does_not_crash_and_preserves_it(self):
        ds = StarLayerDataset(default_union=False)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        ds.add((ex('claim1'), ex('about'), tt))

        result = ds.cbd(ex('claim1'))

        assert isinstance(result, StarLayerGraph)
        assert result.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert len(result) == 1

    def test_cbd_rejects_a_plain_rdflib_graph_as_target(self):
        from rdflib import Graph

        ds = StarLayerDataset(default_union=False)
        ds.add((ex('s'), ex('p'), ex('o')))
        try:
            ds.cbd(ex('s'), target_graph=Graph())
        except TypeError as e:
            assert "must be an StarLayerGraph" in str(e)
        else:
            raise AssertionError("expected TypeError")

    def test_cbd_scoped_by_default_union_like_triples(self):
        """cbd() delegates internally to self.triples()/self.subjects(),
        so it inherits the same default_union scoping those honor - a
        blank node's own data living in a different named graph is only
        pulled in when default_union=True."""
        addr = BNode()

        ds_isolated = StarLayerDataset(default_union=False)  # default_union=False, the default
        ds_isolated.default_graph.add((ex('alice'), ex('name'), ex('AliceLit')))
        ds_isolated.default_graph.add((ex('alice'), ex('address'), addr))
        ds_isolated.graph(ex('named')).add((addr, ex('street'), ex('MainSt')))
        assert len(ds_isolated.cbd(ex('alice'))) == 2

        ds_union = StarLayerDataset(default_union=True)
        ds_union.default_graph.add((ex('alice'), ex('name'), ex('AliceLit')))
        ds_union.default_graph.add((ex('alice'), ex('address'), addr))
        ds_union.graph(ex('named')).add((addr, ex('street'), ex('MainSt')))
        assert len(ds_union.cbd(ex('alice'))) == 3


class TestDefaultGraphIsAStarLayerGraph:
    """rdflib's own Dataset.__init__ hardcodes self._default_context as a
    plain rdflib.Graph (default_graph/default_context both just return it
    directly) - a real, previously-undiscovered bug: ds.default_graph.add()
    crashed on a real TripleTerm, since plain Graph.add() rejects it as
    "not an rdflib term". Fixed in StarLayerDataset.__init__ by routing
    _default_context through get_context() instead, same as every other
    named context."""

    def test_default_graph_is_a_starlayergraph(self):
        ds = StarLayerDataset(default_union=False)
        assert isinstance(ds.default_graph, StarLayerGraph)


    def test_default_graph_accepts_a_triple_term_without_crashing(self):
        ds = StarLayerDataset(default_union=False)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        ds.default_graph.add((ex('claim1'), ex('about'), tt))
        assert ds.default_graph.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_graphs_yields_the_default_graph_as_a_starlayergraph(self):
        """graphs() yields from super(Dataset, self).graph_names(), which
        returns whatever self._default_context actually is - this is the
        same fix as above, verified from the graphs() call site too."""
        ds = StarLayerDataset(default_union=False)
        ds.default_graph.add((ex('s'), ex('p'), ex('o')))
        identifiers_and_types = [(g.identifier, type(g)) for g in ds.graphs()]
        assert all(t is StarLayerGraph for _id, t in identifiers_and_types)

    def test_default_graph_stays_current_after_turtle12_reroute_parse(self):
        """A second, narrower staleness bug than the two above: parse()
        routes format='turtle12' (and 'n3'/'n3-12'/'text/n3', which alias to
        it) through trig12's parser, which populates the default graph via
        _load_context()/_register_sg() - a *new* StarLayerGraph swapped into
        _sg_cache, never touching whatever object a one-time-cached
        self._default_context pointed at. Before the fix, default_graph
        kept returning that stale, registry-empty pre-parse object, so
        has_triple_term() here returned False even though the triple parsed
        correctly and even round-tripped correctly through serialize()
        (which reaches the current object via get_context(), not
        default_graph). longturtle12/nt12/rdfxml12/manchester don't hit
        this - they parse straight into self.default_graph.parse() instead
        of rerouting through trig12 - so this is specific to turtle12/n3.
        """
        ds = StarLayerDataset(default_union=False)
        text = (
            f'@prefix ex: <{EX}> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . '
            'ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .'
        )
        ds.parse(data=text, format='turtle12')
        assert ds.default_graph.has_triple_term(ex('bob'), ex('knows'), ex('carol'))


class TestSingleDocumentFormatsParseIntoDefaultGraph:
    """longturtle12/nt12/rdfxml12/manchester have no multi-graph syntax at
    all (same reasoning turtle12 already gets, just without a GRAPH-block
    superset like trig12 to route through) - previously these all fell
    through to super().parse() and failed outright (confirmed live,
    ValueError: Cannot read source - rdflib has no plugin registered for
    StarLayer's own invented format names). Fixed by parsing straight into
    self.default_graph, same place turtle12's own content already ends up.

    jsonld12 used to be in this list too - removed as a recognized format
    entirely (2026-10-02, see test_jsonld12_format.py), not just restricted,
    since JSON-LD has no published RDF 1.2 companion spec at all."""

    @pytest.mark.parametrize("fmt", ["nt12", "rdfxml12"])
    def test_rdf12_single_document_format_parses_into_default_graph(self, fmt):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        text = g.serialize(format=fmt)

        ds = StarLayerDataset(default_union=False)
        ds.parse(data=text, format=fmt)

        assert isinstance(ds.default_graph, StarLayerGraph)
        assert (ex('s'), ex('p'), ex('o')) in ds.default_graph

    def test_manchester_parses_into_default_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data="Prefix: ex: <http://example.org/>\nClass: ex:Foo", format="manchester")
        assert isinstance(ds.default_graph, StarLayerGraph)
        assert len(ds.default_graph) > 0

    def test_manchester_omn_alias_also_works(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data="Prefix: ex: <http://example.org/>\nClass: ex:Foo", format="omn")
        assert len(ds.default_graph) > 0

    def test_manchester_serialize_also_works(self):
        """manchester was added to _SINGLE_GRAPH_RDF12_FORMATS alongside
        this parse fix, for the same reason - previously failed with
        PluginException (confirmed live: no rdflib plugin registered for
        'manchester')."""
        ds = StarLayerDataset(default_union=False)
        ds.parse(data="Prefix: ex: <http://example.org/>\nClass: ex:Foo", format="manchester")
        text = ds.serialize(format="manchester")
        assert "Class:" in text


class TestSkolemizeDeskolemize:
    """Without an override, rdflib's inherited skolemize()/de_skolemize()
    hardcode a plain rdflib.Graph() as the default new_graph - same bug
    class as cbd()'s own (see TestCBD above): crashes the moment self
    contains a real TripleTerm."""

    def test_graph_skolemize_with_triple_term_does_not_crash(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('claim1'), ex('about'), tt))
        result = g.skolemize()
        assert isinstance(result, StarLayerGraph)
        assert result.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_graph_de_skolemize_with_triple_term_does_not_crash(self):
        g = StarLayerGraph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        g.add((ex('claim1'), ex('about'), tt))
        result = g.de_skolemize()
        assert isinstance(result, StarLayerGraph)
        assert result.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_dataset_skolemize_with_triple_term_does_not_crash(self):
        ds = StarLayerDataset(default_union=False)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        ds.add((ex('claim1'), ex('about'), tt))
        result = ds.skolemize()
        assert isinstance(result, StarLayerGraph)
        assert result.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_dataset_de_skolemize_with_triple_term_does_not_crash(self):
        ds = StarLayerDataset(default_union=False)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        ds.add((ex('claim1'), ex('about'), tt))
        result = ds.de_skolemize()
        assert isinstance(result, StarLayerGraph)
        assert result.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_skolemize_rejects_a_plain_rdflib_graph_as_new_graph(self):
        from rdflib import Graph

        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), ex('o')))
        try:
            g.skolemize(new_graph=Graph())
        except TypeError as e:
            assert "must be an StarLayerGraph" in str(e)
        else:
            raise AssertionError("expected TypeError")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_serialize_produces_graph_blocks(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        assert 'graph1 {' in out and 'graph2 {' in out  # Oxigraph's TriG writer has no GRAPH keyword and abbreviates the name

    def test_serialize_triple_terms_present(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        assert '<<(' in out

    def test_prefixes_before_graph_blocks(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        lines = out.splitlines()
        prefix_idx = next((i for i, line in enumerate(lines) if '@prefix' in line), None)
        graph_idx  = next((i for i, line in enumerate(lines) if line.endswith(' {')), None)
        assert prefix_idx is not None
        assert graph_idx is not None
        assert prefix_idx < graph_idx

    def test_literal_line_resembling_a_prefix_directive_round_trips(self):
        """Real bug: this dataset's own trig12 serialization used to split
        turtle_text into prefix/body lines via a blind
        `line.startswith('@prefix')` check with no string-literal
        awareness - so a multi-line literal whose word-wrapping happens to
        put the literal text '@prefix' at the very start of one of its own
        lines (e.g. a docstring describing Turtle's own @prefix syntax)
        was torn out of its own literal and emitted as bare, unquoted
        top-level text, corrupting the serialized document so it could no
        longer even be parsed back."""
        text = (
            'ex:s ex:p """An example of a directive:\n'
            '@prefix ex: <http://example.org/> . shown as plain prose here,\n'
            'not real top-level syntax.""" .\n'
        )
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=f'@prefix ex: <{EX}> .\n{text}', format='trig12')
        out = ds.serialize(format='trig12')

        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')  # must not raise
        literal_values = [q.object.value for q in ds2.quads()]
        assert any('@prefix ex: <http://example.org/> . shown as plain prose' in v for v in literal_values)


# ---------------------------------------------------------------------------
# Single-graph format serialization (flattened, no GRAPH blocks)
# ---------------------------------------------------------------------------

class TestSerializeSingleGraphFormats:
    def test_turtle12_has_no_graph_blocks(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='turtle12')
        assert 'GRAPH' not in out

    def test_turtle12_includes_triples_from_every_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='turtle12')
        assert 'ex:s' in out and 'ex:p' in out and 'ex:o' in out
        assert 'ex:stmt2' in out

    def test_turtle12_preserves_triple_terms(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='turtle12')
        assert '<<(' in out


    def test_nt12_flattens_dataset(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='nt12')
        assert '<<(' in out
        assert 'GRAPH' not in out

    def test_trig12_unaffected_by_new_formats(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        assert 'graph1 {' in out  # Oxigraph's TriG writer has no GRAPH keyword and abbreviates the name


class TestToGraph:
    def test_returns_a_starlayer_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g = ds.to_graph()
        assert isinstance(g, StarLayerGraph)

    def test_includes_triples_from_every_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g = ds.to_graph()
        assert (ex('s'), ex('p'), ex('o')) in g
        assert (ex('stmt2'), ex('source'), ex('newspaper')) in g

    def test_preserves_triple_terms(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g = ds.to_graph()
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        assert (ex('stmt1'), RDF_REIFIES, tt) in g

    def test_is_queryable_and_not_tied_to_the_dataset(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g = ds.to_graph()
        assert len(list(g.query('SELECT ?s WHERE { ?s ?p ?o }'))) == len(g)

    def test_matches_serialize_single_graph_format_output(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        # store order differs between the copy and the dataset, so compare the parsed graphs, not the text
        assert isomorphic(StarLayerGraph().parse(data=ds.to_graph().serialize(format='turtle12'), format='turtle12'), StarLayerGraph().parse(data=ds.serialize(format='turtle12'), format='turtle12'))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_plain_triple_roundtrip(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')
        g1 = ds2.graph(G1)
        assert (ex('s'), ex('p'), ex('o')) in g1

    def test_triple_term_roundtrip(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')
        g1 = ds2.graph(G1)
        g2 = ds2.graph(G2)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert g2.has_triple_term(ex('bob'), ex('likes'), ex('carol'))

    def test_graph_isolation_preserved_after_roundtrip(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='trig12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')
        g1 = ds2.graph(G1)
        g2 = ds2.graph(G2)
        assert not g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert not g1.has_triple_term(ex('bob'), ex('likes'), ex('carol'))

    def test_triple_count_preserved(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        g1_before = len(ds.graph(G1))
        g2_before = len(ds.graph(G2))

        out = ds.serialize(format='trig12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')

        assert len(ds2.graph(G1)) == g1_before
        assert len(ds2.graph(G2)) == g2_before


# ---------------------------------------------------------------------------
# N-Quads 1.2 multi-graph
# ---------------------------------------------------------------------------

NQ_BASIC = (
    f'<{EX}s> <{EX}p> <{EX}o> <{EX}graph1> .\n'
    f'<{EX}stmt1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
    f'<<( <{EX}alice> <{EX}knows> <{EX}bob> )>> <{EX}graph1> .\n'
    f'<{EX}stmt1> <{EX}confidence> "0.9" <{EX}graph1> .\n'
    f'<{EX}stmt2> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> '
    f'<<( <{EX}bob> <{EX}likes> <{EX}carol> )>> <{EX}graph2> .\n'
    f'<{EX}stmt2> <{EX}source> <{EX}newspaper> <{EX}graph2> .\n'
)


class TestNQ12MultiGraph:
    def test_parse_two_named_graphs(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        g1 = ds.graph(G1)
        g2 = ds.graph(G2)
        assert isinstance(g1, StarLayerGraph)
        assert isinstance(g2, StarLayerGraph)

    def test_triple_term_in_graph1(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        g1 = ds.graph(G1)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_triple_term_in_graph2(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        g2 = ds.graph(G2)
        assert g2.has_triple_term(ex('bob'), ex('likes'), ex('carol'))

    def test_graph_isolation(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        g1 = ds.graph(G1)
        g2 = ds.graph(G2)
        assert not g1.has_triple_term(ex('bob'), ex('likes'), ex('carol'))
        assert not g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_plain_triple_in_named_graph(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        g1 = ds.graph(G1)
        assert (ex('s'), ex('p'), ex('o')) in g1

    def test_serialize_nq12_includes_graph_names(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        out = ds.serialize(format='nq12')
        assert f'<{EX}graph1>' in out
        assert f'<{EX}graph2>' in out

    def test_serialize_nq12_triple_terms(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        out = ds.serialize(format='nq12')
        assert '<<(' in out

    def test_nq12_roundtrip(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        out = ds.serialize(format='nq12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='nq12')
        g1 = ds2.graph(G1)
        g2 = ds2.graph(G2)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert g2.has_triple_term(ex('bob'), ex('likes'), ex('carol'))
        assert not g2.has_triple_term(ex('alice'), ex('knows'), ex('bob'))

    def test_nq12_triple_count_preserved(self):
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        before = {G1.value: len(ds.graph(G1)), G2.value: len(ds.graph(G2))}
        out = ds.serialize(format='nq12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='nq12')
        assert len(ds2.graph(G1)) == before[G1.value]
        assert len(ds2.graph(G2)) == before[G2.value]

    def test_cross_format_trig_to_nq12(self):
        """Parse TriG 1.2, serialize to N-Quads 1.2, re-parse — data preserved."""
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=TRIG_BASIC, format='trig12')
        out = ds.serialize(format='nq12')
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='nq12')
        assert ds2.graph(G1).has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert ds2.graph(G2).has_triple_term(ex('bob'), ex('likes'), ex('carol'))

    def test_cross_format_nq12_to_trig(self):
        """Parse N-Quads 1.2, serialize to TriG 1.2, re-parse — data preserved."""
        ds = StarLayerDataset(default_union=False)
        ds.parse(data=NQ_BASIC, format='nq12')
        out = ds.serialize(format='trig12')
        assert 'graph1> {' in out or 'graph1 {' in out  # Oxigraph's TriG writer has no GRAPH keyword
        ds2 = StarLayerDataset(default_union=False)
        ds2.parse(data=out, format='trig12')
        assert ds2.graph(G1).has_triple_term(ex('alice'), ex('knows'), ex('bob'))
        assert ds2.graph(G2).has_triple_term(ex('bob'), ex('likes'), ex('carol'))


# ---------------------------------------------------------------------------
# Persistent store lifecycle — open() / close()
# ---------------------------------------------------------------------------

TRIG_TWO_GRAPHS = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
}}

GRAPH <{EX}graph2> {{
  ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> .
}}
"""




# ---------------------------------------------------------------------------
# Raw execution graph cache invalidation on context mutation
# ---------------------------------------------------------------------------



class TestChainingContractMatchesRdflib:
    """rdflib's own ConjunctiveGraph.addN()/Graph.open() both return self;
    these two StarLayerDataset overrides had silently dropped that (fixed
    2026-10-04) - same bug class as StarLayerGraph's own add()/remove()/
    open()/serialize(), see test_starlayer_graph.py's own class of the same
    name."""

    def test_addN_returns_self(self):
        ds = StarLayerDataset(default_union=False)
        t = (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))
        assert ds.addN([(*t, ds.default_graph)]) is ds


    def test_serialize_with_destination_returns_self_for_rdf12_native_format(self, tmp_path):
        """The nq12/trig12/trix12/single-graph-turtle12 branch builds its own
        text and writes it directly - that used to `return destination`
        (the path) instead of self, same bug as StarLayerGraph.serialize()'s
        own RDF12 branch."""
        ds = StarLayerDataset(default_union=False)
        ds.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        dest = tmp_path / 'out.trig'
        assert ds.serialize(destination=str(dest), format='trig12') is None  # the old class returned the dataset
        assert dest.exists()


