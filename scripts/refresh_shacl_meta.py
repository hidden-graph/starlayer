"""scripts/refresh_shacl_meta.py - regenerates the ``shacl12-shacl.ttl``
named graph inside starontology.trig from build_meta_shapes_graph().

meta_validate() reads that stored graph instead of reassembling it on every
call (see starlayer.shacl.meta_shapes.load_meta_shapes_graph), so run this
after editing shacl12-validation-shapes.ttl / shacl12-presentation-shapes.ttl
or upgrading pySHACL, then run scripts/publish_starontology_files.py.

Only the one named graph's text is replaced; the rest of the file is left
byte-for-byte alone. The result is re-parsed and checked isomorphic to a
fresh build before anything is written.

Run:
    python scripts/refresh_shacl_meta.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PACKAGES_STARLAYER = Path(__file__).resolve().parents[1] / "packages" / "starlayer"
if str(_PACKAGES_STARLAYER) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_STARLAYER))

from rdflib import Dataset, Graph, URIRef  # noqa: E402
from rdflib.compare import to_isomorphic  # noqa: E402

from starlayer import starontology  # noqa: E402
from starlayer.shacl.meta_shapes import build_meta_shapes_graph  # noqa: E402

_TRIG = _PACKAGES_STARLAYER / "starlayer" / "starontology" / "starontology.trig"
_HEADER = "starontology:shacl12-shacl.ttl {"


def main() -> int:
    text = _TRIG.read_text(encoding="utf-8")
    start = text.index("\n" + _HEADER) + 1
    end = text.index("\n}\n", start) + 3  # the block's closing brace, at column 0

    built = build_meta_shapes_graph()
    probe = Dataset()
    probe.parse(data=text, format="trig")
    for prefix, ns in probe.namespaces():
        built.bind(prefix, ns, override=True)
    body = built.serialize(format="turtle")
    # Prefix declarations live in the trig header; keep only the statements.
    statements = "\n".join(line for line in body.splitlines() if not line.startswith("@prefix")).strip()
    new_block = _HEADER + "\n" + statements + "\n}\n"
    new_text = text[:start] + new_block + text[end:]

    check = Dataset()
    check.parse(data=new_text, format="trig")
    iri = URIRef(starontology.get_resource_iri("shacl_shacl"))
    stored = Graph()
    for triple in check.graph(iri):
        stored.add(triple)
    if to_isomorphic(stored) != to_isomorphic(built):
        print("ABORT: regenerated block is not isomorphic to build_meta_shapes_graph()", file=sys.stderr)
        return 1
    # The other named graphs must be untouched.
    before = {str(g.identifier): len(g) for g in probe.graphs()}
    after = {str(g.identifier): len(g) for g in check.graphs()}
    if before.keys() != after.keys() or any(before[k] != after[k] for k in before if k != str(iri)):
        print("ABORT: another named graph changed", file=sys.stderr)
        return 1
    if re.search(r"^\}\s*$", new_text, re.M) is None:
        return 1
    _TRIG.write_text(new_text, encoding="utf-8")
    print(f"shacl12-shacl.ttl: {len(stored)} triples written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
