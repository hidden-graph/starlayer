"""
starlayer.graph.graph.owl_dl

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
can dispatch to - see starlayer.graph.graph.owl_dl_rustdl for the other
(engine="rustdl": no JVM, but sound-not-provably-complete rather than
sound-and-complete - a real, permanent gap against this module's own
guarantee, not a bug in either). Both engines' Python packages are optional
extras (`pip install starlayer[hermit]` / `[rustdl]`), not core
dependencies - `owlready2` used to be core, moved to opt-in alongside
`rustdl` for a consistent story across both rather than one being special.
A real Java runtime on PATH is the one prerequisite `pip` alone still can't
satisfy for this engine specifically: owlready2 bundles Java HermiT and
needs a real JVM at runtime to run it - see `_require_java()` below.
"""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
import shutil
import tempfile
from pathlib import Path

from rdflib import OWL, RDF, RDFS, BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD

from starlayer.graph.graph import _timeout


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
            "`pip install starlayer[hermit]` (or `pip install "
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
    returning (before, delta) in the same shape
    StarLayerGraph._infer_before_and_delta() returns for the owlrl-backed
    regimes, so infer()'s mode="full"/"delta"/"in-place" branches can
    treat both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent
    under OWL 2 DL semantics.

    Args:
        graph: The graph to classify.
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
        A (before, delta) tuple of Graphs - `before` the decomposed input
        graph, `delta` the newly-entailed triples not already in `before`.
    """
    _require_owlready2()
    _require_java()

    from starlayer.graph.oxgraph._rdflib_bridge import decompose as _decompose
    before = _decompose(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        _skolemize_individuals(before).serialize(destination=str(owl_path), format='xml')
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

        expanded = Graph()
        expanded.parse(str(result_path), format='xml')

    return before, _delta_from_result(expanded, before)


_ANONYMOUS_ONTOLOGY = "http://anonymous"
_SKOLEM = "urn:starlayer:owl-dl-individual#"
_STRUCTURAL_TYPES = frozenset(
    {OWL.Restriction, OWL.Class, OWL.DataRange, RDFS.Datatype, OWL.AllDifferent, OWL.AllDisjointClasses, OWL.AllDisjointProperties,
     OWL.NegativePropertyAssertion, OWL.Axiom, OWL.Annotation, RDF.List, OWL.Ontology}
)
_STRUCTURAL_PREDICATES = frozenset(
    {OWL.onProperty, OWL.onClass, OWL.onDataRange, OWL.onDatatype, OWL.withRestrictions, OWL.someValuesFrom, OWL.allValuesFrom,
     OWL.hasValue, OWL.hasSelf, OWL.cardinality, OWL.minCardinality, OWL.maxCardinality, OWL.qualifiedCardinality,
     OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality, OWL.unionOf, OWL.intersectionOf, OWL.complementOf, OWL.oneOf,
     OWL.datatypeComplementOf, OWL.members, OWL.distinctMembers, OWL.inverseOf, RDF.first, RDF.rest, OWL.sourceIndividual,
     OWL.assertionProperty, OWL.targetIndividual, OWL.targetValue, OWL.annotatedSource, OWL.annotatedProperty,
     OWL.annotatedTarget}
)


def _skolemize_individuals(graph: Graph) -> Graph:
    """A copy of ``graph`` in which every blank node that stands for an individual (or a triple-term placeholder) is an IRI
    of an internal namespace. The reasoners rename the blank nodes they read, so a blank node individual would come back
    under a new name and every triple about it would look new. Blank nodes of class expressions, restrictions and lists must
    stay blank nodes for the RDF mapping to parse, so those are left alone."""
    structural = set()
    for s, p, o in graph:
        if isinstance(s, BNode) and (p in _STRUCTURAL_PREDICATES or str(p).startswith(str(XSD))
                                     or (p == RDF.type and o in _STRUCTURAL_TYPES)):
            structural.add(s)

    def sk(term):
        return URIRef(_SKOLEM + str(term)) if isinstance(term, BNode) and term not in structural else term

    out = Graph()
    for s, p, o in graph:
        out.add((sk(s), p, sk(o)))
    return out


def _unskolemize(term):
    return BNode(str(term)[len(_SKOLEM):]) if isinstance(term, URIRef) and str(term).startswith(_SKOLEM) else term


def _delta_from_result(expanded: Graph, before: Graph) -> Graph:
    """The new triples of the reasoner's ``expanded`` result over the input ``before`` (decomposed, blank nodes as the user
    has them): blank node individuals back under their own names, the closures the reasoners leave out added, and only
    triples about the user's own terms kept. A triple is not new when ``before`` holds it, plain and xsd:string literals
    being the same term. Blank nodes the reasoner invented (renamed class expressions) and the triple-term placeholders and
    their internal namespace are no part of the user's data."""
    from starlayer.graph.oxgraph._rdflib_bridge import (
        decomposition_nodes,
        drop_decomposition,
    )

    unskolemized = Graph()
    for s, p, o in expanded:
        if isinstance(o, Literal) and o.datatype == XSD.string and not o.language:
            o = Literal(str(o))
        unskolemized.add((_unskolemize(s), p, _unskolemize(o)))
    expanded = unskolemized
    _drop_temp_ontology(expanded)
    _complete_closure(expanded, before)
    _complete_type_closure(expanded)

    own_bnodes = {t for tr in before for t in tr if isinstance(t, BNode)}
    before_set = set(before)
    delta = Graph()
    new = (t for t in expanded if t not in before_set and not any(isinstance(x, BNode) and x not in own_bnodes for x in t))
    for t in drop_decomposition(new, decomposition_nodes(before)):
        delta.add(t)
    return delta


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


def _complete_closure(expanded: Graph, before: Graph) -> None:
    """The reasoners' realization output holds only the direct (or no) rdfs:subClassOf / rdfs:subPropertyOf edges and no
    property assertions that follow from a property axiom. Adds, to ``expanded`` in place, what OWL 2 entails and the OWL-RL
    regime already gives: the transitive closure of subClassOf and subPropertyOf over named classes and properties (an
    equivalentClass / equivalentProperty counting as both directions), and the property assertions that follow from
    subPropertyOf, equivalentProperty, inverseOf, SymmetricProperty and TransitiveProperty, read from the input and the result
    together. Purely additive."""
    facts = set(before) | set(expanded)

    def edges(pred, equivalent):
        out: dict = {}
        for s, p, o in facts:
            if not (isinstance(s, URIRef) and isinstance(o, URIRef) and s != o):
                continue
            if p == pred:
                out.setdefault(s, set()).add(o)
            elif p == equivalent:
                out.setdefault(s, set()).add(o)
                out.setdefault(o, set()).add(s)
        return _transitive(out)

    supers = edges(RDFS.subPropertyOf, OWL.equivalentProperty)
    for pred, closed in ((RDFS.subClassOf, edges(RDFS.subClassOf, OWL.equivalentClass)), (RDFS.subPropertyOf, supers)):
        for s, parents in closed.items():
            for o in parents:
                expanded.add((s, pred, o))

    inverse: dict = {}
    symmetric, transitive = set(), set()
    for s, p, o in facts:
        if p == OWL.inverseOf and isinstance(s, URIRef) and isinstance(o, URIRef):
            inverse.setdefault(s, set()).add(o)
            inverse.setdefault(o, set()).add(s)
        elif p == RDF.type and o == OWL.SymmetricProperty:
            symmetric.add(s)
        elif p == RDF.type and o == OWL.TransitiveProperty:
            transitive.add(s)
    if not (supers or inverse or symmetric or transitive):
        return
    relevant = set(supers) | {q for qs in supers.values() for q in qs} | set(inverse) | symmetric | transitive
    by_predicate: dict = {}
    for s, p, o in facts:
        if p in relevant:
            by_predicate.setdefault(p, set()).add((s, o))
    known = {(s, p, o) for p, pairs in by_predicate.items() for s, o in pairs}

    def add(s, p, o):
        if (s, p, o) not in known and isinstance(p, URIRef) and not isinstance(s, Literal):
            known.add((s, p, o))
            by_predicate.setdefault(p, set()).add((s, o))
            expanded.add((s, p, o))
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
                    if not isinstance(o, Literal):
                        changed |= add(o, q, s)
            if p in symmetric:
                for s, o in pairs:
                    if not isinstance(o, Literal):
                        changed |= add(o, p, s)
            if p in transitive:
                forward: dict = {}
                for s, o in pairs:
                    forward.setdefault(s, set()).add(o)
                for s, o in pairs:
                    for z in forward.get(o, ()):
                        changed |= add(s, p, z)


def _drop_temp_ontology(expanded: Graph) -> None:
    """The reasoners read the graph from a temporary ``.../graph.owl`` file, and when the input declares no ontology IRI they
    name the ontology after that file (owlready2 with no file name uses ``http://anonymous``), so the result carries
    ``<file:///tmp/.../graph.owl> a owl:Ontology``: a name that is no part of the user's data and made two runs of the same
    input differ. Removes that declaration."""
    for s in {s for s in expanded.subjects(RDF.type, OWL.Ontology)
              if isinstance(s, URIRef) and (str(s) == _ANONYMOUS_ONTOLOGY
                                            or (str(s).startswith("file:///") and str(s).endswith("/graph.owl")))}:
        expanded.remove((s, None, None))


def _complete_type_closure(expanded: Graph) -> None:
    """HermiT's CLI realization output only reports each individual's
    *most specific* known type(s), not every ancestor class up the
    hierarchy (confirmed live: for a plain `Manager rdfs:subClassOf
    Employee` + `alice a Manager`, HermiT reports `Type(alice, Manager)`
    but never `Type(alice, Employee)`, even though the subClassOf edge
    itself - `SubClassOf(Manager, Employee)` - is reported and present in
    `expanded`). Every other entailment regime infer() supports (all owlrl-backed)
    gives the full transitive rdf:type closure, so this step restores that
    same guarantee here - walks rdfs:subClassOf transitively from each
    individual's reported type(s) and adds every ancestor class as an
    additional rdf:type, mutating `expanded` in place. Purely additive:
    never removes or changes an existing triple, only adds ones already
    implied by what HermiT already reported.
    """
    parents: dict = {}
    for c, _p, parent in expanded.triples((None, RDFS.subClassOf, None)):
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

    new_triples = []
    for ind, _p, cls in expanded.triples((None, RDF.type, None)):
        for ancestor in _ancestors(cls):
            new_triples.append((ind, RDF.type, ancestor))
    for t in new_triples:
        expanded.add(t)
