"""Blank-node-identity-independent comparison of sh:ValidationReport graphs.

Neither starshacl's actual report nor the W3C suite's expected report
promises stable blank-node identifiers (for sh:result nodes, or for
structured values like SHACL paths or RDF-1.2 triple terms nested under
sh:value/sh:resultPath) - comparing by raw term equality would spuriously
fail on every blank node. term_key() instead fingerprints a blank node by its
own outgoing-triple structure, recursively, so two differently-labeled but
structurally identical blank-node values compare equal.
"""

from __future__ import annotations

from collections import Counter

from rdflib import BNode, Graph, Literal
from rdflib.namespace import RDF
from rdflib.term import Node

from .namespaces import SH

TermKey = tuple


def term_key(graph: Graph, term: Node | None) -> TermKey | None:
    if term is None:
        return None
    if isinstance(term, BNode):
        children = tuple(sorted((str(p), term_key(graph, o)) for p, o in graph.predicate_objects(term)))
        return ("BNODE", children)
    if isinstance(term, Literal):
        return ("LITERAL", str(term), str(term.datatype) if term.datatype else None, term.language)
    return ("URI", str(term))


def find_report_node(graph: Graph) -> Node:
    """Find the real, top-level sh:ValidationReport node.

    Usually there's exactly one. But for a self-referential W3C-suite
    fixture (sht:dataGraph <> loading the whole document, including its own
    mf:result expected-result block - itself a well-formed
    sh:ValidationReport structure) a *real* violation's sh:value/sh:focusNode
    can coincidentally equal that embedded block, and pySHACL's own report
    construction copies its triples into the actual report graph as part of
    representing that value - producing a second, incidental
    sh:ValidationReport-typed node. Disambiguated the same way
    starshacl.validator._find_genuine_report_node does: the real
    report is always a fresh node nothing else in the graph points to;
    an incidental one was pulled in specifically because something else
    references it.
    """
    nodes = list(graph.subjects(RDF.type, SH.ValidationReport))
    if len(nodes) == 1:
        return nodes[0]
    if len(nodes) > 1:
        roots = [n for n in nodes if next(graph.subjects(None, n), None) is None]
        if len(roots) == 1:
            return roots[0]
    raise AssertionError(f"expected exactly one sh:ValidationReport node, found {len(nodes)}: {nodes}")


def conforms_of(graph: Graph, report_node: Node) -> bool:
    values = list(graph.objects(report_node, SH.conforms))
    if len(values) != 1:
        raise AssertionError(f"expected exactly one sh:conforms value, found {len(values)}: {values}")
    return bool(values[0].toPython())


def result_multiset(graph: Graph, report_node: Node) -> Counter:
    """Fingerprint each sh:result as (focusNode, resultPath, sourceConstraintComponent, value, severity).

    sh:sourceShape is deliberately excluded - see
    docs/w3c-shacl12-test-suite-plan.md's "Open questions" section: neither
    implementation's sourceShape blank-node identity is guaranteed to match,
    and unlike the other fields a blank-node sourceShape's own structure
    (the whole shape definition) isn't a meaningful fingerprint to compare -
    two different shapes can be structurally different yet both correctly
    produce a given violation.
    """
    counter: Counter = Counter()
    for result_node in graph.objects(report_node, SH.result):
        focus = next(graph.objects(result_node, SH.focusNode), None)
        path = next(graph.objects(result_node, SH.resultPath), None)
        component = next(graph.objects(result_node, SH.sourceConstraintComponent), None)
        value = next(graph.objects(result_node, SH.value), None)
        severity = next(graph.objects(result_node, SH.resultSeverity), None)
        key = (
            term_key(graph, focus),
            term_key(graph, path),
            term_key(graph, component),
            term_key(graph, value),
            term_key(graph, severity),
        )
        counter[key] += 1
    return counter
