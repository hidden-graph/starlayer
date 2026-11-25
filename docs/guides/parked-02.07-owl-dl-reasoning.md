# 02.07 OWL 2 DL Reasoning: material removed from the guide

Not part of the guide, and not run or linked. This is the text and code that the simplification of
[02.07](02.07-owl-dl-reasoning.ipynb) removed or rewrote, in their original order, kept until we decide what to promote to an
appendix and what to drop. The cell ids are the ids the cells had in the notebook. The statements about RustDL (the hang risk, what it
leaves out) were written for an earlier version of `rustdl` and have not been re-verified against 0.4.x.

<!-- old cell d6182484, markdown -->

# 02c OWL 2 DL Reasoning

The [Graph Inferencing guide](02.06-graphs-inferencing.ipynb) covers RDFS and OWL 2 RL reasoning via `infer()`, both backed by `owlrl`, a Python rule engine. `infer()` here is the method of `StarLayerGraph`.

This guide covers a third, separate `infer()` entailment regime instead: `entailment=ENTAILMENT['OWL-Direct']`, genuine OWL 2 DL reasoning. OWL DL reasoning requires one of two separate pluggable reasoners: 

    `engine="hermit"`, the default - [HermiT](http://www.hermit-reasoner.com/), via the `owlready2` library, needs a real Java runtime, or 

    `engine="rustdl"` ([RustDL](https://github.com/MaastrichtU-IDS/rustdl), pure Rust). 

**What OWL 2 DL reasoning means** Three questions this guide keeps coming back to: *classification/subsumption* ("is this specific fact forced to be true, given everything asserted?"), *consistency checking* ("could any model possibly satisfy every axiom at once?"), and *entailment* ("what follows that was never asserted directly?"). A reasoner's answer to any of these is *sound* if it never asserts something that isn't actually forced, and *complete* if it's guaranteed to find everything that genuinely is forced - two independent properties, and a reasoner can have one without the other. Both engines here are sound; they differ in how far their completeness guarantee reaches, and in exactly what each is built to prove.

**HermiT** is a *tableau* reasoner: rather than applying a fixed set of if-then rules, it tries to actually construct a model — a concrete interpretation that makes every axiom true at once based on the data in the graph. Where an axiom leaves a choice open (a class defined as a union, an existential restriction, and so on), HermiT picks a branch and continues; if that choice leads to a contradiction elsewhere in the data, it discards that branch and backtracks to try another. It keeps branching and backtracking over every open choice until it either succeeds — the data is consistent — or exhausts every possibility, in which case the data is inconsistent. If HermiT finds a triple that must be true in every possible model it could build, that triple is inferred. This systematic exploration is what makes it sound and complete for the *full* OWL 2 DL profile, rather than the restricted, rule-friendly OWL 2 RL fragment `owlrl` implements.

**RustDL** takes a different, no-JVM path to the same contract, with real limits of its own: sound throughout, but its own docs describe it as complete by construction only on the EL/Horn fragment - beyond that, empirically near-complete on the cases it's been checked against, not proven so the way HermiT is for all of SROIQ. It also never derives a *disjunctive* property assertion (forcing a property value only by process of elimination, with no single fact pointing at it directly) - the one idiom that needs is a confirmed hang risk, caught pre-flight rather than silently mishandled. Section 4 demonstrates both differences concretely, on the exact same ontologies sections 1-3 already build.

Section 1 (with 1.1 and 1.2, a more elaborate variant) demonstrates entailments `owlrl` cannot derive; section 2 asks a genuinely different kind of question - whether a *class* can ever have any members at all, with no individual involved; section 3 demonstrates an inconsistency that passes through `owlrl` silently but either DL engine correctly rejects; section 4 puts `engine="hermit"` and `engine="rustdl"` side by side on those same examples; section 5 shows how to materialize a closure with `infer()` once and query it many times (the live form, `query(entailment=ENTAILMENT['OWL-Direct'])`, is in the [SPARQL entailment guide](03.04-sparql-entailment.ipynb)). [Appendix B2](appendix-b2-dl-reasoning-examples.ipynb) has a much larger worked example - encoding a 20-person constraint-satisfaction problem as an ontology and solving it via consistency-checking alone - kept separate so it doesn't weigh down the core ideas here.

This is a separate guide from `02b` because the prerequisites are meaningfully heavier: a real Java runtime for the default engine, not just a pip install.

---

<!-- old cell a5e842f4, markdown -->

## How to run this notebook

This guide assumes StarLayer has been pip installed — see [Getting Started](01.01-getting-started.ipynb). Run cells from top to bottom; later cells reuse variables from earlier ones.

`owlready2` additionally requires a Java runtime on `PATH` — HermiT is a Java program. If Java isn't found or isn't configured correctly, an error message is raised.


---

<!-- old cell 378d94a4, code -->

```python
from starlayer.graph import ENTAILMENT, NamedNode
from starlayer.graph import StarLayerGraph

EX = "http://example.org/"
RDF_TYPE = NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
OWL_EQUIVALENT_CLASS = NamedNode("http://www.w3.org/2002/07/owl#equivalentClass")
OWL_NOTHING = NamedNode("http://www.w3.org/2002/07/owl#Nothing")


def ex(name):
    """An ex: IRI as a pyoxigraph NamedNode; terms read from a StarLayerGraph are pyoxigraph terms."""
    return NamedNode(EX + name)


def local(term):
    """The part of an IRI after the last '/'. NamedNode.value is the bare IRI (str() would include the angle brackets)."""
    return term.value.rsplit("/", 1)[-1]
```

---

<!-- old cell 62989eda, markdown -->

## 1. OWL 2 DL entailment

`g.infer(entailment=ENTAILMENT['OWL-Direct'])` runs genuine OWL 2 DL reasoning. The entailed triples come back as `StarLayerGraph` triples.

---

<!-- old cell 3a93fca2, markdown -->

### 1.1 A nested, three-way disjunction

OWL 2 DL can handle complex reasoning. When an analysis identifies a triple that must be true in any possible scenario that triple can be inferred.

---

<!-- old cell 07ce1f77, code -->

```python
# mycar is a Car and known NOT to be FossilFuel (itself Gas-or-Diesel) - ruling
# out that whole branch leaves only Electric, even though Electric is never
# asserted directly and Gas/Diesel are never even individually ruled out.
g_nested = StarLayerGraph()
g_nested.bind("ex", EX)
g_nested.bind("owl", "http://www.w3.org/2002/07/owl#")
g_nested.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
g_nested.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Gas owl:disjointWith ex:Electric, ex:Diesel .
    ex:Diesel owl:disjointWith ex:Electric .
    ex:FossilFuel owl:equivalentClass [ owl:unionOf ( ex:Gas ex:Diesel ) ] .
    ex:Car rdfs:subClassOf [ owl:unionOf ( ex:FossilFuel ex:Electric ) ] .
    ex:mycar a ex:Car, [ owl:complementOf ex:FossilFuel ] .
""", format="turtle")

print("Before")
print(g_nested.serialize(format="turtle", pretty=True))

closed_nested = g_nested.infer(entailment=ENTAILMENT['OWL-Direct'])
print("mycar a Electric:", (ex("mycar"), RDF_TYPE, ex("Electric")) in closed_nested)
print("mycar a Gas:      ", (ex("mycar"), RDF_TYPE, ex("Gas")) in closed_nested)
print("mycar a Diesel:   ", (ex("mycar"), RDF_TYPE, ex("Diesel")) in closed_nested)
```

Output when it was last run:

```text
Before
@prefix ex: <http://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Car rdfs:subClassOf [
        owl:unionOf ( ex:FossilFuel ex:Electric )
    ] .

ex:Diesel owl:disjointWith ex:Electric .

ex:FossilFuel owl:equivalentClass [
        owl:unionOf ( ex:Gas ex:Diesel )
    ] .

ex:Gas owl:disjointWith ex:Diesel, ex:Electric .

ex:mycar a ex:Car, [
        owl:complementOf ex:FossilFuel
    ] .

mycar a Electric: True
mycar a Gas:       False
mycar a Diesel:    False
```

---

<!-- old cell 1186b260, markdown -->

### 1.2 A small logic puzzle

OWL DL reasoning can solve complex logic problems. 

Three people, three houses, three jobs, solved from a positive clue, a negative clue, and three general rules — the classic "logic grid" pattern.

**Setting it up properly**, `ex:livesIn` and `ex:hasJob` are each declared both `owl:FunctionalProperty` and `owl:InverseFunctionalProperty`. `ex:Person` requires *some* `ex:livesIn` value from the nominal set `{RedHouse, BlueHouse, GreenHouse}` (`owl:oneOf` + `owl:someValuesFrom`), and likewise for `ex:hasJob` over `{Doctor, Teacher, Engineer}`. Because that nominal set has exactly three members, and `ex:alice`, `ex:bob`, `ex:carol` are declared pairwise `owl:differentFrom`, an injective mapping from three distinct people into a three-element set is automatically a bijection — every house and every job ends up filled by exactly one person, without ever asserting that directly.

**The clues** are then genuinely minimal:
- *(positive)* `ex:bob` lives in the Red House.
- *(negative)* `ex:carol` is not a Doctor.
- *(general rule)* whoever lives in the Red House is not a Doctor.
- *(general rule)* the Doctor does not live in the Green House.
- *(general rule)* whoever lives in the Green House is not an Engineer.

Each "rule" is a real subsumption between two restrictions (`[...] rdfs:subClassOf [ owl:complementOf [...] ]`), not a one-off fact about a specific individual — it applies to whoever ends up satisfying its antecedent, however that gets determined.

**Solving it**: rule 1 plus Bob's Red House rules Bob out for Doctor; the negative clue rules Carol out too — since the job mapping is a bijection over exactly three people, Alice must be the Doctor. Rule 2 then rules out the Green House for Alice (she's the Doctor); with Bob already in the Red House, the house bijection leaves Alice the Blue House and Carol the Green House. Rule 3 then rules out Engineer for Carol (she's in the Green House); with Alice already the Doctor, the job bijection leaves Carol as Teacher and Bob as Engineer.

---

<!-- old cell 9fb7d969, code -->

```python
g_puzzle = StarLayerGraph()
g_puzzle.bind("ex", EX)
g_puzzle.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

    # each person lives in at most one house and each house has at most one occupant.
    ex:livesIn a owl:ObjectProperty, owl:FunctionalProperty, owl:InverseFunctionalProperty .

    # each person has at most one job and each job has at most one person.
    ex:hasJob a owl:ObjectProperty, owl:FunctionalProperty, owl:InverseFunctionalProperty .

    # a pserson lives in one of three houses
    # a person has one of three jobs
    ex:Person rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty ex:livesIn ;
          owl:someValuesFrom [ owl:oneOf ( ex:RedHouse ex:BlueHouse ex:GreenHouse ) ] ] ,
        [ a owl:Restriction ; owl:onProperty ex:hasJob ;
          owl:someValuesFrom [ owl:oneOf ( ex:Doctor ex:Teacher ex:Engineer ) ] ] .

                 
    ex:alice a ex:Person .
    ex:bob a ex:Person .
    ex:carol a ex:Person .
    ex:alice owl:differentFrom ex:bob, ex:carol .
    ex:bob owl:differentFrom ex:carol .

    # clue 1 (positive): Bob lives in the Red House
    ex:bob ex:livesIn ex:RedHouse .

    # clue 2 (negative): Carol is not a Doctor
    # Carol is a member of the class of things that are not Doctors.
    ex:carol a [ owl:complementOf [ a owl:Restriction ; owl:onProperty ex:hasJob ; owl:hasValue ex:Doctor ] ] .

    # rule 1: whoever lives in the Red House is not a Doctor
    [ a owl:Restriction ; owl:onProperty ex:livesIn ; owl:hasValue ex:RedHouse ]
        rdfs:subClassOf [ owl:complementOf [ a owl:Restriction ; owl:onProperty ex:hasJob ; owl:hasValue ex:Doctor ] ] .

    # rule 2: the Doctor does not live in the Green House
    [ a owl:Restriction ; owl:onProperty ex:hasJob ; owl:hasValue ex:Doctor ]
        rdfs:subClassOf [ owl:complementOf [ a owl:Restriction ; owl:onProperty ex:livesIn ; owl:hasValue ex:GreenHouse ] ] .

    # rule 3: whoever lives in the Green House is not an Engineer
    [ a owl:Restriction ; owl:onProperty ex:livesIn ; owl:hasValue ex:GreenHouse ]
        rdfs:subClassOf [ owl:complementOf [ a owl:Restriction ; owl:onProperty ex:hasJob ; owl:hasValue ex:Engineer ] ] .
""", format="turtle")

closed_puzzle = g_puzzle.infer(entailment=ENTAILMENT['OWL-Direct'])
print("Solution:")
for person in ("alice", "bob", "carol"):
    p = ex(person)
    house = [local(o) for o in closed_puzzle.objects(p, ex("livesIn"))]
    job = [local(o) for o in closed_puzzle.objects(p, ex("hasJob"))]
    print(f"  {person}: house={house}, job={job}")
```

Output when it was last run:

```text
Solution:
  alice: house=['BlueHouse'], job=['Doctor']
  bob: house=['RedHouse'], job=['Engineer']
  carol: house=['GreenHouse'], job=['Teacher']
```

---

<!-- old cell edd4a252, markdown -->

## 2. Class unsatisfiability

A different kind of question than sections 1.1/1.2, which both ask "what type is this individual?" — here the question is about a *class itself*, with no individual involved at all: can anything possibly belong to it? This is a design-time sanity check on the rules themselves, not on any particular piece of data - exactly the kind of check a real policy review would want automated, since the bug can be invisible to a human reading either rule alone.

`ex:PricingTier` carries the Risk team's company-wide baseline: every tier's customers must *all* have excellent credit (`owl:allValuesFrom`). `ex:SecondChanceTier`, a subclass Compliance added later for a second-chance promotional program - without necessarily reviewing `PricingTier`'s own rule - requires that *at least one* customer considered have had a prior default (`owl:someValuesFrom`). `ExcellentCredit` and `PriorDefault` are disjoint credit-bureau categories.

Neither rule is wrong on its own - `PricingTier` alone is perfectly satisfiable. The problem only appears once `SecondChanceTier` inherits the parent's `allValuesFrom` constraint (ordinary subsumption) and combines it with its own `someValuesFrom` requirement.  Nobody could ever satisfy both at once, so `SecondChanceTier` is empty - logically equivalent to `owl:Nothing`. 

---

<!-- old cell b5027442, code -->

```python
# PricingTier (Risk team): every tier's customers must ALL have excellent
# credit. SecondChanceTier (Compliance, added later): at least one customer
# considered must have had a prior default - a subclass of PricingTier, so
# it inherits the allValuesFrom constraint too. ExcellentCredit and
# PriorDefault are disjoint, so combining the two makes SecondChanceTier
# unsatisfiable - even though neither rule is wrong in isolation.
g_unsat = StarLayerGraph()
g_unsat.bind("ex", EX)
g_unsat.bind("owl", "http://www.w3.org/2002/07/owl#")
g_unsat.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
g_unsat.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:hasCreditProfile a owl:ObjectProperty .
    ex:ExcellentCredit owl:disjointWith ex:PriorDefault .
    ex:PricingTier rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty ex:hasCreditProfile ; owl:allValuesFrom ex:ExcellentCredit ] .
    ex:SecondChanceTier rdfs:subClassOf ex:PricingTier ,
        [ a owl:Restriction ; owl:onProperty ex:hasCreditProfile ; owl:someValuesFrom ex:PriorDefault ] .
""", format="turtle")

print("Before")
print(g_unsat.serialize(format="turtle", pretty=True))

closed_unsat = g_unsat.infer(entailment=ENTAILMENT['OWL-Direct'])
print("SecondChanceTier is unsatisfiable (== owl:Nothing):",
      (ex("SecondChanceTier"), OWL_EQUIVALENT_CLASS, OWL_NOTHING) in closed_unsat)
print("PricingTier (the parent) is unsatisfiable:         ",
      (ex("PricingTier"), OWL_EQUIVALENT_CLASS, OWL_NOTHING) in closed_unsat)

# owlrl, for contrast, never concludes this
delta_rl = g_unsat.infer(entailment=ENTAILMENT['OWL-RDF-Based'], mode="delta")
print("owlrl also concludes this:",
      (ex("SecondChanceTier"), OWL_EQUIVALENT_CLASS, OWL_NOTHING) in delta_rl)
```

Output when it was last run:

```text
Before
@prefix ex: <http://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:ExcellentCredit owl:disjointWith ex:PriorDefault .

ex:PricingTier rdfs:subClassOf [
        a owl:Restriction ;
        owl:allValuesFrom ex:ExcellentCredit ;
        owl:onProperty ex:hasCreditProfile
    ] .

ex:SecondChanceTier rdfs:subClassOf ex:PricingTier, [
        a owl:Restriction ;
        owl:onProperty ex:hasCreditProfile ;
        owl:someValuesFrom ex:PriorDefault
    ] .

ex:hasCreditProfile a owl:ObjectProperty .

SecondChanceTier is unsatisfiable (== owl:Nothing): True
PricingTier (the parent) is unsatisfiable:          False
owlrl also concludes this: False
```

---

<!-- old cell ae0d6817, markdown -->

## 3. Detecting inconsistencies

Every car must be electric or gas-powered; `ex:mycar` is asserted to be neither — a genuine contradiction, but not one of `owlrl`'s fixed local violation patterns (Inferencing guide [section 3.5](02.06-graphs-inferencing.ipynb#3.5-Detecting-inconsistencies)), so it passes through `owlrl` silently. `entailment=ENTAILMENT['OWL-Direct']`'s consistency check is sound and complete, and raises `starlayer.graph.entailment.owl_dl.InconsistentOntologyError` outright rather than leaving it for you to notice.

---

<!-- old cell b87b0ce5, code -->

```python
from starlayer_reasoning.owl_dl import InconsistentOntologyError

# every car must be electric or gas-powered, but mycar is asserted to be
# neither - a genuine contradiction no single local rule pattern-matches
DATA = """
    @prefix ex: <http://example.org/> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Electric owl:disjointWith ex:Gas .
    ex:Car rdfs:subClassOf [ owl:unionOf ( ex:Electric ex:Gas ) ] .
    ex:mycar a ex:Car, [ owl:complementOf ex:Electric ], [ owl:complementOf ex:Gas ] .
"""

ERR_ERROR = NamedNode("http://www.daml.org/2002/03/agents/agent-ont#error")
g2 = StarLayerGraph()
g2.bind("ex", EX)
g2.parse(data=DATA, format="turtle")
closed = g2.infer(entailment=ENTAILMENT['OWL-RDF-Based'])
print("owlrl flags this as an inconsistency:", bool(list(closed.objects(None, ERR_ERROR))))

g3 = StarLayerGraph()
g3.bind("ex", EX)
g3.parse(data=DATA, format="turtle")
try:
    g3.infer(entailment=ENTAILMENT['OWL-Direct'])
    print("owl-dl: no exception raised - not reached")
except InconsistentOntologyError as e:
    print("owl-dl: InconsistentOntologyError raised:", e)
```

Output when it was last run:

```text
owlrl flags this as an inconsistency: False
owl-dl: InconsistentOntologyError raised: infer(entailment=ENTAILMENT['OWL-Direct']) found self's data logically inconsistent under OWL 2 DL semantics.
```

---

<!-- old cell ec4b2e8c, markdown -->

## 4. A second engine: `engine="rustdl"`

Both engines were introduced above; every example so far ran with the default, `engine="hermit"`. Now see where the two actually diverge on the same examples already shown. `infer()` also accepts `engine="rustdl"` - [RustDL](https://github.com/MaastrichtU-IDS/rustdl), a pure-Rust SROIQ reasoner with no JVM dependency at all. It is not a drop-in replacement for HermiT, though - a genuine tradeoff, not a strictly-better or strictly-worse alternative:

- **No Java runtime needed** - the entire reason to reach for it. Just `pip install starlayer-reasoning[rustdl]`.
- **Sound, but not provably complete on all of SROIQ** - RustDL's own docs describe it as complete by construction only on the EL/Horn fragment; beyond that, empirically near-complete rather than proven so. HermiT's tableau reasoning is sound *and* complete for the whole OWL 2 DL profile.
- **Disjunctive class entailments still work** - section 1.1's example below reproduces identically under `engine="rustdl"`.
- **A specific disjunctive-*property* idiom is a confirmed hang risk, rejected before it can hang** - not silently under-approximated, which is what an earlier version of this guide (and of `rustdl` itself) described. Section 1.2's logic puzzle uses a property declared both `owl:FunctionalProperty` and `owl:InverseFunctionalProperty`, restricted via `someValuesFrom`/`owl:oneOf` - the standard OWL 2 idiom for "exactly one of these N named individuals," and the only way to force a genuinely disjunctive property assignment in OWL DL at all. As of the currently-installed `rustdl` version, that exact idiom hangs `materialize_inferred_class_assertions()` indefinitely rather than returning an incomplete-but-sound answer - `infer(engine="rustdl")` now detects this pre-flight (a real SHACL shape, not a guess) and raises `rustdl.UnsupportedAxiomError` immediately instead of hanging. This is demonstrated concretely below, not just asserted.

`engine="rustdl"` raises the same `starlayer.graph.entailment.owl_dl.InconsistentOntologyError` for inconsistent data that `engine="hermit"` does - that contract doesn't change between engines.

---

<!-- old cell 042df450, code -->

```python
# The same nested, three-way disjunction from section 1.1, run through
# engine="rustdl" instead - reproduces the identical entailment, since it's a
# disjunctive *class* entailment (mycar's type), not a property assignment.
try:
    g_nested_rustdl = StarLayerGraph()
    g_nested_rustdl.bind("ex", EX)
    g_nested_rustdl.parse(data=g_nested.serialize(format="turtle"), format="turtle")

    closed_rustdl = g_nested_rustdl.infer(entailment=ENTAILMENT['OWL-Direct'], engine="rustdl")
    print("engine=\"rustdl\" — mycar a Electric:", (ex("mycar"), RDF_TYPE, ex("Electric")) in closed_rustdl)
    print("engine=\"rustdl\" — mycar a Gas:      ", (ex("mycar"), RDF_TYPE, ex("Gas")) in closed_rustdl)
    print("engine=\"rustdl\" — mycar a Diesel:   ", (ex("mycar"), RDF_TYPE, ex("Diesel")) in closed_rustdl)
except RuntimeError as exc:
    print("rustdl not installed in this environment - skipping this demo.")
    print(exc)
```

Output when it was last run:

```text
rustdl not installed in this environment - skipping this demo.
StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine='rustdl') requires the optional rustdl package - install it with `pip install starlayer-reasoning[rustdl]` (or `pip install rustdl` directly), then retry.
```

---

<!-- old cell e37b6c8c, markdown -->

### 4.1 The disjunctive-property idiom, rejected pre-flight

Re-running section 1.2's logic puzzle through `engine="rustdl"` demonstrates the point above concretely: the puzzle needs a genuinely disjunctive property assignment (no individual fact forces Alice into Doctor except by process of elimination across the whole nominal set), which needs the `FunctionalProperty`+`InverseFunctionalProperty`+`someValuesFrom`/`oneOf` idiom - exactly the pattern confirmed to hang RustDL, so `infer()` rejects it before ever calling into the hanging function.

---

<!-- old cell 5eb8c3c9, code -->

```python
try:
    g_puzzle_rustdl = StarLayerGraph()
    g_puzzle_rustdl.bind("ex", EX)
    g_puzzle_rustdl.parse(data=g_puzzle.serialize(format="turtle"), format="turtle")

    closed_puzzle_rustdl = g_puzzle_rustdl.infer(entailment=ENTAILMENT['OWL-Direct'], engine="rustdl")
    print("UNEXPECTED: engine=\"rustdl\" did not reject this ontology - see the")
    print("guide's own text above; this branch should not be reachable today.")
except RuntimeError as exc:
    print("rustdl not installed in this environment - skipping this demo.")
    print(exc)
except Exception as exc:
    if type(exc).__name__ == "UnsupportedAxiomError":
        print("Rejected pre-flight, as expected:")
        print(exc)
        print()
        print("engine=\"hermit\" has no such restriction - it solves this puzzle")
        print("correctly via disjunctive reasoning with zero search (section 1.2 above).")
    else:
        raise
```

Output when it was last run:

```text
rustdl not installed in this environment - skipping this demo.
StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine='rustdl') requires the optional rustdl package - install it with `pip install starlayer-reasoning[rustdl]` (or `pip install rustdl` directly), then retry.
```

---

<!-- old cell 73d5f18c, markdown -->

## 5. Materialize once, query many times

`query()` also accepts `entailment=ENTAILMENT['OWL-Direct']` (and `engine=`), the live query-time counterpart to `infer(entailment=ENTAILMENT['OWL-Direct'])`; the [SPARQL entailment guide](03.04-sparql-entailment.ipynb) covers it.

The query-time form reasons again when the graph has changed, so for many queries on unchanging data it is cheaper to materialize the closure with `infer()` and query the result, as below. This is genuine tableau DL reasoning, not `owlrl`'s cheap forward-chaining, so run `infer()` once and query the closure many times (see [Appendix B2](appendix-b2-dl-reasoning-examples.ipynb) for how steeply the cost grows with the individual count). `engine="hermit"` (default) or `engine="rustdl"` selects the reasoner on `infer()`.

---

<!-- old cell b7566db2, code -->

```python
# Same nested, three-way disjunction as section 1.1 - materialize once with infer(),
# then query the closure with ordinary SPARQL (no entailment= argument).
g_live = StarLayerGraph()
g_live.bind("ex", EX)
g_live.parse(data=g_nested.serialize(format="turtle"), format="turtle")

closure_live = g_live.infer(entailment=ENTAILMENT['OWL-Direct'])
rows = list(closure_live.query(
    "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ex:mycar a ?x }"
))
print("mycar's entailed types:", sorted(local(r["x"]) for r in rows))
```

Output when it was last run:

```text
mycar's entailed types: ['Car', 'Electric', 'cf2f0da851358923112fadc21a58e6f6']
```

---

<!-- old cell f2e7e782, markdown -->

### 5.1 Same approach, `engine="rustdl"`

Disjunctive *class* entailments (like `mycar`'s type above) work identically under `engine="rustdl"` when the closure is materialized with `infer(..., engine="rustdl")`, as section 4 shows - the same caveat from section 4 still applies, though: section 1.2's puzzle (a forced *property* assignment via the `FunctionalProperty`+`InverseFunctionalProperty`+`someValuesFrom`/`oneOf` idiom) raises `rustdl.UnsupportedAxiomError` pre-flight, not a silently incomplete answer.

---

<!-- old cell 0ff8db27, code -->

```python
try:
    g_live_rustdl = StarLayerGraph()
    g_live_rustdl.bind("ex", EX)
    g_live_rustdl.parse(data=g_nested.serialize(format="turtle"), format="turtle")
    closure_rustdl = g_live_rustdl.infer(entailment=ENTAILMENT['OWL-Direct'], engine="rustdl")
    rows = list(closure_rustdl.query(
        "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ex:mycar a ?x }"
    ))
    print("engine=\"rustdl\" — mycar's entailed types:", sorted(local(r["x"]) for r in rows))
except RuntimeError as exc:
    print("rustdl not installed in this environment - skipping this demo.")
    print(exc)
```

Output when it was last run:

```text
rustdl not installed in this environment - skipping this demo.
StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine='rustdl') requires the optional rustdl package - install it with `pip install starlayer-reasoning[rustdl]` (or `pip install rustdl` directly), then retry.
```

---

<!-- old cell e18a82f7, markdown -->

### 5.2 Inconsistency

`infer(entailment=ENTAILMENT['OWL-Direct'])` raises `InconsistentOntologyError` (section 3) rather than returning an empty or misleading closure. Because a query over the closure only happens after `infer()` returns, inconsistent data never reaches the query step. (The query-time form raises it from `query()` in the same way.)

---

<!-- old cell 13829bd5, code -->

```python
g_bad_live = StarLayerGraph()
g_bad_live.bind("ex", EX)
g_bad_live.parse(data=DATA, format="turtle")
try:
    g_bad_live.infer(entailment=ENTAILMENT['OWL-Direct'])
    print("no exception raised - not reached")
except InconsistentOntologyError as e:
    print("InconsistentOntologyError raised:", e)
```

Output when it was last run:

```text
InconsistentOntologyError raised: infer(entailment=ENTAILMENT['OWL-Direct']) found self's data logically inconsistent under OWL 2 DL semantics.
```
