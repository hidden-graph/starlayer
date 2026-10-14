# StarLayer User Guide Style Guide

*Established 2026-10-12, following a structural/stylistic review of all 21 existing guide notebooks.*

This document is the house style for every notebook under `docs/guides/`. It exists because the guides grew organically (21 notebooks, several authors/sessions, no agreed template) and drifted into at least three incompatible section-numbering schemes, five different closing-section names, and several notebooks with leftover planning notes still visible to readers. The rules below are deliberately concrete and non-optional — "pick whichever you like" is exactly what produced the drift this document fixes.

## What kind of document a guide is

Useful background before the rules: the [Diataxis](https://diataxis.fr/) framework (the standard reference on technical documentation structure) identifies four distinct documentation modes — **tutorial** (learning-oriented, guided, assumes nothing), **how-to guide** (task-oriented, assumes competence, answers "how do I do X"), **reference** (information-oriented, exhaustive, structured around the product not the user's goal), and **explanation** (understanding-oriented, discusses *why*). Its central warning is that mixing modes in one document serves no reader well — a learner drowns in reference tables, a reference-seeker wades through tutorial preamble.

**StarLayer's guides are deliberately a how-to-guide/reference hybrid for a practitioner audience, not tutorials for beginners.** `01-getting-started.ipynb` already states this assumption explicitly ("assumes a working knowledge of RDF 1.1, SPARQL 1.1 and SHACL 1.1... using rdflib and pyshacl") — readers already know RDF/SPARQL/SHACL and rdflib/pyshacl; a guide's job is showing *what StarLayer adds or changes*, not teaching the underlying standard from scratch. Keep that framing explicit in every guide's opening (see below) rather than drifting toward either a beginner tutorial or a bare API dump — both failure modes have appeared in different guides during the review (see "Opening paragraph," below).

## 1. Guide Index cell

The very first cell of every notebook, before the title, is a single-line markdown cell containing nothing but a link to the master index:

```
[Guide Index](README.md)
```

No surrounding sentence, no heading, no other text in the cell. This is the one fixed, always-in-the-same-place way to reach the master table of contents (`docs/guides/README.md`, §9) from anywhere in any guide. It replaces the earlier approach of mentioning the index inline inside the "How to run this notebook" cell — one link, always in the same spot, rather than a sentence that had to be worded consistently across 21 notebooks.

## 2. Title cell

The second cell (right after the Guide Index link) is always:

```
# <Topic> — User Guide
```

(em dash, not a hyphen) followed immediately, same cell, by a tagline of **1–3 sentences** stating:
1. what capability/feature area this covers, and
2. at least one concrete thing it unlocks that the reader couldn't do (or would do awkwardly) without it — not just "extends X to support Y." `04f-shacl-subgraph-extraction.ipynb`'s opening (a concrete "suppose you record a signed hash of a journal entry..." scenario before any API description) is the model to follow; "`StarLayerGraph` extends rdflib's `Graph` to support RDF 1.2" on its own is not enough.

No exceptions for the entry point: `01-getting-started.ipynb` currently reads `# Getting Started with StarLayer` with no tagline — bring it into the same format as every other guide, not the reverse.

## 3. "How to run this notebook" cell

Always the **third** cell, immediately after the title — never preceded by a scratch/planning cell, never pushed later. Standard text:

> This guide assumes StarLayer has been pip installed — see [Getting Started](01-getting-started.ipynb) if not. Run cells from top to bottom; later sections may reuse variables from earlier ones.

Append, don't replace, when a guide has a real extra prerequisite (a JVM, a running Oxigraph/Fuseki instance, an optional extra like `pyshacl`/`rdflib-sqlalchemy`) — state it plainly and say what happens if it's missing (`02c-owl-dl-reasoning.ipynb`'s HermiT/Java note is the right length and specificity). State every real prerequisite here, not scattered across later sections (`06b`'s own `!pip install -q rdflib-sqlalchemy` buried mid-notebook is the anti-example).

## 4. Section numbering

**One scheme, no exceptions**: `## N. Title` for top-level sections, `### N.M Subtitle` for subsections. Number from 1. Never:
- unnumbered headings (even for a short guide — number it anyway, for consistency, not because the reader needs it for *that* guide specifically),
- a "Step 1 / Step 2" walkthrough style,
- lettered sub-subsections (`### 2.2a`),
- a bold pseudo-heading standing in for a real one (`**Example 2.1**` directly above a code cell — make it a real `###` heading or fold it into the section's own prose).

`####` is never used — if content needs a fourth level, the section is doing too much; split it into a new numbered section instead.

## 5. Opening paragraph (per guide, not just the title tagline)

One paragraph, not an essay, stating what's covered and why it matters (see §2) — then move into numbered sections. A reference-style table summarizing the whole topic (`02b-graphs-inferencing.ipynb`'s entailment-regime table) is fine as part of the opening when the guide is genuinely reference-shaped, but state the orienting sentence first, table second — never the reverse.

## 6. Closing: one section, only when there's something to say

A guide has **at most one** closing section:

- **`## Known limitations`** — only when the guide actually has gaps/unimplemented features to disclose. Omit the section entirely rather than writing an empty or padded one. This is the standardized name — replaces the current five-way split (`Further work`, `Further Reading`, `Next steps`, `What's not supported yet`, or no closing section at all for gaps content specifically).

**There is no `## See also` section, and no repeated master-list recap, at the end of a guide.** Two things replace that job, neither of which needs keeping in sync by hand:
1. The master table of contents is reachable from every notebook via the standalone Guide Index cell at the very top (§1) - always one click away, never duplicated in-body.
2. A specific sibling guide is linked **inline, in context**, wherever it's actually relevant while reading - in the opening paragraph, in a section's own prose, or right next to the construct that the other guide covers in depth (§10). This reads better than a bolted-on list at the end and can't drift the way eight independent copies of the same list did.

Do not use "Further Reading" as a closing-section name going forward - it was doing two different jobs (a navigation recap and, sometimes, a gaps list) depending on the notebook; both jobs are now handled as described above, not by a closing section at all except for `Known limitations`.

## 7. Tone

Baseline voice is impersonal third person: "`X` does `Y`," "This covers...," "A `sh:TripleRule` builds..." — this is already the dominant voice across 20 of 21 guides and stays the house style. Second person ("you can...") is fine for a direct instruction or a warning, used sparingly, not as the dominant register of a whole guide. First-person plural ("we'll show," "we introduce") is not used — `04a-shacl-node-expressions.ipynb` is the one current outlier using it and should be brought in line, not the model to extend.

## 8. Naming and code formatting: StarLayer, StarLayerGraph, and other identifiers

**`StarLayer`** is the product/project name, not a Python identifier — write it as plain text, never backticked (`StarLayer`, not `` `StarLayer` ``). Capitalization is fixed: one word, capital S, capital L, matching the project README and PyPI listing.

**Real identifiers are always code-formatted, with no exception for the two most-mentioned classes.** `` `StarLayerGraph` `` and `` `StarShaclSchema` `` get backticks every time they appear — in prose, in a heading, as the subject of a sentence — exactly like any other identifier already is (`` `sh:rule` ``, `` `owl:equivalentClass` ``, `` `apply_rules()` ``). Several guides today write a bare, unbackticked `StarLayerGraph` as a sentence or heading subject (`01-getting-started.ipynb`'s `## 2. Using StarLayerGraph`, `02-graphs.ipynb`'s "StarLayerGraph extends rdflib's..."); that inconsistency is what this rule fixes, not a pattern to continue.

## 9. The master guide index lives in exactly one place

`docs/guides/README.md` is the single source of truth for the full guide list, reading order, and one-line description of each guide. No notebook duplicates this list — every guide's own Guide Index cell links to it instead (§1/§6). When a guide is added, renamed, or reordered, update `docs/guides/README.md` once; every notebook already points there via the same standard link and needs no further change.

`docs/guides/README.md` itself must stay current — at the time this style guide was written it was already missing `3.b` and `5.f` from its own list and had a stale parameter name (`infer(profile=...)`, renamed to `entailment=` back on 2026-10-07) in its 5.e description. Fixing that file is part of adopting this style guide, not a separate task.

## 10. Cross-referencing

- **Sibling guides**: always a real markdown link with descriptive text, `[Topic](NNx-filename.ipynb)`, optionally with a heading anchor (`02b-graphs-inferencing.ipynb#2.4-Detecting-inconsistencies`) when pointing at one specific subsection rather than a whole guide.
- **Deeper project docs** (`CLAUDE.md` files, the gap-matrix, `functionality-overview.md`, `api-reference.md`): also real markdown links from now on, not bare backtick-quoted paths — e.g. `[shacl12-gap-matrix.md](../../packages/starlayer/docs/shacl/shacl12-gap-matrix.md)`, not `` `packages/starlayer/docs/shacl/shacl12-gap-matrix.md` ``. A bare path isn't clickable in a rendered notebook; a link is, and costs nothing extra. This is a deliberate change from the currently-dominant-but-inconsistent practice, not a continuation of it.
- `docs/api-reference.md` and `docs/future_enhancements.md` are currently never linked from any of the 21 guides. At minimum, `docs/guides/README.md`'s own "Related project documentation" section should point to `api-reference.md` (it already links `functionality-overview.md`) — a reader who wants the exhaustive, reference-style name-by-name surface currently has no path there from the guides at all.

## 11. No leftover authoring notes, ever

A guide is not done while it contains a scratch note, an open question to a future editor, or a literal `CLAUDE:` directive — whether in its own leading cell or embedded mid-content in a cell a reader will actually see. This is a zero-tolerance rule, not a judgment call: seven of the current 21 guides fail it today (see the review notes for the full list), and `05a-manchester-syntax.ipynb` (renamed from `05f-`, see `README.md`) has directives embedded inside its own title and prerequisites cells, not just a quarantined leading cell. Before considering any guide finished: read every cell once as a first-time reader would, and remove anything that isn't meant for them.

## 12. Scope and size

No hard cap, but a guideline: if a guide grows past roughly 40–50 cells, it's probably covering more than one coherent topic and should split into a core guide plus one or more satellites, the same way `04-shacl-shapes.ipynb` already spawned `04a`–`04f`. `04a-shacl-node-expressions.ipynb` (93 cells, by far the largest guide — bigger than any "core" guide in the set) is the clearest current candidate; splitting it is a separate, deliberate task, not implied by adopting this style guide.

## 13. Template for a new guide

```markdown
[Guide Index](README.md)
```
```markdown
# <Topic> — User Guide

<1–3 sentence tagline: what this covers, and one concrete thing it unlocks.>
```
```markdown
## How to run this notebook

This guide assumes StarLayer has been pip installed — see [Getting Started](01-getting-started.ipynb) if not. Run cells from top to bottom; later sections may reuse variables from earlier ones.
<+ any real extra prerequisite, stated plainly.>
```
```markdown
## 1. <First topic>

<One paragraph, then code. Link a sibling guide inline, right here, if one is
directly relevant to this section - not collected into a list at the end.>
```
```markdown
## Known limitations

<Only if real gaps exist - otherwise omit this section entirely.>
```
