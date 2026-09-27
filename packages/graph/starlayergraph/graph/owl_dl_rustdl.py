"""
starlayergraph.graph.owl_dl_rustdl

OWL 2 Direct Semantics reasoning via RustDL - the second engine
infer(profile="owl-dl") can dispatch to, alongside engine="hermit"
(starlayergraph.graph.owl_dl, the default). Same profile, same
InconsistentOntologyError contract, same (before, delta) return shape -
a genuinely different tradeoff, not a strictly-better replacement, which
is why both exist rather than one being swapped for the other.

RustDL (https://github.com/MaastrichtU-IDS/rustdl, `pip install rustdl`)
is a pure-Rust SROIQ reasoner with a native PyO3 Python binding - no JVM,
no subprocess, unlike HermiT via owlready2. That is the entire reason to
choose engine="rustdl" over the default. The reasons NOT to default to it,
found and confirmed live rather than assumed - see
packages/graph/docs/future_enhancements.md for the fuller writeup:

1. **Not provably complete on full SROIQ.** RustDL's own docs: complete
   by construction only on the EL/Horn fragment; beyond it, "the
   classifier trusts the wedge's Sat verdicts - empirically near-complete
   on the measured corpus, not provably complete." HermiT's tableau
   reasoning is sound *and* complete for the whole profile.

2. **No disjunctive-derived property assertions - a concrete, demonstrable
   gap, not just an abstract completeness footnote.** `classify()`/
   `materialize_inferred_class_assertions()` correctly derive disjunctive
   CLASS entailments (confirmed live: the nested-three-way-disjunction
   example this project's own 05e-owl-dl-reasoning.ipynb §1.a uses comes
   back identical to HermiT's answer). But
   `materialize_inferred_property_assertions()` documents itself as a
   "sound under-approximation (no anonymous-witness or
   disjunctive-derived edges)" - confirmed live against §1.b's logic
   puzzle: it returns only the one already-asserted `livesIn` fact, none
   of the forced-by-elimination pairings HermiT derives for that same
   ontology. Anything in this codebase relying on forced *property*
   assignments coming back from a bare `infer()` call with no search
   (the whole premise of §1.b, and of §4.b's "reduce" step in the
   employee/job example) will not reproduce the same way under
   engine="rustdl" - `is_consistent()` still works correctly for it
   (so §4's backtracking-search *approach* is unaffected), just not the
   "get the forced pairings for free from one bare infer() call" shortcut.

3. **`HasKey:` and long role chains are refused outright, not silently
   dropped** - `rustdl.UnsupportedAxiomError`, for exactly the two
   constructs starlayergraph.parsers.manchester_parser can itself emit
   (`HasKey:`, and a `SubPropertyChain:` longer than two properties).
   Some data-property/datatype axioms outside RustDL's own recognized
   preprocessing patterns are a "sound under-approximation" instead -
   dropped, never falsely asserted, per RustDL's own docs.

**RDF/XML compatibility fix, transparent to the caller.** RustDL's RDF/XML
parser rejects an anonymous class-expression node used as, e.g., the
object of `owl:equivalentClass` when that node (or the blank nodes it
chains through) has no explicit `rdf:type` of its own - confirmed live:
identical semantics, HermiT/owlready2 parse the untyped form fine, RustDL
raises `rustdl.ParseError` ("Unknown entity in..."). `_infer_missing_owl_types()`
below adds the missing `rdf:type owl:Class`/`owl:Restriction` before
serializing, but *only* to nodes an OWL/RDFS-vocabulary-specific position
unambiguously identifies as a class expression (the object of `rdf:type`
itself; either side of `rdfs:subClassOf`/`owl:equivalentClass`/
`owl:disjointWith`/`owl:complementOf`; `someValuesFrom`/`allValuesFrom`/
`onClass` targets; `unionOf`/`intersectionOf`/`oneOf` list members; any
node with its own `owl:onProperty` triple) - never a blanket "every
untyped subject is a class," which would risk mistyping an untyped
property or individual (equally normal, valid OWL/RDF style) rather than
just filling in what RustDL's parser needs to see explicitly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from rdflib import RDF, RDFS, Literal, URIRef, Graph
from rdflib.namespace import OWL

from starlayergraph.graph.owl_dl import InconsistentOntologyError, _complete_type_closure


def _require_rustdl():
    """Import and return the rustdl module, or raise a clear, actionable
    RuntimeError naming exactly what to install - the same "loud, not a
    bare ImportError" contract owl_dl._require_owlready2() sets for the
    other engine."""
    try:
        import rustdl
    except ImportError as exc:
        raise RuntimeError(
            "StarLayerGraph.infer(profile='owl-dl', engine='rustdl') "
            "requires the optional rustdl package - install it with "
            "`pip install starlayergraph[rustdl]` (or `pip install rustdl` "
            "directly), then retry."
        ) from exc
    return rustdl


def _infer_missing_owl_types(g: Graph) -> None:
    """See this module's own docstring's "RDF/XML compatibility fix"
    section. Mutates `g` in place, purely additive."""
    already_typed = {s for s, _p, _o in g.triples((None, RDF.type, None))}
    restriction_nodes = {s for s, _p, _o in g.triples((None, OWL.onProperty, None))}
    class_nodes = {o for _s, _p, o in g.triples((None, RDF.type, None))}

    for pred in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith,
                 OWL.complementOf, OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass):
        for s, _p, o in g.triples((None, pred, None)):
            class_nodes.add(s)
            class_nodes.add(o)

    for pred in (OWL.unionOf, OWL.intersectionOf, OWL.oneOf):
        for _s, _p, lst in g.triples((None, pred, None)):
            class_nodes.add(lst)
            node = lst
            while node is not None and node != RDF.nil:
                if pred != OWL.oneOf:
                    first = g.value(node, RDF.first)
                    if first is not None:
                        class_nodes.add(first)
                node = g.value(node, RDF.rest)

    for n in restriction_nodes - already_typed:
        g.add((n, RDF.type, OWL.Restriction))
    for n in class_nodes - already_typed - restriction_nodes:
        g.add((n, RDF.type, OWL.Class))


def classify_owl_dl_rustdl(graph):
    """Run OWL 2 DL classification (RustDL) over `graph`, returning
    (before, delta) in the same shape classify_owl_dl() (engine="hermit")
    returns, so infer()'s mode="full"/"delta"/"in-place" branches treat
    both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent.
    See this module's own docstring for what RustDL does and doesn't
    guarantee relative to engine="hermit" - notably, forced *property*
    assignments derived only through disjunctive reasoning (no search)
    won't reproduce the same way this engine did under HermiT.
    """
    rustdl = _require_rustdl()

    from starlayergraph.compare import _decompose
    before = _decompose(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        to_serialize = Graph()
        for t in before:
            to_serialize.add(t)
        _infer_missing_owl_types(to_serialize)
        to_serialize.serialize(destination=str(owl_path), format='xml')
        path = str(owl_path)

        if not rustdl.is_consistent(path):
            raise InconsistentOntologyError(
                "infer(profile='owl-dl', engine='rustdl') found self's data "
                "logically inconsistent."
            )

        expanded = Graph()
        for s, o in rustdl.materialize_inferred_subclass_axioms(path):
            expanded.add((URIRef(s), RDFS.subClassOf, URIRef(o)))
        for c, i in rustdl.materialize_inferred_class_assertions(path):
            expanded.add((URIRef(i), RDF.type, URIRef(c)))
        for s, p, o in rustdl.materialize_inferred_property_assertions(path):
            expanded.add((URIRef(s), URIRef(p), URIRef(o)))
        for s, p, lexical, datatype, lang in rustdl.materialize_inferred_data_property_assertions(path):
            if lang:
                lit = Literal(lexical, lang=lang)
            elif datatype:
                lit = Literal(lexical, datatype=URIRef(datatype))
            else:
                lit = Literal(lexical)
            expanded.add((URIRef(s), URIRef(p), lit))

    # Same closure-completion pass engine="hermit" needs - reused rather
    # than duplicated, and harmless if RustDL's own class-assertion output
    # already includes every ancestor (purely additive, idempotent).
    _complete_type_closure(expanded)

    before_set = set(before)
    delta = Graph()
    for t in expanded:
        if t not in before_set:
            delta.add(t)
    return before, delta
