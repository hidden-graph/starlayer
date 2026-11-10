"""Regression tests for the robustness hunt: sh:pattern overflow and sh:construct query checks."""

from __future__ import annotations

import http.server
import threading
import warnings

import pytest
from starlayer import StarLayerGraph
from starlayer.shacl import apply_rules, validate
from starlayer.shacl_engine.plan import ShapeError

PRE = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <urn:ex:> .\n"


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle")
    return g


def test_pattern_with_an_oversized_repetition_is_a_shape_error():
    s = _graph(
        PRE + 'ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:pattern "a{99999999999}" ] .'
    )
    d = _graph('@prefix ex: <urn:ex:> . ex:a a ex:C ; ex:p "hello" .')
    with pytest.raises(ShapeError):
        validate(d, s)


@pytest.mark.parametrize("clause", ["SERVICE <http://127.0.0.1:{port}/sparql> {{ ?x ?y ?z }}", "MINUS {{ ?x ?y ?z }}"])
def test_sparql_rule_construct_rejects_service_and_minus(clause):
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _go(self):
            hits.append(self.path)
            body = b'{"head":{"vars":["x","y","z"]},"results":{"bindings":[]}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/sparql-results+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _go

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = clause.format(port=srv.server_address[1])
        data = _graph("<urn:ex:a> <urn:ex:p> 1 .")
        rule = _graph(
            PRE + "ex:R a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:SPARQLRule ; "
            f'sh:construct """CONSTRUCT {{ ?x ?y ?z }} WHERE {{ ?x ?y ?z . {body} }}""" ] .'
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(Exception) as ei:
                apply_rules(data, rule)
        assert type(ei.value).__name__ in ("ShapeError", "RuleError")
        assert not hits
    finally:
        srv.shutdown()
