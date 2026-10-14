"""starlayer.shacl.entailment

Reads and applies a shapes graph's own ``sh:entailment`` declarations
(SHACL 1.2 Core §1.4), and lets ``inference=`` (the keyword every
processing-mode function accepts as a shortcut for declaring entailment
without touching the shapes graph) share that exact same regime - internal
plumbing for ``validate()``/``apply_rules()``/``evaluate()``/
``extract_subgraph()``, not part of the public ``starlayer.shacl`` surface.

Per the spec text, ``sh:entailment`` is a **shapes-graph-level**
declaration ("a shapes graph contains any triple with the predicate
``sh:entailment``"), not scoped to an individual shape, and multiple
declared regimes combine into **one** entailment pass, not one pass per
regime ("the processor MUST provide the entailments for all of the values
of ``sh:entailment``... during the validation process" - plural values,
singular process).

``infer()``/``query()`` (``starlayer.graph``) already speak the real W3C
entailment regime IRIs
(``starlayer.graph.graph.entailment_regimes.ENTAILMENT``), so this module
needs no separate IRI<->string translation table at all: the IRIs read
straight out of ``sh:entailment`` triples are the exact same values
``infer()`` already accepts.

Entailment also sees schema axioms declared only in ``ont_graph`` (the
idiomatic place for ``rdfs:domain``/``rdfs:range``/etc.), not just
``data_graph``.

``inference=`` takes a real ``ENTAILMENT.*`` IRI, or an iterable of them -
the same vocabulary ``sh:entailment`` itself uses - unioned into the
regime set before materializing (the same "multiple regimes combine into
one pass" rule Core §1.4 already gives ``sh:entailment``'s own multiple
declared values), going through the identical
``_apply_entailment_regimes()`` call either way. A caller passing a plain
string (e.g. pySHACL's own ``"rdfs"``/``"owlrl"``/etc. vocabulary) gets
``ValueError`` from ``_apply_entailment_regimes()``'s own
unsupported-regime check, since a plain string is never a member of
``SUPPORTED_REGIMES`` - only real ``ENTAILMENT.*`` IRIs are accepted.
"""

from __future__ import annotations

from typing import Any

from rdflib import Namespace

from starlayer.graph.graph.entailment_regimes import SUPPORTED_REGIMES

SH = Namespace("http://www.w3.org/ns/shacl#")


def declared_entailment_regimes(shacl_graph: Any) -> frozenset:
    """Every distinct object of an ``sh:entailment`` triple anywhere in
    ``shacl_graph`` - not scoped to any one shape's own subject, matching
    the spec's shapes-graph-level declaration.

    Args:
        shacl_graph: The shapes graph to scan.

    Returns:
        The declared ``ENTAILMENT.*`` regime IRIs, or an empty frozenset
        if none are declared (the common case - most shapes graphs rely
        only on the unconditional ``rdf:type``/``rdfs:subClassOf`` "SHACL
        type" closure, which needs no declaration whatsoever).
    """
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
    "compute over a combined view, materialize only what's new" pattern -
    ``combined.infer(mode="delta")`` already excludes everything present
    in either source graph before reasoning ran, so this needs no separate
    bookkeeping to avoid re-adding ``ont_graph``'s own axioms.

    Args:
        data_graph: The graph entailment is applied to. Must already be a
            StarLayerGraph.
        regimes: The ``ENTAILMENT.*`` IRIs to materialize.
        ont_graph: An optional graph unioned in only for computing
            entailment - never copied into the result, never mutated.
        inplace: ``True`` mutates and returns ``data_graph`` itself;
            ``False`` returns a *new* graph (``data_graph``'s own triples
            plus the delta). ``data_graph`` is left completely untouched
            either way when ``ont_graph`` is given, same non-mutation
            guarantee as the ``ont_graph=None`` case.

    Returns:
        The graph to use from here on - ``data_graph`` itself if
        ``inplace``, otherwise a new graph.

    Raises:
        ValueError: If ``regimes`` contains an unsupported entailment
            regime.
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
        return data_graph.infer(entailment=regimes, mode=mode)

    combined = type(data_graph)()
    for t in data_graph:
        combined.add(t)
    for t in ont_graph:
        combined.add(t)
    delta = combined.infer(entailment=regimes, mode="delta")

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

    A no-op (returns ``data_graph`` unchanged, same object either way)
    when ``shacl_graph`` declares no ``sh:entailment`` and ``inference``
    is ``None`` - the overwhelmingly common case. ``shacl_graph`` may
    itself be ``None`` (contributes no declared regimes, same as an empty
    shapes graph).

    Args:
        data_graph: The graph entailment is applied to. Must already be a
            StarLayerGraph (same precondition ``infer()`` itself
            enforces) - every real caller already guarantees this by the
            time entailment needs applying (``validate()``'s own
            ``normalize_graph_inputs()`` call happens first).
        shacl_graph: The shapes graph whose ``sh:entailment`` declarations
            to read. May be ``None``.
        ont_graph: An optional ontology graph, unioned in only for
            computing entailment (see ``_apply_entailment_regimes``).
        inplace: Must be threaded through from the caller's own resolved
            mode options (``resolve_mode_options(...)['inplace']``) - not
            optional/defaulted, since the plain ``"validation"`` mode's
            own ``inplace=False`` guarantee (never mutating the caller's
            data) depends on every caller passing this explicitly rather
            than relying on a default.
        inference: A real ``ENTAILMENT.*`` IRI, or an iterable of them -
            the *same vocabulary* ``sh:entailment`` itself uses, unioned
            into the regime set before materializing (the same "multiple
            regimes combine into one pass" rule Core §1.4 already gives
            ``sh:entailment``'s own multiple declared values). ``None``
            (the default) contributes nothing. This is every
            processing-mode function's own ``inference=`` keyword - a way
            to request entailment without touching the shapes graph.
            Does not accept pySHACL's own string vocabulary
            (``"rdfs"``/``"owlrl"``/etc.) - only real ``ENTAILMENT.*``
            IRIs.

    Returns:
        The graph to use from here on - ``data_graph`` itself if
        ``inplace``, otherwise a new graph.

    Raises:
        ValueError: If a declared or passed entailment regime isn't
            supported (e.g. D-Entailment, or RIF - which has no regime IRI
            at all and so can never even reach here) - this is what
            satisfies Core §1.4's own "the processor MUST signal a
            failure" requirement for an entailment regime it can't
            provide.
    """
    regimes = declared_entailment_regimes(shacl_graph) if shacl_graph is not None else frozenset()
    if inference is not None:
        extra = frozenset(inference) if isinstance(inference, (frozenset, set, tuple, list)) else frozenset({inference})
        regimes = regimes | extra
    return _apply_entailment_regimes(data_graph, regimes, ont_graph, inplace=inplace)
