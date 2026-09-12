"""Native support for SHACL 1.2 Node Expressions' ``shnex:`` namespace.

The W3C Working Draft (https://www.w3.org/TR/shacl12-node-expr/) moved node
expression combinators to a dedicated namespace,
``shnex: = http://www.w3.org/ns/shacl-node-expr#`` - distinct from the older
``sh:union``/``sh:intersection``/``sh:filterShape``/``sh:path`` forms pySHACL
0.40.0 still implements natively in
``pyshacl.helper.expression_helper.nodes_from_node_expression``. This module
adds the ~20 new ``shnex:`` operators (``shnex:pathValues``,
``shnex:filterShape``, ``shnex:var``, ``shnex:if``/``then``/``else``,
``shnex:exists``, ``shnex:distinct``, ``shnex:remove``, ``shnex:intersection``,
``shnex:concat``, ``shnex:orderBy``/``desc``, ``shnex:limit``,
``shnex:offset``, ``shnex:flatMap``, ``shnex:findFirst``, ``shnex:matchAll``,
``shnex:count``/``min``/``max``/``sum``, ``shnex:instancesOf``,
``shnex:nodesMatching``, ``shnex:conformsToShape``, ``shnex:arg``) without touching pySHACL's own implementation of the
old forms - old and new coexist, evaluated by whichever engine actually
understands the blank node in question.

Also implements the spec's "Custom Node Expressions" mechanism
(https://w3c.github.io/data-shapes/shacl12-node-expr/#custom-node-expressions):
user-declared, shapes-graph-defined node-expression functions, dispatched via
``_custom_function_registry``/``_eval_custom_function_call`` rather than a
fixed predicate table, since the call predicate is itself shapes-graph data.
Two forms, both node-expression call sites (not the separate, **still
unimplemented**, mechanism for calling one as an ordinary SPARQL function by
name from ``sh:select``/``sh:sparqlExpr`` query text - see
``docs/shacl12-gap-matrix.md``):

- **Custom List Parameter Functions** (``sh:ListParameterExpressionFunction``):
  called via the function's own IRI, e.g. ``[ ex:spacedConcat ( "a" "b" ) ]``;
  arguments read inside ``sh:bodyExpression`` via ``[ shnex:arg 0 ]``,
  ``[ shnex:arg 1 ]`` (positional, ``xsd:integer``).
- **Custom Named Parameter Functions** (``sh:NamedParameterExpressionFunction``,
  aka "named node expressions"): called via one of the function's own *key
  parameters'* ``sh:path`` IRI, e.g. ``[ ex:average [ shnex:pathValues
  ex:employee ] ]``; read via ``[ shnex:arg ex:average ]`` (keyed by the
  parameter's own ``sh:path`` IRI). A blank node's key-parameter predicate(s)
  must resolve to exactly one function - matching more than one raises
  ``ValueError``, per the spec's "key parameters ... must be disjoint"
  requirement.

Both evaluate ``sh:bodyExpression`` in a *fresh* scope (only the bound
arguments, plus ``focusNode``) rather than the caller's own ``scope`` -
real function-call isolation, not lexical closure over the caller's
``shnex:var`` bindings, per the spec's own
``evalExpr(expr, ..., scope) -> evalExpr(body, ..., argScope)`` notation.

Unlike pySHACL's own ``Set``-returning evaluator, ``shnex:`` is explicitly
order-sensitive (``shnex:orderBy``/``limit``/``offset``/``distinct``/
``shnex:concat`` all depend on it), so :func:`eval_expr` returns an ordered
``list``, not a ``set``.

Wired in by :func:`patch_node_expressions_for_shnex`, which replaces the
``nodes_from_node_expression`` name pySHACL's own call sites imported at
their module scope (``pyshacl.constraints.advanced`` for ``sh:values``,
``pyshacl.rules.triple`` for ``sh:TripleRule``) with a wrapper that
recognizes ``shnex:``-typed expressions first and delegates to pySHACL's
original, unmodified function for everything else - regression-safe and
purely additive, matching the narrow-patch discipline used elsewhere in
``starshacl/validator.py`` (e.g. ``_patch_shape_validate_for_filter_shape``).

**Known limitation**: ``shnex:min``/``max``/``shnex:orderBy`` comparison
uses RDFLib's own typed ``Literal`` ordering (correct for numeric/date/
string literals in practice) rather than a byte-exact reimplementation of
the SPARQL ORDER BY algebra.

``shnex:instancesOf`` matches ``rdf:type`` against the given class *or any
of its transitive* ``rdfs:subClassOf`` *descendants* (searching both the
data graph and the shapes graph, via ``validator.py``'s
``_transitive_subclasses`` - the same helper ``sh:ShapeClass``'s implicit
target discovery uses), independent of the caller's ``inference=`` setting.

**Not a departure from the rest of this codebase, despite an earlier
version of this docstring claiming otherwise** - corrected 2026-09-10 after
a direct user question ("does shnex:instancesOf perform inferencing on
class membership - should it?") prompted checking rather than continuing to
assume. The spec's own "InstancesOf Expressions" section defines this
purely in terms of the "SHACL instance" term (shared with ``sh:targetClass``
/``sh:class``) and says outright (non-normatively) that "the definition of
SHACL instance includes instances of subclasses of the given class." A live
check of plain, unpatched ``pyshacl.validate()`` (no ``inference=`` argument
at all) confirms both ``sh:targetClass`` (``pyshacl/shape.py``'s
``transitive_subjects(RDFS_subClassOf, tc)``, and its SPARQL-mode
``rdf:type/rdfs:subClassOf*`` property path) and ``sh:class``
(``ClassConstraintComponent``'s own ``ASK {$value rdf:type/rdfs:subClassOf*
$class .}``) already do exactly this same unconditional subclass-closure
check, with no dependency on ``inference=`` either. Subclass reasoning is
baseline SHACL Core semantics for *any* class-membership test - not an
opt-in inference tier - so ``shnex:instancesOf`` doing it unconditionally
here isn't a special case at all, just the same requirement reimplemented
at a different call site (node-expression evaluation has no access to
pySHACL's own ``ClassConstraintComponent``/target-resolution internals, so
it can't literally reuse their query, only match their semantics). What
``inference=`` actually gates is unrelated and heavier: RDFS closure beyond
the class hierarchy, and OWL-RL entailments (``owl:equivalentClass``,
property-based classification, etc.) - none of which ``shnex:instancesOf``,
``sh:targetClass``, or ``sh:class`` attempt on their own either.
"""

from __future__ import annotations

import weakref
from typing import Any

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, XSD, Namespace

from starshacl.sparql_node_expressions import eval_sparql_expr, is_sparql_expr
from starshacl.types import is_dirlangstring_like, is_triple_term_like

SHNEX = Namespace("http://www.w3.org/ns/shacl-node-expr#")
SH = Namespace("http://www.w3.org/ns/shacl#")
SH_this = URIRef("http://www.w3.org/ns/shacl#this")

_MAX_RECURSION = 50

# Predicates that uniquely identify a shnex: expression type ("a blank node
# that is the subject of the following properties is called a <foo>
# expression" - one entry per construct in the spec). shnex:nodes,
# shnex:then, shnex:else, shnex:desc are companion arguments, never
# defining predicates on their own.
_DEFINING_PREDICATES = (
    SHNEX.pathValues,
    SHNEX.filterShape,
    SHNEX["var"],
    SHNEX["if"],
    SHNEX.exists,
    SHNEX.distinct,
    SHNEX.remove,
    SHNEX.intersection,
    SHNEX.concat,
    SHNEX.orderBy,
    SHNEX.limit,
    SHNEX.offset,
    SHNEX.flatMap,
    SHNEX.findFirst,
    SHNEX.matchAll,
    SHNEX["count"],
    SHNEX["min"],
    SHNEX["max"],
    SHNEX.sum,
    SHNEX.instancesOf,
    SHNEX.nodesMatching,
    SHNEX.conformsToShape,
    SHNEX["arg"],
)


def _is_shnex_expr(sg: Any, expr: Any) -> bool:
    """True if ``expr`` is a blank node carrying at least one shnex: defining predicate."""
    if not isinstance(expr, BNode):
        return False
    present = set(sg.graph.predicates(expr))
    return any(p in present for p in _DEFINING_PREDICATES)


def _defining_predicate(sg: Any, expr: BNode) -> URIRef:
    present = set(sg.graph.predicates(expr))
    matches = [p for p in _DEFINING_PREDICATES if p in present]
    if len(matches) > 1:
        raise ValueError(
            f"Node expression {expr} has more than one shnex: defining predicate "
            f"({[str(m) for m in matches]}) - a blank node may only be one kind of "
            "node expression."
        )
    return matches[0]


_custom_function_registry_cache: "weakref.WeakKeyDictionary[Any, dict[Any, Any]]" = weakref.WeakKeyDictionary()


def _custom_function_registry(sg: Any) -> dict[Any, Any]:
    """Map each *call predicate* to the custom node-expression function IRI it
    invokes (https://www.w3.org/TR/shacl12-node-expr/#custom-node-expressions):

    - A ``sh:ListParameterExpressionFunction`` IRI maps to itself - a call
      site uses the function's own IRI directly as the blank node's one and
      only predicate, e.g. ``[ ex:spacedConcat ( "a" "b" ) ]``.
    - Each *key* parameter (``sh:parameter [ sh:path ex:foo ; sh:keyParameter
      true ]``) of a ``sh:NamedParameterExpressionFunction`` maps to that
      function - a call site uses the key parameter's own ``sh:path`` IRI as
      (one of) the blank node's predicates, e.g. ``[ ex:average [...] ]``.
      Confirmed live against the spec's own worked examples.

    Computed once per distinct shapes-graph object and cached in a
    ``WeakKeyDictionary`` keyed on ``sg.graph`` - same pattern and same
    same-*content*-not-same-*object* caveat as
    ``native_components._cross_node_reachable_shapes``, and safe for the same
    reason: every native component evaluating shapes from one ``validate()``/
    ``apply_rules()`` call shares the identical shapes-graph object.
    """
    cached = _custom_function_registry_cache.get(sg.graph)
    if cached is not None:
        return cached

    registry: dict[Any, Any] = {}
    for fn in sg.graph.subjects(RDF.type, SH.ListParameterExpressionFunction):
        registry[fn] = fn
    for fn in sg.graph.subjects(RDF.type, SH.NamedParameterExpressionFunction):
        for param in sg.graph.objects(fn, SH.parameter):
            if (param, SH.keyParameter, Literal(True)) not in sg.graph:
                continue
            for path in sg.graph.objects(param, SH.path):
                registry[path] = fn

    _custom_function_registry_cache[sg.graph] = registry
    return registry


def _eval_custom_function_call(
    expr: Any,
    call_predicates: set,
    registry: dict[Any, Any],
    focus_node: Any,
    data_graph: Any,
    sg: Any,
    recurse_depth: int,
) -> list[Any]:
    """Evaluate a call to a custom List/Named Parameter Expression Function.

    Implements both "EVALUATION OF CUSTOM LIST/NAMED PARAMETER EXPRESSIONS"
    algorithms from the spec, which are identical up to how ``argScope`` gets
    built: ``evalExpr(expr, focusGraph, focusNode, scope) ->
    evalExpr(body, focusGraph, focusNode, argScope)`` - the function body is
    evaluated in a *fresh* scope containing only the bound arguments (plus
    ``focusNode``, since ``shnex:var "focusNode"`` reads it out of scope like
    any other entry), never merged with the caller's own ``shnex:var``
    bindings - real function-call isolation, not lexical closure.

    For the named-parameter case, ``argScope`` is built from *every*
    declared ``sh:parameter`` of ``fn``, not just the key parameter(s) -
    found live (2026-09-11), prompted by a direct user question asking for
    a two-parameter example with one non-key parameter: the spec's own
    "EVALUATION OF CUSTOM NAMED PARAMETER EXPRESSIONS" algorithm says
    "argScope is a map of (parameter) nodes as keys and (argument) nodes
    as values, so that **each parameter** of f has the value of the
    parameter's sh:path from expr" - not "each key parameter". An earlier
    version of this function only read ``call_predicates`` (the key
    parameter(s) alone, since only key parameters are registered by
    ``_custom_function_registry`` for dispatch purposes), so a call site
    supplying a value for a declared-but-non-key parameter silently lost
    it - confirmed live with a two-parameter function (`ex:name` as the
    key parameter, `ex:greeting` as a plain, non-key one): the whole
    expression evaluated to an empty result instead of reading
    ``ex:greeting``'s value at all. Key parameters are still what the
    registry uses to *find and dispatch to* the right function in the
    first place - that part is unrelated and correct as-is.
    """
    fns = {registry[p] for p in call_predicates}
    if len(fns) > 1:
        raise ValueError(
            f"Node expression {expr} matches key parameters of more than one custom "
            f"node expression function ({[str(f) for f in fns]}) - a blank node may "
            "only call one custom function."
        )
    (fn,) = fns
    body = next(iter(sg.graph.objects(fn, SH.bodyExpression)))

    def _eval_arg(sub_expr: Any) -> list[Any]:
        return eval_expr(sub_expr, focus_node, data_graph, sg, recurse_depth=recurse_depth + 1)

    arg_scope: dict[Any, Any] = {"focusNode": focus_node}
    if (fn, RDF.type, SH.ListParameterExpressionFunction) in sg.graph:
        (list_pred,) = call_predicates  # "subject of exactly one triple" per spec
        arg_list_node = next(iter(sg.graph.objects(expr, list_pred)))
        for index, arg_expr in enumerate(sg.graph.items(arg_list_node)):
            arg_scope[index] = _eval_arg(arg_expr)
    else:
        for param in sg.graph.objects(fn, SH.parameter):
            for path in sg.graph.objects(param, SH.path):
                value_exprs = list(sg.graph.objects(expr, path))
                if value_exprs:
                    arg_scope[path] = _eval_arg(value_exprs[0])

    return eval_expr(body, focus_node, data_graph, sg, scope=arg_scope, recurse_depth=recurse_depth + 1)


def _shape_conforms(sg: Any, shape_node: Any, data_graph: Any, node: Any) -> bool:
    from pyshacl.pytypes import SHACLExecutor

    shape = sg.lookup_shape_from_node(shape_node)
    conforms, _reports = shape.validate(SHACLExecutor(), data_graph, focus=node)
    return conforms


def _term_key(node: Any):
    """Exact-term-equality key, not RDF value equality.

    ``rdflib.Literal.__eq__`` compares by *value* for compatible datatypes
    (e.g. ``Literal("4", datatype=XSD.integer) == Literal("04",
    datatype=XSD.integer)`` is True), but RDF 1.2's own literal term-equality
    (https://www.w3.org/TR/rdf12-concepts/#dfn-literal-term-equality)
    requires the lexical form to match too - two value-equal-but-lexically-
    different literals are different terms. ``shnex:distinct``/``shnex:remove``
    need exact term equality, confirmed via the W3C SHACL 1.2 Node
    Expressions test suite (distinct-termEquality, remove-list-from-list -
    both explicitly construct a value-equal, lexically-different literal to
    verify it's treated as distinct).
    """
    if isinstance(node, Literal):
        return ("LITERAL", str(node), str(node.datatype) if node.datatype else None, node.language)
    return ("TERM", node)


def _numeric_sum(literals: list) -> Literal:
    """Sum numeric literals, promoting the result datatype per SPARQL/XPath's
    own numeric type promotion rules (any xsd:double -> double; else any
    xsd:decimal -> decimal; else xsd:integer) rather than ``Literal(total)``,
    which infers a datatype purely from the *Python* result type - a Python
    ``float`` always becomes ``xsd:double`` regardless of whether the inputs
    were ``xsd:decimal``, silently changing the result's type. Confirmed via
    the W3C SHACL 1.2 Node Expressions test suite (shnex/sum.ttl's
    sum-list-3-mixed/sum-totalRevenue, both summing xsd:decimal inputs and
    expecting an xsd:decimal result).
    """
    total = 0
    datatypes = set()
    for n in literals:
        if not isinstance(n, Literal):
            continue
        total += n.toPython()
        if n.datatype:
            datatypes.add(n.datatype)
    if XSD.double in datatypes:
        result_type = XSD.double
    elif XSD.float in datatypes:
        result_type = XSD.float
    elif XSD.decimal in datatypes:
        result_type = XSD.decimal
    else:
        result_type = XSD.integer
    return Literal(total, datatype=result_type)


def _sort_key(node: Any):
    """Best-effort SPARQL-ORDER-BY-compatible comparison key.

    RDFLib's own typed ``Literal`` ordering handles numeric/date/string
    comparison correctly for the common cases; falls back to ``str()`` for
    anything it can't compare directly (e.g. comparing across incompatible
    datatypes), matching SPARQL's own permissive-fallback spirit rather than
    raising on mixed input.
    """
    if isinstance(node, Literal):
        try:
            return (0, node.toPython())
        except Exception:
            return (1, str(node))
    return (1, str(node))


def eval_expr(
    expr: Any,
    focus_node: Any,
    data_graph: Any,
    sg: Any,
    scope: dict[str, Any] | None = None,
    recurse_depth: int = 0,
) -> list[Any]:
    """Evaluate a SHACL node expression, recognizing ``shnex:`` forms.

    Delegates wholesale to pySHACL's own ``nodes_from_node_expression`` for
    every expression that isn't a ``shnex:``-tagged blank node (constants,
    ``sh:this``, and every old-style ``sh:union``/``sh:intersection``/
    ``sh:path``/``sh:filterShape``/SHACL-function form) - those keep working
    exactly as pySHACL already implements them, unchanged.

    One exception, handled here rather than delegated: a bare *non-empty* RDF
    list (``expr`` itself has ``rdf:first``) is evaluated as "evaluate each
    member as its own node expression, concatenate the results" - confirmed
    via the W3C SHACL 1.2 Node Expressions test suite that this is how
    ``shnex:`` operators taking a list-of-values argument are meant to work,
    e.g. ``shnex:count ( 4 3 3 )``, and also how a bare list works when used
    directly as a whole node expression, e.g. a top-level ``sht:nodeExpr
    ( 1 2 3 )`` evaluating to ``(1 2 3)``. pySHACL's own
    ``nodes_from_node_expression`` has no code path for this at all (only
    ``sh:union``/``sh:intersection`` get list-of-*expressions* treatment, by
    unwrapping the list themselves before ever calling this function on an
    individual member) - confirmed with a minimal pySHACL-only repro that a
    bare list constant misfires as a bogus FunctionExpression call.
    ``shnex:intersection``/``shnex:concat`` already unwrap their own list
    argument via ``sg.graph.items()`` before calling ``_sub()`` per member,
    so they never hit this branch either way.

    The *empty*-list case (``rdf:nil``, or an argument-position convention
    like ``shnex:count []``) is deliberately **not** handled at this
    top-level entry point - it's context-dependent, confirmed by two W3C
    fixtures that contradict each other under one uniform rule: a bare
    top-level ``sht:nodeExpr ()`` (called from outside this function
    entirely, e.g. directly from a test harness) evaluates to ``(rdf:nil)``
    (the constant resource itself, matching pySHACL's own
    plain-URIRef-constant handling), while ``shnex:count``'s "nodes to
    count" *argument* being empty must mean zero nodes, not ``[rdf:nil]``.
    See the internal ``_sub()`` helper below, which every operator uses for
    its own *internal* recursion and which applies that second meaning
    instead - an argument passed to ``_sub()`` is always conceptually "a set
    of result nodes" from the calling operator's point of view, never a
    literal top-level constant.
    """
    from pyshacl.helper.expression_helper import (
        nodes_from_node_expression as _pyshacl_eval,
    )

    if recurse_depth > _MAX_RECURSION:
        raise ValueError("Node expression recursion depth too great - possible cycle.")

    if scope is None:
        scope = {"focusNode": focus_node}

    if is_dirlangstring_like(expr):
        # A DirLangString constant (e.g. "hello"@en--ltr) evaluates to
        # itself - it's a distinct Python class, not an rdflib term, so
        # pySHACL's own nodes_from_node_expression (isinstance URIRef/
        # Literal/BNode checks only) can't recognize it either and raises
        # NotImplementedError instead of treating it as the plain constant
        # it is. Confirmed via the W3C SHACL 1.2 Node Expressions test suite
        # (shnex-sparql/langdir.ttl, hasLangdir.ttl).
        return [expr]

    if is_triple_term_like(expr):
        # A triple-term constant (e.g. "<<( ex:s ex:p ex:o )>>" decoded to a
        # real TripleTerm by StarLayerGraph's public .objects() view)
        # evaluates to itself - pySHACL's own nodes_from_node_expression has
        # no branch for this type at all (only URIRef/Literal/BNode/sh:this),
        # so delegating to it raises NotImplementedError("Unsupported
        # expression ...") instead of treating it as the plain constant it
        # is. Confirmed via the W3C SHACL 1.2 Node Expressions test suite
        # (shnex/constant.ttl's constant-tt case).
        return [expr]

    if isinstance(expr, BNode) and next(sg.graph.predicate_objects(expr), None) is None:
        # A blank node with *no* triples of its own at all evaluates to no
        # nodes at all - confirmed via the W3C SHACL 1.2 Node Expressions
        # test suite (shnex/empty.ttl's top-level "sht:nodeExpr []" expects
        # "()"). Unlike rdf:nil (a URIRef, so never reaches this branch),
        # there's no competing "return the constant itself" reading for a
        # property-less blank node to conflict with, so this is safe
        # universally, not just inside _sub()'s internal-recursion case.
        return []

    if isinstance(expr, BNode) and next(sg.graph.objects(expr, RDF.first), None) is not None:
        results: list[Any] = []
        for member in sg.graph.items(expr):
            results.extend(
                eval_expr(member, focus_node, data_graph, sg, scope=scope, recurse_depth=recurse_depth + 1)
            )
        return results

    if is_sparql_expr(sg, expr):
        def _eval_arg(sub_expr: Any) -> list[Any]:
            return eval_expr(sub_expr, focus_node, data_graph, sg, scope=scope, recurse_depth=recurse_depth + 1)

        return eval_sparql_expr(expr, sg, _eval_arg)

    if isinstance(expr, BNode):
        registry = _custom_function_registry(sg)
        if registry:
            call_predicates = set(sg.graph.predicates(expr)) & set(registry)
            if call_predicates:
                return _eval_custom_function_call(
                    expr, call_predicates, registry, focus_node, data_graph, sg, recurse_depth
                )

    if not _is_shnex_expr(sg, expr):
        return list(_pyshacl_eval(expr, focus_node, data_graph, sg, recurse_depth=recurse_depth))

    pred = _defining_predicate(sg, expr)

    def _sub(sub_expr: Any, sub_focus: Any = focus_node, sub_scope: dict[str, Any] | None = None) -> list[Any]:
        # rdf:nil as an *argument* means "zero nodes" for every internal
        # shnex-to-shnex recursion, never "the constant rdf:nil itself" - a
        # sub-expression argument is always conceptually "a set of result
        # nodes" from the calling operator's point of view. That second
        # reading (a bare top-level rdf:nil evaluating to itself, matching
        # pySHACL's plain-URIRef-constant handling) only applies to a
        # *top-level* eval_expr() call from outside this function entirely -
        # see eval_expr()'s own docstring. Confirmed via the W3C SHACL 1.2
        # Node Expressions test suite (every "-empty" variant of
        # count/min/max/sum/matchAll/findFirst uses "( )"/rdf:nil this way).
        # A property-less blank node argument (the "shnex:count []"
        # spelling) already returns [] universally via eval_expr()'s own
        # top-level check above, reached the same way through this
        # recursive call - no separate check needed here.
        if sub_expr == RDF.nil:
            return []
        return eval_expr(
            sub_expr, sub_focus, data_graph, sg, scope=sub_scope if sub_scope is not None else scope,
            recurse_depth=recurse_depth + 1,
        )

    def _nodes_arg(default_focus: bool = False) -> list[Any]:
        nodes_exprs = list(sg.graph.objects(expr, SHNEX.nodes))
        if nodes_exprs:
            return _sub(nodes_exprs[0])
        if default_focus:
            return [focus_node]
        raise ValueError(f"Node expression {expr} (shnex:{pred.rsplit('#', 1)[-1]}) requires shnex:nodes.")

    if pred == SHNEX.pathValues:
        from pyshacl.helper.expression_helper import value_nodes_from_path

        path_val = next(iter(sg.graph.objects(expr, SHNEX.pathValues)))
        focus_exprs = list(sg.graph.objects(expr, SHNEX.focusNode))
        bases = _sub(focus_exprs[0]) if focus_exprs else [focus_node]
        results: list[Any] = []
        for base in bases:
            results.extend(value_nodes_from_path(sg, base, path_val, data_graph))
        return results

    if pred == SHNEX.filterShape:
        shape_node = next(iter(sg.graph.objects(expr, SHNEX.filterShape)))
        candidates = _nodes_arg()
        return [n for n in candidates if _shape_conforms(sg, shape_node, data_graph, n)]

    if pred == SHNEX["var"]:
        name = str(next(iter(sg.graph.objects(expr, SHNEX["var"]))))
        if name not in scope:
            # An unbound variable evaluates to no nodes, matching SPARQL's
            # own unbound-variable semantics - confirmed via the W3C SHACL
            # 1.2 Node Expressions test suite (var-unbound expects `()`, not
            # an error).
            return []
        value = scope[name]
        return list(value) if isinstance(value, (list, tuple, set)) else [value]

    if pred == SHNEX["arg"]:
        # Reads an argument bound by _eval_custom_function_call()'s argScope -
        # keyed by xsd:integer position (list parameter functions) or by the
        # parameter's own sh:path IRI (named parameter functions), never a
        # plain string, so this can share scope's namespace with shnex:var's
        # string-keyed bindings (str(...)-derived) with no collision risk.
        key_node = next(iter(sg.graph.objects(expr, SHNEX["arg"])))
        key = int(key_node) if isinstance(key_node, Literal) else key_node
        if key not in scope:
            # Unbound argument - matches shnex:var's identical unbound-name
            # convention above (evaluates to no nodes, not an error).
            return []
        value = scope[key]
        return list(value) if isinstance(value, (list, tuple, set)) else [value]

    if pred == SHNEX["if"]:
        cond_expr = next(iter(sg.graph.objects(expr, SHNEX["if"])))
        cond_result = _sub(cond_expr)
        branch_pred = SHNEX["then"] if cond_result == [Literal(True)] else SHNEX["else"]
        branch_exprs = list(sg.graph.objects(expr, branch_pred))
        results = []
        for b in branch_exprs:
            results.extend(_sub(b))
        return results

    if pred == SHNEX.exists:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX.exists)))
        return [Literal(len(_sub(inner_expr)) > 0)]

    if pred == SHNEX.distinct:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX.distinct)))
        seen: set[Any] = set()
        result: list[Any] = []
        for n in _sub(inner_expr):
            key = _term_key(n)
            if key not in seen:
                seen.add(key)
                result.append(n)
        return result

    if pred == SHNEX.remove:
        remove_expr = next(iter(sg.graph.objects(expr, SHNEX.remove)))
        n_list = _nodes_arg()
        m_keys = {_term_key(n) for n in _sub(remove_expr)}
        return [n for n in n_list if _term_key(n) not in m_keys]

    if pred == SHNEX.intersection:
        list_node = next(iter(sg.graph.objects(expr, SHNEX.intersection)))
        members = list(sg.graph.items(list_node))
        result: list[Any] | None = None
        for m in members:
            member_nodes = _sub(m)
            if result is None:
                result = list(member_nodes)
            else:
                member_keys = {_term_key(n) for n in member_nodes}
                result = [n for n in result if _term_key(n) in member_keys]
        # Deduplicate (term-key-aware, order-preserving) - confirmed via the
        # W3C SHACL 1.2 Node Expressions test suite (intersection-three-lists:
        # "this also tests that duplicates are removed").
        seen: set[Any] = set()
        deduped: list[Any] = []
        for n in result or []:
            key = _term_key(n)
            if key not in seen:
                seen.add(key)
                deduped.append(n)
        return deduped

    if pred == SHNEX.concat:
        list_node = next(iter(sg.graph.objects(expr, SHNEX.concat)))
        members = list(sg.graph.items(list_node))
        out: list[Any] = []
        for m in members:
            out.extend(_sub(m))
        return out

    if pred == SHNEX.orderBy:
        order_expr = next(iter(sg.graph.objects(expr, SHNEX.orderBy)))
        n_list = _nodes_arg()
        desc_vals = list(sg.graph.objects(expr, SHNEX.desc))
        descending = bool(desc_vals) and bool(desc_vals[0])
        keyed = []
        for n in n_list:
            # sub_scope must rebind "focusNode" too, not just sub_focus - a
            # comparator like `shnex:var "focusNode"` (the common "sort by
            # each item's own value" identity expression) reads the *scope*
            # dict, not the focus-node argument directly. Without this every
            # item evaluated the same (stale, outer) comparator value,
            # silently leaving the list in its original order - confirmed
            # via the W3C SHACL 1.2 Node Expressions test suite
            # (orderBy-integer-list). Matches the pattern shnex:flatMap
            # already uses correctly below.
            comparator = _sub(order_expr, sub_focus=n, sub_scope={**scope, "focusNode": n})
            # A missing comparator value sorts first - confirmed via the
            # W3C SHACL 1.2 Node Expressions test suite (orderBy-height:
            # "Person3 has no value, meaning it will go to the beginning of
            # the results").
            key = _sort_key(comparator[0]) if comparator else (-1, "")
            keyed.append((key, n))
        keyed.sort(key=lambda pair: pair[0], reverse=descending)
        return [n for _key, n in keyed]

    if pred == SHNEX.limit:
        limit_val = next(iter(sg.graph.objects(expr, SHNEX.limit)))
        n_list = _nodes_arg()
        return n_list[: int(limit_val)]

    if pred == SHNEX.offset:
        offset_val = next(iter(sg.graph.objects(expr, SHNEX.offset)))
        n_list = _nodes_arg()
        return n_list[int(offset_val) :]

    if pred == SHNEX.flatMap:
        map_expr = next(iter(sg.graph.objects(expr, SHNEX.flatMap)))
        n_list = _nodes_arg(default_focus=True)
        out = []
        for n in n_list:
            out.extend(_sub(map_expr, sub_focus=n, sub_scope={**scope, "focusNode": n}))
        return out

    if pred == SHNEX.findFirst:
        shape_node = next(iter(sg.graph.objects(expr, SHNEX.findFirst)))
        n_list = _nodes_arg(default_focus=True)
        for n in n_list:
            if _shape_conforms(sg, shape_node, data_graph, n):
                return [n]
        return []

    if pred == SHNEX.matchAll:
        shape_node = next(iter(sg.graph.objects(expr, SHNEX.matchAll)))
        n_list = _nodes_arg(default_focus=True)
        return [Literal(all(_shape_conforms(sg, shape_node, data_graph, n) for n in n_list))]

    if pred == SHNEX.conformsToShape:
        args = list(sg.graph.items(next(iter(sg.graph.objects(expr, SHNEX.conformsToShape)))))
        if len(args) != 2:
            raise ValueError(
                f"shnex:conformsToShape requires exactly 2 arguments (a node expression and a "
                f"shape), got {len(args)}."
            )
        node_expr, shape_node = args
        nodes = _sub(node_expr)
        if not nodes:
            return []
        return [Literal(all(_shape_conforms(sg, shape_node, data_graph, n) for n in nodes))]

    if pred == SHNEX["count"]:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX["count"])))
        return [Literal(len(_sub(inner_expr)))]

    if pred == SHNEX["min"]:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX["min"])))
        results = _sub(inner_expr)
        return [min(results, key=_sort_key)] if results else []

    if pred == SHNEX["max"]:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX["max"])))
        results = _sub(inner_expr)
        return [max(results, key=_sort_key)] if results else []

    if pred == SHNEX.sum:
        inner_expr = next(iter(sg.graph.objects(expr, SHNEX.sum)))
        results = _sub(inner_expr)
        return [_numeric_sum(results)]

    if pred == SHNEX.instancesOf:
        type_expr = next(iter(sg.graph.objects(expr, SHNEX.instancesOf)))
        type_nodes = _sub(type_expr)
        from starshacl.validator import _transitive_subclasses

        out: list[Any] = []
        seen: set[Any] = set()
        for t in type_nodes:
            for cls in {t} | _transitive_subclasses(data_graph, sg.graph, t):
                for instance in data_graph.subjects(RDF.type, cls):
                    if instance not in seen:
                        seen.add(instance)
                        out.append(instance)
        return out

    if pred == SHNEX.nodesMatching:
        shape_node = next(iter(sg.graph.objects(expr, SHNEX.nodesMatching)))
        candidates: set[Any] = set()
        for s, _p, o in data_graph.triples((None, None, None)):
            candidates.add(s)
            candidates.add(o)
        return [n for n in candidates if _shape_conforms(sg, shape_node, data_graph, n)]

    raise NotImplementedError(f"Unrecognized shnex: node expression {expr!r}")  # pragma: no cover


_node_expressions_patch_status: bool | None = None


def patch_node_expressions_for_shnex() -> bool:
    """Wire ``shnex:`` node-expression support into pySHACL's two call sites.

    Idempotent (patches at most once per process) and defensive: returns
    ``False`` without raising if pySHACL's internals don't match what this
    expects (e.g. a future/past version with different modules/call sites),
    so the caller can decide how to fail.
    """
    global _node_expressions_patch_status
    if _node_expressions_patch_status is not None:
        return _node_expressions_patch_status

    try:
        import pyshacl.constraints.advanced as _advanced_mod
        import pyshacl.rules.triple as _triple_rule_mod

        def _wrapper(expr, focus_node, data_graph, sg, recurse_depth=0):
            return eval_expr(expr, focus_node, data_graph, sg, recurse_depth=recurse_depth)

        _wrapper._starshacl_shnex_patch = True  # type: ignore[attr-defined]

        for mod in (_advanced_mod, _triple_rule_mod):
            existing = getattr(mod, "nodes_from_node_expression", None)
            if not getattr(existing, "_starshacl_shnex_patch", False):
                mod.nodes_from_node_expression = _wrapper

        _node_expressions_patch_status = True
    except Exception:
        _node_expressions_patch_status = False

    return _node_expressions_patch_status
