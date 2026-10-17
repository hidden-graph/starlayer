"""``IMPORTS`` in SRL (§3.7, §4.5, Appendix B): resolved only when the caller supplies
a loader; each document is read once; rules and DATA are merged; failures are errors."""

from __future__ import annotations

import pytest
from rdflib import BNode, Graph, URIRef
from starlayer.sparql import srl
from starlayer.sparql.srl import SRLImportError, parse_ruleset, resolve_imports
from starlayer.sparql.srl_eval import SRLImportsNotSupportedError

EX = "http://example.org/"
P = f"PREFIX ex: <{EX}>\n"
BASE_LIB = EX + "lib/base.srl"
EXPOSURE_LIB = EX + "lib/exposure.srl"

DOCS = {
    BASE_LIB: P + "RULE { ?x ex:exposedTo ?v } WHERE { ?x ex:hasVulnerability ?v }",
    EXPOSURE_LIB: P
    + f"IMPORTS <{BASE_LIB}>\n"
    + "RULE { ?x ex:exposedTo ?v } WHERE { ?x ex:dependsOn ?y . ?y ex:exposedTo ?v }",
}


def _u(local):
    return URIRef(EX + local)


class _Loader:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def __call__(self, iri):
        self.calls.append(iri)
        return self.docs[iri]


def _graph():
    g = Graph()
    g.parse(
        data=f"@prefix ex: <{EX}> . ex:a ex:dependsOn ex:b . ex:b ex:hasVulnerability ex:v1 .",
        format="turtle",
    )
    return g


ROOT = (
    P
    + f"IMPORTS <{EXPOSURE_LIB}>\nRULE {{ ?x ex:status ex:critical }} WHERE {{ ?x ex:exposedTo ?v }}"
)


def test_a_rule_set_with_imports_is_still_rejected_without_a_loader():
    with pytest.raises(SRLImportsNotSupportedError):
        parse_ruleset(ROOT).infer(_graph())


def test_imported_rules_are_merged_and_the_result_has_no_imports_left():
    root = parse_ruleset(ROOT)
    resolved = resolve_imports(root, _Loader(DOCS))
    assert resolved.imports == [] and len(resolved.rules) == 3
    assert root.imports and len(root.rules) == 1  # the original is not changed


def test_infer_with_a_loader_uses_the_imported_rules():
    inferred = parse_ruleset(ROOT).infer(_graph(), imports_loader=_Loader(DOCS))
    assert {tuple(t) for t in inferred} == {
        (_u("a"), _u("exposedTo"), _u("v1")),
        (_u("b"), _u("exposedTo"), _u("v1")),
        (_u("a"), _u("status"), _u("critical")),
        (_u("b"), _u("status"), _u("critical")),
    }


def test_query_and_plan_accept_a_loader_too():
    root = parse_ruleset(ROOT)
    goal = srl.TriplePattern(
        subject=_u("a"), predicate=_u("status"), object=_u("critical")
    )
    assert root.query(_graph(), goal, imports_loader=_Loader(DOCS)) == [{}]
    assert len(root.plan(imports_loader=_Loader(DOCS)).strata[0].general) >= 2


def test_a_document_imported_twice_is_read_only_once():
    loader = _Loader(DOCS)
    root = parse_ruleset(P + f"IMPORTS <{EXPOSURE_LIB}>\nIMPORTS <{BASE_LIB}>\n")
    resolve_imports(root, loader)
    assert sorted(loader.calls) == sorted([EXPOSURE_LIB, BASE_LIB])


def test_a_cycle_among_imports_does_not_loop():
    docs = {
        EX + "a.srl": P
        + f"IMPORTS <{EX}b.srl>\nRULE {{ ?x ex:a ?y }} WHERE {{ ?x ex:p ?y }}",
        EX + "b.srl": P
        + f"IMPORTS <{EX}a.srl>\nRULE {{ ?x ex:b ?y }} WHERE {{ ?x ex:p ?y }}",
    }
    loader = _Loader(docs)
    resolved = resolve_imports(parse_ruleset(P + f"IMPORTS <{EX}a.srl>"), loader)
    assert len(resolved.rules) == 2 and sorted(loader.calls) == [
        EX + "a.srl",
        EX + "b.srl",
    ]


def test_the_location_of_the_root_counts_as_already_imported():
    loader = _Loader({})
    root = parse_ruleset(
        P + f"IMPORTS <{EX}self.srl>\nRULE {{ ?x ex:a ?y }} WHERE {{ ?x ex:p ?y }}"
    )
    resolved = resolve_imports(root, loader, location=EX + "self.srl")
    assert loader.calls == [] and len(resolved.rules) == 1


def test_a_loader_may_return_an_already_parsed_rule_set():
    parsed = {BASE_LIB: parse_ruleset(DOCS[BASE_LIB])}
    resolved = resolve_imports(
        parse_ruleset(P + f"IMPORTS <{BASE_LIB}>"), parsed.__getitem__
    )
    assert len(resolved.rules) == 1


def test_a_relative_import_is_resolved_against_the_base_of_the_rule_set():
    loader = _Loader({EX + "lib/base.srl": DOCS[BASE_LIB]})
    root = parse_ruleset(f"BASE <{EX}lib/>\nIMPORTS <base.srl>\n")
    resolve_imports(root, loader)
    assert loader.calls == [EX + "lib/base.srl"]


def test_a_loader_that_fails_is_reported_with_the_import_iri():
    def broken(iri):
        raise OSError("no such file")

    with pytest.raises(SRLImportError, match="lib/base.srl.*no such file"):
        resolve_imports(parse_ruleset(P + f"IMPORTS <{BASE_LIB}>"), broken)


def test_an_import_that_is_not_a_valid_rule_set_is_an_error():
    loader = _Loader({BASE_LIB: "RULE { this is not srl"})
    with pytest.raises(SRLImportError, match="not a valid rule set"):
        resolve_imports(parse_ruleset(P + f"IMPORTS <{BASE_LIB}>"), loader)


def test_an_import_that_fails_well_formedness_is_an_error():
    loader = _Loader({BASE_LIB: P + "RULE { ?x ex:r ?unbound } WHERE { ?x ex:p ?y }"})
    with pytest.raises(SRLImportError, match="unbound_head_variable"):
        resolve_imports(parse_ruleset(P + f"IMPORTS <{BASE_LIB}>"), loader)


def test_data_is_merged_and_blank_nodes_in_different_documents_stay_distinct():
    lib = P + "DATA { _:x ex:p 1 . }"
    root = parse_ruleset(P + f"IMPORTS <{BASE_LIB}>\nDATA {{ _:x ex:q 2 . }}")
    resolved = resolve_imports(root, _Loader({BASE_LIB: lib}))
    subjects = [t.subject for block in resolved.data for t in block.triples]
    assert len(subjects) == 2 and all(isinstance(s, BNode) for s in subjects)
    assert (
        subjects[0] != subjects[1]
    )  # the same label `_:x` in two documents is two nodes


def test_the_importing_rule_set_comes_first_then_its_imports_in_order():
    docs = {
        EX + "1.srl": P + "RULE { ?x ex:one ?y } WHERE { ?x ex:p ?y }",
        EX + "2.srl": P + "RULE { ?x ex:two ?y } WHERE { ?x ex:p ?y }",
    }
    root = parse_ruleset(
        P
        + f"IMPORTS <{EX}1.srl>\nIMPORTS <{EX}2.srl>\nRULE {{ ?x ex:own ?y }} WHERE {{ ?x ex:p ?y }}"
    )
    heads = [r.head[0].predicate for r in resolve_imports(root, _Loader(docs)).rules]
    assert heads == [_u("own"), _u("one"), _u("two")]
