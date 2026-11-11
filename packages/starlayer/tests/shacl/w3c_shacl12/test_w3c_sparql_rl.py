"""The vendored W3C SPARQL-RL (SRL) suite, ``tests/sparql-rl/`` of the SHACL 1.2 test suite, against StarLayer's SRL.

Each directory has a ``manifest.ttl`` with ``srt:`` test types (read with pyoxigraph; nothing is hand-listed):

* ``RulesPositiveSyntaxTest`` / ``RulesNegativeSyntaxTest``: the text parses / does not parse. The suite files "variables in a DATA
  block" under syntax; StarLayer reports it as a well-formedness violation, so a negative test passes when the public gate
  (``parse_ruleset``, which includes the well-formedness checks) rejects the text. A positive test uses the grammar-level
  ``parse_srl``, since a syntax test is "regardless of well-formedness and stratification".
* ``RulesPositiveWellFormednessTest`` / ``RulesNegativeWellFormednessTest``: ``parse_ruleset`` accepts / rejects.
* ``RulesPositiveStratificationTest`` / ``RulesNegativeStratificationTest``: ``RuleSet.plan()`` succeeds / raises
  ``StratificationError``.
* ``RulesEvalTest``: ``RuleSet.infer(data)`` is isomorphic with the expected graph (the triples the rule set adds).

Known failures are strict xfails with a reason (``KNOWN``): the entry fails loudly when the gap closes.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pyoxigraph as ox
import pytest
from starlayer.graph.compare import isomorphic
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql.parse_srl import parse_srl
from starlayer.sparql.srl import SRLError, parse_ruleset
from starlayer.sparql.srl_eval import StratificationError

ROOT = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite" / "tests" / "sparql-rl"

MF = "http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#"
SRT = "http://www.w3.org/ns/sparql-rl-tests#"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

_GROUP = "GROUP in a rule body is not implemented (SPARQL 1.2 Rules WD 2026-11-09; docs/working/spec-delta-2026-11-11.md, phase 4)"
KNOWN: dict[str, str] = {
    **{f"syntax/syntax-rule-elements-group-{n:02d}.srl": _GROUP for n in range(1, 17)},
    "eval2/Eval-assign-01": "the manifest names eval-assign-01.srl and its results file, and neither is in the upstream suite",
}


def _entries() -> list[tuple[str, str, str, Path | None, Path | None, Path | None]]:
    """(id, kind, name, ruleset, data, result) for every ``srt:Rules*Test`` of every manifest."""
    out = []
    for manifest in sorted(ROOT.glob("*/manifest.ttl")):
        triples = list(ox.parse(path=str(manifest), format=ox.RdfFormat.TURTLE, base_iri=manifest.as_uri()))
        by_subject: dict = {}
        for t in triples:
            by_subject.setdefault(t.subject, []).append(t)

        def objects(subject, predicate, by_subject=by_subject):
            return [t.object for t in by_subject.get(subject, []) if t.predicate.value == predicate]

        def path_of(node):
            return Path(node.value.removeprefix("file://")) if isinstance(node, ox.NamedNode) else None

        for subject in by_subject:
            kinds = [o.value.removeprefix(SRT) for o in objects(subject, RDF_TYPE.value) if o.value.startswith(SRT)]
            kind = next((k for k in kinds if k.startswith("Rules") and k.endswith("Test")), None)
            if kind is None:
                continue
            name_node = objects(subject, MF + "name")
            name = name_node[0].value if name_node else str(subject)
            action = objects(subject, MF + "action")[0]
            if isinstance(action, ox.BlankNode):
                ruleset = path_of(objects(action, SRT + "ruleset")[0])
                data_nodes = objects(action, SRT + "data")
                data = path_of(data_nodes[0]) if data_nodes else None
            else:
                ruleset, data = path_of(action), None
            result_nodes = objects(subject, MF + "result")
            result = path_of(result_nodes[0]) if result_nodes else None
            # the id: directory/file for the one-file tests, directory/name for the evaluation tests
            ident = f"{manifest.parent.name}/{ruleset.name if kind != 'RulesEvalTest' else name}"
            out.append((ident, kind, name, ruleset, data, result))
    return out


_ENTRIES = _entries()


def pytest_generate_tests(metafunc):
    if "entry" not in metafunc.fixturenames:
        return
    params = []
    for entry in _ENTRIES:
        marks = [pytest.mark.xfail(strict=True, reason=KNOWN[entry[0]])] if entry[0] in KNOWN else []
        params.append(pytest.param(entry, id=entry[0], marks=marks))
    metafunc.parametrize("entry", params or [pytest.param(None, marks=pytest.mark.skip(reason="the SPARQL-RL suite is not vendored"))])


def _graph(path: Path | None) -> StarLayerGraph:
    g = StarLayerGraph()
    if path is not None:
        g.parse(data=path.read_text(), format="turtle", publicID=path.resolve().as_uri())
    return g


def test_sparql_rl(entry) -> None:
    _id, kind, _name, ruleset, data, result = entry
    text = ruleset.read_text()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the fidelity warning: these are not lexical-form tests
        if kind == "RulesPositiveSyntaxTest":
            parse_srl(text)
        elif kind == "RulesNegativeSyntaxTest":
            with pytest.raises(SRLError):
                parse_ruleset(text, validate=False)
        elif kind == "RulesPositiveWellFormednessTest":
            parse_ruleset(text, validate=False)
        elif kind == "RulesNegativeWellFormednessTest":
            with pytest.raises(SRLError):
                parse_ruleset(text, validate=False)
        elif kind == "RulesPositiveStratificationTest":
            parse_ruleset(text, validate=False).plan()
        elif kind == "RulesNegativeStratificationTest":
            with pytest.raises(StratificationError):
                parse_ruleset(text, validate=False).plan()
        elif kind == "RulesEvalTest":
            inferred = parse_ruleset(text, validate=False).infer(_graph(data))
            assert isomorphic(inferred, _graph(result)), "the inferred triples differ from the expected graph"
        else:  # pragma: no cover - a new test type upstream
            pytest.fail(f"unknown SPARQL-RL test type {kind}")
