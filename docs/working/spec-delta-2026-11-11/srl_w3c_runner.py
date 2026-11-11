"""Throwaway: run the new W3C SPARQL-RL suite against StarLayer's SRL (prototype of the harness the plan proposes)."""
import collections
import json
import sys
import warnings
from pathlib import Path

import rdflib
import pyoxigraph as ox

warnings.simplefilter("ignore")
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql.parse_srl import parse_srl
from starlayer.sparql.srl import SRLError, parse_ruleset
from starlayer.sparql.srl_eval import StratificationError

ROOT = Path(sys.argv[1])
MF = rdflib.Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
SRT = "http://www.w3.org/ns/sparql-rl-tests#"


def path_of(iri):
    return Path(str(iri).replace("file://", ""))


def load_ttl(p):
    g = StarLayerGraph()
    g.parse(data=Path(p).read_text(), format="turtle", publicID=Path(p).resolve().as_uri())
    return g


def triples(g):
    return {tuple(t) for t in g.triples((None, None, None))}


def canon(ts):
    """Triples with blank nodes mapped to a placeholder (the tests' blank nodes are existential)."""
    out = set()
    for s, p, o in ts:
        out.add(tuple("_:b" if isinstance(x, ox.BlankNode) else str(x) for x in (s, p, o)))
    return out


results = collections.defaultdict(lambda: collections.Counter())
failures = []
for man in sorted(ROOT.glob("*/manifest.ttl")):
    mg = rdflib.Graph()
    mg.parse(man)
    for s in mg.subjects(rdflib.RDF.type, None):
        kinds = [str(t).split("#")[-1] for t in mg.objects(s, rdflib.RDF.type)]
        kind = next((k for k in kinds if k.startswith("Rules")), None)
        if kind is None:
            continue
        name = str(next(mg.objects(s, MF.name), s))
        action = next(mg.objects(s, MF.action))
        cat = man.parent.name
        try:
            if isinstance(action, rdflib.BNode):
                ruleset = path_of(next(mg.objects(action, rdflib.URIRef(SRT + "ruleset"))))
                data = next(mg.objects(action, rdflib.URIRef(SRT + "data")), None)
            else:
                ruleset, data = path_of(action), None
            text = ruleset.read_text()
            outcome, detail = "pass", ""
            if kind == "RulesPositiveSyntaxTest":
                try:
                    parse_srl(text)
                except Exception as e:  # noqa: BLE001
                    outcome, detail = "FAIL", f"rejected: {type(e).__name__}: {str(e)[:120]}"
            elif kind == "RulesNegativeSyntaxTest":
                try:
                    parse_srl(text)
                    outcome, detail = "FAIL", "accepted by the syntax parser"
                except Exception:  # noqa: BLE001
                    pass
            elif kind == "RulesPositiveWellFormednessTest":
                try:
                    parse_ruleset(text, validate=False)
                except Exception as e:  # noqa: BLE001
                    outcome, detail = "FAIL", f"rejected: {type(e).__name__}: {str(e)[:120]}"
            elif kind == "RulesNegativeWellFormednessTest":
                try:
                    parse_ruleset(text, validate=False)
                    outcome, detail = "FAIL", "accepted (should violate well-formedness)"
                except SRLError:
                    pass
            elif kind == "RulesPositiveStratificationTest":
                try:
                    parse_ruleset(text, validate=False).plan()
                except Exception as e:  # noqa: BLE001
                    outcome, detail = "FAIL", f"rejected: {type(e).__name__}: {str(e)[:120]}"
            elif kind == "RulesNegativeStratificationTest":
                try:
                    parse_ruleset(text, validate=False).plan()
                    outcome, detail = "FAIL", "stratifiable (should not be)"
                except StratificationError:
                    pass
                except SRLError as e:
                    outcome, detail = "FAIL", f"other error: {type(e).__name__}: {str(e)[:100]}"
            elif kind == "RulesEvalTest":
                expected_path = path_of(next(mg.objects(s, MF.result)))
                dg = load_ttl(path_of(data)) if data is not None else StarLayerGraph()
                rs = parse_ruleset(text, validate=False)
                inferred = rs.infer(dg)
                got_new = canon(triples(inferred))
                got_all = canon(triples(inferred) | triples(dg))
                exp = canon(triples(load_ttl(expected_path)))
                if exp == got_new:
                    outcome = "pass"
                elif exp == got_all:
                    outcome = "pass(closure)"
                else:
                    outcome, detail = "FAIL", f"expected {len(exp)}; inferred {len(got_new)}; missing {sorted(exp - got_all)[:2]}; extra {sorted(got_new - exp)[:2]}"
        except Exception as e:  # noqa: BLE001
            outcome, detail = "ERROR", f"{type(e).__name__}: {str(e)[:140]}"
        results[(cat, kind)][outcome] += 1
        if outcome in ("FAIL", "ERROR"):
            failures.append((cat, kind, name, outcome, detail))

for k, v in sorted(results.items()):
    print(k, dict(v))
print("---- failures:", len(failures))
for f in failures:
    print(" ", *f)
json.dump(failures, open(sys.argv[2], "w"), indent=1)
