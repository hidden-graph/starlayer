# starlayer-reasoning

The OWL reasoners of StarLayer, kept out of the `starlayer` core so the core depends on `pyoxigraph` alone. They run on rdflib, so installing this package brings in `starlayer[rdflib]` (the rdflib conversion, which is in the core) and `owlrl`.

```
pip install starlayer-reasoning              # OWL 2 RL (owlrl)
pip install "starlayer-reasoning[hermit]"    # + OWL 2 DL with HermiT (needs a JVM)
pip install "starlayer-reasoning[rustdl]"    # + OWL 2 DL with rustdl
```

Installing it is all that is needed: `starlayer` finds it when a call needs it.

| You call | It needs this package because |
| --- | --- |
| `graph.infer(entailment=ENTAILMENT["OWL-RDF-Based"])`, and combined regimes | OWL 2 RL runs on `owlrl` |
| `graph.infer(entailment=ENTAILMENT["OWL-Direct"], engine="hermit" or "rustdl")`, `query(entailment=...)` for it | the OWL 2 DL engines |

RDF and RDFS inference, and everything else in StarLayer, work without it. The rdflib conversion (`from_rdflib`, `to_rdflib`) is in the core and needs only `pip install "starlayer[rdflib]"`.

## What is here

- `owl_rl`: the OWL 2 RL closure of a graph (`owl_rl_delta`). A graph is converted with the core's `starlayer.graph.rdflib_bridge`: a triple term, which rdflib cannot hold, becomes a synthetic reification fragment on the way in and is dropped from the reasoner's output on the way out.
- `owl_dl`, `owl_dl_rustdl`, `_timeout`: the OWL 2 DL engines, with a wall-clock timeout that kills the whole process group (`owl_direct_delta`).
