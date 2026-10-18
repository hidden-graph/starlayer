"""Every W3C SPARQL 1.2 positive-syntax and query-evaluation fixture, run
through the sqe parser: text -> sqe tree -> text -> sqe tree -> decoded query
(and, for evaluation fixtures, executed and compared with the suite's own
expected results).

Opt-in (``pytest --sqe-coverage``). Fixtures sqe cannot express yet are listed
in ``sqe_known_gaps.txt`` and run as strict xfails, so closing a gap shows up
as an unexpected pass. Regenerate the list (after a change that fixes or
breaks fixtures) with::

    python tests/sparql/sqe_coverage/test_w3c_through_sqe.py --regenerate
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib.compare import to_isomorphic
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.query.version_directive import strip_version_directive
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_query, sqe_tree_to_text
from tests.sparql.w3c_sparql12.harness import (
    bindings_match,
    load_index,
    parse_srj,
    skolemize_graph,
)
from tests.sparql.w3c_sparql12.test_w3c_sparql12 import _data_format, _new_graph

pytestmark = pytest.mark.sqe_coverage

_GAPS_FILE = Path(__file__).with_name("sqe_known_gaps.txt")
_ENTRIES = [
    e for e in load_index() if e.test_type in ("PositiveSyntaxTest", "QueryEvaluationTest")
]


def _key(entry) -> str:
    return entry.category + "/" + entry.test_iri.rsplit("#", 1)[-1]


def _known_gaps() -> set[str]:
    if not _GAPS_FILE.exists():
        return set()
    return {ln.strip() for ln in _GAPS_FILE.read_text().splitlines() if ln.strip() and not ln.startswith("#")}


def run_entry(entry) -> None:
    text, _ = strip_version_directive(entry.read(entry.query_file))
    graph, root = sqe_parse_to_tree(text)
    regenerated = sqe_tree_to_text(graph, root)
    graph2, root2 = sqe_parse_to_tree(regenerated)
    sqe_tree_to_query(graph2, root2)
    if entry.test_type != "QueryEvaluationTest":
        return

    data = _new_graph(entry)
    if entry.data_file:
        data.parse(data=entry.read(entry.data_file), format=_data_format(entry))
    result_text = entry.read(entry.result_file)
    if entry.result_file.endswith(".ttl"):
        expected = StarLayerGraph()
        expected.parse(data=result_text, format="turtle12")
        actual = data.query(regenerated).graph
        assert to_isomorphic(skolemize_graph(actual)) == to_isomorphic(skolemize_graph(expected))
    elif entry.result_file.endswith(".srj"):
        answer = json.loads(result_text)
        if "boolean" in answer:
            assert data.query(regenerated).askAnswer == answer["boolean"]
        else:
            rows = [{k: v for k, v in dict(r).items() if v is not None} for r in data.query(regenerated).bindings]
            assert bindings_match(rows, parse_srj(result_text))


def _param(entry):
    marks = []
    if _key(entry) in _known_gaps():
        marks.append(pytest.mark.xfail(strict=True, reason="sqe cannot express this yet (sqe_known_gaps.txt)"))
    return pytest.param(entry, marks=marks, id=_key(entry))


@pytest.mark.skipif(not _ENTRIES, reason="W3C SPARQL 1.2 test data not fetched")
@pytest.mark.parametrize("entry", [_param(e) for e in _ENTRIES])
def test_w3c_fixture_through_sqe(entry):
    run_entry(entry)


if __name__ == "__main__":
    import sys

    if "--regenerate" not in sys.argv:
        raise SystemExit(__doc__)
    failing = []
    for e in _ENTRIES:
        try:
            run_entry(e)
        except Exception:  # noqa: BLE001 - recording which fixtures fail, whatever the reason
            failing.append(_key(e))
    _GAPS_FILE.write_text(
        "# W3C fixtures sqe cannot yet round-trip (strict xfail). Regenerate: see test_w3c_through_sqe.py\n"
        + "\n".join(sorted(failing))
        + "\n"
    )
    print(f"{len(failing)} of {len(_ENTRIES)} fixtures are known gaps")
