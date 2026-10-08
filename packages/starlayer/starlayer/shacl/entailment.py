"""starlayer.shacl.entailment

Reads and applies a shapes graph's own ``sh:entailment`` declarations
(SHACL 1.2 Core §1.4), and lets ``inference=`` (the keyword every
processing-mode function accepts as a shortcut for declaring entailment
without touching the shapes graph) share that exact same regime - internal
plumbing for ``validate()``/``apply_rules()``/``evaluate()``/
``extract_subgraph()``, not part of the public ``starlayer.shacl`` surface.

Confirmed directly against the live spec text, not guessed: ``sh:entailment``
is a **shapes-graph-level** declaration ("a shapes graph contains any triple
with the predicate ``sh:entailment``"), not scoped to an individual shape,
and multiple declared regimes combine into **one** entailment pass, not one
pass per regime ("the processor MUST provide the entailments for all of the
values of ``sh:entailment``... during the validation process" - plural
values, singular process).

Thanks to ``starlayer.graph``/``starlayer.sparql`` having already migrated
``infer()``/``query()`` onto the real W3C regime IRIs
(``starlayer.graph.graph.entailment_regimes.ENTAILMENT``, 2026-10-07), this
module needs no separate IRI<->string translation table at all: the IRIs
read straight out of ``sh:entailment`` triples are the exact same values
``infer()`` already accepts.

**2026-10-07 - ``ont_graph`` support**: entailment now sees schema axioms
declared only in ``ont_graph`` too (the idiomatic place for
``rdfs:domain``/``rdfs:range``/etc.), not just ``data_graph``.

**2026-10-08 - ``inference=`` disconnected from pySHACL's own string
vocabulary, on direct user instruction** ("I think we wanted to use those
keywords to drive the inference in pyshacl. and disconnect from the
pyshacl strings"). Previously (2026-10-07) ``inference=`` accepted
pySHACL's own ad-hoc strings (``"rdfs"``/``"owlrl"``/``"both"``/``"all"``/
``"rdfsowlrl"``/``"none"``) as a drop-in replacement for callers porting
from plain ``pyshacl.validate(..., inference=...)``, routed through a
separate ``_apply_pyshacl_inference()`` that replicated pySHACL's own
particular ``CustomRDFSSemantics``/``CustomRDFSOWLRLSemantics`` choice for
``"rdfs"``/``"both"`` (a real, verified wrinkle: pySHACL doesn't use plain
``owlrl.RDFS_Semantics`` for those, to avoid owlrl's "hidden sameAs" rule
cross-contaminating literals - see the git history of this docstring for
the full account). That whole mechanism is **removed**, not just changed:
``inference=`` now takes a real ``ENTAILMENT.*`` IRI (or an iterable of
them, combining regimes the same way multiple declared ``sh:entailment``
values already do) - the *exact same* value ``sh:entailment`` itself uses.
A caller passing the old pySHACL strings now gets ``ValueError`` from
``_apply_entailment_regimes()``'s own unsupported-regime check (a plain
string is never a member of ``SUPPORTED_REGIMES``), not a silent
behavior change - there was no way to keep both without the keyword
meaning two different things depending on what was passed. pySHACL's own
particular ``CustomRDFSSemantics`` quirk no longer matters: nothing here
claims pySHACL-string compatibility any more, so the general-purpose
``ENTAILMENT.RDFS`` dispatch (plain ``owlrl.RDFS_Semantics``, already used
for ``sh:entailment``) is the only RDFS implementation needed - one
regime dispatch, one vocabulary, for both entailment pathways.
``apply_entailment()``'s own ``inference=`` parameter is simply merged
into whatever ``shacl_graph`` declares before materializing, both going
through the identical ``_apply_entailment_regimes()`` call.
"""

from __future__ import annotations

from typing import Any

from rdflib import Namespace

from starlayer.graph.graph.entailment_regimes import SUPPORTED_REGIMES

SH = Namespace("http://www.w3.org/ns/shacl#")


def declared_entailment_regimes(shacl_graph: Any) -> frozenset:
    """Every distinct object of an ``sh:entailment`` triple anywhere in
    ``shacl_graph`` - not scoped to any one shape's own subject, matching
    the spec's shapes-graph-level declaration. Empty if none are declared
    (the common case - most shapes graphs declare no entailment regime at
    all, relying only on the unconditional ``rdf:type``/``rdfs:subClassOf``
    "SHACL type" closure that needs no declaration whatsoever)."""
    return frozenset(shacl_graph.objects(None, SH.entailment))


def _apply_entailment_regimes(data_graph: Any, regimes: frozenset, ont_graph: Any | None = None, *, inplace: bool) -> Any:
    """Materialize ``regimes`` (a frozenset of ``ENTAILMENT.*`` IRIs) over
    ``data_graph`` and return the graph to use from here on.

    When ``ont_graph`` is given, entailment is *computed* over
    ``data_graph`` union ``ont_graph`` (so an axiom declared only in
    ``ont_graph``, e.g. ``rdfs:domain``, is actually seen) - but only the
    newly-entailed **delta** is ever materialized back into the result;
    ``ont_graph``'s own raw triples are never copied in, and ``ont_graph``
    itself is never mutated. This mirrors ``infer(mode="delta")``'s own
    established "compute over a combined view, materialize only what's
    new" pattern - ``combined.infer(mode="delta")`` already excludes
    everything that was present in either source graph before reasoning
    ran, so this needs no separate bookkeeping to avoid re-adding
    ``ont_graph``'s own axioms.

    Respects the same ``inplace`` contract ``apply_entailment()`` already
    established: ``True`` mutates and returns ``data_graph`` itself;
    ``False`` returns a *new* graph (``data_graph``'s own triples plus the
    delta) - ``data_graph`` is left completely untouched either way when
    ``ont_graph`` is given, same non-mutation guarantee already proven for
    the ``ont_graph=None`` case.
    """
    if not regimes:
        return data_graph
    unsupported = regimes - SUPPORTED_REGIMES
    if unsupported:
        raise ValueError(
            f"Unsupported entailment regime(s) {sorted(unsupported)!r} - "
            f"expected a combination of {sorted(SUPPORTED_REGIMES)!r}."
        )
    if ont_graph is None:
        mode = "in-place" if inplace else "full"
        return data_graph.infer(profile=regimes, mode=mode)

    combined = type(data_graph)()
    for t in data_graph:
        combined.add(t)
    for t in ont_graph:
        combined.add(t)
    delta = combined.infer(profile=regimes, mode="delta")

    if inplace:
        for t in delta:
            data_graph.add(t)
        return data_graph

    result = type(data_graph)()
    for prefix, ns in data_graph.namespaces():
        result.bind(prefix, ns)
    for t in data_graph:
        result.add(t)
    for t in delta:
        result.add(t)
    return result


def apply_entailment(
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any | None = None,
    *,
    inplace: bool,
    inference: Any | None = None,
) -> Any:
    """Materialize ``shacl_graph``'s own declared ``sh:entailment``
    regime(s) over ``data_graph`` (and ``ont_graph``, if given - see
    ``_apply_entailment_regimes``'s own docstring for exactly how), merged
    with whatever ``inference`` contributes, and return the graph to use
    from here on - which is ``data_graph`` itself only when
    ``inplace=True``.

    ``inference`` (2026-10-08) is a real ``ENTAILMENT.*`` IRI, or an
    iterable of them - the *same vocabulary* ``sh:entailment`` itself
    uses, simply unioned into the regime set before materializing (the
    same "multiple regimes combine into one pass" rule Core §1.4 already
    gives ``sh:entailment``'s own multiple declared values). ``None``
    (the default) contributes nothing. This is every processing-mode
    function's own ``inference=`` keyword - a way to request entailment
    without touching the shapes graph, not a separate mechanism. See this
    module's own docstring for why it no longer accepts pySHACL's own
    string vocabulary.

    ``inplace`` must be threaded through from the caller's own resolved
    profile options (``resolve_profile_options(...)['inplace']``) - it is
    **not** optional/defaulted, on purpose: an earlier version of this
    function always mutated ``data_graph`` in place regardless, which
    silently broke ``validate()``'s own documented guarantee that the
    plain ``"validation"`` profile (``inplace=False``) never mutates the
    caller's data - confirmed live via a real regression (``len(data)``
    grew after a plain ``validate()`` call that happened to use
    ``sh:entailment``) before this parameter was added.

    A no-op (returns ``data_graph`` unchanged, same object either way)
    when ``shacl_graph`` declares no ``sh:entailment`` and ``inference``
    is ``None`` - the overwhelmingly common case. ``shacl_graph`` may
    itself be ``None`` (contributes no declared regimes, same as an empty
    shapes graph) - several callers (e.g. ``evaluate()``) always have one,
    but this stays safe either way rather than requiring every call site
    to guard it. Raises ``ValueError`` naming the exact unsupported
    regime IRI if one is declared/passed that ``infer()`` doesn't support
    (e.g. D-Entailment, or RIF - which has no regime IRI at all and so
    can never even reach here) - this is what satisfies Core §1.4's own
    "the processor MUST signal a failure" requirement for an entailment
    regime it can't provide.

    ``data_graph`` must already be a ``StarLayerGraph`` (same precondition
    ``infer()`` itself enforces) - every real caller already guarantees
    this by the time entailment needs applying (``validate()``'s own
    ``normalize_graph_inputs()`` call happens first).
    """
    regimes = declared_entailment_regimes(shacl_graph) if shacl_graph is not None else frozenset()
    if inference is not None:
        extra = frozenset(inference) if isinstance(inference, (frozenset, set, tuple, list)) else frozenset({inference})
        regimes = regimes | extra
    return _apply_entailment_regimes(data_graph, regimes, ont_graph, inplace=inplace)
