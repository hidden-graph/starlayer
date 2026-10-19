"""Property-based probing of sqe with Hypothesis.

Random but valid SPARQL queries are generated over the synthetic dataset's
vocabulary (the generator tracks which variables are bound, so every query is
well formed), and each is held to these properties:

1. it parses to an sqe tree that passes the sqe shapes and holds no salg: terms;
2. the text rendered from the tree is stable: parsing it again and rendering
   again gives the same text;
3. the regenerated text returns the same rows as the original query on a
   StarLayerDataset (this is the property that catches a silently dropped clause);
4. the decoded ``Query`` object also decodes without error.

Opt-in (``pytest --sqe-coverage``). The number of examples per property comes
from ``STARLAYER_SQE_FUZZ_EXAMPLES`` (default 60); Hypothesis shrinks any
failure to the smallest query that still fails and prints it.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_query, sqe_tree_to_text
from tests.sparql.sqe_coverage.test_sqe_features import P, _rows, build_dataset
from tests.sparql.sqe_coverage.test_w3c_through_sqe import assert_no_salg_terms

pytestmark = pytest.mark.sqe_coverage

_EXAMPLES = int(os.environ.get("STARLAYER_SQE_FUZZ_EXAMPLES", "60"))
_SETTINGS = settings(
    max_examples=_EXAMPLES,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    print_blob=True,
)

_DATA = build_dataset()

# repeated entries weight the choice toward patterns that actually match the data
# Variables have roles so generated queries join on the data and return rows: an "iri" variable is a
# subject (or an IRI object), a "num" variable holds an ex:num value, a "str" variable an ex:name value.
_ROLE_VARS = {
    "iri": ["?s1", "?s2"],
    "num": ["?n1", "?n2", "?n3"],
    "str": ["?t1", "?t2"],
}
# (predicate, role of its object)
_PATTERNS = [("ex:num", "num"), ("ex:num", "num"), ("ex:name", "str"), ("ex:name", "str"), ("ex:kind", "iri"), ("ex:next", "iri")]
_CONSTANTS = {
    "iri": ["ex:even", "ex:odd", "ex:s1", "ex:s4"],
    "num": ["0", "1", "3", "5", "2.5"],
    "str": ["'name0'", "'name1'", "'x'"],
}


# --------------------------------------------------------------------------
# expressions, typed by role (over variables that are already bound)

def _numeric(scope: dict, cross: bool = True):
    nums = [v for v, role in scope.items() if role == "num"]
    leaf = st.one_of(*( [st.sampled_from(nums)] if nums else []), st.integers(-2, 9).map(str))

    def extend(inner):
        binary = st.tuples(inner, st.sampled_from(["+", "-", "*", "/"]), inner).map(lambda t: f"({t[0]} {t[1]} {t[2]})")
        unary = st.tuples(st.sampled_from(["-", "+"]), inner).map(lambda t: f"({t[0]}({t[1]}))")
        absolute = inner.map(lambda e: f"ABS({e})")
        length = _string(scope, 1).map(lambda e: f"STRLEN({e})")
        coalesce = st.lists(inner, min_size=1, max_size=3).map(lambda xs: f"COALESCE({', '.join(xs)})")
        rounding = st.tuples(st.sampled_from(["CEIL", "FLOOR", "ROUND"]), inner).map(lambda t: f"{t[0]}({t[1]})")
        options = [binary, unary, absolute, length, coalesce, rounding]
        if cross:  # a conditional reaches back into boolean expressions, so it is only offered once
            options.append(
                st.tuples(_boolean(scope, 1, cross=False), inner, inner).map(lambda t: f"IF({t[0]}, {t[1]}, {t[2]})")
            )
        return st.one_of(*options)

    return st.recursive(leaf, extend, max_leaves=4)


def _string(scope: dict, leaves: int = 3):
    strs = [v for v, role in scope.items() if role == "str"]
    leaf = st.one_of(*( [st.sampled_from(strs)] if strs else []), st.sampled_from(["'x'", "'name1'", "'ame'"]))

    def extend(inner):
        case = st.tuples(st.sampled_from(["UCASE", "LCASE", "STR"]), inner).map(lambda t: f"{t[0]}({t[1]})")
        concat = st.tuples(inner, inner).map(lambda t: f"CONCAT({t[0]}, {t[1]})")
        part = st.tuples(st.sampled_from(["STRBEFORE", "STRAFTER"]), inner, st.sampled_from(["'e'", "'a'"])).map(
            lambda t: f"{t[0]}({t[1]}, {t[2]})"
        )
        substring = st.tuples(inner, st.integers(1, 3)).map(lambda t: f"SUBSTR({t[0]}, {t[1]})")
        replace = st.tuples(inner, st.sampled_from(["'', ''", "'name', 'N'", "'a', 'b'"])).map(lambda t: f"REPLACE({t[0]}, {t[1]})")
        return st.one_of(case, concat, part, substring, replace)

    return st.recursive(leaf, extend, max_leaves=leaves)


def _boolean(scope: dict, leaves: int = 4, cross: bool = True):
    iris = [v for v, role in scope.items() if role == "iri"]
    anything = list(scope)

    def atoms():
        compare = st.tuples(_numeric(scope, cross), st.sampled_from(["=", "!=", "<", ">", "<=", ">="]), _numeric(scope, cross)).map(
            lambda t: f"({t[0]} {t[1]} {t[2]})"
        )
        text = st.tuples(st.sampled_from(["CONTAINS", "STRSTARTS", "STRENDS"]), _string(scope, 2), _string(scope, 1)).map(
            lambda t: f"{t[0]}({t[1]}, {t[2]})"
        )
        regex = st.tuples(_string(scope, 2), st.sampled_from(["'^n'", "'1$'", "'a|b'"]), st.sampled_from(["", ", 'i'"])).map(
            lambda t: f"REGEX({t[0]}, {t[1]}{t[2]})"
        )
        membership = st.tuples(_numeric(scope, cross), st.lists(st.integers(0, 6).map(str), min_size=1, max_size=3), st.booleans()).map(
            lambda t: f"({t[0]} {'NOT IN' if t[2] else 'IN'} ({', '.join(t[1])}))"
        )
        options = [compare, text, regex, membership]
        if anything:
            options.append(st.sampled_from(anything).map(lambda v: f"BOUND({v})"))
            options.append(st.tuples(st.sampled_from(["isIRI", "isLiteral", "isNumeric", "isBlank"]), st.sampled_from(anything)).map(
                lambda t: f"{t[0]}({t[1]})"
            ))
        if iris:
            options.append(st.tuples(st.sampled_from(iris), st.sampled_from(["ex:s1", "ex:s2", "ex:even"])).map(
                lambda t: f"sameTerm({t[0]}, {t[1]})"
            ))
        return st.one_of(*options)

    def extend(inner):
        logic = st.tuples(inner, st.sampled_from(["&&", "||"]), inner).map(lambda t: f"({t[0]} {t[1]} {t[2]})")
        negate = inner.map(lambda e: f"!({e})")
        return st.one_of(logic, negate)

    return st.recursive(atoms(), extend, max_leaves=leaves)


# --------------------------------------------------------------------------
# graph patterns, tracking the variables (and their roles) each element binds

@st.composite
def _triple(draw, scope: dict):
    predicate, role = draw(st.sampled_from(_PATTERNS))
    subject = draw(st.sampled_from(_ROLE_VARS["iri"][:1] * 3 + _ROLE_VARS["iri"] + ["ex:s0", "ex:s1"]))
    path = draw(st.sampled_from(["", "", "", "+", "*", "?"])) if predicate == "ex:next" else ""
    obj = draw(st.sampled_from(_ROLE_VARS[role] * 3 + _CONSTANTS[role]))
    new = {}
    for term, term_role in ((subject, "iri"), (obj, role)):
        if term.startswith("?"):
            new[term] = term_role
    return f"{subject} {predicate}{path} {obj} .", new


@st.composite
def _group(draw, depth: int, bound: dict | None = None):
    """A group graph pattern; returns (text, variables it binds, all variables in scope)."""
    scope = dict(bound or {})
    parts: list[str] = []
    bound_here: dict = {}

    def add_vars(new: dict):
        for var, role in new.items():
            scope.setdefault(var, role)
            bound_here.setdefault(var, role)

    # the first triple always has a variable subject, so every group binds at least one variable
    predicate, role = draw(st.sampled_from(_PATTERNS))
    obj = draw(st.sampled_from(_ROLE_VARS[role] * 3 + _CONSTANTS[role]))
    parts.append(f"?s1 {predicate} {obj} .")
    add_vars({"?s1": "iri", **({obj: role} if obj.startswith("?") else {})})
    for _ in range(draw(st.integers(0, 2))):
        text, new = draw(_triple(scope))
        parts.append(text)
        add_vars(new)

    elements = ["filter", "filter", "optional", "union", "minus", "bind", "values", "exists", "graph"]
    if depth <= 0:
        elements = ["filter", "filter", "bind", "values"]
    for _ in range(draw(st.integers(0, 3))):
        kind = draw(st.sampled_from(elements))
        if kind == "filter":
            parts.append(f"FILTER({draw(_boolean(scope))})")
        elif kind == "bind":
            numeric = draw(st.booleans())
            fresh = f"?b{len(scope)}" if numeric else f"?z{len(scope)}"
            expression = draw(_numeric(scope)) if numeric else draw(_string(scope))
            parts.append(f"BIND({expression} AS {fresh})")
            add_vars({fresh: "num" if numeric else "str"})
        elif kind == "values":
            var = draw(st.sampled_from(_ROLE_VARS["num"]))
            cells = draw(st.lists(st.sampled_from(["1", "2", "3", "UNDEF"]), min_size=1, max_size=3))
            parts.append(f"VALUES {var} {{ {' '.join(cells)} }}")
            add_vars({var: "num"})
        elif kind == "optional":
            text, inner, _ = draw(_group(depth - 1, scope))
            parts.append(f"OPTIONAL {text}")
            add_vars(inner)
        elif kind == "union":
            # the outer scope is passed down on purpose: a filter in a nested group must NOT see the outer
            # variables (SPARQL evaluates the group alone), and the Oxigraph comparison checks that
            left, lvars, _ = draw(_group(depth - 1, scope))
            right, rvars, _ = draw(_group(depth - 1, scope))
            parts.append(f"{left} UNION {right}")
            add_vars({**lvars, **rvars})
        elif kind == "minus":
            text, _inner, _ = draw(_group(depth - 1, scope))
            parts.append(f"MINUS {text}")
        elif kind == "exists":
            text, _inner, _ = draw(_group(depth - 1, scope))
            parts.append(f"FILTER {'NOT ' if draw(st.booleans()) else ''}EXISTS {text}")
        elif kind == "graph":
            graph_term = draw(st.sampled_from(["ex:g1", "ex:g2", "?g"]))
            text, inner, _ = draw(_group(depth - 1, scope))
            parts.append(f"GRAPH {graph_term} {text}")
            add_vars({**inner, **({graph_term: "iri"} if graph_term.startswith("?") else {})})
    return "{ " + " ".join(parts) + " }", bound_here, scope


# --------------------------------------------------------------------------
# whole queries

@st.composite
def _select_query(draw):
    where, bound, scope = draw(_group(2))
    variables = sorted(bound)
    form = draw(st.sampled_from(["plain", "plain", "star", "aggregate", "alias", "subselect"]))
    modifiers = ""
    if form == "aggregate":
        group_var = draw(st.sampled_from(variables))
        numeric = [v for v in variables if bound[v] == "num"]
        agg_var = draw(st.sampled_from(numeric or variables))
        function = draw(st.sampled_from(["COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE"]))
        distinct = draw(st.sampled_from(["", "DISTINCT "])) if function != "SAMPLE" else ""
        projection = f"{group_var} ({function}({distinct}{agg_var}) AS ?agg)"
        tail = f" GROUP BY {group_var}"
        if draw(st.booleans()):
            tail += f" HAVING ({function}({agg_var}) >= 0)"
        order_vars = [group_var, "?agg"]
        text_where = f"WHERE {where}{tail}"
    elif form == "alias":
        chosen = draw(st.lists(st.sampled_from(variables), min_size=1, max_size=2, unique=True))
        projection = " ".join(chosen) + f" ({draw(_numeric(scope))} AS ?al)"
        order_vars = chosen
        text_where = f"WHERE {where}"
    elif form == "subselect":
        inner = draw(st.sampled_from(variables))
        projection = inner
        order_vars = [inner]
        text_where = f"WHERE {{ {{ SELECT {inner} WHERE {where} }} }}"
    elif form == "star":
        projection = "*"
        order_vars = variables
        text_where = f"WHERE {where}"
    else:
        chosen = draw(st.lists(st.sampled_from(variables), min_size=1, max_size=3, unique=True))
        projection = " ".join(chosen)
        order_vars = chosen
        text_where = f"WHERE {where}"

    distinct = draw(st.sampled_from(["", "DISTINCT ", "REDUCED "])) if form != "aggregate" else ""
    if draw(st.booleans()):
        keys = [f"DESC({v})" if draw(st.booleans()) else v for v in order_vars]
        modifiers += " ORDER BY " + " ".join(keys)
        if draw(st.booleans()):
            modifiers += f" LIMIT {draw(st.integers(0, 6))}"
            if draw(st.booleans()):
                modifiers += f" OFFSET {draw(st.integers(0, 4))}"
    return f"{P}SELECT {distinct}{projection} {text_where}{modifiers}"


@st.composite
def _ask_query(draw):
    where, _bound, _scope = draw(_group(2))
    return f"{P}ASK {where}"


@st.composite
def _construct_query(draw):
    where, bound, _scope = draw(_group(1))
    variables = sorted(bound)
    subject = draw(st.sampled_from(variables))
    obj = draw(st.sampled_from(variables))
    return f"{P}CONSTRUCT {{ {subject} ex:out {obj} }} WHERE {where}"


_QUERIES = st.one_of(_select_query(), _ask_query(), _construct_query())


def _canonical_rows(query):
    """The rows (sorted unless ordered) or, when the engine itself rejects the query at run time (for example
    SUM over strings), the error's class - a regenerated query has to fail in the same way."""
    try:
        rows = _rows(_DATA, query)
    except Exception as error:  # noqa: BLE001 - the error class is the outcome being compared
        event(f"engine error: {type(error).__name__}")
        return ("error", type(error).__name__)
    event("rows: " + ("none" if not rows else "some") if isinstance(rows, list) else f"ask: {rows}")
    return sorted(rows, key=repr) if isinstance(rows, list) else rows


# --------------------------------------------------------------------------
# properties

@_SETTINGS
@given(query=_QUERIES)
def test_tree_is_valid_text_is_stable_and_rows_match(query):
    tree, root = sqe_parse_to_tree(query)  # validates against the sqe shapes
    assert_no_salg_terms(tree)

    text = sqe_tree_to_text(tree, root)
    tree2, root2 = sqe_parse_to_tree(text)
    assert sqe_tree_to_text(tree2, root2) == text, "rendered text is not stable"

    assert _canonical_rows(text) == _canonical_rows(query), f"rows differ for the regenerated text:\n{text}"
    sqe_tree_to_query(tree, root)


@_SETTINGS
@given(query=_QUERIES)
def test_decoded_query_object_returns_the_same_rows(query):
    tree, root = sqe_parse_to_tree(query)
    decoded = sqe_tree_to_query(tree, root)
    assert _canonical_rows(decoded) == _canonical_rows(query), "decoded Query differs from the original"
