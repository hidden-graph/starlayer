"""Machine-readable table of every registered constraint component and node-expression operator, for the Rust port.

``component_table()`` is generated from the live registries (``components.registry.REGISTRY`` and
``expressions.OPERATORS``), so a component or operator added to the engine appears in the table at once. What a registry
cannot know (scope, what the component needs from the executor, the spec clause) is annotated by hand in ``_COMPONENT_META``
and ``_OPERATOR_META`` below; a row with no annotation has ``"annotated": false``, and
``tests/shacl_engine/test_plan_json.py`` fails on such a row, so the annotation cannot drift behind the registry.

``needs`` flags (per component):

* ``graph``: reads the data graph through the five-method interface (every component).
* ``shapes_graph``: reads RDF lists or other shapes-graph structure through the term store, not only ``Shape`` fields.
* ``sparql``: needs a SPARQL engine with pre-binding (SHACL SPARQL Appendix A).
* ``conforms``: recurses into other shapes (``Context.conforms``).
* ``cross_focus``: needs state across focus nodes (``sh:uniqueValuesFor``: the focus nodes of the whole shape).

``scope``: ``value_node`` (one verdict per value node) or ``focus_node`` (a verdict over the focus node's whole value set).

CLI: ``python -m starlayer.shacl_engine.component_table`` prints the table as JSON.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.components.registry import REGISTRY
from starlayer.shacl_engine.expressions import OPERATORS, SHNEX, SPARQL_NS
from starlayer.shacl_engine.plan import SH

UNVERIFIED = "unverified"
_SALG = "https://github.com/hidden-graph/starlayer/ns/sparql/algebra#"


def _local(iri: str) -> str:
    return iri.rsplit("#", 1)[-1]


def _c(scope, required, optional=(), *, shapes=False, sparql=False, conforms=False, cross=False, clause=UNVERIFIED, note=""):
    return {
        "scope": scope,
        "required": tuple(required),
        "optional": tuple(optional),
        "needs": {"graph": True, "shapes_graph": shapes, "sparql": sparql, "conforms": conforms, "cross_focus": cross},
        "clause": clause,
        "note": note,
    }


V, F = "value_node", "focus_node"

# Keyed by the component's local name in the sh: namespace (or the full IRI for components outside it).
_COMPONENT_META: dict[str, dict[str, Any]] = {
    "ClassConstraintComponent": _c(V, ["class"], shapes=True, note="a list value is a union (frozen decision 3)"),
    "DatatypeConstraintComponent": _c(V, ["datatype"], shapes=True, note="a list value is a union; lexical forms matter"),
    "NodeKindConstraintComponent": _c(V, ["nodeKind"], shapes=True, note="sh:TripleTerm matches only a triple term"),
    "MinCountConstraintComponent": _c(F, ["minCount"]),
    "MaxCountConstraintComponent": _c(F, ["maxCount"]),
    "MinExclusiveConstraintComponent": _c(V, ["minExclusive"]),
    "MinInclusiveConstraintComponent": _c(V, ["minInclusive"]),
    "MaxExclusiveConstraintComponent": _c(V, ["maxExclusive"]),
    "MaxInclusiveConstraintComponent": _c(V, ["maxInclusive"]),
    "MinLengthConstraintComponent": _c(V, ["minLength"]),
    "MaxLengthConstraintComponent": _c(V, ["maxLength"]),
    "PatternConstraintComponent": _c(V, ["pattern"], ["flags"], note="regex dialect: XPath/XSD flags s m i x q"),
    "LanguageInConstraintComponent": _c(V, ["languageIn"], shapes=True),
    "UniqueLangConstraintComponent": _c(F, ["uniqueLang"], note="only the term true activates"),
    "SingleLineConstraintComponent": _c(V, ["singleLine"], note="only the term true activates"),
    "EqualsConstraintComponent": _c(F, ["equals"], shapes=True, note="the parameter is a property path term"),
    "DisjointConstraintComponent": _c(F, ["disjoint"], shapes=True, note="the parameter is a property path term"),
    "LessThanConstraintComponent": _c(V, ["lessThan"], shapes=True, note="the parameter is a property path term"),
    "LessThanOrEqualsConstraintComponent": _c(V, ["lessThanOrEquals"], shapes=True, note="the parameter is a property path term"),
    "SubsetOfConstraintComponent": _c(V, ["subsetOf"], shapes=True, note="the parameter is a property path term"),
    "HasValueConstraintComponent": _c(F, ["hasValue"]),
    "InConstraintComponent": _c(V, ["in"], shapes=True),
    "MinListLengthConstraintComponent": _c(V, ["minListLength"], note="the value node is an rdf:list in the data graph"),
    "MaxListLengthConstraintComponent": _c(V, ["maxListLength"], note="the value node is an rdf:list in the data graph"),
    "UniqueMembersConstraintComponent": _c(V, ["uniqueMembers"], note="the value node is an rdf:list in the data graph"),
    "MemberShapeConstraintComponent": _c(V, ["memberShape"], conforms=True, note="the value node is an rdf:list in the data graph"),
    "SomeValueConstraintComponent": _c(F, ["someValue"], conforms=True),
    "NotConstraintComponent": _c(V, ["not"], conforms=True, clause="Core 6.7.3 (recursion, sh:not cycle fails)"),
    "AndConstraintComponent": _c(V, ["and"], shapes=True, conforms=True, clause="Core 6.7.3 (recursion)"),
    "OrConstraintComponent": _c(V, ["or"], shapes=True, conforms=True, clause="Core 6.7.3 (recursion)"),
    "XoneConstraintComponent": _c(V, ["xone"], shapes=True, conforms=True, clause="Core 6.7.3 (recursion)"),
    "NodeConstraintComponent": _c(V, ["node"], conforms=True, clause="Core 6.7.3 (recursion)"),
    "QualifiedMinCountConstraintComponent": _c(
        F, ["qualifiedValueShape", "qualifiedMinCount"], ["qualifiedValueShapesDisjoint"], shapes=True, conforms=True,
        note="siblings for the disjoint case are read from the shapes graph (sh:property parents)",
    ),  # fmt: skip
    "QualifiedMaxCountConstraintComponent": _c(
        F, ["qualifiedValueShape", "qualifiedMaxCount"], ["qualifiedValueShapesDisjoint"], shapes=True, conforms=True,
        note="siblings for the disjoint case are read from the shapes graph (sh:property parents)",
    ),  # fmt: skip
    "ClosedConstraintComponent": _c(
        V, ["closed"], ["ignoredProperties"], shapes=True,
        note="allowed predicates: the shape's sh:path of sh:property shapes plus ignoredProperties; sh:ByTypes reads rdfs:Class shapes",
    ),  # fmt: skip
    "ReifierShapeConstraintComponent": _c(
        V, [], ["reifierShape", "reificationRequired"], conforms=True,
        note="at least one of the two parameters; property shapes with a predicate path only",
    ),  # fmt: skip
    "RootClassConstraintComponent": _c(V, ["rootClass"], note="subclass triples from the data graph only (frozen decision 5)"),
    "UniqueValuesForConstraintComponent": _c(
        F, ["uniqueValuesFor"], shapes=True, cross=True, clause="Core 7.9.5",
        note="peers are the shape's own targets; a node missing any listed property is not compared",
    ),  # fmt: skip
    "ExpressionConstraintComponent": _c(V, ["expression"], conforms=True, clause="Node Expressions 7", note="evaluates a node expression with scope value=v"),
    "NodeByExpressionConstraintComponent": _c(V, ["nodeByExpression"], conforms=True, clause="Node Expressions 7"),
    "SPARQLConstraintComponent": _c(
        F, ["sparql"], sparql=True, shapes=True, clause="SPARQL-Related Features 3",
        note="the sh:sparql node (select, prefixes, message, severity, resultAnnotation) is read from the term store",
    ),  # fmt: skip
    _SALG + "NoUnboundProjectedVariablesConstraintComponent": _c(
        V, ["noUnboundProjectedVariables"], clause="extension (starlayer.sparql.salg), not SHACL",
        note="lazy trampoline into starlayer.sparql.salg.engine_components; a port may omit it",
    ),  # fmt: skip
}


def _o(key, aux=(), arity="1", *, graph=False, shapes=False, conforms=False, sparql=None, clause=UNVERIFIED, note=""):
    return {
        "key": key,
        "aux": tuple(aux),
        "arity": arity,
        "needs": {
            "graph": graph,
            "conforms": conforms,
            "sparql_engine": sparql == "engine",
            "sparql_functions": sparql == "functions",
        },
        "clause": clause,
        "note": note,
    }


# Node expression operators (shnex:). ``arity``: "const" (the key's value is a constant, not an expression), "1" (one
# expression), "list:N" (a list of N expressions), "list" (a list of any length), "shape" (a shape node).
_NE = "Node Expressions"
_OPERATOR_META: dict[str, dict[str, Any]] = {
    SHNEX + "arg": _o("arg", arity="const", note="reads the scope: an integer index or a parameter path IRI"),
    SHNEX + "var": _o("var", arity="const", note="variable name; focusNode is the current focus node"),
    SHNEX + "pathValues": _o("pathValues", ["focusNode"], "const", graph=True, note="the key's value is a path term; focusNode is an optional expression"),
    SHNEX + "exists": _o("exists", arity="1"),
    SHNEX + "if": _o("if", ["then", "else"], "1", note="then/else are expressions; a missing branch gives the empty list"),
    SHNEX + "distinct": _o("distinct"),
    SHNEX + "intersection": _o("intersection", arity="list"),
    SHNEX + "concat": _o("concat", arity="list"),
    SHNEX + "remove": _o("remove", ["nodes"], "1"),
    SHNEX + "limit": _o("limit", ["nodes"], "const", note="an xsd:integer constant"),
    SHNEX + "offset": _o("offset", ["nodes"], "const", note="an xsd:integer constant"),
    SHNEX + "orderBy": _o("orderBy", ["nodes", "desc"], "1"),
    SHNEX + "flatMap": _o("flatMap", ["nodes"], "1", note="the body runs per input node with that node as focus node"),
    SHNEX + "filterShape": _o("filterShape", ["nodes"], "shape", graph=True, conforms=True),
    SHNEX + "findFirst": _o("findFirst", ["nodes"], "shape", graph=True, conforms=True),
    SHNEX + "matchAll": _o("matchAll", ["nodes"], "shape", graph=True, conforms=True),
    SHNEX + "count": _o("count"),
    SHNEX + "min": _o("min"),
    SHNEX + "max": _o("max"),
    SHNEX + "sum": _o("sum", note="SPARQL SUM numeric promotion"),
    SHNEX + "instancesOf": _o("instancesOf", graph=True, note="subclass closure from the data graph"),
    SHNEX + "nodesMatching": _o("nodesMatching", arity="shape", graph=True, conforms=True, note="candidates: every subject and object of the data graph"),
    SHNEX + "conformsToShape": _o("conformsToShape", arity="list:2", conforms=True, note="(node, shape IRI)"),
    str(SH.select): _o("select", arity="const", sparql="engine", graph=True, clause="SPARQL-Related Features (node expression)", note="a SELECT projecting one variable; this and scope variables pre-bound"),
    str(SH.sparqlExpr): _o("sparqlExpr", arity="const", sparql="engine", graph=True, clause="SPARQL-Related Features (node expression)", note="a SPARQL expression, run as SELECT (expr AS ?result) {}"),
}

# sparql: functions (SPARQL_NS). name -> (min arity, max arity or None for variadic); evaluated by a SPARQL function library.
_SPARQL_FN_ARITY: dict[str, tuple[int, int | None]] = {}
for _n in (
    "abs ceil floor round datatype day hours minutes month year seconds timezone tz lang langdir str strlen ucase lcase "
    "encode_for_uri encode iri uri isBlank isIRI isURI isLiteral isNumeric isTriple md5 sha1 sha256 sha384 sha512 subject "
    "predicate object hasLangdir bound logical-not unary-plus unary-minus"
).split():
    _SPARQL_FN_ARITY[_n] = (1, 1)
for _n in (
    "contains strstarts strends strbefore strafter strdt strlang langMatches sameTerm equals sameValue not-equals less-than "
    "greater-than less-than-or-equal greater-than-or-equal plus subtract multiply divide"
).split():
    _SPARQL_FN_ARITY[_n] = (2, 2)
for _n in ("now", "rand", "struuid", "uuid"):
    _SPARQL_FN_ARITY[_n] = (0, 0)
_SPARQL_FN_ARITY.update(
    {
        "bnode": (0, 1), "substr": (2, 3), "replace": (3, 4), "regex": (2, 3), "triple": (3, 3), "strlangdir": (3, 3),
        "if": (3, 3), "hasLang": (1, 2), "concat": (0, None), "coalesce": (0, None), "logical-or": (0, None),
        "logical-and": (0, None),
    }
)  # fmt: skip
_SPARQL_SPECIAL = {"bound", "coalesce", "if", "logical-or", "logical-and", "hasLang"}  # not delegated to a SPARQL template


def _operator_meta(iri: str) -> dict[str, Any] | None:
    if iri in _OPERATOR_META:
        return _OPERATOR_META[iri]
    if iri.startswith(SPARQL_NS):
        name = iri[len(SPARQL_NS) :]
        if name in _SPARQL_FN_ARITY:
            lo, hi = _SPARQL_FN_ARITY[name]
            arity = f"list:{lo}" if lo == hi else (f"list:{lo}..{hi if hi is not None else 'n'}")
            return _o(
                name, arity=arity, sparql="functions", clause=UNVERIFIED,
                note="arguments are a list of expressions; an unbound argument gives the empty list; "
                + ("evaluated by the engine (lazy, three-valued)" if name in _SPARQL_SPECIAL else "delegated to the SPARQL function of the same name"),
            )  # fmt: skip
    return None


def component_rows() -> list[dict[str, Any]]:
    rows = []
    for iri, spec in REGISTRY.items():
        meta = _COMPONENT_META.get(str(iri)) or _COMPONENT_META.get(_local(str(iri)))
        preds = [str(p) for p in spec.predicates]
        by_local = {_local(p): p for p in preds}
        if meta is None:
            rows.append(
                {"component": str(iri), "annotated": False, "parameters": preds, "required": [], "optional": preds,
                 "scope": UNVERIFIED, "needs": {}, "clause": UNVERIFIED, "note": "", "implementation": spec.fn.__module__ + "." + spec.fn.__name__}
            )  # fmt: skip
            continue
        unknown = [p for p in (*meta["required"], *meta["optional"]) if p not in by_local]
        rows.append(
            {
                "component": str(iri),
                "annotated": not unknown and set(by_local) == {*meta["required"], *meta["optional"]},
                "parameters": preds,
                "required": [by_local[p] for p in meta["required"] if p in by_local],
                "optional": [by_local[p] for p in meta["optional"] if p in by_local],
                "scope": meta["scope"],
                "needs": dict(meta["needs"]),
                "clause": meta["clause"],
                "note": meta["note"],
                "implementation": spec.fn.__module__ + "." + spec.fn.__name__,
            }
        )
    return rows


def operator_rows() -> list[dict[str, Any]]:
    rows = []
    for iri in OPERATORS:
        iri = str(iri)
        meta = _operator_meta(iri)
        ns = "shnex" if iri.startswith(SHNEX) else "sparql" if iri.startswith(SPARQL_NS) else "sh"
        if meta is None:
            rows.append({"operator": iri, "namespace": ns, "annotated": False, "key": iri, "aux": [], "arity": UNVERIFIED,
                         "needs": {}, "clause": UNVERIFIED, "note": ""})  # fmt: skip
            continue
        rows.append(
            {
                "operator": iri,
                "namespace": ns,
                "annotated": True,
                "key": iri,
                "aux": [SHNEX + a for a in meta["aux"]],
                "arity": meta["arity"],
                "needs": dict(meta["needs"]),
                "clause": meta["clause"],
                "note": meta["note"],
            }
        )
    return rows


def component_table() -> dict[str, Any]:
    """The whole table. ``dynamic`` names what is not in a registry: SPARQL-based components declared in a shapes graph."""
    return {
        "components": component_rows(),
        "operators": operator_rows(),
        "dynamic": {
            "sparql_based_components": (
                "Declared per shapes graph as sh:ConstraintComponent with sh:parameter and a validator; read by "
                "components.sparql_components.declared_components (SPARQL-Related Features 4). Required parameters are the "
                "non-optional ones; needs: graph, shapes_graph, sparql."
            ),
            "custom_functions": "sh:ListParameterExpressionFunction / sh:NamedParameterExpressionFunction declared in the shapes graph; see expressions._custom_functions.",
        },
    }


def main() -> int:
    json.dump(component_table(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
