"""Introspection: do the tree vocabulary, the encoder and the shapes agree with each other?

These catch the SQE-style gap structurally, without needing a failing input: a ``manch:`` term the
encoder uses but the ontology does not define, an ontology class nothing can produce, or a snapshot that
no longer matches the live file.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .known_failures import ORPHAN_ONTOLOGY_TERMS

HERE = Path(__file__).parent
LIVE = HERE.parent.parent.parent / "starlayer" / "starontology"
MANCH = "https://github.com/hidden-graph/starlayer/ns/graph/manchester-ast#"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("name", ["manchester-ast-ontology.ttl", "manchester_shapes.ttl"])
def test_snapshot_matches_live_file(name):
    """Fails when the live vocabulary/shapes change without a deliberate snapshot refresh (see
    snapshots/SNAPSHOT_FROM.md); the diff of the snapshot is then part of the review."""
    assert _sha(HERE / "snapshots" / name) == _sha(LIVE / name), (
        f"{name} changed in starontology/ - review the change, then refresh snapshots/{name} "
        "and its hash in SNAPSHOT_FROM.md"
    )


def _ontology_terms() -> set[str]:
    g = Graph().parse(LIVE / "manchester-ast-ontology.ttl", format="turtle")
    return {
        str(s)[len(MANCH):]
        for s in set(g.subjects()) if isinstance(s, URIRef) and str(s).startswith(MANCH)
    }


def _terms_used_by_code() -> set[str]:
    """Terms the encoder/decoder reference: ``MANCH.Name`` attribute use, plus quoted tag names that are
    looked up as ``MANCH[tag]`` (expression/data-range tags are dispatched that way). The quoted-name
    scan only counts names that are real ontology terms, so it cannot invent a use."""
    source = (LIVE / "manchester.py").read_text(encoding="utf-8")
    attr = set(re.findall(r"\bMANCH\.([A-Za-z_][A-Za-z0-9_]*)", source))
    quoted = set(re.findall(r"['\"]([A-Za-z][A-Za-z0-9]*)['\"]", source))
    return attr | (quoted & _ontology_terms())


@pytest.mark.manchester_conformance
def test_every_term_the_code_uses_is_defined_in_the_ontology():
    undefined = sorted(_terms_used_by_code() - _ontology_terms())
    assert not undefined, f"manchester.py uses manch: terms the ontology does not define: {undefined}"


@pytest.mark.manchester_conformance
def test_every_ontology_term_is_used_by_the_code():
    g = Graph().parse(LIVE / "manchester-ast-ontology.ttl", format="turtle")
    # Abstract grouping classes (only ever superclasses) are reached through RDFS reasoning, not named in code.
    abstract = {
        str(c)[len(MANCH):]
        for c in set(g.objects(None, RDFS.subClassOf)) if isinstance(c, URIRef) and str(c).startswith(MANCH)
    }
    orphans = sorted(_ontology_terms() - _terms_used_by_code() - abstract - set(ORPHAN_ONTOLOGY_TERMS))
    assert not orphans, f"ontology terms nothing in manchester.py produces or reads: {orphans}"


@pytest.mark.manchester_conformance
def test_orphan_registry_has_no_stale_entries():
    stale = sorted(t for t in ORPHAN_ONTOLOGY_TERMS if t in _terms_used_by_code() or t not in _ontology_terms())
    assert not stale, f"ORPHAN_ONTOLOGY_TERMS entries that are now used or no longer exist: {stale}"


@pytest.mark.manchester_conformance
def test_every_concrete_class_has_a_shape_or_inherits_one():
    """Every non-abstract manch: class must be covered by some SHACL shape (directly, or via a
    superclass the shapes target with RDFS reasoning on, as ``manchester_validate`` does)."""
    onto = Graph().parse(LIVE / "manchester-ast-ontology.ttl", format="turtle")
    shapes = Graph().parse(LIVE / "manchester_shapes.ttl", format="turtle")
    targeted = {str(o) for o in shapes.objects(None, URIRef("http://www.w3.org/ns/shacl#targetClass"))}
    # classes mentioned in sh:class / sh:or lists also count as constrained
    sh_class = {str(o) for o in shapes.objects(None, URIRef("http://www.w3.org/ns/shacl#class"))}

    def ancestors(c):
        seen, todo = set(), [c]
        while todo:
            x = todo.pop()
            for p in onto.objects(x, RDFS.subClassOf):
                if isinstance(p, URIRef) and p not in seen:
                    seen.add(p)
                    todo.append(p)
        return seen

    classes = [c for c in onto.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef) and str(c).startswith(MANCH)]
    uncovered = sorted(
        str(c)[len(MANCH):] for c in classes
        if not ({str(c)} | {str(a) for a in ancestors(c)}) & (targeted | sh_class)
    )
    assert not uncovered, f"manch: classes no shape targets or references (directly or via a superclass): {uncovered}"
