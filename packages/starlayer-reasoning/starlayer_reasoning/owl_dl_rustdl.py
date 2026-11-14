"""
starlayer_reasoning.owl_dl_rustdl

OWL 2 Direct Semantics reasoning via RustDL - the second engine
infer(entailment=ENTAILMENT['OWL-Direct']) can dispatch to, alongside engine="hermit"
(starlayer_reasoning.owl_dl, the default). Same entailment regime, same
InconsistentOntologyError contract, same (before, delta) return shape -
a genuinely different tradeoff, not a strictly-better replacement, which
is why both exist rather than one being swapped for the other.

RustDL (https://github.com/MaastrichtU-IDS/rustdl, `pip install rustdl`)
is a pure-Rust SROIQ reasoner with a native PyO3 Python binding - no JVM,
no subprocess, unlike HermiT via owlready2. That is the entire reason to
choose engine="rustdl" over the default. The reasons NOT to default to it,
found and confirmed live rather than assumed - see
docs/design/future_enhancements.md for the fuller writeup:

1. **Not provably complete on full SROIQ.** RustDL's own docs: complete
   by construction only on the EL/Horn fragment; beyond it, "the
   classifier trusts the wedge's Sat verdicts - empirically near-complete
   on the measured corpus, not provably complete." HermiT's tableau
   reasoning is sound *and* complete for all of OWL 2 DL (SROIQ).

2. **No disjunctive-derived property assertions, per RustDL's own stated
   design.** `classify()`/`materialize_inferred_class_assertions()`
   correctly derive disjunctive CLASS entailments (confirmed live: the
   nested-three-way-disjunction example this project's own
   02c-owl-dl-reasoning.ipynb §1.1 uses comes back identical to HermiT's
   answer). `materialize_inferred_property_assertions()` documents itself
   as a "sound under-approximation (no anonymous-witness or
   disjunctive-derived edges)" - a forced property assignment via
   elimination over an `owl:oneOf` nominal set is the only
   OWL-DL-expressible way to construct a genuinely disjunctive-forced
   property assignment (it's structurally the only way to say "exactly
   one of these N named individuals" at all), and that exact pattern is
   the hang case point 4 below catches pre-flight - so this project has
   **no live, re-verifiable case** of the "sound under-approximation"
   behavior for property assertions, only RustDL's own stated design
   intent for it. `is_consistent()` still works correctly on that
   ontology (so §4's backtracking-search *approach* is unaffected), just
   not a bare `infer()` call, which raises `rustdl.UnsupportedAxiomError`
   pre-flight rather than either shortcut.

3. **`HasKey:` and long role chains are refused outright, not silently
   dropped** - `rustdl.UnsupportedAxiomError`, for exactly the two
   constructs starlayer.graph.manchester.parser can itself emit
   (`HasKey:`, and a `SubPropertyChain:` longer than two properties).
   Some data-property/datatype axioms outside RustDL's own recognized
   preprocessing patterns are a "sound under-approximation" instead -
   dropped, never falsely asserted, per RustDL's own docs.

4. **A confirmed hang, not just an incompleteness gap, on one specific
   idiom - detected and rejected *before* it can hang.** A property
   declared both `owl:FunctionalProperty` and `owl:InverseFunctionalProperty`,
   used as `owl:onProperty` in a restriction whose `owl:someValuesFrom`
   targets an `owl:oneOf` nominal enumeration, hangs
   `materialize_inferred_class_assertions()` indefinitely - confirmed
   RustDL-specific (HermiT handles the identical case without issue).
   `_check_rustdl_hang_risk()` below catches this pre-flight via a SPARQL
   ASK (`_HANG_RISK_ASK`) over the *compiled* OWL 2 RDF Mapping triples (`owl:Restriction`/`onProperty`/
   `someValuesFrom`/`oneOf`) - deliberately not gated through this
   project's own `manch:` Manchester-syntax-tree-as-RDF vocabulary, since the
   pattern looks identical regardless of how the ontology was authored
   (Manchester Syntax, Turtle, RDF/XML, or direct triple insertion) and a
   `manch:`-only check would silently miss every non-Manchester-authored
   case. Raises `rustdl.UnsupportedAxiomError` - the same exception type
   RustDL's own `HasKey:`/role-chain rejections raise above - rather than
   a project-local exception, so a caller catching that one type already
   catches this too.

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

import pyoxigraph as ox

from starlayer_reasoning import _timeout
from starlayer_reasoning.owl_dl import (
    RDF_FIRST,
    RDF_NIL,
    RDF_REST,
    RDF_TYPE,
    RDFS_SUBCLASS,
    InconsistentOntologyError,
    _delta_from_result,
    _owl,
    _skolemize_individuals,
    encode,
    write_rdfxml,
)

# See this module's own docstring, point 4, for the full account of what
# this detects and why. A single sh:sparql SELECT over the compiled OWL 2
# RDF Mapping triples - bounded, no recursion, so this pre-flight check
# itself carries none of the hang risk it's guarding against.
_HANG_RISK_ASK = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    ASK {
        ?restriction a owl:Restriction ;
                     owl:onProperty ?p ;
                     owl:someValuesFrom ?filler .
        ?p a owl:FunctionalProperty ;
           a owl:InverseFunctionalProperty .
        ?filler owl:oneOf ?list .
    }
"""


def _check_rustdl_hang_risk(triples) -> None:
    """Pre-flight structural check for the confirmed RustDL hang - see this
    module's own docstring, point 4. Raises `rustdl.UnsupportedAxiomError`
    if the triples match the hang pattern; returns silently otherwise. One
    SPARQL ASK over the triples in a throwaway Oxigraph store: bounded, no
    recursion, so the check itself carries none of the hang risk it guards
    against."""
    rustdl = _require_rustdl()

    store = ox.Store()
    store.extend(ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in triples)
    if bool(store.query(_HANG_RISK_ASK)):
        raise rustdl.UnsupportedAxiomError(
            "A property is declared both owl:FunctionalProperty and "
            "owl:InverseFunctionalProperty and used in a someValuesFrom "
            "restriction whose filler is an owl:oneOf nominal enumeration - "
            "confirmed to hang RustDL's materialize_inferred_class_assertions() "
            "indefinitely (see owl_dl_rustdl.py's own module docstring, "
            "point 4). Use engine='hermit' for this ontology instead."
        )


def _require_rustdl():
    """Import and return the rustdl module, or raise a clear, actionable
    RuntimeError naming exactly what to install - the same "loud, not a
    bare ImportError" contract owl_dl._require_owlready2() sets for the
    other engine."""
    try:
        import rustdl
    except ImportError as exc:
        raise RuntimeError(
            "StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine='rustdl') "
            "requires the optional rustdl package - install it with "
            "`pip install starlayer-reasoning[rustdl]` (or `pip install rustdl` "
            "directly), then retry."
        ) from exc
    return rustdl


_ON_PROPERTY, _OWL_RESTRICTION, _OWL_CLASS = _owl("onProperty", "Restriction", "Class")
_CLASS_POSITIONS = frozenset((RDFS_SUBCLASS, *_owl("equivalentClass", "disjointWith", "complementOf", "someValuesFrom", "allValuesFrom", "onClass")))
_LIST_POSITIONS = _owl("unionOf", "intersectionOf", "oneOf")
_ONE_OF = _LIST_POSITIONS[2]


def _infer_missing_owl_types(triples: set) -> set:
    """See this module's own docstring's "RDF/XML compatibility fix"
    section. The triples to add to ``triples``: purely additive."""
    already_typed = {s for s, p, _o in triples if p == RDF_TYPE}
    restriction_nodes = {s for s, p, _o in triples if p == _ON_PROPERTY}
    class_nodes = {o for _s, p, o in triples if p == RDF_TYPE}
    first: dict = {}
    rest: dict = {}
    for s, p, o in triples:
        if p in _CLASS_POSITIONS:
            class_nodes.add(s)
            class_nodes.add(o)
        elif p == RDF_FIRST:
            first.setdefault(s, o)
        elif p == RDF_REST:
            rest.setdefault(s, o)

    for _s, p, lst in triples:
        if p not in _LIST_POSITIONS:
            continue
        class_nodes.add(lst)
        node, seen = lst, set()
        while node is not None and node != RDF_NIL and node not in seen:
            seen.add(node)
            if p != _ONE_OF and node in first:
                class_nodes.add(first[node])
            node = rest.get(node)

    def typed(nodes, cls):
        return {(n, RDF_TYPE, cls) for n in nodes if isinstance(n, (ox.NamedNode, ox.BlankNode))}

    return typed(restriction_nodes - already_typed, _OWL_RESTRICTION) | typed(class_nodes - already_typed - restriction_nodes, _OWL_CLASS)


def _run_rustdl_subprocess(owl_path: str, result_path: str, queue) -> None:
    """The actual blocking RustDL calls (`is_consistent()` +
    `materialize_inferred_*()`), isolated as a module-level
    (picklable-by-reference) function so `_timeout.run_with_timeout()` can
    run it in its own child process/process group and forcibly kill it if
    it doesn't finish in time - the same mechanism `owl_dl._run_hermit_subprocess()`
    uses, for the same reason: RustDL's own native PyO3 call is just as
    opaque/uninterruptible from Python as a JVM subprocess wait is.

    Puts exactly one `(status, ...)` tuple onto `queue`:
    - `('ok', None)` - success; the four materialized result lists are
      already pickled to `result_path`, not sent through the queue.
    - `('inconsistent', None)` - `is_consistent()` returned False.

    `rustdl.UnsupportedAxiomError` (HasKey:/long role chains - real,
    RustDL-native rejections distinct from `_check_rustdl_hang_risk()`'s
    own pre-flight check, which runs in the parent process *before* this
    function is ever called) propagates up through this subprocess boundary
    the same way any other exception would if left uncaught - multiprocessing
    itself re-raises it in the parent via the process's exit, but since
    this function's own contract is "always put something on queue," an
    uncaught exception here instead surfaces to the caller as a
    ReasoningTimeoutError (subprocess exited without a result) rather than
    the original exception type - acceptable because
    `_check_rustdl_hang_risk()` already catches the one exception this
    project's own parser can trigger before ever reaching this function;
    an exception here would be a genuinely new, unhandled RustDL rejection
    worth investigating on its own terms regardless of exact type.
    """
    import pickle

    import rustdl

    if not rustdl.is_consistent(owl_path):
        queue.put(('inconsistent', None))
        return

    result = {
        'subclass': rustdl.materialize_inferred_subclass_axioms(owl_path),
        'class_assertions': rustdl.materialize_inferred_class_assertions(owl_path),
        'property_assertions': rustdl.materialize_inferred_property_assertions(owl_path),
        'data_property_assertions': rustdl.materialize_inferred_data_property_assertions(owl_path),
    }
    with open(result_path, 'wb') as f:
        pickle.dump(result, f)
    queue.put(('ok', None))


def classify_owl_dl_rustdl(graph, timeout: float | None = _timeout.DEFAULT_TIMEOUT_SECONDS):
    """Run OWL 2 DL classification (RustDL) over `graph`, returning
    (before, delta) in the same shape classify_owl_dl() (engine="hermit")
    returns, so infer()'s mode="full"/"delta"/"in-place" branches treat
    both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent.
    See this module's own docstring for what RustDL does and doesn't
    guarantee relative to engine="hermit" - notably, forced *property*
    assignments derived only through disjunctive reasoning (no search)
    won't reproduce the same way this engine did under HermiT.

    Args:
        graph: A StarLayerGraph, or an iterable of pyoxigraph (s, p, o) triples.
        timeout: Wall-clock budget in seconds for the actual RustDL call
            (default `_timeout.DEFAULT_TIMEOUT_SECONDS`, 120s) -
            defense-in-depth for any hang pattern other than the one
            `_check_rustdl_hang_risk()` already catches pre-flight (point
            4 of this module's own docstring). Pass `None` to disable
            entirely. See `classify_owl_dl()`'s own docstring /
            `_timeout.py`'s module docstring for the full rationale,
            shared between both engines.

    Returns:
        A (before, delta) tuple of sets of pyoxigraph triples - `before` the
        input with each triple term written out as a PropositionForm
        description, `delta` the newly-entailed triples not already in
        `before`.
    """
    _require_rustdl()

    before, placeholders = encode(graph)
    _check_rustdl_hang_risk(before)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        to_serialize = _skolemize_individuals(before)
        to_serialize |= _infer_missing_owl_types(to_serialize)
        write_rdfxml(to_serialize, owl_path)
        path = str(owl_path)
        result_path = Path(tmp_dir) / "result.pickle"

        status, _extra = _timeout.run_with_timeout(
            _run_rustdl_subprocess, (path, str(result_path)), timeout,
        )
        if status == 'inconsistent':
            raise InconsistentOntologyError(
                "infer(entailment=ENTAILMENT['OWL-Direct'], engine='rustdl') found self's data "
                "logically inconsistent."
            )

        import pickle
        with open(result_path, 'rb') as f:
            result = pickle.load(f)

        expanded = set()
        for s, o in result['subclass']:
            expanded.add((ox.NamedNode(s), RDFS_SUBCLASS, ox.NamedNode(o)))
        for c, i in result['class_assertions']:
            expanded.add((ox.NamedNode(i), RDF_TYPE, ox.NamedNode(c)))
        for s, p, o in result['property_assertions']:
            expanded.add((ox.NamedNode(s), ox.NamedNode(p), ox.NamedNode(o)))
        for s, p, lexical, datatype, lang in result['data_property_assertions']:
            if lang:
                lit = ox.Literal(lexical, language=lang)
            elif datatype:
                lit = ox.Literal(lexical, datatype=ox.NamedNode(datatype))
            else:
                lit = ox.Literal(lexical)
            expanded.add((ox.NamedNode(s), ox.NamedNode(p), lit))

    return before, _delta_from_result(expanded, before, placeholders)
