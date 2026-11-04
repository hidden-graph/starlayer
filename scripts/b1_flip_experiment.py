"""Throwaway measurement helper (docs/working/b1-classification.md).

Defaults the old rdflib-based StarLayerGraph / StarLayerDataset to backend='rdf-1.2' over an in-process Oxigraph store.
Usage: python scripts/b1_flip_experiment.py apply
Undo by restoring the two files under packages/starlayer/starlayer/graph/graph from the index. Never commit the applied state.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "packages/starlayer/starlayer/graph/graph"
SIGS = {
    "starlayer_graph.py": "    def __init__(self, *args, backend: str = 'rdf-1.1', direct_query: bool | None = None, **kwargs):\n",
    "starlayer_dataset.py": "    def __init__(self, *args, backend: str = 'rdf-1.1', bind_namespaces: str | None = None, **kwargs):\n",
}
BODY = """        if backend is None:  # FLIP-EXPERIMENT
            backend = 'rdf-1.2'
            if not args and kwargs.get('store') in (None, 'default'):
                import pyoxigraph
                from oxrdflib import OxigraphStore
                kwargs['store'] = OxigraphStore(store=pyoxigraph.Store())
"""
if sys.argv[1:] != ["apply"]:
    raise SystemExit(__doc__)
for name, sig in SIGS.items():
    p = ROOT / name
    s = p.read_text()
    assert sig in s and "FLIP-EXPERIMENT" not in s
    p.write_text(s.replace(sig, sig.replace("backend: str = 'rdf-1.1'", "backend: str | None = None") + BODY, 1))
