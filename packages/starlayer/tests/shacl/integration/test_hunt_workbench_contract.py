"""Regression tests for the workbench-contract hunt: the public API applications use."""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-W", "ignore", "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=120)


def test_evaluate_expression_gives_pyoxigraph_terms_without_rdflib():
    r = _run(
        """
        import sys
        class Block:
            def find_spec(self, name, path=None, target=None):
                if name == "rdflib" or name.startswith("rdflib."):
                    raise ImportError("rdflib blocked")
        sys.meta_path.insert(0, Block())
        import pyoxigraph as ox
        from starlayer import StarLayerGraph
        from starlayer.shacl import evaluate_expression
        sg = StarLayerGraph(); sg.parse(data="@prefix : <http://e/> . @prefix sparql: <http://www.w3.org/ns/sparql#> . :s :x [ sparql:concat ( 'a' 'b' ) ] .", format="turtle")
        e = next(sg.objects(ox.NamedNode("http://e/s"), ox.NamedNode("http://e/x")))
        out = evaluate_expression(sg, StarLayerGraph(), e, ox.NamedNode("http://e/f"))
        assert out == [ox.Literal("ab")], out
        """
    )
    assert r.returncode == 0, r.stderr


def test_ruleset_parse_and_infer_on_a_graph_without_literals_do_not_warn():
    r = _run(
        """
        import warnings
        from starlayer import StarLayerGraph
        from starlayer.sparql.srl import parse_ruleset
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rs = parse_ruleset("PREFIX ex: <http://e/> RULE { ?x ex:anc ?y } WHERE { ?x ex:parent ?y }")
            g = StarLayerGraph()
            g.parse(data="@prefix ex: <http://e/> . ex:a ex:parent ex:b .", format="turtle")
            rs.infer(g)
        fid = [x for x in w if "Fidelity" in x.category.__name__]
        assert not fid, str(fid[0].message)[:200]
        """
    )
    assert r.returncode == 0, r.stderr


def test_schema_validate_takes_the_keywords_validate_takes():
    import warnings

    from starlayer import StarLayerGraph, StarShaclSchema
    from starlayer.shacl import validate

    warnings.simplefilter("ignore")
    shapes = StarLayerGraph()
    shapes.parse(
        data="@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . :S a sh:NodeShape ; sh:targetNode :a .",
        format="turtle",
    )
    data, spec = StarLayerGraph(), StarLayerGraph()
    validate(data, shapes, specification_graph=spec, shapes_graph_iri="http://e/sg")
    schema = StarShaclSchema(shapes)
    schema.validate(data, specification_graph=spec)
    schema.validate(data, shapes_graph_iri="http://e/sg")


def test_a_none_data_graph_is_a_type_error_naming_data_graph():
    import warnings

    import pytest
    from starlayer import StarLayerGraph
    from starlayer.shacl import apply_rules, validate

    warnings.simplefilter("ignore")
    shapes = StarLayerGraph()
    shapes.parse(
        data="@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . :S a sh:NodeShape ; sh:targetNode :a ; sh:property [ sh:path :p ; sh:minCount 1 ] .",
        format="turtle",
    )
    with pytest.raises(TypeError, match="data_graph"):
        validate(None, shapes)
    with pytest.raises(TypeError, match="data_graph"):
        apply_rules(None, shapes)


def test_check_query_prepare_sends_no_service_request():
    import http.server
    import threading

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/sparql-results+json")
            self.end_headers()
            self.wfile.write(b'{"head":{"vars":["s"]},"results":{"bindings":[]}}')

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        from starlayer.sparql import check_query

        port = server.server_address[1]
        assert check_query(f"SELECT * WHERE {{ SERVICE <http://127.0.0.1:{port}/sparql> {{ ?s ?p ?o }} }}", prepare=True) is None
        assert hits == []
        assert check_query("SELECT * WHERE { ?s nope:p ?o }", prepare=True) is not None  # a plain query is still prepared
    finally:
        server.shutdown()


def test_star_query_runs_on_a_bare_pyoxigraph_store():
    import pyoxigraph as ox
    from starlayer import StarQuery

    store = ox.Store()
    store.add(ox.Quad(ox.NamedNode("http://e/a"), ox.NamedNode("http://e/p"), ox.NamedNode("http://e/b"), ox.DefaultGraph()))
    assert len(list(StarQuery("SELECT ?s { ?s ?p ?o }").run(store))) == 1


def test_sparql_query_problems_agrees_with_validate_on_a_file_bound_prefix():
    import pytest
    from starlayer import StarLayerGraph
    from starlayer.shacl import ShapeError, sparql_query_problems, validate

    text = """@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:S a sh:NodeShape ; sh:targetNode ex:x ; sh:sparql [ sh:message "bad" ; sh:select "SELECT $this WHERE { $this ex:p ?v }" ] .
    ex:x ex:p 1 ."""
    g = StarLayerGraph()
    g.parse(data=text, format="turtle")
    with pytest.raises(ShapeError):
        validate(g, g)
    assert list(sparql_query_problems(g))
