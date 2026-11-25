#!/usr/bin/env python
"""Mechanical rewrites for the guide renumbering (plan: docs/working/guide-renumbering-plan-2026-11-25.md).

The renumbering is done one chapter (or one notebook) at a time. This script computes the rewrites; it never pushes to the
working guides. ``apply`` writes into a target directory laid out like the staging copy, so a later step can compare and
push the result with ``scripts/guide_staging.py``.

Commands (``--root`` is the repository root, for tests):

- ``plan [--chapter NN] [--only FILE]``: a dry run. Per notebook: the new file name, the heading rewrites (with the rule that
  fired), the link rewrites, the in-text rewrites it is sure about, and what it will not touch and flags for a person (cell id and
  sentence), with counts. Writes nothing. The notebooks of other chapters that link into the chapter are listed as referrers: only
  their link cells (and ids in prose) change.
- ``apply --chapter NN --target DIR [--only FILE] [--with-proposals] [--remove-old]``: writes the rewritten notebooks, under their new
  names, to ``DIR/docs/guides``. Referrer notebooks are written with only their link cells changed. Cell ids, metadata and the JSON
  formatting are kept; only the text the rules rewrite changes, and a code cell changes only on a comment line that cites a section.
  A "decision" item carries a proposed text where one can be worked out; it is written only with ``--with-proposals``.
- ``verify --chapter NN [--source DIR]``: the checks of the plan on the working guides after a push: headings fully qualified,
  every ``.ipynb`` link and ``#anchor`` resolves, no old file name of the chapter remains in a guide.
- ``check [--chapter NN]``: every remaining old reference (file names and old ids) in the guides, README, scripts, tests, ttl,
  json and docs. ``leftovers`` is the repository-wide form (tracked files, with the allowed-historical list); exit 1 on a hit
  that must be fixed.
- ``plan-files`` / ``apply-files [--chapter NN] [--group stage|cleanup|all]``: the same for the files that are not guides (README
  rows, STYLE_GUIDE, user-guide-version.json, notebook-links.ttl, the tests, comments in the ontology sources, live docs).

The stages of the plan run in the order ``STAGES``; a chapter's run rewrites links into that chapter and into the chapters of
the stages before it. A link into a chapter that is not renamed yet is left alone.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
GUIDES = "docs/guides"

# ---- the mapping table (plan, section 1) -------------------------------------------------------------------------------------
# (old file, new file). The title part of the name is kept. 05.01 to 05.03 and the appendices keep their names.
GUIDE_MAP: tuple[tuple[str, str], ...] = (
    ("01-getting-started.ipynb", "01.01-getting-started.ipynb"),
    ("02-graphs.ipynb", "02.01-graphs.ipynb"),
    ("02a-graphs-datasets.ipynb", "02.02-graphs-datasets.ipynb"),
    ("02b-oxigraph-wrapper.ipynb", "02.03-oxigraph-wrapper.ipynb"),
    ("02c-graph-content.ipynb", "02.04-graph-content.ipynb"),
    ("02d-combining-comparing-graphs.ipynb", "02.05-combining-comparing-graphs.ipynb"),
    ("02e-graphs-inferencing.ipynb", "02.06-graphs-inferencing.ipynb"),
    ("02f-owl-dl-reasoning.ipynb", "02.07-owl-dl-reasoning.ipynb"),
    ("03-sparql.ipynb", "03.01-sparql.ipynb"),
    ("03a-sparql-12-queries.ipynb", "03.02-sparql-12-queries.ipynb"),
    ("03b-preparing-extending-checking-queries.ipynb", "03.03-preparing-extending-checking-queries.ipynb"),
    ("03c-sparql-entailment.ipynb", "03.04-sparql-entailment.ipynb"),
    ("04-srl-sparql-rules.ipynb", "04.01-srl-sparql-rules.ipynb"),
    ("04a-srl-running-rule-sets.ipynb", "04.02-srl-running-rule-sets.ipynb"),
    ("04b-srl-more-features.ipynb", "04.03-srl-more-features.ipynb"),
    ("04c-srl-vs-sparql.ipynb", "04.04-srl-vs-sparql.ipynb"),
    ("05.01-validating-with-shacl-1.2.ipynb", "05.01-validating-with-shacl-1.2.ipynb"),
    ("05.02-starlayer-shacl-engine.ipynb", "05.02-starlayer-shacl-engine.ipynb"),
    ("05.03-shapes-as-classes.ipynb", "05.03-shapes-as-classes.ipynb"),
    ("05a-shacl-node-expressions.ipynb", "05.04-shacl-node-expressions.ipynb"),
    ("05b-shacl-and-sparql.ipynb", "05.05-shacl-and-sparql.ipynb"),
    ("05c-shacl-inference-rules.ipynb", "05.06-shacl-inference-rules.ipynb"),
    ("05d-shacl-ui.ipynb", "05.07-shacl-ui.ipynb"),
    ("05e-shacl-profiling.ipynb", "05.08-shacl-profiling.ipynb"),
    ("05f-shacl-subgraph-extraction.ipynb", "05.09-shacl-subgraph-extraction.ipynb"),
    ("05g-building-on-shacl.ipynb", "05.10-building-on-shacl.ipynb"),
    ("05h-shacl-evaluate.ipynb", "05.11-shacl-evaluate.ipynb"),
    ("06-starlayer-schemas-and-ontologies.ipynb", "06.01-starlayer-schemas-and-ontologies.ipynb"),
    ("06a-manchester-syntax.ipynb", "06.02-manchester-syntax.ipynb"),
    ("06b-sparql-query-as-rdf.ipynb", "06.03-sparql-query-as-rdf.ipynb"),
    ("06c-srl-sparql-rules-as-rdf.ipynb", "06.04-srl-sparql-rules-as-rdf.ipynb"),
    ("06d-shacl-library-registry.ipynb", "06.05-shacl-library-registry.ipynb"),
    ("07a-serialization-formats.ipynb", "07.01-serialization-formats.ipynb"),
    ("07b-backend-graph-databases.ipynb", "07.02-backend-graph-databases.ipynb"),
    ("07c-canonical-hashing.ipynb", "07.03-canonical-hashing.ipynb"),
    ("appendix-a-public-resources.ipynb", "appendix-a-public-resources.ipynb"),
    ("appendix-b.ipynb", "appendix-b.ipynb"),
    ("appendix-b1-sqe-shared-parts.ipynb", "appendix-b1-sqe-shared-parts.ipynb"),
    ("appendix-b2-dl-reasoning-examples.ipynb", "appendix-b2-dl-reasoning-examples.ipynb"),
)

# The parked notes follow their guide (plan, question 2); nothing links to them.
PARKED_MAP: tuple[tuple[str, str], ...] = (
    ("parked-02b-oxigraph-wrapper.md", "parked-02.03-oxigraph-wrapper.md"),
    ("parked-02d-combining-comparing-graphs.md", "parked-02.05-combining-comparing-graphs.md"),
    ("parked-02f-owl-dl-reasoning.md", "parked-02.07-owl-dl-reasoning.md"),
)

# The stages, in the user's order (plan, section 6).
STAGES: tuple[str, ...] = ("05", "07", "06", "04", "03", "02", "01")

_NEW_NAME = re.compile(r"^\d\d\.\d\d-")


@dataclass(frozen=True)
class Row:
    old: str
    new: str
    old_id: str | None
    new_id: str | None

    @property
    def chapter(self) -> str | None:
        return self.new_id[:2] if self.new_id else None

    @property
    def renamed(self) -> bool:
        return self.old != self.new


def _row(old: str, new: str) -> Row:
    old_id = re.match(r"^(\d\d(?:\.\d\d|[a-h])?)-", old)
    new_id = re.match(r"^(\d\d\.\d\d)-", new)
    return Row(old, new, old_id.group(1) if old_id else None, new_id.group(1) if new_id else None)


ROWS: tuple[Row, ...] = tuple(_row(o, n) for o, n in GUIDE_MAP)
BY_FILE: dict[str, Row] = {}
for _r in ROWS:
    BY_FILE[_r.old] = _r
    BY_FILE[_r.new] = _r
ID_MAP: dict[str, str] = {r.old_id: r.new_id for r in ROWS if r.renamed and r.old_id and r.new_id}  # '05c' -> '05.06'
OLD_STEMS: tuple[str, ...] = tuple(r.old[: -len(".ipynb")] for r in ROWS if r.renamed)
LETTER_ID = re.compile(r"(?<![\w./#:-])(0[1-7][a-h])(?![\w-])")
DOTTED_ID = re.compile(r"(?<![\w.])([1-7])\.([a-h])(?![\w.-])")
CHAPTER_ID = re.compile(r"(?<![\w./#:-])(0[1-7])(?![\w.:/-])(?!-\d)")


def chapters_done(chapter: str) -> set[str]:
    """The chapters whose names are renamed when the run for ``chapter`` has finished (this one and the earlier stages)."""
    return set(STAGES[: STAGES.index(chapter) + 1])


def other_rows_of(chapter: str) -> list[Row]:
    return [r for r in ROWS if r.chapter == chapter]


# ---- reading and writing notebooks -------------------------------------------------------------------------------------------
def dump(nb: dict) -> bytes:
    """The bytes the repo writes: the same as ``guide_staging._dump``."""
    return (json.dumps(nb, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def load_guides(guides: Path) -> dict[str, dict]:
    return {p.name: json.loads(p.read_bytes()) for p in sorted(guides.glob("*.ipynb"))}


def cell_text(cell: dict) -> str:
    src = cell["source"]
    return src if isinstance(src, str) else "".join(src)


def set_cell_text(cell: dict, text: str) -> None:
    cell["source"] = text if isinstance(cell["source"], str) else text.splitlines(keepends=True)


# ---- headings ----------------------------------------------------------------------------------------------------------------
_FENCE = re.compile(r"^ {0,3}(```|~~~)")
_HEADING = re.compile(r"^(#{1,4}) (.*?)\s*$")
_QUAL = re.compile(r"^(\d\d\.\d\d)\.(\d+(?:\.\d+)*)(?=\s|$)")
_REL = re.compile(r"^\.(\d+(?:\.\d+)*)(?=\s|$)")
_OLD = re.compile(r"^(\d+(?:\.\d+)*)(\.?)(?=\s|$)")
_H1_ID = re.compile(r"^(\d\d(?:\.\d\d|[a-h])?)(?=\s)")


@dataclass
class Heading:
    cell: str
    line: int  # line index inside the cell
    level: int
    text: str  # the text after the hashes, as written
    form: str  # 'old', 'qual', 'rel', 'none', or for level 1 'id', 'qual1', 'none'
    nums: tuple[int, ...] = ()
    prefix: str | None = None  # the guide prefix of a qualified heading
    old_id: str | None = None  # level 1


def _classify(level: int, text: str) -> Heading:
    h = Heading("", 0, level, text, "none")
    if level == 1:
        m = _H1_ID.match(text)
        if m:
            h.old_id = m.group(1)
            h.form = "qual1" if "." in m.group(1) else "id"
        return h
    m = _QUAL.match(text)
    if m:
        h.form, h.prefix, h.nums = "qual", m.group(1), tuple(int(x) for x in m.group(2).split("."))
        return h
    m = _REL.match(text)
    if m:
        h.form, h.nums = "rel", tuple(int(x) for x in m.group(1).split("."))
        return h
    m = _OLD.match(text)
    if m:
        h.form, h.nums = "old", tuple(int(x) for x in m.group(1).split("."))
    return h


def heading_lines(nb: dict):
    """Yield (cell, line index, line text without its newline, in_fence) for every line of every markdown cell."""
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        fenced = False
        for i, line in enumerate(cell_text(cell).split("\n")):
            if _FENCE.match(line):
                fenced = not fenced
                continue
            yield cell["id"], i, line, fenced


def headings(nb: dict) -> list[Heading]:
    found: list[Heading] = []
    for cell_id, i, line, fenced in heading_lines(nb):
        m = None if fenced else _HEADING.match(line)
        if m:
            h = _classify(len(m.group(1)), m.group(2))
            h.cell, h.line = cell_id, i
            found.append(h)
    return found


def anchor_of(heading_text: str) -> str:
    """The anchor of a heading in a notebook link: the heading text with spaces as hyphens, case kept (plan, 3.3)."""
    return re.sub(r"\s+", "-", heading_text.strip())


def qualified(row: Row, nums) -> str:
    return f"{row.new_id}." + ".".join(str(n) for n in nums)


def heading_rewrite(h: Heading, row: Row) -> tuple[int, str, str] | None:
    """(length of the old number token, the new token, the rule) for a heading that changes, None when it stays.

    Raises ValueError for a heading the rules do not know. The text after the token is never touched."""
    if row.new_id is None or row.old_id is None:
        return None  # an appendix keeps its headings (plan, question 9)
    if h.level == 1:
        if h.form == "none":
            return None
        if h.old_id not in (row.old_id, row.new_id):
            raise ValueError(f"H1 names {h.old_id!r}, the file is {row.old_id!r}")
        return None if h.old_id == row.new_id else (len(h.old_id), row.new_id, "H1")
    if h.form == "none":
        if re.match(r"^\d", h.text) and h.level == 2:
            raise ValueError(f"numbered-looking heading not recognised: {h.text!r}")
        return None
    if h.form == "qual":
        if h.prefix != row.new_id:
            raise ValueError(f"heading {h.text!r} carries the prefix {h.prefix}, the guide is {row.new_id}")
        return None
    m = {"old": _OLD, "rel": _REL}[h.form].match(h.text)
    depth = {2: 1, 3: 2, 4: 3}[h.level]
    if len(h.nums) != depth:
        raise ValueError(f"a level-{h.level} heading has the number {'.'.join(map(str, h.nums))}: {h.text!r}")
    return m.end(), qualified(row, h.nums), f"H{h.level}" + ("-relative" if h.form == "rel" else "")


def new_heading_text(h: Heading, row: Row) -> tuple[str, str | None]:
    """(the heading text after the hashes as it will read, the rule that fired or None)."""
    r = heading_rewrite(h, row)
    return (h.text, None) if r is None else (r[1] + h.text[r[0] :], r[2])


def check_headings(hs: list[Heading], row: Row) -> list[str]:
    """The sanity checks of the plan (3.2): no gap in the H2 numbers, each H3/H4 prefixed by its parent, numbers unique."""
    problems: list[str] = []
    if row.new_id is None:
        return problems
    seen: dict[tuple[int, ...], str] = {}
    last2: tuple[int, ...] = ()
    last3: tuple[int, ...] = ()
    expect = 1
    for h in hs:
        if h.level == 1 or h.form == "none":
            continue
        if h.nums in seen:
            problems.append(f"duplicate number {'.'.join(map(str, h.nums))}: {h.text!r} and {seen[h.nums]!r}")
        seen[h.nums] = h.text
        if h.level == 2:
            if h.nums != (expect,):
                problems.append(f"gap or order in the ## numbers: expected {expect}, found {h.text!r}")
            expect = h.nums[0] + 1
            last2, last3 = h.nums, ()
        elif h.level == 3:
            if h.nums[:-1] != last2:
                problems.append(f"### number does not extend the preceding ##: {h.text!r}")
            last3 = h.nums
        elif h.nums[:-1] != last3:
            problems.append(f"#### number does not extend the preceding ###: {h.text!r}")
    return problems


# ---- the line engine ---------------------------------------------------------------------------------------------------------
@dataclass
class Edit:
    start: int
    end: int
    new: str  # applied always
    alt: str | None = None  # applied instead of ``new`` with --with-proposals
    rule: str = ""


@dataclass
class Change:
    rule: str
    cell: str
    old: str
    new: str
    sentence: str


@dataclass
class Flag:
    category: str  # 'decision', 'left', 'deferred', 'unmapped'
    rule: str
    cell: str
    text: str
    sentence: str
    proposal: str | None = None


_CODE_SPAN = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")
_LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<dir>[^()\s#]*?)(?P<file>[\w.-]+\.ipynb)(?P<anchor>#[^()\s]*)?\)")
_ANY_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)|https?://[^\s)>\]]+")
_SECTION = re.compile(
    r"(?P<word>\b[Ss]ections?)\s+(?P<num>\.?\d+(?:\.\d+)*)(?P<more>(?:\s*(?:,|and|or|&|to|[-\u2013])\s*\d+(?:\.\d+)*(?![\d.]))*)"
)
_SECTION_SIGN = re.compile(r"§\s*\d+(?:\.\d+)*")
_QUALIFIED_ANY = re.compile(r"\b(\d\d\.\d\d)(?:\.\d+)+\b")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[*]*[A-Z])|\s*\|\s*")
_FILE_NAME = re.compile(r"(?<![\w./-])([\w.-]+\.ipynb)(?![\w-])")
_BULLET_REL = re.compile(r"^(\s*(?:[-*+]|\d+\.)\s+\*\*)\.(\d+(?:\.\d+)+)(?=\s)")
_GUIDE_MARKER = re.compile(
    r"\.ipynb|\bguides?\b|\bspec(?:ification)?s?\b|\bdraft\b|w3\.org|\bW3C\b|\beditor's\b|"
    r"\b(?:SRL|SHACL|SPARQL|RDF|OWL|Profiling|Turtle)\s+(?:\d[\d.]*\s+)?[Ss]ections?\b",
    re.I,
)


def code_spans(line: str) -> list[tuple[int, int]]:
    return [m.span() for m in _CODE_SPAN.finditer(line)]


def _inside(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b in spans)


def sentence_at(line: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _SENT_SPLIT.finditer(line):
        if m.end() <= pos:
            start = m.end()
        elif m.start() >= pos:
            return start, m.start()
    return start, len(line)


def neutral(text: str, width: int = 240) -> str:
    """A sentence as plain text for a report: a link is not written as a link, so no link check follows it."""
    text = text.replace("](", "] (").strip()
    return text if len(text) <= width else text[: width - 3] + "..."


def apply_edits(line: str, edits: list[Edit], proposals: bool) -> str:
    for e in sorted(edits, key=lambda e: e.start, reverse=True):
        new = e.alt if (proposals and e.alt is not None) else e.new
        line = line[: e.start] + new + line[e.end :]
    return line


@dataclass
class Ctx:
    row: Row
    scope: str  # 'primary' or 'referrer'
    link_chapters: set[str]  # chapters whose names are rewritten in this run
    guides: dict[str, dict]
    proposals: bool = False
    own_old_nums: set[tuple[int, ...]] = field(default_factory=set)
    head_cache: dict[str, list[Heading]] = field(default_factory=dict)

    def heads(self, file: str) -> list[Heading]:
        if file not in self.head_cache:
            self.head_cache[file] = headings(self.guides[file]) if file in self.guides else []
        return self.head_cache[file]


def guide_file(ctx: Ctx, name: str) -> str | None:
    """The name a mapped guide has in the guides we read: the old name or the new one."""
    row = BY_FILE.get(name)
    if row is None:
        return None
    return row.old if row.old in ctx.guides else (row.new if row.new in ctx.guides else None)


def _target_in_scope(ctx: Ctx, row: Row) -> bool:
    return row.chapter in ctx.link_chapters


def retarget_link(ctx: Ctx, m: re.Match, cell: str, line: str, changes: list, flags: list) -> Edit | None:
    """The edit for one link (file name, anchor, text), or None."""
    name = m.group("file")
    row = BY_FILE.get(name)
    if row is None:
        flags.append(Flag("unmapped", "link-target", cell, m.group(0), neutral(line)))
        return None
    if not _target_in_scope(ctx, row):
        return None
    text, anchor = m.group("text"), m.group("anchor") or ""
    new_anchor = anchor
    if anchor:
        old_file = guide_file(ctx, name)
        found = None
        if old_file:
            for h in ctx.heads(old_file):
                if h.level > 1 and anchor_of(h.text) == anchor[1:]:
                    found = h
                    break
        if found is None:
            flags.append(Flag("decision", "link-anchor", cell, m.group(0), neutral(line)))
        else:
            try:
                new_text, _rule = new_heading_text(found, row)
            except ValueError:
                new_text = found.text
            new_anchor = "#" + anchor_of(new_text)
    new_text_link, alt_text = text, None
    if text in (row.old_id, row.old[:-6]) or text == row.old:
        new_text_link = {row.old_id: row.new_id, row.old[:-6]: row.new[:-6], row.old: row.new}[text]
    elif LETTER_ID.fullmatch(text) or re.fullmatch(r"0[1-7]", text):
        if text in ID_MAP or re.fullmatch(r"0[1-7]", text):
            flags.append(Flag("decision", "link-text-id", cell, m.group(0), neutral(line), row.new_id))
            alt_text = row.new_id
    elif DOTTED_ID.fullmatch(text):
        flags.append(Flag("decision", "dotted-id", cell, m.group(0), neutral(line), row.new_id))
        alt_text = row.new_id
    new_target = f"{m.group('dir')}{row.new}{new_anchor}"
    new = f"[{new_text_link}]({new_target})"
    alt = f"[{alt_text}]({new_target})" if alt_text else None
    if new == m.group(0) and alt is None:
        return None
    if new != m.group(0):
        if row.renamed:
            changes.append(Change("link-target", cell, name + anchor, row.new + new_anchor, neutral(line)))
        elif new_anchor != anchor:
            changes.append(Change("link-anchor", cell, name + anchor, row.new + new_anchor, neutral(line)))
        if new_text_link != text:
            changes.append(Change("link-text", cell, text, new_text_link, neutral(line)))
        if row.renamed and new_anchor != anchor:
            changes.append(Change("link-anchor", cell, anchor, new_anchor, neutral(line)))
    return Edit(m.start(), m.end(), new, alt, "link")


def _sentence_markers(ctx: Ctx, sent: str, own: Row) -> list[str]:
    """What in this sentence points at a guide or a specification other than the cell's own guide."""
    text = re.sub(r"\bthis guide\b", "", sent, flags=re.I)
    found = [m.group(0) for m in _GUIDE_MARKER.finditer(text)]
    found += [m.group(0) for m in LETTER_ID.finditer(sent)]
    for m in _QUALIFIED_ANY.finditer(sent):
        if m.group(1) != own.new_id:
            found.append(m.group(0))
    return found


def _mentions(sent: str) -> list[tuple[int, int, Row]]:
    """The guides a sentence names: links to a guide, and old letter ids."""
    found = [(m.start(), m.end(), BY_FILE[m.group("file")]) for m in _LINK.finditer(sent) if m.group("file") in BY_FILE]
    for m in LETTER_ID.finditer(sent):
        if not any(a <= m.start() < b for a, b, _ in found):
            found += [(m.start(), m.end(), r) for r in ROWS if r.old_id == m.group(1)]
    return found


def _near_referent(sent: str, a: int, b: int) -> Row | None:
    """The guide a 'section N' in ``sent[a:b]`` belongs to: the link it sits in, the one just before it ('[05c](...), section 2'),
    or the one just after it ('section 5 of the [inferencing guide](...)'). None when nothing is that close."""
    for s0, e0, row in _mentions(sent):
        if s0 <= a and b <= e0:
            return row
        if e0 <= a and re.fullmatch(r"[\s,;:()\u2014-]{0,6}", sent[e0:a]):
            return row
        if s0 >= b and re.fullmatch(r"\s*(?:of|in|from)\s+(?:the\s+)?[^\[\]()]{0,40}", sent[b:s0]):
            return row
    return None


def _resolves(ctx: Ctx, row: Row, nums: list[tuple[int, ...]]) -> bool:
    file = guide_file(ctx, row.old)
    have = {h.nums for h in ctx.heads(file) if h.nums} if file else set()
    return bool(nums) and all(n in have for n in nums)


def section_refs(ctx: Ctx, line: str, offset: int, cell: str, kind: str, edits: list, changes: list, flags: list) -> None:
    """Rule 5: 'section N' references in ``line[offset:]``. ``kind`` is 'markdown' or 'code' (a comment)."""
    spans = code_spans(line)
    for fix in KNOWN_FIXES.get((ctx.row.old, cell), ()):
        at = line.find(fix["old"], offset)
        if at >= 0:
            edits.append(Edit(at, at + len(fix["old"]), fix["old"], fix["new"], "known-fix"))
            flags.append(Flag("decision", "known-fix", cell, fix["old"], neutral(line), fix["new"]))
    taken = [(e.start, e.end) for e in edits if e.rule == "known-fix"]
    for m in _SECTION.finditer(line, offset):
        if _inside(m.start(), spans) or _inside(m.start(), taken):
            continue
        s0, s1 = sentence_at(line, m.start())
        sent = line[s0:s1]
        refs = [(m.start("num"), m.end("num"), m.group("num"))]
        refs += [(m.start("more") + r.start(), m.start("more") + r.end(), r.group(0)) for r in re.finditer(r"\d+(?:\.\d+)*", m.group("more"))]
        if any(_QUAL_NUM.match(t) for _, _, t in refs):
            continue  # already the target scheme (pattern F of the plan)
        nums = [_nums(t) for _, _, t in refs]
        if any(n is None for n in nums):
            continue
        shown = neutral(sent)
        near = _near_referent(sent, m.start() - s0, m.end() - s0)
        if ctx.scope == "referrer":
            if near and near.chapter in ctx.link_chapters and near is not ctx.row:
                if _resolves(ctx, near, nums):
                    props = [qualified(near, n) for n in nums]
                    for (a, b, t), p in zip(refs, props, strict=True):
                        edits.append(Edit(a, b, t, p, "section-ref"))
                    flags.append(Flag("decision", "section-other-guide", cell, m.group(0), shown, " and ".join(props)))
                else:
                    flags.append(Flag("left", "section-unresolved", cell, m.group(0), shown))
            continue
        if re.search(r"[-\u2013]|\bto\b", m.group("more")):  # a range: written out in full only as a proposal
            if _resolves(ctx, ctx.row, nums):
                text = " to ".join(qualified(ctx.row, n) for n in (nums[0], nums[-1]))
                edits.append(Edit(refs[0][0], refs[-1][1], line[refs[0][0] : refs[-1][1]], text, "section-ref"))
                flags.append(Flag("decision", "section-range", cell, m.group(0), shown, text))
            else:
                flags.append(Flag("left", "section-unresolved", cell, m.group(0), shown))
            continue
        relative = any(t.startswith(".") for _, _, t in refs)
        own = all(n in ctx.own_old_nums for n in nums)
        markers = _sentence_markers(ctx, sent, ctx.row)
        if relative:
            row = near if near and near is not ctx.row else ctx.row
            props = [qualified(row, n) for n in nums] if _resolves(ctx, row, nums) else None
            if props and row.chapter in ctx.link_chapters:
                for (a, b, t), p in zip(refs, props, strict=True):
                    edits.append(Edit(a, b, t, p, "section-ref"))
            flags.append(Flag("decision", "section-relative", cell, m.group(0), shown, " and ".join(props) if props else None))
        elif markers:
            if near and near is not ctx.row:
                if not _resolves(ctx, near, nums):
                    flags.append(Flag("left", "section-unresolved", cell, m.group(0), shown))
                elif near.chapter in ctx.link_chapters:
                    props = [qualified(near, n) for n in nums]
                    for (a, b, t), p in zip(refs, props, strict=True):
                        edits.append(Edit(a, b, t, p, "section-ref"))
                    flags.append(Flag("decision", "section-other-guide", cell, m.group(0), shown, " and ".join(props)))
                else:
                    flags.append(Flag("deferred", "section-other-guide", cell, m.group(0), shown))
            elif own:
                flags.append(Flag("decision", "section-with-marker", cell, m.group(0), shown))
            else:
                flags.append(Flag("left", "section-unresolved", cell, m.group(0), shown))
        elif own:
            new_nums = [qualified(ctx.row, n) for n in nums]
            for (a, b, _t), p in zip(refs, new_nums, strict=True):
                edits.append(Edit(a, b, p, None, "section-ref"))
            after = m.group(0)
            for (a, b, _t), p in sorted(zip(refs, new_nums, strict=True), key=lambda x: -x[0][0]):
                after = after[: a - m.start()] + p + after[b - m.start() :]
            changes.append(Change("code-comment" if kind == "code" else "section-ref", cell, m.group(0), after, shown))
        else:
            flags.append(Flag("left", "section-unresolved", cell, m.group(0), shown))
    if kind != "code":
        for m in _SECTION_SIGN.finditer(line, offset):
            if not _inside(m.start(), spans):
                flags.append(Flag("left", "spec-sign", cell, m.group(0), neutral(sentence_text(line, m.start()))))


_QUAL_NUM = re.compile(r"^\d\d\.\d\d(\.|$)")


def _nums(t: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in t.lstrip(".").split("."))
    except ValueError:
        return None


def sentence_text(line: str, pos: int) -> str:
    a, b = sentence_at(line, pos)
    return line[a:b]


def process_markdown_line(ctx: Ctx, line: str, cell: str, h: Heading | None, changes: list, flags: list) -> str:
    """Rewrite one markdown line (without its newline). The order follows the plan: links, link text, heading, bullets, sections, ids."""
    spans = code_spans(line)
    # (1) and (2): links and their text
    edits: list[Edit] = []
    for m in _LINK.finditer(line):
        if _inside(m.start(), spans):
            continue
        e = retarget_link(ctx, m, cell, line, changes, flags)
        if e:
            edits.append(e)
    # a non-ipynb mention of an old file name
    for m in _FILE_NAME.finditer(line):
        name = m.group(1)
        if _inside(m.start(), spans) or any(e.start <= m.start() < e.end for e in edits):
            continue
        if any(a <= m.start() < b for a, b in (x.span() for x in _ANY_LINK.finditer(line))):
            continue
        row = BY_FILE.get(name)
        if row and row.renamed and _target_in_scope(ctx, row) and name == row.old:
            edits.append(Edit(m.start(), m.end(), row.new, None, "file-name"))
            changes.append(Change("file-name", cell, name, row.new, neutral(line)))
    out = apply_edits(line, edits, ctx.proposals)
    # (3) heading
    if h is not None and ctx.scope == "primary":
        hm = _HEADING.match(out)
        if hm:
            hh = _classify(len(hm.group(1)), hm.group(2))
            r = heading_rewrite(hh, ctx.row)
            if r:
                at = len(hm.group(1)) + 1
                out = out[:at] + r[1] + out[at + r[0] :]
                changes.append(Change(r[2], cell, line.rstrip(), out.rstrip(), ""))
        return out
    if _HEADING.match(out):
        return out
    spans = code_spans(out)
    edits = []
    # (4) overview bullets
    if ctx.scope == "primary":
        bm = _BULLET_REL.match(out)
        if bm:
            new_num = qualified(ctx.row, tuple(int(x) for x in bm.group(2).split(".")))
            edits.append(Edit(bm.start(2) - 1, bm.end(2), new_num, None, "bullet-relative"))
            changes.append(Change("bullet-relative", cell, "." + bm.group(2), new_num, neutral(out)))
    # (5) section references
    section_refs(ctx, out, 0, cell, "markdown", edits, changes, flags)
    # (6) bare ids, dotted ids, chapter ids
    protected = [m.span() for m in _ANY_LINK.finditer(out)] + spans
    for m in LETTER_ID.finditer(out):
        if _inside(m.start(), protected) or any(e.start <= m.start() < e.end for e in edits):
            continue
        old = m.group(1)
        if old not in ID_MAP:
            flags.append(Flag("unmapped", "bare-id", cell, old, neutral(sentence_text(out, m.start()))))
            continue
        row = next(r for r in ROWS if r.old_id == old)
        if row.chapter in ctx.link_chapters:
            edits.append(Edit(m.start(), m.end(), ID_MAP[old], None, "bare-id"))
            changes.append(Change("bare-id", cell, old, ID_MAP[old], neutral(sentence_text(out, m.start()))))
    if ctx.scope == "primary":
        for m in DOTTED_ID.finditer(out):
            if not _inside(m.start(), protected):
                flags.append(Flag("decision", "dotted-id", cell, m.group(0), neutral(sentence_text(out, m.start()))))
        for m in CHAPTER_ID.finditer(out):
            if not _inside(m.start(), protected):
                flags.append(Flag("decision", "chapter-id", cell, m.group(0), neutral(sentence_text(out, m.start()))))
    return apply_edits(out, edits, ctx.proposals)


def process_code_line(ctx: Ctx, line: str, cell: str, changes: list, flags: list) -> str:
    """A code cell is touched on a comment line that cites a section, and only there (plan question 7)."""
    if ctx.scope != "primary":
        return line
    at = line.find("#")
    if at < 0 or not re.search(r"[Ss]ection", line[at:]):
        return line
    edits: list[Edit] = []
    section_refs(ctx, line, at, cell, "code", edits, changes, flags)
    return apply_edits(line, edits, ctx.proposals)


# Corrections of references that are wrong today (plan, question 11). Always a decision for a person; written only with
# --with-proposals. Key: (old file name, cell id).
KNOWN_FIXES: dict[tuple[str, str], tuple[dict, ...]] = {
    ("05.02-starlayer-shacl-engine.ipynb", "f5b00004"): (
        {"old": "see section 2.1)", "new": "see section 05.01.2)", "why": "the same comment in 05.01 and 05.03 says 05.01.2"},
    ),
    ("05h-shacl-evaluate.ipynb", "f5a00004"): (
        {"old": "see section 2.1)", "new": "see section 05.01.2)", "why": "the same comment in 05.01 and 05.03 says 05.01.2"},
    ),
}


# ---- one notebook ------------------------------------------------------------------------------------------------------------
@dataclass
class Result:
    row: Row
    scope: str
    notebook: dict  # the rewritten notebook
    changes: list[Change] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    heading_changes: list[tuple[str, str, str, str]] = field(default_factory=list)  # cell, rule, old, new
    cells_changed: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def rewrite_notebook(
    file: str, nb: dict, guides: dict[str, dict], chapter: str, scope: str, proposals: bool = False
) -> Result:
    """The result of the rules for one notebook. ``nb`` is not changed; the rewritten copy is ``Result.notebook``."""
    row = BY_FILE[file]
    link_chapters = {chapter} if scope == "referrer" else chapters_done(chapter)
    ctx = Ctx(row, scope, link_chapters, guides, proposals)
    own_name = guide_file(ctx, file) or file
    hs = headings(nb)
    ctx.own_old_nums = {h.nums for h in hs if h.nums}
    ctx.head_cache[own_name] = hs
    new_nb = json.loads(json.dumps(nb))
    res = Result(row, scope, new_nb)
    if scope == "primary":
        res.problems += check_headings(hs, row)
    by_line = {(h.cell, h.line): h for h in hs}
    for cell in new_nb["cells"]:
        before = cell_text(cell)
        changes: list[Change] = []
        flags: list[Flag] = []
        lines = before.split("\n")
        fenced = False
        for i, line in enumerate(lines):
            if cell["cell_type"] == "code":
                lines[i] = process_code_line(ctx, line, cell["id"], changes, flags)
                continue
            if cell["cell_type"] != "markdown":
                continue
            if _FENCE.match(line):
                fenced = not fenced
                continue
            if fenced:
                continue
            try:
                lines[i] = process_markdown_line(ctx, line, cell["id"], by_line.get((cell["id"], i)), changes, flags)
            except ValueError as exc:
                res.problems.append(f"cell {cell['id']}: {exc}")
        after = "\n".join(lines)
        for c in changes:
            if c.rule.startswith(("H1", "H2", "H3", "H4")):
                res.heading_changes.append((c.cell, c.rule, c.old, c.new))
            else:
                res.changes.append(c)
        res.flags += flags
        if after != before:
            set_cell_text(cell, after)
            res.cells_changed.append(cell["id"])
    return res


def verify_pair(old: dict, new: dict) -> list[str]:
    """The checks of the plan (3.3) on a rewritten notebook against its input."""
    problems: list[str] = []
    if {k: v for k, v in old.items() if k != "cells"} != {k: v for k, v in new.items() if k != "cells"}:
        problems.append("notebook metadata changed")
    oc, nc = old["cells"], new["cells"]
    ids = [c["id"] for c in nc]
    if ids != [c["id"] for c in oc]:
        problems.append("cell ids or their order changed")
    if len(set(ids)) != len(ids):
        problems.append("cell ids not unique")
    for a, b in zip(oc, nc, strict=False):
        if {k: v for k, v in a.items() if k != "source"} != {k: v for k, v in b.items() if k != "source"}:
            problems.append(f"cell {a['id']}: something other than the source changed")
        if a["cell_type"] == "code" and cell_text(a) != cell_text(b):
            for x, y in zip(cell_text(a).split("\n"), cell_text(b).split("\n"), strict=False):
                if x != y and not ("#" in x and x.index("#") <= len(x) - len(x.split("#", 1)[1]) and re.search("[Ss]ection", x)):
                    problems.append(f"cell {a['id']}: code line changed that is not a section comment: {x!r}")
    return problems


# ---- driving a chapter -------------------------------------------------------------------------------------------------------
@dataclass
class Plan:
    chapter: str
    results: list[tuple[str, Result]] = field(default_factory=list)  # (file name as read, result)
    referrers: list[tuple[str, Result]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def make_plan(guides_dir: Path, chapter: str, only: str | None = None, proposals: bool = False) -> Plan:
    guides = load_guides(guides_dir)
    plan = Plan(chapter)
    for name, nb in guides.items():
        row = BY_FILE.get(name)
        if row is None:
            plan.problems.append(f"{name}: not in the mapping table")
            continue
        if only and only not in (row.old, row.new):
            continue
        if dump(nb) != (guides_dir / name).read_bytes():
            plan.problems.append(f"{name}: not in the repo's JSON format (indent=1, ensure_ascii=False, trailing newline)")
        if row.chapter == chapter:
            res = rewrite_notebook(name, nb, guides, chapter, "primary", proposals)
            plan.results.append((name, res))
        else:
            res = rewrite_notebook(name, nb, guides, chapter, "referrer", proposals)
            if res.cells_changed or any(f.category != "left" for f in res.flags):
                plan.referrers.append((name, res))
    if only and not plan.results and not plan.referrers:
        plan.problems.append(f"{only}: no such guide in the chapter or its referrers")
    return plan


def verify_notebook(name: str, nb: dict, available: set[str], chapter: str | None, fully_qualified: bool) -> list[str]:
    """Links resolve (file and anchor), headings of a primary are fully qualified, no old file name of the chapter is left."""
    problems: list[str] = []
    row = BY_FILE.get(name)
    done = chapters_done(chapter) if chapter else set()
    own = headings(nb)
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        text = cell_text(cell)
        fenced = False
        for line in text.split("\n"):
            if _FENCE.match(line):
                fenced = not fenced
            if fenced:
                continue
            spans = code_spans(line)
            for m in _LINK.finditer(line):
                if _inside(m.start(), spans):
                    continue
                target = m.group("file")
                if target not in available:
                    problems.append(f"{name} cell {cell['id']}: link to {target} does not resolve")
                    continue
                tr = BY_FILE.get(target)
                if tr and tr.renamed and tr.chapter in done and target == tr.old:
                    problems.append(f"{name} cell {cell['id']}: link names the old file {target}")
                if m.group("anchor"):
                    # the anchors of the target are read by the caller through ``anchors``
                    pass
            for stem in OLD_STEMS:
                r = BY_FILE[stem + ".ipynb"]
                hit = re.search(r"(?<![\w.-])" + re.escape(stem) + r"(?![\w-])", line) if r.chapter in done else None
                if hit and not _inside(hit.start(), spans):
                    problems.append(f"{name} cell {cell['id']}: old name {stem} remains")
    if fully_qualified and row and row.new_id:
        for h in own:
            if h.level == 1 and h.form == "id":
                problems.append(f"{name}: H1 {h.text!r} is not fully qualified")
            if h.level > 1 and h.form in ("old", "rel"):
                problems.append(f"{name} cell {h.cell}: heading {h.text!r} is not fully qualified")
    return problems


def broken_anchors(name: str, nb: dict, guides: dict[str, dict]) -> list[tuple[str, str, str]]:
    """(cell id, target file, '#anchor') of every link to a heading that the target does not have."""
    found: list[tuple[str, str, str]] = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        for m in _LINK.finditer(cell_text(cell)):
            if not m.group("anchor") or m.group("file") not in guides:
                continue
            anchors = {anchor_of(h.text) for h in headings(guides[m.group("file")]) if h.level > 1}
            if m.group("anchor")[1:] not in anchors:
                found.append((cell["id"], m.group("file"), m.group("anchor")))
    return found


def check_anchors(name: str, nb: dict, guides: dict[str, dict]) -> list[str]:
    return [f"{name} cell {c}: {f}{a} names no heading" for c, f, a in broken_anchors(name, nb, guides)]


# ---- reports -----------------------------------------------------------------------------------------------------------------
def _count(items) -> Counter:
    return Counter(items)


def render_notebook(name: str, res: Result, out: list[str]) -> None:
    row = res.row
    renamed = res.scope == "primary" and name != row.new
    out.append(f"### `{name}`" + (f" -> `{row.new}`" if renamed else " (name unchanged in this stage)" if res.scope == "referrer" else " (name unchanged)"))
    out.append("")
    hc = res.heading_changes
    out.append(f"Cells that change: {len(res.cells_changed)}")
    out.append("")
    out.append(f"Heading rewrites: {len(hc)}")
    for cell, rule, old, new in hc:
        out.append(f"- [{rule}] cell {cell}: `{old}` -> `{new}`")
    link_changes = [c for c in res.changes if c.rule.startswith("link") or c.rule == "file-name"]
    out.append("")
    out.append(f"Link and file-name rewrites: {len(link_changes)}")
    for c in link_changes:
        out.append(f"- [{c.rule}] cell {c.cell}: `{c.old}` -> `{c.new}`")
    text_changes = [c for c in res.changes if c not in link_changes]
    out.append("")
    out.append(f"In-text rewrites it is sure about: {len(text_changes)}")
    for c in text_changes:
        out.append(f"- [{c.rule}] cell {c.cell}: `{c.old}` -> `{c.new}`: {c.sentence}")
    for cat, title in (
        ("decision", "Needs a decision (not written unless --with-proposals, and only where a proposal exists)"),
        ("deferred", "Deferred (the referent guide is in a chapter that is not renamed yet)"),
        ("left", "Left alone, listed for a read (probably a specification section or no heading of this guide)"),
        ("unmapped", "UNMAPPED reference (stops the stage)"),
    ):
        fl = [f for f in res.flags if f.category == cat]
        out.append("")
        out.append(f"{title}: {len(fl)}")
        for f in fl:
            prop = f" Proposal: `{f.proposal}`." if f.proposal else ""
            out.append(f"- [{f.rule}] cell {f.cell}: `{neutral(f.text, 100)}`.{prop} Sentence: {f.sentence}")
    for p in res.problems:
        out.append(f"- PROBLEM: {p}")
    out.append("")


def render_plan(plan: Plan) -> tuple[str, Counter, int]:
    out: list[str] = [f"# Dry run of the renumbering, chapter {plan.chapter}", ""]
    out.append(
        f"Chapter {plan.chapter}: {len(plan.results)} guides, {len(plan.referrers)} referrer guides (other chapters that link into it). "
        "Nothing is written."
    )
    out.append("")
    totals: Counter = Counter()
    flags: Counter = Counter()
    problems = len(plan.problems)
    out.append("## Primary guides")
    out.append("")
    for name, res in plan.results:
        render_notebook(name, res, out)
        problems += len(res.problems) + sum(1 for f in res.flags if f.category == "unmapped")
        for _, rule, _, _ in res.heading_changes:
            totals[rule] += 1
        for c in res.changes:
            totals[c.rule] += 1
        for f in res.flags:
            flags[f"{f.category}:{f.rule}"] += 1
    out.append("## Referrer guides (only the cells named here change)")
    out.append("")
    for name, res in plan.referrers:
        render_notebook(name, res, out)
        problems += len(res.problems) + sum(1 for f in res.flags if f.category == "unmapped")
        for c in res.changes:
            totals["referrer:" + c.rule] += 1
        for f in res.flags:
            flags[f"referrer {f.category}:{f.rule}"] += 1
        out.append(f"Cells changed in this guide: {', '.join(res.cells_changed) or 'none'}")
        out.append("")
    out.append("## Counts")
    out.append("")
    out.append("Rewrites by rule:")
    for k, v in sorted(totals.items()):
        out.append(f"- {k}: {v}")
    out.append("")
    out.append("Flags by category and rule:")
    for k, v in sorted(flags.items()):
        out.append(f"- {k}: {v}")
    out.append("")
    cells = sum(len(r.cells_changed) for _, r in plan.results)
    out.append(f"Cells that change in the primary guides: {cells}. Cells that change in referrer guides: {sum(len(r.cells_changed) for _, r in plan.referrers)}.")
    if plan.problems:
        out.append("")
        out.append("Problems:")
        out += [f"- {p}" for p in plan.problems]
    return "\n".join(out) + "\n", totals, problems


# ---- apply -------------------------------------------------------------------------------------------------------------------
def apply_plan(guides_dir: Path, chapter: str, target: Path, only: str | None, proposals: bool, remove_old: bool) -> tuple[list[str], list[str]]:
    """Write the rewritten notebooks under ``target/docs/guides``. Returns (written file names, problems); with a problem nothing is written.

    The checks use the whole chapter's result, so an anchor into a guide that ``only`` leaves out is still checked against that
    guide's new headings."""
    plan = make_plan(guides_dir, chapter, None, proposals)
    guides = load_guides(guides_dir)
    problems = list(plan.problems)
    written: list[str] = []
    done = chapters_done(chapter)
    available = {(BY_FILE[n].new if BY_FILE[n].chapter in done else n) if n in BY_FILE else n for n in guides}
    final = {(BY_FILE[n].new if BY_FILE[n].chapter in done else n): v for n, v in guides.items() if n in BY_FILE}
    for _name, res in plan.results:
        final[res.row.new] = res.notebook
    for name, res in plan.referrers:
        final[res.row.new if res.row.chapter in done else name] = res.notebook

    def selected(name: str, row: Row) -> bool:
        return only is None or only in (row.old, row.new, name)

    chosen = [(n, r, True) for n, r in plan.results if selected(n, r.row)] + [(n, r, False) for n, r in plan.referrers if only is not None and selected(n, r.row)]
    if only is None:
        chosen += [(n, r, False) for n, r in plan.referrers]
    for name, res, primary in chosen:
        problems += [f"{name}: {p}" for p in res.problems]
        problems += [f"{name}: unmapped {f.rule}: {f.text}" for f in res.flags if f.category == "unmapped"]
        problems += [f"{name}: {p}" for p in verify_pair(guides[name], res.notebook)]
        new_name = res.row.new if primary or res.row.chapter in done else name
        problems += verify_notebook(new_name, res.notebook, available, chapter, fully_qualified=primary)
        # an anchor that was already broken in the source is a decision item, not a failure of the rewrite
        was_broken = {(c, a) for c, _f, a in broken_anchors(name, guides[name], guides)}
        problems += [
            f"{new_name} cell {c}: {f}{a} names no heading"
            for c, f, a in broken_anchors(new_name, res.notebook, final)
            if (c, a) not in was_broken
        ]
    if problems:
        return written, problems
    outdir = target / GUIDES
    outdir.mkdir(parents=True, exist_ok=True)
    for name, res, primary in chosen:
        if primary:
            (outdir / res.row.new).write_bytes(dump(res.notebook))
            written.append(res.row.new)
            if remove_old and res.row.renamed:
                (outdir / res.row.old).unlink(missing_ok=True)
        elif res.cells_changed:
            (outdir / name).write_bytes(dump(res.notebook))
            written.append(name)
    return written, problems


def verify_tree(root: Path, chapter: str, guides_dir: Path | None = None) -> list[str]:
    """The checks on the working guides after a push (plan, stage checks): every guide, links and anchors, the chapter's headings."""
    guides_dir = guides_dir or root / GUIDES
    guides = load_guides(guides_dir)
    problems: list[str] = []
    available = set(guides)
    for name, nb in guides.items():
        row = BY_FILE.get(name)
        primary = bool(row and row.chapter == chapter)
        problems += verify_notebook(name, nb, available, chapter, fully_qualified=primary)
        problems += check_anchors(name, nb, guides)
        if primary:
            problems += [f"{name}: {p}" for p in check_headings(headings(nb), row)]
    done_new = {r.new for r in ROWS if r.chapter == chapter}
    problems += [f"{n}: the working guides do not have {n}" for n in sorted(done_new) if n not in guides]
    return problems


# ---- other files -------------------------------------------------------------------------------------------------------------
GROUP_STAGE = (
    "docs/guides/README.md",
    "docs/user-guide-version.json",
    "tools/kg/codekg/curated/notebook-links.ttl",
    "packages/starlayer/tests/repo/test_hunt_docs_notebooks.py",
)

# Plain-text fixes to files that are not guides: (path, old text, new text, chapter).
KNOWN_TEXT_FIXES: tuple[tuple[str, str, str, str], ...] = (
    (
        "packages/starlayer/tests/repo/test_hunt_docs_notebooks.py",
        'heads = dict(re.findall(r"^## (\\d+)\\. (.*)$", nb, re.M))',
        'heads = dict(re.findall(r"^## 05\\.09\\.(\\d+) (.*)$", nb, re.M))',
        "05",
    ),
    (
        "packages/starlayer/tests/repo/test_hunt_docs_notebooks.py",
        "def test_guide_04f_section_references_point_at_the_right_sections",
        "def test_guide_05_09_section_references_point_at_the_right_sections",
        "05",
    ),
)

ALLOWED_HISTORICAL = (
    "docs/working/archive/",
    "docs/guides-staging/",
    "vendor/",
    "w3c_sparql11/data/index.tsv",
    "shacl12-test-suite",
)
ASK_FIRST = ("docs/working/step-a-error-scheme-plan-2026-11-25.md",)
LIVE_WORKING_NOTES = ("docs/working/guide-coverage-2026-11-13.md",)  # updated; every other dated note in docs/working is history
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__", ".ruff_cache", ".pytest_cache", "guides-staging"}
_TEXT_SUFFIXES = {".md", ".py", ".ttl", ".json", ".ipynb", ".toml", ".yml", ".yaml", ".txt", ".trig"}


def walk_files(root: Path) -> list[str]:
    """Repo-relative paths of text files, without the staging copy, build products and caches."""
    found = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if _SKIP_DIRS & set(rel.parts) or not p.is_file() or p.suffix not in _TEXT_SUFFIXES or p.suffix == ".trig":
            continue
        found.append(rel.as_posix())
    return found


def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split("\n")
        return [f for f in out if f and Path(f).suffix in _TEXT_SUFFIXES and (root / f).is_file()]
    except (OSError, subprocess.CalledProcessError):
        return walk_files(root)


def classify_path(path: str) -> str:
    if path.startswith("docs/working/"):
        if path in ASK_FIRST:
            return "ask-first"
        if path not in LIVE_WORKING_NOTES:
            return "allowed-historical"
    if any(a in path for a in ALLOWED_HISTORICAL):
        return "allowed-historical"
    return "must-fix"


@dataclass
class Hit:
    path: str
    line: int
    kind: str  # 'stem', 'id', 'dotted-id'
    text: str
    klass: str


def scan(root: Path, files: list[str], chapter: str | None = None, ids: bool = True) -> list[Hit]:
    """The old references still in ``files``: old file names, old letter ids and dotted letter ids."""
    rows = [r for r in ROWS if r.renamed and (chapter is None or r.chapter == chapter)]
    stems = [r.old[:-6] for r in rows] + [p[0][:-3] for p in PARKED_MAP if chapter is None or p[1].split("-")[1][:2] == chapter]
    stem_re = re.compile(r"(?<![\w.-])(" + "|".join(re.escape(s) for s in sorted(stems, key=len, reverse=True)) + r")(?![\w])")
    ids_old = [r.old_id for r in rows if r.old_id and re.fullmatch(r"0[1-7][a-h]", r.old_id)]
    id_re = re.compile(r"(?<![\w./#-])(" + "|".join(ids_old) + r")(?![\w-])") if ids_old else None
    dotted = [f"{r.old_id[1]}.{r.old_id[2]}" for r in rows if r.old_id and re.fullmatch(r"0[1-7][a-h]", r.old_id)]
    dotted_re = re.compile(r"(?<![\w.])(" + "|".join(re.escape(d) for d in dotted) + r")(?![\w.-])") if dotted else None
    hits: list[Hit] = []
    for rel in files:
        if rel == "scripts/renumber_guides.py" or rel.endswith("test_renumber_guides.py"):
            continue
        path = root / rel
        try:
            if rel.endswith(".ipynb"):
                nb = json.loads(path.read_text(encoding="utf-8"))
                lines = [
                    (cell["id"], ln) for cell in nb["cells"] for ln in cell_text(cell).split("\n")
                ]
            else:
                lines = [(i + 1, ln) for i, ln in enumerate(path.read_text(encoding="utf-8").split("\n"))]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        klass = classify_path(rel)
        for where, text in lines:
            for m in stem_re.finditer(text):
                hits.append(Hit(rel, where, "stem", m.group(1), klass))
            if ids and id_re:
                for m in id_re.finditer(text):
                    hits.append(Hit(rel, where, "id", m.group(1), klass))
            if ids and dotted_re and (rel.startswith("docs/guides") or rel.startswith("docs/README")):
                for m in dotted_re.finditer(text):
                    hits.append(Hit(rel, where, "dotted-id", m.group(1), klass))
    return hits


def render_hits(hits: list[Hit]) -> str:
    out = []
    counts: Counter = Counter()
    for h in hits:
        counts[(h.klass, h.kind)] += 1
        out.append(f"{h.klass:18} {h.kind:9} {h.path}:{h.line}: {h.text}")
    out.append("")
    for (klass, kind), n in sorted(counts.items()):
        out.append(f"{klass} {kind}: {n}")
    if not hits:
        out.append("no old reference left")
    return "\n".join(out)


# ---- the non-guide files -----------------------------------------------------------------------------------------------------
@dataclass
class FileEdit:
    path: str
    new_text: str
    old_text: str
    changes: list[tuple[int, str, str, str]] = field(default_factory=list)  # line, rule, old, new
    flags: list[tuple[int, str, str]] = field(default_factory=list)  # line, rule, text


def _names_in_scope(chapters: set[str]) -> dict[str, str]:
    return {r.old: r.new for r in ROWS if r.renamed and r.chapter in chapters}


def _name_re(names) -> re.Pattern | None:
    names = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w.-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])") if names else None


def rewrite_readme_line(line: str, chapters: set[str]) -> tuple[str, list[tuple[str, str, str]]]:
    """A README row: the file name in the link, and the label (`5.c` or `5.2`) in front of it."""
    out: list[tuple[str, str, str]] = []
    names = _names_in_scope(chapters)
    rx = _name_re(names)
    new = line
    if rx:
        new = rx.sub(lambda m: names[m.group(1)], new)
    m = re.match(r"^(\s*-\s+\*\*)(\d)\.([a-h0-9])(\s+\[)", new)
    if m:
        letter_id = f"0{m.group(2)}{m.group(3)}" if m.group(3).isalpha() else f"0{m.group(2)}.0{m.group(3)}"
        new_id = ID_MAP.get(letter_id, letter_id if re.match(r"^0\d\.\d\d$", letter_id) else None)
        if new_id and new_id[:2] in chapters:
            new = f"{m.group(1)}{new_id}{m.group(4)}" + new[m.end() :]
    if new != line:
        out.append(("readme-row", line.strip(), new.strip()))
    return new, out


def rewrite_ttl(text: str, chapters: set[str]) -> tuple[str, list[tuple[int, str, str, str]]]:
    """notebook-links.ttl: the path of each link, and the id prefix of each link block (plan, question 6)."""
    names = _names_in_scope(chapters)
    changes: list[tuple[int, str, str, str]] = []
    lines = text.split("\n")
    blocks = [i for i, ln in enumerate(lines) if re.match(r"^nl:[\w.-]+ a ", ln)]
    for k, start in enumerate(blocks):
        end = blocks[k + 1] if k + 1 < len(blocks) else len(lines)
        path_i = next((j for j in range(start, end) if "slkg:notebookPath" in lines[j]), None)
        if path_i is None:
            continue
        pm = re.search(r'"docs/guides/([\w.-]+\.ipynb)"', lines[path_i])
        if not pm:
            continue
        row = BY_FILE.get(pm.group(1))
        if not row or row.chapter not in chapters:
            continue
        if pm.group(1) in names:
            new = lines[path_i].replace(pm.group(1), names[pm.group(1)])
            changes.append((path_i + 1, "ttl-path", lines[path_i].strip(), new.strip()))
            lines[path_i] = new
        im = re.match(r"^nl:(\d\d(?:\.\d\d|[a-z])?)-(.+?) a ", lines[start])
        if im and im.group(1) != row.new_id:
            new = f"nl:{row.new_id}-{im.group(2)} a " + lines[start][im.end() :]
            changes.append((start + 1, "ttl-id", lines[start].strip(), new.strip()))
            lines[start] = new
    return "\n".join(lines), changes


def edit_file(root: Path, rel: str, chapters: set[str], chapter: str) -> FileEdit | None:
    path = root / rel
    if not path.is_file():
        return None
    old_text = path.read_text(encoding="utf-8")
    fe = FileEdit(rel, old_text, old_text)
    text = old_text
    if rel == "docs/guides/README.md":
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            lines[i], ch = rewrite_readme_line(ln, chapters)
            fe.changes += [(i + 1, r, a, b) for r, a, b in ch]
            for m in DOTTED_ID.finditer(ln):
                old_id = f"0{m.group(1)}{m.group(2)}"
                if old_id in ID_MAP and ID_MAP[old_id][:2] in chapters and not re.match(r"^\s*-\s+\*\*\d\.[a-h]", ln):
                    fe.flags.append((i + 1, "dotted-id", f"{m.group(0)} (now {ID_MAP[old_id]}): {neutral(ln, 160)}"))
        text = "\n".join(lines)
    elif rel.endswith("notebook-links.ttl"):
        text, ch = rewrite_ttl(text, chapters)
        fe.changes += ch
    else:
        names = _names_in_scope(chapters)
        rx = _name_re(names)
        if rx:
            lines = text.split("\n")
            for i, ln in enumerate(lines):
                new = rx.sub(lambda m: names[m.group(1)], ln)
                if new != ln:
                    fe.changes.append((i + 1, "file-name", ln.strip()[:160], new.strip()[:160]))
                    lines[i] = new
            text = "\n".join(lines)
        for r in ROWS:
            if r.renamed and r.chapter in chapters and r.old_id and re.fullmatch(r"0[1-7][a-h]", r.old_id) and not rel.endswith(".json"):
                for i, ln in enumerate(text.split("\n")):
                    for m in LETTER_ID.finditer(ln):
                        if m.group(1) == r.old_id:
                            fe.flags.append((i + 1, "letter-id", neutral(ln, 160)))
    for p, old, new, ch in KNOWN_TEXT_FIXES:
        if p == rel and ch == chapter and old in text:
            fe.changes.append((text.count("\n", 0, text.index(old)) + 1, "known-fix", old, new))
            text = text.replace(old, new)
    fe.new_text = text
    return fe if (fe.changes or fe.flags) else None


def files_for(root: Path, group: str) -> list[str]:
    """The non-guide files of a group: 'stage' (README, manifest, links ttl, the test that names guides) or 'cleanup' (the rest)."""
    stage = [f for f in GROUP_STAGE if (root / f).is_file()]
    if group == "stage":
        return stage
    rest = [
        f
        for f in walk_files(root)
        if f not in GROUP_STAGE
        and not f.endswith(".ipynb")
        and classify_path(f) == "must-fix"
        and f != "scripts/renumber_guides.py"
        and not f.endswith("test_renumber_guides.py")
    ]
    return rest if group == "cleanup" else stage + rest


def plan_files(root: Path, chapter: str, group: str = "all") -> list[FileEdit]:
    chapters = {chapter}
    edits = []
    for rel in files_for(root, group):
        e = edit_file(root, rel, chapters, chapter)
        if e:
            edits.append(e)
    return edits


def render_file_edits(edits: list[FileEdit], chapter: str) -> str:
    out = [f"# Edits to files that are not guides, chapter {chapter}", ""]
    total = Counter()
    for e in edits:
        out.append(f"### `{e.path}`: {len(e.changes)} edits, {len(e.flags)} flags")
        for line, rule, old, new in e.changes:
            total[rule] += 1
            out.append(f"- [{rule}] line {line}: `{neutral(old, 120)}` -> `{neutral(new, 120)}`")
        for line, rule, text in e.flags:
            total["flag:" + rule] += 1
            out.append(f"- FLAG [{rule}] line {line}: {text}")
        out.append("")
    out.append("## Counts")
    out += [f"- {k}: {v}" for k, v in sorted(total.items())]
    return "\n".join(out) + "\n"


def apply_files(root: Path, chapter: str, group: str, generated: bool = False) -> list[str]:
    """Write the edits to ``root``. The generated ontology copy is edited only with ``generated`` (it is rebuilt from the source)."""
    written = []
    for e in plan_files(root, chapter, group):
        if not generated and e.path.endswith("starontology/shacl/shacl12-shacl.ttl"):
            continue
        if e.new_text != e.old_text:
            (root / e.path).write_text(e.new_text, encoding="utf-8")
            written.append(e.path)
    for old, new in PARKED_MAP:
        if group != "stage" and new.split("-")[1][:2] == chapter and (root / GUIDES / old).is_file():
            (root / GUIDES / old).rename(root / GUIDES / new)
            written.append(f"{GUIDES}/{new}")
    return written


# ---- command line ------------------------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root (for tests)")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply", "verify", "check", "leftovers", "plan-files", "apply-files"):
        p = sub.add_parser(name)
        p.add_argument("--chapter", choices=STAGES, default="05" if name in ("plan", "apply", "verify", "plan-files", "apply-files") else None)
        if name in ("plan", "apply"):
            p.add_argument("--only", help="one guide, by old or new file name")
            p.add_argument("--source", type=Path, help="the folder of guides to read (default: docs/guides under --root)")
            p.add_argument("--with-proposals", action="store_true", help="also write the proposed text of the decision items")
        if name == "apply":
            p.add_argument("--target", type=Path, required=True, help="a tree laid out like the staging copy (docs/guides inside)")
            p.add_argument("--remove-old", action="store_true", help="delete the old file name under the target")
        if name == "verify":
            p.add_argument("--source", type=Path)
        if name in ("plan-files", "apply-files"):
            p.add_argument("--group", choices=("stage", "cleanup", "all"), default="all")
        if name == "apply-files":
            p.add_argument("--generated", action="store_true", help="also edit the generated shacl12-shacl.ttl (normally rebuilt)")
    args = ap.parse_args(argv)
    root: Path = args.root
    if args.command in ("plan", "apply"):
        guides_dir = args.source or root / GUIDES
        if args.command == "plan":
            text, _totals, problems = render_plan(make_plan(guides_dir, args.chapter, args.only, args.with_proposals))
            print(text)
            return 1 if problems else 0
        written, problems = apply_plan(guides_dir, args.chapter, args.target, args.only, args.with_proposals, args.remove_old)
        for p in problems:
            print("PROBLEM:", p)
        print(f"wrote {len(written)} notebooks to {args.target / GUIDES}: {', '.join(written)}")
        return 1 if problems else 0
    if args.command == "verify":
        problems = verify_tree(root, args.chapter, args.source)
        print("\n".join(problems) or "ok")
        return 1 if problems else 0
    if args.command in ("check", "leftovers"):
        files = tracked_files(root) if args.command == "leftovers" else walk_files(root)
        if args.command == "check":
            files = [f for f in files if classify_path(f) == "must-fix"]
        hits = scan(root, files, args.chapter)
        print(render_hits(hits))
        return 1 if any(h.klass != "allowed-historical" for h in hits) else 0
    if args.command == "plan-files":
        print(render_file_edits(plan_files(root, args.chapter, args.group), args.chapter))
        return 0
    if args.command == "apply-files":
        written = apply_files(root, args.chapter, args.group, args.generated)
        print(f"wrote {len(written)} files: {', '.join(written)}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
