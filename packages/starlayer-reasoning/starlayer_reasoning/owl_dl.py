"""
starlayer_reasoning.owl_dl

OWL 2 Direct Semantics reasoning via owlready2 + Java HermiT - a genuinely
different computational model (tableau-based DL reasoning, with real
disjunctive case-splitting and sound-and-complete consistency checking)
from every other entailment regime StarLayerGraph.infer() supports, all of which run
owlrl's forward-chaining rule engine. See infer()'s own docstring for the
entailment=ENTAILMENT['OWL-Direct'] contract; this module is the bridge that makes it work.

Deliberately HermiT only, never Pellet (owlready2 bundles both behind
sync_reasoner()/sync_reasoner_pellet()): HermiT is LGPL, Pellet is AGPL - a
materially stronger copyleft obligation - and one conformant OWL 2 DL
reasoner is sufficient to cover this regime. sync_reasoner_pellet() is
never called anywhere in this module.

engine="hermit" (this module) is one of two engines infer(entailment=ENTAILMENT['OWL-Direct'])
can dispatch to - see starlayer_reasoning.owl_dl_rustdl for the other
(engine="rustdl": no JVM, but sound-not-provably-complete rather than
sound-and-complete - a real, permanent gap against this module's own
guarantee, not a bug in either). Both engines' Python packages are optional
extras (`pip install starlayer-reasoning[hermit]` / `[rustdl]`), not core
dependencies - `owlready2` used to be core, moved to opt-in alongside
`rustdl` for a consistent story across both rather than one being special.
A real Java runtime on PATH is the one prerequisite `pip` alone still can't
satisfy for this engine specifically: owlready2 bundles Java HermiT and
needs a real JVM at runtime to run it - see `_require_java()` below.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyoxigraph as ox
from starlayer.graph import interop

from starlayer_reasoning import _timeout

Triple = tuple[Any, Any, Any]


class InconsistentOntologyError(RuntimeError):
    """Raised when entailment=ENTAILMENT['OWL-Direct'] finds self's data logically
    inconsistent under OWL 2 DL semantics - e.g. an individual typed as two
    classes declared owl:disjointWith each other. Unlike entailment=ENTAILMENT['OWL-RDF-Based']
    (whose consistency checking, via owlrl, is partial and silently embeds
    a synthetic err:error triple into the result instead of raising - see
    infer()'s own docstring), HermiT's check is sound and complete, so an
    inconsistency here is surfaced as an unmissable exception rather than
    left for the caller to notice on their own.
    """


def _require_owlready2():
    """Import and return the owlready2 module, or raise a clear, actionable
    RuntimeError naming exactly what to install - the "opt-in package
    missing" counterpart to _require_java()'s "JVM missing" check below,
    checked first since it's the cheaper, more fundamental question (no
    point checking for a JVM to run a reasoner whose Python package isn't
    even installed yet)."""
    try:
        import owlready2
    except ImportError as exc:
        raise RuntimeError(
            "StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine='hermit') "
            "requires the optional owlready2 package - install it with "
            "`pip install starlayer-reasoning[hermit]` (or `pip install "
            "owlready2` directly), then retry."
        ) from exc
    return owlready2


def _require_java() -> None:
    """Confirm a real Java runtime is reachable - the one prerequisite
    `pip install`ing owlready2 (checked by _require_owlready2() above)
    still can't satisfy: owlready2's HermiT reasoner is a Java program,
    not a pure-Python one.
    """
    if shutil.which("java") is None:
        raise RuntimeError(
            "StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct']) requires a Java runtime "
            "on PATH - owlready2's HermiT reasoner is a Java program, not a "
            "pure-Python one. Install a JRE/JDK (e.g. `brew install openjdk` "
            "on macOS, or your platform's package manager) and confirm "
            "`java -version` works, then retry."
        )


def _run_hermit_subprocess(owl_path: str, result_path: str, queue) -> None:
    """The actual blocking `owlready2.sync_reasoner()` call, isolated as a
    module-level (picklable-by-reference) function so `_timeout.run_with_timeout()`
    can run it in its own child process/process group and forcibly kill it
    (JVM grandchild included) if it doesn't finish in time - see
    `_timeout.py`'s own module docstring for why that's necessary at all.

    Puts exactly one `(status, ...)` tuple onto `queue`:
    - `('ok', None)` - success; results are already on disk at
      `result_path` (this function's own `world.save()`), not sent
      through the queue itself.
    - `('inconsistent', message)` - HermiT found the ontology logically
      inconsistent.
    - `('java_error', message)` - a present-but-broken JVM failed inside
      the HermiT subprocess call itself (not merely missing - `_require_java()`
      only confirms a `java` binary exists on PATH, not that it works).

    Arbitrary exception *objects* aren't reliably picklable across the
    process boundary (owlready2's own exception classes are not
    guaranteed to be) - only plain strings go through `queue`, and the
    parent (`classify_owl_dl()`) reconstructs the right exception type
    from the status tag.
    """
    import owlready2

    world = owlready2.World()
    onto = world.get_ontology(f"file://{owl_path}").load()
    try:
        with onto:
            owlready2.sync_reasoner(world, infer_property_values=True, debug=0)
    except owlready2.OwlReadyInconsistentOntologyError as exc:
        queue.put(('inconsistent', str(exc)))
        return
    except owlready2.OwlReadyJavaError as exc:
        queue.put(('java_error', str(exc)))
        return
    world.save(result_path, format='rdfxml')
    queue.put(('ok', None))


def classify_owl_dl(graph, timeout: float | None = _timeout.DEFAULT_TIMEOUT_SECONDS):
    """Run OWL 2 DL classification (HermiT, via owlready2) over `graph`,
    returning (before, delta) in the same shape classify_owl_dl_rustdl()
    returns, so infer()'s mode="full"/"delta"/"in-place" branches can
    treat both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent
    under OWL 2 DL semantics.

    Args:
        graph: A StarLayerGraph, or an iterable of pyoxigraph (s, p, o) triples.
        timeout: Wall-clock budget in seconds for the actual HermiT call
            (default `_timeout.DEFAULT_TIMEOUT_SECONDS`, 120s) - the call
            runs in its own subprocess/process group so it can be forcibly
            killed, JVM child included, if it's exceeded; raises
            `_timeout.ReasoningTimeoutError`. Pass `None` to disable the
            timeout entirely (wait indefinitely - the pre-this-feature
            behavior). See `_timeout.py`'s own module docstring for why a
            subprocess kill, not a cooperative cancellation, is the only
            mechanism that reliably works here.

    Returns:
        A (before, delta) tuple of sets of pyoxigraph triples - `before` the
        input with each triple term written out as a PropositionForm
        description (the reasoners cannot hold a triple term), `delta` the
        newly-entailed triples not already in `before`.
    """
    _require_owlready2()
    _require_java()

    before, placeholders = encode(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        write_rdfxml(_skolemize_individuals(before), owl_path)
        result_path = Path(tmp_dir) / "result.owl"

        status, message = _timeout.run_with_timeout(
            _run_hermit_subprocess, (str(owl_path), str(result_path)), timeout,
        )
        if status == 'inconsistent':
            raise InconsistentOntologyError(
                "infer(entailment=ENTAILMENT['OWL-Direct']) found self's data logically "
                "inconsistent under OWL 2 DL semantics."
            )
        if status == 'java_error':
            # `_require_java()` above only confirms a `java` binary exists on
            # PATH - it doesn't confirm that binary actually runs. A present
            # but broken/misconfigured JVM (corrupted install, bad
            # JAVA_HOME, missing shared libs, ...) fails here instead,
            # inside the HermiT subprocess call - confirmed live by
            # replacing `java` on PATH with a script that always exits
            # non-zero. Re-wrapped into the same RuntimeError family
            # `_require_java()` uses, so both "Java missing" and "Java
            # present but broken" are one exception type to catch, not two.
            raise RuntimeError(
                "StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct']) found `java` on PATH, "
                "but it failed to run HermiT - the JVM itself is broken or "
                f"misconfigured, not just missing. {message}"
            )

        expanded = read_rdfxml(result_path)

    return before, _delta_from_result(expanded, before, placeholders)


# ---- what goes to the reasoners and what comes back: pyoxigraph triples, RDF/XML on disk ----------------------------------

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_OWL = "http://www.w3.org/2002/07/owl#"
_XSD = "http://www.w3.org/2001/XMLSchema#"
RDF_TYPE, RDF_FIRST, RDF_REST, RDF_NIL, RDF_LIST = (ox.NamedNode(_RDF + n) for n in ("type", "first", "rest", "nil", "List"))
RDFS_SUBCLASS, RDFS_SUBPROPERTY, RDFS_DATATYPE = (ox.NamedNode(_RDFS + n) for n in ("subClassOf", "subPropertyOf", "Datatype"))


def _owl(*names: str) -> tuple:
    return tuple(ox.NamedNode(_OWL + n) for n in names)


_ANONYMOUS_ONTOLOGY = "http://anonymous"
_SKOLEM = "urn:starlayer:owl-dl-individual#"
_STRUCTURAL_TYPES = frozenset(
    _owl("Restriction", "Class", "DataRange", "AllDifferent", "AllDisjointClasses", "AllDisjointProperties",
         "NegativePropertyAssertion", "Axiom", "Annotation", "Ontology") + (RDFS_DATATYPE, RDF_LIST)
)
_STRUCTURAL_PREDICATES = frozenset(
    _owl("onProperty", "onClass", "onDataRange", "onDatatype", "withRestrictions", "someValuesFrom", "allValuesFrom",
         "hasValue", "hasSelf", "cardinality", "minCardinality", "maxCardinality", "qualifiedCardinality",
         "minQualifiedCardinality", "maxQualifiedCardinality", "unionOf", "intersectionOf", "complementOf", "oneOf",
         "datatypeComplementOf", "members", "distinctMembers", "inverseOf", "sourceIndividual",
         "assertionProperty", "targetIndividual", "targetValue", "annotatedSource", "annotatedProperty",
         "annotatedTarget") + (RDF_FIRST, RDF_REST)
)
_ONTOLOGY, _EQUIVALENT_CLASS, _EQUIVALENT_PROPERTY, _INVERSE_OF, _SYMMETRIC, _TRANSITIVE = _owl(
    "Ontology", "equivalentClass", "equivalentProperty", "inverseOf", "SymmetricProperty", "TransitiveProperty")
_PF_PREDICATES = frozenset((interop.PF_SUBJECT, interop.PF_PREDICATE, interop.PF_OBJECT))


def triples_of(graph: Any) -> list[Triple]:
    """The (s, p, o) triples of a StarLayerGraph, or of any iterable of triples."""
    items = graph.triples() if hasattr(graph, "triples") else graph
    return [(s, p, o) for s, p, o in items]


def encode(graph: Any) -> tuple[set[Triple], set]:
    """``graph`` as plain RDF 1.1 triples, which is what the reasoners read: each triple term becomes a blank node with a
    ``rdf:PropositionForm`` description (``interop.to_basic``) and a base-direction literal its datatype-IRI form
    (``interop.encode_directions``). Also the blank nodes that stand for triple terms, whose entailments are no part of the
    user's graph."""
    quads = [ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in triples_of(graph)]
    quads = interop.encode_directions(interop.to_basic(quads))
    triples = {(q.subject, q.predicate, q.object) for q in quads}
    return triples, {s for s, p, _o in triples if p == interop.PF_SUBJECT}


def write_rdfxml(triples: Iterable[Triple], path: Path) -> None:
    """``triples`` as RDF/XML at ``path`` (Oxigraph's writer): the format both reasoners read."""
    path.write_bytes(ox.serialize([ox.Triple(s, p, o) for s, p, o in triples], format=ox.RdfFormat.RDF_XML))


def read_rdfxml(path: Path) -> set[Triple]:
    """The triples of the RDF/XML file at ``path``."""
    return {(t.subject, t.predicate, t.object) for t in ox.parse(path=str(path), format=ox.RdfFormat.RDF_XML)}


def _skolemize_individuals(triples: Iterable[Triple]) -> set[Triple]:
    """A copy of ``triples`` in which every blank node that stands for an individual (or a triple-term placeholder) is an IRI
    of an internal namespace. The reasoners rename the blank nodes they read, so a blank node individual would come back
    under a new name and every triple about it would look new. Blank nodes of class expressions, restrictions and lists must
    stay blank nodes for the RDF mapping to parse, so those are left alone."""
    triples = set(triples)
    structural = set()
    for s, p, o in triples:
        if isinstance(s, ox.BlankNode) and (p in _STRUCTURAL_PREDICATES or p.value.startswith(_XSD)
                                            or (p == RDF_TYPE and o in _STRUCTURAL_TYPES)):
            structural.add(s)

    def sk(term):
        return ox.NamedNode(_SKOLEM + term.value) if isinstance(term, ox.BlankNode) and term not in structural else term

    return {(sk(s), p, sk(o)) for s, p, o in triples}


def _unskolemize(term):
    return ox.BlankNode(term.value[len(_SKOLEM):]) if isinstance(term, ox.NamedNode) and term.value.startswith(_SKOLEM) else term


def _delta_from_result(expanded: Iterable[Triple], before: set[Triple], placeholders: set) -> set[Triple]:
    """The new triples of the reasoner's ``expanded`` result over the input ``before`` (blank nodes as the user has them):
    blank node individuals back under their own names, the closures the reasoners leave out added, and only triples about the
    user's own terms kept. Blank nodes the reasoner invented (renamed class expressions) and the triple-term placeholders and
    their PropositionForm vocabulary are no part of the user's data."""
    result = {(_unskolemize(s), p, _unskolemize(o)) for s, p, o in expanded}
    _drop_temp_ontology(result)
    result |= _closure_additions(result, before)
    result |= _type_closure_additions(result)

    own_bnodes = {t for triple in before for t in triple if isinstance(t, ox.BlankNode)}
    return {
        t for t in result
        if t not in before
        and not any(isinstance(x, ox.BlankNode) and x not in own_bnodes for x in t)
        and t[1] not in _PF_PREDICATES and not any(x in placeholders for x in t)
    }


def _transitive(edges: dict) -> dict:
    """The transitive closure of a ``{node: set(successors)}`` map (a new dict; a node is never its own successor)."""
    out = {}
    for n in edges:
        seen: set = set()
        stack = list(edges[n])
        while stack:
            m = stack.pop()
            if m in seen:
                continue
            seen.add(m)
            stack.extend(edges.get(m, ()))
        seen.discard(n)
        if seen:
            out[n] = seen
    return out


def _closure_additions(expanded: set[Triple], before: set[Triple]) -> set[Triple]:
    """The reasoners' realization output holds only the direct (or no) rdfs:subClassOf / rdfs:subPropertyOf edges and no
    property assertions that follow from a property axiom. The triples to add to ``expanded``: what OWL 2 entails and the
    OWL-RL regime already gives: the transitive closure of subClassOf and subPropertyOf over named classes and properties (an
    equivalentClass / equivalentProperty counting as both directions), and the property assertions that follow from
    subPropertyOf, equivalentProperty, inverseOf, SymmetricProperty and TransitiveProperty, read from the input and the result
    together."""
    facts = before | expanded
    added: set[Triple] = set()

    def edges(pred, equivalent):
        out: dict = {}
        for s, p, o in facts:
            if not (isinstance(s, ox.NamedNode) and isinstance(o, ox.NamedNode) and s != o):
                continue
            if p == pred:
                out.setdefault(s, set()).add(o)
            elif p == equivalent:
                out.setdefault(s, set()).add(o)
                out.setdefault(o, set()).add(s)
        return _transitive(out)

    supers = edges(RDFS_SUBPROPERTY, _EQUIVALENT_PROPERTY)
    for pred, closed in ((RDFS_SUBCLASS, edges(RDFS_SUBCLASS, _EQUIVALENT_CLASS)), (RDFS_SUBPROPERTY, supers)):
        for s, parents in closed.items():
            for o in parents:
                added.add((s, pred, o))

    inverse: dict = {}
    symmetric, transitive = set(), set()
    for s, p, o in facts:
        if p == _INVERSE_OF and isinstance(s, ox.NamedNode) and isinstance(o, ox.NamedNode):
            inverse.setdefault(s, set()).add(o)
            inverse.setdefault(o, set()).add(s)
        elif p == RDF_TYPE and o == _SYMMETRIC:
            symmetric.add(s)
        elif p == RDF_TYPE and o == _TRANSITIVE:
            transitive.add(s)
    if not (supers or inverse or symmetric or transitive):
        return added
    relevant = set(supers) | {q for qs in supers.values() for q in qs} | set(inverse) | symmetric | transitive
    by_predicate: dict = {}
    for s, p, o in facts:
        if p in relevant:
            by_predicate.setdefault(p, set()).add((s, o))
    known = {(s, p, o) for p, pairs in by_predicate.items() for s, o in pairs}

    def add(s, p, o):
        if (s, p, o) not in known and isinstance(p, ox.NamedNode) and not isinstance(s, ox.Literal):
            known.add((s, p, o))
            by_predicate.setdefault(p, set()).add((s, o))
            added.add((s, p, o))
            return True
        return False

    changed = True
    while changed:
        changed = False
        for p in list(by_predicate):
            pairs = list(by_predicate[p])
            for q in supers.get(p, ()):
                for s, o in pairs:
                    changed |= add(s, q, o)
            for q in inverse.get(p, ()):
                for s, o in pairs:
                    if not isinstance(o, ox.Literal):
                        changed |= add(o, q, s)
            if p in symmetric:
                for s, o in pairs:
                    if not isinstance(o, ox.Literal):
                        changed |= add(o, p, s)
            if p in transitive:
                forward: dict = {}
                for s, o in pairs:
                    forward.setdefault(s, set()).add(o)
                for s, o in pairs:
                    for z in forward.get(o, ()):
                        changed |= add(s, p, z)
    return added


def _drop_temp_ontology(triples: set[Triple]) -> None:
    """The reasoners read the graph from a temporary ``.../graph.owl`` file, and when the input declares no ontology IRI they
    name the ontology after that file (owlready2 with no file name uses ``http://anonymous``), so the result carries
    ``<file:///tmp/.../graph.owl> a owl:Ontology``: a name that is no part of the user's data and made two runs of the same
    input differ. Removes that declaration."""
    temporary = {
        s for s, p, o in triples
        if p == RDF_TYPE and o == _ONTOLOGY and isinstance(s, ox.NamedNode)
        and (s.value == _ANONYMOUS_ONTOLOGY or (s.value.startswith("file:///") and s.value.endswith("/graph.owl")))
    }
    triples.difference_update({t for t in triples if t[0] in temporary})


def _type_closure_additions(expanded: set[Triple]) -> set[Triple]:
    """HermiT's CLI realization output only reports each individual's
    *most specific* known type(s), not every ancestor class up the
    hierarchy (confirmed live: for a plain `Manager rdfs:subClassOf
    Employee` + `alice a Manager`, HermiT reports `Type(alice, Manager)`
    but never `Type(alice, Employee)`, even though the subClassOf edge
    itself - `SubClassOf(Manager, Employee)` - is reported and present in
    `expanded`). Every other entailment regime infer() supports (all owlrl-backed)
    gives the full transitive rdf:type closure, so this step restores that
    same guarantee here - the triples to add: every ancestor class of each
    individual's reported type(s), by walking rdfs:subClassOf transitively.
    Purely additive: only what HermiT already reported implies."""
    parents: dict = {}
    for c, p, parent in expanded:
        if p == RDFS_SUBCLASS:
            parents.setdefault(c, set()).add(parent)

    def _ancestors(cls):
        seen = set()
        stack = list(parents.get(cls, ()))
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            stack.extend(parents.get(p, ()))
        return seen

    return {(ind, RDF_TYPE, ancestor) for ind, p, cls in expanded if p == RDF_TYPE for ancestor in _ancestors(cls)}
