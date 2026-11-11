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
