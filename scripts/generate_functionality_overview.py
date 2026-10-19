"""First-pass generator for docs/generated/functionality-overview.generated.md,
built from the hand-curated functionality graph
(packages/starlayer/starlayer/codekg/curated/functionality.ttl).

Prose only: it does not render code or source links. A roadmap item's
slkg:seeAlsoPath becomes a link to that file on GitHub.

Run: python3 scripts/generate_functionality_overview.py
"""

from __future__ import annotations

import pathlib

from rdflib import RDF, RDFS, Graph, Namespace

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "packages/starlayer/starlayer"
CURATED_PATH = PKG_ROOT / "codekg/curated/functionality.ttl"
OUT_PATH = REPO_ROOT / "docs/generated/functionality-overview.generated.md"

SLKG = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg#")
BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/"


def main() -> None:
    curated = Graph()
    curated.parse(CURATED_PATH, format="turtle")

    areas = sorted(
        curated.subjects(RDF.type, SLKG.CapabilityArea),
        key=lambda a: int(curated.value(a, SLKG.position) or 0),
    )

    lines = [
        "# StarLayer Functionality Overview",
        "",
        "What StarLayer does today, and what is planned.",
        "",
    ]

    for area in areas:
        label = str(curated.value(area, RDFS.label))
        lines.append(f"## {label}")
        lines.append("")

        caps = sorted(
            curated.subjects(SLKG.inCapabilityArea, area),
            key=lambda c: int(curated.value(c, SLKG.position) or 0),
        )
        implemented = [c for c in caps if str(curated.value(c, SLKG.hasStatus)) == "implemented"]
        roadmap = [c for c in caps if str(curated.value(c, SLKG.hasStatus)) == "roadmap"]

        for cap in implemented:
            comment = str(curated.value(cap, RDFS.comment))
            specs = sorted(str(s) for s in curated.objects(cap, SLKG.implementsSpecification))
            line = f"- {comment}"
            if specs:
                line += " (" + ", ".join(f"[{s.rstrip('/').rsplit('/', 1)[-1]}]({s})" for s in specs) + ")"
            lines.append(line)
        lines.append("")

        if roadmap:
            lines.append("**Planned / deferred:**")
            lines.append("")
            for cap in roadmap:
                comment = str(curated.value(cap, RDFS.comment))
                see_also = curated.value(cap, SLKG.seeAlsoPath)
                line = f"- {comment}"
                if see_also:
                    line += f" ([details]({BLOB_BASE}{see_also}))"
                lines.append(line)
            lines.append("")

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text("\n".join(lines))
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
