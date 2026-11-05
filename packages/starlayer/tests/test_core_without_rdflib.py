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
            @prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui#> .
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
    assert "http://www.w3.org/ns/shacl-ui#TextAreaEditor" in out and "TextFieldEditor" in out


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


def test_native_sparql_parse_helpers_import_lazily():
    # the SPARQL facade names are lazy: a name that needs rdflib raises the clear error, the rest of the package imports
    result = run_blocked("""
        import starlayer.sparql
        starlayer.sparql.prepare_query_12
    """)
    assert result.returncode != 0
    assert "pip install starlayer[rdflib]" in result.stderr


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


DUMP_PARSE = """
    from starlayer.sparql.parse_sparql import Node, parse_sparql, parse_sparql_update
    from starlayer.sparql import _terms

    def dump(x):
        if isinstance(x, Node):
            return [x.kind, [(k, dump(v)) for k, v in x.f.items()]]
        if isinstance(x, (list, tuple)):
            return [dump(i) for i in x]
        if hasattr(x, "n3"):
            return x.n3() if not type(x).__name__ == "BNode" else "_:b"
        return repr(x)

    QUERIES = [
        'PREFIX : <http://e/> SELECT ?s (COUNT(?o) AS ?n) WHERE { ?s :p ?o . FILTER(?o > 1 && lang(?o) != "en") } GROUP BY ?s',
        'SELECT * WHERE { <<( ?s <http://e/p> 1.50 )>> <http://e/q> "x"@en--rtl , "y"^^<http://e/dt> , true , -3 , 1e0 . }',
        'ASK { ?s a ?t OPTIONAL { ?s <http://e/p>/^<http://e/q> ?o } FILTER NOT EXISTS { ?o ?p [] } } ',
        'CONSTRUCT { ?s <http://e/p> ( 1 2 ) } WHERE { { ?s ?p ?o } UNION { VALUES ?s { <http://e/a> UNDEF } } }',
    ]
    out = [dump(parse_sparql(q)) for q in QUERIES]
    out.append(dump(parse_sparql_update('INSERT DATA { GRAPH <http://e/g> { <http://e/s> <http://e/p> "v" } }')))
    print(repr(out))
    print(_terms.encode_dirlang_datatype("en", "ltr").n3())
"""


def test_the_parser_gives_the_same_tree_with_and_without_rdflib():
    """Without rdflib the parser builds its tree from the stand-in terms in ``sparql/_terms.py``: same tree as with rdflib's."""
    blocked = ok(DUMP_PARSE)
    plain = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(DUMP_PARSE)], capture_output=True, text=True, timeout=300,
        env={"PYTHONPATH": PACKAGE_ROOT, "PYTHONHASHSEED": "0", "PATH": ""},
    )
    assert plain.returncode == 0, plain.stderr[-2000:]
    assert blocked == plain.stdout


def test_the_stand_in_dirlang_datatype_matches_the_vocabulary():
    from starlayer.sparql import _terms
    from starlayer.sparql.vocab import encode_dirlang_datatype

    assert str(_terms.encode_dirlang_datatype("en", "ltr")) == str(encode_dirlang_datatype("en", "ltr"))


@pytest.mark.parametrize(
    "code",
    [
        "from starlayer.graph import StarLayerGraph; StarLayerGraph().to_rdflib()",
        "from starlayer.graph import StarLayerGraph; StarLayerGraph.from_rdflib(None)",
        "from starlayer.graph import StarLayerGraph, ENTAILMENT; g = StarLayerGraph(); "
        "g.update('INSERT DATA { <http://e/s> a <http://e/C> }'); g.infer(entailment=ENTAILMENT['OWL-RDF-Based'])",
        "from starlayer.graph import StarLayerGraph, ENTAILMENT; StarLayerGraph().query('SELECT * WHERE {?s ?p ?o}', entailment=ENTAILMENT.RDFS)",
        "from starlayer.sparql import prepare_query_12",
        "import starlayer.sparql.srl",
        "import starlayer.starontology.manchester as m; m.manchester_validate(m.manchester_parse_to_tree('Class: <http://e/A>'))",
    ],
)
def test_an_rdflib_feature_raises_a_clear_import_error(code):
    result = run_blocked(code)
    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "starlayer[rdflib]" in result.stderr, result.stderr[-1500:]
