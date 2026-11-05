"""Pretty Turtle / TriG (``oxgraph/pretty.py``): the gates (re-parse isomorphic with byte-preserved lexical forms, idempotence),
the layout rules the old rdflib writer had, and goldens (``fixtures/pretty/golden``).

Corpus: the vendored W3C Turtle 1.2 inputs, the RDFC-1.0 N-Quads inputs (``test074``, the poison graph, left out), the SHACL
test-suite Turtle, the fixtures here, and seeded random datasets (blank-node trees and cycles, shared blank nodes, collections,
malformed lists, nested triple terms, reifiers and annotations, directional literals, named graphs).
"""

from __future__ import annotations

import glob
import os
import random
import re

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph
from starlayer.graph.oxgraph.pretty import pretty_trig, pretty_turtle
from starlayer.graph.rdfc_native import isomorphic

HERE = os.path.dirname(__file__)
TESTS = os.path.dirname(os.path.dirname(HERE))
FIX = os.path.join(HERE, "fixtures", "pretty")
EX = {"ex": "http://example/"}
FMT = {"ttl": ox.RdfFormat.TURTLE, "nq": ox.RdfFormat.N_QUADS, "trig": ox.RdfFormat.TRIG, "nt": ox.RdfFormat.N_TRIPLES}


def parse(text: str, fmt=ox.RdfFormat.TURTLE) -> list[ox.Quad]:
    return list(ox.parse(text.encode(), format=fmt, base_iri="http://example/base/"))


def lexical(quads) -> list[tuple]:
    return sorted((q.object.value, q.object.datatype.value, q.object.language or "", str(q.object.direction))
                  for q in quads if isinstance(q.object, ox.Literal))


def check_gates(quads, **kw) -> str:
    """Re-parse is isomorphic, lexical forms are byte-identical, and a second pass over the re-parse is the same text."""
    out = pretty_trig(quads, **kw)
    again = parse(out, ox.RdfFormat.TRIG)
    assert isomorphic(quads, again)
    assert lexical(quads) == lexical(again)
    assert pretty_trig(again, **kw) == out
    return out


N = ox.NamedNode
R = ox.NamedNode
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"
LITERALS = [
    ox.Literal("1", datatype=N(XSD + "integer")), ox.Literal("+1.5", datatype=N(XSD + "decimal")),
    ox.Literal("1E5", datatype=N(XSD + "double")), ox.Literal("true", datatype=N(XSD + "boolean")),
    ox.Literal("1", datatype=N(XSD + "boolean")), ox.Literal('a\nb"""\\'), ox.Literal('q"'),
    ox.Literal("x", language="en-us"), ox.Literal("x", language="ar", direction=ox.BaseDirection.RTL),
    ox.Literal("\t\x01 \u00e9"), ox.Literal("x", datatype=N("http://e/dt")), ox.Literal("5.", datatype=N(XSD + "decimal")),
]


def gen(seed: int, n: int = 40) -> list[ox.Quad]:
    """A random dataset with blank-node trees and cycles, shared nodes, lists (some malformed), nested triple terms, reifiers
    (some shared, some reifying two triples), directional literals and named graphs."""
    r = random.Random(seed)
    iris = [N(f"http://e/{c}") for c in "abcdefg"]
    preds = [N(f"http://e/p{i}") for i in range(4)] + [N(RDF + "type")]
    bn = [ox.BlankNode(f"x{i}") for i in range(r.randint(2, 10))]
    graphs = [ox.DefaultGraph()] * 3 + [N("http://g/1"), N("http://g/2"), bn[0]]
    first, rest, nil, reifies = (N(RDF + x) for x in ("first", "rest", "nil", "reifies"))

    def tt(depth: int = 0) -> ox.Triple:
        o = r.choice(iris + LITERALS + bn + ([tt(depth + 1)] if depth < 2 else []))
        return ox.Triple(r.choice(iris + bn), r.choice(preds), o)

    def subj() -> ox.NamedNode | ox.BlankNode:
        return r.choice(iris + bn)

    def obj():
        k = r.random()
        if k < 0.5:
            return r.choice(iris + bn)
        return r.choice(LITERALS) if k < 0.8 else tt()

    quads: set[ox.Quad] = set()
    for _ in range(n):
        quads.add(ox.Quad(subj(), r.choice(preds), obj(), r.choice(graphs)))
    for _ in range(r.randint(0, 4)):  # lists
        cells = [ox.BlankNode() for _ in range(r.randint(1, 4))]
        g = r.choice(graphs)
        for j, c in enumerate(cells):
            quads.add(ox.Quad(c, first, obj() if r.random() < 0.8 else cells[0], g))
            last = j == len(cells) - 1
            tail = nil if last and r.random() < 0.8 else (r.choice(bn) if last else cells[j + 1])
            quads.add(ox.Quad(c, rest, tail, g))
            if r.random() < 0.1:
                quads.add(ox.Quad(c, preds[0], iris[0], g))
        quads.add(ox.Quad(subj(), preds[1], cells[0], g))
    for _ in range(r.randint(0, 6)):  # reifiers
        g = r.choice(graphs[:4])
        t = tt()
        who = r.choice(bn + iris) if r.random() < 0.6 else ox.BlankNode()
        quads.add(ox.Quad(who, reifies, t, g))
        if r.random() < 0.7:
            quads.add(ox.Quad(t.subject, t.predicate, t.object, g))
        for _ in range(r.randint(0, 2)):
            quads.add(ox.Quad(who, r.choice(preds[:4]), obj(), g))
        if r.random() < 0.2:
            quads.add(ox.Quad(who, reifies, tt(), g))
        if r.random() < 0.2:
            quads.add(ox.Quad(subj(), preds[2], who, g))
    for _ in range(r.randint(0, 3)):  # blank-node trees, some with a back edge
        a, b, g = ox.BlankNode(), ox.BlankNode(), r.choice(graphs)
        quads.add(ox.Quad(subj(), preds[2], a, g))
        quads.add(ox.Quad(a, preds[3], b, g))
        quads.add(ox.Quad(b, preds[0], obj(), g))
        if r.random() < 0.3:
            quads.add(ox.Quad(b, preds[1], a, g))
    return list(quads)


# ---- the gates over the corpus ----------------------------------------------------------------------------------------
def _corpus() -> list[tuple[str, ox.RdfFormat]]:
    found = []
    for pattern, ext in ((f"{TESTS}/graph/w3c_turtle12/data/*.ttl", "ttl"), (f"{TESTS}/shacl/vendor/**/*.ttl", "ttl"),
                         (f"{TESTS}/graph/vendor/rdfc10/rdfc10/*.nq", "nq"), (f"{FIX}/*.ttl", "ttl"), (f"{FIX}/*.trig", "trig")):
        found += [(f, FMT[ext]) for f in sorted(glob.glob(pattern, recursive=True)) if "test074" not in f]
    return found


def test_vendored_corpus_roundtrips() -> None:
    ok = 0
    for path, fmt in _corpus():
        try:
            with open(path, "rb") as fh:
                quads = list(ox.parse(fh.read(), format=fmt, base_iri="http://example/base/"))
        except (SyntaxError, ValueError):
            continue  # the negative syntax tests do not parse
        check_gates(quads)
        ok += 1
    assert ok > 500


@pytest.mark.parametrize("seed", range(300))
def test_random_datasets_roundtrip(seed: int) -> None:
    quads = gen(seed)
    check_gates(quads, width=60 if seed % 2 else 100)


def test_random_datasets_use_the_shorthand() -> None:
    seen = {"{|": 0, "<< ": 0, "[\n": 0, " ( ": 0, "~ ": 0}
    for seed in range(100):
        out = pretty_trig(gen(seed))
        for k in seen:
            seen[k] += k in out
    assert all(v > 10 for v in seen.values()), seen


def test_output_does_not_depend_on_blank_node_labels_or_order() -> None:
    quads = gen(7)
    names: dict[str, ox.BlankNode] = {}

    def new(t):
        if isinstance(t, ox.BlankNode):
            return names.setdefault(t.value, ox.BlankNode(f"z{len(names)}"))
        return ox.Triple(new(t.subject), t.predicate, new(t.object)) if isinstance(t, ox.Triple) else t

    relabelled = [ox.Quad(new(q.subject), q.predicate, new(q.object), new(q.graph_name)) for q in quads]
    random.Random(1).shuffle(relabelled)
    assert isomorphic(quads, relabelled)
    assert pretty_trig(quads) == pretty_trig(relabelled)


# ---- goldens ------------------------------------------------------------------------------------------------------------
CASES = sorted(os.path.basename(f).rsplit(".", 1)[0] for f in glob.glob(f"{FIX}/*.ttl") + glob.glob(f"{FIX}/*.trig"))


@pytest.mark.parametrize("case", CASES)
def test_golden(case: str) -> None:
    path = next(p for p in (f"{FIX}/{case}.ttl", f"{FIX}/{case}.trig") if os.path.exists(p))
    text = open(path).read()
    prefixes = dict(re.findall(r"@prefix (\w*): <([^>]*)>", text))
    out = pretty_trig(parse(text, FMT[path.rsplit(".", 1)[1]]), prefixes=prefixes)
    assert out == open(f"{FIX}/golden/{case}.turtle.trig").read()


# ---- layout rules (the old writer's tests, ported) ----------------------------------------------------------------------
def pt(text: str, **kw) -> str:
    return pretty_turtle(parse("@prefix ex: <http://example/> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + text),
                         prefixes={"ex": "http://example/", "xsd": "http://www.w3.org/2001/XMLSchema#"}, **kw)


def test_grouping_type_and_used_prefixes_only() -> None:
    out = pt("ex:s a ex:C ; ex:p ex:o1, ex:o2 .")
    assert out == "@prefix ex: <http://example/> .\n\nex:s a ex:C ;\n    ex:p ex:o1, ex:o2 .\n"
    assert "xsd" not in out and "rdf:type" not in out


def test_only_used_prefixes_false_declares_all() -> None:
    assert "@prefix xsd:" in pt("ex:s ex:p ex:o .", only_used_prefixes=False)


def test_prefixes_default_to_the_graph_s_and_invalid_ones_are_renamed() -> None:
    g = StarLayerGraph(prefixes={"a.": "http://x/"})
    g.add((ox.NamedNode("http://x/s"), ox.NamedNode("http://x/p"), ox.NamedNode("http://x/o")))
    assert g.serialize(format="turtle", pretty=True) == "@prefix pfx1: <http://x/> .\n\npfx1:s pfx1:p pfx1:o .\n"


def test_triple_term_and_version() -> None:
    out = pt("ex:s ex:p <<( ex:a ex:b ex:c )>> .")
    assert out.startswith('@version "1.2" .\n') and "<<( ex:a ex:b ex:c )>>" in out
    assert "@version" not in pt("ex:s ex:p ex:o .")
    assert pretty_turtle([]) == ""


def test_reification_forms() -> None:
    assert "{| ex:ann ex:val |}" in pt("ex:s ex:p ex:o {| ex:ann ex:val |} .")
    assert "~ ex:i {| ex:ann ex:val |}" in pt("ex:s ex:p ex:o ~ ex:i {| ex:ann ex:val |} .")
    assert pt("ex:s ex:p ex:o ~ ex:i .").rstrip().endswith("ex:s ex:p ex:o ~ ex:i .")
    unasserted = pt("<< ex:a ex:b ex:c >> ex:funny true .")
    assert "<< ex:a ex:b ex:c >> ex:funny true ." in unasserted and "reifies" not in unasserted
    assert "ex:x ex:ref << ex:a ex:b ex:c >> ." in pt("ex:x ex:ref << ex:a ex:b ex:c >> .")


def test_two_reifiers_of_one_unasserted_triple_stay_two() -> None:
    quads = parse("@prefix : <http://example/> .\n<< :a :b :c >> :p :o .\n<< :a :b :c >> :p :o2 .")
    assert len(parse(pretty_turtle(quads))) == len(quads) == 4


def test_reifier_that_cannot_fold_keeps_rdf_reifies() -> None:
    out = pt("ex:r ex:p ex:o . ex:r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ex:a ex:b ex:c )>>, <<( ex:a ex:b ex:d )>> .")
    assert out.count("<<(") == 2 and "rdf:reifies" in out


def test_collections() -> None:
    assert "ex:p ( ex:a ex:b ex:c )" in pt("ex:s ex:p ( ex:a ex:b ex:c ) .")
    assert "ex:p ()" in pt("ex:s ex:p () .")
    out = pt("ex:S ex:or ( [ ex:path ex:email ] [ ex:path ex:orcid ] ) .")
    assert "rdf:first" not in out and out.count("[") == 2


def test_malformed_lists_stay_expanded_and_roundtrip() -> None:
    text = ("ex:s ex:p _:b0 . _:b0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> ex:a ; "
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> () ; ex:extra 1 .")
    out = pt(text)
    assert "rdf:first" in out
    assert isomorphic(parse("@prefix ex: <http://example/> .\n" + text), parse(out))


def test_nil_is_never_a_collection_where_the_grammar_forbids_it() -> None:
    nil = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#nil")
    q = [ox.Quad(ox.NamedNode("http://x/s"), nil, ox.Triple(nil, nil, nil), ox.DefaultGraph())]
    check_gates(q)


def test_nested_blank_nodes_and_cycles() -> None:
    out = pt("ex:s ex:p [ a ex:T ; ex:q [ ex:r 1 ] ] .")
    assert out.count("[") == 2 and "_:" not in out
    cyc = pt("_:a ex:p _:a . _:b ex:p _:c . _:c ex:p _:b .")
    assert isomorphic(parse("@prefix ex: <http://example/> ." + "_:a ex:p _:a . _:b ex:p _:c . _:c ex:p _:b ."), parse(cyc))


def test_shorthand_only_when_the_lexical_form_is_exact() -> None:
    bare = pt('ex:s ex:p 1, +2, -3, 1.5, .5, 1.5e3, 2E-1, true, false .')
    for tok in ("1", "+2", "-3", "1.5", ".5", "1.5e3", "2E-1", "true", "false"):
        assert f" {tok}" in bare or f", {tok}" in bare
    assert "^^" not in bare
    for lex, dt in (("1", "boolean"), ("5.", "decimal"), ("5", "decimal"), ("1.", "double"), ("x", "integer"), ("+", "integer"), ("1e", "double")):
        out = pt(f'ex:s ex:p "{lex}"^^xsd:{dt} .')
        assert f'"{lex}"^^xsd:{dt}' in out
    # a double written 1e0 comes back as "1e0", not "1.0E0"
    assert lexical(parse(pt('ex:s ex:p "1e0"^^xsd:double .'))) == lexical(parse('<http://x/s> <http://x/p> 1e0 .'))


def test_literals_strings_and_directions() -> None:
    out = pt('ex:s ex:p """a\nb""", "q\\"x", "tab\there"@en, "ar"@ar--rtl, "\\u0001" .')
    assert '"""a\nb"""' in out and '"q\\"x"' in out and "@ar--rtl" in out and "\\u0001" in out
    assert '@version "1.2"' in out
    assert lexical(parse(pretty_turtle(parse(out)))) == lexical(parse(out))


def test_long_string_inside_a_triple_term_uses_the_short_form() -> None:
    q = [ox.Quad(ox.NamedNode("http://x/s"), ox.NamedNode("http://x/p"),
                 ox.Triple(ox.NamedNode("http://x/a"), ox.NamedNode("http://x/b"), ox.Literal("l1\nl2")), ox.DefaultGraph())]
    assert '"l1\\nl2"' in check_gates(q)


def test_quote_runs_in_long_strings() -> None:
    q = [ox.Quad(ox.NamedNode("http://x/s"), ox.NamedNode("http://x/p"), ox.Literal(v), ox.DefaultGraph())
         for v in ('a\n"""b', 'a\nb"', 'a\nb""', 'a\n\\', 'a\r\nb')]
    check_gates(q)


def test_base_makes_iris_relative() -> None:
    q = parse("<http://example/base/x> <http://example/base/p> <http://example/base/sub/y>, <http://other/z> .")
    out = pretty_turtle(q, base_iri="http://example/base/")
    assert out.startswith("@base <http://example/base/> .") and "<x> <p> <sub/y>" in out
    assert isomorphic(q, ox.parse(out.encode(), format=ox.RdfFormat.TURTLE))


def test_wrapping() -> None:
    objs = ", ".join(f"ex:object{i}" for i in range(12))
    text = f"ex:s ex:p {objs} ."
    assert "\n" not in pt(text, width=None).strip().split("\n\n", 1)[1].rstrip(" .\n")
    wrapped = pt(text, width=60)
    assert max(len(ln) for ln in wrapped.splitlines()) <= 60 and wrapped.count(",\n") == 11


def test_trig_graphs_and_shared_blank_nodes() -> None:
    quads = parse(open(f"{FIX}/trig_graphs.trig").read(), ox.RdfFormat.TRIG)
    out = pretty_trig(quads, prefixes=EX)
    assert out.count("GRAPH ") == 3 and "ex:default ex:p [" in out
    assert out.count("_:b0") == 2  # shared between two graphs: labelled
    with pytest.raises(ValueError, match="named graphs"):
        pretty_turtle(quads)
    assert "GRAPH" not in pretty_turtle(quads, graph=ox.NamedNode("http://example/g2"), prefixes=EX)


def test_inputs_store_dataset_and_wrappers() -> None:
    quads = parse("@prefix ex: <http://example/> . ex:s ex:p [ ex:q 1 ] .")
    want = pretty_turtle(quads, prefixes=EX)
    store = ox.Store()
    store.extend(quads)
    assert pretty_turtle(store, prefixes=EX) == want
    assert pretty_turtle(ox.Dataset(quads), prefixes=EX) == want
    assert pretty_turtle(StarLayerGraph(store, prefixes=EX)) == want
    assert pretty_trig(StarLayerDataset(store, prefixes=EX)) == want
    assert pretty_turtle((q.subject, q.predicate, q.object) for q in quads if True)  # 3-tuples


def test_serialize_hook() -> None:
    g = StarLayerGraph(prefixes=EX)
    g.parse(data="@prefix ex: <http://example/> . ex:s ex:p ( 1 2 ) .", format="turtle")
    assert g.serialize(format="turtle", pretty=True).endswith("ex:s ex:p ( 1 2 ) .\n")
    with pytest.raises(ValueError):
        g.serialize(format="turtle", pretty="longturtle")  # the flat layout is Oxigraph's own writer: not offered here
    d = StarLayerDataset(prefixes=EX)
    d.parse(data="@prefix ex: <http://example/> . ex:g { ex:s ex:p 1 }", format="trig")
    assert "GRAPH ex:g {" in d.serialize(format="trig", pretty=True)
    with pytest.raises(ValueError):
        g.serialize(format="nt", pretty=True)
    with pytest.raises(TypeError):
        pretty_turtle([], style="wide")  # there is one layout: `style` was removed with `longturtle`
