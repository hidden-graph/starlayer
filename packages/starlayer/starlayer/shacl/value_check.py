"""``ValueCheck``: the answer of ``check_value()``, whether one value is accepted for one field of a node."""

from __future__ import annotations

from dataclasses import dataclass

from starlayer.shacl.report_results import ReportResult


@dataclass(frozen=True)
class ValueCheck:
    """What ``check_value()`` found for one value of one field.

    ``conforms`` is the validation's own rule (the severity floor included). ``results`` are the top-level results of validating the
    focus node against the property shape given, as ``ReportResult``s, most severe first.

    This is that property shape only: its own constraints and what it reaches (``sh:node``, ``sh:or``, nested property shapes). It is
    not the shapes-about-shapes layer, so a value this shape accepts but that is not, for example, a valid regular expression is
    accepted here; the regex and SPARQL-text checks of ``meta_validate`` are separate shapes (``stsh:RegexShape``,
    ``stsh:SPARQLQueryTextShape``) and answer a different question, whether the shapes graph being edited is well formed."""

    conforms: bool
    results: tuple[ReportResult, ...]
