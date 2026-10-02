"""A recorded snapshot of every plain-rdflib method and property
``StarLayerGraph``/``StarLayerDataset`` inherit **unchanged** - never
overridden anywhere in this project's own code, reaching a caller purely
via Python's normal inheritance.

**Why this exists.** Relying on plain inheritance for these methods is the
right call (duplicating ~38 method bodies as do-nothing wrappers just to
"be explicit" would mean manually tracking every future rdflib signature
change forever, for methods this project doesn't actually modify - a real,
ongoing maintenance cost for no behavioral benefit). But "we accept
whatever rdflib gives us here" shouldn't mean "we never notice if that
changes." This file is the deliberate, written-down record of what we
currently know about each one - consumed two ways:

1. ``tests/graph/unit/test_rdflib_inherited_contract.py`` re-introspects
   each entry's real, live signature on every test run and asserts it
   still matches ``signature`` below - a future rdflib upgrade that
   changes one of these (renamed/reordered/added parameter, changed
   return type) fails loudly and visibly, forcing a deliberate update to
   this file, rather than ``docs/api-reference.md`` silently going stale.
2. ``docs/api-reference.md``'s generation step reads ``returns`` from here
   to populate the Returns column for these rows - most of rdflib's own
   methods already carry a real return-type annotation (introspectable
   directly, no need to duplicate it here), but a few genuinely don't
   (``transitiveClosure`` - see its own entry below) and need a
   hand-derived value recorded once, by a human who actually read the
   source.

**Scope**: only the ``Unchanged`` rows in the ``StarLayerGraph``/
``StarLayerDataset`` member tables - i.e. methods this project's own code
never touches. ``New``/``Modified`` methods are StarLayer's own code and
should carry real type annotations at their own definition site instead of
being recorded here - that's a separate, still-open piece of work (adding
annotations to ``starlayer_graph.py``/``starlayer_dataset.py``'s own
method definitions), not something this file is meant to stand in for.

**Recorded against**: rdflib 7.x, as installed when this file was last
updated (2026-10-02). If the drift test ever fails, don't just paste in
the new signature and move on - check *why* it changed (a real behavior
change vs. a cosmetic typing update) before updating the entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InheritedMethodContract:
    """One inherited-and-unchanged method's recorded signature/return type.

    ``owner`` names which class (``"StarLayerGraph"`` or
    ``"StarLayerDataset"``) the drift test should introspect - for a method
    present on both with the exact same underlying function object (true
    for most of these; confirmed live), it doesn't matter which one is
    checked. For the few where StarLayerGraph *does* override the method
    (``triples_choices``/``isomorphic`` - Modified on Graph, but still
    plain-inherited on Dataset), ``owner`` deliberately points at
    ``StarLayerDataset``, the genuinely-unchanged occurrence. (``cbd`` used
    to be a third example here too, until StarLayerDataset got its own
    ``cbd()`` override - see that method's own docstring for the real bug
    that motivated it. No longer anything to record in this file.)
    """

    owner: str
    signature: str
    returns: str
    hand_authored_returns: bool = False


@dataclass(frozen=True)
class InheritedPropertyContract:
    """One inherited-and-unchanged property's recorded return type.

    No ``signature`` field (a property takes no arguments by definition -
    there's nothing to drift there beyond whether it still exists), just
    ``returns``, keyed by ``(owner, name)`` since - unlike most of the
    methods above - ``identifier`` genuinely has a *different* underlying
    function per class (``StarLayerDataset.identifier`` is rdflib's own
    deprecation-warning wrapper around ``StarLayerGraph.identifier``'s
    value, confirmed live: different ``fget`` objects, and accessing it on
    a ``Dataset`` actually emits a ``DeprecationWarning`` at runtime).
    ``deprecated`` records that distinction so the drift test (and anyone
    reading this file) doesn't mistake the two for identical.
    """

    returns: str
    hand_authored_returns: bool = False
    deprecated: str | None = None  # the real DeprecationWarning message, if any, confirmed by actually triggering it


INHERITED_PROPERTY_CONTRACTS: dict[tuple[str, str], InheritedPropertyContract] = {
    ("StarLayerGraph", "identifier"): InheritedPropertyContract(
        returns="URIRef | BNode",
    ),
    ("StarLayerDataset", "identifier"): InheritedPropertyContract(
        returns="URIRef | BNode",
        deprecated="Dataset.identifier is deprecated and will be removed in future versions.",
    ),
    ("StarLayerGraph", "namespace_manager"): InheritedPropertyContract(
        returns="NamespaceManager",
    ),
    ("StarLayerDataset", "namespace_manager"): InheritedPropertyContract(
        returns="NamespaceManager",
    ),
    ("StarLayerGraph", "store"): InheritedPropertyContract(
        returns="Store",
    ),
    ("StarLayerDataset", "store"): InheritedPropertyContract(
        returns="Store",
    ),
    ("StarLayerDataset", "default_context"): InheritedPropertyContract(
        # Was "Graph" until StarLayerDataset.__init__ was fixed to build
        # self._default_context via get_context() instead of rdflib's own
        # hardcoded plain Graph() - see __init__'s own comment for the real
        # bug this fixed (default_graph.add() crashing on a TripleTerm).
        returns="StarLayerGraph",
        hand_authored_returns=True,  # rdflib's own source has no return annotation here - derived by reading the source
        deprecated="Dataset.default_context is deprecated, use Dataset.default_graph instead.",
    ),
    ("StarLayerDataset", "default_graph"): InheritedPropertyContract(
        # same fix as default_context above - see its comment.
        returns="StarLayerGraph",
        hand_authored_returns=True,  # rdflib's own source has no return annotation here - derived by reading the source
    ),
}


INHERITED_METHOD_CONTRACTS: dict[str, InheritedMethodContract] = {
    "add_graph": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, g: 'Optional[Union[_ContextIdentifierType, _ContextType, str]]') -> 'Graph'",
        # rdflib's own annotation says Graph (accurate for a plain rdflib.Dataset),
        # but add_graph() -> graph() -> _graph() -> self.get_context() internally,
        # and get_context() IS overridden on StarLayerDataset to construct a real
        # StarLayerGraph - confirmed live, not assumed (see test_rdflib_inherited_contract.py
        # and the chat transcript this was verified in). returns intentionally more
        # precise than the live `signature` annotation above.
        returns="StarLayerGraph",
    ),
    "all_nodes": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self) -> 'Set[Node]'",
        returns="Set[Node]",
    ),
    "bind": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, prefix: 'Optional[str]', namespace: 'Any', override: 'bool' = True, replace: 'bool' = False) -> 'None'",
        returns="None",
    ),
    "collection": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, identifier: '_SubjectType') -> 'Collection'",
        returns="Collection",
    ),
    "commit": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self: '_GraphT') -> '_GraphT'",
        returns="self (same graph/dataset)",
    ),
    "compute_qname": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, uri: 'str', generate: 'bool' = True) -> 'Tuple[str, URIRef, str]'",
        returns="Tuple[str, URIRef, str]",
    ),
    "connected": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self) -> 'bool'",
        returns="bool",
    ),
    "context_id": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, uri: 'str', context_id: 'Optional[str]' = None) -> 'URIRef'",
        returns="URIRef",
    ),
    "destroy": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self: '_GraphT', configuration: 'str') -> '_GraphT'",
        returns="self (same graph/dataset)",
    ),
    "get_graph": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, identifier: '_ContextIdentifierType') -> 'Union[Graph, None]'",
        # self.contexts() (called internally) is overridden to yield StarLayerGraph,
        # so a hit returns one - but the Optional in rdflib's own annotation is
        # itself misleading: a miss raises IndexError, never returns None.
        # Confirmed live, a pre-existing rdflib bug, not a StarLayer one - see
        # docs/api-reference.md's own row for this method for the full note.
        returns="Optional[StarLayerGraph]",
    ),
    "graph": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, identifier: 'Optional[Union[_ContextIdentifierType, _ContextType, str]]' = None, base: 'Optional[str]' = None) -> 'Graph'",
        # same divergence as add_graph() above (which just calls this) - see its comment.
        returns="StarLayerGraph",
    ),
    "graphs": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, triple: 'Optional[_TripleType]' = None) -> 'Generator[_ContextType, None, None]'",
        # Was "Generator[Graph, ...]" until StarLayerDataset.__init__'s own
        # _default_context fix (see __init__'s comment) - graphs() yields from
        # super(Dataset, self).contexts(), which returns whatever
        # self._default_context actually is; now that's a StarLayerGraph too.
        returns="Generator[StarLayerGraph, None, None]",
    ),
    "isomorphic": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, other: 'Graph') -> 'bool'",
        returns="bool",
    ),
    "items": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, list: 'Node') -> 'Generator[Node, None, None]'",
        returns="Generator[Node, None, None]",
    ),
    "n3": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, namespace_manager: 'Optional[NamespaceManager]' = None) -> 'str'",
        returns="str",
    ),
    "namespaces": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self) -> 'Generator[Tuple[str, URIRef], None, None]'",
        returns="Generator[Tuple[str, URIRef], None, None]",
    ),
    "objects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, subject: 'Optional[Union[_SubjectType, List[_SubjectType]]]' = None, predicate: 'Union[None, Path, _PredicateType]' = None, unique: 'bool' = False) -> 'Generator[_ObjectType, None, None]'",
        returns="Generator[Node, None, None]",
    ),
    "predicate_objects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, subject: 'Optional[_SubjectType]' = None, unique: 'bool' = False) -> 'Generator[Tuple[_PredicateType, _ObjectType], None, None]'",
        returns="Generator[Tuple[Node, Node], None, None]",
    ),
    "predicates": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, subject: 'Optional[_SubjectType]' = None, object: 'Optional[_ObjectType]' = None, unique: 'bool' = False) -> 'Generator[_PredicateType, None, None]'",
        returns="Generator[Node, None, None]",
    ),
    "print": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, format: 'str' = 'turtle', encoding: 'str' = 'utf-8', out: 'Optional[TextIO]' = None) -> 'None'",
        returns="None",
    ),
    "qname": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, uri: 'str') -> 'str'",
        returns="str",
    ),
    "remove_context": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, context: '_ContextType') -> 'None'",
        returns="None",
    ),
    "remove_graph": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self: '_DatasetT', g: 'Optional[Union[_ContextIdentifierType, _ContextType, str]]') -> '_DatasetT'",
        returns="self (same dataset)",
    ),
    "resource": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, identifier: 'Union[Node, str]') -> 'Resource'",
        returns="Resource",
    ),
    "rollback": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self: '_GraphT') -> '_GraphT'",
        returns="self (same graph/dataset)",
    ),
    "set": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self: '_GraphT', triple: 'Tuple[_SubjectType, _PredicateType, _ObjectType]') -> '_GraphT'",
        returns="self (same graph)",
    ),
    "subject_objects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, predicate: 'Union[None, Path, _PredicateType]' = None, unique: 'bool' = False) -> 'Generator[Tuple[_SubjectType, _ObjectType], None, None]'",
        returns="Generator[Tuple[Node, Node], None, None]",
    ),
    "subject_predicates": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, object: 'Optional[_ObjectType]' = None, unique: 'bool' = False) -> 'Generator[Tuple[_SubjectType, _PredicateType], None, None]'",
        returns="Generator[Tuple[Node, Node], None, None]",
    ),
    "subjects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, predicate: 'Union[None, Path, _PredicateType]' = None, object: 'Optional[Union[_ObjectType, List[_ObjectType]]]' = None, unique: 'bool' = False) -> 'Generator[_SubjectType, None, None]'",
        returns="Generator[Node, None, None]",
    ),
    "toPython": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self: '_GraphT') -> '_GraphT'",
        returns="self (a Graph is its own Python-value form)",
    ),
    "transitiveClosure": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, func: 'Callable[[_TCArgT, Graph], Iterable[_TCArgT]]', arg: '_TCArgT', seen: 'Optional[Dict[_TCArgT, int]]' = None)",
        returns="Generator[Node, None, None]",
        hand_authored_returns=True,  # rdflib's own source has no return annotation here, despite being a generator (confirmed via `yield` in its body) - derived by reading the source, not introspected
    ),
    "transitive_objects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, subject: 'Optional[_SubjectType]', predicate: 'Optional[_PredicateType]', remember: 'Optional[Dict[Optional[_SubjectType], int]]' = None) -> 'Generator[Optional[_SubjectType], None, None]'",
        returns="Generator[Optional[Node], None, None]",
    ),
    "transitive_subjects": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, predicate: 'Optional[_PredicateType]', object: 'Optional[_ObjectType]', remember: 'Optional[Dict[Optional[_ObjectType], int]]' = None) -> 'Generator[Optional[_ObjectType], None, None]'",
        returns="Generator[Optional[Node], None, None]",
    ),
    "triples_choices": InheritedMethodContract(
        owner="StarLayerDataset",
        signature="(self, triple: '_TripleChoiceType', context: 'Optional[_ContextType]' = None) -> 'Generator[_TripleType, None, None]'",
        returns="Generator[Triple, None, None]",
    ),
    "value": InheritedMethodContract(
        owner="StarLayerGraph",
        signature="(self, subject: 'Optional[_SubjectType]' = None, predicate: 'Optional[_PredicateType]' = rdflib.term.URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#value'), object: 'Optional[_ObjectType]' = None, default: 'Optional[Node]' = None, any: 'bool' = True) -> 'Optional[Node]'",
        returns="Optional[Node]",
    ),
}
