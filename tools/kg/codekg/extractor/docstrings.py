"""codekg.extractor.docstrings - the Args:/Returns: hand-rolled
parser.

Implements the code-KG plan's exact docstring grammar (column-0 headers,
case-sensitive)::

    <summary prose - everything before the first "Args:"/"Returns:" line>

    Args:
        <param_name>: <description, first line>
            <continuation line, indented >= 8 spaces, optional>
        <param_name_2>: <description>

    Returns:
        <free-text description, indented >= 4 spaces, may wrap>

No third-party docstring-parsing library is a dependency (none is in
``pyproject.toml``/``uv.lock``), so this is pure stdlib ``inspect``/``re``.
One function, ``parse_docstring()`` - deliberately defensive: a malformed
or unexpected structure never raises, worst case it falls back to treating
the whole thing as summary text.
"""

from __future__ import annotations

import inspect
import re

# Exactly "    <name>: <rest of line>" - 4 spaces, a bare identifier, a
# colon-space, then the rest of that line as the description's first line.
_PARAM_RE = re.compile(r"^ {4}(\w+): (.*)$")

_ARGS_HEADER = "Args:"
_RETURNS_HEADER = "Returns:"


def parse_docstring(raw: str | None) -> dict:
    """Parse ``raw`` against this project's ``Args:``/``Returns:``
    docstring grammar.

    Args:
        raw: The raw docstring text (as written in source, pre-
            ``inspect.cleandoc``), or ``None``.

    Returns:
        A dict with three keys: ``"summary"`` (``str``, the prose before
        any recognized header), ``"params"`` (``dict[str, str]``, one
        entry per ``Args:`` parameter), and ``"returns"``
        (``str | None``, the ``Returns:`` section's text, or ``None`` if
        there is no ``Returns:`` section). All default to empty/``None``
        for a missing/empty ``raw``. Never raises - a docstring that
        doesn't clearly match the grammar is returned as pure summary
        text instead of causing a crash.
    """
    if not raw:
        return {"summary": "", "params": {}, "returns": None}

    try:
        return _parse(raw)
    except Exception:
        # Defensive fallback: whatever went wrong, don't take down the
        # whole extractor over one file's one weird docstring - treat the
        # entire thing as summary prose instead.
        try:
            fallback_summary = inspect.cleandoc(raw).strip()
        except Exception:
            fallback_summary = raw.strip()
        return {"summary": fallback_summary, "params": {}, "returns": None}


def _parse(raw: str) -> dict:
    cleaned = inspect.cleandoc(raw)
    lines = cleaned.split("\n")

    header_idx = _find_first_header(lines)
    if header_idx is None:
        return {"summary": _join_summary(lines), "params": {}, "returns": None}

    summary = _join_summary(lines[:header_idx])
    params: dict[str, str] = {}
    returns: str | None = None

    idx = header_idx
    if lines[idx].strip() == _ARGS_HEADER:
        idx = _parse_args(lines, idx + 1, params)

    if idx < len(lines) and _is_column0_header(lines[idx], _RETURNS_HEADER):
        idx += 1
        returns_lines, idx = _collect_returns_lines(lines, idx)
        returns = _join_returns(returns_lines)

    return {"summary": summary, "params": params, "returns": returns}


def _is_column0_header(line: str, header: str) -> bool:
    """True if `line` is exactly `header`, with no indentation at all (the
    stripped form must equal the raw line - a header must start at column
    0, not merely contain the header text after stripping)."""
    stripped = line.strip()
    return stripped == line and stripped == header


def _find_first_header(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if _is_column0_header(line, _ARGS_HEADER) or _is_column0_header(line, _RETURNS_HEADER):
            return i
    return None


def _parse_args(lines: list[str], start: int, params: dict[str, str]) -> int:
    """Parse the Args: section starting at `start` (the line right after
    the "Args:" header), mutating `params` in place. Returns the index of
    the first line not consumed by this section (either a "Returns:"
    header, some other column-0 line that ends the section, or
    len(lines))."""
    idx = start
    current_param: str | None = None

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if _is_column0_header(line, _RETURNS_HEADER):
            break
        if stripped == line and stripped != "":
            # Any other non-blank column-0 line ends the Args section too
            # (an unrecognized future header shouldn't be silently
            # absorbed into the last param's description).
            break

        match = _PARAM_RE.match(line)
        if match:
            current_param = match.group(1)
            params[current_param] = match.group(2)
        elif current_param is not None and stripped != "" and line.startswith(" " * 8):
            # A continuation line (>= 8 spaces indent) of the current
            # param's description - strip its leading whitespace down to
            # nothing and join with a single space so wrapped lines read
            # as continuous prose.
            params[current_param] = f"{params[current_param]} {stripped}"
        # Anything else (a blank line, or a malformed/under-indented line
        # that matches none of the above) is ignored rather than crashing
        # the parse - defensive per this module's own contract.

        idx += 1

    return idx


def _collect_returns_lines(lines: list[str], start: int) -> tuple[list[str], int]:
    """Collect the Returns: section's contributing lines starting at
    `start` (the line right after the "Returns:" header). Each contributed
    entry is either a stripped content line (indent >= 4 spaces) or the
    empty string, marking a blank-line paragraph break. Stops at the next
    column-0 non-blank line or end of the docstring. Returns the collected
    lines plus the index of the first line not consumed."""
    collected: list[str] = []
    idx = start

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if stripped == line and stripped != "":
            # Column-0 non-blank line (e.g. a stray "Raises:") ends the
            # Returns section - never absorbed into its text.
            break
        if stripped == "":
            collected.append("")
        elif line.startswith(" " * 4):
            collected.append(stripped)
        else:
            # Indented less than 4 spaces but not column-0 (an odd,
            # malformed case) - treat as the end of the section rather
            # than guessing.
            break

        idx += 1

    return collected, idx


def _join_summary(lines: list[str]) -> str:
    """Strip leading/trailing blank lines, keep internal structure
    (blank lines between paragraphs) exactly as written."""
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(lines[start:end])


def _join_returns(lines: list[str]) -> str:
    """Join Returns: section lines (as produced by
    `_collect_returns_lines`) into flowing prose: consecutive non-blank
    entries join with a single space (wrapped lines read as continuous
    text); a blank entry marks a paragraph break, joined with "\\n\\n"."""
    start = 0
    end = len(lines)
    while start < end and lines[start] == "":
        start += 1
    while end > start and lines[end - 1] == "":
        end -= 1
    lines = lines[start:end]

    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)
