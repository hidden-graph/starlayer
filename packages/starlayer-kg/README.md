# starlayer-kg

The StarLayer code knowledge graph as a data install. It is built once per release from the StarLayer source, tests and
curated files, so installing it needs no build and no checkout.

    pip install starlayer-kg

```python
import starlayer_kg

kg = starlayer_kg.load()          # a StarLayerDataset with default_union=True
starlayer_kg.build_info()         # {"starlayer_version", "commit", "built", "triples", "named_graphs"}
starlayer_kg.path()               # the TriG file itself, for any other RDF library
```

The file holds the code graph (one named graph per module), the vocabulary, the curated capability, notebook-link and
upstream-issue layers, the query library, and the SPARQL text of every named query:

```sparql
SELECT ?q ?t WHERE { ?q a slkg:NamedQuery ; slkg:queryText ?t }
```

The graph describes the commit named in `build_info()`. It does not follow later source changes; install the
`starlayer-kg` release that matches your `starlayer` version.

Maintainers: `python scripts/publish_kg.py` builds this package (see AGENTS.md).
