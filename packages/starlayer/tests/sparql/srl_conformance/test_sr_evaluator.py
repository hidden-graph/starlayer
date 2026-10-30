"""An independent evaluator for SRL, written from the draft's normative pseudocode, against ``RuleSet.infer()``.

The oracle below is deliberately small and shares no code with the implementation: plain Python sets of
``(s, p, o)`` tuples, its own matcher and its own tiny expression evaluator. It follows the draft's section 6.4
(``evalRuleElements`` / ``evalRule``) and 6.5 (stratum-by-stratum evaluation to a fixpoint, ``GI``/``GE``/``G0``,
``WHERE DATA`` and ``NOT DATA`` matching only the base graph) line by line.

Scope, chosen so the oracle stays simple and obviously right: positive and negated triple patterns, FILTER and
SET over integers, ``DATA`` blocks, ``WHERE DATA`` / ``NOT DATA``, recursion (including mutual) and
stratified negation. Not covered: blank nodes in heads (run-once rules), triple terms, aggregation (undecided in
the draft), imports.

Rule sets are generated stratifiable by construction: head predicates ``:p0..:p3`` may use positively any
``:pJ`` with J <= K and negatively only ``:pJ`` with J < K or a base predicate, so stratum K = head predicate
index is a valid stratification, and the inference graph does not depend on which valid one is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rdflib import XSD, Graph, Literal, URIRef

from .corpus import PRELUDE
from .helpers import parse_ruleset

EX = "http://example.org/"

# ---------------------------------------------------------------------------------------------------------
# The oracle
# ---------------------------------------------------------------------------------------------------------
# Terms: str for IRIs (local names), int for integer literals. A pattern slot is ("v", name) or ("c", term).


class Err(Exception):
    """An expression evaluation error (the draft: an error drops the solution)."""


def match(graph, pattern):
    """graphMatch(G, TP): every solution mapping that makes ``pattern`` a triple of ``graph``."""
    solutions = []
    for triple in graph:
        mu, ok = {}, True
        for (kind, x), value in zip(pattern, triple, strict=True):
            if kind == "c":
                ok = ok and x == value
            elif x in mu:
                ok = ok and mu[x] == value
            else:
                mu[x] = value
        if ok:
            solutions.append(mu)
    return solutions


def compatible(a, b):
    return all(b[k] == v for k, v in a.items() if k in b)


def eval_expr(e, mu):
    """evalFunction(F, mu) for the small expression language the generator uses."""
    tag = e[0]
    if tag == "const":
        return e[1]
    if tag == "var":
        return mu[e[1]]
    op, left, right = e[1], eval_expr(e[2], mu), eval_expr(e[3], mu)
    if not (isinstance(left, int) and isinstance(right, int)):
        raise Err  # IRI used as a number: a type error, so the solution is dropped
    return {"+": left + right, "-": left - right, "*": left * right,
            ">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]


def eval_elements(body, seq, g, gd):
    """evalRuleElements(B, SEQ, G, GD), section 6.4."""
    for element in body:
        kind = element[0]
        out = []
        if kind == "tp":
            for mu1 in match(g, element[1]):
                for mu2 in seq:
                    if compatible(mu1, mu2):
                        out.append({**mu2, **mu1})
        elif kind == "filter":
            for mu in seq:
                try:
                    if eval_expr(element[1], mu) is True:
                        out.append(mu)
                except Err:
                    pass
        elif kind == "not":
            _, inner, evaldata = element
            for mu in seq:
                neg = eval_elements(inner, [mu], g if evaldata else gd, gd)
                if not neg:
                    out.append(mu)
        elif kind == "set":
            for mu in seq:
                try:
                    out.append({**mu, element[1]: eval_expr(element[2], mu)})
                except Err:
                    pass
        seq = out
    return seq


def eval_rule(rule, g, gd):
    """evalRule(R, G, GD): the head triples produced by one rule."""
    head, body, evaldata = rule
    seq = eval_elements(body, [{}], g if evaldata else gd, gd)
    out = set()
    for mu in seq:
        for tpl in head:
            out.add(tuple(mu[x] if kind == "v" else x for kind, x in tpl))
    return out


def oracle_infer(g0, strata, data):
    """Section 6.5: returns GI. ``strata`` is a list of rule lists, in evaluation order."""
    gi = {t for t in data if t not in g0}
    ge = set(g0) | set(data)
    for stratum in strata:
        finished = False
        while not finished:
            finished = True
            for rule in stratum:
                new = {t for t in eval_rule(rule, ge, g0) if t not in ge}
                if new:
                    finished = False
                    gi |= new
                    ge |= new
    return gi


# ---------------------------------------------------------------------------------------------------------
# Grounding the oracle in the draft, independently of the implementation
# ---------------------------------------------------------------------------------------------------------

def _tp(s, p, o):
    return tuple(("v", x[1:]) if isinstance(x, str) and x.startswith("?") else ("c", x) for x in (s, p, o))


def test_oracle_reproduces_the_drafts_worked_example():
    """Section 6.6, rules R1 to R4 (R5 creates blank nodes, outside the oracle's scope), checked against the
    triples the draft states, with no reference to the implementation."""
    base = {
        ("frontend", "type", "Component"), ("frontend", "dependsOn", "app"),
        ("app", "type", "Component"), ("app", "dependsOn", "db"), ("app", "dependsOn", "logger"),
        ("db", "type", "Component"), ("db", "hasVulnerability", "vuln1"),
        ("logger", "type", "Component"), ("vuln1", "severity", 9.1),
    }
    # severity is a decimal in the draft; the oracle's small expression language is integers, so use 9 for the test
    base = {t if t[2] != 9.1 else ("vuln1", "severity", 9) for t in base}
    r1 = ([_tp("?x", "exposedTo", "?v")], [("tp", _tp("?x", "hasVulnerability", "?v"))], True)
    r2 = ([_tp("?x", "exposedTo", "?v")],
          [("tp", _tp("?x", "dependsOn", "?y")), ("tp", _tp("?y", "exposedTo", "?v"))], True)
    r3 = ([_tp("?x", "status", "criticallyExposed")],
          [("tp", _tp("?x", "exposedTo", "?v")), ("tp", _tp("?v", "severity", "?s")),
           ("filter", ("cmp", ">=", ("var", "s"), ("const", 9)))], True)
    r4 = ([_tp("?x", "status", "safeToDeploy")],
          [("tp", _tp("?x", "type", "Component")),
           ("not", [("tp", _tp("?x", "status", "criticallyExposed"))], True)], True)
    # strata from the draft's 6.6.2: {R1, R2}, {R3}, {R4}
    inferred = oracle_infer(base, [[r1, r2], [r3], [r4]], set())
    assert inferred == {
        ("db", "exposedTo", "vuln1"), ("app", "exposedTo", "vuln1"), ("frontend", "exposedTo", "vuln1"),
        ("db", "status", "criticallyExposed"), ("app", "status", "criticallyExposed"),
        ("frontend", "status", "criticallyExposed"),
        ("logger", "status", "safeToDeploy"),
    }


def test_oracle_where_data_matches_only_the_base_graph():
    """Section 6.5 passes G0, not the growing evaluation graph, for WHERE DATA / NOT DATA."""
    base = {("a", "q", "b")}
    derive = ([_tp("?x", "r", "?y")], [("tp", _tp("?x", "q", "?y"))], True)
    # only matches the base graph, so it must NOT see the triple derived by `derive`
    from_data = ([_tp("?x", "s", "?y")], [("tp", _tp("?x", "r", "?y"))], False)
    assert oracle_infer(base, [[derive, from_data]], set()) == {("a", "r", "b")}


# ---------------------------------------------------------------------------------------------------------
# Known answers, derived by hand from the draft - deterministic, and the reason the generated test is not alone
# ---------------------------------------------------------------------------------------------------------
# A mutation check of this file found that the random test alone never notices a missing fixpoint (random rule
# sets almost never contain a recursive join that needs several passes) and needs many examples to notice
# WHERE DATA / NOT DATA mistakes. These cases pin each semantic point with an answer worked out on paper.

def _run(rule_list, base, data=()):
    """(oracle result, implementation result) for rules given as Rule objects (one stratum per head predicate)."""
    strata = [[r for r in rule_list if r.head_pred == p] for p in DERIVED]
    strata = [group for group in strata if group]
    text = PRELUDE + "\n".join(r.srl() for r in rule_list) + "\n"
    oracle = oracle_infer(set(base), [[r.oracle() for r in group] for group in strata], set(data))
    actual = _from_rdflib(parse_ruleset(text, validate=False).infer(_to_rdflib(base)))
    return oracle, actual


def _rule(head_pred, head, body, evaldata=True):
    return Rule(head_pred, head, tuple(body), evaldata)


def test_recursion_runs_to_a_fixpoint():
    """Transitive closure over the chain a-b-c-d needs three passes: it is not a single sweep over the rules."""
    base = {("a", "b0", "b"), ("b", "b0", "c"), ("c", "b0", "d")}
    seed = _rule("p0", ("x", "y"), [("tp", _tp("?x", "b0", "?y"))])
    step = _rule("p0", ("x", "z"), [("tp", _tp("?x", "p0", "?y")), ("tp", _tp("?y", "b0", "?z"))])
    expected = {("a", "p0", "b"), ("b", "p0", "c"), ("c", "p0", "d"),
                ("a", "p0", "c"), ("b", "p0", "d"), ("a", "p0", "d")}
    oracle, actual = _run([seed, step], base)
    assert oracle == expected
    assert actual == expected


def test_where_data_sees_only_the_base_graph():
    """Draft 6.5 passes G0 for WHERE DATA, so a rule that matches a *derived* predicate with it finds nothing."""
    base = {("a", "b0", "b")}
    derive = _rule("p0", ("x", "y"), [("tp", _tp("?x", "b0", "?y"))])
    from_data = _rule("p1", ("x", "y"), [("tp", _tp("?x", "p0", "?y"))], evaldata=False)
    oracle, actual = _run([derive, from_data], base)
    assert oracle == actual == {("a", "p0", "b")}


def test_not_succeeds_or_fails_depending_on_the_graph_it_looks_at():
    """NOT is evaluated after p0 is derived (stratification), so it fails; NOT DATA looks at the base graph,
    which has no p0, so it succeeds."""
    base = {("a", "b0", "b")}
    derive = _rule("p0", ("x", "y"), [("tp", _tp("?x", "b0", "?y"))])
    not_derived = _rule("p1", ("x", "y"), [("tp", _tp("?x", "b0", "?y")), ("not", [("tp", _tp("?x", "p0", "?y"))], True)])
    not_in_base = _rule("p2", ("x", "y"), [("tp", _tp("?x", "b0", "?y")), ("not", [("tp", _tp("?x", "p0", "?y"))], False)])
    oracle, actual = _run([derive, not_derived, not_in_base], base)
    assert oracle == actual == {("a", "p0", "b"), ("a", "p2", "b")}


def test_data_blocks_start_the_evaluation_graph_but_only_new_triples_are_inferred():
    """GI starts as the DATA triples not already in the base graph; GE = G0 + D."""
    base = {("a", "b0", "b")}
    data = {("a", "b0", "b"), ("c", "b0", "d")}  # the first is already in the base graph
    derive = _rule("p0", ("x", "y"), [("tp", _tp("?x", "b0", "?y"))])
    text = PRELUDE + "DATA { :a :b0 :b . :c :b0 :d . }\n" + derive.srl() + "\n"
    oracle = oracle_infer(set(base), [[derive.oracle()]], data)
    actual = _from_rdflib(parse_ruleset(text, validate=False).infer(_to_rdflib(base)))
    assert oracle == actual == {("c", "b0", "d"), ("a", "p0", "b"), ("c", "p0", "d")}


# ---------------------------------------------------------------------------------------------------------
# The generator: one structure, rendered both as SRL text and as oracle input
# ---------------------------------------------------------------------------------------------------------

BASE_PREDS = ["b0", "b1"]
DERIVED = ["p0", "p1", "p2", "p3"]
NODES = ["a", "b", "c", "d"]
VARS = ["x", "y", "z"]


@dataclass(frozen=True)
class Rule:
    head_pred: str
    head: tuple  # (subject_var, object_var)
    body: tuple  # oracle elements
    evaldata: bool

    def srl(self) -> str:
        def slot(k, v):
            return f"?{v}" if k == "v" else (f":{v}" if isinstance(v, str) else str(v))

        def expr(e):
            if e[0] == "const":
                return str(e[1])
            if e[0] == "var":
                return f"?{e[1]}"
            return f"({expr(e[2])} {e[1]} {expr(e[3])})"

        def element(el):
            if el[0] == "tp":
                s, p, o = (slot(*part) for part in el[1])
                return f"{s} {p} {o} ."
            if el[0] == "filter":
                return f"FILTER {expr(el[1])}"
            if el[0] == "set":
                return f"SET (?{el[1]} := {expr(el[2])})"
            inner = " ".join(element(i) for i in el[1])
            return f"NOT {'' if el[2] else 'DATA '}{{ {inner} }}"

        head = f"?{self.head[0]} :{self.head_pred} ?{self.head[1]} ."
        return f"RULE {{ {head} }} WHERE {'' if self.evaldata else 'DATA '}{{ {' '.join(element(e) for e in self.body)} }}"

    def oracle(self):
        head = [(("v", self.head[0]), ("c", self.head_pred), ("v", self.head[1]))]
        return head, list(self.body), self.evaldata


def _term_slot(draw_var, node):
    return st.one_of(draw_var, node)


variables = st.sampled_from(VARS).map(lambda v: ("v", v))
nodes = st.sampled_from(NODES).map(lambda n: ("c", n))
numbers = st.integers(min_value=0, max_value=4).map(lambda n: ("c", n))


@st.composite
def rules(draw):
    k = draw(st.integers(0, len(DERIVED) - 1))
    positive_preds = BASE_PREDS + DERIVED[: k + 1]
    negative_preds = BASE_PREDS + DERIVED[:k]
    evaldata = draw(st.sampled_from([True, True, True, False]))
    # First pattern: two variables, so the body binds at least one subject variable.
    first_s, first_o = draw(st.sampled_from(VARS)), draw(st.sampled_from(VARS))
    body: list = [("tp", (("v", first_s), ("c", draw(st.sampled_from(positive_preds))), ("v", first_o)))]
    subject_vars = {first_s}
    bound = {first_s, first_o}
    if draw(st.booleans()):  # a second pattern, anything goes
        s2 = draw(st.one_of(variables, nodes))
        o2 = draw(st.one_of(variables, nodes, numbers))
        body.append(("tp", (s2, ("c", draw(st.sampled_from(positive_preds))), o2)))
        bound |= {x for kind, x in (s2, o2) if kind == "v"}
        if s2[0] == "v":
            subject_vars.add(s2[1])
    names = sorted(bound)
    if draw(st.booleans()):  # a filter over bound variables
        right = draw(st.one_of(st.integers(0, 4).map(lambda n: ("const", n)), st.sampled_from(names).map(lambda n: ("var", n))))
        body.append(("filter", ("cmp", draw(st.sampled_from([">", "<", ">=", "<="])), ("var", draw(st.sampled_from(names))), right)))
    if draw(st.booleans()):  # a negation over variables already bound; only lower strata, so it stratifies
        inner = [("tp", (("v", draw(st.sampled_from(names))), ("c", draw(st.sampled_from(negative_preds))), ("v", draw(st.sampled_from(names)))))]
        body.append(("not", inner, draw(st.booleans())))
    recursive = any(e[0] == "tp" and e[1][1] == ("c", DERIVED[k]) for e in body)
    if draw(st.booleans()) and not recursive:  # SET only where it cannot feed itself, so evaluation terminates
        body.append(("set", "w", ("arith", "+", ("var", draw(st.sampled_from(names))), ("const", draw(st.integers(0, 3))))))
        names = [*names, "w"]
    # The head subject is a variable bound in a subject position, so it is never a number (a literal subject is not RDF).
    head = (draw(st.sampled_from(sorted(subject_vars))), draw(st.sampled_from(names)))
    return Rule(DERIVED[k], head, tuple(body), evaldata)


@st.composite
def chain_rules(draw):
    """A seed rule plus a recursive join (transitive-closure shape), so evaluation needs several passes."""
    k = draw(st.integers(0, len(DERIVED) - 1))
    base_pred = draw(st.sampled_from(BASE_PREDS))
    head_pred = DERIVED[k]
    seed = Rule(head_pred, ("x", "y"), (("tp", (("v", "x"), ("c", base_pred), ("v", "y"))),), True)
    left_recursive = draw(st.booleans())
    first, second = ((head_pred, base_pred) if left_recursive else (base_pred, head_pred))
    step = Rule(head_pred, ("x", "z"), (
        ("tp", (("v", "x"), ("c", first), ("v", "y"))),
        ("tp", (("v", "y"), ("c", second), ("v", "z"))),
    ), True)
    return [seed, step]


rule_sets = st.lists(st.one_of(rules().map(lambda r: [r]), chain_rules()), min_size=1, max_size=3).map(
    lambda groups: [r for group in groups for r in group]
)

base_triples = st.lists(
    st.tuples(st.sampled_from(NODES), st.sampled_from(BASE_PREDS), st.one_of(st.sampled_from(NODES), st.integers(0, 4))),
    min_size=0, max_size=8, unique=True,
)
data_triples = st.lists(
    st.tuples(st.sampled_from(NODES), st.sampled_from(BASE_PREDS + DERIVED[:1]), st.sampled_from(NODES)),
    min_size=0, max_size=2, unique=True,
)


def _to_rdflib(triples) -> Graph:
    g = Graph()
    for s, p, o in triples:
        g.add((URIRef(EX + s), URIRef(EX + p), Literal(o, datatype=XSD.integer) if isinstance(o, int) else URIRef(EX + o)))
    return g


def _from_rdflib(graph: Graph) -> set:
    def term(t):
        return int(t) if isinstance(t, Literal) else str(t)[len(EX):]

    return {(term(s), term(p), term(o)) for s, p, o in graph}


SETTINGS = settings(
    max_examples=int(os.environ.get("SRL_HYPOTHESIS_EXAMPLES", "150")),
    deadline=None,
    derandomize=not os.environ.get("SRL_HYPOTHESIS_HUNT"),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.mark.srl_conformance
@given(rule_sets, base_triples, data_triples)
@SETTINGS
def test_infer_matches_the_independent_evaluator(rule_list, base, data):
    strata = [[r for r in rule_list if r.head_pred == p] for p in DERIVED]
    strata = [group for group in strata if group]

    data_text = ("DATA { " + " ".join(f":{s} :{p} :{o} ." for s, p, o in data) + " }\n") if data else ""
    text = PRELUDE + data_text + "\n".join(r.srl() for r in rule_list) + "\n"

    expected = oracle_infer(set(base), [[r.oracle() for r in group] for group in strata], set(data))
    actual = _from_rdflib(parse_ruleset(text, validate=False).infer(_to_rdflib(base)))
    assert actual == expected, (
        f"rule set:\n{text}\nbase: {sorted(base, key=str)}\n"
        f"expected - actual: {sorted(expected - actual, key=str)}\nactual - expected: {sorted(actual - expected, key=str)}"
    )
