"""Classify the failures of the rdf-1.2 default flip (docs/working/b1-classification.md).

Input: a JUnit XML from `pytest tests --deferred --junitxml=run1.xml` run with scripts/b1_flip_experiment.py applied.
Output: per-file / per-class counts and the Markdown table used in the report.
Usage: python scripts/b1_classify.py run1.xml
Classes: D delete, M migrate, B real bug (BUG subtag), X environmental or flaky (here: a strict xfail that passes only because
the flipped old class loaded the data).
"""

import collections
import re
import sys
import xml.etree.ElementTree as ET

# (file substring, test-name regex or None, message regex or None) -> (class, tag); first match wins
RULES = [
    (None, None, r"^\[XPASS\(strict\)\]", ("X", "xpass")),
    (None, None, r"cannot pickle", ("B", "pickle")),
    ("test_contracts_hunt3", r"replace|regex", None, ("B", "xpath-regex")),
    ("test_sparql_builtins_hunt3", None, None, ("B", "boolean-order")),
    ("test_property_paths_hunt2", None, None, ("B", "paths")),
    ("test_update_hunt3", r"missing_graph.*(COPY|ADD)", None, ("B", "copy-add")),
    ("test_starlayer_graph", r"TestFromRdflib", None, ("B", "api-from_rdflib")),
    ("test_prefixes", r"reduced_copy", None, ("B", "api-reduce_prefixes")),
    ("test_dataset", r"StoreLifecycle|Chaining|RawCacheInvalidation", None, ("D", "rdflib-store")),
    ("test_starlayer_graph", r"StoreLifecycle|Chaining", None, ("D", "rdflib-store")),
    ("test_cross_backend_parity", None, None, ("D", "backend-parity")),
    ("test_oxigraph_store_rdf12", None, None, ("D", "backend-parity")),
    ("graph/oxgraph/test_conformance", None, None, ("D", "old-vs-new comparator")),
    ("test_helpers_conformance", None, None, ("D", "old-vs-new comparator")),
    ("unit/test_conformance", None, None, ("D", "hand-parser warnings (O3)")),
    ("test_query_prepare_cache", None, None, ("D", "prepared-query cache")),
    ("test_rdf12_formats", None, None, ("D", "hand writers (O3)")),
    ("test_rdfc_native", None, None, ("D", "old-vs-new comparator")),
    ("test_turtle12_serializer", None, None, ("D", "hand writer")),
    ("test_turtle_parser", None, None, ("D", "hand parser")),
    ("test_trig_graph_blocks", None, None, ("D", "hand parser")),
    ("test_parser_fixes", None, None, ("D", "hand parser")),
    ("test_interop", r"TestAgainstTheOldEncoding", None, ("D", "tt: encoding")),
    ("test_lower_rdf11", None, None, ("D", "lowering")),
    ("test_phase3_rdf12", None, None, ("D", "lowering/algebra round trip")),
    ("test_entailment", None, None, ("M", "entailment on StarLayerGraph.query")),
    ("test_star_query", r"Entailment", None, ("M", "entailment on StarLayerGraph.query")),
    ("test_parse_fidelity", None, None, ("M", "lexical forms (O1)")),
    ("test_proposition_form_encoding", None, None, ("M", "basic-encoding input (O4)")),
    ("test_shape_derivation", None, None, ("M", "derive_shape on StarLayerGraph")),
    ("test_sparql12_grammar_hunt2", None, None, ("M", "error type (O5)")),
    ("test_update_hunt3", None, None, ("M", "error type (O5) / prepared query")),
    ("test_dirlang_string_functions", None, None, ("M", "prepared query object -> text")),
    ("test_star_query", None, None, ("M", "prepared query object -> text")),
    ("test_used_graphs_and_configuration", None, None, ("M", "graph identifier")),
    ("test_report_text_provenance", None, None, ("M", "graph identifier")),
    (None, None, r"expected (string or bytes|one of|IRI|OPTIONAL)|Prefix not found|n3|IRI parsing", ("M", "old-wrapper artefact: identifier scoping, tuple wildcards, prefixes")),
    (None, None, None, ("M", "old-class API: row access, identifiers, isomorphic, str of triple terms, bnode labels")),
]


def classify(file, name, msg):
    for f, n, m, cls in RULES:
        if f and f not in file:
            continue
        if n and not re.search(n, file):  # `file` is the module path plus class plus test name
            continue
        if m and not re.search(m, msg):
            continue
        return cls
    raise AssertionError


def main(path):
    rows = []
    for tc in ET.parse(path).iter("testcase"):
        for k in ("failure", "error"):
            e = tc.find(k)
            if e is not None:
                cn = tc.get("classname").replace(".", "/")
                rows.append((cn, tc.get("name"), (e.get("message") or "").replace("\n", " ")))
    per_file = collections.defaultdict(collections.Counter)
    per_class = collections.Counter()
    per_tag = collections.Counter()
    for file, name, msg in rows:
        cls, tag = classify(file + "::" + name, name, msg)
        base = re.sub(r"^packages/starlayer/", "", file)
        base = re.sub(r"/Test\w+$", "", base)
        per_file[base][cls + ":" + tag] += 1
        per_class[cls] += 1
        per_tag[(cls, tag)] += 1
    print(len(rows), dict(per_class))
    for (c, t), n in sorted(per_tag.items()):
        print(f"{c} {t}: {n}")
    for f in sorted(per_file):
        print(f"| `{f}.py` | {sum(per_file[f].values())} | " + ", ".join(f"{k} x{v}" for k, v in sorted(per_file[f].items())) + " |")


if __name__ == "__main__":
    main(sys.argv[1])
