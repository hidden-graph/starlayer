"""
starlayergraph.model.conformance

RDF 1.2 / SPARQL 1.2 VERSION-directive conformance checking.

Per RDF 1.2 Concepts sec 2.1 ("Version Labels") and SPARQL 1.2 Query sec 4.3,
three version labels are defined:

    "1.2"        full RDF 1.2 conformance - triple terms and dirLangString allowed
    "1.2-basic"  RDF 1.2 syntax, but excludes triple terms and dirLangString
    "1.1"        legacy RDF 1.1 compatibility mode (discouraged in a VERSION
                 directive, since it would needlessly break RDF 1.1 parsers)

The directive is explicitly only a hint: the spec states a parser "is not
required to reject features that are outside the announced version (but
could signal them with a warning)", and the SPARQL spec similarly says
"processors may treat unrecognized labels as an error or as a warning" -
neither mandates specific behavior. StarLayer signals via a warning, never a
hard error, to stay consistent with its permissive-by-default posture: a
stale-but-harmless VERSION line should never turn otherwise-valid data or a
otherwise-valid query into a hard failure.

Two distinct warning classes are used, per SPARQL 1.2 Query sec 4.3's own
observation that "the SPARQL version labels refer to SPARQL syntax and
semantics, while the RDF version labels refer to RDF syntax and semantics":
RDF12ConformanceWarning for RDF document formats (Turtle, TriG,
N-Triples/N-Quads, RDF/XML), SPARQL12ConformanceWarning for a SPARQL
query/update's own VERSION directive.
"""

import warnings

VALID_VERSION_LABELS = frozenset({'1.2', '1.2-basic', '1.1'})


class RDF12ConformanceWarning(UserWarning):
    """A declared VERSION label doesn't match the RDF 1.2 features actually
    used in an RDF document (Turtle, TriG, N-Triples/N-Quads, RDF/XML)."""


class SPARQL12ConformanceWarning(UserWarning):
    """A declared VERSION label doesn't match the RDF 1.2 features actually
    used in a SPARQL query/update's own text.

    Deliberately not a subclass of RDF12ConformanceWarning: per SPARQL 1.2
    Query sec 4.3, "the SPARQL version labels refer to SPARQL syntax and
    semantics, while the RDF version labels refer to RDF syntax and
    semantics" - the two directives share label spelling but check a
    different kind of conformance, so they get distinct warning classes.
    """


def check_version_conformance(declared_version, *, uses_triple_term: bool,
                               uses_dirlangstring: bool, context: str,
                               warning_class: type = RDF12ConformanceWarning,
                               stacklevel: int = 3) -> None:
    """Warn if declared_version is unrecognized, or is "1.2-basic"/"1.1" while
    a triple term and/or dirLangString is actually present.

    "1.1" is included alongside "1.2-basic" here, not just "1.2-basic": "1.1"
    means plain RDF 1.1 syntax/semantics, which by definition has neither of
    the two RDF 1.2 additions this project tracks (see the README's own
    scope note) - so it excludes triple terms/dirLangString at least as
    strictly as "1.2-basic" does, not more permissively.

    declared_version -- the VERSION directive's label, or None if no
                         directive was present (in which case this is a no-op)
    context           -- short label identifying what was checked, for the
                          warning message, e.g. "Turtle document" or
                          "SPARQL query"
    warning_class     -- RDF12ConformanceWarning (default) for RDF document
                          formats, or SPARQL12ConformanceWarning for a
                          SPARQL query/update's own VERSION directive
    stacklevel        -- passed straight to warnings.warn(); the default (3)
                          is correct for a direct caller (warn's own frame,
                          then this function's, then the caller's - pointing
                          the warning at the caller's line). A wrapper that
                          itself calls this function - e.g.
                          check_version_conformance_for_graphs() below -
                          should pass stacklevel=4 so the warning still
                          points at *its* caller, not at the wrapper itself.
    """
    if declared_version is None:
        return

    if declared_version not in VALID_VERSION_LABELS:
        warnings.warn(
            f'{context} declares unrecognized VERSION {declared_version!r} '
            f'(expected one of {sorted(VALID_VERSION_LABELS)})',
            warning_class, stacklevel=stacklevel,
        )
        return

    if declared_version in ('1.2-basic', '1.1'):
        used = [name for name, present in (
            ('a triple term', uses_triple_term),
            ('a directional language-tagged literal (dirLangString)', uses_dirlangstring),
        ) if present]
        if used:
            citation = (
                'SPARQL 1.2 Query sec 4.3'
                if issubclass(warning_class, SPARQL12ConformanceWarning)
                else 'RDF 1.2 Concepts sec 2.1'
            )
            warnings.warn(
                f'{context} declares VERSION {declared_version!r} but uses {" and ".join(used)}, '
                f'which {declared_version!r} conformance excludes ({citation})',
                warning_class, stacklevel=stacklevel,
            )


def check_version_conformance_for_graphs(declared_version, graphs, *, context: str) -> None:
    """Convenience wrapper: computes uses_triple_term/uses_dirlangstring by
    scanning the given StarLayerGraph(s) (their _tt_nodes registry and
    triples() for a DirLangString object), then calls
    check_version_conformance().

    Shared by StarLayerGraph.parse()'s per-format branches (Turtle,
    N-Triples/N-Quads, TriG, RDF/XML each pass graphs=[self]) and
    StarLayerDataset (passes graphs=self.contexts(), since a document-level
    VERSION directive covers every named graph, not just one) - previously
    each of those call sites duplicated this exact scan inline.
    """
    if declared_version is None:
        return
    from starlayergraph.model.dirlangstring import DirLangString
    graphs = list(graphs)
    check_version_conformance(
        declared_version,
        uses_triple_term=any(bool(g._tt_nodes) for g in graphs),
        uses_dirlangstring=any(
            isinstance(o, DirLangString)
            for g in graphs
            for _, _, o in g.triples((None, None, None))
        ),
        context=context,
        stacklevel=4,
    )
