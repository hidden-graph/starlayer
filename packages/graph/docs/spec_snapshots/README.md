# RDF 1.2 / SPARQL 1.2 Spec Snapshots

*Last reviewed: 2026-07-17*

## Purpose

Point-in-time plain-text snapshots of the seven W3C documents this project tracks conformance against (see `docs/rdf12_sparql12_gap_analysis.md`). RDF 1.2 is still pre-Recommendation, so the spec text moves. Instead of re-reading each document from scratch at every re-check, run `refresh_snapshots.py` and `git diff` the result — the diff shows exactly what changed since the last review, which is what actually needs re-verifying.

## Documents

| File | Title | Snapshot status | Snapshot date |
|---|---|---|---|
| `rdf12-concepts.txt` | RDF 1.2 Concepts and Abstract Data Model | Candidate Recommendation Snapshot | 2026-04-07 |
| `rdf12-schema.txt` | RDF 1.2 Schema | Working Draft | 2026-03-28 |
| `rdf12-turtle.txt` | RDF 1.2 Turtle | Working Draft | 2026-06-12 |
| `rdf12-n-triples.txt` | RDF 1.2 N-Triples | Working Draft | 2026-06-24 |
| `rdf12-xml.txt` | RDF 1.2 XML Syntax | Working Draft | 2026-06-18 |
| `sparql12-query.txt` | SPARQL 1.2 Query Language | Working Draft | 2026-06-25 |
| `sparql12-update.txt` | SPARQL 1.2 Update | Working Draft | 2026-06-12 |

These dates match `docs/rdf12_sparql12_gap_analysis.md`'s own "Status fetched" table as of this writing — the two should be refreshed together. N-Quads and TriG have no separate W3C spec document (both are covered within `rdf12-n-triples` and inherit `rdf12-turtle`'s grammar, respectively), so there's no separate snapshot for either.

## Regenerating

```bash
pip install html2text   # dev-only, not a project dependency - not added to pyproject.toml
python3 docs/spec_snapshots/refresh_snapshots.py
git diff docs/spec_snapshots/*.txt
```

Each file is converted from the live W3C page's HTML to plain text (headings, links, and structure preserved; styling/navigation chrome stripped) specifically so the diff is readable and signal isn't drowned in markup noise. If a diff shows a real content change, that's the trigger to re-run the relevant section of `docs/rdf12_sparql12_gap_analysis.md`'s review against the new text and update the "Status fetched" date there.

## License

These snapshots are copied and converted from W3C Technical Reports. Per the [W3C Software and Document License](https://www.w3.org/copyright/software-license-2023/), which the source documents are distributed under:

> Copyright © 2004-2026 [World Wide Web Consortium](https://www.w3.org/). All Rights Reserved. This work is distributed under the [W3C® Software and Document License](https://www.w3.org/copyright/software-license-2023/) in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Each snapshot file's own header carries the same notice plus its specific source URL, matching the license's per-work attribution requirement. No modification is made to the substantive spec text beyond HTML-to-plain-text conversion (link/heading structure preserved).
