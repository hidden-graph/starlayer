"""
starlayer.graph.graph.owl_dl

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

engine="hermit" (this module) is one of two engines infer(profile="owl-dl")
can dispatch to - see starlayer.graph.graph.owl_dl_rustdl for the other
(engine="rustdl": no JVM, but sound-not-provably-complete rather than
sound-and-complete - a real, permanent gap against this module's own
guarantee, not a bug in either). Both engines' Python packages are optional
extras (`pip install starlayer.graph[hermit]` / `[rustdl]`), not core
dependencies - `owlready2` used to be core, moved to opt-in alongside
`rustdl` for a consistent story across both rather than one being special.
A real Java runtime on PATH is the one prerequisite `pip` alone still can't
satisfy for this engine specifically: owlready2 bundles Java HermiT and
needs a real JVM at runtime to run it - see `_require_java()` below.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from rdflib import RDF, RDFS, Graph

from starlayer.graph.graph import _timeout


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
            "StarLayerGraph.infer(profile='owl-dl', engine='hermit') "
            "requires the optional owlready2 package - install it with "
            "`pip install starlayer.graph[hermit]` (or `pip install "
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
            "StarLayerGraph.infer(profile='owl-dl') requires a Java runtime "
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
    profiles, so infer()'s mode="full"/"delta"/"in-place" branches can
    treat both engines uniformly without knowing which one ran.

    Raises InconsistentOntologyError if the data is logically inconsistent
    under OWL 2 DL semantics.

    timeout -- wall-clock budget in seconds for the actual HermiT call
        (default `_timeout.DEFAULT_TIMEOUT_SECONDS`, 120s) - the call runs
        in its own subprocess/process group so it can be forcibly killed,
        JVM child included, if it's exceeded; raises
        `_timeout.ReasoningTimeoutError`. Pass `None` to disable the
        timeout entirely (wait indefinitely - the pre-this-feature
        behavior). See `_timeout.py`'s own module docstring for why a
        subprocess kill, not a cooperative cancellation, is the only
        mechanism that reliably works here.
    """
    owlready2 = _require_owlready2()
    _require_java()

    from starlayer.graph.compare import _decompose
    before = _decompose(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        owl_path = Path(tmp_dir) / "graph.owl"
        before.serialize(destination=str(owl_path), format='xml')
        result_path = Path(tmp_dir) / "result.owl"

        status, message = _timeout.run_with_timeout(
            _run_hermit_subprocess, (str(owl_path), str(result_path)), timeout,
        )
        if status == 'inconsistent':
            raise InconsistentOntologyError(
                "infer(profile='owl-dl') found self's data logically "
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
                "StarLayerGraph.infer(profile='owl-dl') found `java` on PATH, "
                "but it failed to run HermiT - the JVM itself is broken or "
                f"misconfigured, not just missing. {message}"
            )

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
