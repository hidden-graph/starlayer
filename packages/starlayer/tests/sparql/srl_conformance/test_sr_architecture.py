"""Architecture rule: SRL is published (ontology, shapes, tree format) without ``salg:`` and without starlayer.

``salg:`` is the query-algebra tree encoding. Using it *inside* starlayer is fine; what must hold is that what is
published for SRL stands alone: ``srl:`` plus the shared ``spexpr:`` expression vocabulary and ``sqe:``
(which supplies ``sqe:TripleTerm``), none of which may reference ``salg:``, validated by any SHACL engine.

Five checks, each a passing guard:

- the ``.ttl`` files SRL is published with contain no ``salg:`` IRI and import no ``salg:`` shapes graph;
- the ``srl:`` trees SRL produces contain no ``salg:`` term (triple terms are ``sqe:TripleTerm``);
- the graphs ``srl_validate`` loads contain no ``salg:`` term;
- ``srl.py`` loads no ``salg`` module or graph;
- **the published shapes validate real SRL trees in a clean process that imports only rdflib and pyshacl** (no
  starlayer), which is what a downstream publisher or user would run.

History: before 2026-10-19 the trees used four ``salg:`` terms, ``srl_validate`` loaded all of ``salg:``'s
ontology (290 terms) and shapes (617), and expressions were encoded and rendered by ``salg:``'s machinery.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef

from .corpus import CASES
from .helpers import srl_parse_to_tree

SALG = "https://github.com/hidden-graph/starlayer/ns/sparql/algebra#"
STARLAYER = Path(__file__).resolve().parents[3] / "starlayer"
ONTOLOGY_DIR = STARLAYER / "starontology"

PUBLISHED = {
    "shapes": ["srl_shapes.ttl", "spexpr_shapes.ttl", "sqe_shapes.ttl"],
    "ontologies": ["srl-ontology.ttl", "spexpr-ontology.ttl", "sqe-ontology.ttl"],
}

# Representative cases: triple terms, expressions of every family, functions, negation, data, paths.
TREE_CASES = [c for c in CASES if c.id in {
    "rdf12-triple-term", "rdf12-triple-term-nested", "rdf12-reified-triple", "head-triple-term",
    "body-filter-brackets", "body-filter-builtin", "body-filter-function", "body-set", "body-not", "expr-in",
    "expr-builtin-nesting", "expr-unary-not", "expr-unary-minus", "expr-parens", "pat-path-sequence",
    "data-simple", "rule-where-data", "lit-lang-dir",
}]


def _salg_terms(graph) -> set[str]:
    found = set()
    for triple in graph:
        for term in triple:
            if isinstance(term, URIRef) and str(term).startswith(SALG):
                found.add(str(term))
            if isinstance(term, Literal) and term.datatype and str(term.datatype).startswith(SALG):
                found.add(str(term.datatype))
    return found


@pytest.mark.srl_conformance
def test_published_files_contain_no_salg_terms_and_import_no_salg_graph():
    for name in PUBLISHED["shapes"] + PUBLISHED["ontologies"]:
        graph = Graph().parse(ONTOLOGY_DIR / name, format="turtle")
        assert not _salg_terms(graph), f"{name}: {sorted(_salg_terms(graph))[:5]}"
        text = (ONTOLOGY_DIR / name).read_text(encoding="utf-8")
        assert "algebra#ShapesGraph" not in text and "salg:ShapesGraph" not in text, name


@pytest.mark.srl_conformance
def test_trees_contain_no_salg_terms():
    found: set[str] = set()
    for case in TREE_CASES:
        graph, _ = srl_parse_to_tree(case.text)
        found |= _salg_terms(graph)
    assert not found, f"salg: terms in srl: trees: {sorted(found)}"


@pytest.mark.srl_conformance
def test_validation_graphs_do_not_load_salg():
    from starlayer.sparql.srl import _ontology_graph, _shapes_graph

    ontology, shapes = _salg_terms(_ontology_graph()), _salg_terms(_shapes_graph())
    assert not ontology and not shapes, f"salg: terms: {len(ontology)} in the ontology, {len(shapes)} in the shapes"


@pytest.mark.srl_conformance
def test_srl_source_loads_no_salg_module_or_graph():
    code = (STARLAYER / "sparql" / "srl.py").read_text(encoding="utf-8")
    code_lines = [ln for ln in code.splitlines() if not ln.lstrip().startswith(("#", '"', "'")) and "``" not in ln]
    offending = [ln.strip() for ln in code_lines if re.search(r"sparql_owl|sparql_shacl|\.salg\b|import salg", ln)]
    assert not offending, offending


@pytest.mark.srl_conformance
def test_published_shapes_validate_srl_trees_without_starlayer(tmp_path):
    """The publishing check: a separate process with only rdflib and pyshacl, the published .ttl files, and trees
    serialized by SRL, must find every tree conformant. It asserts starlayer was never imported."""
    tree_files = []
    for case in TREE_CASES:
        graph, _ = srl_parse_to_tree(case.text)
        path = tmp_path / f"{case.id}.ttl"
        try:
            graph.serialize(path, format="turtle")
            Graph().parse(path, format="turtle")  # plain rdflib must be able to read it back
        except Exception:  # noqa: BLE001 - a tree with RDF 1.2 syntax plain rdflib cannot read is not a candidate
            continue
        tree_files.append(path.name)
    assert len(tree_files) >= 12, tree_files

    script = textwrap.dedent(f"""
        import sys, warnings
        from pathlib import Path
        from rdflib import Graph
        import pyshacl
        onto = Path({str(ONTOLOGY_DIR)!r})
        def load(names):
            g = Graph()
            for n in names:
                g.parse(onto / n, format="turtle")
            return g
        shapes, ont = load({PUBLISHED["shapes"]!r}), load({PUBLISHED["ontologies"]!r})
        failed = []
        for name in {tree_files!r}:
            data = Graph().parse(Path({str(tmp_path)!r}) / name, format="turtle")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                conforms, _, text = pyshacl.validate(data, shacl_graph=shapes, ont_graph=ont,
                                                     inference="rdfs", advanced=True, max_validation_depth=100)
            if not conforms:
                failed.append(name)
        assert "starlayer" not in sys.modules, "starlayer was imported"
        print("FAILED:" + ",".join(failed))
    """)
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-800:]
    assert result.stdout.strip().endswith("FAILED:"), result.stdout[-400:]
