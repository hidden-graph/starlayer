"""Public entry points for ingesting SPARQL 1.2 (triple-term) query/update
text into a genuine, post-``translateQuery``/``translateUpdate`` algebra
tree — see ``grammar12.py`` for how ``<<( s p o )>>``/``TRIPLE(s, p, o)``
syntax is made parseable at all, and ``triple_term.py`` for why the
resulting node has to be a ``TripleTermNode``, not a bare ``CompValue``.

Because the grammar extension (``grammar12.install()``) constructs a
``TripleTermNode`` directly inside its parse action, the parse tree these
functions produce never contains a plain ``CompValue('TripleTerm', ...)`` to
promote after the fact — ``translateQuery``/``translateUpdate`` can be
called on it immediately, completely unmodified.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyparsing.exceptions import ParseBaseException
from rdflib import BNode
from rdflib.plugins.sparql.algebra import translateQuery, translateUpdate
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.parserutils import ParseResults  # re-exported for callers
from rdflib.plugins.sparql.sparql import Query, Update

from . import grammar12
from .triple_term import _reject_triple_term_pattern_subjects

grammar12.install()


def _parse_with_recovery(parse_fn, text: str):
    """Shared body for ``parse_query_12``/``parse_update_12``: re-verify the
    grammar installation (cheap - see ``grammar12._already_installed``'s
    own docstring) before parsing, and if the parse still fails with a
    ``ParseBaseException`` anyway, force a full unconditional re-install
    (``grammar12.install(force=True)``) and retry exactly once before
    giving up.

    The re-verification alone was confirmed insufficient on its own: some
    pytest runs still hit a residual corruption ``_already_installed()``'s
    own check doesn't catch (the exact trigger inside pytest's import
    machinery wasn't fully isolated - non-deterministic-looking, not
    reproduced by a plain script, only by certain full test-suite runs).
    A forced reinstall immediately before retrying the *same* text was
    confirmed to recover every case tried. If the retry *also* fails, that
    reliably means the query text itself is genuinely invalid syntax, not
    a grammar-state artifact - propagates normally, no third attempt.
    """
    grammar12.install()
    try:
        return parse_fn(text)
    except ParseBaseException:
        grammar12.install(force=True)
        return parse_fn(text)


def parse_query_12(text: str) -> ParseResults:
    """Parse SPARQL 1.2 query text into a parse tree with genuine
    ``TripleTermNode`` nodes wherever ``<<( s p o )>>``/``TRIPLE(s, p, o)``
    appears — rdflib's own parser, unmodified, operating on its own grammar
    objects extended in place by ``grammar12.install()``. See
    ``_parse_with_recovery`` for why this isn't just a bare ``parseQuery``
    call.
    """
    return _parse_with_recovery(parseQuery, text)


def parse_update_12(text: str):
    """``parse_query_12``'s counterpart for SPARQL 1.2 Update text - same
    re-verify-then-recover-on-failure treatment, same reason."""
    return _parse_with_recovery(parseUpdate, text)


def _canonicalize_construct_where(query: Query) -> Query:
    """``CONSTRUCT WHERE { pattern }`` shorthand (the template IS the WHERE
    pattern) reaches here with ``algebra.template`` set to ``None`` —
    confirmed via plain, unmodified ``rdflib.plugins.sparql.algebra
    .translateQuery``, not something this project's own grammar/algebra
    work introduced. ``pattern`` itself is required by the SPARQL grammar
    (``ConstructWhere`` — a plain ``TriplesTemplate``, no FILTER/OPTIONAL/
    UNION/etc permitted) to be exactly a flat BGP, so ``algebra.p.p.triples``
    is always exactly the triple list needed.

    Populating ``template`` explicitly here — the *canonical*, always-
    explicit-template form of a CONSTRUCT query — rather than leaving the
    ``None``/"use the WHERE clause" convention for downstream code to
    rediscover is a deliberate simplification, not merely a serialization
    workaround: this project's own RDF encoding of the algebra
    (``to_rdf.py``) has no special "template is really the WHERE clause"
    convention of its own, so leaving ``template=None`` here means that
    information is silently lost the moment the algebra is encoded to RDF
    - confirmed via the W3C ``construct-*``/``expr-1`` fixtures, which
    regenerated as ``CONSTRUCT {}`` (a literal, always-empty-result
    template) after a round trip through RDF, a real semantic
    mistranslation, not just lost shorthand syntax. Regenerating the
    *shorthand* ``CONSTRUCT WHERE`` spelling specifically (as opposed to an
    equivalent explicit ``CONSTRUCT { ... } WHERE { ... }``) is explicitly
    out of scope for now, per instruction - only the meaning needs to
    survive, not the original surface syntax.
    """
    alg = query.algebra
    if getattr(alg, "name", None) == "ConstructQuery" and not alg.template:
        # CompValue['template'] = ..., NOT alg.template = ... - CompValue
        # (rdflib.plugins.sparql.parserutils) is an OrderedDict subclass
        # whose __getattr__ routes attribute *reads* through to dict access
        # (`alg.template` == `alg['template']`), but has no real __setattr__
        # override at runtime (only a `if TYPE_CHECKING:` stub, never
        # executed) - so a plain `alg.template = [...]` silently creates an
        # ordinary shadow instance attribute instead of updating the dict
        # storage _encode_comp_value's own `for key, value in node.items()`
        # loop (to_rdf.py) actually iterates over. Confirmed a real, silent
        # bug this way: `alg.template` read back the assigned list
        # correctly (plain attribute lookup finds the instance dict first),
        # while `graph.triples((root, SALG.template, None))` after
        # query_to_rdf() showed zero results - the assignment never reached
        # anywhere query_to_rdf() could see it.
        alg["template"] = list(alg.p.p.triples)
    return query


def prepare_query_12(
    text: str, base: str | None = None, initNs: Mapping[str, Any] | None = None
) -> Query:
    """Parse and translate SPARQL 1.2 query text into a real, executable-
    shaped rdflib ``Query`` — ``query.algebra`` contains genuine
    ``TripleTermNode`` nodes in triple-pattern position, not a lowered
    SPARQL-1.1-equivalent shape.

    ``base``/``initNs`` are threaded straight through to
    ``translateQuery`` — same two parameters, same precedence, as plain
    rdflib's own ``prepareQuery(queryString, initNs=None, base=None)``:
    ``initNs`` seeds the query's Prologue first, then any ``BASE``/``PREFIX``
    declaration actually written in ``text`` is applied after and overrides
    it (confirmed via ``rdflib.plugins.sparql.algebra.translatePrologue``'s
    own source — ``initNs`` binds first, the parsed prologue's own
    declarations are applied in a loop afterward)."""
    query = _canonicalize_construct_where(
        translateQuery(parse_query_12(text), base, initNs)
    )
    _reject_triple_term_pattern_subjects(query.algebra)
    return query


def prepare_update_12(
    text: str, base: str | None = None, initNs: Mapping[str, Any] | None = None
) -> Update:
    """``prepare_query_12``'s counterpart for SPARQL 1.2 Update text — same
    ``base``/``initNs`` passthrough to ``translateUpdate``."""
    update = _reject_blank_nodes_in_delete(
        translateUpdate(parse_update_12(text), base, initNs)
    )
    _reject_triple_term_pattern_subjects(update.algebra)
    return update


def _reject_blank_nodes_in_delete(update: Update) -> Update:
    """SPARQL Update forbids a blank node appearing in ``DELETE DATA``'s
    ``QuadData`` or in ``Modify``'s ``DELETE`` template - deleting requires
    matching a specific, already-existing term, and a blank node (whether
    written directly as ``_:x`` or minted implicitly by an anonymous
    ``{| ... |}`` annotation reifier - see ``grammar12.py``'s ``_reify``)
    can never identify one. Confirmed real, unmodified rdflib doesn't
    enforce this syntactically either, so it's checked here, post-translate,
    against the two operation shapes that carry a delete template:
    ``DeleteData.triples``/``.quads`` directly, and ``Modify.delete.triples``/
    ``.quads`` (``Modify.delete`` is ``None`` for an INSERT-only Modify —
    confirmed via ``algebra.translateUpdate1``)."""
    for op in update.algebra:
        if op.name == "DeleteData":
            _check_no_blank_nodes(op.triples, op.quads, "DELETE DATA")
        elif op.name == "Modify" and op.delete is not None:
            _check_no_blank_nodes(op.delete.triples, op.delete.quads, "DELETE")
    return update


def _check_no_blank_nodes(triples, quads, context: str) -> None:
    all_triples = list(triples)
    for graph_triples in quads.values():
        all_triples.extend(graph_triples)
    for s, p, o in all_triples:
        if isinstance(s, BNode) or isinstance(p, BNode) or isinstance(o, BNode):
            raise ValueError(
                f"starsparql: a blank node (possibly minted implicitly by an "
                f"anonymous {{| ... |}} annotation reifier) is not permitted in a "
                f"{context} template - it can never identify a specific existing term"
            )
