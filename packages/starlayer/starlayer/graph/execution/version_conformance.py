"""
starlayer.graph.execution.version_conformance

RDF 1.2 / SPARQL 1.2 VERSION-directive conformance checking.

Per RDF 1.2 Concepts sec 2.1 ("Version Labels") and SPARQL 1.2 Query sec 4.3,
three version labels are defined:

    "1.2"        full RDF 1.2 conformance - triple terms and dirLangString allowed
    "1.2-basic"  RDF 1.2 syntax, but excludes triple terms (SPARQL 1.2 Query 4.3.1: "without triple terms and without
                 triple patterns that have a triple pattern in their subject or object position"); directional
                 language-tagged literals are allowed
    "1.1"        legacy RDF 1.1 compatibility mode (discouraged in a VERSION
                 directive, since it would needlessly break RDF 1.1 parsers)

The spec says a parser "is not required to reject features that are outside the
announced version (but could signal them with a warning)", and the SPARQL spec
says "processors may treat unrecognized labels as an error or as a warning" -
neither mandates specific behavior. StarLayer rejects a SPARQL query or update
whose own VERSION directive its text contradicts, or that names an unknown
label (SPARQL12ConformanceError, a ValueError), before anything is run or sent
to a store: a query that declares a version it does not meet is wrong, and a
query headed for a store that does not support 1.2 should not go out as one.

Only a SPARQL query/update's own VERSION directive is checked. The check
for RDF documents (Turtle, TriG, N-Triples/N-Quads, RDF/XML) was dropped on 2026-11-06: an RDF label is
a hint and a mismatch is not signalled. A mismatch that is a hard error stays one.
"""

VALID_VERSION_LABELS = frozenset({'1.2', '1.2-basic', '1.1'})


class SPARQL12ConformanceError(ValueError):
    """A declared VERSION label doesn't match the RDF 1.2 features actually
    used in a SPARQL query/update's own text, or is not a known label."""


def check_version_conformance(declared_version, *, uses_triple_term: bool,
                               uses_dirlangstring: bool, context: str,
                               error_class: type = SPARQL12ConformanceError) -> None:
    """Raise if declared_version is unrecognized, or is "1.2-basic"/"1.1" while
    a triple term and/or dirLangString is actually present.

    "1.1" is included alongside "1.2-basic" here, not just "1.2-basic": "1.1"
    means plain RDF 1.1 syntax/semantics, which by definition has neither of
    the two RDF 1.2 additions this project tracks (see the README's own
    scope note) - so it excludes triple terms/dirLangString at least as
    strictly as "1.2-basic" does, not more permissively.

    declared_version -- the VERSION directive's label, or None if no
                         directive was present (in which case this is a no-op)
    context           -- short label identifying what was checked, for the
                          error message, e.g. "SPARQL query"
    error_class       -- SPARQL12ConformanceError
    """
    if declared_version is None:
        return

    if declared_version not in VALID_VERSION_LABELS:
        raise error_class(
            f'{context} declares unrecognized VERSION {declared_version!r} '
            f'(expected one of {sorted(VALID_VERSION_LABELS)})'
        )

    if declared_version in ('1.2-basic', '1.1'):
        # "1.2-basic" excludes only triple terms; "1.1" also excludes directional language-tagged literals
        used = [name for name, present in (
            ('a triple term', uses_triple_term),
            ('a directional language-tagged literal (dirLangString)', uses_dirlangstring and declared_version == '1.1'),
        ) if present]
        if used:
            citation = 'SPARQL 1.2 Query sec 4.3'
            raise error_class(
                f'{context} declares VERSION {declared_version!r} but uses {" and ".join(used)}, '
                f'which {declared_version!r} conformance excludes ({citation})'
            )
