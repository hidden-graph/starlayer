"""
starlayergraph.parsers.lexer

Character-level tokenization for Turtle 1.2. Handles all token forms:
<<( )>> triple terms, << >> reification shorthand, <IRI>, quoted strings,
[ ] blank nodes, ( ) collections, and plain whitespace-delimited tokens.

Every form below that scans for a closing delimiter raises
starlayergraph.parsers.errors.TurtleSyntaxError if it reaches the end of the
statement text without finding one, rather than silently treating "no
closing delimiter found" as "the rest of the text is one token" - the
statement-level TurtleSyntaxError.line is filled in by the caller
(StarLayerTurtleParser.parse()), since these functions only see
already-extracted, single-statement text with no document-level line info.
"""

from starlayergraph.parsers.errors import TurtleSyntaxError

# A bare token (PrefixedName, IRI-without-brackets, "a", boolean/numeric
# literal shorthand, ...) never legally contains any of these - each
# unambiguously starts (or is) a different token form, so none of them need a
# preceding space to act as a boundary. See next_token()'s fallback branch.
_BARE_TOKEN_STOP_CHARS = ('<', '(', ')', '[', ']', '{', '}', '"', "'", ',', ';')


def next_token(s):
    """Return (token, remaining) for the next atomic token in s (pre-stripped)."""
    if not s:
        return None, ''

    if s.startswith('<<('):
        i, depth = 3, 1
        while i < len(s):
            if s[i:i+3] == ')>>':
                depth -= 1
                if depth == 0:
                    return s[:i+3], s[i+3:].lstrip()
                i += 3
            elif s[i:i+2] == '<<':
                depth += 1
                i += 2
            else:
                i += 1
        raise TurtleSyntaxError('unterminated <<( )>> triple term', s, pos=len(s))

    if s.startswith('<<'):
        i, depth, in_iri = 2, 1, False
        while i < len(s):
            if in_iri:
                if s[i] == '>':
                    in_iri = False
                i += 1
                continue
            if s[i:i+2] == '<<':
                depth += 1
                i += 2
            elif s[i:i+2] == '>>':
                depth -= 1
                if depth == 0:
                    return s[:i+2], s[i+2:].lstrip()
                i += 2
            elif s[i] == '<':
                in_iri = True
                i += 1
            else:
                i += 1
        raise TurtleSyntaxError('unterminated << >> reification', s, pos=len(s))

    if s.startswith('<'):
        end = s.find('>', 1)
        if end == -1:
            raise TurtleSyntaxError("unterminated IRI (missing '>')", s, pos=len(s))
        return s[:end+1], s[end+1:].lstrip()

    if s.startswith('"""') or s.startswith("'''"):
        q = s[:3]
        i = 3
        while i <= len(s) - 3:
            if s[i:i+3] == q:
                return s[:i+3], s[i+3:].lstrip()
            i += 1
        raise TurtleSyntaxError(f'unterminated {q!r} string', s, pos=len(s))

    if s.startswith('"') or s.startswith("'"):
        q = s[0]
        i = 1
        while i < len(s):
            if s[i] == '\\':
                i += 2
                continue
            if s[i] == q:
                return s[:i+1], s[i+1:].lstrip()
            i += 1
        raise TurtleSyntaxError(f'unterminated {q!r} string', s, pos=len(s))

    if s.startswith('['):
        i, depth, in_str, str_char = 1, 1, False, ''
        while i < len(s) and depth > 0:
            c = s[i]
            if in_str:
                if c == str_char:
                    in_str = False
            elif c in ('"', "'"):
                in_str, str_char = True, c
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
            i += 1
        if depth > 0:
            raise TurtleSyntaxError("unclosed '[' blank node property list", s, pos=len(s))
        return s[:i], s[i:].lstrip()

    if s.startswith('('):
        i, depth, in_str, str_char = 1, 1, False, ''
        while i < len(s) and depth > 0:
            c = s[i]
            if in_str:
                if c == str_char:
                    in_str = False
            elif c in ('"', "'"):
                in_str, str_char = True, c
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            i += 1
        if depth > 0:
            raise TurtleSyntaxError("unclosed '(' collection", s, pos=len(s))
        return s[:i], s[i:].lstrip()

    # Previously only whitespace/'<' stopped this scan, so e.g.
    # "sh:resultPath(...)" (a collection value with no space before '(')
    # glued the '(' onto the predicate token instead of starting a new one -
    # confirmed via the W3C SHACL 1.2 test suite's
    # core/path/path-complex-002.ttl, which has exactly this (no-space) form.
    i = 0
    while i < len(s) and not s[i].isspace() and s[i] not in _BARE_TOKEN_STOP_CHARS:
        i += 1
    return s[:i], s[i:].lstrip()


def consume_annotation_block(s):
    """s starts with '{|'. Return (body_str, remaining). Handles nested {| |} and strings."""
    i, depth = 2, 1
    in_str, str_char = False, ''
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '\\' and i + 1 < len(s):
                i += 2
                continue
            if c == str_char:
                in_str = False
            i += 1
            continue
        if c in ('"', "'"):
            in_str, str_char = True, c
            i += 1
            continue
        if s[i:i+2] == '{|':
            depth += 1
            i += 2
        elif s[i:i+2] == '|}':
            depth -= 1
            if depth == 0:
                return s[2:i].strip(), s[i+2:].lstrip()
            i += 2
        else:
            i += 1
    return s[2:].strip(), ''


def split_obj_and_annotations(s):
    """Split 'obj [~ reifier [{| body |}]]* [{| body |}]*' into
    (obj_token, [(reifier_or_None, body_or_None), ...])."""
    s = s.strip()
    obj_tok, rest = next_token(s)
    rest = rest.strip()
    while rest.startswith('^^') or (rest.startswith('@') and len(rest) > 1 and rest[1].isalpha()):
        suffix, rest = next_token(rest)
        obj_tok += suffix
        rest = rest.strip()
    annotations = []
    while rest:
        if rest.startswith('~'):
            rest = rest[1:].lstrip()
            if rest.startswith('{|'):
                # reifier ::= '~' (iri|BlankNode)? - the name is optional.
                # A bare '~' directly followed by an annotation block is an
                # anonymous/empty reifier that the block attaches to (W3C
                # turtle12-ann-8, "empty reifier with annotation block" -
                # see tests/w3c/). Must not call next_token() here: it has
                # no '{' case, so it would mis-tokenize the block's own
                # opening "{|" as if it were a reifier name.
                reifier = None
            else:
                reifier, rest = next_token(rest)
                rest = rest.strip()
                if not reifier:
                    break
            if rest.startswith('{|'):
                body, rest = consume_annotation_block(rest)
                annotations.append((reifier, body))
            else:
                annotations.append((reifier, None))
            rest = rest.strip()
        elif rest.startswith('{|'):
            body, rest = consume_annotation_block(rest)
            annotations.append((None, body))
            rest = rest.strip()
        else:
            # By the time this function runs, s holds exactly one
            # comma-split object (plus any ~reifier/{| |} annotation
            # suffixes) - the caller already split the surrounding
            # predicateObjectList on ','/';'. Anything left over here is
            # unexpected trailing content on that single object, e.g. a
            # second term with no separator ("{| :s :p :o |}" as an
            # annotation body: pred=:s takes ":p :o" as its object slot,
            # next_token grabs just ":p", leaving stray ":o" - previously
            # silently dropped instead of being flagged as the malformed
            # input it is).
            raise TurtleSyntaxError(
                f'unexpected trailing content {rest!r} after object '
                f'(expected "," ";" "." or end of input)',
                rest, pos=0,
            )
    return obj_tok, annotations
