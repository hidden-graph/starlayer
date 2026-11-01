"""Execute every guide notebook (docs/guides/*.ipynb) and fail on any cell error.

Opt-in: ``pytest --notebooks`` (or ``STARLAYER_NOTEBOOKS=1``). Needs the ``notebooks`` extra (nbclient, ipykernel).

``scripts/check_notebook_links.py`` only checks that the hand-made notebook-to-code links are current; nothing else runs
the cells, so this is what shows a notebook broken by a change to the library.

A cell may fail for one reason only: an optional package is not installed (the notebook says so itself). Cells that need
a running Oxigraph or Fuseki server skip cleanly in the notebook and do not count.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

pytestmark = pytest.mark.notebooks

REPO = Path(__file__).resolve().parents[4]
GUIDES = REPO / "docs" / "guides"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]

# error text that means "an optional package is missing", not "the notebook is broken"
OPTIONAL_PACKAGES = ("owlready2", "rdflib_sqlalchemy", "rdflib-sqlalchemy", "rustdl", "owlrl", "oxrdflib")


def _is_missing_optional(error: dict) -> bool:
    text = f"{error.get('ename', '')} {error.get('evalue', '')}"
    return any(name in text for name in OPTIONAL_PACKAGES)


@pytest.mark.parametrize("notebook", sorted(GUIDES.glob("*.ipynb")), ids=lambda p: p.stem)
def test_notebook_runs(notebook, monkeypatch):
    # the kernel is a child process: it finds starlayer through PYTHONPATH when the package is not installed
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(PACKAGE_ROOT), os.environ.get("PYTHONPATH", "")])))
    nb = nbformat.read(notebook, as_version=4)
    client = nbclient.NotebookClient(
        nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(GUIDES)}}, allow_errors=True
    )
    client.execute()

    problems = []
    failed_optional = False
    for index, cell in enumerate(nb.cells):
        for output in cell.get("outputs", []):
            if output.get("output_type") != "error":
                continue
            if _is_missing_optional(output):
                failed_optional = True
                continue
            # a cell that follows one lost to a missing package may fail only because of it
            if failed_optional and output.get("ename") == "NameError":
                continue
            problems.append(f"cell {index}: {output['ename']}: {output['evalue'][:200]}\n    {cell.source[:120]!r}")
    assert not problems, f"{notebook.name}:\n" + "\n".join(problems)
