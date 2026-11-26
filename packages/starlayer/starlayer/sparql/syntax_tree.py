"""SPARQL, SPARQL Update and SRL as RDF syntax trees: text to tree, tree to text, and validation of a tree.

Three public functions work on any of the three kinds of text, and find the kind themselves:

- :func:`sparql_to_tree` reads a SPARQL query, a SPARQL Update request or an SRL rule set and writes it as a tree: ``sqe:``
  (``sparql/sqe/vocab.py``) for a query or an update, ``srl:`` (``srl.py``) for a rule set.
- :func:`tree_to_sparql` writes a tree back as text, by the class of its root.
- :func:`validate_sparql_tree` checks a tree against the shapes of its vocabulary and the checks the shapes cannot state.

A rule set is also reachable as a ``RuleSet`` object (``srl.parse_ruleset``, ``srl.ruleset_to_tree``, ``srl.tree_to_ruleset``,
``srl.ruleset_to_text``), which running it needs; those stay in ``srl.py``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pyoxigraph as ox

from starlayer.errors import FormatError

if TYPE_CHECKING:
    from starlayer.shacl.results import ValidationReport

_PROLOGUE = (
    r"(?:\s+|#[^\n]*|(?:PREFIX\s+[^\s:]*:\s*<[^>]*>)|(?:BASE\s*<[^>]*>)|(?:VERSION\s+(?:'[^']*'|\"[^\"]*\")))*"
)
_UPDATE_START = re.compile(r"(?is)\A" + _PROLOGUE + r"(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|WITH)\b")
_SRL_START = re.compile(r"(?is)\A" + _PROLOGUE + r"(RULE|DATA|IMPORTS)\b")
# text with a prologue and nothing else (PREFIX / BASE / VERSION lines, comments, blanks, or no text at all): an update request with no operation
_PROLOGUE_ONLY = re.compile(r"(?is)\A" + _PROLOGUE + r"\Z")


def sparql_to_tree(text: str, tree_graph: Any = None, root: Any = None, *, base: str | None = None) -> tuple[Any, Any]:
    """Encode SPARQL query text, SPARQL Update text or SRL rule-set text as RDF.

    The kind of text is found by trying the SPARQL query grammar, then the update grammar (when the text starts, after its prologue,
    with an update keyword, or holds only a prologue), then SRL (when it starts with ``RULE``, ``DATA`` or ``IMPORTS``). A query
    gives an ``sqe:`` tree, an update an ``sqe:UpdateRequest`` tree and a rule set an ``srl:RuleSet`` tree. Text that no grammar
    reads is reported with the error of the grammar that read furthest into it.

    Any text a grammar understands gives a tree, even one that breaks the shapes (an unbound projected variable, an unbound head
    variable): nothing is validated here, so text with problems can still be loaded and fixed. Call :func:`validate_sparql_tree`
    on the tree to report those problems, and again after editing a tree directly.

    A query may hold IRIs that are not absolute (``<s>`` with no ``BASE``) or other text an RDF term cannot be: the tree
    keeps each as an opaque stand-in IRI (``urn:starlayer:invalid-iri:...``) that :func:`tree_to_sparql` turns back into the
    original text. A store rewrites some literal lexical forms (``"007"^^xsd:integer`` becomes ``"7"``).

    Text that holds only a prologue (``PREFIX``, ``BASE``, ``VERSION``, comments) or nothing at all is an update request with no
    operation: it loads as an empty ``sqe:UpdateRequest``, and :func:`tree_to_sparql` writes back its prologue (or an empty
    string), which loads again as the same empty request.

    Args:
        text: The SPARQL query, SPARQL Update or SRL text to encode.
        tree_graph: The graph to add the tree to: a ``StarLayerGraph`` (pyoxigraph terms), or an rdflib graph (filled with rdflib
            terms; rdflib is then needed). Defaults to a fresh ``StarLayerGraph``. A graph may hold several trees; give each its
            own ``root`` to tell them apart.
        root: The node to use as the root of the tree: any ``NamedNode`` or ``BlankNode``. Defaults to a fresh blank node. An IRI
            makes the tree findable by that identity later.
        base: The base IRI for relative IRIs in the text, whichever kind it is.

    Returns:
        A ``(tree_graph, root)`` tuple, the tree not checked against the shapes; with no ``tree_graph`` given, a ``StarLayerGraph``
        and a pyoxigraph ``root``.

    Raises:
        FormatError: (kind ``"sparql"``) For text outside every grammar tried, with ``line`` and ``col``; (kind ``"srl"``) when the
            text starts as a rule set and the SRL grammar read furthest into it.
        ExecutionError: (kind ``"limit"``) The text is nested too deeply for Python's stack.
        TypeError: ``root`` is not an IRI or a blank node.
    """
    from .parse_sparql import ast_to_triples, parse_sparql, parse_sparql_update
    from .srl import ruleset_to_tree

    if root is not None:
        from starlayer.shacl.engine.terms import to_engine

        root = to_engine(root)
        if not isinstance(root, (ox.NamedNode, ox.BlankNode)):
            raise TypeError(f"root must be an IRI or a blank node, not {type(root).__name__}")

    ast = None
    try:
        ast = parse_sparql(text, base)
    except FormatError as query_error:
        failures = [query_error]
        if _UPDATE_START.match(text) or _PROLOGUE_ONLY.match(text):
            try:
                ast = parse_sparql_update(text, base)
            except FormatError as error:
                failures.append(error)
        elif _SRL_START.match(text):
            from .parse_srl import parse_srl

            try:
                ruleset = parse_srl(text, base)
            except FormatError as error:
                failures.append(error)
            else:
                return ruleset_to_tree(ruleset, tree_graph, root=root)
        if ast is None:
            raise max(failures, key=lambda e: (e.pos or 0, e is failures[0])) from None  # the grammar that read furthest; a tie is the query's
    triples, root = ast_to_triples(ast, root)
    from starlayer.graph.core import StarLayerGraph

    tree = StarLayerGraph(prefixes={}) if tree_graph is None else tree_graph
    tree.extend(triples)
    return tree, root


def _roots(graph: Any) -> tuple[list[Any], list[Any]]:
    """``(sqe roots, srl roots)`` of an engine-term graph: each ``sqe:Query``, ``sqe:UpdateRequest`` and ``srl:RuleSet`` node."""
    from .sqe.vocab import QUERY, UPDATE_REQUEST
    from .srl import SRL

    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    sqe = {s for cls in (QUERY, UPDATE_REQUEST) for s in graph.subjects(rdf_type, cls)}
    srl = set(graph.subjects(rdf_type, SRL.RuleSet))
    return sorted(sqe, key=str), sorted(srl, key=str)


def tree_to_sparql(tree_graph: Any, root: Any = None) -> str:
    """Write a tree made by :func:`sparql_to_tree` back as text: SPARQL query text, SPARQL Update text or SRL rule-set text by the
    class of ``root`` (``sqe:SelectQuery`` and the other query forms, ``sqe:UpdateRequest``, ``srl:RuleSet``). A query is written
    with the ``PREFIX`` declarations kept on its root wherever one matches. Run the text with ``StarLayerGraph.query()`` or
    ``update()``.

    Args:
        tree_graph: The graph that holds the tree.
        root: The root node to write. It may be left out only when the graph holds exactly one root (one ``sqe:Query``,
            ``sqe:UpdateRequest`` or ``srl:RuleSet``).

    Returns:
        The text.

    Raises:
        ValueError: ``root`` is left out and the graph holds no root or more than one.
        ExecutionError: (kind ``"limit"``) the tree nests too deeply to write within the Python stack; (kind ``"unsupported"``) it
            holds a node, term or operation with no text form.
        FormatError: (kind ``"rdf"``) an ordered child has no ``tree:ord`` or one that is not a non-negative integer, two children of
            one parent and property share an ordinal, or a named node, literal or variable is a child without its ``tree:Item``
            (``graph/ordinals.py``): the tree has no order to write. (kind ``"srl"``) a part of a rule set tree is missing or is
            not what a rule set needs.
    """
    from .sqe._memtree import as_engine_graph
    from .sqe.to_text import render_sqe_tree
    from .srl import SRL, ruleset_to_text, tree_to_ruleset

    graph, root = as_engine_graph(tree_graph, root)
    if root is None:
        found = [*_roots(graph)[0], *_roots(graph)[1]]
        if len(found) != 1:
            raise ValueError(
                "the graph holds no root (no sqe:Query, sqe:UpdateRequest or srl:RuleSet): nothing to write"
                if not found
                else f"the graph holds {len(found)} roots; pass root= to say which one to write"
            )
        root = found[0]
    if (root, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), SRL.RuleSet) in graph:
        return ruleset_to_text(tree_to_ruleset(graph, root))
    return render_sqe_tree(graph, root)


def validate_sparql_tree(tree_graph: Any) -> ValidationReport:
    """Validate a tree made by :func:`sparql_to_tree`, or an LLM- or UI-authored one not yet decoded, against the shapes of its
    vocabulary, and run the checks the shapes cannot state.

    A graph with ``sqe:`` trees (queries, updates) is checked against the ``sqe:`` shapes; when they conform, each query is
    written out with :func:`tree_to_sparql` and checked as ``check_query`` does: the text must be in the grammar, agree with its
    ``VERSION`` and run on an empty graph in Oxigraph, which has the last word on what it accepts. A query with a ``SERVICE``
    pattern (which would send the request) and an update are not run. A structurally broken tree may not write out, so it is left to
    the shapes. Oxigraph runs the query without any custom function, so a query that calls an extension function is rejected here;
    ``check_query`` takes ``custom_functions`` for that.

    A graph with ``srl:`` trees (rule sets) is checked against the ``srl:`` shapes, which cover the structure and the spec's
    section 4.2 well-formedness conditions (an unbound head, filter or assignment variable, a ``SET`` or aggregation variable
    that is already bound, and so on; each is an ``sh:Violation`` whose focus node is the offending element). Two things shapes
    cannot say are added when the structure conforms: that the rules can be ordered (section 4.4) is an ``sh:Violation`` with the
    ``srl:RuleSet`` node as its focus node, and an ``IMPORTS`` entry that is not resolved is an ``sh:Warning``, which does not make
    the report non-conforming.

    A graph with both kinds is checked as each, and the results are merged in one report. A graph with neither is checked
    as an ``sqe:`` graph.

    Goes through ``starlayer.shacl`` (the native SHACL 1.2 engine): a tree may embed genuine RDF 1.2 content (a triple term).

    Args:
        tree_graph: The tree graph (a ``StarLayerGraph``) to validate.

    Returns:
        The ``ValidationReport`` ``starlayer.shacl.validate()`` gives, with the engine and ordering findings added; it is not
        iterable, so read ``conforms``, ``report_text`` and the rest by name.
    """
    from .sqe._memtree import as_engine_graph
    from .sqe.shapes import validate_sqe_tree
    from .srl import SRL, validate_srl_tree

    graph, _ = as_engine_graph(tree_graph)
    sqe_roots, srl_roots = _roots(graph)
    if sqe_roots and srl_roots:
        return _merge_reports(validate_sqe_tree(graph), validate_srl_tree(graph))
    if srl_roots:
        return validate_srl_tree(graph)
    if not sqe_roots:  # no root of either kind: a stray srl: node is read as a rule set, anything else as sqe:
        rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        if any(str(o.value).startswith(SRL.RuleSet.value.rsplit("#", 1)[0]) for o in graph.objects(None, rdf_type) if isinstance(o, ox.NamedNode)):
            return validate_srl_tree(graph)
    return validate_sqe_tree(graph)


def _merge_reports(first: ValidationReport, second: ValidationReport) -> ValidationReport:
    """One report holding the results of ``first`` and ``second``: it conforms when both do, its graph is ``first``'s with the
    results of ``second`` added, its text lists both."""
    from starlayer.shacl.engine.terms import SH
    from starlayer.shacl.results import ValidationReport

    graph, other = first.report_graph, second.report_graph
    top = next(iter(graph.subjects(SH.conforms, None)))
    other_top = next(iter(other.subjects(SH.conforms, None)))
    conforms = first.conforms and second.conforms
    graph.remove((top, SH.conforms, None))
    graph.add((top, SH.conforms, ox.Literal("true" if conforms else "false", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))))
    graph.extend([t for t in other.triples((None, None, None)) if t[0] != other_top])
    graph.extend([(top, SH.result, result) for result in other.objects(other_top, SH.result)])

    def blocks(report: ValidationReport) -> list[str]:
        lines = report.report_text.split("\n")
        return lines[3:] if len(lines) > 3 and lines[2].startswith("Results (") else []

    total = len(list(graph.objects(top, SH.result)))
    text = "\n".join(["Validation Report", f"Conforms: {conforms}", f"Results ({total}):", *blocks(first), *blocks(second)])
    return ValidationReport(conforms, graph, text, diagnostics=first.diagnostics)
