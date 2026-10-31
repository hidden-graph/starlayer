"""SHACL 1.2 Core constraint components: string, property pair and list.

Terms are pyoxigraph terms (a language-tagged string with a base direction is an ``ox.Literal`` with ``direction``).
Lexical forms are never normalized. Parameters that are paths (``sh:equals`` etc.) are evaluated from
the focus node.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from starlayer.shacl.xpath_regex import xpath_regex_to_python
from starlayer.shacl_engine import xsd_values as xv
from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import SH, ShapeError
from starlayer.shacl_engine.terms import RDF, XSD, BlankNode, Literal, NamedNode
from starlayer.shacl_engine.terms import NamedNode as URIRef
from starlayer.shacl_engine.terms import text as term_text

_LINE_BREAK = re.compile(r"[\f\r\n\v]")


# ---- term helpers ---------------------------------------------------------------------------------------------------


def _lexical(term: Any) -> str | None:
    """The string a string constraint looks at: IRI text or literal lexical form; None for blank and triple terms."""
    if isinstance(term, NamedNode | Literal):
        return term.value
    return None


def _lang_key(term: Any) -> tuple[str, str] | None:
    """(lowercased language, direction or '') of a language-tagged literal, else None."""
    if isinstance(term, Literal) and term.language:
        return term.language.lower(), str(term.direction) if term.direction is not None else ""
    return None


def _int_param(shape: Any, pred: URIRef, term: Any) -> int:
    if isinstance(term, Literal) and term.datatype in (XSD.integer, XSD.int, XSD.long, XSD.nonNegativeInteger):
        try:
            return int(term.value)
        except ValueError:
            pass
    raise ShapeError(f"{term_text(shape.node)}: {term_text(pred)} must be an xsd:integer literal, got {term!r}")


def _bool_param(shape: Any, pred: URIRef, term: Any) -> bool:
    if isinstance(term, Literal) and term.datatype == XSD.boolean and term.value in ("true", "false", "1", "0"):
        return term.value == "true"  # only the lexical form "true" activates (W3C uniqueLang-002)
    raise ShapeError(f"{term_text(shape.node)}: {term_text(pred)} must be an xsd:boolean literal, got {term!r}")


def _string_param(shape: Any, pred: URIRef, term: Any) -> str:
    if isinstance(term, Literal) and term.datatype == XSD.string:
        return term.value
    raise ShapeError(f"{term_text(shape.node)}: {term_text(pred)} must be a string literal, got {term!r}")


def _members_or_none(graph: Any, head: Any) -> list[Any] | None:
    """Members of a SHACL list (rdf:nil, or nodes with exactly one rdf:first and one rdf:rest, acyclic); else None."""
    items: list[Any] = []
    seen: set[Any] = set()
    node = head
    while node != RDF.nil:
        if node in seen or not isinstance(node, NamedNode | BlankNode):
            return None
        seen.add(node)
        firsts = list(graph.objects(node, RDF.first))
        rests = list(graph.objects(node, RDF.rest))
        if len(firsts) != 1 or len(rests) != 1:
            return None
        items.append(firsts[0])
        node = rests[0]
    if any(True for _ in graph.objects(RDF.nil, RDF.first)) or any(True for _ in graph.objects(RDF.nil, RDF.rest)):
        return None
    return items


def _list_items(graph: Any, head: Any, what: str) -> list[Any]:
    items = _members_or_none(graph, head)
    if items is None:
        raise ShapeError(f"{what}: {term_text(head)!r} is not a well-formed rdf:List")
    return items


def _other_values(ctx: Any, path_term: Any, focus: Any) -> list[Any]:
    from starlayer.shacl_engine.paths import eval_path, parse_path

    return list(eval_path(ctx.data, parse_path(ctx.shapes, path_term), focus))


# ---- string components ----------------------------------------------------------------------------------------------


@component(SH.MinLengthConstraintComponent, SH.minLength)
def min_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.minLength]:
        n = _int_param(shape, SH.minLength, param)
        for v in values:
            text = _lexical(v)
            if text is None or len(text) < n:
                yield Violation(value=v)


@component(SH.MaxLengthConstraintComponent, SH.maxLength)
def max_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.maxLength]:
        n = _int_param(shape, SH.maxLength, param)
        for v in values:
            text = _lexical(v)
            if text is None or len(text) > n:
                yield Violation(value=v)


def _compile(shape: Any, pattern: str, flags: str) -> re.Pattern:
    if set(flags) - set("smixq"):
        raise ShapeError(f"{term_text(shape.node)}: invalid sh:flags {flags!r}")
    py_flags = 0
    for ch, flag in (("s", re.DOTALL), ("m", re.MULTILINE), ("i", re.IGNORECASE)):
        if ch in flags:
            py_flags |= flag
    try:
        if "q" in flags:
            text = re.escape(pattern)
        else:
            text = xpath_regex_to_python(pattern)
            if "x" in flags:
                text = _strip_free_space(text)
        return re.compile(text, py_flags)
    except (re.error, ValueError) as exc:
        raise ShapeError(f"{term_text(shape.node)}: invalid sh:pattern {pattern!r}: {exc}") from exc


def _strip_free_space(pattern: str) -> str:
    """XPath's ``x`` flag: drop whitespace outside character classes (``#`` is not a comment in XPath)."""
    out: list[str] = []
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append(pattern[i : i + 2])
            i += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        if in_class or not ch.isspace():
            out.append(ch)
        i += 1
    return "".join(out)


@component(SH.PatternConstraintComponent, SH.pattern, SH.flags)
def pattern(ctx, shape, params, focus, values) -> Iterator[Violation]:
    if SH.pattern not in params:
        return
    flag_values = params.get(SH.flags, ())
    if len(flag_values) > 1:
        raise ShapeError(f"{term_text(shape.node)}: more than one sh:flags")
    flags = _string_param(shape, SH.flags, flag_values[0]) if flag_values else ""
    for param in params[SH.pattern]:
        regex = _compile(shape, _string_param(shape, SH.pattern, param), flags)
        for v in values:
            text = _lexical(v)
            if text is None or not regex.search(text):
                yield Violation(value=v)


def _range_matches(rng: str, tag: str) -> bool:
    """RFC 4647 basic filtering: case-insensitive; ``*`` matches any tag; else equal or a prefix before ``-``."""
    rng, tag = rng.lower(), tag.lower()
    return rng == "*" or tag == rng or tag.startswith(rng + "-")


@component(SH.LanguageInConstraintComponent, SH.languageIn)
def language_in(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for head in params[SH.languageIn]:
        what = f"{term_text(shape.node)} sh:languageIn"
        ranges = [_string_param(shape, SH.languageIn, r) for r in _list_items(ctx.shapes, head, what)]
        for v in values:
            key = _lang_key(v)
            if key is None or not any(_range_matches(r, key[0]) for r in ranges):
                yield Violation(value=v)


@component(SH.UniqueLangConstraintComponent, SH.uniqueLang)
def unique_lang(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.uniqueLang]:
        if not _bool_param(shape, SH.uniqueLang, param):
            continue
        counts: dict[tuple[str, str], int] = {}
        for v in set(values):
            key = _lang_key(v)
            if key is not None:
                counts[key] = counts.get(key, 0) + 1
        for (lang, direction), n in counts.items():
            if n > 1:
                tag = f"{lang}--{direction}" if direction else lang  # str-ok: a BaseDirection prints ltr / rtl
                yield Violation(message=f"Language tag {tag!r} is used by {n} value nodes")  # str-ok: n is a count


@component(SH.SingleLineConstraintComponent, SH.singleLine)
def single_line(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.singleLine]:
        if not _bool_param(shape, SH.singleLine, param):
            continue
        for v in values:
            if isinstance(v, Literal) and _LINE_BREAK.search(_lexical(v)):
                yield Violation(value=v)


# ---- property pair components ---------------------------------------------------------------------------------------


@component(SH.EqualsConstraintComponent, SH.equals)
def equals(ctx, shape, params, focus, values) -> Iterator[Violation]:
    own = set(values)
    for param in params[SH.equals]:
        others = _other_values(ctx, param, focus)
        other = set(others)
        for v in dict.fromkeys(values):
            if v not in other:
                yield Violation(value=v)
        for w in dict.fromkeys(others):
            if w not in own:
                yield Violation(value=w)


@component(SH.DisjointConstraintComponent, SH.disjoint)
def disjoint(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.disjoint]:
        other = set(_other_values(ctx, param, focus))
        for v in values:
            if v in other:
                yield Violation(value=v)


def _less(a: Any, b: Any, or_equal: bool) -> bool:
    """SPARQL ``<`` / ``<=`` on the XSD value order (``xsd_values.compare``); incomparable pairs are False."""
    c = xv.compare(a, b)
    return c is not None and (c <= 0 if or_equal else c < 0)


def _pair_order(pred: URIRef, params: dict, ctx: Any, focus: Any, values: tuple, or_equal: bool):
    for param in params[pred]:
        other = _other_values(ctx, param, focus)
        for v in values:
            for w in other:  # one result per (value node, other value) pair, as the SPARQL-based definition gives
                if not _less(v, w, or_equal):
                    yield Violation(value=v)


@component(SH.LessThanConstraintComponent, SH.lessThan)
def less_than(ctx, shape, params, focus, values) -> Iterator[Violation]:
    yield from _pair_order(SH.lessThan, params, ctx, focus, values, False)


@component(SH.LessThanOrEqualsConstraintComponent, SH.lessThanOrEquals)
def less_than_or_equals(ctx, shape, params, focus, values) -> Iterator[Violation]:
    yield from _pair_order(SH.lessThanOrEquals, params, ctx, focus, values, True)


@component(SH.SubsetOfConstraintComponent, SH.subsetOf)
def subset_of(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.subsetOf]:
        other = set(_other_values(ctx, param, focus))
        for v in values:
            if v not in other:
                yield Violation(value=v)


# ---- list components -------------------------------------------------------------------------------------------------


@component(SH.MinListLengthConstraintComponent, SH.minListLength)
def min_list_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.minListLength]:
        n = _int_param(shape, SH.minListLength, param)
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None or len(members) < n:
                yield Violation(value=v)


@component(SH.MaxListLengthConstraintComponent, SH.maxListLength)
def max_list_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.maxListLength]:
        n = _int_param(shape, SH.maxListLength, param)
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None or len(members) > n:
                yield Violation(value=v)


@component(SH.UniqueMembersConstraintComponent, SH.uniqueMembers)
def unique_members(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH.uniqueMembers]:
        if not _bool_param(shape, SH.uniqueMembers, param):
            continue
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v)
            elif len(set(members)) != len(members):
                # Core 7.5.4: "Each duplicate member m of a list v should be reported as a separate sh:detail"
                dups = [m for m, n in Counter(members).items() if n > 1]
                yield Violation(
                    value=v,
                    details=tuple(
                        Result(
                            focus=focus,
                            path=shape.path,
                            value=m,
                            has_value=True,
                            component=SH.UniqueMembersConstraintComponent,
                            shape=shape.node,
                            severity=shape.severity,
                            messages=shape.messages,
                        )
                        for m in dups
                    ),
                )


@component(SH.MemberShapeConstraintComponent, SH.memberShape)
def member_shape(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for member_shape_node in params[SH.memberShape]:
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v)
                continue
            failing = [m for m in members if not ctx.conforms(member_shape_node, m)]
            if failing:
                # Core 7.5.1: "Each member m of a value node v that does not conform to the $memberShape should be reported
                # as a separate sh:detail in the validation result for v." The details are the member shape's own results.
                details = tuple(r for m in dict.fromkeys(failing) for r in ctx.detail_results(member_shape_node, m))
                yield Violation(value=v, details=details)


@component(SH.SomeValueConstraintComponent, SH.someValue)
def some_value(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for shape_node in params[SH.someValue]:
        if not any(ctx.conforms(shape_node, v) for v in values):
            yield Violation()
