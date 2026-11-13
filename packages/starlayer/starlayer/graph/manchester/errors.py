"""starlayer.graph.manchester.errors - ``ManchesterSyntaxError``, raised by the Manchester syntax parser for malformed input."""


class ManchesterSyntaxError(SyntaxError):
    """Malformed Manchester OWL Syntax input, or a syntactically valid
    construct this parser doesn't support yet (see
    starlayer.graph.manchester.parser's module docstring for the
    supported subset).

    Styled after rdflib's ``BadSyntax``: a ``SyntaxError`` that reports a line number and a caret pointer into the surrounding text.
    """

    def __init__(self, why: str, text: str, pos: int = 0, line: int | None = None):
        """Store the error location and reason, used by __str__ to build
        the formatted ^-pointer message.

        Args:
            why: Short description of what's wrong.
            text: The local text the error was found in (used only to
                build the ^-pointer context in the message).
            pos: Character offset into text where the problem was
                detected.
            line: 1-based line number in the original source document, or
                None.
        """
        self.why = why
        self.text = text
        self.pos = pos
        self.line = line
        super().__init__(str(self))

    def __str__(self) -> str:
        """Format the error with its location and a ^ marker at the failing position; reads 'at end of input' while line is unset."""
        pre = '...' if self.pos > 60 else ''
        start = max(0, self.pos - 60)
        before = self.text[start:self.pos]
        after = self.text[self.pos:self.pos + 60]
        post = '...' if len(self.text) - self.pos > 60 else ''
        loc = f'at line {self.line}' if self.line is not None else 'at end of input'
        return f'{loc}:\nBad syntax ({self.why}) at ^ in:\n"{pre}{before}^{after}{post}"'
