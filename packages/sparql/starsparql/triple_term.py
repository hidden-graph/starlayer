"""``TripleTermNode`` — the algebra-tree representation of a SPARQL 1.2
``<<( s p o )>>``/``TRIPLE(s, p, o)`` triple term.

A plain ``CompValue('TripleTerm', subject=, predicate=, object=)`` node
cannot survive rdflib's own ``algebra.translateQuery``/``translateUpdate``
unmodified: ``reorderTriples``/``_knownTerms`` (BGP join-order optimization)
require every triple-pattern term to be hashable, and a bare ``CompValue``
(an ``OrderedDict`` subclass) is not. A further, less obvious requirement
found empirically: when two triples tie on ``_knownTerms``' sort key (common
for fully-ground triples), rdflib's own sort falls back to comparing the raw
triples with ``<``, so the term must be *orderable* too, not merely hashable.

Subclassing ``CompValue`` (rather than substituting some other, unrelated
hashable object) is what makes this safe on both fronts: rdflib's
``_addVars``/``analyse`` bookkeeping pass walks the tree via a generic
recursive traversal (``_traverseAgg``) that is closed over
``CompValue``/``list``/``tuple``/``ParseResults`` — nothing else. A
non-``CompValue`` proxy would make any ``Variable`` nested inside a
pattern-with-variables triple term invisible to that traversal, silently
under-computing ``_vars`` on every ancestor node. A ``CompValue`` subclass
does not have this problem: the existing generic recursion already finds
nested variables correctly, for free.
"""

from __future__ import annotations

from rdflib.plugins.sparql.parserutils import CompValue


class InvalidTripleTermError(ValueError):
    """A triple term is being used somewhere RDF 1.2 never permits one.
    Covers two distinct rules, both enforced here as hard backstops
    regardless of construction path (parsed from SPARQL 1.2 text, decoded
    from RDF via ``from_rdf.py``, or built programmatically) rather than
    relying on the grammar alone to reject them:

    **1. A triple term's own subject/predicate slot is itself a triple
    term** — illegal per RDF 1.2's grammar
    (https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm):

        tripleTerm ::= '<<(' ttSubject verb ttObject ')>>'
        ttSubject  ::= iri | BlankNode
        ttObject   ::= iri | BlankNode | literal | tripleTerm

    Neither ``ttSubject`` nor ``verb`` (the predicate production) has a
    ``tripleTerm`` alternative — unconditionally, not just when the triple
    term is used as an expression value. Nesting a triple term is legal
    only in *object* position, where ``ttObject`` explicitly allows it.
    Enforced by ``TripleTermNode.validate()``/``_reject_nested_triple_term``
    below, called at every construction site.

    **2. A whole triple term is used as the *subject* of an ordinary
    triple/quad pattern** (one level up from rule 1 — not nested *inside*
    another triple term at all, just an everyday `<<( s p o )>> :q :r .`
    pattern) — illegal per RDF 1.2 Concepts' own normative triple-formation
    rules (https://www.w3.org/TR/rdf12-concepts/#section-triple-terms),
    quoted directly, not paraphrased:

        "If s is an IRI or a blank node, p is an IRI, and o is an RDF
        triple, then (s, p, o) is an RDF triple."

    That is the *only* rule admitting a triple term anywhere in a triple,
    and it only ever permits one as ``o`` — every triple-formation rule
    requires ``s`` to be an IRI or blank node, full stop. Confirmed a real,
    previously-unfixed gap 2026-08-15 (found via a user directly
    challenging this project's own claim that triple-term-as-subject was
    legal): `<<(:x ?R :z )>> :p <<(:a :b ?C )>> .` parsed and constructed
    without error before ``_reject_triple_term_pattern_subjects`` below
    existed, even though no valid RDF 1.2 data could ever match it. See
    ``docs/w3c-sparql12-test-suite-issues.md`` Issue 1 for the two W3C
    `PositiveSyntaxTest` fixtures this affects (`compound-tripleterm-subject`,
    `nested-tripleterm-02`) and why they're believed to be a suite defect
    rather than evidence this shape should be accepted.

    **Does not affect the RDF 1.2 reifier-shorthand form** (`<<s p o>>`/
    `<<s p o ~ r>>`, no parens) in subject position — confirmed still
    legal and unaffected by rule 2: that shorthand desugars
    (`grammar12.py`'s own `_reify`) to an ordinary blank-node reifier
    substituted into the pattern, with the actual triple term only ever
    appearing as the *object* of a separate `rdf:reifies` triple — exactly
    the shape rule 2 allows. Verified live: `<<:x ?R :z >> :p
    <<:a :b ?C ~ _:bnode >> .` still produces three ordinary, fully legal
    triples, none with a triple term as subject.

    Rule 1 was confirmed empirically (2026-08-08) to still *parse* as
    SPARQL syntax (the W3C SPARQL 1.2 test suite labels the two fixtures
    above `PositiveSyntaxTest`) — but "SPARQL's grammar parses this text"
    and "this represents a valid RDF 1.2 term" are different claims, and
    only the first is true here. This project previously (mis)read those
    fixtures as evidence rule 1's shape should be *accepted* (see git
    history / CLAUDE.md's now-superseded finding #20) and widened the
    pattern-position subject grammar accordingly — confirmed as a real bug
    via a live Oxigraph instance rejecting exactly this shape (`HTTP 500`)
    while this project's own construction path did not reject it at all;
    see the sibling `starlayergraph` repo's
    `docs/oxigraph-upstream-issues.md` Issue 1 for the full investigation
    (retracted as an Oxigraph bug, redirected here instead). Rule 2's gap
    was the same underlying grammar permissiveness, one level up, missed
    by that earlier investigation because it only tested the nested case.

    Both rules are deliberately enforced as semantic checks — rule 1 at
    ``TripleTermNode`` construction, rule 2 via a post-translation tree
    walk (see ``_reject_triple_term_pattern_subjects`` below) — rather than
    by further constraining the SPARQL grammar itself, since the grammar's
    own splice points (`GraphTerm`/`VarOrTerm`/`GraphNode`/`GraphNodePath`
    in `grammar12.py`) are shared, interconnected pyparsing objects where a
    narrow, surgical grammar-level fix risks silently breaking a
    legitimate case elsewhere in the tree - the semantic check catches
    what parsing alone can't, without touching grammar internals at all.
    """


def _reject_nested_triple_term(value, position: str, node: "TripleTermNode") -> None:
    if isinstance(value, TripleTermNode):
        raise InvalidTripleTermError(
            f"RDF 1.2: a triple term's {position} may never itself be a triple term "
            f"(nesting a triple term is legal only in object position) — "
            f"got {value!r} as the {position} of {node!r}"
        )


def _sort_key(value):
    """A stable, total-ordering key for one subject/predicate/object slot.

    Always a plain ``str`` — never the raw nested tuple ``TripleTermNode
    ._sort_key()`` produces — which matters more than it looks: two
    *sibling* triples in the same BGP can tie on rdflib's outer sort key
    (`_knownTerms`) and fall back to comparing raw triples slot-by-slot
    with ``<``. If triple A's subject is a ground triple term with a
    *nested* triple-term subject (recursing into another 3-tuple) while
    triple B's subject in that same slot is an ordinary, non-nested term
    (a plain ``repr()`` string), Python ends up comparing a ``tuple``
    against a ``str`` at that slot — a real, reproducible ``TypeError``
    confirmed via the W3C test `compound-tripleterm-subject`, not a
    hypothetical. Wrapping the nested case in `repr(...)` keeps every
    slot's key a `str` unconditionally, so two sort keys are always
    comparable regardless of how deeply either side nests — the actual
    order chosen still doesn't matter semantically, only that comparisons
    never raise.
    """
    if isinstance(value, TripleTermNode):
        return repr(value._sort_key())
    return repr(value)


class TripleTermNode(CompValue):
    """A ``CompValue`` subclass for SPARQL 1.2 triple terms — see module
    docstring for why plain ``CompValue`` isn't sufficient here specifically
    (every other operator/expression name in this project's vocabulary is
    fine as a bare ``CompValue``)."""

    def _sort_key(self):
        return (
            _sort_key(self.get("subject")),
            _sort_key(self.get("predicate")),
            _sort_key(self.get("object")),
        )

    def __hash__(self):
        return hash(self._sort_key())

    def __eq__(self, other):
        if isinstance(other, TripleTermNode):
            return self._sort_key() == other._sort_key()
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, TripleTermNode):
            return self._sort_key() < other._sort_key()
        return NotImplemented

    def validate(self) -> "TripleTermNode":
        """Raise ``InvalidTripleTermError`` if this node's own subject or
        predicate is itself a triple term — see that exception's docstring
        for why. Not enforced automatically on every dict mutation (kept
        explicit rather than hooking ``update()``/``__setitem__``, to avoid
        surprising ``CompValue``'s existing, delicately-hash/order-balanced
        behavior) — call this at every construction site instead:
        ``grammar12.py``'s ``_promote`` and ``from_rdf.py``'s ``TripleTerm``
        decode branch both do. Returns ``self`` so it can be chained
        directly onto a construction call.
        """
        _reject_nested_triple_term(self.get("subject"), "subject", self)
        _reject_nested_triple_term(self.get("predicate"), "predicate", self)
        return self


def _reject_triple_term_pattern_subjects(root) -> None:
    """Post-translation hard backstop for ``InvalidTripleTermError``'s rule
    2 — see that class's own docstring for the full RDF 1.2 Concepts
    citation and reasoning. Call this once, on the *finished* algebra tree
    (a ``Query``'s ``.algebra``, or an ``Update``'s ``.algebra`` list of
    operations) — after ``translateQuery``/``translateUpdate`` (or this
    project's own ``from_rdf.rdf_to_query``/``rdf_to_update`` decode
    equivalents) have already assembled every ordinary triple/quad pattern
    into its final ``(s, p, o)`` tuple form.

    Deliberately generic over both shapes a triple list can appear in this
    codebase's algebra representation, found by walking the *whole* tree
    once rather than special-casing each operator by name:

    - A ``BGP`` node's own ``.triples`` (an ordinary list of ``(s, p, o)``
      tuples) — reached wherever it sits in the tree (top-level, or nested
      under ``Filter``/``LeftJoin``/``Union``/``Minus``/``Graph``/a
      subquery/etc.), since the walk recurses into every ``CompValue``'s
      own values generically.
    - An Update operation's flat ``.triples``/``.quads`` attributes
      (``InsertData``/``DeleteData``/``DeleteWhere``, and ``Modify``'s own
      ``.insert``/``.delete``, each a ``CompValue`` carrying triples/quads
      directly rather than via a nested ``BGP`` — see ``vocab.py``'s
      "Update's quads-by-graph maps" convention). A ``Modify``'s own
      ``.where`` (an ordinary nested pattern tree) is covered for free by
      the same generic recursion, no special-casing needed.

    ``seen`` guards against re-walking the same node twice when a value
    appears in more than one place in the tree (rare, but ``id()``-keyed
    rather than value-keyed since these nodes aren't reliably hashable
    before ``TripleTermNode``'s own hash/eq existed, and value-equality
    isn't what "already visited" means here anyway).
    """
    seen: set = set()

    def _check_triples(triples) -> None:
        for t in triples:
            s = t[0]
            if isinstance(s, TripleTermNode):
                raise InvalidTripleTermError(
                    "RDF 1.2: a triple term may never be the subject of an "
                    "ordinary triple pattern (a triple term is only ever "
                    f"legal as an object) — got {s!r} as the subject of {t!r}"
                )

    def _walk(node) -> None:
        if isinstance(node, TripleTermNode):
            return  # already validated at its own construction; nothing further to check inside it
        if isinstance(node, CompValue):
            key = id(node)
            if key in seen:
                return
            seen.add(key)
            triples = node.get("triples")
            if isinstance(triples, list):
                _check_triples(triples)
            quads = node.get("quads")
            if isinstance(quads, dict):
                for graph_triples in quads.values():
                    _check_triples(graph_triples)
            for value in node.values():
                _walk(value)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(root)
