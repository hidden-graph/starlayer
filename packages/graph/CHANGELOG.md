# Changelog

## Unreleased

### Fixed

- **Blank-node label collision across repeated `StarLayerGraph.parse()` calls.** Turtle 1.2 parsing (`format="turtle12"`/`"longturtle12"`) minted anonymous-node labels (`_:sl_N`, `_:si_N`) from a counter that restarted at 0 on every call. Calling `.parse()` more than once on the same graph, where more than one call's Turtle body contained an anonymous `[ ... ]` node, could silently merge unrelated blank nodes that happened to land on the same number into a single node, corrupting the graph. Found live while building a guide example that used two separate `.parse()` calls; every call site elsewhere in this codebase happened to use a single call, which is why this had never surfaced. Fixed by seeding the counter with a random per-call offset (`starlayergraph/parsers/turtle_parser.py`) so labels from different calls can never collide. Regression test: `tests/unit/test_turtle_parser.py::TestBlankNodeUniquenessAcrossCalls`.
