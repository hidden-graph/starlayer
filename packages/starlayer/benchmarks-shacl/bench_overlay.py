"""Where does the time go in the inferred-triples overlay, and is an Oxigraph-backed overlay faster?

Generated data (``bench_engine_vs_old.make_data``) plus an RDFS hierarchy (subClassOf, subPropertyOf, domain), and a rules
shapes graph (shape-level SPARQLRule, two global copying SPARQLRules, a TripleRule). Stages timed, best of ``--reps``:

* ``entailed_view`` (rdfs): split into combined copy / owlrl closure (``StarLayerGraph.infer``) / overlay fill;
* ``apply_rules`` over the entailed view;
* ``validate`` on the finished overlay (``rules=False``), and the whole ``validate(..., inference=ENTAILMENT.RDFS, rules=True)``;
* a lookup micro-benchmark: triples/objects/subjects/__contains__ on the finished overlay.

    PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_overlay.py --sizes 5000,20000 --overlay python
    PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_overlay.py --sizes 5000,20000 --overlay oxigraph
    PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_overlay.py --sizes 20000 --profile 10
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import bench_engine_vs_old as base_bench  # noqa: E402
from starlayer.graph.graph.entailment_regimes import ENTAILMENT  # noqa: E402

RULES_TTL = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex: a sh:ShapesGraph ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .
ex:RuleShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:Colleague, ex:Flag .
ex:Colleague a sh:SPARQLRule ; sh:prefixes ex: ;
  sh:construct "CONSTRUCT { $this ex:affiliation ?o } WHERE { $this ex:worksFor ?o }" .
ex:Flag a sh:TripleRule ; sh:predicate ex:flag ; sh:object true .
ex:CopyAge a sh:SPARQLRule ; sh:prefixes ex: ;
  sh:construct "CONSTRUCT { ?s ex:ageCopy ?o } WHERE { ?s ex:age ?o }" .
ex:Reach a sh:SPARQLRule ; sh:prefixes ex: ;
  sh:construct "CONSTRUCT { ?a ex:reach ?b } WHERE { ?a ex:knows ?b }" .
"""


def make_inputs(triples: int):
    from rdflib import RDFS, Namespace

    ex = Namespace("http://example.org/")
    data = base_bench.make_data(triples)
    for sub, sup in ((ex.worksFor, ex.affiliatedWith), (ex.age, ex.years), (ex.skill, ex.ability)):
        data.add((sub, RDFS.subPropertyOf, sup))
    data.add((ex.address, RDFS.domain, ex.Person))
    data.add((ex.worksFor, RDFS.range, ex.Org))
    shapes = base_bench.make_shapes(unique=False)
    shapes.parse(data=RULES_TTL, format="turtle")
    return data, shapes


def select(overlay: str) -> None:
    from starlayer.shacl_engine import rules

    rules.use_oxigraph_overlay(overlay == "oxigraph")


def timed(fn, reps: int):
    best, out = float("inf"), None
    for _ in range(reps):
        t = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t)
    return best, out


def entailed_split(data):
    """The three phases inside ``entailed_view``: copy to combined, owlrl closure, fill the overlay."""
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph, legal_rdf_triples
    from starlayer.shacl_engine.rules import new_overlay

    t0 = time.perf_counter()
    combined = StarLayerGraph()
    for t in data.triples((None, None, None)):
        combined.add(t)
    t1 = time.perf_counter()
    delta = combined.infer(entailment=frozenset({ENTAILMENT.RDFS}), mode="delta")
    t2 = time.perf_counter()
    from starlayer.shacl_engine.terms import engine_view, to_engine_triple

    view = new_overlay(engine_view(data))
    n = 0
    for t in legal_rdf_triples(delta):
        view.add(to_engine_triple(tuple(t)))
        n += 1
    t3 = time.perf_counter()
    return {"copy": t1 - t0, "owlrl": t2 - t1, "fill": t3 - t2, "delta": n}


def lookups(view, data, calls: int = 20000):
    """Mixed read workload typical of the engine: s-p-? objects, ?-p-o subjects, s-?-? scan, membership."""
    from starlayer.shacl_engine.terms import NS, RDF, engine_view

    ex = NS("http://example.org/")
    data = engine_view(data)  # the overlay speaks engine (pyoxigraph) terms
    rnd = random.Random(1)
    n = max(1, len(list(data.subjects(RDF.type, ex.Manager))) * 10)
    people = [ex[f"p{rnd.randrange(n)}"] for _ in range(calls)]
    out = {}
    t = time.perf_counter()
    for p in people:
        for _ in view.objects(p, ex.worksFor):
            pass
        for _ in view.objects(p, ex.affiliation):
            pass
    out["objects(s,p)"] = (time.perf_counter() - t) / (2 * calls) * 1e6
    t = time.perf_counter()
    for _ in range(calls // 20):
        for _ in view.subjects(RDF.type, ex.Person):
            break
        sum(1 for _ in view.subjects(ex.worksFor, ex[f"org{rnd.randrange(10)}"]))
    out["subjects(p,o)"] = (time.perf_counter() - t) / (calls // 20) * 1e6
    t = time.perf_counter()
    for p in people:
        sum(1 for _ in view.triples((p, None, None)))
    out["triples(s,?,?)"] = (time.perf_counter() - t) / calls * 1e6
    t = time.perf_counter()
    for p in people:
        _ = (p, RDF.type, ex.Person) in view
    out["contains"] = (time.perf_counter() - t) / calls * 1e6
    return out


def stages(triples: int, reps: int):
    from starlayer.shacl_engine.api import validate
    from starlayer.shacl_engine.entailment import entailed_view
    from starlayer.shacl_engine.rules import apply_rules

    data, shapes = make_inputs(triples)
    row = {"triples": len(data)}
    row["entailed_view"], view = timed(lambda: entailed_view(data, "rdfs"), reps)
    row["split"] = entailed_split(data)
    row["apply_rules"], res = timed(lambda: apply_rules(view, shapes), reps)
    row["inferred_by_rules"] = len(res.inferred)
    row["validate_on_overlay"], out = timed(lambda: validate(res.view, shapes, rules=False), reps)
    row["validate_full"], out2 = timed(lambda: validate(data, shapes, inference=ENTAILMENT.RDFS, rules=True), reps)
    row["results"] = (len(out.results), len(out2.results))
    row["lookups_us"] = lookups(res.view, data)
    return row


def profile_full(triples: int, top: int):
    from starlayer.shacl_engine.api import validate

    data, shapes = make_inputs(triples)
    pr = cProfile.Profile()
    pr.enable()
    validate(data, shapes, inference=ENTAILMENT.RDFS, rules=True)
    pr.disable()
    st = pstats.Stats(pr)
    print(f"\n=== profile validate(rdfs + rules), {len(data)} triples: {st.total_tt:.2f}s profiler-inflated; top {top} by tottime ===")
    st.sort_stats("tottime").print_stats(top)
    # attribute cumulative time to buckets
    buckets = {
        "overlay (rules.py/overlay_oxigraph.py/oxigraph_view.py)": ("shacl_engine/rules.py", "overlay_oxigraph", "oxigraph_view"),
    }
    total = st.total_tt
    print("cumulative time of selected entry points (inclusive, overlapping):")
    wanted = {
        "owlrl closure   StarLayerGraph.infer": ("infer",),
        "overlay.materialised": ("materialised",),
        "overlay.construct": ("construct",),
        "overlay.sparql_query": ("sparql_query",),
        "overlay.add": ("add",),
        "overlay.triples": ("triples",),
        "overlay.objects": ("objects",),
        "overlay.subjects": ("subjects",),
        "overlay.__contains__": ("__contains__",),
    }
    for label, (fn,) in wanted.items():
        for (fname, _ln, name), (_cc, nc, tt, ct, _c) in st.stats.items():
            if name != fn:
                continue
            if ("rules.py" in fname or "overlay_oxigraph" in fname or (fn == "infer" and "starlayer_graph" in fname)):
                print(f"  {label:42s} {ct:7.2f}s cum  {tt:7.2f}s own  {nc} calls  ({ct / total * 100:.0f}% of profile)")
    del buckets


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="5000,20000")
    ap.add_argument("--overlay", choices=("python", "oxigraph"), default="python")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--profile", type=int, metavar="TOP")
    a = ap.parse_args()
    select(a.overlay)
    for size in (int(s) for s in a.sizes.split(",")):
        if a.profile:
            profile_full(size, a.profile)
            continue
        r = stages(size, a.reps)
        sp = r["split"]
        print(f"--- overlay={a.overlay} triples={r['triples']} (rdfs delta {sp['delta']}, rule-inferred {r['inferred_by_rules']}, results {r['results']})")
        print(f"entailed_view {r['entailed_view']:.2f}s = copy {sp['copy']:.2f} + owlrl {sp['owlrl']:.2f} + overlay fill {sp['fill']:.2f}")
        print(f"apply_rules {r['apply_rules']:.2f}s | validate on overlay {r['validate_on_overlay']:.2f}s | validate full {r['validate_full']:.2f}s")
        print("lookups us/call: " + ", ".join(f"{k} {v:.1f}" for k, v in r["lookups_us"].items()), flush=True)


if __name__ == "__main__":
    main()
