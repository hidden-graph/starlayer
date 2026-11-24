"""StarLayer's own SPARQL extension functions, available to every SPARQL query the engine runs (a constraint, a rule, a node expression).

They are the verdicts of checks that cannot be written in standard SPARQL (the engine's own regular-expression compile, the SPARQL parser and the ``sqe:``
structure check), so the shapes of ``shacl_shacl_starlayer`` can ask them and the result still arrives as an ordinary SHACL validation result. A function that
finds nothing wrong gives no value (``None``), which leaves the variable it is bound to unbound; ``shacl_functions`` merges this registry into the
functions of the shapes graph, and the registry wins, so a shapes graph cannot redefine one.

Function IRIs are in the StarLayer SHACL namespace (``stsh:``). A processor other than StarLayer does not have them: a query that calls one is then
not portable, which is why the shapes that do are kept out of ``shacl_shacl``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from starlayer.shacl.engine.terms import XSD, Literal, NamedNode

STSH = "https://github.com/hidden-graph/starlayer/ns/shacl#"
REGEX_PROBLEM = NamedNode(STSH + "regexProblem")
SPARQL_PROBLEM = NamedNode(STSH + "sparqlProblem")
TIME_ZONE_PROBLEM = NamedNode(STSH + "timeZoneProblem")

_PREFIX_LINE = re.compile(r"^\s*PREFIX\s+([^\s:]*):\s*<([^>]*)>\s*$", re.IGNORECASE | re.MULTILINE)


def _string(term: Any) -> str | None:
    """The lexical form of a string literal (plain or language-tagged), else None: the functions take no other term."""
    if isinstance(term, Literal) and (term.language or term.datatype == XSD.string):
        return term.value
    return None


def regex_problem_function(pattern: Any, flags: Any = None) -> Literal | None:
    """``stsh:regexProblem(pattern, flags)``: why the engine cannot compile this ``sh:pattern`` with these ``sh:flags``, else no value. ``flags`` may be left out.
    Bad flags are not held against the pattern (they have their own result, from ``stsh:regexProblem("", flags)``), so the pattern is then tried without them."""
    from starlayer.shacl.engine.components.core_string_pair import regex_problem

    text = _string(pattern)
    flag_text = "" if flags is None else _string(flags)
    if text is None or flag_text is None:
        return None
    anywhere = NamedNode("urn:starlayer:regex")  # (the node only names the shape in the engine's message, which regex_problem strips)
    flags_reason = regex_problem(anywhere, "", flag_text)
    reason = flags_reason if text == "" else regex_problem(anywhere, text, "" if flags_reason else flag_text)
    return Literal(reason) if reason else None


def sparql_problem_function(query_text: Any, predicate: Any, prefixes: Any = None, parameters: Any = None) -> Literal | None:
    """``stsh:sparqlProblem(text, predicate, prefixes, parameters)``: what is wrong with the SPARQL ``text`` held by ``predicate`` (``sh:select``, ``sh:ask``,
    ``sh:construct`` or ``shui:searchQuery``), else no value. ``prefixes`` is a ``PREFIX p: <namespace>`` line for each declaration the query's owner
    makes with ``sh:declare`` (the query is parsed under them, so line and column numbers stay those of the text itself), ``parameters`` the names
    of the variables its owner's ``sh:parameter``s bind, separated by spaces. Both are optional."""
    from starlayer.shacl.meta_shapes import sparql_text_problem

    text, prefix_lines, names = _string(query_text), _string(prefixes) if prefixes is not None else "", _string(parameters) if parameters is not None else ""
    if text is None or prefix_lines is None or names is None or not isinstance(predicate, NamedNode):
        return None
    from starlayer.shacl.meta_shapes import _QUERY_FORMS

    if predicate not in _QUERY_FORMS:
        return None
    # Only the owner's sh:declare prefixes, as at run time: the engine binds no others, not even rdf:, rdfs: or owl:
    known: dict[str, str] = {}
    known.update(_PREFIX_LINE.findall(prefix_lines))
    problem = sparql_text_problem(predicate, text, known, frozenset(names.split()))
    return Literal(problem) if problem else None


def time_zone_problem_function(value: Any) -> Literal | None:
    """``stsh:timeZoneProblem(value)``: says so when the platform's time-zone database does not know the identifier, else no value. A machine without
    a database (an empty list, as on a system without tzdata) gives no value for any identifier, or every zone would be reported as unknown."""
    import zoneinfo

    name = _string(value)
    if name is None:
        return None
    known = zoneinfo.available_timezones()
    if not known or name in known:
        return None
    return Literal("The platform's time-zone database does not know the time zone \"" + name + "\"")


BUILTIN_FUNCTIONS: dict[NamedNode, Callable[..., Literal | None]] = {
    REGEX_PROBLEM: regex_problem_function,
    SPARQL_PROBLEM: sparql_problem_function,
    TIME_ZONE_PROBLEM: time_zone_problem_function,
}
