# SPARQL to sqe tree vocabulary: proposed end state (2026-11-25)

Status: untracked working note for John to review; nothing in code, tests, notebooks or the workbench was changed. Not for commit.

## Summary

1. Scope: every `sqe:` and shared `spexpr:` class and property that SPARQL 1.2 query/update uses, in grammar order. Column 1 is what the user types (with the SPARQL 1.2 production in parentheses, names from the repo's vendored production table); column 2 the proposed tree term; column 3 what it represents; column 4 notes.
2. Naming rule: class = the production name where the tree node is a whole production, else the keyword as typed (`STR`, `isIRI`, `COUNT`); property = the grammar field or keyword (`where`, `limit`, `separator`). No SPARQL algebra names (BGP, Join, LeftJoin, Extend...).
3. Where the grammar has no name (variable datatype, PlainString, arity families, list cells, Alias, sqe:Query marker) the term is a modelling helper; its row says what it stands for.
4. Reified triples, annotations, collections, `[ ]`, `a`, `;`/`,` lists and prefixed names are stored expanded and have no tree term (rows say so).
5. Every ordered list is marked `order encoding: see tree-encoding decision`; I did not decide it.
6. Sources: the ontology and shapes ttl, `parse_sparql.py`, the vendored production table, and probes: 621 of the 703 `.rq`/`.ru` files under `tests/sparql/w3c_sparql11` and `w3c_sparql12` parse (the 82 that fail are the negative syntax tests). "seen Nx" in notes is the number of tree nodes/properties those 621 queries produced under the term.
7. Tables use the keyword forms for patterns and built-ins (`sqe:Optional`, `spexpr:STR`), which is what the user types; the production-name alternative is Q1/Q2.
8. Removed from the end state: see section 13.
9. Coverage: section 14; nothing in the ontology files is unplaced except the dead terms listed in section 13.
10. Open naming questions: below, each with a recommendation.

## Open naming questions

1. Pattern classes: keyword (`sqe:Optional`, `Union`, `Minus`, `Graph`, `Service`, `Values`) or production name (`OptionalGraphPattern`, `GroupOrUnionGraphPattern`, `MinusGraphPattern`, `GraphGraphPattern`, `ServiceGraphPattern`, `InlineData`)? Recommend keyword: it is what the user types and the production names are long.
2. Built-in classes: as typed (`spexpr:STR`, `spexpr:isIRI`, `spexpr:sameTerm`, lower-case start where SPARQL has it) or a prefix such as `Builtin_STR`? Recommend as typed.
3. Aggregate classes: `spexpr:COUNT` ... `spexpr:GROUP_CONCAT` as typed? Recommend yes.
4. Aggregate operand: rename `spexpr:vars` to `spexpr:expr` (it is one expression or the `*` marker), and make `spexpr:distinct` boolean true/absent (today the string DISTINCT or `rdf:nil`). Recommend yes to both.
5. EXISTS: one class with a `negated` flag, or two classes `sqe:Exists` and `sqe:NotExists` (grammar: ExistsFunc, NotExistsFunc)? Recommend two classes; also decide whether it moves to `spexpr:` (it is an expression); recommend leave in `sqe:` until the shared-namespace decision.
6. Paths: `PathSequence`, `PathAlternative`, `PathNegatedPropertySet` follow productions; inverse (`PathInverse`, alternative `PathEltOrInverse`) and repeat (`PathElt`) are judgment calls. Recommend as proposed.
7. Prologue: `sqe:PrefixDecl` (production) instead of `PrefixBinding`, root link `sqe:prefixDecl`. Recommend yes.
8. Operand properties: keep `expr`/`op`/`other` for chains and `arg`/`arg1..3` for built-ins (the latter follow spec 17.4 prototype names, not re-fetched); use one `spexpr:args` for every ordered argument list (FunctionCall, CONCAT, COALESCE, path members). Recommend yes.
9. `sqe:Alias` for `( expr AS ?v )`: the grammar has no name. Recommend keep.
10. A bare `{ ... }` group is stored as a one-alternative `sqe:Union`. Recommend leave (semantically equal), no `sqe:Group`.
11. Shared namespace for terms both SPARQL and SRL use (TripleTerm, Filter, Exists, Variable): decide after the encoding decision; recommend defer.
12. `sqe:UpdateOperation` (helper superclass; grammar `Update1`): recommend keep.
13. `sqe:QuadGraph` for `GRAPH g { }` inside quads (grammar `QuadsNotTriples`; `sqe:Graph` is taken by the pattern): recommend keep.
14. Unary operators `UnaryNot`, `UnaryMinus`, `UnaryPlus`: names I believe come from the spec's operator table (not re-fetched). Recommend keep.
15. `sqe:undef` (VALUES `UNDEF`) is a bare IRI constant, not declared in the ontology; recommend declare it as an individual of the ontology.


## 1. Prologue

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `BASE <iri>` (BaseDecl) | `sqe:base` | the base IRI declaration, on the root; relative IRIs in the tree are already resolved against it | the declaration is kept only so the text can be re-rendered; seen 7x |
| `PREFIX p: <iri>` (PrefixDecl) | `sqe:PrefixDecl` (class) | one prefix declaration (label + namespace IRI); exists so rendering reuses the author's prefixes; prefixed names themselves are stored expanded | Q7: production name; unchanged would be PrefixBinding; seen 635x |
| (the link root -> declaration) | `sqe:prefixDecl` | property from a query/update root or operation to its PrefixDecl nodes | modelling helper; several per root, no order needed; seen 635x |
| `p:` (PNAME_NS) | `sqe:prefixLabel` | the label before the colon, a PlainString (empty for `:`) | helper name; the production is PNAME_NS; seen 635x |
| `<iri>` after the label (IRIREF) | `sqe:namespace` | the namespace IRI of the declaration | helper name; seen 635x |
| `VERSION "1.2"` (VersionDecl) | `sqe:version` | the declared version, a plain string literal; may repeat | seen 7x |
| (prefixed names `p:x`, PrefixedName) | no tree term | a prefixed name is stored as its full IRI | by design; only PrefixDecl remembers the spelling |

## 2. Query forms

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| (the whole query) (Query, QueryUnit) | `sqe:Query` | root marker typed on every query root of any form, so one pattern `?q a sqe:Query` finds all queries | grammar production; also typed with the form class; seen 475x |
| `SELECT ...` (SelectQuery) | `sqe:SelectQuery` | a SELECT query root | unchanged; seen 472x |
| `ASK ...` (AskQuery) | `sqe:AskQuery` | an ASK query root | unchanged; seen 21x |
| `CONSTRUCT ...` (ConstructQuery) | `sqe:ConstructQuery` | a CONSTRUCT query root; `CONSTRUCT WHERE` is stored expanded as template + where | unchanged; seen 43x |
| `DESCRIBE ...` (DescribeQuery) | `sqe:DescribeQuery` | a DESCRIBE query root | unchanged; never seen in test queries |
| `{ SELECT ... }` (SubSelect) | `sqe:SubSelect` | a SELECT nested in a pattern list; the node is also typed sqe:SelectQuery but is not a sqe:Query | unchanged; seen 61x |
| `SELECT ?x (expr AS ?y)` (SelectClause) | `sqe:projection` | the projected items (variables and Alias nodes) | order encoding: see tree-encoding decision; seen 296x |
| `( expr AS ?v )` (inside SelectClause, GroupCondition; no production name) | `sqe:Alias` | one `expr AS ?var` item in a projection or GROUP BY | Q9: grammar has no name; any name is invented; seen 207x |
| `SELECT *` | `sqe:selectAll` | boolean true; replaces sqe:projection | seen 176x |
| `DISTINCT` | `sqe:distinct` | boolean true on the SELECT | seen 91x |
| `REDUCED` | `sqe:reduced` | boolean true on the SELECT | never seen in test queries |
| `CONSTRUCT { ... }` (ConstructTemplate) | `sqe:template` | the template triple patterns | order encoding: see tree-encoding decision; seen 43x |
| `DESCRIBE <a> ?x` (VarOrIri+) | `sqe:describe` | the DESCRIBE targets | order encoding: see tree-encoding decision; never seen in test queries |
| `DESCRIBE *` | `sqe:describeAll` | boolean true; replaces sqe:describe | never seen in test queries |

## 3. Dataset clauses

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `FROM <g>` / `FROM NAMED <g>` (DatasetClause; DefaultGraphClause, NamedGraphClause) | `sqe:DatasetClause` | one FROM or FROM NAMED clause; also used for USING / USING NAMED | one class for both alternatives, told apart by sqe:named; seen 18x |
| (the list of clauses) | `sqe:dataset` | the dataset clauses of a query, in source order | order encoding: see tree-encoding decision; seen 5x |
| `<g>` (SourceSelector) | `sqe:source` | the graph IRI of the clause | seen 18x |
| `NAMED` | `sqe:named` | boolean true for FROM NAMED / USING NAMED | seen 5x |

## 4. Graph patterns

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `WHERE { ... }` (WhereClause, GroupGraphPattern) | `sqe:where` | the flat ordered list of sibling pattern elements of a group | order encoding: see tree-encoding decision; the tree flattens GroupGraphPatternSub; also used by Optional, Minus, Graph, Service, Exists, Modify; seen 725x |
| `{ ... }` alone (GroupGraphPattern) | no tree term | a bare group is stored as a one-alternative Union (probe: `{ ?s a ?o }` gives sqe:Union with one list) | Q10 |
| `{ ... } UNION { ... }` (GroupOrUnionGraphPattern) | `sqe:Union` | a union of groups | Q1: production name is long; keyword kept; seen 22x |
| (the UNION operands) | `sqe:alternatives` | the groups joined by UNION, each a pattern list | order encoding: see tree-encoding decision; seen 22x |
| `OPTIONAL { ... }` (OptionalGraphPattern) | `sqe:Optional` | an optional group | Q1; seen 18x |
| `MINUS { ... }` (MinusGraphPattern) | `sqe:Minus` | a MINUS group | Q1; seen 14x |
| `GRAPH ?g { ... }` (GraphGraphPattern) | `sqe:Graph` | a GRAPH group | Q1; seen 52x |
| (the graph name) | `sqe:graph` | the graph IRI or variable of the group | seen 52x |
| `SERVICE [SILENT] <e> { ... }` (ServiceGraphPattern) | `sqe:Service` | a federated group | Q1; seen 13x |
| (the endpoint) | `sqe:service` | the endpoint IRI or variable | seen 13x |
| `SILENT` | `sqe:silent` | boolean true; on Service and on Load, Clear, Drop, Create, Add, Move, Copy | seen 24x |
| `FILTER ( ... )` (Filter, Constraint) | `sqe:Filter` | a filter element | unchanged; seen 86x |
| `BIND ( expr AS ?v )` (Bind) | `sqe:Bind` | a bind element | unchanged; seen 63x |
| (the filter/bind/alias/order expression) | `sqe:expr` | the expression of Filter, Bind, Alias, OrderCondition | shared property, no domain; seen 546x |
| (the bound variable) | `sqe:var` | the variable of Bind and Alias | seen 270x |
| `EXISTS { ... }` (ExistsFunc) | `sqe:Exists` | an EXISTS test in an expression | Q5; seen 28x |
| `NOT EXISTS { ... }` (NotExistsFunc) | `sqe:NotExists` | a NOT EXISTS test | Q5: today the class Exists plus sqe:negated true; seen 15x |
| `VALUES ...` in a pattern (InlineData) | `sqe:Values` | an inline data block; see section 8 | Q1; seen 60x |

## 5. Triples and property paths

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `?s ?p ?o .` (TriplesSameSubjectPath; no class production) | `sqe:TriplePattern` | one triple pattern (spec concept 'triple pattern'); `;` and `,` lists are flattened, one node per triple | seen 2080x |
| subject (VarOrTerm) | `sqe:subject` |  | shared with TripleTerm, no domain; seen 2427x |
| predicate / verb (VerbPath, VerbSimple) | `sqe:predicate` | an IRI, a variable or a path node | seen 2427x |
| object (ObjectPath) | `sqe:object` |  | seen 2427x |
| `a` | no tree term | stored as the IRI rdf:type (probe) | the keyword is not kept |
| `<<( s p o )>>` (TripleTerm, TripleTermData, ExprTripleTerm), `TRIPLE(s,p,o)` | `sqe:TripleTerm` | an RDF 1.2 triple term, as a pattern object or inside an expression; a subclass of spexpr:Expression | `TRIPLE(...)` call is stored as the same class (probe), the function call is not distinguished; seen 347x |
| `<< s p o ~ r >>` (ReifiedTriple, Reifier) | no tree term | stored expanded: a TriplePattern `?r rdf:reifies <TripleTerm>` | by design (future work in future_enhancements.md) |
| `{\| p o \|}` (AnnotationBlock) | no tree term | stored expanded as ordinary triples on a generated blank node | by design |
| `( a b )` (Collection), `[ p o ]` (BlankNodePropertyList) | no tree term | stored expanded to rdf:first/rest triples and blank nodes | by design |
| `p/q` (PathSequence) | `spexpr:PathSequence` | a sequence path | Q6; seen 17x |
| `p\|q` (PathAlternative) | `spexpr:PathAlternative` | an alternative path | Q6; seen 9x |
| `^p` (PathEltOrInverse) | `spexpr:PathInverse` | an inverse path | Q6: alternative `PathEltOrInverse`; seen 8x |
| `p*` `p+` `p?` (PathElt + PathMod) | `spexpr:PathElt` | a path with a repeat modifier | Q6: only exists when a modifier is present; seen 17x |
| `!p` `!(p\|^q)` (PathNegatedPropertySet) | `spexpr:PathNegatedPropertySet` | a negated property set | Q6; always stored with a list, even for one member; seen 5x |
| (any path node) | `spexpr:Path` | superclass of the five path classes | modelling helper; the production `Path`; never seen in test queries |
| (operands of sequence, alternative, negated set) | `spexpr:args` | the member paths/IRIs | order encoding: see tree-encoding decision; seen 31x |
| (operand of inverse) | `spexpr:arg` | the inverted path or IRI | seen 112x |
| (operand of a repeat) | `spexpr:path` | the repeated path (PathPrimary) | seen 17x |
| `*` `+` `?` (PathMod) | `spexpr:mod` | the modifier as a bare string, not PlainString-tagged | seen 17x |

## 6. Expressions: operators

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| (any expression node) (Expression) | `spexpr:Expression` | superclass of every expression node | grammar production; never seen in test queries |
| `a \|\| b` (ConditionalOrExpression) | `spexpr:ConditionalOrExpression` | an OR chain | unchanged; seen 14x |
| `a && b` (ConditionalAndExpression) | `spexpr:ConditionalAndExpression` | an AND chain | unchanged; seen 7x |
| (the two chain classes above) | `spexpr:ConditionalExpression` | superclass of the OR/AND chains | modelling helper, drives shapes; never seen in test queries |
| `= != < > <= >= IN NOT IN` (RelationalExpression) | `spexpr:RelationalExpression` | a comparison or IN test | unchanged; seen 75x |
| `+ -` (AdditiveExpression) | `spexpr:AdditiveExpression` | an additive chain | unchanged; seen 28x |
| `* /` (MultiplicativeExpression) | `spexpr:MultiplicativeExpression` | a multiplicative chain | unchanged; seen 6x |
| (the two chain classes above) | `spexpr:ArithmeticExpression` | superclass of the additive/multiplicative chains | modelling helper; never seen in test queries |
| (first operand of any chain) | `spexpr:expr` | the left-most operand; also the single operand of the unary classes | Q8; also FunctionCall args today; seen 546x |
| the operator symbol | `spexpr:op` | the operator string(s), PlainString; a list for Additive/Multiplicative, a single value for Relational | order encoding: see tree-encoding decision; Q8; seen 109x |
| the remaining operands | `spexpr:other` | the operands after the first, a list; for IN the value list | order encoding: see tree-encoding decision; Q8; seen 130x |
| `!a` | `spexpr:UnaryNot` | logical not | Q14: the spec's operator table names; not re-fetched; seen 4x |
| `-a` | `spexpr:UnaryMinus` | unary minus | Q14; seen 3x |
| `+a` | `spexpr:UnaryPlus` | unary plus | Q14; never seen in test queries |
| (the three unary classes) (UnaryExpression) | `spexpr:UnaryExpression` | superclass of the unary operators | helper; the production of the same name also covers a plain PrimaryExpression; never seen in test queries |
| `prefix:fn(args)`, `<iri>(args)` (FunctionCall, ArgList) | `spexpr:FunctionCall` | a call of a non-built-in function by IRI | one class replaces Function + FunctionExpression; seen 9x |
| (superclass of the above) | removed |  | see section 14; never seen in test queries |
| `<iri>` of the call | `spexpr:iri` | the function IRI | seen 9x |
| `DISTINCT` inside `fn(DISTINCT ...)` | `spexpr:distinct` | boolean true; also on aggregates | Q4; seen 91x |
| the arguments (ArgList) | `spexpr:args` | the argument expressions | order encoding: see tree-encoding decision; Q8: today spexpr:expr; seen 546x |

## 7.A String functions

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `STR(x)` | `spexpr:STR` | exactly one argument | family OneArgExpression; seen 12x |
| `LANG(x)` | `spexpr:LANG` | exactly one argument | family OneArgExpression; seen 6x |
| `LANGMATCHES(tag, range)` | `spexpr:LANGMATCHES` | two arguments | family TwoArgExpression; seen 4x |
| `LANGDIR(x)` | `spexpr:LANGDIR` | exactly one argument | family OneArgExpression; seen 2x |
| `hasLANG(x)` | `spexpr:hasLANG` | exactly one argument | family OneArgExpression; seen 1x |
| `hasLANGDIR(x)` | `spexpr:hasLANGDIR` | exactly one argument | family OneArgExpression; seen 1x |
| `STRLEN(x)` | `spexpr:STRLEN` | exactly one argument | family OneArgExpression; seen 3x |
| `SUBSTR(x, start [, length])` | `spexpr:SUBSTR` | SUBSTR; properties arg, start, length (length optional) | family SubstringExpression; seen 2x |
| `UCASE(x)` | `spexpr:UCASE` | exactly one argument | family OneArgExpression; seen 1x |
| `LCASE(x)` | `spexpr:LCASE` | exactly one argument | family OneArgExpression; seen 2x |
| `STRSTARTS(a, b)` | `spexpr:STRSTARTS` | two arguments | family TwoArgExpression; seen 1x |
| `STRENDS(a, b)` | `spexpr:STRENDS` | two arguments | family TwoArgExpression; seen 1x |
| `CONTAINS(a, b)` | `spexpr:CONTAINS` | two arguments | family TwoArgExpression; seen 3x |
| `STRBEFORE(a, b)` | `spexpr:STRBEFORE` | two arguments | family TwoArgExpression; seen 8x |
| `STRAFTER(a, b)` | `spexpr:STRAFTER` | two arguments | family TwoArgExpression; seen 8x |
| `ENCODE_FOR_URI(x)` | `spexpr:ENCODE_FOR_URI` | exactly one argument | family OneArgExpression; seen 1x |
| `CONCAT(a, b, ...)` | `spexpr:CONCAT` | CONCAT; spexpr:args the list (order matters) | order encoding: see tree-encoding decision; Q8: today spexpr:arg; family VariadicArgExpression; seen 12x |
| `REGEX(text, pattern [, flags])` | `spexpr:REGEX` | REGEX; properties text, pattern, flags (flags optional) | family RegexExpression; seen 3x |
| `REPLACE(arg, pattern, replacement [, flags])` | `spexpr:REPLACE` | REPLACE; properties arg, pattern, replacement, flags (flags optional) | family StrReplaceExpression; seen 4x |

## 7.B Numeric functions

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `ABS(x)` | `spexpr:ABS` | exactly one argument | family OneArgExpression; seen 1x |
| `CEIL(x)` | `spexpr:CEIL` | exactly one argument | family OneArgExpression; seen 1x |
| `FLOOR(x)` | `spexpr:FLOOR` | exactly one argument | family OneArgExpression; seen 1x |
| `ROUND(x)` | `spexpr:ROUND` | exactly one argument | family OneArgExpression; seen 1x |
| `RAND()` | `spexpr:RAND` | no arguments | family ZeroArgExpression; seen 1x |

## 7.C Date and time functions

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `NOW()` | `spexpr:NOW` | no arguments | family ZeroArgExpression; seen 1x |
| `YEAR(x)` | `spexpr:YEAR` | exactly one argument | family OneArgExpression; seen 1x |
| `MONTH(x)` | `spexpr:MONTH` | exactly one argument | family OneArgExpression; seen 1x |
| `DAY(x)` | `spexpr:DAY` | exactly one argument | family OneArgExpression; seen 1x |
| `HOURS(x)` | `spexpr:HOURS` | exactly one argument | family OneArgExpression; seen 1x |
| `MINUTES(x)` | `spexpr:MINUTES` | exactly one argument | family OneArgExpression; seen 1x |
| `SECONDS(x)` | `spexpr:SECONDS` | exactly one argument | family OneArgExpression; seen 1x |
| `TIMEZONE(x)` | `spexpr:TIMEZONE` | exactly one argument | family OneArgExpression; seen 1x |
| `TZ(x)` | `spexpr:TZ` | exactly one argument | family OneArgExpression; seen 1x |

## 7.D Hash functions

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `MD5(x)` | `spexpr:MD5` | exactly one argument | family OneArgExpression; seen 2x |
| `SHA1(x)` | `spexpr:SHA1` | exactly one argument | family OneArgExpression; seen 2x |
| `SHA256(x)` | `spexpr:SHA256` | exactly one argument | family OneArgExpression; seen 2x |
| `SHA384(x)` | `spexpr:SHA384` | exactly one argument | family OneArgExpression; seen 2x |
| `SHA512(x)` | `spexpr:SHA512` | exactly one argument | family OneArgExpression; seen 2x |

## 7.E RDF term tests and functional forms

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `isIRI(x)` | `spexpr:isIRI` | exactly one argument | family OneArgExpression; seen 1x |
| `isURI(x)` | `spexpr:isURI` | synonym of isIRI, kept as typed | family OneArgExpression; never seen in test queries |
| `isBLANK(x)` | `spexpr:isBLANK` | exactly one argument | family OneArgExpression; never seen in test queries |
| `isLITERAL(x)` | `spexpr:isLITERAL` | exactly one argument | family OneArgExpression; seen 1x |
| `isNUMERIC(x)` | `spexpr:isNUMERIC` | exactly one argument | family OneArgExpression; seen 2x |
| `BOUND(?v)` | `spexpr:BOUND` | argument is a variable | family OneArgExpression; never seen in test queries |
| `sameTerm(a, b)` | `spexpr:sameTerm` | two arguments | family TwoArgExpression; seen 3x |
| `DATATYPE(x)` | `spexpr:DATATYPE` | exactly one argument | family OneArgExpression; seen 10x |
| `IF(c, a, b)` | `spexpr:IF` | IF; properties arg1 arg2 arg3 | family ThreeArgExpression; seen 3x |
| `COALESCE(a, b, ...)` | `spexpr:COALESCE` | COALESCE; spexpr:args the list | order encoding: see tree-encoding decision; Q8; family VariadicArgExpression; seen 7x |

## 7.F Triple-term functions (RDF 1.2)

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `isTRIPLE(x)` | `spexpr:isTRIPLE` | exactly one argument | family OneArgExpression; seen 2x |
| `SUBJECT(t)` | `spexpr:SUBJECT` | exactly one argument | family OneArgExpression; seen 2x |
| `PREDICATE(t)` | `spexpr:PREDICATE` | exactly one argument | family OneArgExpression; seen 2x |
| `OBJECT(t)` | `spexpr:OBJECT` | exactly one argument | family OneArgExpression; seen 2x |

## 7.G Constructors

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `IRI(x)` | `spexpr:IRI` | exactly one argument | family OneArgExpression; seen 2x |
| `URI(x)` | `spexpr:URI` | synonym of IRI, kept as typed | family OneArgExpression; seen 2x |
| `BNODE([x])` | `spexpr:BNODE` | BNODE with an optional argument | family OptionalOneArgExpression; seen 4x |
| `UUID()` | `spexpr:UUID` | no arguments | family ZeroArgExpression; seen 3x |
| `STRUUID()` | `spexpr:STRUUID` | no arguments | family ZeroArgExpression; seen 1x |
| `STRDT(lex, dt)` | `spexpr:STRDT` | two arguments | family TwoArgExpression; seen 3x |
| `STRLANG(lex, tag)` | `spexpr:STRLANG` | two arguments | family TwoArgExpression; seen 12x |
| `STRLANGDIR(lex, tag, dir)` | `spexpr:STRLANGDIR` | STRLANGDIR; properties lex, lang, direction | family StrLangDirExpression; seen 8x |

## 7.H Named-parameter properties of the built-ins

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| (argument) | `spexpr:text` | the string REGEX tests | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 3x |
| (argument) | `spexpr:pattern` | the regular expression (REGEX, REPLACE) | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 7x |
| (argument) | `spexpr:flags` | the optional flags string (REGEX, REPLACE) | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 3x |
| (argument) | `spexpr:replacement` | the replacement string of REPLACE | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 4x |
| (argument) | `spexpr:start` | the start position of SUBSTR | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 2x |
| (argument) | `spexpr:length` | the optional length of SUBSTR | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 1x |
| (argument) | `spexpr:lex` | the lexical form of STRLANGDIR | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 8x |
| (argument) | `spexpr:lang` | the language tag of STRLANGDIR | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 8x |
| (argument) | `spexpr:direction` | the direction of STRLANGDIR | names follow the argument names of spec section 17.4 prototypes; not re-fetched; seen 8x |
| (argument) | `spexpr:arg` | the single argument of a one-argument built-in (BNODE: optional); on the unary and inverse-path classes too | Q8; seen 112x |
| (argument) | `spexpr:arg1` | first argument of a two- or three-argument built-in | Q8; seen 46x |
| (argument) | `spexpr:arg2` | second argument | Q8; seen 46x |
| (argument) | `spexpr:arg3` | third argument (IF) | Q8; seen 3x |

## 8. Aggregates (Aggregate)

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| (any aggregate call) (Aggregate) | `spexpr:Aggregate` | superclass of the seven aggregates | grammar production; never seen in test queries |
| `COUNT( [DISTINCT] x )` | `spexpr:COUNT` | the COUNT aggregate | Q3; seen 33x |
| `SUM( [DISTINCT] x )` | `spexpr:SUM` | the SUM aggregate | Q3; seen 5x |
| `MIN( [DISTINCT] x )` | `spexpr:MIN` | the MIN aggregate | Q3; seen 6x |
| `MAX( [DISTINCT] x )` | `spexpr:MAX` | the MAX aggregate | Q3; seen 9x |
| `AVG( [DISTINCT] x )` | `spexpr:AVG` | the AVG aggregate | Q3; seen 9x |
| `SAMPLE( [DISTINCT] x )` | `spexpr:SAMPLE` | the SAMPLE aggregate | Q3; seen 4x |
| `GROUP_CONCAT( [DISTINCT] x [; SEPARATOR=","] )` | `spexpr:GROUP_CONCAT` | the GROUP_CONCAT aggregate | Q3; seen 10x |
| the aggregated expression, or `*` | `spexpr:expr` | the operand of an aggregate; the marker `*` (PlainString) for COUNT(*) | Q4: wrong name today (vars: it is one expression); seen 136x |
| `DISTINCT` | `spexpr:distinct` | boolean true on an aggregate | Q4: today the string DISTINCT or rdf:nil when absent; seen 91x |
| `SEPARATOR="..."` | `spexpr:separator` | the GROUP_CONCAT separator string | seen 2x |

## 9. Solution modifiers

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `GROUP BY` (GroupClause, GroupCondition) | `sqe:groupBy` | grouping items: variables, expressions, Alias nodes | order encoding: see tree-encoding decision; seen 36x |
| `HAVING` (HavingClause) | `sqe:having` | the HAVING conditions | order encoding: see tree-encoding decision; seen 5x |
| `ORDER BY` (OrderClause) | `sqe:orderBy` | the order conditions | order encoding: see tree-encoding decision; seen 41x |
| `ASC(x)` / `DESC(x)` / `?x` (OrderCondition) | `sqe:OrderCondition` | one ordering key (expr + direction) | unchanged; seen 44x |
| `DESC` | `sqe:descending` | boolean true for DESC; absent for ASC and the bare form | no DESC in the vendored .rq files; never seen in test queries |
| `LIMIT n` (LimitClause) | `sqe:limit` | xsd:integer | seen 27x |
| `OFFSET n` (OffsetClause) | `sqe:offset` | xsd:integer | seen 24x |

## 10. Inline data

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `VALUES ... { ... }` in a pattern or trailing (InlineData, ValuesClause, DataBlock) | `sqe:Values` | an inline data block (same class in a pattern and as a trailing clause) | Q1; seen 60x |
| (the trailing clause) | `sqe:values` | links a query to its trailing Values block | seen 30x |
| `?x` or `(?x ?y)` (InlineDataOneVar, InlineDataFull) | `sqe:vars` | the variables of the block | order encoding: see tree-encoding decision; seen 136x |
| `{ (1 2) (3 UNDEF) }` | `sqe:rows` | the data rows, each a list of terms | order encoding: see tree-encoding decision (rows, then cells); seen 60x |
| `UNDEF` | `sqe:undef` | a constant IRI used as the cell value, not a class or property | not declared in sqe-ontology.ttl, only in code and shapes; never seen in test queries |

## 11. Update

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| (update request) (UpdateUnit, Update) | `sqe:UpdateRequest` | root of an update request | unchanged; seen 146x |
| `op ; op` (Update1 list) | `sqe:operations` | the operations in source order | order encoding: see tree-encoding decision; seen 146x |
| (any operation) (Update1) | `sqe:UpdateOperation` | superclass of the eleven operations; carries the prologue written before it | Q12: helper name; grammar's is Update1; never seen in test queries |
| `INSERT DATA { ... }` (InsertData) | `sqe:InsertData` |  | unchanged; seen 19x |
| `DELETE DATA { ... }` (DeleteData) | `sqe:DeleteData` |  | unchanged; seen 11x |
| `DELETE WHERE { ... }` (DeleteWhere) | `sqe:DeleteWhere` |  | unchanged; seen 8x |
| `WITH ... DELETE ... INSERT ... USING ... WHERE` (Modify) | `sqe:Modify` | the general modify operation | unchanged; seen 64x |
| `LOAD [SILENT] <i> [INTO GRAPH <g>]` (Load) | `sqe:Load` |  | unchanged; seen 7x |
| `CLEAR` (Clear) | `sqe:Clear` |  | unchanged; seen 14x |
| `DROP` (Drop) | `sqe:Drop` |  | unchanged; seen 22x |
| `CREATE` (Create) | `sqe:Create` |  | unchanged; seen 4x |
| `ADD` (Add) | `sqe:Add` |  | unchanged; seen 8x |
| `MOVE` (Move) | `sqe:Move` |  | unchanged; seen 6x |
| `COPY` (Copy) | `sqe:Copy` |  | unchanged; seen 6x |
| `{ quads }` (QuadData, QuadPattern, Quads) | `sqe:quads` | the quads of INSERT DATA / DELETE DATA / DELETE WHERE: TriplePattern and QuadGraph in written order | order encoding: see tree-encoding decision; seen 38x |
| `GRAPH g { ... }` inside quads (QuadsNotTriples) | `sqe:QuadGraph` | a graph block inside a quad list | Q13; seen 45x |
| (its graph) | `sqe:graphName` | IRI or variable | seen 45x |
| (its triples) | `sqe:triples` | the triple patterns of the block | order encoding: see tree-encoding decision; seen 45x |
| `WITH <g>` | `sqe:with` | the default graph for the operation | seen 10x |
| `DELETE { ... }` (DeleteClause) | `sqe:delete` | the delete template | order encoding: see tree-encoding decision; seen 31x |
| `INSERT { ... }` (InsertClause) | `sqe:insert` | the insert template | order encoding: see tree-encoding decision; seen 38x |
| `USING [NAMED] <g>` (UsingClause) | `sqe:using` | the USING clauses (DatasetClause nodes) | order encoding: see tree-encoding decision; seen 9x |
| `LOAD <i>` | `sqe:loadFrom` | the IRI to read | seen 7x |
| `INTO GRAPH <g>` | `sqe:into` | a GraphRef | seen 3x |
| `CLEAR/DROP/CREATE target` (GraphRefAll) | `sqe:target` | a graph reference | seen 40x |
| `ADD/MOVE/COPY <a> TO <b>` (GraphOrDefault) | `sqe:from` | the source | seen 20x |
| (the destination) | `sqe:to` | the destination | seen 20x |
| `GRAPH <g>` as a target (GraphRef) | `sqe:GraphRef` | a reference to one named graph | unchanged; seen 54x |
| (its IRI) | `sqe:graphIri` |  | seen 54x |
| `DEFAULT` | `sqe:DefaultGraph` | the default graph as a target | keyword stand-in; seen 17x |
| `NAMED` | `sqe:NamedGraphs` | every named graph | keyword stand-in; same keyword as sqe:named; seen 6x |
| `ALL` | `sqe:AllGraphs` | default and all named graphs | keyword stand-in; seen 6x |

## 12. Terms

| SPARQL as written (production) | Proposed sqe tree term | What the term represents | Notes |
|---|---|---|---|
| `?x` `$x` (Var, VAR1, VAR2) | datatype `spexpr:Variable` | a variable is a literal whose lexical form is the name (no `?`) and whose datatype is spexpr:Variable; a modelling device because a variable is not an RDF term | helper; the same encoding in patterns, expressions, projections; no `?`/`$` distinction kept; never seen in test queries |
| (operator symbols, `*`, DISTINCT markers, PNAME_NS labels) | datatype `spexpr:PlainString` | a bare string that is not an RDF term, tagged so it never equals an xsd:string value | helper; mod is the exception (untagged); never seen in test queries |
| `<iri>` (iri, IRIREF), `p:x` (PrefixedName) | an RDF IRI node | an ordinary IRI; prefixed names and relative IRIs are stored resolved; an IRI that cannot be one is kept as `urn:starlayer:invalid-iri:...` | no tree class |
| `"x"`, `'x'`, `"x"@en`, `"x"@en--ltr`, `"x"^^<dt>` (RDFLiteral, String, LANG_DIR) | an RDF literal | stored as an RDF literal (xsd:string, rdf:langString, rdf:dirLangString or typed) | no tree class |
| `12`, `1.5`, `1e3`, `-3` (NumericLiteral) | an RDF literal | stored as xsd:integer / decimal / double; the store may canonicalise the lexical form (issue #190); a leading `-` in an expression is UnaryMinus | no tree class |
| `true` `false` (BooleanLiteral) | an RDF literal | xsd:boolean | no tree class |
| `_:b`, `[]` (BlankNode, ANON) | an RDF blank node | a blank node; in a pattern it acts as a variable | no tree class |
| (any ordered list of children) | `rdf:List` (rdf:first, rdf:rest, rdf:nil) | how every list-valued property above is stored | order encoding: see tree-encoding decision |

## 13. Removed from the vocabulary

| Term | Why |
|---|---|
| `spexpr:Builtin_EXISTS, Builtin_NOTEXISTS, ExistsExpression, spexpr:graph` | dead: the encoder writes sqe:Exists; shapes still carry a body shape |
| `spexpr:TrueFilter` | rdflib algebra artefact, no producer |
| `spexpr:FunctionExpression` | folded into FunctionCall |
| `spexpr:Function` | replaced by FunctionCall |
| `spexpr:Builtin_X (62), Aggregate_X (7)` | replaced by the keyword classes |
| `spexpr:vars (aggregate operand)` | replaced by expr |

## 14. Coverage check

- Ontology files (`sqe-ontology.ttl`, `spexpr-ontology.ttl`): 186 distinct terms declared (classes + properties; the spexpr ontology declares no properties, they exist only in its shapes). Terms used only by the shapes, code or serialiser and not declared in an ontology: 30 (a loose grep of the shapes, e.g. `sqe:base`, `prologuePrefix`, `PrefixBinding`, `prefixLabel`, `namespace`, `spexpr:Variable`, `arg`, `args`, `path`, `mod`).
- Table rows: 218, of which 1 say `removed`. Every ontology term is the current name of at least one row except: `spexpr:Builtin_EXISTS`, `spexpr:Builtin_NOTEXISTS`, `spexpr:ExistsExpression`, `spexpr:TrueFilter` (all in section 13). Shapes-only terms not placed: none.
- Terms never produced by the 621 test queries (still placed): `sqe:descending`, `reduced`, `DescribeQuery`, `describe`, `describeAll`, `spexpr:UnaryPlus`, `BOUND`, `isBLANK`, `isURI`, and the helper superclasses. My probes show DESC, REDUCED, DESCRIBE, `+?x`, `BOUND` all produce them (DESC, BOUND, `+` and DESCRIBE verified; REDUCED verified).
- SPARQL constructs with no tree term (stored expanded or dropped, by design): `a`, prefixed names, relative IRIs (resolved), `;` and `,` lists, `[ ]`, `( )`, `<< >> ~`, `{| |}`, bare `{ }` group (becomes a one-alternative Union), `TRIPLE(...)` call (becomes TripleTerm), `CONSTRUCT WHERE` shorthand, comments, `$x` vs `?x`.
- Could not verify: the spec 17.4 argument names (`arg1`, `text`, ...) and the operator-table names for the unary classes were not re-fetched; grammar names come from the vendored table (draft 2026-11-01); whether the `spexpr:graph`/`ExistsExpression` shapes are exercised by any test (grep finds no producer); the notes' counts cover only the vendored W3C `.rq`/`.ru` files; the proposed names were not run against the shapes.
