"""
starlayer.graph.parsers.errors

Turtle12SyntaxError — raised by the hand-rolled Turtle 1.2 parser
(starlayer.graph/parsers/{turtle_parser,lexer,syntax}.py) for malformed input.

Styled after rdflib's own rdflib.plugins.parsers.notation3.BadSyntax (a
SyntaxError subclass that reports a line number and a caret pointer into the
surrounding source text), so starlayer.graph's own hand-written parser fails as
loudly and as legibly as rdflib's does, rather than silently misinterpreting
malformed Turtle as valid data. Does not subclass or depend on BadSyntax
itself, since that class is tightly coupled to notation3's own internal
byte-offset/source-URI parser state, which this parser doesn't track the
same way (see split_statements_with_lines in starlayer.graph.parsers.syntax for
this module's own, coarser "which statement" line tracking).
"""


class Turtle12SyntaxError(SyntaxError):
    """Malformed Turtle 1.2 input that the parser cannot recognize as any
    valid token or statement form.

    why  -- short description of what's wrong, e.g. "unterminated string literal"
    text -- the local text the error was found in (a token, or a whole
            statement) - used only to build the ^-pointer context in the
            message, not necessarily the full source document
    pos  -- character offset into text where the problem was detected
    line -- 1-based line number in the original source document, or None if
            not yet known (see StarLayerTurtleParser.parse(), which fills
            this in once it has statement-level line information that the
            lower-level lexer/tokenizer functions don't have)
    """

    def __init__(self, why: str, text: str, pos: int = 0, line: int | None = None):
        self.why = why
        self.text = text
        self.pos = pos
        self.line = line
        super().__init__(str(self))

    def __str__(self) -> str:
        pre = '...' if self.pos > 60 else ''
        start = max(0, self.pos - 60)
        before = self.text[start:self.pos]
        after = self.text[self.pos:self.pos + 60]
        post = '...' if len(self.text) - self.pos > 60 else ''
        loc = f'at line {self.line}' if self.line is not None else 'at end of input'
        return f'{loc}:\nBad syntax ({self.why}) at ^ in:\n"{pre}{before}^{after}{post}"'


class MultipleGraphsError(ValueError):
    """A quad-shaped document (nquads/trig/trix, bare or the RDF 1.2
    nq12/trig12/trix12 variants) names more than one distinct graph, but
    was parsed via StarLayerGraph.parse() - not StarLayerDataset.parse() -
    which can only ever resolve to a single graph. Flattening the input
    would silently mix unrelated graphs' triples together with no way for
    the caller to know, so this is raised instead. A document that
    resolves to at most one distinct graph (including the trivial case of
    everything being in the default graph) parses normally - nothing is
    actually being conflated then.

    format     -- the format= string that was being parsed
    graph_ids  -- every distinct graph identifier found in the document,
                  as strings ("None" stands in for the default graph)
    """

    def __init__(self, format: str, graph_ids: list):
        self.format = format
        self.graph_ids = graph_ids
        super().__init__(
            f"{format!r} input spans {len(graph_ids)} distinct graphs "
            f"({', '.join(graph_ids)}); StarLayerGraph.parse() can only "
            "resolve to a single graph. Use StarLayerDataset.parse() to "
            "keep each graph separate."
        )


class ManchesterSyntaxError(SyntaxError):
    """Malformed Manchester OWL Syntax input, or a syntactically valid
    construct this parser doesn't support yet (see
    starlayer.graph.parsers.manchester_parser's module docstring for the
    supported subset).

    A separate class from Turtle12SyntaxError, not a subclass of it, despite
    the identical shape - "Turtle" in the name would be misleading for
    errors raised while parsing an unrelated concrete syntax.

    why  -- short description of what's wrong
    text -- the local text the error was found in (used only to build the
            ^-pointer context in the message)
    pos  -- character offset into text where the problem was detected
    line -- 1-based line number in the original source document, or None
    """

    def __init__(self, why: str, text: str, pos: int = 0, line: int | None = None):
        self.why = why
        self.text = text
        self.pos = pos
        self.line = line
        super().__init__(str(self))

    def __str__(self) -> str:
        pre = '...' if self.pos > 60 else ''
        start = max(0, self.pos - 60)
        before = self.text[start:self.pos]
        after = self.text[self.pos:self.pos + 60]
        post = '...' if len(self.text) - self.pos > 60 else ''
        loc = f'at line {self.line}' if self.line is not None else 'at end of input'
        return f'{loc}:\nBad syntax ({self.why}) at ^ in:\n"{pre}{before}^{after}{post}"'
