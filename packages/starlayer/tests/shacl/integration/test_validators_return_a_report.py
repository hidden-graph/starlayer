"""The four shape validators (``sqe_validate``, ``srl_validate``, ``manchester_validate``, ``meta_validate``) return the
``ValidationReport`` that ``validate()`` returns, not a tuple (decision 2026-11-25): the report is not iterable, so no caller can
unpack the old ``(conforms, report_graph, report_text)`` triple.
"""

import pytest
from starlayer.errors import MetaShaclError
from starlayer.graph import StarLayerGraph
from starlayer.shacl import ValidationReport, meta_validate
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_validate
from starlayer.sparql.sqe.vocab import LIMIT, PROJECTION
from starlayer.sparql.srl import srl_parse_to_tree, srl_validate
from starlayer.starontology.manchester import manchester_parse_to_tree, manchester_validate

import pyoxigraph as ox

SQE = "SELECT * WHERE { ?s ?p ?o }"
SRL = "RULE { ?x <http://e/q> ?y } WHERE { ?x <http://e/p> ?y }"
MANCH = "Prefix: : <http://e/>\nClass: :A\n"
SHAPES = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://e/> . ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:minCount 1 ."


def _sqe(broken=False):
    tree, root = sqe_parse_to_tree(SQE)
    if broken:
        tree.add((root, PROJECTION, ox.Literal("x")))  # SELECT * and a projection are exclusive
    return tree


def _srl(broken=False):
    tree, root = srl_parse_to_tree(SRL)
    if broken:
        from starlayer.sparql.srl import SRL as SRL_NS

        # no rules at all is a valid (empty) rule set, so break a rule instead: drop its required evaluation flag
        rule = next(tree.objects(root, SRL_NS["rules"]))
        tree.remove((rule, SRL_NS["ruleEvalground"], None))
    return tree


def _manchester(broken=False):
    from starlayer.starontology.manchester import MANCH as M

    tree = manchester_parse_to_tree(MANCH)
    if broken:
        (doc,) = list(tree.subjects(ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), M.Document))
        tree.remove((doc, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), M.Document))
    return tree


TREES = [(sqe_validate, _sqe), (srl_validate, _srl), (manchester_validate, _manchester)]
IDS = ["sqe", "srl", "manchester"]


@pytest.mark.parametrize(("validator", "build"), TREES, ids=IDS)
def test_a_tree_validator_returns_a_validation_report(validator, build):
    report = validator(build())
    assert isinstance(report, ValidationReport)
    assert report.conforms is True
    assert "Conforms: True" in report.report_text
    assert report.results == () and report.counts() == {"total": 0}


@pytest.mark.parametrize(("validator", "build"), TREES, ids=IDS)
def test_a_broken_tree_gives_a_non_conforming_report_with_text_and_results(validator, build):
    report = validator(build(broken=True))
    assert isinstance(report, ValidationReport)
    assert report.conforms is False
    assert report.report_text.startswith("Validation Report\nConforms: False")
    assert report.results and report.counts()["total"] == len(report.results)
    assert report.report_graph is not None


@pytest.mark.parametrize(("validator", "build"), TREES, ids=IDS)
def test_the_report_cannot_be_unpacked_or_indexed(validator, build):
    report = validator(build())
    with pytest.raises(TypeError):
        conforms, report_graph, report_text = report  # noqa: F841
    with pytest.raises(TypeError):
        report[0]
    with pytest.raises(TypeError):
        iter(report)


def test_meta_validate_returns_a_conforming_report_for_valid_shapes():
    report = meta_validate(_shapes(SHAPES.replace(" ; sh:minCount 1 .", " .")))
    assert isinstance(report, ValidationReport)
    assert report.conforms is True and "Conforms: True" in report.report_text
    assert report.results == ()
    with pytest.raises(TypeError):
        conforms, report_graph, report_text = report  # noqa: F841
    with pytest.raises(TypeError):
        report[0]


def test_meta_validate_still_raises_for_invalid_shapes_with_the_same_problems():
    with pytest.raises(MetaShaclError) as error:
        meta_validate(_shapes(SHAPES))  # sh:minCount on a node shape: a misplaced constraint
    problems = error.value.problems
    assert problems and str(error.value).startswith("The shapes graph is not valid SHACL")
    assert error.value.report_text and error.value.report_graph is not None and error.value.scope is not None


def _shapes(text):
    return StarLayerGraph().parse(data=text, format="turtle")
