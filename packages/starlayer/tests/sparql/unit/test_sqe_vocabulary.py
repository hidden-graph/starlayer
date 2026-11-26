"""The end-state vocabulary of the ``sqe:`` / ``spexpr:`` trees (docs/working/sqe-vocabulary-table-2026-11-25.md): every renamed family is
written by the encoder, read back to the same text, accepted by the shapes, and no old name is left in the source."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.sparql.expr_families import _EXPR_NODE_FAMILY
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text, sqe_validate
from starlayer.sparql.sqe.shapes import _validate_shapes
from starlayer.sparql.vocab import SPEXPR, SQE

RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
PACKAGE = Path(__file__).resolve().parents[3] / "starlayer"
LIBRARY = Path(__file__).resolve().parents[5] / "tools" / "kg" / "codekg" / "curated" / "query-library.ttl"

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_HEAD = "PREFIX ex: <http://example.org/> SELECT * WHERE { ?x ex:p ?y . ?z ex:q ?w . FILTER(%s) }"

_SKIP_FAMILIES = {"Unary", "Relational", "Conditional", "Arithmetic", "FunctionCall"}


def _call(name: str, family: str) -> str:
    return {
        "ZeroArg": f"{name}()",
        "OneArg": f"{name}(?x)",
        "OptionalOneArg": f"{name}(?x)",
        "TwoArg": f"{name}(?x, ?y)",
        "ThreeArg": f"{name}(?x, ?y, ?z)",
        "VariadicArg": f"{name}(?x, ?y)",
        "StrLangDir": f'{name}("a", "en", "ltr")',
        "Regex": f'{name}(?x, "a")',
        "Replace": f'{name}(?x, "a", "b")',
        "Substr": f"{name}(?x, 1)",
    }[family]


def _types(tree) -> set[str]:
    return {o.value for _s, _p, o in tree.triples((None, RDF_TYPE, None))}


def _tree(text: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sqe_parse_to_tree(text)


BUILTINS = sorted(name for name, family in _EXPR_NODE_FAMILY.items() if family not in _SKIP_FAMILIES)


@pytest.mark.parametrize("name", BUILTINS)
def test_a_built_in_is_typed_as_it_is_written_and_renders_back(name):
    text = _HEAD % _call(name, _EXPR_NODE_FAMILY[name])
    tree, root = _tree(text)
    assert SPEXPR[name].value in _types(tree)
    assert f"spexpr#Builtin_{name}" not in "".join(_types(tree))
    again = sqe_tree_to_text(tree, root)
    assert _call(name, _EXPR_NODE_FAMILY[name]) in again
    assert _validate_shapes(tree).conforms


@pytest.mark.parametrize("name", ["COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE", "GROUP_CONCAT"])
@pytest.mark.parametrize("distinct", [False, True])
def test_an_aggregate_is_typed_as_written_with_expr_and_a_boolean_distinct(name, distinct):
    inner = "DISTINCT ?o" if distinct else "?o"
    tree, root = _tree(f"SELECT ({name}({inner}) AS ?c) WHERE {{ ?s ?p ?o }}")
    aggregate = next(s for s, _p, _o in tree.triples((None, RDF_TYPE, SPEXPR[name])))
    assert tree.value(aggregate, SPEXPR.expr) == ox.Literal("o", datatype=ox.NamedNode(SPEXPR.Variable.value))
    assert list(tree.objects(aggregate, SPEXPR.vars)) == []
    flag = list(tree.objects(aggregate, SPEXPR.distinct))
    assert flag == ([ox.Literal("true", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))] if distinct else [])
    assert f"{name}({inner})" in sqe_tree_to_text(tree, root)
    assert _validate_shapes(tree).conforms


def test_count_star_keeps_the_marker_in_expr():
    tree, root = _tree("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
    aggregate = next(s for s, _p, _o in tree.triples((None, RDF_TYPE, SPEXPR.COUNT)))
    assert tree.value(aggregate, SPEXPR.expr).value == "*"
    assert "COUNT(*)" in sqe_tree_to_text(tree, root)


def test_exists_and_not_exists_are_two_classes_and_there_is_no_negated_flag():
    tree, root = _tree("SELECT * WHERE { ?s ?p ?o FILTER EXISTS { ?o ?q ?r } FILTER NOT EXISTS { ?o ?q ?s } }")
    assert {SQE.Exists.value, SQE.NotExists.value} <= _types(tree)
    assert not list(tree.triples((None, SQE.negated, None)))
    text = sqe_tree_to_text(tree, root)
    assert "FILTER(EXISTS {" in text and "FILTER(NOT EXISTS {" in text
    assert _validate_shapes(tree).conforms


def test_the_prologue_uses_prefix_decl():
    tree, root = _tree("PREFIX ex: <http://example.org/> BASE <http://b/> SELECT * WHERE { ?s ex:p ?o }")
    assert SQE.PrefixDecl.value in _types(tree)
    assert list(tree.objects(root, SQE.prefixDecl))
    assert SQE.PrefixBinding.value not in _types(tree)
    assert "PREFIX ex: <http://example.org/>" in sqe_tree_to_text(tree, root)
    assert _validate_shapes(tree).conforms


@pytest.mark.parametrize(
    "path,cls",
    [("ex:a/ex:b", "PathSequence"), ("ex:a|ex:b", "PathAlternative"), ("^ex:a", "PathInverse"), ("ex:a*", "PathElt"), ("!(ex:a|ex:b)", "PathNegatedPropertySet")],
)
def test_the_five_path_classes(path, cls):
    tree, root = _tree(f"PREFIX ex: <http://example.org/> SELECT * WHERE {{ ?s {path} ?o }}")
    assert SPEXPR[cls].value in _types(tree)
    assert path in sqe_tree_to_text(tree, root).replace("<http://example.org/", "ex:").replace(">", "")
    assert _validate_shapes(tree).conforms


def test_a_function_call_has_args_and_a_boolean_distinct():
    tree, root = _tree("PREFIX ex: <http://example.org/> SELECT * WHERE { ?s ?p ?o FILTER(ex:f(DISTINCT ?o, 1)) FILTER(ex:g(?o)) }")
    calls = [s for s, _p, _o in tree.triples((None, RDF_TYPE, SPEXPR.FunctionCall))]
    assert len(calls) == 2
    assert all(list(tree.objects(c, SPEXPR.args)) for c in calls)
    assert sorted(len(list(tree.objects(c, SPEXPR.distinct))) for c in calls) == [0, 1]
    assert all((c, SPEXPR.expr, None) not in tree for c in calls)
    again = sqe_tree_to_text(tree, root)
    assert "ex:f(DISTINCT ?o, 1)" in again and "ex:g(?o)" in again


@pytest.mark.parametrize("function", ["CONCAT", "COALESCE"])
def test_the_variadic_built_ins_use_args(function):
    tree, root = _tree(f'SELECT * WHERE {{ ?s ?p ?o FILTER({function}(?o, "a") = "a") }}')
    call = next(s for s, _p, _o in tree.triples((None, RDF_TYPE, SPEXPR[function])))
    assert list(tree.objects(call, SPEXPR.args)) and not list(tree.objects(call, SPEXPR.arg))
    assert f'{function}(?o, "a")' in sqe_tree_to_text(tree, root)


def test_undef_is_declared_in_the_ontology():
    ontology = starontology.get_ontology_graph("sqe_owl")
    assert (SQE.undef, RDF_TYPE, ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#Resource")) in ontology


def test_every_built_in_class_is_declared_in_the_ontology():
    ontology = starontology.get_ontology_graph("spexpr_owl")
    declared = {s for s, _p, _o in ontology.triples((None, None, None))}
    missing = [n for n in BUILTINS if SPEXPR[n] not in declared]
    assert not missing
    for name in ("COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE", "GROUP_CONCAT", "FunctionCall"):
        assert SPEXPR[name] in declared
    assert SQE.NotExists in {s for s, _p, _o in starontology.get_ontology_graph("sqe_owl").triples((None, None, None))}


OLD_NAMES = re.compile(
    r"Builtin_|Aggregate_|PrefixBinding|prologuePrefix|\bSequencePath|\bAlternativePath|\bInvPath|\bMulPath|\bNegatedPath"
    r"|FunctionExpression|TrueFilter|ExistsExpression|spexpr:Function\b|spexpr:vars|sqe:negated|\bNEGATED\b|PREFIX_BINDING"
)


def _sources() -> list[Path]:
    files = list((PACKAGE / "sparql").rglob("*.py"))
    for vocabulary in ("sqe", "spexpr", "srl", "tree"):
        files += list((PACKAGE / "starontology" / vocabulary).glob("*.ttl"))
    return files


def test_no_old_name_is_left_in_the_sources():
    found = [f"{f.relative_to(PACKAGE)}:{n}: {line.strip()[:80]}" for f in _sources() for n, line in enumerate(f.read_text().splitlines(), 1) if OLD_NAMES.search(line)]
    assert not found, "\n".join(found)


def test_no_old_name_is_left_in_the_query_library():
    assert not OLD_NAMES.findall(LIBRARY.read_text())


def test_the_vocabulary_files_declare_no_dead_term():
    text = "".join(f.read_text() for f in (PACKAGE / "starontology").glob("s*/*.ttl"))
    for dead in ("spexpr:graph", "spexpr:_ExistsExprBodyShape", "DistinctMarkerShape"):
        assert dead not in text


def test_a_hand_built_tree_with_the_new_names_validates_and_renders():
    tree, root = _tree("PREFIX ex: <http://example.org/> SELECT ?s WHERE { ?s ex:p ?o FILTER(isIRI(?o)) }")
    report = sqe_validate(tree)
    assert report.conforms
