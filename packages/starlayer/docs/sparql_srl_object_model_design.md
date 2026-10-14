# Design: a SPARQL "prepared query" object, and SRL `RuleSet` enhancements

*Status: implemented 2026-10-14 - see `starlayer/sparql/CLAUDE.md`'s own same-day entry for what shipped and the real `StarLayerGraph.query()` bug found along the way. This document is kept as the design record; the "open questions" below are resolved as noted.*

Two related items from `docs/guides/Notes on guides and other comments`' "Function" list:

1. "create a SPARQL equivalent to StarGraph and StarSchema."
2. "Do the same with SRL."

The user's own framing for (1): a class whose "primary purpose is to hold a query object. That object then could be used to perform queries on different graphs. It may also hold entailment regime." For (2), the follow-up brainstorm: *"if a ruleset is an object like graph or schema, what could it do. we point it to different graphs and get graphs in return. applying inferencing is an interesting idea. we could feed it a shape and have it validate the result."*

## Decided vs. still open

| | Decided | Resolution |
|---|---|---|
| SPARQL class | Rich binding (query + every per-call option `StarLayerGraph.query()` takes). No SHACL-validation of a `CONSTRUCT` result at this class's level - "probably too much." | Named `StarQuery`. |
| SRL `RuleSet` | Gains an entailment regime and a schema/shape to validate the inferred result against; the schema argument accepts either a `StarShaclSchema` instance or a bare shapes graph. `starlayer.sparql` → `starlayer.shacl` dependency accepted. | Lives directly on `infer()` (conditional return: bare graph when `schema` is omitted, `RulesResult` when given) rather than a separate `infer_and_validate()` method. |

A real, previously-unknown bug was found while implementing the SPARQL class - `StarLayerGraph.query()`'s `entailment=ENTAILMENT.RDF`/`RDFS` silently has no effect when `query_object` is an already-prepared `Query` rather than text. See `starlayer/sparql/CLAUDE.md`'s same-day entry for the full account and how `StarQuery` works around it.

## What already exists (confirmed against real code)

- `starlayer.sparql.parse12.prepare_query_12(text, base=None, initNs=None) -> Query` (`parse12.py:118`) already returns a real, executable rdflib `Query` object.
- `StarLayerGraph.query()` (`starlayer_graph.py:1994`) already accepts either raw query text or an already-prepared `Query` object as `query_object`, plus `processor=`, `result=`, `initNs=`, `initBindings=`, `use_store_provided=`, `entailment=`, `infer=`, `engine=`, `timeout=`. The new class's whole job is binding this method's own options once, not re-implementing query execution.
- `srl.RuleSet` (`_srl_ast.py:211`) already has exactly the "point it at different graphs, get graphs/rows back" shape:
  ```python
  def infer(self, base_graph: Graph) -> Graph: ...        # _srl_ast.py:228
  def query(self, base_graph: Graph, goal_pattern: TriplePattern) -> list[dict]: ...  # _srl_ast.py:246
  ```
  `RuleSet` is a plain (non-frozen) `@dataclass` with three fields: `rules`, `data`, `imports`. It is also the value `ruleset_to_tree()`/`tree_to_ruleset()` round-trip to/from RDF (`srl.py`). That dual role is the one real technical constraint shaping Part 2 below.
- `starlayer.shacl.RulesResult` (`results.py:29`) is already exactly the shape `(inferred_graph, validation: ValidationResult)` that "feed it a shape and validate the result" needs - reusing it directly avoids inventing a parallel result type for the identical concept.
- `starlayer.shacl.StarShaclSchema(shacl_graph=None, ont_graph=None, *, data_graph=None, inference=None, adapter=None, validate_fn=None)` - the binding-pattern precedent both designs below are modeled on: bind the "thing to interpret" plus cross-cutting config once at construction, then call processing methods repeatedly against different data without re-passing the same arguments.

## Part 1: the SPARQL-side class

Binds everything `StarLayerGraph.query()` takes as a per-call option, once, around a query prepared exactly once:

```python
class StarQuery:
    def __init__(
        self,
        text: str,
        *,
        base: str | None = None,
        initNs: Mapping[str, Any] | None = None,
        initBindings: Mapping[str, Any] | None = None,
        entailment: Any | None = None,
        infer: str = "changed",
        engine: str = "hermit",
        timeout: float | None = _OWL_DL_TIMEOUT_DEFAULT,
    ) -> None:
        self._prepared = prepare_query_12(text, base=base, initNs=initNs)
        self.initNs = initNs
        self.initBindings = initBindings
        self.entailment = entailment
        self.infer = infer
        self.engine = engine
        self.timeout = timeout

    def run(self, graph, **overrides):
        """Run the bound query against any graph. Any bound option can be
        overridden per call without disturbing what's bound."""
        kwargs = dict(
            initNs=self.initNs, initBindings=self.initBindings,
            entailment=self.entailment, infer=self.infer,
            engine=self.engine, timeout=self.timeout,
        )
        kwargs.update(overrides)
        return graph.query(self._prepared, **kwargs)
```

Usage:

```python
q = StarQuery("SELECT ?s WHERE { ?s ex:worksFor ?o }", entailment=ENTAILMENT.RDFS)
rows_a = q.run(graph_a)
rows_b = q.run(graph_b, entailment=None)  # per-call override, bound value untouched
```

This mirrors `StarShaclSchema`'s own "bind once, call repeatedly, override per call" shape exactly. `prepare_query_12` runs only once, at construction - repeated `.run()` calls against different graphs reuse the same prepared `Query` object, the same performance benefit rdflib's own `prepareQuery()`/`graph.query(prepared)` precedent already offers, just with the surrounding options bound alongside it instead of the caller repeating them on every call.

**Explicitly out of scope**, per the user's own call: no SHACL-shape validation of a `CONSTRUCT` query's own result graph at this class's level.

**Naming - resolved**: `StarQuery` (direct analogy to the user's own "StarGraph"/"StarSchema" shorthand), confirmed directly rather than put through the same multi-day deliberation `StarShaclSchema` itself got.

## Part 2: SRL `RuleSet` enhancements

Two new **per-call** keyword-only parameters on `.infer()` (and `inference=` on `.query()` too) - **not new stored fields on the `RuleSet` dataclass itself**. This is the one real technical constraint, not a style preference: `RuleSet` is also the value `ruleset_to_tree()` serializes to RDF - a stored "bound schema"/"bound entailment regime" field would either leak into that encoding or need special-casing to exclude it, for no benefit over a per-call parameter. Keeping `RuleSet` exactly as clean an AST value as it is today was the deciding factor.

```python
def infer(
    self,
    base_graph: Graph,
    *,
    inference: Any | None = None,                    # an ENTAILMENT.* regime, or iterable of them
    schema: "StarShaclSchema | Any | None" = None,    # a StarShaclSchema, or a bare shapes graph
):
    if inference is not None:
        base_graph = base_graph.infer(entailment=inference, mode="full")  # pre-entail, same spirit as sh:entailment-before-rules

    from . import srl_eval
    inferred = srl_eval._srl_infer(base_graph, self)  # today's existing logic, unchanged

    if schema is None:
        return inferred  # unchanged return shape when schema isn't used - zero breakage for any existing caller

    from starlayer.shacl import RulesResult, StarShaclSchema
    resolved_schema = schema if isinstance(schema, StarShaclSchema) else StarShaclSchema(shacl_graph=schema)
    validation = resolved_schema.validate(data_graph=inferred)
    return RulesResult(inferred_graph=inferred, validation=validation)
```

Usage:

```python
result = ruleset.infer(base, inference=ENTAILMENT.RDFS, schema=person_schema)
print(result.inferred_graph)
print(result.validation.conforms)

# "allow both" - a bare shapes graph works too, not just a StarShaclSchema instance
result2 = ruleset.infer(base, schema=shapes_graph)
```

`schema=` is normalized with one `isinstance` check: a `StarShaclSchema` instance is used as-is (so a caller who already has one bound with its own `ont_graph`/`inference` gets that reused); a bare shapes graph is wrapped in a throwaway `StarShaclSchema(shacl_graph=schema)` first.

`starlayer.sparql` gains a real, direct dependency on `starlayer.shacl` for this - confirmed via `grep` that neither `srl.py` nor `_srl_ast.py` imports anything from `starlayer.shacl` today, so this is new, not already present. Accepted per the user's explicit "I do not worry about the dependency." (For reference: `starlayer.graph`⇄`starlayer.shacl` already has a two-way dependency elsewhere in this project - e.g. `StarLayerGraph.derive()` - so a one-way `sparql → shacl` dependency is a smaller addition than that existing precedent.)

`.query()` gains `inference=` the same way (pre-entail the base graph before evaluating the goal pattern); `schema=` doesn't apply there - `.query()` returns rows, not a graph, so there's nothing to validate.

**Return-shape - resolved**: lives directly on `.infer()` as shown above (conditional return - a bare `Graph` when `schema` is omitted, a `RulesResult` when it's given), confirmed rather than the alternative also considered - a dedicated `.infer_and_validate()` method always returning `RulesResult`, leaving plain `.infer()` untouched.

## Comparison table

| Capability | Binds/added | Cost | Precedent mirrored |
|---|---|---|---|
| `StarQuery` (or final name) | query text (prepared once), `entailment`, `initNs`, `initBindings`, `infer`, `engine`, `timeout` | One new class, no new dependency (`starlayer.sparql` already depends on nothing new - `prepare_query_12`/`StarLayerGraph.query()` are both already in-package or already-depended-on) | `StarShaclSchema`'s own constructor-binding shape |
| `RuleSet.infer(inference=...)` | an entailment regime, applied to `base_graph` before inference | None - pure addition, optional parameter, `None` default preserves today's behavior exactly | SHACL's own `sh:entailment`-before-rules precedent |
| `RuleSet.infer(schema=...)` | a `StarShaclSchema` or bare shapes graph, used to validate the inferred result | New `starlayer.sparql → starlayer.shacl` dependency; conditional return shape (flagged above) | `RulesResult`'s own existing `(inferred_graph, validation)` shape, reused verbatim |

## Next step

Once naming (Part 1) and the `.infer()`-vs-`.infer_and_validate()` return-shape question (Part 2) are settled, this becomes a real implementation plan - new test coverage for both, and (per this project's own standing discipline) a `CLAUDE.md` entry in both `starlayer/sparql/` and `starlayer/shacl/` documenting the cross-package dependency addition.
