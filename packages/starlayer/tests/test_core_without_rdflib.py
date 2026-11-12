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


def test_widget_selection_runs_without_rdflib():
    out = ok("""
        import pyoxigraph as ox
        from starlayer import StarLayerGraph
        from starlayer.shacl import select_widget, select_widgets

        shapes = StarLayerGraph()
        shapes.parse(format="turtle12", data='''
            @prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui/> .
            :S a sh:NodeShape ; sh:property :P , :Q .
            :P sh:path :p ; shui:editor shui:TextFieldEditor .
            :Q sh:path :q .
            [ a shui:WidgetScore ; shui:widget shui:TextAreaEditor ; shui:score 5 ] .
        ''')
        S = ox.NamedNode("http://e/S")
        got = select_widgets(shape_node=S, shapes_graph=shapes, scoring_graph=shapes, role="editor")
        print(sorted((k.value, v.value if v else None) for k, v in got.items()))
        print(select_widget(shape_node=ox.NamedNode("http://e/P"), shapes_graph=shapes, role="editor").value)
    """)
    assert "http://www.w3.org/ns/shacl-ui/TextAreaEditor" in out and "TextFieldEditor" in out


def test_canonical_hashing_and_isomorphism_run_without_rdflib():
    out = ok("""
        from starlayer import StarLayerGraph
        from starlayer.graph.rdfc import rdfc10_hash, to_canonical_nquads, CanonicalizationComplexityError
        from starlayer.graph import isomorphic

        a, b = StarLayerGraph(), StarLayerGraph()
        a.parse(format="turtle", data="<http://e/a> <http://e/p> [ <http://e/q> 1 ] .")
        b.parse(format="turtle", data="<http://e/a> <http://e/p> [ <http://e/q> 1 ] .")
        assert isomorphic(a, b) and rdfc10_hash(a) == rdfc10_hash(b)
        ring = StarLayerGraph()
        ring.parse(format="turtle", data="".join(f"_:b{i} <http://e/p> _:b{j} . " for i in range(10) for j in range(10) if i != j))
        try:
            to_canonical_nquads(ring)
        except CanonicalizationComplexityError:
            print("refused")
    """)
    assert "refused" in out


def test_the_sparql_facade_imports_without_rdflib():
    # the retired rdflib-based names (prepare_query_12, query_to_rdf, SALG, ...) are gone, not lazy
    out = ok("""
        import starlayer.sparql
        from starlayer.sparql import StarQuery, check_query
        assert check_query("SELECT * WHERE { ?s ?p ?o }") is None
        assert not hasattr(starlayer.sparql, "prepare_query_12")
        print("done")
    """)
    assert "done" in out


MANCHESTER = """
    Prefix: : <http://example.org/>
    Prefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    Ontology: <http://example.org/onto>
    Class: Animal
    Class: Cat
        SubClassOf: Animal, hasPet some (Animal and not Cat), Annotations: rdfs:comment "why" Animal
    ObjectProperty: hasPet
    DataProperty: age
        Range: xsd:integer[>= 0]
    Individual: felix
        Types: Cat
        Facts: age 3, not hasPet felix
"""


def test_manchester_parse_and_serialize_round_trip():
    out = ok("""
        import pyoxigraph as ox
        from starlayer.graph import StarLayerGraph, isomorphic
        from starlayer.graph.parsers.manchester_parser import parse_manchester
        from starlayer.graph.serializers.manchester import serialize_manchester
        text = __TEXT__
        g = StarLayerGraph(); g.parse(data=text, format="manchester")
        assert len(g) > 10 and all(isinstance(t[0], (ox.NamedNode, ox.BlankNode)) for t in g)
        assert all(isinstance(t, tuple) and isinstance(t[1], ox.NamedNode) for t in parse_manchester(text))
        out = g.serialize(format="manchester")
        assert out == serialize_manchester(g)
        h = StarLayerGraph(); h.parse(data=out, format="manchester")
        assert isomorphic(g, h), out
        print("done")
    """.replace("__TEXT__", repr(MANCHESTER)))
    assert "done" in out


def test_manchester_syntax_tree_round_trip():
    out = ok("""
        from starlayer.graph import StarLayerGraph, isomorphic
        from starlayer.starontology.manchester import (
            manchester_parse_to_tree, manchester_tree_to_owl, manchester_tree_to_text,
        )
        text = __TEXT__
        tree = manchester_parse_to_tree(text)
        assert isinstance(tree, StarLayerGraph)
        owl = manchester_tree_to_owl(tree)
        direct = StarLayerGraph(); direct.parse(data=text, format="manchester")
        assert isomorphic(owl, direct)
        again = manchester_parse_to_tree(manchester_tree_to_text(tree))
        assert isomorphic(manchester_tree_to_owl(again), direct)
        print("done")
    """.replace("__TEXT__", repr(MANCHESTER)))
    assert "done" in out


def test_rdfs_inference_and_infer_types_run_without_rdflib():
    out = ok("""
        import sys
        from starlayer import StarLayerGraph
        from starlayer.graph import ENTAILMENT
        from starlayer.shacl import infer_types, validate

        g = StarLayerGraph()
        g.parse(format="turtle12", data="@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . :A rdfs:subClassOf :B . :x a :A .")
        delta = g.infer(ENTAILMENT.RDFS, mode="delta")
        assert any(str(o) == "<http://e/B>" for _s, _p, o in delta.triples()), "subclass typing missing"
        shapes = StarLayerGraph()
        shapes.parse(format="turtle12", data="@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . :S sh:property [ sh:path :p ; sh:group :G ] .")
        types = infer_types(shapes)
        got = {(s.value, o.value) for s, _p, o in types.triples()}
        assert ("http://e/G", "http://www.w3.org/ns/shacl#PropertyGroup") in got, got
        import starlayer.starontology.manchester as m
        m.manchester_validate(m.manchester_parse_to_tree("Class: <http://e/A>"))  # validates with RDFS inference
        print("done", "rdflib" in sys.modules and sys.modules["rdflib"] is not None)
    """)
    assert out.strip() == "done False"


def test_nothing_in_the_core_imports_rdflib():
    # With rdflib importable, the core surface must still not load it.
    code = """
        import sys
        from starlayer.graph import StarLayerGraph, StarLayerDataset
        from starlayer.shacl import validate
        g = StarLayerGraph(); g.parse(data='Prefix: : <http://e/>\\nClass: A\\n', format='manchester'); g.serialize(format='manchester')
        import starlayer.starontology.manchester as m; m.manchester_tree_to_owl(m.manchester_parse_to_tree('Class: <http://e/A>\\n'))
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


SRL_CODE = """
    from starlayer.graph import StarLayerGraph
    from starlayer.sparql import srl

    RULES = '''PREFIX : <http://e/>
    RULE { ?x :anc ?y } WHERE { ?x :parent ?y }
    RULE { ?x :anc ?z } WHERE { ?x :anc ?y . ?y :parent ?z }
    RULE { ?x :adult true } WHERE { ?x :age ?a . FILTER(?a >= 18 && STRLEN(STR(?x)) > 3) }
    RULE { ?x :next ?n } WHERE { ?x :age ?a . SET(?n := ?a + 1) }
    RULE { ?x :safe true } WHERE { ?x :age ?a . NOT { ?x :banned ?b } }
    RULE { ?x :saw <<( ?x :age ?a )>> } WHERE { ?x :age ?a }
    DATA { :seed :age 30 . }
    '''
"""


def test_srl_parse_evaluate_encode_and_validate_work_without_rdflib():
    out = ok(SRL_CODE + """
    rules = srl.parse_ruleset(RULES)  # parses, checks well-formedness and validates against the srl: shapes
    g = StarLayerGraph()
    g.update('PREFIX : <http://e/> INSERT DATA { :a :parent :b . :b :parent :c . :a :age 20 . :c :banned 1 . :c :age 5 }')
    inferred = rules.infer(g)
    assert type(inferred).__name__ == "StarLayerGraph"
    rows = {tuple(t.value if hasattr(t, "value") else str(t) for t in triple) for triple in inferred}
    anc = "http://e/anc"
    assert ("http://e/a", anc, "http://e/c") in rows
    assert any(p == "http://e/adult" for _, p, _ in rows) and any(p == "http://e/next" for _, p, _ in rows)
    assert not any(s == "http://e/c" and p == "http://e/safe" for s, p, _ in rows)
    found = rules.query(g, srl.TriplePattern(__import__("pyoxigraph").Variable("x"), __import__("pyoxigraph").NamedNode(anc), __import__("pyoxigraph").NamedNode("http://e/c")))
    assert len(found) == 2
    assert rules.plan().strata
    tree, root = srl.ruleset_to_tree(rules)
    assert srl.srl_validate(tree)[0]
    again = srl.tree_to_ruleset(tree, root)
    assert srl.ruleset_to_text(again) == srl.ruleset_to_text(rules)
    graph2, root2 = srl.srl_parse_to_tree(RULES)
    assert "RULE" in srl.srl_tree_to_text(graph2, root2)
    print("done")
    """)
    assert "done" in out


def test_srl_errors_work_without_rdflib():
    out = ok("""
        from starlayer.sparql import srl
        for bad in ("RULE { ?x <http://e/p> ?y } WHERE { ?z <http://e/q> ?w }", "RULE { ?x"):
            try:
                srl.parse_ruleset(bad)
            except srl.SRLParseError:
                print("rejected")
    """)
    assert out.count("rejected") == 2


def test_srl_and_the_embedded_query_check_load_no_rdflib_module():
    code = SRL_CODE + """
    import sys
    rules = srl.parse_ruleset(RULES)
    g = StarLayerGraph()
    g.update('PREFIX : <http://e/> INSERT DATA { :a :parent :b . :a :age 20 }')
    rules.infer(g); rules.query(g, rules.rules[0].head[0])
    tree, root = srl.ruleset_to_tree(rules); srl.srl_validate(tree); srl.tree_to_ruleset(tree, root)
    from starlayer.shacl.meta_shapes import sparql_query_problems
    shapes = StarLayerGraph()
    shapes.parse(data='@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://e/> . ex:S a sh:NodeShape ; sh:sparql [ sh:prefixes ex: ; sh:select "SELECT $this WHERE { $this ex:p ?o }" ] . ex: sh:declare [ sh:prefix "ex" ; sh:namespace "http://e/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .', format="turtle")
    assert list(sparql_query_problems(shapes)) == []
    from starlayer.sparql import StarQuery
    StarQuery("SELECT * WHERE { ?s ?p ?o }").run(g)
    print([m for m in sys.modules if m == 'rdflib' or m.startswith('rdflib.')][:3])
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=300,
        env={"PYTHONPATH": PACKAGE_ROOT, "PYTHONHASHSEED": "0", "PATH": ""},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]", f"SRL loaded rdflib: {result.stdout.strip()}"


def test_srl_on_an_rdflib_graph_needs_rdflib_and_says_so():
    result = run_blocked("""
        from starlayer.sparql import srl
        class Foreign:  # not an Oxigraph graph, so the rdflib bridge is asked to copy it
            def __iter__(self):
                return iter(())
        srl.parse_ruleset("RULE { ?x <http://e/p> ?y } WHERE { ?x <http://e/q> ?y }").infer(Foreign())
    """)
    assert result.returncode != 0
    assert "starlayer[rdflib]" in result.stderr


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
        "from starlayer.graph import StarLayerGraph, ENTAILMENT; g = StarLayerGraph(); "
        "g.update('INSERT DATA { <http://e/s> a <http://e/C> }'); g.infer(entailment=[ENTAILMENT.RDFS, ENTAILMENT['OWL-RDF-Based']])",
    ],
)
def test_an_rdflib_feature_raises_a_clear_import_error(code):
    result = run_blocked(code)
    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "starlayer[rdflib]" in result.stderr, result.stderr[-1500:]
