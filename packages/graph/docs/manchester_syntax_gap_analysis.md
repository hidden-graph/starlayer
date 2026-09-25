# Manchester OWL Syntax — Conformance vs. the OWL API Parser

**Last reviewed:** 2026-09-25 (updated same day to close inline per-axiom
annotations), against OWL API 5.1.20's
`org.semanticweb.owlapi.manchestersyntax.parser.ManchesterOWLSyntaxOntologyParser`
(the real, standard-conformant OWL API parser - not a reimplementation),
run via `manchester-owl/manchester-syntax-parser`'s `OWLAPIInterface parse`
command. This is a snapshot conformance checklist against a specific
external tool, not a changelog - for fix-by-fix history see `CHANGELOG.md`.
For the RDF 1.2/SPARQL 1.2 equivalent of this document (tracking a W3C
spec directly rather than a reference implementation) see
`rdf12_sparql12_gap_analysis.md`.

The target here is deliberately "conformity with this specific OWL API
version," not "the W3C REC" - OWL API extends the Manchester syntax grammar
in a few places (`SuperClassOf:`, `that`, `onlysome`, ...), and that's what
was asked for: parity with *this* parser, unless there's a good reason not
to close a given gap.

## How this was derived

Rather than working from memory of the spec text, the keyword surface was
pulled directly from the oracle's own implementation:

```
jar xf owlapi-parsers-5.1.20.jar org/semanticweb/owlapi/manchestersyntax/parser/ManchesterOWLSyntax.class
javap -c -p ManchesterOWLSyntax.class   # every keyword + its
                                         # frame/section/axiom/quantifier/
                                         # connective flags
```

Ambiguous cases (semantics not obvious from the keyword name alone) were
then confirmed by piping a small Manchester document through
`OWLAPIInterface parse` and reading the Turtle it produced, diffed against
`starlayergraph.parsers.manchester_parser.parse_manchester()`'s own output
via `starlayergraph.compare.isomorphic()` (or a manual `graph_diff()` read
where list *order* isn't semantically significant - see the note at the
bottom). Re-run the same two steps against a newer oracle jar to
re-verify this table if it's ever upgraded.

## Conformance table

| Construct | Oracle behavior | Status |
|---|---|---|
| `Prefix:`, `Ontology:` (+ `Import:`) | header declarations; `Import:` → `owl:imports` | ✅ Match |
| `Class:`, `ObjectProperty:`, `DataProperty:`, `AnnotationProperty:`, `Individual:`, `Datatype:` frames | standard `rdf:type` declaration | ✅ Match |
| `SubClassOf:` / `SuperClassOf:` | `rdfs:subClassOf`, `SuperClassOf:` swaps subject/object | ✅ Match |
| `EquivalentTo:`, `DisjointWith:` (Class/Object/DataProperty) | `owl:equivalentClass`/`owl:equivalentProperty`, `owl:disjointWith`/`owl:propertyDisjointWith` | ✅ Match |
| `DisjointUnionOf:`, `HasKey:` | `owl:disjointUnionOf`/`owl:hasKey` + `rdf:List` | ✅ Match |
| `Domain:`, `Range:` | `rdfs:domain`/`rdfs:range`; `Range:` on DataProperty takes a **data range**, not a class expression | ✅ Match |
| `SubPropertyOf:` / `SuperPropertyOf:` | `rdfs:subPropertyOf`, `SuperPropertyOf:` swaps subject/object | ✅ Match |
| `InverseOf:`, `inverse` | `owl:inverseOf` | ✅ Match |
| `SubPropertyChain:` (`p1 o p2 o ...`) | `owl:propertyChainAxiom` + `rdf:List` | ✅ Match |
| `Characteristics:` (Functional/InverseFunctional/Transitive/Symmetric/Asymmetric/Reflexive/Irreflexive) | `rdf:type owl:*Property` | ✅ Match |
| `and`/`or`/`not`, parens | `owl:intersectionOf`/`unionOf`/`complementOf` | ✅ Match |
| `that` | confirmed a straight synonym for `and` at this position (English-readable restriction refinement) | ✅ Match |
| `some`/`only`/`value`/`Self` | `owl:Restriction` + `someValuesFrom`/`allValuesFrom`/`hasValue`/`hasSelf` | ✅ Match |
| `onlysome` | confirmed = `(p some C) and (p only C)` | ✅ Match |
| `min`/`max`/`exactly` (qualified + unqualified) | `owl:{min,max,}[Qualified]Cardinality` (+`owl:onClass`) | ✅ Match |
| `{a, b}` (class enumeration) | `owl:oneOf` | ✅ Match |
| Data ranges: atomic, `and`/`or`/`not`, `{lit, ...}` (DataOneOf), `datatype[facet lit, ...]` | `owl:DatatypeRestriction`/`onDatatype`/`withRestrictions`, `datatypeComplementOf`, `unionOf`/`intersectionOf`/`oneOf` typed `rdfs:Datatype` | ✅ Match (numeric + length/pattern facets: `>=`/`<=`/`>`/`<`/`length`/`minLength`/`maxLength`/`pattern`; `langRange` not implemented - narrow, rarely-used facet) |
| `Datatype: EquivalentTo:` | `owl:equivalentClass` (yes, reused for datatype definitions - confirmed, not a typo) | ✅ Match |
| `Types:`, `SameAs:`, `DifferentFrom:` | `rdf:type`, `owl:sameAs`, `owl:differentFrom` | ✅ Match |
| `Facts:` (positive) | direct triple / data-property assertion | ✅ Match |
| `Facts: not ...` (negative) | `owl:NegativePropertyAssertion` + `sourceIndividual`/`assertionProperty`/`targetIndividual`-or-`targetValue` | ✅ Match |
| `EquivalentClasses:`, `DisjointClasses:` (Misc) | pairwise chain / `owl:AllDisjointClasses`+`members` for >2 | ✅ Match |
| `EquivalentProperties:`, `DisjointProperties:` (Misc) | same shape, property-flavored (`owl:AllDisjointProperties` for >2) | ✅ Match |
| `SameIndividual:`, `DifferentIndividuals:` (Misc) | pairwise chain / `owl:AllDifferent`+`members` for >2 | ✅ Match |
| Frame-level `Annotations:` clause | direct triples on the frame's own subject (`Class: A Annotations: rdfs:label "Foo"` → `(A, rdfs:label, "Foo")`) - confirmed **no** reification | ✅ Match |
| Inline per-axiom `Annotations:` (e.g. `SubClassOf: Annotations: rdfs:comment "why" B, C` - annotates just the B axiom, not C) | `owl:Axiom`/`owl:annotatedSource`/`owl:annotatedProperty`/`owl:annotatedTarget` + the annotation triples, alongside the plain axiom triple - confirmed on `SubClassOf:`, `HasKey:`, and `Facts:` (object-property case); generalized by the same mechanism (`_parse_item_annotations()`/`_maybe_reify()`) to every other clause where one list item maps to one axiom triple. A negative `Facts:` item attaches its annotation straight to the existing `owl:NegativePropertyAssertion` bnode instead of a second wrapper node (that bnode is already the reification-like structure) - a reasoned extrapolation from the OWL 2 RDF mapping, not independently oracle-confirmed for that specific combination. **Not** supported on the six top-level Misc axioms (`EquivalentClasses:` and friends) - see below. | ✅ Match (Misc axioms excepted) |

## Deliberately not matched, with reasons

| Construct | Why not |
|---|---|
| `inv` (short alias for `inverse`) | Empirically confirmed the oracle **itself rejects it** (`Encountered inv... Expected one of: Object property name, inverse`) - a reserved-but-dead enum entry. Nothing to conform to. |
| `ValuePartition:`, `DASH` (`-`) | Every `frameKeyword`/`sectionKeyword`/`axiomKeyword`/quantifier/connective flag on both enum constants is `false` - not wired up as parseable input even by OWL API 5.1.20 itself, despite the token being reserved. |
| `Rule:` (SWRL rules) | Real and functional in the oracle, but a whole separate rule-language grammar orthogonal to OWL axiom parsing - out of scope for this parser, not a small conformance gap. Revisit as its own piece of work if wanted. |
| Inline `Annotations:` on the six top-level Misc axioms (`EquivalentClasses:`/`DisjointClasses:`/`EquivalentProperties:`/`DisjointProperties:`/`SameIndividual:`/`DifferentIndividuals:`) | Every other clause reduces cleanly to "one list item → one axiom triple," which is what `_maybe_reify()` reifies. Misc axioms don't: their RDF mapping is a pairwise chain (2 items) or an `owl:AllDisjoint*`/`members` collection (>2 items) - there's no single item-to-triple correspondence to hang a per-item annotation off. Rather than guess at an unconfirmed grammar/mapping for this shape, it's left unimplemented - `ManchesterSyntaxError`, not silently mis-parsed. |
| Declaration-order / entity-type-checking strictness | The oracle requires every name to be declared via its own frame before use elsewhere (`Encountered Pet at line 9... Expected one of: Class name, Object property name...` for an undeclared name) - because it builds a strongly-typed `OWLOntology` object model where an entity's punning type must be resolvable from context. `manchester_parser.py` only produces RDF triples, where `(x, rdf:type, owl:Class)` doesn't require `x` to have been "declared" first. Replicating this would make the parser *reject* well-formed axiom fragments that map to perfectly valid RDF, for no benefit here - a deliberate design difference, not a bug. |
| `owl:unionOf`/`intersectionOf`/`oneOf`/`members`/`withRestrictions` **list member order** | Confirmed via a direct probe (`xsd:string or xsd:integer`) that the oracle's `rdf:List` member order for these mathematically-unordered constructs doesn't reliably match written order - almost certainly Java `HashSet`/collection iteration order inside OWL API, not a spec requirement. `graph_diff()`/`isomorphic()` will report a difference here purely from list-cell ordering even when both sides represent the identical OWL axiom; this is expected and not something to chase - don't read a list-order mismatch alone as a real bug. |

## Where the parser lives

`packages/graph/starlayergraph/parsers/manchester_parser.py`
(entry point `parse_manchester(text, base=None) -> list[tuple]`), wired
into `StarLayerGraph.parse(format="manchester")` (alias `"omn"`). Tests:
`packages/graph/tests/unit/test_manchester_parser.py` - oracle-free,
asserting the RDF shapes this document describes directly.
