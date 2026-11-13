"""scripts/_docs_ref.py - the branch the generated docs link to (imported by the generators, not run).

Each line of the project (``main`` and ``shacl-engine``) carries its own copy of this file, so its generated docs link to
its own code. Resource identifiers (``starontology._GITHUB_BLOB_BASE``) and the code knowledge graph are not links and
stay as they are.
"""

DOCS_REF = "shacl-engine"
REPO_BLOB = f"https://github.com/hidden-graph/starlayer/blob/{DOCS_REF}/"
