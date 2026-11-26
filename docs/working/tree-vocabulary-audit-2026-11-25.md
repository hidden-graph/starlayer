# Tree vocabularies against the languages' own grammars: audit (2026-11-25)

Status: investigation note for John to decide. Nothing in code, tests, notebooks or the workbench was changed. Untracked, not for commit.
Question: "I think we may have started with the rdflib algebra, which is not really needed. Can everything be tied back to its
SPARQL / SRL / Manchester syntax?"

Sources read: `starontology/{sqe,spexpr,srl,manchester}/*.ttl`, `sparql/vocab.py`, `sparql/sqe/vocab.py`, `sparql/_srl_ast.py`,
`sparql/parse_sparql.py` (node kinds), `sparql/expr_families.py`, the vendored production tables
(`tests/sparql/parse_sparql_conformance/vendor/sparql12-query-productions.json`, 194 productions, WD 2026-11-01;
`tests/sparql/srl_conformance/vendor/sparql12-rl-productions.json`; `tests/starontology/manchester_conformance/vendor/owl2-manchester-productions.json`),
and https://www.w3.org/TR/sparql12-rl/ section 4.1 (fetched 2026-11-25, first 100 000 characters only). Counts are `git ls-files` greps of
the CURIE (`sqe:Filter`) plus, for Python, the kind string or `SQE.<Name>` constant; they are occurrences, not distinct files.

## 1. Answer in one paragraph

Mostly no for `sqe:`, `srl:` and `manch:`, yes for `spexpr:`. The statement "we started from the rdflib algebra" is not what the tree
shows: no class is named after an rdflib *algebra operator* (no BGP, Join, LeftJoin, Extend, Project, ToMultiSet, AggregateJoin,
Slice, ...). `sqe:` is already named after SPARQL grammar productions or keywords (the flat `sqe:where` list is the raw parse tree's
`GroupGraphPatternSub`, as `sqe/vocab.py` says). `srl:` is named after the draft's section 4.1 abstract syntax and `manch:` after the
Note's keywords and productions. What remains of rdflib is in the shared expression vocabulary `spexpr:`: its class names are rdflib's
*parser* node names (`Builtin_STR`, `Aggregate_Count`, `Function`, `UnaryNot`), its path classes are rdflib's `rdflib.paths` class
names (`SequencePath`, `AlternativePath`, `InvPath`, `MulPath`, `NegatedPath`), its argument properties are rdflib's `CompValue` key
names (`arg`, `arg1`, `arg2`, `arg3`, `other`, `vars`), and `spexpr:TrueFilter` is a pure algebra artefact (rdflib's stand-in for an
OPTIONAL with no FILTER). The grammar productions are mostly already spec names for the operator-chain expressions
(`RelationalExpression`, `ConditionalOrExpression`, `AdditiveExpression`, ...).

## 2. Is any trace of `salg:` / rdflib left?

No import and no `salg:` term is produced or consumed (retired in a70f98f2; `tests/.../test_sr_architecture.py` and the packaging tests
assert it). Comment, docstring and design-doc residue remains:

- `sparql/sqe/vocab.py`: 16 mentions of `salg`/`ssyn`/`sast`. Stale statements: line 149 `FILTER = SQE.Filter  # .expr -> salg: expression
  (fallback boundary)`, line 150 (BIND), line 185 (`EXPR`: "the salg:-boundary property"), line 117 "see salg:Query's own identical convention",
  and lines 5 to 74 (the rationale is written as a contrast with `salg:`, with `ssyn:`/`sast:` as precedents that no longer exist).
- `sparql/expr_families.py`: five comments say `salg:arg`, `salg:expr`, `salg:arg1/arg2`. The docstring says the node names "are the
  parser's": they are rdflib's parser's names, kept by `parse_sparql.py` on purpose.
- `sparql/expr_validation.py` (lines 4, 8, 11, 37): "`salg` imports this module; `sqe` must not import `salg`" and "needs rdflib".
- `sparql/sqe/shapes.py` (lines 7, 53): "Nothing here imports or loads salg" (true, but the sentence now only records history).
- `starontology/manchester/__init__.py` lines 25, 77, 100, 1250, 1258: comparisons with `salg:`/`sast:` ("same bar `salg:` itself holds").
- `starontology/sqe/sqe-ontology.ttl` `sqe:where` comment ("not a resolved algebra's nested LeftJoin/Filter wrapping"),
  `spexpr-ontology.ttl` `spexpr:Expression` ("any of rdflib's ~63 expression builtins") and `spexpr:TrueFilter`.
- `docs/design/sparql/implementation-notes.md` and `docs/design/sparql_srl_object_model_design.md` still describe the retired design
  (rdflib `CompValue` to `salg:` encoder, `parse12`, `lower_rdf11`, `starsparql/` paths). They read as current.
- `docs/working/archive/sparql-layers-exploration.md` mentions `TrueFilter` in the archived salg context.
- No rdflib import at module level in `sparql/`, `starontology/manchester`, `graph/manchester` (grep). rdflib survives as optional input
  (`to_rdf.py` takes an rdflib graph to fill; `sqe/entailment.py` accepts an `ENTAILMENT.RDFS` constant as a string) and as a test oracle.
- `sqe/_memtree.py` is "memory tree" (an in-memory `TreeIndex` so a rewrite needs no store); it is not an algebra module.

## 3. `sqe:` mapped to the SPARQL 1.2 grammar

Legend: OK = same as the grammar's production or keyword; STYLE = names the right construct but the grammar's name is longer or
differs; (a) rdflib; (b) invented, no grammar counterpart; (c) modelling helper.

### Classes

| Term | Grammar production / construct | Verdict |
|---|---|---|
| `sqe:Query` | `Query` (also `QueryUnit`) | OK (typed on every root) |
| `sqe:SelectQuery`, `AskQuery`, `ConstructQuery`, `DescribeQuery` | `SelectQuery`, `AskQuery`, `ConstructQuery`, `DescribeQuery` | OK |
| `sqe:SubSelect` | `SubSelect` | OK |
| `sqe:TriplePattern` | no production: the spec's concept "triple pattern" (SPARQL section 5.1, SRL 4.1 "Triple pattern"); nearest productions `TriplesSameSubjectPath`, `TriplesBlock`, `TriplesTemplate` | OK as spec term, one node per triple (property lists `;` `,` are flattened) |
| `sqe:TripleTerm` | `TripleTerm` (and `ExprTripleTerm`, `TripleTermData`) | OK |
| `sqe:Optional` | `OptionalGraphPattern` | STYLE (keyword) |
| `sqe:Union` | `GroupOrUnionGraphPattern` | STYLE (keyword) |
| `sqe:Minus` | `MinusGraphPattern` | STYLE (keyword) |
| `sqe:Graph` | `GraphGraphPattern` | STYLE (keyword) |
| `sqe:Service` | `ServiceGraphPattern` | STYLE (keyword) |
| `sqe:Values` | `InlineData` in a pattern, `ValuesClause` trailing (same `VALUES DataBlock`) | STYLE |
| `sqe:Filter` | `Filter` | OK (also an rdflib algebra name; irrelevant, it is the grammar's) |
| `sqe:Bind` | `Bind` | OK |
| `sqe:Exists` (+ `negated`) | `ExistsFunc` / `NotExistsFunc` (BuiltInCall) | STYLE; one class with a flag where the grammar has two productions (c); it lives in `sqe:` though it is an expression |
| `sqe:Alias` | none: `( Expression AS Var )` inside `SelectClause` and `GroupCondition` | (b) unnamed in the grammar; keep |
| `sqe:OrderCondition` | `OrderCondition` | OK |
| `sqe:DatasetClause` | `DatasetClause` (`DefaultGraphClause`/`NamedGraphClause`, flag `sqe:named`) | OK |
| `sqe:UpdateRequest` | `UpdateUnit` / `Update` (spec text: "update request") | OK |
| `sqe:UpdateOperation` | `Update1` | STYLE (abstract superclass; the grammar's name is opaque) |
| `sqe:InsertData`, `DeleteData`, `DeleteWhere`, `Modify`, `Load`, `Clear`, `Drop`, `Create`, `Add`, `Move`, `Copy` | same names | OK |
| `sqe:QuadGraph` | `QuadsNotTriples` (`GRAPH VarOrIri { TriplesTemplate? }`) | STYLE |
| `sqe:GraphRef` | `GraphRef` | OK |
| `sqe:DefaultGraph`, `NamedGraphs`, `AllGraphs` | the keywords `DEFAULT`, `NAMED`, `ALL` of `GraphOrDefault` / `GraphRefAll` | (c) keyword stand-ins, fine |
| `sqe:PrefixBinding` | `PrefixDecl` | STYLE (not in `sqe-ontology.ttl`; used by shapes, to_rdf, to_text) |

### Properties (grammar fields)

All of these follow the grammar field or keyword, so none needs renaming: `where` (`WhereClause`/`GroupGraphPattern`), `projection`
(`SelectClause`), `selectAll` (`*`), `distinct`, `reduced`, `template` (`ConstructTemplate`), `orderBy` (`OrderClause`), `descending`
(`DESC`), `limit`, `offset`, `groupBy` (`GroupClause`), `having` (`HavingClause`), `values` (`ValuesClause`), `vars`/`rows`
(`InlineDataFull`), `undef` (`UNDEF`), `alternatives` (the `UNION` operands), `graph`, `service`, `silent`, `dataset`, `source`,
`named`, `describe`, `describeAll`, `version` (`VersionDecl`), `base` (`BaseDecl`), `operations`, `quads` (`Quads`/`QuadData`),
`with`, `delete` (`DeleteClause`), `insert` (`InsertClause`), `using` (`UsingClause`), `loadFrom`, `into`, `target`, `from`, `to`,
`graphIri`, `graphName`, `triples`, `negated`, `var`, `expr`, `subject`/`predicate`/`object`.
Not grammar names, all modelling helpers (c): `prologuePrefix`, `prefixLabel`, `namespace` (the `PrefixDecl` parts `PNAME_NS` and `IRIREF`).
The `rdf:List` wrapping of every ordered child is out of scope here (another agent).

## 4. `spexpr:` mapped to the grammar

| Term | Grammar | Origin and verdict |
|---|---|---|
| `Expression`, `Variable` (datatype of `Var`), `RelationalExpression`, `ConditionalOrExpression`, `ConditionalAndExpression`, `AdditiveExpression`, `MultiplicativeExpression` | same production names | OK (the parser's node names happen to equal the grammar's) |
| `ArithmeticExpression`, `ConditionalExpression`, `UnaryExpression` (superclass) | none (helper superclasses); `UnaryExpression` exists as a production but means "prefix `!`/`+`/`-` or a `PrimaryExpression`", which the class does not | (c); `UnaryExpression` reuses a spec name for a narrower thing |
| `UnaryNot`, `UnaryMinus`, `UnaryPlus` | the three prefix alternatives of `UnaryExpression` (`!`, `-`, `+`) | (a) rdflib parser names; STYLE |
| `Builtin_STR` ... `Builtin_isTRIPLE` (62 classes) | no per-function production: all inside `BuiltInCall`; the grammar's name is the keyword (`STR`, `isIRI`, `sameTerm`, `LANGDIR`, `STRLANGDIR`, `hasLANG`) | (a) the `Builtin_` prefix is rdflib's `CompValue` name; STYLE |
| `Builtin_REGEX`, `Builtin_SUBSTR`, `Builtin_REPLACE` (+ `RegexExpression` etc.) | `RegexExpression`, `SubstringExpression`, `StrReplaceExpression` | helper family classes carry names (c); the grammar names are close but not equal (`SubstrExpression` vs `SubstringExpression`, `ReplaceExpression` vs `StrReplaceExpression`) |
| `Builtin_EXISTS`, `Builtin_NOTEXISTS`, `ExistsExpression`, `spexpr:graph` | `ExistsFunc`, `NotExistsFunc` | (a) dead: the encoder writes `sqe:Exists` instead; the parser node kinds still carry the `Builtin_` names internally; the shape for `spexpr:graph` appears to be dead (see the syntax-tree plan note) |
| `Function`, `FunctionExpression` | `FunctionCall` (`iri ArgList`) | (a) rdflib's `Function`; two classes where one suffices |
| `OneArgExpression`, `TwoArgExpression`, `ThreeArgExpression`, `ZeroArgExpression`, `OptionalOneArgExpression`, `VariadicArgExpression`, `StrLangDirExpression` | none (arity families) | (c) generated from rdflib's key shapes; used only to drive shapes (`expr_families.py`) |
| `arg`, `arg1`, `arg2`, `arg3` | the unnamed positional `Expression`s of `BuiltInCall`; spec section 17.4 names the parameters per function (`text`, `pattern`, `flags` ...) | (a) rdflib `CompValue` keys |
| `expr`, `op`, `other` | chain shape of `AdditiveExpression ::= MultiplicativeExpression ( '+' ... )*` | (a)/(c) rdflib's chain shape; the grammar has no field names |
| `text`, `pattern`, `flags`, `replacement`, `start`, `length`, `lex`, `lang`, `direction`, `separator` | section 17.4 parameter names / `SEPARATOR` | OK (not re-checked one by one against the 17.4 text) |
| `Aggregate`, `Aggregate_Count/Sum/Min/Max/Avg/Sample/GroupConcat` | `Aggregate` (alternatives `COUNT`, `SUM`, `MIN`, `MAX`, `AVG`, `SAMPLE`, `GROUP_CONCAT`) | (a) rdflib parser names `Aggregate_Count`; STYLE |
| `Aggregate` `spexpr:vars` | the `Expression` or `*` after `COUNT(`, so one expression, not variables | WRONG CONCEPT (rdflib's key name; a single expression or the `*` marker) |
| `distinct` | `DISTINCT` | OK |
| `Path`, `SequencePath`, `AlternativePath`, `InvPath`, `MulPath`, `NegatedPath` | `Path`, `PathSequence`, `PathAlternative`, `PathEltOrInverse` (`^`), `PathElt` + `PathMod`, `PathNegatedPropertySet` | (a) the five names are the `rdflib.paths` class names; STYLE (right concept, other name) |
| `args`, `arg`, `path`, `mod` | operands of the path productions; `PathMod` | `mod` OK; `args` and `path` fine (c) |
| `PlainString` (datatype) | none | (c) encoding helper (a bare string that must not equal an `xsd:string`) |
| `TrueFilter` | none: rdflib algebra's stand-in for an OPTIONAL with no filter | (a) pure algebra, dead: grep finds it only in the ontology (and one archived note); delete |

## 5. `srl:` mapped to the SPARQL 1.2 Rules draft

`_srl_ast.py` states its field names are the draft's section 4.1 names. Checked against the fetched section 4.1 (elements and the
"Component Notation" table):

| Term | Draft section 4.1 / grammar | Verdict |
|---|---|---|
| `srl:RuleSet`, `Rule`, `Data` | "Rule set", "Rule", "Data block" (productions `RuleSet`, `Rule`, `Data`) | OK |
| `srl:TriplePattern` | "Triple pattern" and "Triple template" (one class for both) | OK, deliberate merge |
| `srl:FilterElement`, `AssignmentElement`, `NegationElement`, `GroupElement` | "Filter element", "Assignment element", "Negation element", "Group element" (productions `Filter`, `Assignment`, `Negation`, `GroupAggregate`) | OK against section 4.1 (abstract syntax names, not the grammar's) |
| `srl:Aggregation` | "Aggregation assignment" (production `AggregationAssignment`) | STYLE |
| `srl:BodyElement`, `GroupBodyElement`, `NegationBodyElement` | the unions allowed by `BodyNotTriples`, `GroupPatternNotTriples`, `NegationPatternNotTriples` plus triples | (c) classes for shape dispatch |
| `rules`, `data`, `imports`, `head`, `body`, `id`, `inner`, `keys`, `pattern`, `aggregations`, `expr`, `argument`, `distinct` | `ruleset.rules/data/imports`, `rule.head/body/id`, `negation.inner`, `group.keys/pattern/aggregations`, `filter.expr`, `assign.expr`, `aggfunc.argument/distinct` | OK |
| `srl:var` | `assign.var` and `aggregation.variable` | OK on assign; STYLE on aggregation |
| `srl:function` | `aggfunc.name` (the draft nests `aggfunc` under `aggregation.function`) | STYLE, flattened |
| `srl:ruleEvaldata`, `srl:negationEvaldata` (and the Python field `evaldata`) | `rule.evalground`, `negation.evalground` (renamed in the draft of 2026-11-19; keyword `WHERE GROUND`, `NOT GROUND`) | DRIFT: the old term of the same concept; deliberate, recorded in `docs/working/spec-delta-2026-11-23.md` and guide 06.04; "no deprecation aliases" applies if renamed |
| `srl:triples` (Data) | "Data block" triples | OK |

Note: SRL has no `TRANSITIVE` anywhere in the vendored production table or in `parse_srl.py` (grep): nothing to represent.

## 6. `manch:` mapped to the OWL 2 Manchester Syntax Note

The classes are named after keywords or per-frame clause keywords, the Note's productions where they exist.

| Term | Note production / construct | Verdict |
|---|---|---|
| `Document` | `ontologyDocument` | STYLE |
| `OntologyHeader` | the head of `ontology` (`Ontology:` iri versionIRI, `import`, `annotations`) | (c) split of one production |
| `PrefixDecl`, `prefixLabel`, `prefixIri` | `prefixDeclaration` (`prefixName`, `fullIRI`) | STYLE |
| `Frame`, `ClassFrame`, `ObjectPropertyFrame`, `DataPropertyFrame`, `AnnotationPropertyFrame`, `IndividualFrame`, `DatatypeFrame` | `frame`, `classFrame`, ... `datatypeFrame` | OK |
| `Clause` and the 45 `*Clause` classes (`ClassSubClassOfClause`, `ObjPropDomainClause`, ...) | the keyword alternatives inside each frame (`'SubClassOf:' descriptionAnnotatedList`); the Note has no named production per clause | (c), named frame + keyword; `ObjProp`/`DataProp` abbreviations are StarLayer's |
| `ClauseItem`, `FactItem` | one item of an `<NT>AnnotatedList` (`annotations` + value); `fact` | (c) / OK for `FactItem` (`fact`) |
| `MiscAxiom` and `Misc*Axiom` | `misc` alternatives (`EquivalentClasses:` ...) | OK in spirit |
| `ClassExpression` | `description` (with `conjunction`, `primary`, `atomic`) | STYLE: the Note says "description"; OWL-API/functional syntax say ClassExpression |
| `And`, `Or`, `Not` | `conjunction` (`and`), `description` (`or`), `primary` (`not`) | keyword-named; fine |
| `Some`, `Only`, `Value`, `SelfR`, `Min`, `Max`, `Exact`, `DSome`, `DOnly`, `DMin`, `DMax`, `DExact` | the labelled alternatives of `restriction`: objectsome, objectonly, objectvalue, objectSelf, objectmin/max/exactly, datasome, dataonly, datamin/max/exactly (vendored as `LABELLED_ALTERNATIVES`) | keyword-named. `SelfR` is a Python-tag artefact for `Self`. `Value` stands for both `objectvalue` and `datavalue` |
| `OneOf`, `DOneOf` | `atomic` `{ individualList }`; `dataAtomic` `{ literalList }` | keyword/shape-named |
| `DataRange`, `DAnd`, `DOr`, `DNot`, `DRestriction`, `FacetRestriction` | `dataRange`, `dataConjunction`, `dataRange` `or`, `dataPrimary` `not`, `datatypeRestriction`, `facet restrictionValue` | STYLE (`D` prefix is StarLayer's) |
| `PropertyExpression`, `Inverse` | `objectPropertyExpression` / `dataPropertyExpression`; `inverseObjectProperty` | OK in spirit |
| `AnnotationAssertion` | `annotation` (`annotationPropertyIRI annotationTarget`) | STYLE ("AnnotationAssertion" is OWL functional-syntax vocabulary, and the object is only an annotation, not an assertion) |
| properties `onProperty`, `filler`, `cardinality`, `operand(s)`, `individuals`, `literals`, `facets`, `facetPredicate`, `facetValue`, `onDatatype`, `annotations`, `items`, `value`, `subject`, `clauses`, `frames`, `misc`, `header`, `ontologyIri`, `versionIri`, `imports`, `prefixes`, `negative`, `property`, `annotationProperty`, `annotationValue` | `objectPropertyExpression` etc., `primary`, `nonNegativeInteger`, `facet`/`restrictionValue`, `annotationTarget`, `ontologyIRI`, `versionIRI`, `import` | mostly OWL/RDF-mapping words (`onProperty`, `onDatatype`, `cardinality` are `owl:` terms), not Manchester production names; (c) |
| `manch:reversed` | NOT IN THE NOTE: the vendored `classFrame`, `objectPropertyFrame`, `dataPropertyFrame` have no `SuperClassOf:` / `SuperPropertyOf:` (grep of the vendored productions finds no `Super`) | (b) StarLayer extension accepted from the OWL API, carried by a flag |

## 7. What is not representable (text to tree to text)

Quick probes run 2026-11-25 (scratchpad, not committed): 16 SPARQL queries, 2 update requests, 7 rule sets, 2 Manchester documents.
Every SPARQL probe parsed, rendered, and re-parsed to the same text (fixpoint). No query-form or pattern construct was refused.

SPARQL query and update (`sqe:`): the repo's own record agrees. `sqe_known_gaps.txt` lists 3 W3C fixtures, none an sqe gap (the project parser
also rejects them, or the suite is wrong). Probed and fine: `VERSION`, `SERVICE SILENT`, `<<( )>>` triple terms, `{| |}` annotations,
reifiers `<< >> ~`, `a/b|^c|!(d|^e)` paths, sub-select, aggregates with GROUP BY/HAVING/ORDER BY, FILTER (NOT) EXISTS, VALUES with UNDEF
(in a pattern and trailing), GRAPH, MINUS, OPTIONAL, UNION, BIND, `LANGDIR`/`isTRIPLE`, `"a"@en--ltr`, DESCRIBE, CONSTRUCT WHERE, INSERT DATA with
GRAPH, `WITH/DELETE/INSERT/USING NAMED/WHERE`, CLEAR, COPY, LOAD INTO GRAPH. What round-trips only semantically (a tree stores the meaning,
not the spelling):

- Reifier/annotation shorthand, `[ ]`, `( )` collections are stored expanded to `rdf:reifies`/`rdf:first`/`rdf:rest` triples with generated
  blank nodes, and render expanded. There is no `sqe:` term for the productions `Reifier`, `AnnotationBlock`, `Collection`,
  `BlankNodePropertyList`, or for `;` and `,` lists (`TriplesSameSubject` grouping): by design, listed as future work (`sqe:group`,
  `sqe:objectSpelling` etc. in `docs/design/future_enhancements.md`).
- Comments and blank lines are dropped; numbers render as `"3"^^xsd:integer`; `(:p)*` renders `:p*`; `a/b|c` is regrouped `(a/b)|c`.
- Not representable by design: nothing in the grammar is refused, but the concrete syntax (spelling, layout, comments) is not kept.

SRL (`srl:`): grammar `RULE`, `DATA`, `NOT [GROUND]`, `SET`, `GROUP BY ... { } [ ?v := AGG ]`, `WHERE GROUND`, `FILTER`, triple terms
round-trip in the probes. Observations: `PREFIX`, `BASE` and `VERSION` are not in the tree or the rendered text (prefixes live only in the Python
`RuleSet.prefixes`, and the text carries full IRIs); a resolved `IMPORTS` is inlined (probe: `imports == []`, 2 rules, no `IMPORTS` line
in the text), so the declaration is lost once loaded; property paths are limited to `/` and `^` and expanded (`parse_srl._expand_path`,
as the draft requires); reifier and annotation shorthand are expanded as in sqe. `TRANSITIVE`: absent from the draft's productions.

Manchester (`manch:`): the 2026-11 conformance work closed the gap list in `tests/.../manchester_conformance/known_failures.py`
(`DIFFERENTIAL_FAILURES` is empty); the one declared exclusion in `manchester_syntax_gap_analysis.md` is SWRL `Rule:`, which is not in the W3C
Note's grammar at all (no `Rule` production in the vendored table) and is refused with a `ManchesterSyntaxError` (probe). Probe notes: a
document with `Prefix:`, versioned `Ontology:`, `Import:`, ontology and axiom annotations, `HasKey:`, `SubPropertyChain:`, datatype
restrictions, negative facts, `DisjointClasses:` and `SameIndividual:` parsed and rendered; the output spells names with full IRIs
(`<http://www.w3.org/2000/01/rdf-schema#label>`), not the written abbreviated forms, and comments are dropped.

## 8. Proposal

### Naming rules

- `sqe:` and `spexpr:` (SPARQL): class = the SPARQL 1.2 Query/Update *grammar* production (or the keyword where the grammar has only an
  alternative inside a production, e.g. `STR` inside `BuiltInCall`); property = the grammar's field/keyword (`WhereClause` is `where`,
  `DESC` is `descending`). Do not use SPARQL's "abstract syntax": in SPARQL that is the section 18 algebra (BGP, Join, LeftJoin ...),
  exactly the layer to avoid.
- `srl:`: class = the draft's section 4.1 abstract-syntax element ("Filter element" is `FilterElement`), property = its component
  notation (`rule.head` is `head`). This is already the rule in `_srl_ast.py`; SRL's abstract syntax is element-level and close to its
  grammar, so no change of rule is needed.
- `manch:`: class = the Note's production in CamelCase, the Note's keyword for alternatives of `restriction`/`frame`/`misc` clauses;
  property = the production the value comes from.
- Modelling helpers (list wrappers, arity families, `PlainString`, `reversed`, `ClauseItem`) stay, flagged as (c) in the ontology
  comment, with no grammar name claimed.

### Renames the rule implies, and costs

Costs are occurrence counts: ttl = the four vocabulary folders (ontology + shapes); src = Python kind strings/constants in the package;
qlib = `tools/kg/codekg/curated/query-library.ttl`; guides = `docs/guides/*.ipynb`; docs = other `docs/`; wb = `../graph-workbench`
(src, tests, docs): zero for every `sqe:`/`spexpr:`/`srl:`/`manch:` term and for the IRIs (grep). About 64 test files call the public
functions, which do not change; only a test that names a class or kind string in text is affected (tests column).

#### Names that point at the wrong or a stale concept (do first)

| Current | Grammar / spec name | ttl | src | tests | qlib | guides | docs |
|---|---|---|---|---|---|---|---|
| `spexpr:vars` (on `Aggregate`) | the `Expression` (or `*`) after `COUNT(`: `expr` plus a star marker | 6 | 18 | 0 | 1 | 0 | 0 |
| `spexpr:TrueFilter` | none: delete | 1 | 1 | 0 | 0 | 0 | 1 |
| `spexpr:ExistsExpression`, `Builtin_EXISTS`, `Builtin_NOTEXISTS`, `spexpr:graph` | `ExistsFunc` / `NotExistsFunc` (already `sqe:Exists`); delete the dead copy | 3+2+... | 21 | 1 | 0 | 0 | 2 |
| `srl:ruleEvaldata`, `srl:negationEvaldata`, Python `evaldata` | `evalground` (draft of 2026-11-19; `rule.evalground`, `negation.evalground`) | 6 | 29 | 19 | 0 | 6 | 5 |
| `manch:reversed` | none: `SuperClassOf:`/`SuperPropertyOf:` are not in the Note | 6 | 1 | 6 | 0 | 1 | 1 |
| stale comments naming `salg:` (section 2) | rewrite | 3 | ~30 lines | 0 | 0 | 0 | 2 design docs |

`reversed` should stay (the OWL API accepts the keywords and the semantics differ), but be labelled an extension beyond the Note.

#### Names that merely differ in style (rename for the rule, no semantic fix)

| Current | Grammar name | ttl | src | tests | qlib | guides | docs |
|---|---|---|---|---|---|---|---|
| `spexpr:Builtin_X` (62) | `X`, the `BuiltInCall` keyword (`spexpr:STR`, `spexpr:isIRI`, `spexpr:sameTerm`) | 64 | 139 lines | 3 | 61 | 0 | 14 |
| `spexpr:Aggregate_Count` ... (7) | `COUNT` ... `GROUP_CONCAT` alternatives of `Aggregate` | 14 | 18 | 0 | 1 | 0 | 1 |
| `spexpr:SequencePath`, `AlternativePath`, `InvPath`, `MulPath`, `NegatedPath` | `PathSequence`, `PathAlternative`, `PathEltOrInverse`, `PathElt` (with `PathMod`), `PathNegatedPropertySet` | 16 | 67 | 5 | 2 | 0 | 4 |
| `spexpr:UnaryNot/UnaryMinus/UnaryPlus` | alternatives of `UnaryExpression` (keep, or name `Not`/`Minus`/`Plus`) | 3 | 16 | 2 | 10 | 0 | 0 |
| `spexpr:Function`, `FunctionExpression` | `FunctionCall` | 7 | 13 | 2 | 0 | 0 | 4 |
| `spexpr:SubstrExpression`, `ReplaceExpression` | `SubstringExpression`, `StrReplaceExpression` | 4 | few | 0 | 0 | 0 | 0 |
| `sqe:Optional`, `Union`, `Minus`, `Graph`, `Service`, `Values` | `OptionalGraphPattern`, `GroupOrUnionGraphPattern`, `MinusGraphPattern`, `GraphGraphPattern`, `ServiceGraphPattern`, `InlineData` | 5, 6, 5, 12, 13, 16 | 8, 9, 9, 12, 10, 11 | 1, 1, 0, 0, 1, 0 | 42, 1, 0, 0, 0, 10 | 0, 0, 0, 1, 1, 1 | 1, 0, 0, 0, 3, 0 |
| `sqe:QuadGraph` | `QuadsNotTriples` | 11 | 7 | 1 | 0 | 0 | 1 |
| `sqe:PrefixBinding` (+ `prologuePrefix`, `prefixLabel`, `namespace`) | `PrefixDecl` | 9 | ~10 | 1 | 72 | 11 | 2 |
| `sqe:UpdateOperation` | `Update1` | 13 | 0 | 0 | 0 | 0 | 1 |
| `srl:Aggregation` | `AggregationAssignment` (spec element "Aggregation assignment") | 13 | 0 | 0 | 0 | 0 | 1 |
| `manch:Document` | `ontologyDocument` | 6 | 9 | 10 | 0 | 2 | 3 |
| `manch:ClassExpression` | `description` | 23 | 0 | 25 | 0 | 1 | 0 |
| `manch:AnnotationAssertion` | `annotation` | 5 | 0 | 5 | 0 | 0 | 0 |
| `manch:SelfR` | `Self` | 2 | 0 | 2 | 0 | 0 | 0 |

All the SPARQL-side renames are one place in `sqe/vocab.py` plus the Node kind strings in `parse_sparql.py` plus the `.ttl` files;
`query-library.ttl` holds the big count (`sqe:Optional` 42, `PrefixBinding` 72, `sqe:TriplePattern` 142), but it is a regenerated curated
file, so the real cost is the regeneration, not the edit count. The `Builtin_` rename is the largest by lines; every one is mechanical
and the kind names are shared by `expr_families.py`, `expr_validation.py`, `expr_text.py` and the parser.

### Leave alone, and why

- All `sqe:` update classes and query forms, `Filter`, `Bind`, `OrderCondition`, `DatasetClause`, `SubSelect`, `TripleTerm`: already grammar names.
- `sqe:TriplePattern` and `srl:TriplePattern`: the spec's own concept in both languages (no production); it is the shared term.
- `sqe:Alias`: the grammar has no name for `( Expression AS Var )`; any name is invented, so keep and flag (b).
- The `srl:*Element` classes: they follow section 4.1 as `_srl_ast.py` promises; renaming to the grammar's `Negation`/`Assignment`/`GroupAggregate` would
  move away from the component notation (`negation.inner`) the properties use.
- The `spexpr:*ArgExpression` families, `ConditionalExpression`, `ArithmeticExpression`, `PlainString`, `ClauseItem`, `Clause*`, `BodyElement` unions:
  helpers (c); no grammar name exists, claim none.
- `manch:And/Or/Not/Some/Only/...`: keywords, and the Note itself has only labelled alternatives.
- Properties named after rdflib keys that carry a correct concept (`op`, `other`, `arg`, `arg1`..): renaming them has high cost (qlib 24+14+42+19+19)
  for a gain only in provenance; revisit only if the three languages' expression vocabulary is rebuilt.

## 9. Unifying the shared parts

What the specs themselves share (same production name in SPARQL Query/Update and in SPARQL RL, from the vendored tables): `Prologue`,
`BaseDecl`, `PrefixDecl`, `VersionDecl`, `Filter`, `Constraint`, the whole `Expression` family (`ConditionalOrExpression` ... `PrimaryExpression`,
`BuiltInCall` minus the excluded functions, `FunctionCall`, `ArgList`), `Path`/`PathSequence`/`PathEltOrInverse`/`PathElt` (SRL restricts the
operators), `Var`, `VarOrIri`, `iri`, `TripleTerm` (`TripleTermSubject`/`Object`), `ReifiedTriple`, `Reifier`, `Annotation`/`AnnotationBlock`, and the
triple-block productions (`PropertyListNotEmpty` ...). The concept "triple pattern" is shared in the prose.

What the specs do NOT share (different production names), so a unified name would contradict one spec:

- `Bind` (SPARQL) against `Assignment` (`SET ( Var := Expression )`, SRL): not the same construct, keep two classes (`sqe:Bind`, `srl:AssignmentElement`)
  with the same two properties `var`/`expr`.
- `ExistsFunc`/`NotExistsFunc`/`MinusGraphPattern` against `Negation` (`NOT [GROUND] { }`): different semantics; keep separate.
- `GroupClause`/`Aggregate` (expression-level, SPARQL) against `GroupAggregate`/`AggregationAssignment` (a body element, SRL): keep separate.
- `QuadData`/`InsertData` against SRL `Data`: keep separate.

So a shared core is justified for: `TriplePattern` (and its `subject`/`predicate`/`object`), `Filter` (SPARQL `Filter` and SRL `Filter` are one
production), `Variable`, the `spexpr:` expression and path vocabulary, `TripleTerm` and the prologue terms. Today `srl:` borrows `sqe:TripleTerm`
and `sqe:Exists` lives in `sqe:` though it is an expression; both belong in the shared namespace if one is built. Renaming `spexpr:` to grammar
names first makes that shared namespace spec-true for both languages, because the expression and path productions are the ones the specs
share; the order "rename `spexpr:` (section 8), then merge `TriplePattern`/`Filter`" avoids doing the shared part twice. The
`srl:FilterElement` against `sqe:Filter` mismatch is the only name that would have to change on the SRL side (to `Filter`, the production name),
which conflicts with the section-4.1 rule above; decide that when the merge is decided.

## 10. Could not verify

- The SPARQL 1.2 Query and Update pages (439 943 characters) were not read beyond their first 100 000; production names come from the repo's
  vendored table (the draft of 2026-11-01), not from a fresh fetch. The SRL page: section 4.1 only (first 100 000 characters of 200 881).
- Whether the section 17.4 parameter names match `text`, `pattern`, `flags`, `start`, `length`, `lex`, `lang`, `direction`, `separator` one by one.
- That `rdflib.paths` and the rdflib parser are the origin of each name is from inspecting rdflib 7.6.0's source text (`TrueFilter` only in the
  algebra, `Aggregate_Count`, `Builtin_STR`, `UnaryNot` in the parser, path class names via `algebra`), not from the first commit's intent.
- Counts are CURIE and kind-string greps; Python code that builds names dynamically (`"Aggregate_" + ...`, `kind.capitalize()`) and test code
  that checks names through generated shape names are not counted, so src and tests are lower bounds for the `Builtin_`, `Aggregate_` and update renames.
- The three conformance suites (`--sqe-coverage`, `--srl-conformance`, Manchester) were not run (minutes each); statements about gaps rest
  on their known-failure registries and READMEs plus the probes above.
- Whether the shape for `spexpr:graph`/`ExistsExpression` is dead: from the plan note and a grep, not traced through a test.
- The workbench was grepped for the CURIEs, the namespace IRIs and `evaldata`/`evalground`: no hits; JS bundles and non-listed file types were not searched.
