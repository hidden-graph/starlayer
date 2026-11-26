"""The ``srl:`` tree writes its ordered children as ordinals (``tree:ord``, ``graph/ordinals.py``), not as ``rdf:List``: what that
changes for the encoder, the decoder, ``srl_validate`` and hashing."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph, ordinals
from starlayer.graph.rdfc import rdfc10_hash
from starlayer.sparql import srl

SRLNS = "https://github.com/hidden-graph/starlayer/ns/sparql/srl#"
RULES, BODY, HEAD, IMPORTS = (ox.NamedNode(SRLNS + n) for n in ("rules", "body", "head", "imports"))
RDF_FIRST = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first")
PRE = "PREFIX : <http://example.org/>\n"

TEXT = PRE + """IMPORTS <http://example.org/lib>
DATA { :a :b :c . :d :b :e }
RULE { ?x :r ?y . ?x :s ?n } WHERE { ?x :p ?y . FILTER(?y > 1) NOT { ?x :q ?z . FILTER(?z > 2) } GROUP BY ?x { ?x :t ?o } [ ?n := COUNT(*) ] SET(?w := ?y + 1) }
RULE { ?x :u ?y } WHERE { ?x :p ?y }
"""


def _many(n: int) -> str:
    return PRE + "".join(
        f"RULE {{ ?x :h{i} ?y }} WHERE {{ ?x :p{i} ?y . ?y :q{i} ?z . FILTER(?z > {i}) NOT {{ ?x :n{i} ?w . FILTER(?w != ?y) }} SET(?v := ?z + {i}) }}\n"
        for i in range(n)
    )


def _below(graph, node):
    """The triples of ``node`` and of every blank node reachable from it."""
    seen, pending, out = set(), [node], []
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for triple in graph.triples((current, None, None)):
            out.append(triple)
            if isinstance(triple[2], ox.BlankNode):
                pending.append(triple[2])
    return out


def _tree(text: str = TEXT):
    return srl.srl_parse_to_tree(text)


def test_no_rdf_list_is_written_for_the_srl_children():
    g, root = _tree()
    lists = {s for s, _p, _o in g.triples((None, RDF_FIRST, None))}
    assert not [t for t in g.triples((None, None, None)) if t[1].value.startswith(SRLNS) and t[2] in lists]  # no srl: property holds a list
    rules = ordinals.ordered_children(g, root, RULES)
    assert len(rules) == 2 and all(child == member for child, member in rules)  # a rule is its own child: no wrapper
    imports = ordinals.ordered_children(g, root, IMPORTS)
    assert imports[0][1] == ox.NamedNode("http://example.org/lib") and imports[0][0] != imports[0][1]  # an IRI sits in a tree:Item


def test_an_empty_sequence_is_no_triples_and_round_trips():
    text = PRE + "RULE { :a :b :c } WHERE { }"
    g, root = _tree(text)
    assert not list(g.objects(root, srl.SRL["imports"])) and not list(g.objects(root, srl.SRL["data"]))
    assert srl.tree_to_ruleset(g, root).rules[0].body == []
    assert srl.srl_tree_to_text(g, root) == srl.ruleset_to_text(srl.parse_ruleset(text))


def test_the_round_trip_text_is_unchanged():
    g, root = _tree()
    assert srl.srl_tree_to_text(g, root) == srl.ruleset_to_text(srl.parse_ruleset(TEXT))


def test_edit_a_rule_body_with_the_ordinal_helpers_and_decode():
    g, root = _tree()
    rule = ordinals.ordered_items(g, root, RULES)[1]
    extra, _ = _tree(PRE + "RULE { ?x :u ?y } WHERE { ?x :q ?y }")
    new = next(iter(ordinals.ordered_items(extra, next(iter(extra.subjects(None, srl.SRL.RuleSet))), RULES)))
    new_body = ordinals.remove_at(extra, new, BODY, 0)  # a blank node child has one parent: detach it before it moves
    g.extend(_below(extra, new_body))
    ordinals.append(g, rule, BODY, new_body)
    assert srl.srl_validate(g).conforms
    assert [t.predicate for t in srl.tree_to_ruleset(g, root).rules[1].body] == [ox.NamedNode("http://example.org/p"), ox.NamedNode("http://example.org/q")]


def test_a_tie_in_a_rule_head_is_a_format_error_on_decode_and_a_violation_in_validate():
    g, root = _tree()
    rule = ordinals.ordered_items(g, root, RULES)[0]  # two head triples
    first, second = (child for child, _member in ordinals.ordered_children(g, rule, HEAD))
    g.remove((second, ordinals.ORD, None))
    g.add((second, ordinals.ORD, g.value(first, ordinals.ORD)))
    with pytest.raises(FormatError, match="same tree:ord"):
        srl.tree_to_ruleset(g, root)
    report = srl.srl_validate(g)
    assert not report.conforms and "same tree:ord" in report.report_text


@pytest.mark.parametrize("damage", ["missing", "text", "decimal", "negative", "two"])
def test_a_bad_ordinal_is_a_format_error_on_decode_and_a_violation_in_validate(damage):
    g, root = _tree()
    rule = ordinals.ordered_items(g, root, RULES)[0]
    child = ordinals.ordered_children(g, rule, HEAD)[0][0]
    g.remove((child, ordinals.ORD, None))
    new = {
        "text": [ox.Literal("first")],
        "decimal": [ox.Literal("1.5", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#decimal"))],
        "negative": [ordinals._integer(-1)],
        "two": [ordinals._integer(5), ordinals._integer(6)],
        "missing": [],
    }[damage]
    for value in new:
        g.add((child, ordinals.ORD, value))
    with pytest.raises(FormatError):
        srl.tree_to_ruleset(g, root)
    assert not srl.srl_validate(g).conforms


def test_a_blank_child_shared_by_two_parents_is_rejected_by_the_shapes():
    g, root = _tree()
    first, second = ordinals.ordered_items(g, root, RULES)
    shared = ordinals.ordered_items(g, first, HEAD)[0]
    g.add((second, HEAD, shared))  # the same head triple under a second rule: its ordinal cannot serve both
    report = srl.srl_validate(g)
    assert not report.conforms and "more than one parent" in report.report_text


def test_a_named_node_can_be_held_by_two_rule_sets_in_items():
    """The appendix B1 case at the structure level: one IRI (an IMPORTS entry) under two parents, each at its own position."""
    g, root = _tree()
    other = ox.BlankNode()
    g.add((other, ordinals.RDF_TYPE, srl.SRL.RuleSet))
    lib = ox.NamedNode("http://example.org/lib")
    ordinals.write_ordered(g, other, IMPORTS, [ox.NamedNode("http://example.org/first"), lib])
    assert ordinals.ordered_items(g, root, IMPORTS) == [lib]
    assert ordinals.ordered_items(g, other, IMPORTS)[1] == lib
    assert not [x for x in srl._results_of(srl._validate_against_shapes(g)) if "tree:ord" in x[2]]  # the shapes have nothing to say about it


def test_a_loop_through_the_ordered_children_cannot_be_decoded_or_conform():
    g, root = _tree()
    rule = ordinals.ordered_items(g, root, RULES)[0]
    negation = next(m for m in ordinals.ordered_items(g, rule, BODY) if (m, ordinals.RDF_TYPE, srl.SRL.NegationElement) in g)
    inner = srl.SRL["inner"]
    g.add((negation, inner, negation))  # the negation holds itself; it also needs a position
    g.add((negation, ordinals.ORD, ordinals._integer(9)))
    with pytest.raises(FormatError):
        srl.tree_to_ruleset(g, root)
    assert not srl.srl_validate(g).conforms


def test_a_40_rule_tree_hashes_and_a_renumbered_copy_hashes_equal():
    """With ``rdf:List`` cells RDFC-1.0 refuses a tree of about 12 generated rules; with ordinals it hashes. Removing a rule leaves a gap, so
    the hash differs from the shorter text parsed fresh until ``renumber_dense`` runs."""
    long_graph, long_root = _tree(_many(40))
    digest = rdfc10_hash(long_graph)
    assert digest == rdfc10_hash(_tree(_many(40))[0])  # two parses (other blank node labels) hash equal
    copy = StarLayerGraph(prefixes={})
    copy.extend(long_graph.triples((None, None, None)))
    assert rdfc10_hash(ordinals.renumber_dense(copy)) == digest  # already dense: nothing changes

    removed = ordinals.remove_at(long_graph, long_root, RULES, 7)
    for triple in _below(long_graph, removed):  # the rule and everything below it, so that only the sequence position differs
        long_graph.remove(triple)
    shorter = _many(40).splitlines()
    del shorter[8]  # the PREFIX line is the first
    fresh, _ = _tree("\n".join(shorter) + "\n")
    assert rdfc10_hash(long_graph) != rdfc10_hash(fresh)  # the gap is data
    ordinals.renumber_dense(long_graph)
    assert rdfc10_hash(long_graph) == rdfc10_hash(fresh)
