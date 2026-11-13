# starlayer-reasoning

The parts of StarLayer that need rdflib or a reasoner, kept out of the `starlayer` core so the core depends on `pyoxigraph` alone.

```
pip install starlayer-reasoning              # OWL 2 RL (owlrl) and rdflib interchange
pip install "starlayer-reasoning[hermit]"    # + OWL 2 DL with HermiT (needs a JVM)
pip install "starlayer-reasoning[rustdl]"    # + OWL 2 DL with rustdl
```

Installing it is all that is needed: `starlayer` finds it when a call needs it.

| You call | It needs this package because |
| --- | --- |
| `StarLayerGraph.from_rdflib(g)`, `StarLayerDataset.from_rdflib(ds)`, `to_rdflib()` | rdflib holds the other side of the conversion |
| `graph.infer(entailment=ENTAILMENT["OWL-RDF-Based"])`, and combined regimes | OWL 2 RL runs on `owlrl` |
| `graph.infer(entailment=ENTAILMENT["OWL-Direct"], engine="hermit" or "rustdl")`, `query(entailment=...)` for it | the OWL 2 DL engines |

RDF and RDFS inference, and everything else in StarLayer, work without it.

## What is here

- `rdflib_bridge`: pyoxigraph terms to rdflib terms and back. A triple term, which rdflib cannot hold, becomes a synthetic reification fragment on the way in and is dropped from a reasoner's output on the way out; a directional literal travels in its datatype-IRI form.
- `owl_rl`: the OWL 2 RL closure of a graph (`owl_rl_delta`).
- `owl_dl`, `owl_dl_rustdl`, `_timeout`: the OWL 2 DL engines, with a wall-clock timeout that kills the whole process group (`owl_direct_delta`).
- `model`: `TripleTerm` and `DirLangString`, the rdflib-side value classes the bridge uses.
