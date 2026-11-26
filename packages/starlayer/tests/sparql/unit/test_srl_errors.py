"""The errors SRL raises, by cause (error scheme stage 3): no SRL error class and no ``ValueError``; a malformed tree or import text is
a ``FormatError`` (kind ``"srl"``, or ``"rdf"`` for an undefined order), a rule set that cannot be run or ordered or an import that
cannot be loaded is an ``ExecutionError`` (kinds ``"rule"`` and ``"import"``), and a bad argument is a plain ``TypeError``."""

import pytest
from starlayer.errors import ExecutionError, FormatError, StarLayerError
from starlayer.graph import StarLayerGraph, ordinals
from starlayer.sparql import srl, validate_sparql_tree
from starlayer.sparql.srl import parse_ruleset, resolve_imports

P = "PREFIX : <http://e/>\n"
LIB = "http://e/lib"
CYCLE = P + "RULE { ?x :p ?x } WHERE { ?x :q ?x NOT { ?x :r ?x } }\nRULE { ?x :r ?x } WHERE { ?x :p ?x }\n"


def test_no_srl_error_class_is_left():
    for name in ("SRLError", "SRLDecodeError", "SRLImportError", "SRLEvalError", "StratificationError", "SRLImportsNotSupportedError"):
        assert not hasattr(srl, name)
    from starlayer.sparql import srl_eval

    assert not hasattr(srl_eval, "StratificationError") and not hasattr(srl_eval, "SRLEvalError")


def test_a_tree_with_an_unknown_body_element_is_a_format_error_of_kind_srl():
    rs = parse_ruleset(P + "RULE { ?x :p ?y } WHERE { ?x :q ?y }")
    g, root = srl.ruleset_to_tree(rs)
    rule = ordinals.ordered_items(g, root, srl.SRL["rules"])[0]
    element = ordinals.ordered_items(g, rule, srl.SRL["body"])[0]
    g.remove((element, ordinals.RDF_TYPE, srl.SRL.TriplePattern))
    with pytest.raises(FormatError) as caught:
        srl.tree_to_ruleset(g, root)
    assert caught.value.kind == "srl" and caught.value.context == "srl: tree"
    assert isinstance(caught.value, StarLayerError) and not isinstance(caught.value, ValueError)


def test_a_tree_with_a_tied_ordinal_is_a_format_error_of_kind_rdf():
    rs = parse_ruleset(P + "RULE { ?x :p ?y } WHERE { ?x :q ?y . ?y :q ?x }")
    g, root = srl.ruleset_to_tree(rs)
    rule = ordinals.ordered_items(g, root, srl.SRL["rules"])[0]
    first, second = ordinals.ordered_items(g, rule, srl.SRL["body"])[:2]
    old = next(g.objects(second, ordinals.ORD))
    g.remove((second, ordinals.ORD, old))
    g.add((second, ordinals.ORD, next(g.objects(first, ordinals.ORD))))
    with pytest.raises(FormatError) as caught:
        srl.tree_to_ruleset(g, root)
    assert caught.value.kind == "rdf"


def test_an_import_the_loader_cannot_read_is_an_execution_error_of_kind_import():
    def broken(iri):
        raise OSError("no such file")

    with pytest.raises(ExecutionError, match="no such file") as caught:
        resolve_imports(parse_ruleset(P + f"IMPORTS <{LIB}>"), broken)
    assert caught.value.kind == "import" and LIB in caught.value.context


def test_an_import_that_is_not_a_rule_set_is_a_format_error_of_kind_srl():
    with pytest.raises(FormatError, match="not a valid rule set") as caught:
        resolve_imports(parse_ruleset(P + f"IMPORTS <{LIB}>"), lambda iri: "RULE { this is not srl")
    assert caught.value.kind == "srl" and LIB in caught.value.context


def test_an_import_left_unresolved_when_the_rules_run_is_an_execution_error_of_kind_import():
    rs = parse_ruleset(P + f"IMPORTS <{LIB}>\nRULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y }}")
    with pytest.raises(ExecutionError) as caught:
        rs.infer(StarLayerGraph())
    assert caught.value.kind == "import" and LIB in caught.value.context and LIB in str(caught.value)


def test_a_rule_set_that_cannot_be_ordered_is_an_execution_error_of_kind_rule():
    rs = parse_ruleset(CYCLE)
    with pytest.raises(ExecutionError) as caught:
        rs.infer(StarLayerGraph())
    assert caught.value.kind == "rule" and caught.value.context == "stratification"
    with pytest.raises(ExecutionError) as plan:
        rs.plan()
    assert plan.value.kind == "rule"


def test_srl_validate_reports_the_unorderable_rule_set_instead_of_raising():
    tree, _root = srl.ruleset_to_tree(parse_ruleset(CYCLE))
    assert not validate_sparql_tree(tree).conforms


def test_a_rule_that_breaks_the_well_formedness_conditions_is_a_format_error_of_kind_srl_when_run():
    rs = parse_ruleset(P + "RULE { ?x :p ?unbound } WHERE { ?x :q ?y }")
    with pytest.raises(FormatError) as caught:
        rs.infer(StarLayerGraph())
    assert caught.value.kind == "srl"


def test_a_data_block_with_a_literal_subject_is_a_format_error_of_kind_srl_when_run():
    rs = parse_ruleset(P + 'DATA { "a" :p :b }')
    with pytest.raises(FormatError) as caught:
        rs.infer(StarLayerGraph())
    assert caught.value.kind == "srl" and caught.value.context == "DATA"


def test_a_bad_argument_is_a_plain_type_error():
    rs = parse_ruleset(P + "RULE { ?x :p ?y } WHERE { ?x :q ?y }")
    with pytest.raises(TypeError):
        rs.infer("not a graph")
