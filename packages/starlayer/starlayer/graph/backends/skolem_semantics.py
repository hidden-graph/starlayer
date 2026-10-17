"""Make skolemized blank nodes behave like blank nodes inside SPARQL text.

On an engine whose blank-node ids are not stable across queries (Fuseki), this
library stores blank nodes as skolem IRIs (``skolemize_bnode()``) so they can
be referred to exactly. Values coming *out* are turned back into ``BNode``s
(``deskolemize_bnode()``), but three things are evaluated inside the engine,
before anything comes out, and would see an IRI:

* ``isBLANK(x)``  -> must be true for a skolem IRI
* ``isIRI(x)`` / ``isURI(x)`` -> must be false for a skolem IRI
* ``ORDER BY x``  -> SPARQL 1.1 sec 15.1 sorts blank nodes before IRIs before
  literals, so a skolem IRI must sort in the blank-node bucket

``rewrite()`` rewrites those constructs in query text so the engine computes
what it would have for real blank nodes. Text-level, with a small tokenizer
that skips strings, IRIs and comments; it does not parse SPARQL. It rewrites
only the simple, common forms (an ``ORDER BY`` condition that is a variable,
``ASC(...)``/``DESC(...)``, or a bracketed expression / function call).
"""

from __future__ import annotations

import re

from starlayer.graph.model.encoding import BN_NS

_IRIREF = re.compile(r'<[^<>"{}|^`\\\x00-\x20]*>')
_FUNCS = re.compile(r'\b(isBLANK|isIRI|isURI)\s*\(', re.IGNORECASE)
_ORDER_BY = re.compile(r'\bORDER\s+BY\b', re.IGNORECASE)
_VAR = re.compile(r'[?$][A-Za-z0-9_·-￿]+')
_WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_:\-]*')


def _is_skolem(arg: str) -> str:
    return f'(isIRI({arg}) && STRSTARTS(STR({arg}), "{BN_NS}"))'


def _skip_literal_or_iri(text: str, i: int) -> int | None:
    """If a string literal, IRI or comment starts at ``i``, return the index
    just past it; otherwise None."""
    c = text[i]
    if c in ('"', "'"):
        q = c * 3
        if text.startswith(q, i):
            j = text.find(q, i + 3)
            return len(text) if j < 0 else j + 3
        j = i + 1
        while j < len(text):
            if text[j] == '\\':
                j += 2
                continue
            if text[j] == c:
                return j + 1
            j += 1
        return len(text)
    if c == '<':
        m = _IRIREF.match(text, i)
        if m:
            return m.end()
        return None
    if c == '#':
        j = text.find('\n', i)
        return len(text) if j < 0 else j + 1
    return None


def _balanced(text: str, open_idx: int) -> int:
    """Index of the ')' matching the '(' at ``open_idx`` (strings/IRIs skipped)."""
    depth, i = 0, open_idx
    while i < len(text):
        skip = _skip_literal_or_iri(text, i)
        if skip is not None:
            i = skip
            continue
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError('unbalanced parentheses in SPARQL text')


def _rewrite_functions(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        skip = _skip_literal_or_iri(text, i)
        if skip is not None:
            out.append(text[i:skip])
            i = skip
            continue
        m = _FUNCS.match(text, i)
        if m and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in '_?$:')):
            open_idx = m.end() - 1
            close = _balanced(text, open_idx)
            arg = _rewrite_functions(text[open_idx + 1:close]).strip()
            name = m.group(1).lower()
            if name == 'isblank':
                out.append(f'(isBLANK({arg}) || {_is_skolem(arg)})')
            else:
                out.append(f'(isIRI({arg}) && !STRSTARTS(STR({arg}), "{BN_NS}"))')
            i = close + 1
            continue
        out.append(text[i])
        i += 1
    return ''.join(out)


def _rank(expr: str) -> str:
    return f'IF(isBLANK({expr}) || {_is_skolem(expr)}, 0, IF(isIRI({expr}), 1, 2))'


def _rewrite_order_by(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        skip = _skip_literal_or_iri(text, i)
        if skip is not None:
            out.append(text[i:skip])
            i = skip
            continue
        m = _ORDER_BY.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        out.append(text[i:m.end()])
        j = m.end()
        conditions = []
        while True:
            k = j
            while k < len(text) and text[k].isspace():
                k += 1
            direction, expr, end = 'ASC', None, None
            word = _WORD.match(text, k)
            if word and word.group(0).upper() in ('ASC', 'DESC') and re.match(r'\s*\(', text[word.end():]):
                direction = word.group(0).upper()
                open_idx = text.index('(', word.end())
                close = _balanced(text, open_idx)
                expr, end = text[open_idx + 1:close].strip(), close + 1
            elif _VAR.match(text, k):
                v = _VAR.match(text, k)
                expr, end = v.group(0), v.end()
            elif k < len(text) and text[k] == '(':
                close = _balanced(text, k)
                expr, end = text[k + 1:close].strip(), close + 1
            elif word and re.match(r'\s*\(', text[word.end():]) and word.group(0).upper() not in ('LIMIT', 'OFFSET'):
                open_idx = text.index('(', word.end())
                close = _balanced(text, open_idx)
                expr, end = text[k:close + 1], close + 1
            else:
                break
            conditions.append(f' {direction}({_rank(expr)}) {direction}({expr})')
            j = end
        out.append(''.join(conditions))
        i = j
    return ''.join(out)


def rewrite(sparql: str) -> str:
    """Return ``sparql`` with isBLANK/isIRI/ORDER BY adjusted for skolemized
    blank nodes. Text without any of those constructs is returned unchanged."""
    if not (_FUNCS.search(sparql) or _ORDER_BY.search(sparql)):
        return sparql
    # functions first, so the helper expressions ORDER BY generates are not rewritten again
    return _rewrite_order_by(_rewrite_functions(sparql))
