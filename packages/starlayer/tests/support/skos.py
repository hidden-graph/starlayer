"""SKOS validation for tests: the bundled SKOS shapes through ``starlayer.shacl.validate``."""

from __future__ import annotations

from typing import Any

from starlayer.shacl import validate
from starlayer.starontology import get_ontology_graph


def skos_validate(data_graph: Any) -> tuple[bool, Any, str]:
    """``(conforms, report_graph, report_text)`` of ``data_graph`` against the bundled SKOS shapes (``sh:Info`` hints do not flip ``conforms``)."""
    result = validate(data_graph, shacl_graph=get_ontology_graph("skos_shacl"), max_validation_depth=100, allow_infos=True)
    return result.conforms, result.report_graph, result.report_text
