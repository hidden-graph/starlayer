"""The OWL 2 DL engines (HermiT, rustdl) run on pyoxigraph terms: no rdflib in their modules, and the things an rdflib graph could
not hold (a triple term, a base-direction literal) and the things a reasoner renames (blank node individuals) come through.

Both reasoners read RDF/XML from a file, so the ontology goes through Oxigraph's RDF/XML writer; the result comes back through its
parser (HermiT) or as plain IRIs and literals (rustdl).
"""

import ast
import shutil
from pathlib import Path

import pyoxigraph as ox
import pytest
from starlayer.graph import (
    RDF,
    RDFS,
    BlankNode,
    Literal,
    Namespace,
    StarLayerGraph,
    Triple,
)
from starlayer.graph.entailment import ENTAILMENT

PACKAGE = Path(__file__).resolve().parents[1] / "starlayer_reasoning"
EX = Namespace("http://example.org/")

try:
    import owlready2  # noqa: F401

    _HERMIT = shutil.which("java") is not None
except ImportError:
    _HERMIT = False
try:
    import rustdl  # noqa: F401

    _RUSTDL = True
except ImportError:
    _RUSTDL = False

ENGINES = [
    pytest.param("hermit", marks=pytest.mark.skipif(not _HERMIT, reason="owlready2 or a JVM is not available")),
    pytest.param("rustdl", marks=pytest.mark.skipif(not _RUSTDL, reason="rustdl is not installed")),
]


@pytest.mark.parametrize("module", ["owl_dl.py", "owl_dl_rustdl.py", "owl_dl_delta.py"])
def test_the_dl_modules_do_not_import_rdflib(module):
    tree = ast.parse((PACKAGE / module).read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert not imported & {"rdflib", "owlrl"}, imported & {"rdflib", "owlrl"}


@pytest.mark.parametrize("engine", ENGINES)
def test_a_triple_term_a_direction_literal_and_a_blank_node_individual_come_through(engine):
    g = StarLayerGraph()
    g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
    g.add((EX.alice, RDF.type, EX.Manager))
    g.add((EX.report, EX.says, Triple(EX.alice, EX.worksFor, EX.AcmeCorp)))
    g.add((EX.alice, EX.label, Literal("hello", language="ar", direction=ox.BaseDirection.RTL)))
    anonymous = BlankNode()
    g.add((anonymous, RDF.type, EX.Manager))
    g.add((anonymous, EX.knows, EX.alice))

    delta = set(g.infer(entailment=ENTAILMENT["OWL-Direct"], engine=engine, mode="delta"))

    assert (EX.alice, RDF.type, EX.Employee) in delta
    assert (anonymous, RDF.type, EX.Employee) in delta  # the blank node individual keeps its own name
    for s, p, o in delta:  # nothing about the triple term's description, nothing the reasoner invented
        assert "propositionForm" not in p.value and "PropositionForm" not in str(o)
        assert not (isinstance(s, BlankNode) and s != anonymous)
    assert not any(t in set(g) for t in delta)
