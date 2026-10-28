"""Translate the XPath/XSD regular-expression syntax of ``sh:pattern`` to Python's ``re`` (GitHub issue #94).

``sh:pattern`` is SPARQL ``REGEX``, whose syntax is XPath ``fn:matches`` (XSD 1.0 Appendix F plus XPath additions). Python's
``re`` shares most of it. What it lacks is translated here:

* ``\\p{L}``, ``\\p{Lu}``, ``\\P{Nd}`` (general categories, from ``unicodedata``) and ``\\p{IsBasicLatin}`` (block names, a
  table of the common XSD blocks);
* ``\\i``, ``\\I``, ``\\c``, ``\\C`` (XML name start character / name character and their complements);
* character class subtraction ``[a-z-[aeiou]]``, which Python compiles to a *different* class without an error.

A pattern that uses none of these is returned unchanged (:func:`needs_translation` is false), so the translation can never alter
a pattern that already works. Anything it cannot translate (an unknown category or block name, a malformed escape) raises
``ValueError`` with a message naming the feature.
"""

from __future__ import annotations

import re
import sys
import unicodedata

__all__ = ["needs_translation", "xpath_regex_to_python"]

_MAX = sys.maxunicode

# \p / \P / \i / \I / \c / \C, or a subtraction "-[" ... only an unescaped backslash counts (an escaped one is "\\\\").
_XPATH_ONLY = re.compile(r"(?<!\\)(?:\\\\)*(?:\\[pPiIcC]|-\[)")

_NAME_START = [
    (0x3A, 0x3A), (0x41, 0x5A), (0x5F, 0x5F), (0x61, 0x7A), (0xC0, 0xD6), (0xD8, 0xF6), (0xF8, 0x2FF), (0x370, 0x37D),
    (0x37F, 0x1FFF), (0x200C, 0x200D), (0x2070, 0x218F), (0x2C00, 0x2FEF), (0x3001, 0xD7FF), (0xF900, 0xFDCF),
    (0xFDF0, 0xFFFD), (0x10000, 0xEFFFF),
]  # fmt: skip
_NAME_CHAR = sorted(
    _NAME_START + [(0x2D, 0x2E), (0x30, 0x39), (0xB7, 0xB7), (0x300, 0x36F), (0x203F, 0x2040)]
)

_BLOCKS = {
    "BasicLatin": (0x0000, 0x007F), "Latin-1Supplement": (0x0080, 0x00FF), "LatinExtended-A": (0x0100, 0x017F),
    "LatinExtended-B": (0x0180, 0x024F), "IPAExtensions": (0x0250, 0x02AF), "SpacingModifierLetters": (0x02B0, 0x02FF),
    "CombiningDiacriticalMarks": (0x0300, 0x036F), "Greek": (0x0370, 0x03FF), "GreekandCoptic": (0x0370, 0x03FF),
    "Cyrillic": (0x0400, 0x04FF), "Armenian": (0x0530, 0x058F), "Hebrew": (0x0590, 0x05FF), "Arabic": (0x0600, 0x06FF),
    "Devanagari": (0x0900, 0x097F), "Thai": (0x0E00, 0x0E7F), "Georgian": (0x10A0, 0x10FF), "HangulJamo": (0x1100, 0x11FF),
    "LatinExtendedAdditional": (0x1E00, 0x1EFF), "GreekExtended": (0x1F00, 0x1FFF), "GeneralPunctuation": (0x2000, 0x206F),
    "SuperscriptsandSubscripts": (0x2070, 0x209F), "CurrencySymbols": (0x20A0, 0x20CF), "LetterlikeSymbols": (0x2100, 0x214F),
    "NumberForms": (0x2150, 0x218F), "Arrows": (0x2190, 0x21FF), "MathematicalOperators": (0x2200, 0x22FF),
    "BoxDrawing": (0x2500, 0x257F), "CJKSymbolsandPunctuation": (0x3000, 0x303F), "Hiragana": (0x3040, 0x309F),
    "Katakana": (0x30A0, 0x30FF), "CJKUnifiedIdeographs": (0x4E00, 0x9FFF), "HangulSyllables": (0xAC00, 0xD7AF),
    "PrivateUse": (0xE000, 0xF8FF), "HalfwidthandFullwidthForms": (0xFF00, 0xFFEF),
}  # fmt: skip

_category_ranges_cache: dict[str, list[tuple[int, int]]] | None = None


def needs_translation(pattern: str) -> bool:
    """Whether ``pattern`` uses a feature Python's ``re`` does not have (or reads differently)."""
    return _XPATH_ONLY.search(pattern) is not None


def _categories() -> dict[str, list[tuple[int, int]]]:
    """Code point ranges per two-letter general category, built once (about a quarter of a second)."""
    global _category_ranges_cache
    if _category_ranges_cache is None:
        ranges: dict[str, list[tuple[int, int]]] = {}
        previous = None
        start = 0
        for code in range(_MAX + 1):
            category = unicodedata.category(chr(code))
            if category != previous:
                if previous is not None:
                    ranges.setdefault(previous, []).append((start, code - 1))
                previous, start = category, code
        ranges.setdefault(previous, []).append((start, _MAX))  # type: ignore[arg-type]
        _category_ranges_cache = ranges
    return _category_ranges_cache


def _normalise(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for low, high in sorted(ranges):
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _complement(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    next_low = 0
    for low, high in _normalise(ranges):
        if low > next_low:
            result.append((next_low, low - 1))
        next_low = high + 1
    if next_low <= _MAX:
        result.append((next_low, _MAX))
    return result


def _property_ranges(name: str) -> list[tuple[int, int]]:
    if name.startswith("Is"):
        block = _BLOCKS.get(name[2:])
        if block is None:
            raise ValueError(
                f"unknown Unicode block \\p{{{name}}} in an XPath regular expression "
                f"(supported blocks: {', '.join('Is' + b for b in sorted(_BLOCKS))})"
            )
        return [block]
    categories = _categories()
    if len(name) == 1:
        found = [r for category, rs in categories.items() if category[0] == name for r in rs]
    else:
        found = list(categories.get(name, []))
    if not found:
        raise ValueError(f"unknown Unicode category \\p{{{name}}} in an XPath regular expression")
    return _normalise(found)


def _ranges_text(ranges: list[tuple[int, int]]) -> str:
    def escape(code: int) -> str:
        return f"\\U{code:08x}"

    return "".join(escape(low) if low == high else f"{escape(low)}-{escape(high)}" for low, high in ranges)


def _read_property_name(pattern: str, index: int) -> tuple[str, int]:
    """``index`` is just after ``\\p``/``\\P``; returns the name inside the braces and the index after ``}``."""
    if index >= len(pattern) or pattern[index] != "{":
        raise ValueError("\\p and \\P must be followed by a braced name, such as \\p{L}")
    end = pattern.find("}", index)
    if end == -1:
        raise ValueError("unterminated \\p{...} in an XPath regular expression")
    return pattern[index + 1 : end], end + 1


def _escape_ranges(pattern: str, index: int) -> tuple[list[tuple[int, int]] | None, int]:
    """If ``pattern[index:]`` starts a multi-character escape (``\\p{..}``, ``\\i``, ...), its code point ranges and the next
    index; otherwise ``(None, index)``."""
    escape = pattern[index + 1] if index + 1 < len(pattern) else ""
    if escape in ("p", "P"):
        name, after = _read_property_name(pattern, index + 2)
        ranges = _property_ranges(name)
        return (_complement(ranges) if escape == "P" else ranges), after
    if escape in ("i", "I", "c", "C"):
        ranges = _NAME_START if escape in ("i", "I") else _NAME_CHAR
        return (_complement(ranges) if escape in ("I", "C") else list(ranges)), index + 2
    return None, index


def _translate_class(pattern: str, index: int) -> tuple[str, int]:
    """``pattern[index]`` is ``[``; returns the Python text for the class (with any subtraction) and the index after it."""
    index += 1
    negated = index < len(pattern) and pattern[index] == "^"
    if negated:
        index += 1
    body: list[str] = []
    subtraction: str | None = None
    while index < len(pattern):
        char = pattern[index]
        if char == "]":
            index += 1
            break
        if char == "-" and index + 1 < len(pattern) and pattern[index + 1] == "[":
            subtraction, index = _translate_class(pattern, index + 1)
            if index >= len(pattern) or pattern[index] != "]":
                raise ValueError("a character class subtraction must end the class: [a-z-[aeiou]]")
            index += 1
            break
        if char == "\\":
            ranges, after = _escape_ranges(pattern, index)
            if ranges is not None:
                body.append(_ranges_text(ranges))
                index = after
                continue
            body.append(pattern[index : index + 2])
            index += 2
            continue
        body.append(char)
        index += 1
    else:
        raise ValueError("unterminated character class in an XPath regular expression")
    inner = "".join(body)
    if subtraction is None:
        return f"[{'^' if negated else ''}{inner}]", index
    positive = f"(?:(?!{subtraction})[{inner}])"
    if negated:
        return f"(?:(?!{positive})[\\s\\S])", index
    return positive, index


def xpath_regex_to_python(pattern: str) -> str:
    """The Python ``re`` pattern equivalent to the XPath regular expression ``pattern``; raises ``ValueError`` for what it cannot
    translate. A pattern without XPath-only syntax is returned unchanged."""
    if not needs_translation(pattern):
        return pattern
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            ranges, after = _escape_ranges(pattern, index)
            if ranges is not None:
                out.append(f"[{_ranges_text(ranges)}]" if ranges else "(?!)")
                index = after
            else:
                out.append(pattern[index : index + 2])
                index += 2
        elif char == "[":
            text, index = _translate_class(pattern, index)
            out.append(text)
        else:
            out.append(char)
            index += 1
    return "".join(out)
