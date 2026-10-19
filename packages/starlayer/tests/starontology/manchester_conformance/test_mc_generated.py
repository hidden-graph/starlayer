"""Grammar-driven property tests (Hypothesis): random valid Manchester documents, tree invariants checked.

Hand-written cases find the gaps someone thought to probe; a generator finds the combinations nobody did
(a restriction inside a negation inside a union inside a ``that`` list...). Documents are built from the
W3C productions the parser *supports today*; constructs recorded as findings in ``known_failures.py``
are deliberately excluded here and enter the generator as their gaps are closed.

Invariants per generated document: the parse succeeds; the tree validates; ``tree -> OWL`` is isomorphic
to compiling the text directly; the rendered text re-parses to the same OWL; a second tree pass is stable.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from starlayer.graph.compare import isomorphic
from starlayer.starontology.manchester import (
    manchester_parse_to_tree,
    manchester_tree_to_owl,
    manchester_tree_to_text,
    manchester_validate,
)

from .corpus import PRELUDE
from .helpers import parse_to_graph, to_graph

CLASSES = ["A", "B", "C", "D"]
OBJ_PROPS = ["p", "q", "r"]
DATA_PROPS = ["d", "e"]
INDIVIDUALS = ["i", "j", "k"]
DATATYPES = ["xsd:integer", "xsd:string", "xsd:decimal", "xsd:boolean"]

names = st.sampled_from(CLASSES)
obj_prop = st.one_of(st.sampled_from(OBJ_PROPS), st.sampled_from(OBJ_PROPS).map(lambda p: f"inverse {p}"))
small_int = st.integers(min_value=0, max_value=5)


def class_expr(max_depth: int = 3):
    atoms = st.one_of(
        names,
        st.lists(st.sampled_from(INDIVIDUALS), min_size=1, max_size=3, unique=True).map(lambda xs: "{" + ", ".join(xs) + "}"),
    )

    def extend(child):
        paren = child.map(lambda c: f"({c})")
        return st.one_of(
            st.tuples(child, child).map(lambda t: f"({t[0]}) and ({t[1]})"),
            st.tuples(child, child).map(lambda t: f"({t[0]}) or ({t[1]})"),
            child.map(lambda c: f"not ({c})"),
            st.tuples(obj_prop, paren).map(lambda t: f"{t[0]} some {t[1]}"),
            st.tuples(obj_prop, paren).map(lambda t: f"{t[0]} only {t[1]}"),
            st.tuples(obj_prop, st.sampled_from(INDIVIDUALS)).map(lambda t: f"{t[0]} value {t[1]}"),
            obj_prop.map(lambda p: f"{p} Self"),
            st.tuples(obj_prop, st.sampled_from(["min", "max", "exactly"]), small_int).map(lambda t: f"{t[0]} {t[1]} {t[2]}"),
            st.tuples(obj_prop, st.sampled_from(["min", "max", "exactly"]), small_int, paren).map(
                lambda t: f"{t[0]} {t[1]} {t[2]} {t[3]}"
            ),
            # A restriction's filler is one dataPrimary, so a compound data range needs parentheses.
            st.tuples(st.sampled_from(DATA_PROPS), st.sampled_from(["some", "only"]), data_range()).map(
                lambda t: f"{t[0]} {t[1]} ({t[2]})"
            ),
            st.tuples(st.sampled_from(DATA_PROPS), st.sampled_from(["min", "max", "exactly"]), small_int, data_range()).map(
                lambda t: f"{t[0]} {t[1]} {t[2]} ({t[3]})"
            ),
            st.tuples(st.sampled_from(DATA_PROPS), small_int).map(lambda t: f"{t[0]} value {t[1]}"),
        )

    return st.recursive(atoms, extend, max_leaves=max_depth * 2)


def data_range():
    atom = st.one_of(
        st.sampled_from(DATATYPES),
        st.sampled_from(["xsd:integer[>= 1]", "xsd:integer[>= 0, <= 9]", "xsd:string[minLength 1]", "xsd:decimal[> 0.5]"]),
        st.lists(small_int, min_size=1, max_size=3, unique=True).map(lambda xs: "{" + ", ".join(map(str, xs)) + "}"),
    )
    return st.recursive(
        atom,
        lambda child: st.one_of(
            st.tuples(child, child).map(lambda t: f"({t[0]}) or ({t[1]})"),
            st.tuples(child, child).map(lambda t: f"({t[0]}) and ({t[1]})"),
            child.map(lambda c: f"not ({c})"),
        ),
        max_leaves=4,
    )


node_id = st.sampled_from(["_:b1", "_:b2", "_:anon"])

literal = st.one_of(
    st.integers(min_value=-9, max_value=99).map(str),
    st.integers(min_value=0, max_value=9).map(lambda n: f"+{n}"),
    st.sampled_from(["1.5", "-2.25", "+0.5"]),
    st.sampled_from(["2f", ".5f", "1.5e3f", "-3.25f", "2E-2F"]),
    st.sampled_from(['"plain"', '"with \\"quote\\" and \\\\ slash"', '"hello"@en', '"5"^^xsd:integer', '"x"^^string']),
)


def annotation_prefix():
    """``Annotations: ...`` (possibly nested) followed by a space, or nothing."""
    plain = st.sampled_from(['note "a"', 'note2 "b"', "note 5"])
    nested = st.tuples(plain, plain).map(lambda t: f"Annotations: {t[0]} {t[1]}")
    return st.one_of(
        st.just(""),
        plain.map(lambda a: f"Annotations: {a} "),
        nested.map(lambda a: f"Annotations: {a} "),
    )


def axiom_text():
    cls = class_expr()
    return st.one_of(
        st.tuples(names, st.sampled_from(["SubClassOf:", "EquivalentTo:", "DisjointWith:"]), cls).map(
            lambda t: f"Class: {t[0]}\n  {t[1]} {t[2]}\n"
        ),
        st.tuples(st.sampled_from(INDIVIDUALS), cls).map(lambda t: f"Individual: {t[0]}\n  Types: {t[1]}\n"),
        st.tuples(st.sampled_from(OBJ_PROPS), st.sampled_from(["Domain:", "Range:"]), cls).map(
            lambda t: f"ObjectProperty: {t[0]}\n  {t[1]} {t[2]}\n"
        ),
        st.tuples(st.sampled_from(DATA_PROPS), data_range()).map(lambda t: f"DataProperty: {t[0]}\n  Range: {t[1]}\n"),
        st.lists(cls, min_size=2, max_size=3).map(lambda xs: "DisjointClasses: " + ", ".join(xs) + "\n"),
        st.lists(cls, min_size=2, max_size=3).map(lambda xs: "EquivalentClasses: " + ", ".join(xs) + "\n"),
        # annotations: on one list item, nested, and on a whole top-level axiom
        st.tuples(names, annotation_prefix(), cls).map(lambda t: f"Class: {t[0]}\n  SubClassOf: {t[1]}{t[2]}\n"),
        st.tuples(annotation_prefix(), st.lists(cls, min_size=2, max_size=3)).map(
            lambda t: "EquivalentClasses: " + t[0] + ", ".join(t[1]) + "\n"
        ),
        st.tuples(annotation_prefix(), st.lists(cls, min_size=2, max_size=3)).map(
            lambda t: "DisjointClasses: " + t[0] + ", ".join(t[1]) + "\n"
        ),
        st.tuples(annotation_prefix(), st.lists(st.sampled_from(INDIVIDUALS), min_size=2, max_size=3, unique=True)).map(
            lambda t: "DifferentIndividuals: " + t[0] + ", ".join(t[1]) + "\n"
        ),
        # nodeID individuals and the new literal forms
        st.tuples(node_id, cls).map(lambda t: f"Individual: {t[0]}\n  Types: {t[1]}\n"),
        st.tuples(st.sampled_from(INDIVIDUALS), node_id).map(lambda t: f"Individual: {t[0]}\n  SameAs: {t[1]}\n"),
        st.tuples(st.sampled_from(INDIVIDUALS), st.sampled_from(DATA_PROPS), literal).map(
            lambda t: f"Individual: {t[0]}\n  Facts: {t[1]} {t[2]}\n"
        ),
    )


documents = st.lists(axiom_text(), min_size=1, max_size=4).map(lambda frames: PRELUDE + "".join(frames))

# Default is small and reproducible (each example runs SHACL validation, ~1s). To hunt for new
# counterexamples: MANCHESTER_HYPOTHESIS_EXAMPLES=300 MANCHESTER_HYPOTHESIS_HUNT=1 pytest -k generated
SETTINGS = settings(
    max_examples=int(os.environ.get("MANCHESTER_HYPOTHESIS_EXAMPLES", "20")),
    deadline=None,
    derandomize=not os.environ.get("MANCHESTER_HYPOTHESIS_HUNT"),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@pytest.mark.manchester_conformance
@given(documents)
@SETTINGS
def test_generated_documents_hold_the_tree_invariants(text):
    direct = parse_to_graph(text)
    tree = manchester_parse_to_tree(text)

    conforms, _report, report_text = manchester_validate(tree)
    assert conforms, report_text[:400]

    assert isomorphic(direct, to_graph(manchester_tree_to_owl(tree))), "tree OWL differs from direct parse"

    rendered = manchester_tree_to_text(tree)
    assert isomorphic(direct, parse_to_graph(rendered)), f"render does not re-parse to the same OWL:\n{rendered}"

    assert manchester_tree_to_text(manchester_parse_to_tree(rendered)) == rendered, "second pass unstable"
