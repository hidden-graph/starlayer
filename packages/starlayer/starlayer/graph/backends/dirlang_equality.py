"""Keep SPARQL value equality away from ``rdf:dirLangString`` on Oxigraph.

Oxigraph's SPARQL engine aborts the whole process (a Rust ``unreachable!()``
panic, uncatchable from Python) when ``=`` compares two ``rdf:dirLangString``
terms - oxigraph/oxigraph#1982, see ``docs/upstream-issues/
oxigraph-upstream-issues.md``. ``sameTerm()`` is not affected. Because the abort
cannot be caught, the only safe place to deal with it is before the query
reaches the engine.

``guard()`` rewrites each equality ``L = R`` (and ``!=``, ``IN``, ``NOT IN``)
whose operands could both be a ``dirLangString`` into

    IF(COALESCE(hasLANGDIR(L), false) && COALESCE(hasLANGDIR(R), false),
       sameTerm(L, R),
       L = R)

so the engine's own ``=`` runs only when at least one side is *not* a
``dirLangString``, which is the case it handles correctly. For two
``dirLangString`` terms the answer is the same as ``=`` would give (equal when
value, language and direction all match), because there ``=`` and ``sameTerm()``
agree. ``COALESCE`` keeps an unbound or non-literal operand from turning the
condition into an error: it falls through to the original ``=``, which then
fails or succeeds exactly as it did.

An equality is left alone when one side is provably not a ``dirLangString``: an
IRI, a prefixed name, a number, a boolean, a string literal without a base
direction, or a call to a function that never returns one (``STR()``,
``LANG()``, ``STRLEN()`` and so on). Most queries therefore pass through
unchanged and keep the engine's own optimizations; only comparisons between two
unknowns, such as ``FILTER(?a = ?b)``, are rewritten.

Text-level, with the small tokenizer of ``skolem_semantics.py`` (strings, IRIs
and comments are skipped); it does not parse SPARQL. Operand boundaries follow
the SPARQL grammar's precedence: an operand is the arithmetic/unary expression
on either side of the operator, delimited by an unmatched parenthesis, ``,``,
``&&``, ``||``, braces, ``;``, ``.`` or a clause keyword.

Limits, by design:

* An operand that calls ``RAND()``, ``NOW()``, ``UUID()``, ``STRUUID()``,
  ``BNODE()`` or contains ``EXISTS`` cannot be evaluated twice without changing
  its meaning, so that equality is left as written. None of these returns a
  ``dirLangString`` by itself.
* Where the answer differs from ``=``: for two ``dirLangString`` terms that are
  not the same term, ``=`` on a strict reading is an error and this gives
  ``false``; the two agree in a ``FILTER`` (an error filters the row out) and
  differ only under ``!`` or ``!=`` of a mismatch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from starlayer.graph.backends.skolem_semantics import _skip_literal_or_iri

_EQ = ''  # stands for a comparison already guarded, so it is not rewritten again
_NE = ''
_MAX_REWRITES = 500

_VAR = re.compile(r'[?$][A-Za-z0-9_·-￿]+')
_NUMBER = re.compile(r'(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?')
_LANG = re.compile(r'@[A-Za-z]+(?:-[A-Za-z0-9]+)*(?:--[A-Za-z]+)?')
_PNAME = re.compile(r'(?:[A-Za-z_][\w\-]*)?:(?:[\w%:\-]|\.(?=[\w%:\-]))*')
_WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_PUNCT2 = ('!=', '<=', '>=', '&&', '||', '^^')

# keywords that end an operand (clause structure, never part of an expression)
_BOUNDARY_WORDS = frozenset({
    'FILTER', 'BIND', 'HAVING', 'SELECT', 'WHERE', 'AS', 'ORDER', 'BY', 'GROUP', 'VALUES',
    'OPTIONAL', 'UNION', 'MINUS', 'GRAPH', 'SERVICE', 'LIMIT', 'OFFSET', 'ASC', 'DESC',
    'DISTINCT', 'REDUCED', 'INSERT', 'DELETE', 'DATA', 'LOAD', 'CLEAR', 'DROP', 'CREATE',
    'ADD', 'MOVE', 'COPY', 'USING', 'WITH', 'CONSTRUCT', 'ASK', 'DESCRIBE', 'FROM',
})
_COMPARISON = frozenset({'=', '!=', '<', '>', '<=', '>=', _EQ, _NE})

# functions whose result is never a dirLangString (so an equality on one cannot abort)
_SAFE_FUNCTIONS = frozenset({
    'STR', 'LANG', 'LANGDIR', 'DATATYPE', 'STRLEN', 'IRI', 'URI', 'BNODE', 'BOUND', 'SAMETERM',
    'ISIRI', 'ISURI', 'ISBLANK', 'ISLITERAL', 'ISNUMERIC', 'ISTRIPLE', 'HASLANG', 'HASLANGDIR',
    'ABS', 'CEIL', 'FLOOR', 'ROUND', 'RAND', 'NOW', 'YEAR', 'MONTH', 'DAY', 'HOURS', 'MINUTES',
    'SECONDS', 'TIMEZONE', 'TZ', 'UUID', 'STRUUID', 'MD5', 'SHA1', 'SHA256', 'SHA384', 'SHA512',
    'ENCODE_FOR_URI', 'CONTAINS', 'STRSTARTS', 'STRENDS', 'REGEX', 'LANGMATCHES', 'COUNT',
    'SUM', 'AVG',
})
# an operand that calls one of these cannot be evaluated twice without changing its meaning
_IMPURE = frozenset({'RAND', 'NOW', 'UUID', 'STRUUID', 'BNODE', 'EXISTS'})


@dataclass(frozen=True)
class _Tok:
    kind: str  # string iri var number pname word lang punct
    text: str
    start: int
    end: int

    @property
    def upper(self) -> str:
        return self.text.upper()


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        skip = _skip_literal_or_iri(text, i)
        if skip is not None:
            if c != '#':  # comments are dropped
                tokens.append(_Tok('string' if c in '"\'' else 'iri', text[i:skip], i, skip))
            i = skip
            continue
        for rx, kind in ((_VAR, 'var'), (_LANG, 'lang'), (_NUMBER, 'number'), (_PNAME, 'pname'), (_WORD, 'word')):
            m = rx.match(text, i)
            if m and m.end() > i:
                tokens.append(_Tok(kind, m.group(0), i, m.end()))
                i = m.end()
                break
        else:
            two = text[i:i + 2]
            width = 2 if two in _PUNCT2 else 1
            tokens.append(_Tok('punct', text[i:i + width], i, i + width))
            i += width
    return tokens


def _matching_close(tokens: list[_Tok], open_idx: int) -> int:
    depth = 0
    for j in range(open_idx, len(tokens)):
        if tokens[j].text == '(':
            depth += 1
        elif tokens[j].text == ')':
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


def _is_boundary(tok: _Tok) -> bool:
    if tok.kind == 'punct':
        return tok.text in {',', '&&', '||', '{', '}', ';', '.'} or tok.text in _COMPARISON
    if tok.kind == 'word':
        return tok.upper in _BOUNDARY_WORDS or tok.upper == 'IN'
    return False


def _operand_left(tokens: list[_Tok], op_idx: int) -> int | None:
    """Index of the first token of the operand that ends just before ``op_idx``."""
    depth, j = 0, op_idx - 1
    start = op_idx
    while j >= 0:
        t = tokens[j]
        if t.text == ')':
            depth += 1
        elif t.text == '(':
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and _is_boundary(t):
            break
        start = j
        j -= 1
    return start if start < op_idx else None


def _operand_right(tokens: list[_Tok], op_idx: int) -> int | None:
    """Index of the last token of the operand that starts just after ``op_idx``."""
    depth, j = 0, op_idx + 1
    end = op_idx
    while j < len(tokens):
        t = tokens[j]
        if t.text == '(':
            depth += 1
        elif t.text == ')':
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and _is_boundary(t):
            break
        end = j
        j += 1
    return end if end > op_idx else None


def _never_dirlang(toks: list[_Tok]) -> bool:
    """True if the operand made of ``toks`` can never evaluate to a dirLangString."""
    toks = [t for t in toks if t.text not in {'+', '-'}] if len(toks) > 1 and toks[0].text in {'+', '-'} else toks
    if not toks:
        return False
    first = toks[0]
    if len(toks) == 1:
        if first.kind in {'iri', 'number', 'pname'}:
            return True
        if first.kind == 'word' and first.upper in {'TRUE', 'FALSE', 'A'}:
            return True
        if first.kind == 'string':
            return True
        return False
    if first.kind == 'string':
        # "x"@lang, "x"^^dt
        if len(toks) == 2 and toks[1].kind == 'lang':
            return '--' not in toks[1].text
        return len(toks) == 3 and toks[1].text == '^^'
    if first.kind == 'word' and first.upper in _SAFE_FUNCTIONS and len(toks) > 1 and toks[1].text == '(':
        return _matching_close(toks, 1) == len(toks) - 1  # a single call to a safe function
    return False


def _impure(toks: list[_Tok]) -> bool:
    return any(t.kind == 'word' and t.upper in _IMPURE for t in toks)


def _guarded(left: str, right: str, negate: bool) -> str:
    both = f'COALESCE(hasLANGDIR({left}), false) && COALESCE(hasLANGDIR({right}), false)'
    same = f'!sameTerm({left}, {right})' if negate else f'sameTerm({left}, {right})'
    op = _NE if negate else _EQ
    return f'(IF({both}, {same}, {left} {op} {right}))'


def _split_list(tokens: list[_Tok], open_idx: int, close_idx: int) -> list[list[_Tok]]:
    items, cur, depth = [], [], 0
    for t in tokens[open_idx + 1:close_idx]:
        if t.text == '(':
            depth += 1
        elif t.text == ')':
            depth -= 1
        if t.text == ',' and depth == 0:
            items.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur or items:
        items.append(cur)
    return items


def _rewrite_one(text: str) -> str | None:
    """Rewrite the rightmost equality that needs it; ``None`` when none is left."""
    tokens = _tokenize(text)
    for idx in range(len(tokens) - 1, -1, -1):
        t = tokens[idx]
        is_eq = t.kind == 'punct' and t.text in {'=', '!='}
        is_in = t.kind == 'word' and t.upper == 'IN'
        if not (is_eq or is_in):
            continue
        negate_in = is_in and idx > 0 and tokens[idx - 1].kind == 'word' and tokens[idx - 1].upper == 'NOT'
        left_start = _operand_left(tokens, (idx - 1) if negate_in else idx)
        if left_start is None:
            continue
        left_end = (idx - 2) if negate_in else (idx - 1)
        left_toks = tokens[left_start:left_end + 1]
        left_text = text[left_toks[0].start:left_toks[-1].end]

        if is_eq:
            right_end = _operand_right(tokens, idx)
            if right_end is None:
                continue
            right_toks = tokens[idx + 1:right_end + 1]
            if _never_dirlang(left_toks) or _never_dirlang(right_toks) or _impure(left_toks) or _impure(right_toks):
                continue
            right_text = text[right_toks[0].start:right_toks[-1].end]
            replacement = _guarded(left_text, right_text, t.text == '!=')
            return text[:left_toks[0].start] + replacement + text[right_toks[-1].end:]

        # IN / NOT IN: x IN (a, b)  ->  (x = a || x = b);  x NOT IN (a, b)  ->  (x != a && x != b)
        if idx + 1 >= len(tokens) or tokens[idx + 1].text != '(':
            continue
        close = _matching_close(tokens, idx + 1)
        items = _split_list(tokens, idx + 1, close)
        if _never_dirlang(left_toks) or _impure(left_toks) or all(_never_dirlang(i) for i in items):
            continue
        joiner, cmp_op = (' && ', '!=') if negate_in else (' || ', '=')
        if not items:
            body = 'true' if negate_in else 'false'
        else:
            body = joiner.join(f'{left_text} {cmp_op} {text[i[0].start:i[-1].end]}' for i in items if i)
        return text[:left_toks[0].start] + f'({body})' + text[tokens[close].end:]
    return None


def guard(sparql: str) -> str:
    """Return ``sparql`` with every equality that could compare two
    ``dirLangString`` terms made safe (see the module docstring). Text with no
    such equality is returned unchanged."""
    if '=' not in sparql and not re.search(r'\bIN\b', sparql, re.IGNORECASE):
        return sparql
    text = sparql
    for _ in range(_MAX_REWRITES):
        rewritten = _rewrite_one(text)
        if rewritten is None:
            break
        text = rewritten
    return text.replace(_EQ, '=').replace(_NE, '!=')
