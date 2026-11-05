"""The core surface works with rdflib absent; the rdflib-only features say so clearly.

rdflib is an optional extra (``pip install starlayer[rdflib]``). Each test runs a child interpreter that sets
``sys.modules["rdflib"] = None`` first (so ``import rdflib`` and any ``from rdflib...`` fail), then imports and exercises the
core: graphs, parse and serialize, SPARQL query and update, SHACL validation and rules. ``test_nothing_in_the_core_imports_rdflib``
also checks that no rdflib module got loaded.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PACKAGE_ROOT = str(Path(__file__).resolve().parents[1])

BLOCK = "import sys\nsys.modules['rdflib'] = None\n"


def run_blocked(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCK + textwrap.dedent(code)],
        capture_output=True, text=True, timeout=300, env={"PYTHONPATH": PACKAGE_ROOT, "PYTHONHASHSEED": "0", "PATH": ""},
    )


def ok(code: str) -> str:
    result = run_blocked(code)
    assert result.returncode == 0, result.stderr[-3000:]
    return result.stdout


def test_imports():
    ok("""
        import starlayer, starlayer.graph, starlayer.shacl, starlayer.sparql, starlayer.starontology
        from starlayer import StarLayerGraph, StarLayerDataset, StarShaclSchema, StarQuery
        from starlayer.graph import TripleTerm, DirLangString, ENTAILMENT, isomorphic, interop, setops, rdfc_native
        from starlayer.shacl import validate, apply_rules, evaluate, extract_subgraph
        import starlayer.conformance
    """)


def test_parse_serialize_and_isomorphism():
    out = ok("""
        from starlayer.graph import StarLayerGraph, StarLayerDataset, isomorphic
        ttl = '@prefix : <http://e/> . :s :p "x", :o ; :q <<( :a :b :c )>> .'
        g = StarLayerGraph(); g.parse(data=ttl, format="turtle12")
        assert len(g) == 3
        for fmt in ("turtle12", "nt12"):
            h = StarLayerGraph(); h.parse(data=g.serialize(format=fmt), format=fmt)
            assert isomorphic(g, h), fmt
        pretty = StarLayerGraph(); pretty.parse(data=g.serialize(format="turtle12", pretty=True), format="turtle12")
        assert isomorphic(g, pretty)
        d = StarLayerDataset(); d.parse(data='<http://e/s> <http://e/p> <http://e/o> <http://e/g> .', format="nquads")
        trig = d.serialize(format="trig")
        d2 = StarLayerDataset(); d2.parse(data=trig, format="trig")
        assert isomorphic(d, d2)
        assert not isomorphic(g, StarLayerGraph())
        print("done")
    """)
    assert "done" in out


def test_query_and_update():
    out = ok("""
        from starlayer.graph import StarLayerGraph, StarLayerDataset
        g = StarLayerGraph()
        g.update('INSERT DATA { <http://e/s> <http://e/p> "v", 1 ; <http://e/q> <<( <http://e/a> <http://e/b> <http://e/c> )>> }')
        rows = list(g.query("SELECT ?o WHERE { <http://e/s> <http://e/p> ?o }"))
        assert len(rows) == 2
        assert g.query("ASK { ?s ?p <<( <http://e/a> <http://e/b> <http://e/c> )>> }").askAnswer
        built = g.query("CONSTRUCT { ?s <http://e/p2> ?o } WHERE { ?s <http://e/p> ?o }")
        assert len(built) == 2
        g.update("DELETE WHERE { ?s <http://e/p> ?o }")
        assert len(g) == 1
        d = StarLayerDataset()
        d.update('INSERT DATA { GRAPH <http://e/g> { <http://e/s> <http://e/p> <http://e/o> } }')
        assert len(list(d.query("SELECT * WHERE { GRAPH ?g { ?s ?p ?o } }"))) == 1
        print("done")
    """)
    assert "done" in out


def test_shacl_validate_and_rules():
    out = ok("""
        from starlayer.graph import StarLayerGraph
        from starlayer.shacl import validate, apply_rules, StarShaclSchema
        shapes = StarLayerGraph(); shapes.parse(format="turtle12", data='''
            @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix : <http://e/> .
            :S a sh:NodeShape ; sh:targetClass :C ;
               sh:property [ sh:path :p ; sh:minCount 1 ] ;
               sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate :derived ; sh:object :yes ] .
        ''')
        data = StarLayerGraph(); data.parse(format="turtle12", data='@prefix : <http://e/> . :a a :C . :b a :C ; :p 1 .')
        result = validate(data, shapes)
        assert not result.conforms and 'MinCountConstraintComponent' in result.report_text
        rules = apply_rules(data, shapes)
        assert len(rules.inferred_graph) >= 1
        schema = StarShaclSchema(shacl_graph=shapes)
        assert not schema.validate(data).conforms
        print("done")
    """)
    assert "done" in out


def test_shacl_sparql_constraints_and_exists_queries():
    out = ok("""
        from starlayer.graph import StarLayerGraph
        from starlayer.shacl import validate
        shapes = StarLayerGraph(); shapes.parse(format="turtle12", data='''
            @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix : <http://e/> .
            :S a sh:NodeShape ; sh:targetClass :C ;
               sh:sparql [ sh:message "no friend" ; sh:prefixes :decl ;
                  sh:select "SELECT $this WHERE { FILTER NOT EXISTS { $this :knows ?x } }" ] .
            :decl sh:declare [ sh:prefix "" ; sh:namespace "http://e/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .
        ''')
        data = StarLayerGraph(); data.parse(format="turtle12", data='@prefix : <http://e/> . :a a :C . :b a :C ; :knows :a .')
        result = validate(data, shapes)
        assert not result.conforms
        rows = list(data.query("PREFIX : <http://e/> SELECT ?s WHERE { ?s a :C FILTER NOT EXISTS { ?s :knows ?o } }"))
        assert len(rows) == 1
        print("done")
    """)
    assert "done" in out


def test_native_sparql_parse_helpers_import_lazily():
    # the SPARQL facade names are lazy: a name that needs rdflib raises the clear error, the rest of the package imports
    result = run_blocked("""
        import starlayer.sparql
        starlayer.sparql.prepare_query_12
    """)
    assert result.returncode != 0
    assert "pip install starlayer[rdflib]" in result.stderr


def test_nothing_in_the_core_imports_rdflib():
    # With rdflib importable, the core surface must still not load it.
    code = """
        import sys
        from starlayer.graph import StarLayerGraph, StarLayerDataset
        from starlayer.shacl import validate
        g = StarLayerGraph(); g.update('INSERT DATA { <http://e/s> <http://e/p> 1 }')
        list(g.query('SELECT * WHERE { ?s ?p ?o }'))
        print([m for m in sys.modules if m == 'rdflib' or m.startswith('rdflib.')][:3])
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=300,
        env={"PYTHONPATH": PACKAGE_ROOT, "PYTHONHASHSEED": "0", "PATH": ""},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]", f"the core surface loaded rdflib: {result.stdout.strip()}"


SQE_CODE = """
    from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text, sqe_validate
    from starlayer.sparql.sqe.rewrite import rewrite_exists_text
    from starlayer.graph import ENTAILMENT, StarLayerGraph

    QUERIES = [
        'PREFIX : <http://e/> SELECT ?s (COUNT(?o) AS ?n) WHERE { ?s :p ?o . FILTER(?o > 1 && lang(?o) != "en") } GROUP BY ?s',
        'SELECT * WHERE { <<( ?s <http://e/p> 1.50 )>> <http://e/q> "x"@en--rtl , "y"^^<http://e/dt> , true , -3 , 1e0 . }',
        'ASK { ?s a ?t OPTIONAL { ?s <http://e/p>/^<http://e/q> ?o } FILTER NOT EXISTS { ?o ?p [] } } ',
        'CONSTRUCT { ?s <http://e/p> ( 1 2 ) } WHERE { { ?s ?p ?o } UNION { VALUES ?s { <http://e/a> UNDEF } } }',
        'SELECT * WHERE { <s> <p> ?o }',
        'DELETE { ?s ?p ?o } INSERT { ?s ?p 1 } WHERE { ?s ?p ?o }',
    ]
"""


def test_sqe_parse_render_and_validate_work_without_rdflib():
    out = ok(SQE_CODE + """
    for q in QUERIES:
        graph, root = sqe_parse_to_tree(q)
        assert type(graph).__name__ == "StarLayerGraph"
        assert sqe_validate(graph)[0]
        text = sqe_tree_to_text(graph, root)
        graph2, root2 = sqe_parse_to_tree(text)
        assert sqe_tree_to_text(graph2, root2) == text, (q, text)
    print("done")
    """)
    assert "done" in out


def test_the_exists_rewrite_and_the_entailment_rewrite_work_without_rdflib():
    out = ok(SQE_CODE + """
    from starlayer.sparql.sqe.entailment import rewrite_for_entailment
    q = "PREFIX : <http://e/> SELECT ?s WHERE { ?s :p ?o FILTER NOT EXISTS { ?s :q ?x FILTER(?x = ?o) } }"
    rewritten = rewrite_exists_text(q)
    assert rewritten != q and "MINUS" in rewritten and "EXISTS" not in rewritten, rewritten
    plain = "SELECT ?s WHERE { ?s a <http://e/C> }"
    assert rewrite_for_entailment(plain, ENTAILMENT.RDF) == plain  # RDF entailment only widens rdf:Property tests
    assert rewrite_for_entailment("SELECT ?s WHERE { ?s a <http://www.w3.org/1999/02/22-rdf-syntax-ns#Property> }", ENTAILMENT.RDF) != plain
    assert rewrite_for_entailment(plain, ENTAILMENT.RDFS) != plain
    g = StarLayerGraph()
    g.parse(format="turtle12", data="@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . :D rdfs:subClassOf :C . :a a :D .")
    rows = list(g.query("PREFIX : <http://e/> SELECT ?s WHERE { ?s a :C }", entailment=ENTAILMENT.RDFS))
    assert len(rows) == 1
    print("done")
    """)
    assert "done" in out


def test_the_syntax_checks_of_a_star_query_work_without_rdflib():
    out = ok("""
        from starlayer.sparql.star_query import StarQuery
        StarQuery("SELECT * WHERE { ?s ?p ?o }")
        try:
            StarQuery("SELECT * WHERE { ?s ?p }")
        except ValueError:
            print("rejected")
    """)
    assert "rejected" in out


def test_sqe_tree_to_query_needs_rdflib_and_says_so():
    result = run_blocked("from starlayer.sparql.sqe import sqe_tree_to_query")
    assert result.returncode != 0 and "starlayer[rdflib]" in result.stderr


def test_the_sqe_text_path_loads_no_rdflib_module():
    code = SQE_CODE + """
    import sys
    graph, root = sqe_parse_to_tree(QUERIES[0])
    sqe_validate(graph); sqe_tree_to_text(graph, root); rewrite_exists_text(QUERIES[2])
    print([m for m in sys.modules if m == 'rdflib' or m.startswith('rdflib.')][:3])
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=300,
        env={"PYTHONPATH": PACKAGE_ROOT, "PYTHONHASHSEED": "0", "PATH": ""},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]", f"the sqe path loaded rdflib: {result.stdout.strip()}"


@pytest.mark.parametrize(
    "code",
    [
        "from starlayer.graph import StarLayerGraph; StarLayerGraph().to_rdflib()",
        "from starlayer.graph import StarLayerGraph; StarLayerGraph.from_rdflib(None)",
        "from starlayer.graph import StarLayerGraph, ENTAILMENT; g = StarLayerGraph(); "
        "g.update('INSERT DATA { <http://e/s> a <http://e/C> }'); g.infer(entailment=ENTAILMENT['OWL-RDF-Based'])",
        "import starlayer.shacl.ui_widget_selection",
        "from starlayer.shacl import select_widget",
        "from starlayer.sparql import prepare_query_12",
        "import starlayer.sparql.srl",
        "import starlayer.starontology.manchester",
        "from starlayer.graph.compare import to_isomorphic; to_isomorphic(object())",
    ],
)
def test_an_rdflib_feature_raises_a_clear_import_error(code):
    result = run_blocked(code)
    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "starlayer[rdflib]" in result.stderr, result.stderr[-1500:]
