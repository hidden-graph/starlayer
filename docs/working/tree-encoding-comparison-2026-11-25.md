# How to store ordered children in the syntax trees: rdf:List against two alternatives (2026-11-25)

Status: investigation note for John to decide. Nothing in the library, tests, shapes or notebooks was changed. Everything
below was measured with throwaway code in the session scratchpad
(`/private/tmp/claude-501/-Users-johnclements-Documents-GitHub-hidden-graph-starlayer/c7ee9849-07ef-4260-9f2c-bc8ee0388c47/scratchpad/tree-encoding/`):
a converter that rewrites the list-valued properties of an existing tree graph into another encoding and back
(`enc.py`), the ported SPARQL constraints (`gen.py`), the shapes (`mkshapes.py`), and the scripts that produced each number
(`bench.py`, `t2.py` ... `t14.py`; raw timings in `bench_out.json` and `bench_out2.json`, two full runs).

## 0. Short answer

- The three costs named in the question are not all caused by `rdf:List`, and the library already has most of the fix for
  the first one. `StarLayerGraph.items`, `set_list`, `add_list` and `remove_list` exist (`graph/rdflist.py`). With them an
  append is one line, an insert, remove or replace three. The 15-line cell in guide 06.05.3 does the surgery by hand and
  does not use them. (I did not check why; it may predate the helpers.)
- Shape duplication is real and an alternative encoding removes it: SRL's nine list shapes plus the five node shapes that
  point at them are 265 non-blank lines; with child-carried ordinals (C below) the same checks are 58 lines, with indexed
  item nodes (B) 88.
- Speed is mixed. Child-carried ordinals (C) are faster on the three constraints I ported (40 rules: 917 ms against 1536 ms
  for the same three shipped constraints plus structure); indexed items (B) are slower (2110 ms). The per-query formulation
  matters as much as the encoding: rewriting the same shipped query with my macros in the same encoding made it up to 5 times
  slower, so differences under about 2 times between encodings are within what a rewrite does.
- Two findings about the current encoding that the question did not ask about: (a) the shipped SRL shapes accept a list
  that loops, a cell with two `rdf:first`, a forked `rdf:rest`, and one list shared by two rules (the report conforms;
  only the decoder objects, except the shared list, which decodes); (b) RDFC-1.0 canonicalisation of an SRL tree is refused from
  about 12 generated rules up, because list cells cannot be told apart, while B and C hash fine.
- Recommendation: helpers-only now (section 9), with C as the target if you decide the hash refusal and the list shapes
  are worth a migration across all three languages. B is not worth it.

## 1. What was built

| Encoding | Shape of one sequence | Notes |
|---|---|---|
| A | `parent p ( x y z )`, `rdf:List` | the baseline |
| B | `parent p [ a srl:Item ; srl:index 0 ; srl:value x ]`, one item per child | also run gapped, indices 10, 20, 30 ("B10") |
| C | the child node itself carries the ordinal: `parent p x . x srl:ord 0` | a literal, an IRI, a shared node, or a list that is itself a list member is wrapped as in B (with `srl:ord`) |

Why C: it is the smallest change that makes the tree a tree. The children of the tree are already blank nodes owned by
one parent and typed, so the ordinal can live on the child and no item node, no cell and no wrapper is needed for them.
Then a shape on `srl:body` is an ordinary property shape (`sh:class`), a path to the children is one property, and an
"earlier sibling" is a comparison of two integers. I also considered `rdf:_1`, `rdf:_2` on a container node (the
position is in the predicate IRI, so a query has to parse it out of the IRI text, and a SHACL path cannot say it), a
`:next` chain (a linked list again, with the same surgery and cycle problem, and it needs an item node per child), and
RDF 1.2 reifier or annotation nodes (still one node per child, plus triple-term machinery, with no gain over B). I did not build those.

Limits of the prototypes: the converter turns lists of the `srl:` namespace only for the timing runs (the `spexpr:`
expression lists stay `rdf:List`, since their three list shapes are not part of the SRL file); counts with every list
converted are given where they differ. B and C do not distinguish an empty sequence from an absent one (A writes
`rdf:nil`); the back converter needs a table of which properties a class must carry to restore the empties (5 classes for
SRL). A list that is a member of another list (SQE `UNION` alternatives, `VALUES` rows, Manchester class lists) needs a
node to hang its members on; the converter makes an `srl:Sequence` node.

## 2. Triple counts for the same tree

| Tree | A | B | C | Notes |
|---|---|---|---|---|
| SRL, 1 data block, 2 rules, one NOT, GROUP, SET (`SMALL`) | 124 | 152 (+23%) | 116 (-6%) | `srl:` lists converted |
| SRL, 3 generated rules | 232 | 286 (+23%) | 220 (-5%) | all lists converted: 232 / 292 / 226 |
| SRL, 40 generated rules | 3044 | 3801 (+25%) | 2921 (-4%) | all lists converted: 3044 / 3881 / 3001 |
| Manchester, the 3-line document of guide 06.05 | 32 | 37 (+16%) | 25 (-22%) | all lists |
| SQE, `SELECT ... GROUP BY ... ORDER BY ... UNION ... VALUES` | 87 | 120 (+38%) | 92 (+6%) | all lists; list-of-lists need extra nodes in B and C |

B and B10 have the same count. C is smaller than A when most members are typed nodes (one ordinal triple against two
cell triples) and larger when members are literals or nested lists.

## 3. Editing (1)

All snippets were run, and after each edit the tree was converted back to `rdf:List` and rendered with the existing
`srl_tree_to_text` / `manchester_tree_to_text`; the five variants of each operation (A bare, A with the library helpers,
B, B gapped, C) gave the same text. Counts are non-blank, non-comment body lines, on one rule's `srl:body`; `new` is an
element node already built (that part is the same in every encoding). Source: `edits.py`.

| Operation | A, bare | A, library helpers | B (dense) | B gapped | C |
|---|---|---|---|---|---|
| append | 12 | 1 | 6 | 6 | 3 |
| insert in the middle | 8 | 3 | 8 | 11 | 4 |
| remove | 7 | 3 | 3 | 3 | 3 |
| replace | 4 | 3 | 1 | 1 | 4 |

Plus 2 lines of shared sort helper for B and C (`_items_b`, `_kids_c`). Notes:

- A bare append needs the empty-list case (the owner points at `rdf:nil`), which is where the 12 comes from; the guide cell
  hits the same problem only because its list is never empty. The library helper version is
  `g.set_list(rule, BODY, [*g.items(g.value(rule, BODY)), new])`.
- B gapped insert is a midpoint, and falls back to a renumbering loop when two neighbours are adjacent (that is the 11 lines);
  dense B and C insert renumber everything after the insertion point. Remove never renumbers in B or C and leaves a gap.
- A would-be helper API (`append / insert / remove_at / replace_at(graph, owner, prop, ...)`) costs one line per call in
  every encoding; what differs is its implementation: about 5 lines on top of `items` and `set_list` for A, about 12 for B
  and about 10 for C (estimates from the snippets above, not written out as a library).
- On the real Manchester example (append `hasWheelCount some xsd:integer` to the `SubClassOf:` clause) A with helpers is 1
  line, B 4, C 3; the three rendered texts are equal and differ from the original.

Result: editing alone is no reason to change the encoding. A with the shipped helpers is as short as anything.

## 4. Shapes (2)

SRL, from `srl_shapes.ttl` (non-blank lines, comments excluded; the new shapes parse and were run, see section 7):

| | A (shipped) | B | C |
|---|---|---|---|
| the nine `*ListShape` blocks (`RuleList`, `DataList`, `ImportsList`, `BodyList`, `NegationInnerList`, `TripleList`, `GroupKeysList`, `GroupPatternList`, `AggregationList`) | 173 | 0 | 0 |
| the five node shapes that refer to them (`RuleSet`, `Rule`, `Data`, `NegationElement`, `GroupElement`) | 92 | 77 | 45 |
| shared shape for position (type and uniqueness of the integer) | 0 | 11 | 13 |
| total for this part | 265 | 88 | 58 |
| structural SRL shapes (the part I rebuilt, without the 14 section 4.2 constraints) | 375 | 198 | 168 |

- In A the nine list shapes are one SPARQL constraint copied nine times; seven differ only in the class name and message, one
  in the IRI test, one in the variable-literal test. In C each sequence is one line of the owner's property shape
  (`sh:path srl:body ; sh:class srl:BodyElement ; sh:node srl:OrdShape`); only `keys` and `imports` need the wrapper form.
  In B each sequence is a nested property shape of about 5 lines.
- One shared shape (`OrdShape` / `ItemShape`) carries all the position rules: exactly one integer, and no two members of
  one owner and property with the same integer (one SPARQL constraint, not per class).
- Strength: I checked three structural faults (an `srl:Aggregation` in a rule body, a GROUP inside a NOT, a literal in a
  head): A, B and C all report non-conforming.
- Other files: the same count for `sqe_shapes.ttl` is 6 list shapes (138 lines), `manchester_shapes.ttl` 13 (231 lines),
  `spexpr_shapes.ttl` 3 (61 lines): 31 in all, 603 lines. I did not rewrite these three files; the SRL ratio is
  the only measured one. Nested lists in SQE (`UNION`, `VALUES`) would not shrink as much, because they need a node type
  for the inner list.
- Untested alternative that keeps A: generate the 31 list shapes from one template (the way `spexpr` already generates the
  per-builtin shapes), or declare one parameterised constraint component. That removes the duplication without changing
  the data; I did not try it.

## 5. SPARQL constraint cost (3)

Ported by hand from `srl_shapes.ttl` with one set of macros (`gen.py`): `UnboundHeadVariableShape`,
`UnboundFilterVariableShape` and `VariableInUseShape` (the last is the largest, seven `UNION` branches). The macros
generate the A form too, so the A form could be checked against the shipped text.

Agreement: on 232 rule sets (the conformance suite's section 4.2 negative cases, the extra texts and the four seeded random
sets of `test_srl_wellformedness_agreement.py`; 158 of them with at least one finding) the three constraints give exactly the
same `(shape, focus node, variable)` rows from the shipped shapes on A, the macro form on A, and the macro form on B,
B gapped and C. The focus nodes are the same blank nodes because the converter keeps them.

Timing: steady state (shapes graph and parsed plan cached, `rdfs_entailed_copy` included, then the cost of an empty
shape subtracted), median of 5 runs, one machine (Apple, other work was running; two complete runs agree within about
5%). The rule sets are generated (`samples.big(n)`): each rule has 2 head triples, 2 triple patterns, a FILTER, a NOT with a
FILTER inside, a SET and one more triple pattern. They are heavier than the set behind the 585 ms figure in the question:
here the whole shipped `srl_validate` takes 55 ms on 3 rules and 2440 ms on 40, so compare ratios, not absolute numbers.

Per focus node (microseconds), 40 rules (240 triple patterns, 80 filters):

| Constraint | A shipped | A, macro form | B | B gapped | C |
|---|---|---|---|---|---|
| UnboundHeadVariable | 444 | 2234 | 311 | 303 | 97 |
| UnboundFilterVariable | 11342 | 12363 | 11753 | 11493 | 5100 |
| VariableInUse | 1492 | 1517 | 4312 | 4235 | 1485 |

Same, 3 rules (18 triple patterns, 6 filters):

| Constraint | A shipped | A, macro form | B | B gapped | C |
|---|---|---|---|---|---|
| UnboundHeadVariable | 108 | 230 | 104 | 101 | 69 |
| UnboundFilterVariable | 661 | 748 | 859 | 1082 | 634 |
| VariableInUse | 1037 | 1060 | 1454 | 1434 | 859 |

Totals (ms), the structural shapes plus the three constraints, merged with the `spexpr:` and `sqe:` shapes the way
`srl_validate` does:

| Rule set | A shipped text | A macro form | B | B gapped | C | whole shipped `srl_validate` (14 constraints, A) |
|---|---|---|---|---|---|---|
| 3 rules | 34.3 | 37.0 | 44.1 | 45.5 | 29.3 | 54.6 |
| 40 rules | 1536 | 2055 | 2110 | 2101 | 917 | 2440 |

Structural shapes alone (no section 4.2 constraints): 3 rules 8.3 (A) / 9.9 (B) / 9.3 (C) ms; 40 rules 124 / 114 / 111 ms.
Cost per shipped constraint on 40 rules (A, ms): UnboundFilter 991, UnboundAssignmentExpression 518, VariableInUse 363,
ReusedAssignment 199, UnboundHead 107, UnsupportedVariableName 66, the other eight under 12.

What this says, and what it does not:

- C is the only encoding that beat the shipped A on all three at 40 rules (head 4.6 times, filter 2.2 times, in-use equal).
  B is equal or worse. B's cost is the extra join through the item node.
- The cost per focus node grows with the size of the tree, not the rule: UnboundFilter is 0.66 ms per filter at 3 rules and
  11.3 ms at 40, in all encodings. The expensive part is the unbounded "earlier siblings" join, not the list walk. C halves
  it; it does not fix it. At 40 rules `srl_validate` stays above 1 second on this input whatever the list encoding is,
  which is why the run-time check is in Python.
- The same query written two ways in A differs by 5 times (head: 444 against 2234 us), so single results under 2 times
  are not conclusive.
- The constraint text is not shorter: VariableInUse is 3550 characters in A (macro form), 4630 in B and 3712 in C. The A path
  `^rdf:first/^rdf:rest+/rdf:first` is compact for "earlier sibling"; B and C need a filter on two integers. What B and C
  remove is every `rdf:rest*`. C's "earlier sibling" cannot be written as a path.
- Not ported: the other 11 section 4.2 constraints, the SQE constraints. The totals above are for the structural shapes
  plus three of the 14, so they are not a full `srl_validate` for B or C. I did not time SQE or Manchester validation.

## 6. Round trip (4)

For each of the 3 SRL sets, SMALL, the SQE query and the Manchester document: tree in A, converted to B, B gapped, C, converted
back to `rdf:List` with the table of required empty lists, rendered with the existing `srl_tree_to_text`,
`sqe_tree_to_text`, `manchester_tree_to_text`. The text equals the original text in every case. The back-converted graph is
isomorphic to the original (library `isomorphic`) for SMALL, the 3-rule set, SQE and Manchester. For the 40-rule A tree the
isomorphism check itself is refused (section 8), so only the text was compared there. A generic decoder (not written)
would read the same facts; the existing decoders read each list with `_read_list` (11 call sites in `srl.py`).

## 7. Ordering robustness (5)

Faults injected into a two-rule SRL tree (`t5.py`), checked with the shipped `srl_validate` (A) and with the structural
shapes plus the three constraints (B, C):

| Fault | A: `srl_validate` | A: decoder | B | C |
|---|---|---|---|---|
| list cycle (last `rdf:rest` back to the first cell) | conforms | `SRLDecodeError` (cycle) | cannot occur | cannot occur |
| cell with two `rdf:first` | conforms | `SRLDecodeError` | n/a | n/a |
| cell with no `rdf:first` | violation | `SRLDecodeError` | n/a | n/a |
| cell with two `rdf:rest` (a fork) | conforms | `SRLDecodeError` | n/a | n/a |
| one list shared by two rules | conforms | decodes | n/a | n/a |
| two children with the same index | n/a | n/a | violation (`ItemShape`) | violation (`OrdShape`) |
| a child with no index | n/a | n/a | violation | violation |
| index not an integer | n/a | n/a | violation | violation |
| a child with two indices | n/a | n/a | violation | violation |
| item without a value / with two values | n/a | n/a | violation (min / max count) | n/a |
| an untyped blank node as a member | n/a | n/a | violation | violation |
| a negative or large index | allowed (the order is still defined) | | allowed | allowed |
| the same member listed under two rules | n/a | | violation, only because two indices collided (a shared member at distinct indices would pass) | same |

So the statement that in A "the structure forbids it" is true of the decoder, not of the shapes: the shipped list
shapes use `rdf:rest*/rdf:first` and `FILTER NOT EXISTS { $this rdf:first ?head }`, and they are blind to cycles, doubled
cells, forks and sharing. Manchester already works around this with a `_preflight` walk for loops
(`manchester/__init__.py`, about 12 lines) because the engine itself raises on a cyclic list. B and C can be made to
reject every fault in the table with one shared shape, but a missing or duplicated index has no valid reading, so the
decoder must raise on ties. It must not break a tie by blank node label, which would not be reproducible between
parses. (My converter breaks ties by `str(member)`, which is a convenience of the prototype, not a proposal.) A loop in
the tree itself (a node that contains itself) is possible in every encoding; I did not test it.

## 8. Hashing and isomorphism (6)

RDFC-1.0 through `graph/rdfc_native.py` (`canonical_hash`, `isomorphic`); the library refuses a graph when too many
blank nodes are indistinguishable from their neighbours:

| Generated rules | A | B | C |
|---|---|---|---|
| 3 | hash in 3.2 ms | 4.2 ms | 2.3 ms |
| 10 | 18.5 ms | 13.7 ms | 7.3 ms |
| 12 to 30 | `CanonicalizationComplexityError` | hashes | hashes |
| 40 | refused ("741 blank nodes that the quads around them cannot tell apart ... more than 200") | 57 ms | 31 ms |

- A refuses because (my reading of the error message, not traced in the algorithm) list cells look identical at first degree: the chain of cells has no distinguishing literal. B and C
  put a distinct integer on every position, so nothing is tied. This was an unexpected finding; it matters for the
  use case in the notes (hash a tracked subset and verify it later) once the subset has a dozen rules. Whether real rule sets reach
  the limit I cannot say: these are generated rules of one shape.
- Two parses of the same text hash equal in all four encodings (blank node labels do not matter).
- Index values are part of the meaning in B and C. The same tree with indices 0,1,2, with 10,20,30 and with 1,2,3 gives three
  different hashes (B). Appending and then removing an item restores the original hash in all three. Removing a middle item
  does not: B and C leave a gap and hash differently from a freshly parsed shorter tree (A is equal to the fresh
  tree). Renumbering to dense indices (re-encoding through A in my prototype) restores equality for C (verified); B is
  the same mechanism (not run).
- So with B or C a "normalise" step (renumber densely) must run before hashing or comparing, and a gapped scheme
  (B10) makes this worse, not better.

## 9. Could one generic encoder serve all three languages

Read: `parse_sparql._Encoder`, `srl.py` (`_Writer`, decoders, renderers), `starontology/manchester/__init__.py`.

- The three do not share an AST type. SQE's parser produces `parse_sparql.Node(kind, **f)`; SRL's rule structures are frozen
  dataclasses in `_srl_ast.py`, and only its expression leaves are `Node` (they go through the shared `_Encoder.term`);
  Manchester's parser produces plain tuples tagged by a string (`('Some', prop, filler)`).
- Shared today: the term and expression encoder (`_Encoder.term` / `node` / `path`, about 50 lines), and the sequence
  write call (`_list` in `parse_sparql.py`, `_build_rdf_list` in Manchester which is `add_list`; `_read_list` in `srl.py`,
  `_read_rdf_list` in Manchester, `graph.items` in SQE's text renderer: three implementations of the same walk).
- Per-language, in non-blank lines (counted with `ast`, rough):

| | encode | decode | text renderer |
|---|---|---|---|
| SQE | `_Encoder` 284 (of which about 50 are the shared term and expression part) | `sqe/to_text.py` 421 + `expr_text.py` 205 | in the same files |
| SRL | `_Writer` 72 + `ruleset_to_tree` 18 | 110 | 82 |
| Manchester | about 304 (encoders + the parse hooks) | about 150 | about 187 |

- A table-driven walk works for SRL. `generic.py` is a 22-line `encode()` plus an 11-line table (class to RDF class, field
  to property and kind). It produces a graph isomorphic to `ruleset_to_tree` for A, and isomorphic to the converter's B
  and C, with the sequence policy as one swappable function. That is 33 lines against 90, for the encoding side only.
  The decoders and text renderers would still be per language (SRL 192, SQE 626, Manchester 337 lines), because they
  hold the grammar, not the data layout.
- It would not work as cleanly for SQE or Manchester without more tables: `_Encoder.element` and `body` (100 lines) have
  special cases (a lone `SubSelect` is unwrapped, `UNION` with one alternative, flags written only when true, triple order
  hook), and Manchester's tuple shapes are positional, with annotation wrappers and nested lists. I did not
  prototype them, so the saving there is an estimate: roughly the term/path and list-writing code (tens of lines), not the
  clause logic.
- The point that matters here: the sequence encoding is already behind a handful of calls in each encoder
  (about 85 grep hits for `_list(` / `_build_rdf_list(` in the three encoders, 11 `_read_list(` in `srl.py`, 15 `_read_rdf_list(`
  in Manchester, plus the `.items(` reads in `sqe/to_text.py` (20), `sqe/expr_text.py`, `sqe/entailment.py`, `_memtree.py`).
  Changing the encoding in code is mechanical; the cost is in the shapes and the SPARQL constraints that spell
  `rdf:rest*` (81 mentions of `rdf:first` / `rdf:rest` in `sqe_shapes.ttl`, 37 in `srl_shapes.ttl`, 31 in
  `manchester_shapes.ttl`, 8 in `spexpr_shapes.ttl`).

## 10. Recommendation

Do now, helpers only (no data change):

1. Make guide 06.05.3 use `graph.items` and `set_list`, and add `insert_at`, `remove_at`, `replace_at` next to `set_list`
   in `graph/rdflist.py` (about 5 lines each) if they are wanted.
2. Replace the 31 hand-copied list shapes by a generated or parameterised one (the `spexpr` generator pattern) and add the
   list-integrity checks the shipped shapes lack (loop, doubled or missing `rdf:first`, fork).

Choose C (ordinal on the child, wrapper only for literals, IRIs and nested lists) if these are decisive for you:

- RDFC-1.0 canonicalisation of an SRL tree is refused above about 11 generated rules and hash-and-reverify is a goal (section 8).
- You want `sh:class` on `srl:body` to be an ordinary property shape and the 9, 6, 13 and 3 list shapes gone (-78% of that SRL part).
- You accept two kinds of child (a typed node carries `srl:ord`, a leaf is wrapped), empty and absent meaning the same, a
  decoder that raises on a tie, a "renumber before hashing" step, and a migration of all three languages, their shapes,
  tests and guides 06.03 to 06.05.

I would not choose B: 23% more triples, slower on two of three constraints (VariableInUse 3 times), and no shape or hash advantage over C.
Gapped indices add nothing for a tree (insertion is rare and a renumber is cheap) and make hashes depend on history.

Deciding criteria, with the numbers that moved them: edit lines (A helpers 1 to 3; C 3 to 4; B up to 11); list-shape lines
(265, 58, 88); constraint time at 40 rules (A 1536 ms, C 917, B 2110 for three constraints plus structure); hash refusal (A
at 12 rules); triple count (-5% C, +23% B, +25% B at 40 rules); migration cost (three encoders, three shape files, tests,
guides).

If C were adopted, the files that change (from grep, not exhaustive): `sparql/parse_sparql.py` (`_list`, `_Encoder`),
`sparql/srl.py` (`_Writer`, `_read_list` and the decoders), `starontology/manchester/__init__.py` (list helpers, encoders,
decoders, `_preflight` loop check), `sparql/sqe/to_text.py`, `sparql/sqe/expr_text.py`, `sparql/sqe/_memtree.py`
(`TreeIndex.items`), `sparql/sqe/entailment.py` and `rewrite.py`, possibly `sparql/check.py` (their `.items(` hits not
checked one by one), the ontologies `srl-ontology.ttl`, `sqe-ontology.ttl`, `manchester-ast-ontology.ttl`,
`spexpr-ontology.ttl` (the new terms, domain and range), the shapes `srl_shapes.ttl`, `sqe_shapes.ttl`,
`manchester_shapes.ttl`, `spexpr_shapes.ttl`, `sparql/sqe/shapes.py` if it hard-codes list paths, the tests for to_rdf,
shapes and round trips of the three languages, and guides 06.03, 06.04, 06.05 (06.05.3 especially).

## 11. What I could not verify

- Timings are one machine with other processes running; two full runs agree within about 5%, but I did not control for
  CPU frequency or run on a quiet machine.
- Only three of the 14 section 4.2 constraints were ported and timed; the rest of `srl_validate` (and SQE's and
  Manchester's validation) for B and C is not measured. The generated rule sets are not the 40-rule set behind the 585 ms figure.
- Shape sizes for SQE and Manchester are counted for the list shapes only; I did not rewrite those files. Nothing was
  measured for SQE constraints (for example the unbound projected variable one).
- The `spexpr:` expression lists (function arguments, `IN` lists) were left as `rdf:List` in the timing runs; the all-lists
  triple counts include them, the shape and speed numbers do not.
- A tie-break policy, the empty-versus-absent question and shared nodes (a child under two parents) are described, not
  solved. The back converter uses a table of empty lists per class for SRL, and a schema inferred from the tree for SQE and
  Manchester (adequate for text round trips; exact isomorphism could differ where an instance omits a list that a sibling carries).
- Helper API sizes for B and C are estimates from the snippets, not written as library functions.
- Why guide 06.05.3 does not use `set_list` was not investigated.
