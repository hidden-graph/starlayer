"""Decode RDF triples (as produced by ``to_rdf.py``) back into an rdflib
SPARQL algebra tree / ``Query`` object — runnable directly via
``rdflib.plugins.sparql.evaluate.evalQuery`` or serializable back to query
text via ``rdflib.plugins.sparql.algebra.translateAlgebra``.

The hard part decoding has that encoding doesn't: rdflib's evaluator
requires *expression* nodes (``RelationalExpression``, ``Builtin_BOUND``,
``Function``, ...) to be actual ``Expr`` instances with a bound ``_evalfn``
(``rdflib.plugins.sparql.parserutils.value()`` raises on a plain
``CompValue`` used as an expression — "What do I do with this CompValue?").
That binding happens once, at *parse* time, via each grammar production's
``Comp(name, ...).setEvalFn(fn)`` call in ``rdflib.plugins.sparql.parser``.
Rather than hand-transcribing that table (name -> evalfn) — which would
silently drift out of sync with whatever rdflib version is actually
installed — ``_discover_expr_evalfns()`` below rebuilds it by walking the
live pyparsing grammar object graph in that module and collecting every
``Comp`` with a bound ``evalfn``. Same generic-mirror principle as the
encoder in ``to_rdf.py`` and the design note in ``vocab.py``.
"""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
from rdflib import BNode, Graph
from rdflib.collection import Collection
from rdflib.plugins.sparql.sparql import Prologue, Query, Update

from ._vocab_rdflib import (
    SALG,
)
from .spexpr_codec import _decode, _decode_list_field


def rdf_to_query(graph: Graph, root: BNode) -> Query:
    """Decode ``root`` (as produced by ``to_rdf.query_to_rdf``) back into an
    rdflib ``Query`` — same type ``prepareQuery``/``translateQuery`` return.

    The returned ``Query``'s ``Prologue`` is reconstructed from
    ``salg:base``/``salg:prologuePrefix`` on ``root`` (see vocab.py's
    "Prologue (BASE/PREFIX)" section) — this fixes real evaluation-time
    behavior (``BASE``-relative ``IRI()``/``URI()`` builtin resolution), but
    does *not* make ``algebra.translateAlgebra`` emit prefixed names: that
    function never reads ``query.prologue`` at all, confirmed empirically,
    so its output stays full-IRI-only regardless.

    Args:
        graph: The graph holding the encoded query.
        root: The query's root node, as returned by ``to_rdf.query_to_rdf``.

    Returns:
        A fully reconstructed, evaluator-ready ``Query``.
    """
    if root is None or (root, None, None) not in graph:
        raise ValueError(f"{root!r} is not an encoded query in this graph")
    algebra = _decode(root, graph)

    # Recompute the _vars/lazy bookkeeping to_rdf.py deliberately doesn't
    # encode (see _INTERNAL_BOOKKEEPING_KEYS there) — the same two passes
    # translateQuery() itself runs on a freshly-built algebra tree, so the
    # decoded tree is evaluator-ready exactly like one built straight from
    # query text.
    from rdflib.plugins.sparql.algebra import _addVars, _traverseAgg, analyse, traverse
    from rdflib.plugins.sparql.algebra import simplify as _reorder_bgps

    algebra = traverse(algebra, visitPost=_reorder_bgps)
    _traverseAgg(algebra, visitor=analyse)
    _traverseAgg(algebra, _addVars)

    from .triple_term import _reject_triple_term_pattern_subjects

    _reject_triple_term_pattern_subjects(algebra)

    return Query(_decode_prologue(root, graph), algebra)


def rdf_to_update(graph: Graph, root: BNode) -> Update:
    """Decode ``root`` (as produced by ``to_rdf.update_to_rdf``) back into an
    rdflib ``Update`` — same type ``prepareUpdate``/``translateUpdate``
    return, runnable via ``rdflib.plugins.sparql.update.evalUpdate``.

    Unlike a Query's algebra, an Update operation's WHERE clause (Modify)
    never gets the _vars/lazy bookkeeping pass in stock rdflib either —
    ``translateUpdate`` never calls ``_addVars``/``analyse`` the way
    ``translateQuery`` does for a SELECT/etc. — so there's nothing to
    recompute here to match. The request's single shared Prologue (see
    ``update_to_rdf``) is reconstructed the same way as a Query's, and
    assigned to every operation — ``evalUpdate`` reads ``u.prologue`` off
    each operation individually, even though it's the same object for all
    of them in a real ``prepareUpdate`` result too.

    Args:
        graph: The graph holding the encoded update.
        root: The update's root node, as returned by
            ``to_rdf.update_to_rdf``.

    Returns:
        A fully reconstructed ``Update``.
    """
    operations = graph.value(root, SALG.operations) if root is not None else None
    if operations is None:
        raise ValueError(f"{root!r} is not an encoded update in this graph")
    ops = _decode_list_field(operations, graph)
    prologue = _decode_prologue(root, graph)
    for op in ops:
        op.prologue = prologue

    from .triple_term import _reject_triple_term_pattern_subjects

    _reject_triple_term_pattern_subjects(ops)

    return Update(prologue, ops)


def rdf_to_collection(graph: Graph, root: BNode) -> list[Query]:
    """Decode ``root`` (as produced by ``to_rdf.queries_to_collection``)
    back into a list of independent, directly executable rdflib ``Query``
    objects, in the same order they were encoded.

    Each member is decoded via ``rdf_to_query`` individually — not the
    generic ``_decode`` walker an ordinary ``rdf:List`` goes through
    elsewhere in this module — since each member needs that function's own
    per-query handling (recomputed ``_vars``/``lazy`` bookkeeping via
    ``_addVars``/``analyse``, its own reconstructed Prologue), the same
    reason ``rdf_to_update`` doesn't reuse plain ``_decode`` for its own
    operations list's *individual members* either (only the list structure
    itself goes through the generic walker there).

    Args:
        graph: The graph holding the encoded collection.
        root: The collection's root node, as returned by
            ``to_rdf.queries_to_collection``.

    Returns:
        The member queries, in the order they were encoded.
    """
    query_nodes = Collection(graph, graph.value(root, SALG.queries))
    return [rdf_to_query(graph, node) for node in query_nodes]


def _decode_prologue(root, graph: Graph) -> Prologue:
    """Inverse of to_rdf._encode_prologue."""
    prologue = Prologue()
    base = graph.value(root, SALG.base)
    if base is not None:
        prologue.base = str(base)
    for binding in graph.objects(root, SALG.prologuePrefix):
        prefix = _decode(graph.value(binding, SALG.prefixLabel), graph)
        namespace = graph.value(binding, SALG.namespace)
        prologue.bind(prefix, namespace)
    return prologue
