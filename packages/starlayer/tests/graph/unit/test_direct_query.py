"""The opt-in direct-execution spike (``starlayer.graph.query.direct``): query text straight to in-process Oxigraph."""
import pytest
from rdflib import Literal, URIRef
from starlayer.graph import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.graph.query.direct import run_direct, run_direct_update

ox = pytest.importorskip('pyoxigraph')
OxigraphStore = pytest.importorskip('oxrdflib').OxigraphStore

E = 'http://e/'


@pytest.fixture
def g():
    graph = StarLayerGraph(store=OxigraphStore(store=ox.Store()), backend='rdf-1.2', direct_query=True)
    graph.update('PREFIX e: <http://e/> INSERT DATA { e:a e:p 1, 2 . e:b e:p 3 . '
                 'e:a e:q <<( e:x e:y "z"@en--ltr )>> }')
    return graph


def test_init_ns_and_base(g):
    r = g.query('SELECT ?o WHERE { e:a e:p ?o }', initNs={'e': E})
    assert sorted(int(row[0]) for row in r) == [1, 2]
    r = run_direct(g.store, 'SELECT ?o WHERE { <a> <p> ?o }', base=E)
    assert len(list(r)) == 2


def test_init_bindings_projected_and_not_projected(g):
    r = g.query('SELECT * WHERE { ?s e:p ?o }', initNs={'e': E}, initBindings={'s': URIRef(E + 'b')})
    assert [int(row.o) for row in r] == [3]
    # ?s is not projected: the engine refuses substitutions, the VALUES fallback applies
    r = g.query('SELECT ?o WHERE { ?s e:p ?o }', initNs={'e': E}, initBindings={'s': URIRef(E + 'b')})
    assert [int(row[0]) for row in r] == [3]


def test_triple_term_and_dirlangstring_come_back_as_starlayer_types(g):
    row = next(iter(g.query('SELECT ?o WHERE { e:a e:q ?o }', initNs={'e': E})))
    assert isinstance(row[0], TripleTerm)
    assert row[0].object.direction == 'ltr'


def test_ask_construct_update(g):
    assert g.query('ASK { ?s ?p 3 }').askAnswer is True
    c = g.query('CONSTRUCT { ?s e:r ?o } WHERE { ?s e:p ?o }', initNs={'e': E})
    assert len(c.graph) == 3
    run_direct_update(g.store, 'INSERT DATA { e:c e:p 4 }', init_ns={'e': E})
    assert Literal(4) in {row[0] for row in g.query('SELECT ?o WHERE { e:c e:p ?o }', initNs={'e': E})}


def test_syntax_error_is_the_engines(g):
    with pytest.raises(SyntaxError):
        g.query('SELEC nothing')


def test_flag_off_by_default():
    plain = StarLayerGraph(store=OxigraphStore(store=ox.Store()), backend='rdf-1.2')
    assert plain._direct_query is None
