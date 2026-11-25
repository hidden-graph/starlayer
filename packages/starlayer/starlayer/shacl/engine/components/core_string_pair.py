"""SHACL 1.2 Core constraint components: string, property pair and list.

Terms are pyoxigraph terms (a language-tagged string with a base direction is an ``ox.Literal`` with ``direction``).
Lexical forms are never normalized. Parameters that are paths (``sh:equals`` etc.) are evaluated from
the focus node.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from starlayer.shacl.engine import xsd_values as xv
from starlayer.shacl.engine.components.registry import Violation, component, words
from starlayer.shacl.engine.executor import Result
from starlayer.shacl.engine.plan import SH, ShapeError, ShapeCompileError
from starlayer.shacl.engine.terms import RDF, XSD, BlankNode, Literal, NamedNode
from starlayer.shacl.engine.terms import NamedNode as URIRef
from starlayer.shacl.engine.terms import text as term_text
from starlayer.shacl.engine.xpath_regex import xpath_regex_to_python

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
    raise ShapeCompileError(f"{term_text(shape.node)}: {term_text(pred)} must be an xsd:integer literal, got {term!r}")


def _bool_param(shape: Any, pred: URIRef, term: Any) -> bool:
    if isinstance(term, Literal) and term.datatype == XSD.boolean and term.value in ("true", "false", "1", "0"):
        return term.value == "true"  # only the lexical form "true" activates (W3C uniqueLang-002)
    raise ShapeCompileError(f"{term_text(shape.node)}: {term_text(pred)} must be an xsd:boolean literal, got {term!r}")


def _string_param(shape: Any, pred: URIRef, term: Any) -> str:
    if isinstance(term, Literal) and term.datatype == XSD.string:
        return term.value
    raise ShapeCompileError(f"{term_text(shape.node)}: {term_text(pred)} must be a string literal, got {term!r}")


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
        raise ShapeCompileError(f"{what}: {term_text(head)!r} is not a well-formed rdf:List")
    return items


def _other_values(ctx: Any, path_term: Any, focus: Any) -> list[Any]:
    from starlayer.shacl.engine.paths import eval_path, parse_path

    return list(eval_path(ctx.data, parse_path(ctx.shapes, path_term), focus))


def _own_path(shape: Any) -> Any:
    """The shape's path term (what a message calls the property), or None for a node shape."""
    return shape.path.node if shape.path is not None else None


def _of(w: Any, shape: Any) -> str:
    """`` of ex:p`` for a property shape, else nothing."""
    path = _own_path(shape)
    return f" of {w.path(path)}" if path is not None else ""  # str-ok: text


def _not_a_list(w: Any, shape: Any, value: Any) -> str:
    """``The value of ex:p should be a list`` (the value is named unless it is a blank node, whose label means nothing)."""
    named = w.data(value)
    named = "" if named == "a blank node" else f" {named}"  # str-ok: text
    return f"The value{named}{_of(w, shape)} should be a list"  # str-ok: text


def _int_check(pred: URIRef):
    def check(shapes, shape, params) -> None:
        for param in params[pred]:
            _int_param(shape, pred, param)

    return check


def _bool_check(pred: URIRef):
    def check(shapes, shape, params) -> None:
        for param in params[pred]:
            _bool_param(shape, pred, param)

    return check


def _path_check(pred: URIRef):
    """The parameter of a property pair component is a property path, read when a focus node is checked."""

    def check(shapes, shape, params) -> None:
        from starlayer.shacl.engine.paths import parse_path

        for param in params[pred]:
            parse_path(shapes, param)

    return check


def _shape_refs_check(pred: URIRef):
    def check(shapes, shape, params):
        return [p for p in params[pred] if not isinstance(p, Literal)]

    return check


def _members(n: int) -> str:
    return f"{n} member" if n == 1 else f"{n} members"  # str-ok: n is a count


# ---- string components ----------------------------------------------------------------------------------------------


@component(SH.MinLengthConstraintComponent, SH.minLength, check=_int_check(SH.minLength))
def min_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:minLength: each value node's lexical form must be at least n characters; blank nodes and triple terms always fail."""
    for param in params[SH.minLength]:
        n = _int_param(shape, SH.minLength, param)
        for v in values:
            text = _lexical(v)
            if text is None or len(text) < n:
                yield Violation(value=v)


@component(SH.MaxLengthConstraintComponent, SH.maxLength, check=_int_check(SH.maxLength))
def max_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:maxLength: each value node's lexical form must be at most n characters; blank nodes and triple terms always fail."""
    for param in params[SH.maxLength]:
        n = _int_param(shape, SH.maxLength, param)
        for v in values:
            text = _lexical(v)
            if text is None or len(text) > n:
                yield Violation(value=v)


def _compile(shape: Any, pattern: str, flags: str) -> re.Pattern:
    if set(flags) - set("smixq"):
        raise ShapeCompileError(f"{term_text(shape.node)}: invalid sh:flags {flags!r}")
    py_flags = 0
    for ch, flag in (("s", re.DOTALL), ("m", re.MULTILINE), ("i", re.IGNORECASE)):
        if ch in flags:
            py_flags |= flag
    try:
        if "q" in flags:
            text = re.escape(pattern)
        else:
            text = xpath_regex_to_python(pattern, multiline="m" in flags, dotall="s" in flags)
            if "x" in flags:
                text = _strip_free_space(text)
        return re.compile(text, py_flags)
    except (re.error, ValueError, OverflowError) as exc:  # OverflowError: a repetition count such as a{99999999999}
        raise ShapeCompileError(f"{term_text(shape.node)}: invalid sh:pattern {pattern!r}: {exc}") from exc


def regex_problem(node: Any, pattern: str, flags: str) -> str | None:
    """The engine's own reason a ``sh:pattern`` with these ``sh:flags`` cannot be compiled, or None when it can; the meta check asks this so it
    never disagrees with validation."""
    try:
        _compile(SimpleNamespace(node=node), pattern, flags)
    except ShapeError as exc:
        return str(exc).removeprefix(term_text(node) + ": ")
    return None


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


def _regexes(shape: Any, params: dict) -> list[re.Pattern]:
    """The compiled ``sh:pattern`` values of a shape (empty without ``sh:pattern``); ShapeError for a bad flag or expression."""
    if SH.pattern not in params:
        return []
    flag_values = params.get(SH.flags, ())
    if len(flag_values) > 1:
        raise ShapeCompileError(f"{term_text(shape.node)}: more than one sh:flags")
    flags = _string_param(shape, SH.flags, flag_values[0]) if flag_values else ""
    return [_compile(shape, _string_param(shape, SH.pattern, param), flags) for param in params[SH.pattern]]


def _check_pattern(shapes, shape, params) -> None:
    _regexes(shape, params)


@component(SH.PatternConstraintComponent, SH.pattern, SH.flags, check=_check_pattern)
def pattern(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:pattern with sh:flags: each value node's lexical form must match the XPath regular expression somewhere."""
    for regex in _regexes(shape, params):
        for v in values:
            text = _lexical(v)
            if text is None or not regex.search(text):
                yield Violation(value=v)


def _range_matches(rng: str, tag: str) -> bool:
    """RFC 4647 basic filtering: case-insensitive; ``*`` matches any tag; else equal or a prefix before ``-``."""
    rng, tag = rng.lower(), tag.lower()
    return rng == "*" or tag == rng or tag.startswith(rng + "-")


def _check_language_in(shapes, shape, params) -> None:
    for head in params[SH.languageIn]:
        for r in _list_items(shapes, head, f"{term_text(shape.node)} sh:languageIn"):
            _string_param(shape, SH.languageIn, r)


@component(SH.LanguageInConstraintComponent, SH.languageIn, check=_check_language_in)
def language_in(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:languageIn: each value must be a language-tagged literal whose tag matches one of the listed language ranges."""
    for head in params[SH.languageIn]:
        what = f"{term_text(shape.node)} sh:languageIn"
        ranges = [_string_param(shape, SH.languageIn, r) for r in _list_items(ctx.shapes, head, what)]
        for v in values:
            key = _lang_key(v)
            if key is None or not any(_range_matches(r, key[0]) for r in ranges):
                yield Violation(value=v)


@component(SH.UniqueLangConstraintComponent, SH.uniqueLang, check=_bool_check(SH.uniqueLang))
def unique_lang(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:uniqueLang true: no two distinct value nodes may share a language tag and base direction."""
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
                w, path = words(ctx), _own_path(shape)
                yield Violation(message=f"Allows at most 1 value{w.on(path)} with the language tag {tag}, found {n}")  # str-ok: text


@component(SH.SingleLineConstraintComponent, SH.singleLine, check=_bool_check(SH.singleLine))
def single_line(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:singleLine true: no literal value node may contain a line break."""
    for param in params[SH.singleLine]:
        if not _bool_param(shape, SH.singleLine, param):
            continue
        for v in values:
            if isinstance(v, Literal) and _LINE_BREAK.search(_lexical(v)):
                yield Violation(value=v)


# ---- property pair components ---------------------------------------------------------------------------------------


@component(SH.EqualsConstraintComponent, SH.equals, check=_path_check(SH.equals))
def equals(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:equals: the value nodes and the values of the other path from the focus node must be the same set."""
    own = set(values)
    wd, path = words(ctx), _own_path(shape)
    for param in params[SH.equals]:
        others = _other_values(ctx, param, focus)
        other = set(others)
        there = wd.path(param)
        for v in dict.fromkeys(values):
            if v not in other:
                yield Violation(value=v, message=f"Value {wd.data(v)}{wd.on(path)} is not also a value of {there}")  # str-ok: text
        here = f"{wd.path(path)}" if path is not None else "the focus node"  # str-ok: text
        for w in dict.fromkeys(others):
            if w not in own:
                yield Violation(value=w, message=f"Value {wd.data(w)} for {there} is not also a value of {here}")  # str-ok: text


@component(SH.DisjointConstraintComponent, SH.disjoint, check=_path_check(SH.disjoint))
def disjoint(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:disjoint: no value node may also be a value of the other path from the focus node."""
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
    wd = words(ctx)
    limit = "at most" if or_equal else "less than"
    for param in params[pred]:
        other = _other_values(ctx, param, focus)
        for v in values:
            for w in other:  # one result per (value node, other value) pair, as the SPARQL-based definition gives
                if not _less(v, w, or_equal):
                    yield Violation(value=v, message=f"Value {wd.data(v)} should be {limit} the value {wd.data(w)} of {wd.path(param)}")  # str-ok: text


@component(SH.LessThanConstraintComponent, SH.lessThan, check=_path_check(SH.lessThan))
def less_than(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:lessThan: each value node must be strictly less than every value of the other path from the focus node."""
    yield from _pair_order(SH.lessThan, params, ctx, focus, values, False)


@component(SH.LessThanOrEqualsConstraintComponent, SH.lessThanOrEquals, check=_path_check(SH.lessThanOrEquals))
def less_than_or_equals(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:lessThanOrEquals: each value node must be less than or equal to every value of the other path from the focus node."""
    yield from _pair_order(SH.lessThanOrEquals, params, ctx, focus, values, True)


@component(SH.SubsetOfConstraintComponent, SH.subsetOf, check=_path_check(SH.subsetOf))
def subset_of(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:subsetOf: every value node must also be a value of the other path from the focus node."""
    for param in params[SH.subsetOf]:
        other = set(_other_values(ctx, param, focus))
        for v in values:
            if v not in other:
                yield Violation(value=v)


# ---- list components -------------------------------------------------------------------------------------------------


@component(SH.MinListLengthConstraintComponent, SH.minListLength, check=_int_check(SH.minListLength))
def min_list_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:minListLength: each value node must be a well-formed rdf:List with at least n members."""
    wd = words(ctx)
    for param in params[SH.minListLength]:
        n = _int_param(shape, SH.minListLength, param)
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v, message=_not_a_list(wd, shape, v))
            elif len(members) < n:
                yield Violation(value=v, message=f"The list{_of(wd, shape)} has {_members(len(members))}, at least {n} {'is' if n == 1 else 'are'} needed")  # str-ok: text


@component(SH.MaxListLengthConstraintComponent, SH.maxListLength, check=_int_check(SH.maxListLength))
def max_list_length(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:maxListLength: each value node must be a well-formed rdf:List with at most n members."""
    wd = words(ctx)
    for param in params[SH.maxListLength]:
        n = _int_param(shape, SH.maxListLength, param)
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v, message=_not_a_list(wd, shape, v))
            elif len(members) > n:
                yield Violation(value=v, message=f"The list{_of(wd, shape)} has {_members(len(members))}, at most {n} {'is' if n == 1 else 'are'} allowed")  # str-ok: text


@component(SH.UniqueMembersConstraintComponent, SH.uniqueMembers, check=_bool_check(SH.uniqueMembers))
def unique_members(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:uniqueMembers true: each value node must be a well-formed rdf:List without repeated members."""
    wd = words(ctx)
    for param in params[SH.uniqueMembers]:
        if not _bool_param(shape, SH.uniqueMembers, param):
            continue
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v, message=_not_a_list(wd, shape, v))
            elif len(set(members)) != len(members):
                # Core 7.5.4: "Each duplicate member m of a list v should be reported as a separate sh:detail"
                dups = [m for m, n in Counter(members).items() if n > 1]
                twice = lambda m: f"The list{_of(wd, shape)} has {wd.data(m)} more than once"  # noqa: E731  # str-ok: text
                yield Violation(
                    value=v,
                    message=f"The list{_of(wd, shape)} has {', '.join(sorted(wd.data(m) for m in dups))} more than once",  # str-ok: text
                    details=tuple(
                        Result(
                            focus=focus,
                            path=shape.path,
                            value=m,
                            has_value=True,
                            component=SH.UniqueMembersConstraintComponent,
                            shape=shape.node,
                            severity=shape.severity,
                            messages=shape.messages or (Literal(twice(m)),),
                        )
                        for m in dups
                    ),
                )


@component(SH.MemberShapeConstraintComponent, SH.memberShape, check=_shape_refs_check(SH.memberShape))
def member_shape(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:memberShape: each value node must be a well-formed rdf:List whose members all conform to the given shape."""
    wd = words(ctx)
    for member_shape_node in params[SH.memberShape]:
        for v in values:
            members = _members_or_none(ctx.data, v)
            if members is None:
                yield Violation(value=v, message=_not_a_list(wd, shape, v))
                continue
            failing = [m for m in members if not ctx.conforms(member_shape_node, m)]
            if failing:
                named = sorted({wd.data(m) for m in failing})
                subject = f"The member {named[0]}" if len(failing) == 1 else f"The members {', '.join(named)}"  # str-ok: text
                verb = "does" if len(failing) == 1 else "do"
                # Core 7.5.1: "Each member m of a value node v that does not conform to the $memberShape should be reported
                # as a separate sh:detail in the validation result for v." The details are the member shape's own results.
                details = tuple(r for m in dict.fromkeys(failing) for r in ctx.detail_results(member_shape_node, m))
                message = f"{subject} of the list{_of(wd, shape)} {verb} not conform to the shape {wd.shape(member_shape_node)}"  # str-ok: text
                yield Violation(value=v, details=details, message=message)


@component(SH.SomeValueConstraintComponent, SH.someValue, check=_shape_refs_check(SH.someValue))
def some_value(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:someValue: at least one value node must conform to the given shape."""
    for shape_node in params[SH.someValue]:
        if not any(ctx.conforms(shape_node, v) for v in values):
            wd, path = words(ctx), _own_path(shape)
            if path is not None:
                message = f"No value of {wd.path(path)} conforms to {wd.shape(shape_node)}"  # str-ok: text
            else:
                message = f"{wd.data(focus)} does not conform to {wd.shape(shape_node)}"  # str-ok: text
            yield Violation(message=message)
