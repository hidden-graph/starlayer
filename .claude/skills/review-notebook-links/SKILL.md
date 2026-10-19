---
name: review-notebook-links
description: Review links from guide notebook cells to the code they demonstrate, when `python scripts/check_notebook_links.py` reports a cell as edited, moved or broken, or when adding new links. Decides whether each cell still demonstrates its symbols, then fixes the link or restamps it.
---

# Review notebook links

The links live in `packages/starlayer/starlayer/codekg/curated/notebook-links.ttl` (hand-edited; vocabulary in
`codekg/ontology.ttl`, shapes in `codekg/notebook-links-shapes.ttl`, logic in `starlayer.codekg.notebook_links`).
A link names a guide cell by notebook path and cell id, the dotted identifiers of the symbols it demonstrates, one
sentence saying why, and a hash of the cell as of the last review. The hash answers "did it change". This skill
answers "is it still a good relationship".

Notebooks are never edited from here. If a cell is wrong or missing something, say so and wait to be told.

## Reviewing flagged links

1. Run `python scripts/check_notebook_links.py`. Each line is `edited`, `moved` or `broken` with a reason.
2. For each flagged link run `python scripts/check_notebook_links.py --show NAME`. It prints the link, its reason, the
   cell as it is now, and the `git log -p` command that shows what changed since the review.
3. Run that `git log -p` command, so the review is of the change, not of the whole cell.
4. Look up each symbol as it is now: `python -m starlayer.codekg.queries run symbol-info symbol=<identifier>` (and
   `parameters-of`). The code graph can lag the source: if it disagrees with the source file, trust the file.
5. Decide, per link:
   - **Still good.** The cell still calls the symbol, in the way `why` says. A cosmetic edit, a changed example value or a
     reworded comment all count. Run `python scripts/check_notebook_links.py --restamp NAME`.
   - **Good, but `why` is stale.** The cell now shows something different about the same symbol. Rewrite `rdfs:comment`
     in the Turtle, then restamp.
   - **Wrong symbol.** The symbol was renamed or moved: fix `slkg:demonstratesIdentifier`. Check the new name exists
     (`queries.run_query("find-symbol", text=...)`), then restamp. A cell that stopped using the symbol and now uses
     another one: change the identifier, or drop the link, and say which.
   - **moved.** The cell is elsewhere: set `slkg:notebookPath` and `slkg:cellId` to the place the finding names, then
     restamp.
   - **broken, cell removed.** Remove the link, and name a replacement cell if there is one.
6. Run the check again, and `python -m pytest packages/starlayer/tests/codekg -q`, which also validates the links
   against their shapes. Report each link as kept, rewritten, repointed or removed, with the reason in a few words.
   Do not restamp a link you did not read.

## Adding links

- Write the file by hand: one `nl:<notebook-number>-<cell-id>` block per link. Copy a block, then run
  `--restamp NAME` to fill in the hash and date.
- Pick the cell that **calls** the symbol in a way a reader learns from, not the cell that imports it or merely
  mentions the name. `import`-only cells and setup helpers were the usual wrong first match.
- Check that the call is to StarLayer's symbol. A cell can use a same-named function from another library: the Getting
  Started validation cell calls `pyshacl.validate`, not `StarShaclSchema.validate`, so it is not a link.
- Method versus function: `select_widgets()` the function and `StarShaclSchema.select_widgets` the method are
  different identifiers with different cells. Link each to the cell that uses it.
- Name symbols by `dcterms:identifier` as in `functionality.ttl`. A package is `pkg.__init__`. The identifier must exist
  in the code graph; the tests fail otherwise.
- Write `why` as one true sentence about what the cell does with the symbol. If the cell does not do it, do not claim it.
- Cell ids are unique within a notebook, not across notebooks.
- A new notebook needs ids on every cell (`scripts/check_docs.py` checks it).

## What the check cannot see

It sees that the cell changed and that the symbol's name is still a word in the cell. It does not see that the cell's
text around the call became misleading, or that the symbol's behaviour changed under an unchanged name. A symbol
whose signature or docstring changed since the review deserves a look at each of its links even if its cells did not
change: `queries.run_query("callers-of"...)` is not enough here; compare `git log -p` for the symbol's file with the
review date.
