"""Confirms every entry in ``_rdflib_inherited_contract.INHERITED_METHOD_CONTRACTS``
still matches the real, live signature of the rdflib method it describes.

These ~38 methods are never overridden anywhere in this project's own code
- they reach a ``StarLayerGraph``/``StarLayerDataset`` caller purely via
plain Python inheritance from rdflib's own ``Graph``/``Dataset`` classes.
That's the right design (see the contract module's own docstring for why
explicit wrappers would be worse), but it means a future rdflib upgrade
could silently change one of these - a renamed parameter, a different
return type, a dropped default - with nothing in this codebase noticing.
This test is that notice: a real, deliberate assertion instead of quietly
trusting whatever rdflib happens to ship.

If this test fails after an rdflib upgrade: don't just copy the new
signature into the contract file and move on. Read *why* it changed first
(a real behavior change this project's docs/users should know about, vs. a
cosmetic typing-only update) - then update the entry and, if it's a real
behavior change, check whether `docs/api-reference.md`'s own description
for that row still holds.
"""

import inspect
import warnings

from starlayer import StarLayerDataset, StarLayerGraph
from starlayer.graph.graph._rdflib_inherited_contract import (
    INHERITED_METHOD_CONTRACTS,
    INHERITED_PROPERTY_CONTRACTS,
)

_OWNERS = {"StarLayerGraph": StarLayerGraph, "StarLayerDataset": StarLayerDataset}


def test_every_contract_entry_matches_the_live_signature() -> None:
    mismatches = []
    for name, contract in INHERITED_METHOD_CONTRACTS.items():
        cls = _OWNERS[contract.owner]
        attr = getattr(cls, name)
        live_signature = str(inspect.signature(attr))
        if live_signature != contract.signature:
            mismatches.append(
                f"{contract.owner}.{name}:\n"
                f"  recorded: {contract.signature}\n"
                f"  live:     {live_signature}"
            )
    assert not mismatches, "rdflib signature drift detected:\n\n" + "\n\n".join(mismatches)


def test_hand_authored_returns_are_still_genuinely_unannotated() -> None:
    """Entries flagged ``hand_authored_returns=True`` exist because rdflib's
    own source had no return annotation to introspect at the time this file
    was written. If rdflib later adds one, the hand-authored value in this
    file becomes redundant (and could quietly drift from the real one) -
    this test catches that so the entry can be switched back to
    introspection instead of staying hand-maintained forever."""
    still_unannotated = []
    for name, contract in INHERITED_METHOD_CONTRACTS.items():
        if not contract.hand_authored_returns:
            continue
        cls = _OWNERS[contract.owner]
        sig = inspect.signature(getattr(cls, name))
        if sig.return_annotation is not inspect.Signature.empty:
            still_unannotated.append(name)
    assert not still_unannotated, (
        f"rdflib now annotates the return type for: {still_unannotated} - "
        "update the contract entry to use introspection instead of the "
        "hand-authored value."
    )


def test_every_property_contract_entry_still_exists_and_is_a_property() -> None:
    """Properties have no signature to drift (they take no arguments), so
    the one thing worth confirming on every run is simpler: the attribute
    still exists and is still a real ``property`` (rdflib could in theory
    turn one into a plain method, or remove it, in a future version)."""
    for (owner, name), contract in INHERITED_PROPERTY_CONTRACTS.items():
        cls = _OWNERS[owner]
        attr = cls.__dict__.get(name) or getattr(cls, name)
        assert isinstance(attr, property), f"{owner}.{name} is no longer a property"


def test_property_deprecation_warnings_still_fire_as_recorded() -> None:
    """Entries recording a ``deprecated`` message exist because accessing
    that property genuinely emits a ``DeprecationWarning`` today (confirmed
    live, not assumed) - if rdflib ever actually removes the deprecated
    property instead of just warning about it, this catches that too (the
    attribute access itself would raise instead of warn)."""
    instances = {"StarLayerGraph": StarLayerGraph(), "StarLayerDataset": StarLayerDataset()}
    for (owner, name), contract in INHERITED_PROPERTY_CONTRACTS.items():
        if contract.deprecated is None:
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            getattr(instances[owner], name)
        messages = [str(w.message) for w in caught]
        assert contract.deprecated in messages, (
            f"{owner}.{name}: expected DeprecationWarning {contract.deprecated!r}, got {messages!r}"
        )
