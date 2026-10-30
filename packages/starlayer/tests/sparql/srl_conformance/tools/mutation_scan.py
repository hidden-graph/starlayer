"""Mutation scan of the srl: shapes: how well do they tell a broken tree from a good one?

Takes the srl: tree of every corpus case and applies each mutation operator once per distinct
(node class, property, operator). For every mutant it records whether ``srl_validate`` REJECTS it, whether it
validates and still decodes (usually a legitimate optional thing removed), or - the finding that matters -
whether it passes validation yet CRASHES the decoder: a hole in the shapes.

    python tests/sparql/srl_conformance/tools/mutation_scan.py [--out mutants.json]

Same method as tests/starontology/manchester_conformance/tools/mutation_scan.py. Operators: remove a triple;
replace a value by a literal; add a second value; drop an rdf:type; break an rdf:List's termination.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE.parent))

from rdflib import BNode, Graph, Literal, URIRef  # noqa: E402
from rdflib.namespace import RDF  # noqa: E402
from srl_conformance.corpus import CASES  # noqa: E402
from starlayer.sparql.srl import (  # noqa: E402
    srl_parse_to_tree,
    srl_tree_to_text,
    srl_validate,
    tree_to_ruleset,
)

NS = "https://github.com/hidden-graph/starlayer/ns/sparql/"


def local(term) -> str:
    return str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def types_of(g, node) -> str:
    return ",".join(sorted(local(o) for o in g.objects(node, RDF.type) if str(o).startswith(NS))) or "(untyped)"


def verdict(g, root):
    try:
        ok, _, _ = srl_validate(g)
    except Exception as error:  # noqa: BLE001
        return "validator-crash", f"{type(error).__name__}: {str(error)[:80]}"
    if not ok:
        return "rejected", None
    try:
        srl_tree_to_text(g, root)
        tree_to_ruleset(g, root)
    except Exception as error:  # noqa: BLE001
        return "HOLE-decoder-crash", f"{type(error).__name__}: {str(error)[:80]}"
    return "survives-decodes", None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many mutants (0 = all)")
    args = ap.parse_args()

    seen: set = set()
    results: list = []
    started = time.time()
    for case in CASES:
        try:
            tree, root = srl_parse_to_tree(case.text)
        except Exception:  # noqa: BLE001
            continue
        base = Graph()
        for t in tree:
            base.add(t)
        for s, p, o in sorted(base, key=str):
            in_ns = str(p).startswith(NS)
            is_type = p == RDF.type and str(o).startswith(NS)
            if not (in_ns or is_type or p in (RDF.first, RDF.rest)):
                continue
            ops = []
            if in_ns:
                ops += ["remove", "wrongkind-literal", "duplicate"]
            if is_type:
                ops.append("drop-type")
            if p == RDF.rest:
                ops.append("break-rest")
            if p == RDF.first:
                ops.append("wrongkind-literal-first")
            for op in ops:
                signature = (types_of(base, s), local(p), op)
                if signature in seen:
                    continue
                seen.add(signature)
                g = Graph()
                for t in base:
                    g.add(t)
                if op in ("remove", "drop-type", "break-rest"):
                    g.remove((s, p, o))
                elif op.startswith("wrongkind"):
                    g.remove((s, p, o))
                    g.add((s, p, Literal("MUTANT")))
                else:  # duplicate
                    other = URIRef("urn:mutant:other") if isinstance(o, URIRef) else (
                        Literal("MUTANT") if isinstance(o, Literal) else BNode())
                    g.add((s, p, other if other != o else URIRef("urn:mutant:other2")))
                result, detail = verdict(g, root)
                results.append([result, *signature, detail, case.id])
                if args.limit and len(results) >= args.limit:
                    break
            if args.limit and len(results) >= args.limit:
                break
        if args.limit and len(results) >= args.limit:
            break

    counts = collections.Counter(r[0] for r in results)
    print(f"mutants: {len(results)}  seconds: {round(time.time() - started)}")
    print(dict(counts))
    for r in results:
        if r[0] in ("HOLE-decoder-crash", "validator-crash"):
            print("  ", r)
    if args.out:
        args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 1 if counts.get("HOLE-decoder-crash") or counts.get("validator-crash") else 0


if __name__ == "__main__":
    raise SystemExit(main())
