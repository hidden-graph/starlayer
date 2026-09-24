"""
starlayergraph.graph.owl_dl

OWL 2 Direct Semantics reasoning via owlready2 + Java HermiT - a genuinely
different computational model (tableau-based DL reasoning, with real
disjunctive case-splitting and sound-and-complete consistency checking)
from every other profile StarLayerGraph.infer() supports, all of which run
owlrl's forward-chaining rule engine. See infer()'s own docstring for the
profile="owl-dl" contract; this module is the bridge that makes it work.

Deliberately HermiT only, never Pellet (owlready2 bundles both behind
sync_reasoner()/sync_reasoner_pellet()): HermiT is LGPL, Pellet is AGPL - a
materially stronger copyleft obligation - and one conformant OWL 2 DL
reasoner is sufficient to cover this regime. sync_reasoner_pellet() is
never called anywhere in this module.

``owlready2`` is a normal (core) dependency of this package, so `pip install
starlayergraph` brings it in automatically - unlike the pure-Python `owlrl`
path every other profile uses, there is one prerequisite this can't
satisfy: a real Java runtime on PATH. owlready2 bundles Java HermiT and
needs a real JVM at runtime to run it - see `_require_java()` below.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import owlready2
from rdflib import RDF, RDFS, Graph


class InconsistentOntologyError(RuntimeError):
    """Raised when profile="owl-dl" finds self's data logically
    inconsistent under OWL 2 DL semantics - e.g. an individual typed as two
    classes declared owl:disjointWith each other. Unlike profile="owl-rl"
    (whose consistency checking, via owlrl, is partial and silently embeds
    a synthetic err:error triple into the result instead of raising - see
    infer()'s own docstring), HermiT's check is sound and complete, so an
    inconsistency here is surfaced as an unmissable exception rather than
    left for the caller to notice on their own.
    """


def _require_java() -> None:
    """Confirm a real Java runtime is reachable. `owlready2` itself is a
    normal dependency, always installed - this is the one prerequisite
    that can't be: owlready2's HermiT reasoner is a Java program, not a
    pure-Python one.
    """
    if shutil.which("java") is None:
        raise RuntimeError(
            "StarLayerGraph.infer(profile='owl-dl') requires a Java runtime "
            "on PATH - owlready2's HermiT reasoner is a Java program, not a "
            "pure-Python one. Install a JRE/JDK (e.g. `brew install openjdk` "
            "on macOS, or your platform's package manager) and confirm "
            "`java -version` works, then retry."
        )


def classify_owl_dl(graph):
    """Run OWL 2 DL classification (HermiT, via owlready2) over `graph`,
    returning (before, delta) in the same shape
    StarLayerGraph._infer_before_and_delta() returns for the owlrl-backed
    profiles, so infer()'s mode="full"/"delta"/"in-place" branches can
    treat both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent
    under OWL 2 DL semantics.
    """
    _require_java()

    from starlayergraph.compare import _decompose
    before = _decompose(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        before.serialize(destination=str(owl_path), format='xml')

        # A fresh, disposable World per call - never owlready2's
        # process-global default_world - so concurrent/repeated infer()
        # calls never see each other's data. sync_reasoner() must be
        # called with this world passed explicitly: bare sync_reasoner()
        # silently reasons over the (likely empty, or wrong) default_world
        # instead - confirmed live, a real footgun in owlready2's own API.
        world = owlready2.World()
        onto = world.get_ontology(f"file://{owl_path}").load()

        try:
            with onto:
                owlready2.sync_reasoner(world, infer_property_values=True, debug=0)
        except owlready2.OwlReadyInconsistentOntologyError as exc:
            raise InconsistentOntologyError(
                "infer(profile='owl-dl') found self's data logically "
                "inconsistent under OWL 2 DL semantics."
            ) from exc
        except owlready2.OwlReadyJavaError as exc:
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
                "StarLayerGraph.infer(profile='owl-dl') found `java` on PATH, "
                "but it failed to run HermiT - the JVM itself is broken or "
                f"misconfigured, not just missing. {exc}"
            ) from exc

        result_path = Path(tmp_dir) / "result.owl"
        world.save(str(result_path), format='rdfxml')
        expanded = Graph()
        expanded.parse(str(result_path), format='xml')

    _complete_type_closure(expanded)

    before_set = set(before)
    delta = Graph()
    for t in expanded:
        if t not in before_set:
            delta.add(t)
    return before, delta


def _complete_type_closure(expanded: Graph) -> None:
    """HermiT's CLI realization output only reports each individual's
    *most specific* known type(s), not every ancestor class up the
    hierarchy (confirmed live: for a plain `Manager rdfs:subClassOf
    Employee` + `alice a Manager`, HermiT reports `Type(alice, Manager)`
    but never `Type(alice, Employee)`, even though the subClassOf edge
    itself - `SubClassOf(Manager, Employee)` - is reported and present in
    `expanded`). Every other profile infer() supports (all owlrl-backed)
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
