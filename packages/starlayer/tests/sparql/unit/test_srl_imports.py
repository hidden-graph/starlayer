"""``IMPORTS`` in SRL (§3.7, §4.5, Appendix B): resolved only when the caller supplies
a loader; each document is read once; rules and DATA are merged; failures are errors."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph as Graph
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
    return ox.NamedNode(EX + local)


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
    assert len(subjects) == 2 and all(isinstance(s, ox.BlankNode) for s in subjects)
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
    assert heads == [ox.NamedNode(EX + name) for name in ("own", "one", "two")]


class TestStratificationAtParseTime:
    """``parse_ruleset()`` checks the rules in its text have an evaluation order; with ``IMPORTS`` that is only the rules in the text,
    and a warning says so. ``resolve_imports()`` checks the combined rule set."""

    P = "PREFIX ex: <http://example.org/>\n"
    SELF_NOT = "RULE { ?x ex:a ?y } WHERE { ?x ex:b ?y . NOT { ?x ex:a ?y } }"

    def test_a_rule_set_that_cannot_be_ordered_is_rejected_at_parse(self):
        from starlayer.sparql.srl_eval import StratificationError

        with pytest.raises(StratificationError):
            parse_ruleset(self.P + self.SELF_NOT)

    def test_validate_false_skips_the_check(self):
        assert parse_ruleset(self.P + self.SELF_NOT, validate=False).rules

    def test_the_rules_in_the_text_are_checked_when_there_are_imports(self):
        from starlayer.sparql.srl_eval import StratificationError

        with pytest.raises(StratificationError, match="not yet resolved: <http://example.org/lib>"):
            parse_ruleset("IMPORTS <http://example.org/lib>\n" + self.P + self.SELF_NOT)

    def test_a_rule_set_with_imports_that_passes_warns_and_says_it_is_not_resolved(self):
        from starlayer.sparql.srl import SRLUnresolvedImportsWarning

        with pytest.warns(SRLUnresolvedImportsWarning, match="http://example.org/lib"):
            ruleset = parse_ruleset("IMPORTS <http://example.org/lib>\n" + self.P + "RULE { ?x ex:a ?y } WHERE { ?x ex:b ?y }")
        assert not ruleset.is_resolved

    def test_no_warning_without_imports(self, recwarn):
        ruleset = parse_ruleset(self.P + "RULE { ?x ex:a ?y } WHERE { ?x ex:b ?y }")
        assert ruleset.is_resolved
        assert not [w for w in recwarn if "IMPORTS" in str(w.message)]

    def test_an_import_that_adds_the_cycle_is_caught_when_the_imports_are_resolved(self):
        from starlayer.sparql.srl import SRLUnresolvedImportsWarning, resolve_imports
        from starlayer.sparql.srl_eval import StratificationError

        library = self.P + "RULE { ?x ex:b ?y } WHERE { ?x ex:c ?y . NOT { ?x ex:a ?y } }"
        with pytest.warns(SRLUnresolvedImportsWarning):
            ruleset = parse_ruleset("IMPORTS <http://example.org/lib>\n" + self.P + "RULE { ?x ex:a ?y } WHERE { ?x ex:b ?y }")
        with pytest.raises(StratificationError):
            resolve_imports(ruleset, lambda iri: library)


class TestParseWithAnImportsLoader:
    P = "PREFIX ex: <http://example.org/>\n"
    LIB = P + "RULE { ?x ex:e ?v } WHERE { ?x ex:h ?v }"
    TEXT = "IMPORTS <http://example.org/lib>\n" + P + "RULE { ?x ex:s ?v } WHERE { ?x ex:e ?v }"

    def test_it_returns_the_resolved_rule_set_without_a_warning(self, recwarn):
        ruleset = parse_ruleset(self.TEXT, imports_loader=lambda iri: self.LIB)
        assert ruleset.is_resolved
        assert len(ruleset.rules) == 2
        assert not [w for w in recwarn if "IMPORTS" in str(w.message)]

    def test_it_runs_without_a_loader_afterwards(self):
        base = Graph()
        base.parse(data="@prefix ex: <http://example.org/> . ex:a ex:h ex:b .", format="turtle")
        ruleset = parse_ruleset(self.TEXT, imports_loader=lambda iri: self.LIB)
        assert len(ruleset.infer(base)) == 2

    def test_the_combined_rule_set_is_checked(self):
        from starlayer.sparql.srl_eval import StratificationError

        library = self.P + "RULE { ?x ex:e ?y } WHERE { ?x ex:h ?y . NOT { ?x ex:s ?y } }"
        with pytest.raises(StratificationError):
            parse_ruleset(self.TEXT, imports_loader=lambda iri: library)
        assert parse_ruleset(self.TEXT, imports_loader=lambda iri: library, validate=False).is_resolved

    def test_the_loader_is_not_called_when_there_are_no_imports(self):
        def loader(iri):
            raise AssertionError("no import to read")

        assert parse_ruleset(self.LIB, imports_loader=loader).is_resolved

    def test_a_loader_that_fails_is_an_import_error(self):
        def loader(iri):
            raise KeyError(iri)

        with pytest.raises(SRLImportError, match="not found"):
            parse_ruleset(self.TEXT, imports_loader=loader)
