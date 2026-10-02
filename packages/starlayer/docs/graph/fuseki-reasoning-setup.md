# Configuring a Reasoning-Enabled Fuseki Backend

*Last reviewed: 2026-09-20*

`StarLayerGraph.query(..., entailment="native")` (only legal with `backend="rdf-1.2"`) adds no rewriting or materialization of its own - it's a self-documenting label on top of what `native_query()` already does, which is send SPARQL text straight through to the endpoint unmodified (see `backends/native.py`'s own module docstring). That means entailment support for a native-backed `StarLayerGraph` is entirely a property of how the *endpoint itself* is configured, not something this library provides. This doc shows two ways to configure a real Apache Jena Fuseki instance to reason before answering queries - both confirmed live (2026-09-20, Fuseki 6.1.0 via `atomgraph/fuseki:6.1.0`, the same image `docs/fuseki-upstream-issues.md` uses), then queried successfully through `StarLayerGraph`'s own `entailment="native"` path.

See `docs/guides/03b-sparql-inferencing.ipynb` for what this project's *own* reasoning (`entailment="rdfs"`/`"owl-rl"`, `StarLayerGraph.infer()`) covers without needing any of this - delegating to Fuseki is for when you'd rather the endpoint carry that cost, or need something (e.g. custom rules) neither our rewrite nor `owlrl` covers.

## Option 1: RDFS via `--rdfs=FILE` (simplest)

Fuseki's own CLI has a dedicated flag for exactly this - no assembler config needed. Point it at a Turtle file containing your RDFS schema (`rdfs:subClassOf`/`rdfs:subPropertyOf`/`rdfs:domain`/`rdfs:range` triples); Fuseki applies RDFS entailment over the dataset using that schema for every query.

```bash
docker run -d --name fuseki-rdfs -p 3030:3030 \
  -v /path/to/schema.ttl:/fuseki/schema.ttl:ro \
  atomgraph/fuseki:6.1.0 --mem --rdfs=/fuseki/schema.ttl --update /ds
```

Confirmed live with `schema.ttl` containing:

```turtle
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Manager rdfs:subClassOf ex:Employee .
ex:worksAt rdfs:domain ex:Person .
```

then, via `StarLayerGraph`:

```python
from starlayergraph import StarLayerGraph, Namespace
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

EX = Namespace("http://example.org/")
store = SPARQLUpdateStore(
    query_endpoint="http://localhost:3030/ds/query",
    update_endpoint="http://localhost:3030/ds/update",
)
g = StarLayerGraph(store=store, backend="rdf-1.2")
g.update("PREFIX ex: <http://example.org/> INSERT DATA { ex:alice a ex:Manager . ex:alice ex:worksAt ex:Acme . }")

list(g.query("PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }", entailment="native"))
# -> [ex:alice], via rdfs:subClassOf
list(g.query("PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }", entailment="native"))
# -> [ex:alice], via rdfs:domain
```

Both confirmed returning `ex:alice` as expected.

## Option 2: Assembler config, for OWL (or anything the CLI flag doesn't cover)

There's no CLI shortcut for OWL - it needs a full assembler `.ttl` config wrapping the dataset's default graph in a `ja:InfModel` bound to one of Jena's reasoner URIs.

```turtle
@prefix ja: <http://jena.hpl.hp.com/2005/11/Assembler#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .

<#service> a fuseki:Service ;
    fuseki:name "ds" ;
    fuseki:endpoint [ fuseki:operation fuseki:query ] ;
    fuseki:endpoint [ fuseki:operation fuseki:update ] ;
    fuseki:dataset <#dataset> .

<#dataset> a ja:RDFDataset ;
    ja:defaultGraph <#owlModel> .

<#owlModel> a ja:InfModel ;
    ja:baseModel [ a ja:MemoryModel ] ;
    ja:reasoner [ ja:reasonerURL <http://jena.hpl.hp.com/2003/OWLFBRuleReasoner> ] .
```

**The reasoner spec must be its own blank node** (`ja:reasoner [ ja:reasonerURL <...> ]`), not `ja:reasonerURL` directly on the `InfModel` node - putting it directly on the `InfModel` node throws `AmbiguousSpecificTypeException: cannot find a most specific type ... possibilities: ja:InfModel ja:ReasonerFactory` at startup (confirmed live hitting this exact error before fixing it).

**No named endpoints means the endpoint path is the bare dataset path**, not `/ds/query`/`/ds/update` - `fuseki:endpoint [ fuseki:operation fuseki:query ]` with no `fuseki:name` registers the operation directly at `/ds` itself (confirmed via `GET /$/server`, which reports `"srv.endpoints": [""]` for exactly this reason). Point both `query_endpoint` and `update_endpoint` at the bare `/ds` path when using a config shaped like the one above.

```bash
docker run -d --name fuseki-owl -p 3030:3030 \
  -v /path/to/owl-config.ttl:/fuseki/config.ttl:ro \
  atomgraph/fuseki:6.1.0 --config=/fuseki/config.ttl
```

Confirmed live:

```python
store = SPARQLUpdateStore(query_endpoint="http://localhost:3030/ds", update_endpoint="http://localhost:3030/ds")
g = StarLayerGraph(store=store, backend="rdf-1.2")
g.update("""
    PREFIX ex: <http://example.org/> PREFIX owl: <http://www.w3.org/2002/07/owl#>
    INSERT DATA { ex:Manager owl:equivalentClass ex:TeamLead . ex:alice a ex:Manager . }
""")
list(g.query("PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:TeamLead }", entailment="native"))
# -> [ex:alice], via owl:equivalentClass
```

## What this does and doesn't give you

Per Jena's own inference documentation: the OWL reasoners (`OWLFBRuleReasoner` above, plus `OWLMiniRuleReasoner`/`OWLMicroRuleReasoner` for lighter-weight subsets) are **sound but explicitly not complete** - Jena's own words: "the rule based approach cannot offer a complete solution for OWL/Lite, let alone the OWL/Full fragment." There's no built-in DL reasoner (for that, Jena's own docs point to an external one - Pellet, Racer, FaCT); D-Entailment (datatype canonicalization) is explicitly excluded from the RDFS reasoner too - see `docs/guides/03b-sparql-inferencing.ipynb`'s entailment-regime status table for how this compares to what StarLayerGraph covers on its own.

## Other reasoner URIs

Confirmed present in Jena's assembler vocabulary docs (not independently verified live beyond the two used above): `http://jena.hpl.hp.com/2003/RDFSExptRuleReasoner` (RDFS, for the assembler-config route instead of `--rdfs=FILE`), `http://jena.hpl.hp.com/2003/OWLMiniRuleReasoner`, `http://jena.hpl.hp.com/2003/OWLMicroRuleReasoner` (lighter OWL subsets than `OWLFBRuleReasoner` above), and `http://jena.hpl.hp.com/2003/TransitiveReasoner` (just `subClassOf`/`subPropertyOf` transitive closure, no domain/range/OWL).
