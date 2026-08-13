"""Serialize a SPARQL 1.2 algebra tree (with ``TripleTermNode`` nodes) back
into SPARQL 1.2 query text — the counterpart to ``parse12.py``.

Extends rdflib's own ``algebra.translateAlgebra``/``_AlgebraTranslator``,
which already turns an ordinary (SPARQL-1.1-shaped) algebra tree back into
query text, in three ways:

1. ``BGP``/``TriplesBlock`` (the latter used for CONSTRUCT templates) call
   ``.n3()`` directly on each triple-pattern term rather than delegating
   through ``convert_node_arg``/child traversal the way most other
   operators do — confirmed by reading the real ``algebra.py`` source
   before relying on it. ``CompValue`` (and therefore ``TripleTermNode``)
   has no ``.n3()`` method, so both branches are overridden to render a
   ``TripleTermNode`` as ``<<( s p o )>>`` instead of crashing with
   ``AttributeError``.
2. ``Builtin_isTRIPLE``/``SUBJECT``/``PREDICATE``/``OBJECT`` are new SPARQL
   1.2 builtins rdflib has no branch for at all — added following the same
   pattern as any other single-argument builtin (e.g. ``Builtin_STR``).
3. ``ConstructQuery`` is a **new capability**, not a patch to an existing
   branch: confirmed empirically that plain, unmodified rdflib has *no*
   ``ConstructQuery`` case at all — ``translateAlgebra`` already returns an
   empty string for a CONSTRUCT query even with zero triple terms involved,
   since ``self._alg_translation`` is only ever seeded by the ``SelectQuery``
   branch. Two non-obvious things had to be gotten right, both found only by
   testing against a real execution target, not by reading source alone:
   (a) ``node.p`` (a ``Project`` wrapping the WHERE pattern) can't be
   referenced the way ``SelectQuery`` does — for CONSTRUCT, ``Project.PV``
   is internal bookkeeping (which variables the template needs), not "the
   variable list to print after SELECT", but the base class's ``Project``
   branch doesn't know that distinction and prints it anyway, producing
   invalid syntax (a stray ``?x`` between ``WHERE`` and ``{``) — fixed by
   referencing ``node.p.p`` directly, skipping ``Project``'s own branch
   entirely; (b) the literal ``WHERE`` keyword, though optional per the
   SPARQL grammar itself (confirmed: rdflib's own ``WhereClause`` production
   is ``Optional(Keyword("WHERE")) + ...``, and this project's SELECT
   serialization has always omitted it), is required for compatibility with
   *starlayergraph's* SPARQL-1.2-to-1.1 rewriter specifically — a regex-based,
   non-full-grammar-parsing tool (by its own docstring) confirmed to fail on
   a WHERE-less CONSTRUCT even though plain rdflib itself re-parses that
   same text without complaint.

Everything else is inherited from ``_AlgebraTranslator`` completely
unchanged.

Scope: Query algebra only (``SELECT``/``CONSTRUCT``), matching this
project's existing ``translateAlgebra`` usage — Update algebra was never
serialized back to text by this project either (see
``test_phase2_update.py``'s docstring: "this project doesn't attempt to
serialize Update algebra back to text at all"). ``ASK``/``DESCRIBE`` are
still unsupported — confirmed the same "no branch, nothing ever seeds
``self._alg_translation``" gap applies to them too, not investigated
further since nothing in this project's scope currently needs them. A
``VALUES`` row containing a triple-term *value* (as opposed to a triple
term appearing in an ordinary triple pattern) is not yet handled either —
rdflib's own ``values`` branch calls ``.n3()`` on each row value too, the
same class of gap, just not hit by any test yet. Worth fixing the same way
if either comes up.
"""

from __future__ import annotations

from rdflib.plugins.sparql.algebra import ExpressionNotCoveredException, _AlgebraTranslator
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import Query
from rdflib.term import Identifier, Literal

from .triple_term import TripleTermNode
from .vocab import decode_dirlang_datatype


def _dirlang_n3(term) -> str | None:
    """The real ``"text"@lang--dir`` SPARQL 1.2 syntax for `term`, if it's a
    Literal using this project's own ``dirlang:`` datatype encoding (see
    ``grammar12.py``'s ``LangDirLiteral`` for why that encoding is used at
    all in the algebra in the first place - rdflib's own ``Literal`` can't
    hold ``lang="en--rtl"`` directly, so a plain ``term.n3()`` would emit
    the *internal* encoding datatype IRI verbatim - syntactically valid
    SPARQL, but a real, different, wrong literal value once sent to a real
    RDF 1.2 endpoint, not the base-direction string it's supposed to mean).
    ``None`` for any other term, so callers fall through to the ordinary
    ``term.n3()`` path unchanged.
    """
    if isinstance(term, Literal) and term.datatype is not None:
        decoded = decode_dirlang_datatype(term.datatype)
        if decoded is not None:
            lang, direction = decoded
            escaped = str(term).replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"@{lang}--{direction}'
    return None


def _term_text(term) -> str:
    """``.n3()`` for an ordinary RDF term/Variable/Path; ``<<( s p o )>>`` —
    built recursively, so a nested triple term renders correctly too — for
    a ``TripleTermNode``; ``"text"@lang--dir`` for a dirlang-encoded
    Literal (see ``_dirlang_n3``)."""
    if isinstance(term, TripleTermNode):
        return (
            "<<( "
            + _term_text(term["subject"])
            + " "
            + _term_text(term["predicate"])
            + " "
            + _term_text(term["object"])
            + " )>>"
        )
    dirlang = _dirlang_n3(term)
    if dirlang is not None:
        return dirlang
    return term.n3()


def _triples_text(triples) -> str:
    # Trailing space after each "." (not just "."), unlike rdflib's own
    # algebra.py BGP branch (`triple[0].n3() + " " + ... + "."`, joined with
    # "".join with no separator at all) - confirmed via direct reproduction
    # that this is a real, pre-existing rdflib *parser* bug/sharp-edge, not
    # a starlayergraph one: a period-terminated triple ending in a blank-node
    # object, immediately followed (zero whitespace) by another triple
    # whose subject is a blank node, fails to reparse
    # (`prepareQuery("SELECT * {_:y <p> _:x._:x <p2> <o2>.}")` raises
    # `ParseException` at the second `_:x`; adding a single space before it
    # fixes it - isolated down to exactly this, with no dependency on this
    # project's own grammar12 install() being active). Annotation syntax's
    # reification triples (RDF.subject/predicate/object/reifies, all
    # blank-node-heavy) hit this constantly once regenerated - previously
    # misdiagnosed as "starlayergraph's own Turtle parser rejecting nested
    # syntax" when investigating W3C harness failures, before tracing it
    # down to this exact whitespace omission in our own serializer.
    return "".join(
        _term_text(s) + " " + _term_text(p) + " " + _term_text(o) + ". "
        for s, p, o in triples
    )


class _AlgebraTranslator12(_AlgebraTranslator):
    """``rdflib.plugins.sparql.algebra._AlgebraTranslator``, with the two
    triple-serialization branches (``BGP``, ``TriplesBlock``) patched to
    handle a ``TripleTermNode`` term — see module docstring for why only
    these two need it."""

    def convert_node_arg(self, node_arg):
        # BGP/TriplesBlock triple positions go through _term_text (see
        # _triples_text), which already checks _dirlang_n3 - but ordinary
        # *expression*-position terms (BIND(...)/FILTER(...)/VALUES row
        # values reached via the base class's own generic traversal) go
        # through this method instead, inherited unchanged from the base
        # class otherwise. Same check, same reason: a bare
        # node_arg.n3() would emit the *internal* dirlang: datatype IRI
        # verbatim rather than real "text"@lang--dir syntax.
        dirlang = _dirlang_n3(node_arg)
        if dirlang is not None:
            return dirlang
        return super().convert_node_arg(node_arg)

    def translateAlgebra(self) -> str:
        text = super().translateAlgebra()
        # -*-SELECT-*-/{GroupBy}/{Having} are rdflib's own base-class
        # placeholder tokens. The base class only ever replaces them as a
        # side effect of visiting a BGP/TriplesBlock node (see the BGP
        # branch below, and algebra.py's own identical pairing) - a real,
        # pre-existing rdflib bug, confirmed independent of this project's
        # own RDF-1.2 work: plain, unmodified rdflib produces the exact
        # same unresolved placeholders for any *ordinary* SPARQL 1.1 query
        # with no triple pattern at all, e.g.
        # `SELECT * { VALUES ?t {1 2 3} FILTER(?t > 1) }` (no BGP anywhere)
        # - confirmed via direct reproduction against
        # rdflib.plugins.sparql.algebra.translateAlgebra() with zero
        # involvement from this project. It surfaces here because a
        # triple-term-using SPARQL 1.2 query can just as easily have no
        # ordinary BGP either (VALUES of triple terms plus
        # isTRIPLE()/SUBJECT()/etc FILTERs, no `{?s ?p ?o}` anywhere - see
        # the W3C expr-2/triple-on-* fixtures, which hit exactly this).
        # Applying the replacement unconditionally here, rather than only
        # as a side effect of the BGP branch, guarantees every query gets
        # valid text regardless of whether it happens to contain a BGP.
        text = text.replace("-*-SELECT-*-", "SELECT")
        text = text.replace("{GroupBy}", "")
        text = text.replace("{Having}", "")
        return text

    def sparql_query_text(self, node):
        if isinstance(node, TripleTermNode):
            # Two different visit contexts, both handled correctly by this
            # one branch:
            #  - Inline within BGP/TriplesBlock.triples: the branch below
            #    renders the term via _term_text() directly into the triples
            #    string, never leaving a "{TripleTerm}" placeholder behind —
            #    so if traverse() *also* visits this same node standalone
            #    afterward (it does - see next bullet), the _replace() call
            #    here finds nothing to replace and is a harmless no-op.
            #  - Standalone, e.g. a triple term used as an ordinary
            #    expression value (Extend.expr for BIND(<<(...)>> AS ?x),
            #    or a Builtin_SUBJECT/etc.'s arg): the base class's own
            #    convert_node_arg() (used by the Extend/Builtin_* branches)
            #    emits a bare "{TripleTerm}" placeholder for any CompValue
            #    argument, same as it would for any other operator name, and
            #    traverse()'s ordinary recursion visits this node afterward
            #    expecting it to fill that placeholder in — which a bare
            #    no-op previously failed to do, confirmed empirically
            #    (BIND(<<(...)>> AS ?x) regenerated as literal, unresolved
            #    "{TripleTerm}" text before this fix).
            self._replace("{TripleTerm}", _term_text(node))
            return node

        if isinstance(node, CompValue) and node.name in (
            "Builtin_isTRIPLE",
            "Builtin_SUBJECT",
            "Builtin_PREDICATE",
            "Builtin_OBJECT",
        ):
            # These four names aren't in the base class's if/elif chain at
            # all (they're new SPARQL 1.2 builtins, unknown to plain
            # rdflib) - same "not covered, placeholder left unresolved"
            # failure mode as TripleTerm above would have without a branch
            # here. Render the same way rdflib itself renders every other
            # single-argument builtin (e.g. Builtin_STR: "STR(" + arg + ")").
            keyword = node.name[len("Builtin_") :]
            self._replace(
                "{" + node.name + "}",
                keyword + "(" + self.convert_node_arg(node.arg) + ")",
            )
            # Deliberately NOT `return node` here, unlike the TripleTerm/BGP/
            # TriplesBlock branches above/below. rdflib's own _traverse()
            # (algebra.py) stops recursing into a node's *children* the
            # moment its visitPre callback returns non-None - confirmed
            # empirically as the exact cause of a real bug: `.arg` can
            # itself be a TripleTermNode (e.g. PREDICATE(TRIPLE(:a,:b,:c))),
            # whose own "{TripleTerm}" placeholder (just inserted by the
            # convert_node_arg() call above) needs a *separate* later visit
            # to resolve - which never happened while this branch returned
            # `node`, leaving literal unresolved "{TripleTerm}" text in the
            # output. Falling through (implicit None), matching every
            # ordinary base-class builtin branch's own convention, lets
            # _traverse's normal per-child recursion reach `.arg` on its own.

        if isinstance(node, CompValue) and node.name == "ConstructQuery":
            # rdflib's own _AlgebraTranslator has NO case for ConstructQuery
            # at all (confirmed empirically: plain rdflib's translateAlgebra
            # already returns "" for a CONSTRUCT query with zero triple
            # terms involved — self._alg_translation is only ever *seeded*
            # by the SelectQuery branch, so nothing ever gets written for
            # any other query form). This is a real, pre-existing rdflib
            # gap unrelated to TripleTerm, not something narrow to work
            # around — so, unlike the other branches here, this one adds a
            # genuinely new capability rather than patching an existing one
            # that almost works. `node.template` is a bare list of (s, p, o)
            # tuples directly on the ConstructQuery node (not wrapped in its
            # own TriplesBlock/BGP CompValue), so it's rendered the same way
            # as BGP.triples/TriplesBlock.triples via _triples_text - reused
            # unchanged. `node.p` (a Project, PV always empty for CONSTRUCT)
            # is referenced via a placeholder and deliberately left for
            # ordinary traversal to resolve, exactly like the SelectQuery
            # branch does for its own `node.p` - not returning early here.
            # The literal "WHERE" keyword is optional per the SPARQL
            # grammar itself (confirmed: rdflib's own WhereClause production
            # is `Optional(Keyword("WHERE")) + ...`, and this project's
            # existing SELECT-query serialization already omits it, e.g.
            # "SELECT ?x{...}") - but starlayergraph's *own* SPARQL-1.2-to-1.1
            # rewriter (sparql12_to_11.py) is a regex-based, non-full-
            # grammar-parsing tool (by its own docstring), and confirmed
            # empirically to fail on a WHERE-less CONSTRUCT specifically
            # (though not on a WHERE-less SELECT) — regenerated text that
            # plain rdflib itself re-parses without complaint still crashed
            # going through StarLayerGraph.query(text). Including "WHERE"
            # explicitly here, unlike the (unmodified, inherited)
            # SelectQuery branch, is what makes this compatible with both
            # execution targets rather than just the stricter one.
            #
            # node.p is a Project wrapping the WHERE pattern, but — unlike a
            # SELECT query — its PV here isn't "the variables to print after
            # SELECT"; it's internal bookkeeping (the variables the template
            # needs projected out of the pattern). The base class's own
            # Project branch doesn't know that distinction: it always
            # renders PV as a printed variable list (correct for SELECT,
            # confirmed empirically to be wrong here — it inserted a stray
            # "?x" directly between "WHERE" and "{", which isn't valid
            # CONSTRUCT syntax at all). Referencing node.p.p directly skips
            # Project's own branch entirely, going straight to the
            # underlying pattern (BGP/etc.), which renders correctly via
            # its own existing branch with no variable-list side effect.
            # Double braces around node.p.p.name, matching Project's own
            # "{{" + name + "}}" convention: the *inner* "{Name}" is the
            # placeholder Name's own branch replaces; the *outer* literal
            # "{"/"}" are the actual WHERE-clause block delimiters and must
            # survive that replacement. A single "{" + name + "}" (tried
            # first) is indistinguishable from the placeholder itself, so
            # the pattern's own branch consumes the delimiters along with
            # it — confirmed empirically: produced "WHERE <iri> <iri> ?x."
            # with the braces gone entirely, invalid SPARQL syntax.
            template_text = _triples_text(node.template) if node.template else ""
            self._alg_translation = (
                "CONSTRUCT {" + template_text + "} WHERE {{" + node.p.p.name + "}}"
            )
            return None

        if isinstance(node, CompValue) and node.name in ("BGP", "TriplesBlock"):
            # Mirrors algebra.py's own BGP/TriplesBlock branches exactly,
            # with _term_text in place of a bare triple[i].n3() call. The
            # base class also replaces -*-SELECT-*-/{GroupBy}/{Having} here
            # as a side effect of this same branch - handled instead,
            # unconditionally, in translateAlgebra() above (see its own
            # docstring for why a BGP-triggered-only replacement isn't
            # reliable).
            self._replace("{" + node.name + "}", _triples_text(node.triples))
            return node

        if (
            isinstance(node, CompValue)
            and node.name == "RelationalExpression"
            and isinstance(node.other, list)
        ):
            # A genuine, pre-existing rdflib bug, confirmed independent of
            # this project's own grammar/triple-term work: the base class's
            # own "RelationalExpression" branch (used for IN/NOT IN among
            # other relational operators) guards its list-handling code with
            # `isinstance(list, type(node.other))` - backwards from the
            # intended `isinstance(node.other, list)` (it asks "is the class
            # object `list` itself an instance of `type(node.other)`",
            # which is never true for any value of `node.other`, since
            # `list` is an instance of `type`, not of itself). That makes
            # the correct branch dead code, and every multi-value IN/NOT IN
            # falls through to `self.convert_node_arg(node.other)` -
            # passing the *whole list* as one argument to a method with no
            # list case at all, raising ExpressionNotCoveredException.
            # Confirmed via a plain, unmodified rdflib repro with no triple
            # terms involved at all: `FILTER(?o IN (:a, :b, :c))` alone
            # already crashes `translateAlgebra`. First surfaced here via
            # the W3C test `basic-9`
            # (`FILTER (?o IN (<<( :s :p "o" )>>, ...))`), which additionally
            # needs each list element rendered through _term_text (for a
            # TripleTermNode element) rather than a bare .n3()/
            # convert_node_arg call - both gaps fixed together here rather
            # than patching rdflib itself, matching every other override in
            # this class.
            expr = self.convert_node_arg(node.expr)
            other = (
                "("
                + ", ".join(
                    _term_text(item) if isinstance(item, TripleTermNode) else self.convert_node_arg(item)
                    for item in node.other
                )
                + ")"
            )
            self._replace(
                "{RelationalExpression}",
                "{left} {operator} {right}".format(left=expr, operator=node.op, right=other),
            )
            return node

        if isinstance(node, CompValue) and node.name == "values":
            # Mirrors algebra.py's own "values" branch exactly (same
            # placeholder key "values", no braces - matching the base
            # class's own convention there, not this project's usual
            # double-brace one), with _term_text in place of a bare
            # term.n3() call so a VALUES row containing a triple-term
            # value (`VALUES ?x { <<( :s :p :o )>> }`) renders instead of
            # hitting the base class's `ExpressionNotCoveredException`
            # (confirmed empirically via the W3C test `basic-8`/`basic-9`,
            # each using several TripleTermNode rows) - previously a
            # documented, explicitly-deferred gap (see the Phase 6 status
            # entry in CLAUDE.md), closed here the same way BGP/
            # TriplesBlock/ConstructQuery already were.
            columns = []
            for key in node.res[0].keys():
                if isinstance(key, Identifier):
                    columns.append(key.n3())
                else:
                    raise ExpressionNotCoveredException(
                        "The expression {0} might not be covered yet.".format(key)
                    )
            values = "VALUES (" + " ".join(columns) + ")"

            rows = ""
            for elem in node.res:
                row = []
                for term in elem.values():
                    if isinstance(term, TripleTermNode):
                        row.append(_term_text(term))
                    elif isinstance(term, Identifier):
                        # _term_text, not a bare term.n3(): also covers a
                        # dirlang-encoded Literal (see _dirlang_n3) - a bare
                        # .n3() here was a real, confirmed gap (this exact
                        # branch is a separate .n3() call site from both
                        # _triples_text and convert_node_arg, so fixing
                        # those two alone didn't cover VALUES rows) that
                        # emitted the *internal* dirlang: datatype IRI
                        # verbatim instead of real "text"@lang--dir syntax.
                        row.append(_term_text(term))
                    elif isinstance(term, str):
                        row.append(term)
                    else:
                        raise ExpressionNotCoveredException(
                            "The expression {0} might not be covered yet.".format(term)
                        )
                rows += "(" + " ".join(row) + ")"

            self._replace("values", values + "{" + rows + "}")
            return node

        return super().sparql_query_text(node)


def translate_algebra_12(query: Query) -> str:
    """SPARQL 1.2 counterpart to rdflib's ``algebra.translateAlgebra`` —
    turns a ``Query`` whose algebra may contain ``TripleTermNode`` nodes
    back into SPARQL 1.2 query text, emitting ``<<( s p o )>>`` syntax for
    each one. Full IRIs only, never prefixed names, for the same reason as
    ``translateAlgebra`` itself: ``query.prologue`` is never read by this
    machinery — see CLAUDE.md finding #3."""
    return _AlgebraTranslator12(query).translateAlgebra()
