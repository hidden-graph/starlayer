"""Render ``ssyn:`` RDF (``to_ssyn_rdf.py``'s output) back into literal
SPARQL query text — the completion of the round trip, closing it through
text rather than by hand-reconstructing algebra ``CompValue`` trees.

This is a much lower-risk path than driving ``rdflib.plugins.sparql.algebra
.translateGroupGraphPattern``/``translateQuery`` directly: ``ssyn:`` is
already syntax-shaped (flat WHERE-clause elements, real resolved terms), so
rendering it as text is close to mechanical — no reconstruction of
``TriplesBlock``/path/precedence-chain shapes needed at all, since none of
that verbosity was ever introduced on the encode side. Once we have text,
execution goes through this project's own real, already-tested pipeline
(``parse12.prepare_query_12`` / plain ``prepareQuery``) unchanged — nothing
new needed there either.

The one place this *does* reuse existing machinery rather than writing a
new renderer: ``ssyn:Filter``/``ssyn:Bind``'s ``ssyn:expr`` falls back to
the existing ``salg:`` expression vocabulary (see ``to_ssyn_rdf.py``'s
module docstring), and rendering *that* subtree as text reuses rdflib's own
``algebra.translateAlgebra`` — via a throwaway wrapper query
(``SELECT * WHERE { FILTER(<expr>) }``), since ``translateAlgebra`` only
ever seeds its output from a top-level query node (confirmed, see CLAUDE.md
finding #14) — rather than hand-writing a second expression-to-text
renderer duplicating ``_AlgebraTranslator``'s existing ~63-builtin
coverage.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.plugins.sparql.algebra import translateAlgebra
from rdflib.plugins.sparql.parserutils import CompValue, Expr
from rdflib.plugins.sparql.sparql import Prologue, Query

from .from_rdf import _decode as _decode_algebra
from .ssyn_vocab import (
    BIND,
    BIND_VAR,
    EXPR,
    FILTER,
    OPTIONAL,
    SELECT,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    UNION,
    UNION_ALTERNATIVES,
    VARIABLE_DATATYPE,
    WHERE,
)
from .vocab import SALG


def ssyn_rdf_to_query_text(graph: Graph, root) -> str:
    """Render ``root`` (``rdf:type ssyn:SelectQuery``) back into a plain
    SPARQL query string — full IRIs only, no prefixes (matching
    ``translateAlgebra``'s own established behavior, CLAUDE.md finding #3:
    it never reads a ``Prologue``)."""
    select_vars = [_term_text(v) for v in Collection(graph, graph.value(root, SELECT))]
    where_text = _where_group_text(graph, graph.value(root, WHERE))
    return f"SELECT {' '.join(select_vars)} WHERE {{ {where_text} }}"


def _where_group_text(graph: Graph, list_node) -> str:
    return " ".join(_where_element_text(graph, element) for element in Collection(graph, list_node))


def _where_element_text(graph: Graph, element) -> str:
    types = set(graph.objects(element, RDF.type))
    if TRIPLE_PATTERN in types:
        s = graph.value(element, TRIPLE_PATTERN_SUBJECT)
        p = graph.value(element, TRIPLE_PATTERN_PREDICATE)
        o = graph.value(element, TRIPLE_PATTERN_OBJECT)
        return f"{_term_text(s)} {_predicate_text(graph, p)} {_term_text(o)} ."
    if OPTIONAL in types:
        inner = _where_group_text(graph, graph.value(element, WHERE))
        return f"OPTIONAL {{ {inner} }}"
    if FILTER in types:
        return f"FILTER({_expr_text(graph, graph.value(element, EXPR))})"
    if BIND in types:
        expr_text = _expr_text(graph, graph.value(element, EXPR))
        var_text = _term_text(graph.value(element, BIND_VAR))
        return f"BIND({expr_text} AS {var_text})"
    if UNION in types:
        alts = [
            _where_group_text(graph, alt)
            for alt in Collection(graph, graph.value(element, UNION_ALTERNATIVES))
        ]
        return " UNION ".join(f"{{ {a} }}" for a in alts)
    raise NotImplementedError(
        f"starsparql.ssyn_to_text: WHERE-clause element types {types!r} not modeled yet"
    )


def _term_text(term) -> str:
    if isinstance(term, Literal) and term.datatype == VARIABLE_DATATYPE:
        return "?" + str(term)
    return term.n3()


def _predicate_text(graph: Graph, term) -> str:
    """A predicate position may be a genuine property path — see
    to_ssyn_rdf.py's _encode_predicate, which falls back to the existing
    salg: path encoding (to_rdf._encode_path) for that case, the same
    salg:-boundary principle used for expressions. Decode it back into a
    real rdflib.paths.Path object (from_rdf._decode already knows how,
    dispatching on the node's salg: type) and reuse *its* own .n3() —
    Path objects already render themselves as valid SPARQL path syntax,
    no new rendering logic needed."""
    if isinstance(term, BNode) and (term, RDF.type, None) in graph:
        types = {str(t) for t in graph.objects(term, RDF.type)}
        if any(t.startswith(str(SALG)) for t in types):
            path = _decode_algebra(term, graph)
            return path.n3()
    return _term_text(term)


def _expr_text(graph: Graph, expr_node) -> str:
    decoded_expr = _decode_algebra(expr_node, graph)
    return render_expr_text(decoded_expr)


def _simplify_expr_immutable(expr):
    """A non-mutating equivalent of ``rdflib.plugins.sparql.operators
    .simplify`` — same collapsing rule (any ``*Expression``-named node
    whose ``.other`` is absent/``None`` collapses to its own ``.expr``,
    recursively), but rdflib's own version is genuinely unsafe to reuse
    here: it mutates its input **in place** for every node it doesn't
    collapse outright (``expr[k] = simplify(expr[k])`` on each remaining
    key) — confirmed live that calling it on a still-referenced
    ``starsparql.srl_ast.FilterElement.expr`` silently corrupted that same
    object's nested structure as a side effect (a later equality check
    broke, even though the mutating call's own return value was never
    stored anywhere). ``copy.deepcopy`` isn't a fix either — ``Expr``'s
    constructor takes ``evalfn`` positionally in a shape deepcopy's default
    reconstruction can't satisfy (confirmed live: ``TypeError: Expr
    .__init__() missing 1 required positional argument``). Building fresh
    nodes bottom-up, as this does, sidesteps both problems - the original
    tree is never touched, and each ``Expr`` node is reconstructed via its
    own real constructor with its original ``_evalfn`` reattached.

    Needed at all because a full ``parseQuery``/``translateQuery`` pipeline
    always runs (the mutating) ``simplify`` as part of translating the raw
    grammar tree, collapsing every trivial single-operand precedence-chain
    wrapper (``ConditionalOrExpression``/``ConditionalAndExpression``/
    ``AdditiveExpression``/... with no real ``other``) down to its own
    inner value - confirmed live that skipping this crashes
    ``_AlgebraTranslator.sparql_query_text`` outright (``TypeError:
    'NoneType' object is not iterable``) on an otherwise completely
    ordinary shape like plain ``FILTER(?age > 26)`` (no ``&&``). A caller
    that already goes through a full query parse (every existing
    ``ssyn_to_text.py`` caller) gets this for free from ``translateQuery``
    itself; a caller that only ever ran a bare, standalone ``Constraint``/
    ``Expression`` parse - as SRL's own grammar does, since SRL text is
    never a full SPARQL query - does not, and needs it applied explicitly.
    """
    if isinstance(expr, list):
        return [_simplify_expr_immutable(item) for item in expr]
    if not isinstance(expr, CompValue):
        return expr
    if expr.name.endswith("Expression") and expr.other is None:
        return _simplify_expr_immutable(expr.expr)
    new_values = {k: _simplify_expr_immutable(v) for k, v in expr.items()}
    if isinstance(expr, Expr):
        evalfn = expr._evalfn.__func__ if expr._evalfn is not None else None
        return Expr(expr.name, evalfn, **new_values)
    return CompValue(expr.name, **new_values)


def render_expr_text(expr) -> str:
    """Render a real algebra expression node (an ``Expr``/``CompValue``
    tree) as text by wrapping it in a throwaway query and reusing rdflib's
    own translateAlgebra, then slicing out the FILTER(...) contents — see
    this module's docstring for why. Public (not module-private) since
    ``srl_to_text.py`` reuses it directly too — SRL's own ``filter.expr``/
    ``assign.expr`` are the same real rdflib ``Expr`` trees, no RDF
    round-trip needed to call this. See :func:`_simplify_expr_immutable`
    for why the expression is simplified via a fresh, non-mutating rebuild
    rather than rdflib's own (in-place-mutating) ``operators.simplify``."""
    expr = _simplify_expr_immutable(expr)
    wrapper = CompValue(
        "SelectQuery",
        p=CompValue(
            "Project",
            p=CompValue("Filter", expr=expr, p=CompValue("BGP", triples=[])),
            PV=[],
        ),
        datasetClause=None,
        PV=[],
    )
    text = translateAlgebra(Query(Prologue(), wrapper))
    start = text.index("FILTER(") + len("FILTER")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    raise RuntimeError(f"starsparql.ssyn_to_text: unbalanced parens rendering expression: {text!r}")
