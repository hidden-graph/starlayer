"""
starlayer.graph.parsers.syntax

Statement-level parsing for Turtle 1.2. Splits raw text into statements,
classifies them, extracts predicate-object fields, and expands blank-node
shorthand and RDF collections into flat triple dicts.
"""

import re

from rdflib import Literal
from rdflib.namespace import XSD

from starlayer.graph.parsers.lexer import next_token, split_obj_and_annotations

# Turtle grammar distinguishes INTEGER/DECIMAL/DOUBLE purely by lexical
# shape: an exponent suffix means DOUBLE even with no decimal point (e.g.
# "123e0"), a decimal point with no exponent means DECIMAL. Order matters
# below - DOUBLE must be checked before DECIMAL, since e.g. "1.5e2" would
# otherwise never reach the DOUBLE branch (nothing here requires it to,
# since DECIMAL's pattern doesn't match a trailing exponent anyway, but
# checking DOUBLE first keeps the two independent instead of relying on
# that).
_INTEGER_RE = re.compile(r'^[+-]?[0-9]+$')
_DOUBLE_RE  = re.compile(r'^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)[eE][+-]?[0-9]+$')
_DECIMAL_RE = re.compile(r'^[+-]?[0-9]*\.[0-9]+$')


def coerce_object(s):
    """Coerce a plain (unquoted) object-position token to a Python value
    when the type is unambiguous - true/false to a Python bool, a bare
    numeric literal to a correctly-typed Literal.

    Only ever called for a token already known to be in *object* position
    (a triple's object field, or an rdf:first collection element) - a bare
    numeric literal or boolean is only legal there, never as a subject or
    predicate, so this function doesn't need to (and must not) run for
    those; turtle_parser._to_node() has no other path that accepts one,
    which is what correctly rejects a fixture like the W3C Turtle 1.2
    negative-syntax test using a bare integer as a subject.

    Built directly as a Literal (not int/float) so INTEGER/DECIMAL/DOUBLE
    stay distinguishable - a Python int/float can't tell "123e0" (DOUBLE)
    from "123.0" (DECIMAL) from "123" (INTEGER) - and normalize=False
    preserves the source document's exact lexical form (e.g. "04" stays
    "04", not silently "4"), matching turtle_parser._to_node()'s
    ^^-typed-literal branch, which takes the same care for the same reason.

    Args:
        s: The unquoted object-position token text to coerce.

    Returns:
        True/False for "true"/"false", a correctly-typed xsd:double/
        xsd:decimal/xsd:integer Literal for a bare numeric literal, or s
        unchanged if it doesn't match any of those shapes.
    """
    s = s.strip()
    if s == 'true':
        return True
    if s == 'false':
        return False
    if _DOUBLE_RE.match(s):
        return Literal(s, datatype=XSD.double, normalize=False)
    if _DECIMAL_RE.match(s):
        return Literal(s, datatype=XSD.decimal, normalize=False)
    if _INTEGER_RE.match(s):
        return Literal(s, datatype=XSD.integer, normalize=False)
    return s


def _split_on_delimiter(text, delim):
    """Split text on delim at bracket-depth 0, respecting strings.

    Triple-quoted (``\"\"\"``/``'''``) strings are tracked as one atomic
    unit, not three independent single-char toggles. Previously this
    function only ever tracked single-character quote state (toggling
    ``in_str`` on literally every ``"``/``'`` it saw) - for a real
    triple-quoted string the first two characters of the opening
    ``\"\"\"`` canceled each other out as a complete, empty string, so
    the *third* quote character was misread as starting a brand-new
    single-quoted string - one that then terminated early at the real
    string's own first embedded quote (e.g. a multi-line docstring
    quoting a short phrase, as this project's own cleaned-up docstring
    convention - see starlayer.codekg.extractor - routinely produces).
    Any ``;``/``,`` between that false terminator and the literal's real
    closing ``\"\"\"`` was then silently swallowed into the wrong group
    instead of splitting there, corrupting every predicate/object pair
    that followed. Confirmed via the code-KG extractor's own real pilot
    run against ``starlayer.graph.model.conformance``'s
    ``SPARQL12ConformanceWarning`` docstring, the first multi-line
    comment in this project's fixtures to combine a triple-quoted
    serialization with an embedded, quoted short phrase.
    """
    parts = []
    buf = ''
    depth = 0
    in_str = False
    str_char = ''
    triple = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == '\\' and i + 1 < n:
                buf += text[i:i + 2]
                i += 2
                continue
            if ch == str_char and (not triple or text[i:i + 3] == str_char * 3):
                width = 3 if triple else 1
                buf += text[i:i + width]
                i += width
                in_str = False
                continue
            buf += ch
            i += 1
            continue
        if ch == '\\' and i + 1 < n:
            buf += text[i:i + 2]  # PN_LOCAL_ESC in a prefixed name: the next character is part of the name (GitHub issue #59)
            i += 2
            continue
        if ch in ('"', "'"):
            if text[i:i + 3] == ch * 3:
                in_str, str_char, triple = True, ch, True
                buf += ch * 3
                i += 3
            else:
                in_str, str_char, triple = True, ch, False
                buf += ch
                i += 1
            continue
        if ch in '[({':
            depth += 1
        elif ch in '])}':
            depth -= 1
        if ch == delim and depth == 0:
            if buf.strip():
                parts.append(buf.strip())
            buf = ''
        else:
            buf += ch
        i += 1
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _scan_directive_end(data, i):
    """From position i (the start of a directive keyword), find where this
    directive statement ends.

    A directive is terminated by a depth-0 '.' if it has one (e.g.
    "@prefix : <http://example.org/> ."), the same as any other statement -
    finding it here (bracket/string-depth-aware, so a '.' inside the
    directive's own <IRI>, e.g. "example.com", doesn't false-terminate it)
    is what lets content following the directive on the *same* physical
    line be correctly split into its own, separate statement. If there's
    no '.' before the line ends, the directive is dot-less (both the
    dotted @prefix/@base/@version and the bare SPARQL-style prefix/base/
    version spellings are accepted without a trailing '.' - existing,
    intentional leniency), so it ends at end-of-line instead.

    Returns the exclusive end offset (just past the '.' if found, otherwise
    at the line-terminating '\\n'/'\\r' or end of data).
    """
    depth = {'[': 0, '(': 0, '{': 0, '<': 0}
    in_string = False
    string_char = ''
    triple = False
    j = i
    while j < len(data):
        c = data[j]
        if in_string:
            if c == '\\' and j + 1 < len(data):
                # Same escaped-character-before-the-closing-delimiter fix
                # as _split_statements_impl()'s matching block - consume
                # the pair atomically before string_char ever sees it.
                j += 2
                continue
            if c == string_char:
                if triple:
                    # Only a real '"""'/"'''" closes a triple-quoted string -
                    # see _split_statements_impl()'s matching fix/comment for
                    # the full rationale (a lone embedded quote is legal,
                    # ordinary string content, not a closing delimiter).
                    if data[j:j+3] == string_char * 3:
                        j += 3
                        in_string = False
                        continue
                else:
                    in_string = False
            j += 1
            continue
        if c in ('"', "'"):
            in_string = True
            string_char = c
            if data[j:j+3] == c * 3:
                triple = True
                j += 3
            else:
                triple = False
                j += 1
            continue
        if c == '#' and depth['<'] == 0:
            # A '#' outside a string and outside an <IRI> (which may
            # legitimately contain one, e.g. a fragment) starts a comment
            # running to end-of-line - not real statement content.
            while j < len(data) and data[j] not in ('\n', '\r'):
                j += 1
            continue
        if c in '[({<':
            depth[c] += 1
        elif c in '])}>':
            if c == ']':   depth['['] = max(0, depth['['] - 1)
            elif c == ')': depth['('] = max(0, depth['('] - 1)
            elif c == '}': depth['{'] = max(0, depth['{'] - 1)
            elif c == '>': depth['<'] = max(0, depth['<'] - 1)
        if c in ('\n', '\r') and all(v == 0 for v in depth.values()):
            return j
        if c == '.' and all(v == 0 for v in depth.values()):
            return j + 1
        j += 1
    return len(data)


def _split_statements_impl(data):
    """Split Turtle text into (statement, start_offset) pairs, start_offset
    being the 0-based character offset in *data* where that statement's
    buffering began - statement-start granularity, not byte-exact (newlines
    are stripped while buffering a multi-line statement, so a precise
    within-statement offset isn't recoverable here), which is enough to
    convert to a "close enough" line number for error reporting. See
    split_statements() and split_statements_with_lines() below, and
    Turtle12SyntaxError in starlayer.graph.parsers.errors.
    """
    from starlayer.graph.parsers.errors import Turtle12SyntaxError

    stmts = []
    buf = ''
    stmt_start = 0
    depth = {'[': 0, '(': 0, '{': 0, '<': 0}
    in_string = False
    string_char = ''
    triple = False
    i = 0
    while i < len(data):
        at_line_start = (i == 0 or data[i-1] in ('\n', '\r'))
        if at_line_start and not in_string:
            # Directives (dotted @prefix/@base/@version, or bare SPARQL-style
            # prefix/base/version) end at their own '.' if they have one, or
            # at end-of-line if they don't (both spellings are accepted
            # without a trailing '.' - existing, intentional leniency).
            # Previously this always read to end-of-line regardless, which
            # silently swallowed any further content on the *same* physical
            # line as a dotted directive into the directive's own statement
            # text and dropped it (extract_fields()'s prefix regex only
            # matches its own leading portion and ignores the rest) - see
            # _scan_directive_end().
            #
            # The `and not in_string` guard matters: without it, a line that
            # merely *starts with* one of these keywords while still inside
            # an open triple-quoted string literal (e.g. a multi-line
            # docstring whose prose begins a line with "version ..." or
            # "based on ...") was misdetected as a real directive and split
            # the statement apart mid-string - confirmed via this project's
            # own code-KG extractor feeding its own docstrings back through
            # this parser.
            found_directive = False
            for kw in ('@version', '@prefix', 'prefix', '@base', 'base', 'version'):
                if data[i:i+len(kw)].lower() == kw:
                    end = _scan_directive_end(data, i)
                    stmt = data[i:end].strip()
                    if stmt:
                        if buf.strip():
                            stmts.append((buf.strip(), stmt_start))
                            buf = ''
                        stmts.append((stmt, i))
                    i = end
                    while i < len(data) and data[i] in ('\n', '\r'):
                        i += 1
                    stmt_start = i
                    found_directive = True
                    break
            if found_directive:
                continue
        c = data[i]
        if in_string:
            if c == '\\' and i + 1 < len(data):
                # Consume an escaped character as one atomic pair, before
                # the string_char check below ever sees it - otherwise an
                # escaped quote immediately preceding the real closing
                # '"""'/"'''" (e.g. a docstring ending "...the word
                # \"profile.\"\"\"\"", where only the first of the trailing
                # four quote characters is the escaped one) gets misread as
                # itself starting the real closing delimiter, one character
                # too early. The triple-quote branch below already had this
                # exact bug fixed for a *mid-string* embedded quote (see its
                # own comment); this is the matching fix for one sitting
                # directly against the closing delimiter, confirmed live via
                # the code-KG extractor's own cleaned `shacl_profiling.py`
                # module docstring, which ends in exactly this shape.
                # Mirrors _split_on_delimiter()'s own already-correct
                # backslash-pair handling below.
                buf += data[i:i + 2]
                i += 2
                continue
            buf += c
            if c == string_char:
                if triple:
                    # Only a genuine '"""'/"'''" (three in a row) closes a
                    # triple-quoted string - a single embedded quote
                    # character identical to the delimiter (legal, unescaped,
                    # per Turtle's STRING_LITERAL_LONG_QUOTE/_SINGLE_QUOTE
                    # grammar - e.g. a docstring quoting a short phrase) is
                    # just ordinary string content. Previously this branch
                    # ran regardless of how the string was opened, so a lone
                    # embedded quote was misread as closing a single-quoted
                    # string even inside an open triple-quoted one - the same
                    # bug _split_on_delimiter() below already documents and
                    # fixes for its own, separate scan; this is the matching
                    # fix for this function's statement-level scan.
                    if data[i:i+3] == string_char * 3:
                        buf += data[i+1:i+3]
                        i += 2
                        in_string = False
                else:
                    in_string = False
            i += 1
            continue
        if c == '#' and depth['<'] == 0:
            # Comment to end-of-line - not real statement content. Previously
            # only a *whole* comment-only line was recognized (stripped
            # before this function ever runs, in StarLayerTurtleParser.parse's
            # pre-filter) - a trailing comment after real content on the same
            # line (e.g. "sh:targetNode ex:Invalid ;  # note") was fed into
            # the grammar as literal text instead, confirmed via the W3C
            # SHACL 1.2 test suite (e.g. core/node/class-003.ttl,
            # core/complex/shacl-shacl-data-shapes.ttl).
            while i < len(data) and data[i] not in ('\n', '\r'):
                i += 1
            continue
        if c == '\\' and i + 1 < len(data) and depth['<'] == 0:
            buf += data[i:i+2]  # PN_LOCAL_ESC in a prefixed name: the next character is part of the name, not syntax
            i += 2
            continue
        if c in ('"', "'"):
            if data[i:i+3] == c * 3:
                in_string = True
                string_char = c
                triple = True
                buf += c * 3
                i += 3
                continue
            else:
                in_string = True
                string_char = c
                triple = False
        elif c in '[({<':
            depth[c] += 1
        elif c in '])}>':
            if c == ']':   depth['['] = max(0, depth['['] - 1)
            elif c == ')': depth['('] = max(0, depth['('] - 1)
            elif c == '}': depth['{'] = max(0, depth['{'] - 1)
            elif c == '>': depth['<'] = max(0, depth['<'] - 1)
        if c in ('\n', '\r') and not in_string:
            i += 1
            continue
        if c == '.' and all(v == 0 for v in depth.values()):
            # A '.' at depth 0 terminates the statement unless the very
            # next character continues the bare token this '.' is
            # actually part of, rather than ending it - two distinct
            # cases, both legal Turtle: a DECIMAL/DOUBLE literal's own
            # decimal point (always followed by a digit, e.g. "3.14" or
            # ".5e10"), and a PN_LOCAL's internal '.' (Turtle's PN_LOCAL
            # grammar allows '.' anywhere except as the first or last
            # character, e.g. a prefixed name like "ns1:thing.py" or
            # "ns4:builtins.str" - the GitHub-blob-URL-derived filenames
            # and dotted identifiers this project's own code-KG extractor
            # mints as subjects, see starlayer.codekg.extractor.visitor).
            # A real statement-terminating '.' is never immediately
            # followed by a character that could extend the token just
            # scanned - only whitespace, EOF, '#' (comment), or another
            # statement-level delimiter. Previously only the DECIMAL/
            # DOUBLE case was recognized (`next_char.isdigit()`), so any
            # dotted PN_LOCAL silently mis-split mid-token - confirmed via
            # exactly that case the first time this project's own custom
            # trig12 parser (not stock rdflib, which starontology.trig
            # itself happens to be parsed with - see starontology's own
            # _dataset(), format="trig") was asked to round-trip one.
            # Previously required the '.' to be immediately followed by a
            # newline instead, which - as a side effect - silently merged
            # any two statements written on the same physical line into
            # one, dropping everything the resulting bad split fed to a
            # regex-based field extractor that just ignores its own
            # unmatched trailing text (worst for a directive: found and
            # fixed together with this same bug).
            next_char = data[i+1] if i + 1 < len(data) else ''
            continues_token = next_char != '' and (next_char.isalnum() or next_char in '_-:%.')
            # ...except that a '.' which STARTS a token cannot be part of a name: PN_LOCAL may not begin with '.', and the
            # only token that can begin with '.' is a number (".5", always followed by a digit). So a '.' after whitespace
            # or after something that has just ended (a string, an IRI, a bracket) is the statement's end even when a
            # name follows it directly ("'x' .ex:b ex:p 'y' ." is two statements). GitHub issue #64.
            prev_char = data[i-1] if i > 0 else ''
            if continues_token and not next_char.isdigit() and (prev_char == '' or prev_char.isspace() or prev_char in '"\'>])'):
                continues_token = False
            if not continues_token:
                buf += c
                stmts.append((buf.strip(), stmt_start))
                buf = ''
                i += 1  # past '.'
                # Consume every line terminator up to the next statement
                # (including blank lines between statements), not just one -
                # stmt_start must be captured after all of them, not before,
                # so data[:stmt_start].count('\n') downstream counts
                # correctly regardless of how many blank lines separate two
                # statements. data[i] at this point is the first character
                # of the next statement (or EOF).
                while i < len(data) and data[i] in ('\n', '\r'):
                    if data[i:i+2] == '\r\n':
                        i += 2
                    else:
                        i += 1
                stmt_start = i
                continue
        buf += c
        i += 1

    if in_string or any(d > 0 for d in depth.values()):
        why = (f'unterminated {string_char!r} string at end of document' if in_string
               else f'unclosed {next(c for c, d in depth.items() if d > 0)!r} at end of document')
        line = data[:stmt_start].count('\n') + 1
        raise Turtle12SyntaxError(why, buf or data[stmt_start:], pos=len(buf or data[stmt_start:]), line=line)

    if buf.strip():
        stmts.append((buf.strip(), stmt_start))
    return stmts


def split_statements(data):
    """Split Turtle text into a list of statement strings.

    See split_statements_with_lines() for the same split with each
    statement's approximate source line number attached.

    Args:
        data: The Turtle 1.2 document text to split.

    Returns:
        A list of statement strings (prefix/base/version directives and
        triple statements), each stripped of surrounding whitespace.
    """
    return [stmt for stmt, _offset in _split_statements_impl(data)]


def split_statements_with_lines(data):
    """Split Turtle text into a list of (statement, line) pairs, line being
    the 1-based line number in *data* where that statement approximately
    begins (statement-start granularity - see _split_statements_impl).
    Raises Turtle12SyntaxError if the document ends with an unterminated
    string or an unclosed bracket.

    Args:
        data: The Turtle 1.2 document text to split.

    Returns:
        A list of (statement, line) pairs, line being the 1-based
        approximate source line number where that statement begins.
    """
    return [
        (stmt, data[:offset].count('\n') + 1)
        for stmt, offset in _split_statements_impl(data)
    ]


def classify_statement(stmt):
    """Classify a single statement string by its leading keyword.

    Args:
        stmt: A single statement string, as produced by split_statements().

    Returns:
        'version', 'prefix', or 'base' for a directive statement, 'triple'
        for anything else.
    """
    s = stmt.strip().lower()
    if s.startswith('@version') or s.startswith('version'):
        return 'version'
    if s.startswith('@prefix') or s.startswith('prefix'):
        return 'prefix'
    if s.startswith('@base') or s.startswith('base'):
        return 'base'
    return 'triple'


def extract_fields(stmt, typ, blank_counter=None):
    """Parse a single statement string into a fields dict.

    Args:
        stmt: A single statement string, as produced by split_statements().
        typ: The statement's kind, as returned by classify_statement() -
            'version', 'prefix', 'base', or 'triple'.
        blank_counter: A single-element list holding the next fresh
            blank-node suffix counter, shared across calls within one
            parse so minted blank nodes (`_:sl_N`) don't collide; None
            disables blank-node-property-list/collection expansion in
            subject position (for a caller that doesn't need it, e.g. a
            directive statement).

    Returns:
        A dict of the statement's fields - {'version': ...} for a VERSION
        directive, {'prefix': ..., 'iri': ...} for @prefix, {'iri': ...}
        for @base, or {'triple_set': [...]} for a triple statement (a list
        of subject/predicate/object/annotation field dicts) - or {} if the
        statement doesn't match its claimed type's grammar.
    """
    from starlayer.graph.parsers.errors import Turtle12SyntaxError

    s = stmt.strip()
    if typ == 'version':
        # Two spellings (RDF 1.2 Turtle): "@version "1.2" ." (dotted) and
        # "VERSION "1.2"" (bare, SPARQL-style) - both a single quoted label,
        # optionally followed by a '.'. Grammar: VersionSpecifier ::=
        # STRING_LITERAL_QUOTE | STRING_LITERAL_SINGLE_QUOTE only - the
        # long/triple-quoted forms (""".."""/'''...''') are a different
        # production and not valid here, and neither is a bare unquoted
        # number. A statement classified as 'version' (starts with the
        # keyword) that doesn't match this is malformed, not absent -
        # raise rather than silently discarding it as a no-op.
        m = re.match(r'@?version\s*([\'"])((?:(?!\1).)*)\1\s*\.?\s*$', s, re.IGNORECASE)
        if m:
            return {'version': m.group(2)}
        raise Turtle12SyntaxError(
            'malformed VERSION directive - expected a single-quoted string label, '
            'e.g. VERSION "1.2" or @version "1.2" . (not a triple-quoted string or '
            'an unquoted value)',
            s, pos=0,
        )
    elif typ == 'prefix':
        m = re.match(r'@?prefix\s+([\w-]*)\s*:\s*<([^>]+)>', s, re.IGNORECASE)
        if m:
            return {'prefix': m.group(1), 'iri': m.group(2)}
    elif typ == 'base':
        m = re.match(r'@?base\s*<([^>]+)>', s, re.IGNORECASE)
        if m:
            return {'iri': m.group(1)}
    elif typ == 'triple':
        body = s.rstrip('.')
        subj, rest = next_token(body.strip())
        inner_triples = []
        if subj == '[]' and blank_counter is not None:
            subj = f'_:sl_{blank_counter[0]}'
            blank_counter[0] += 1
        elif (
            blank_counter is not None
            and isinstance(subj, str)
            and subj.startswith('[') and subj.endswith(']')
        ):
            # A non-empty bracketed property list used as the statement's
            # own subject - Turtle's blankNodePropertyList production,
            # legal in subject position exactly like object position
            # (`[ :q :z ] .` or `[ :q :z ] :b :c .`, vs. the already-handled
            # `:s :p [ :q :z ] .`). Mirrors expand_triple_set()'s own
            # object-position expansion below - mint a fresh blank node,
            # recursively parse the bracket's inner content as if it were
            # `{bnode} inner .`, and use the blank node as this statement's
            # real subject. Must happen here, not in expand_triple_set():
            # when nothing follows the closing bracket (`rest` empty, the
            # `if subj and rest:` guard below never fires), extract_fields()
            # is the only place that ever sees the whole statement, and
            # previously just silently returned an empty triple_set instead
            # of raising or expanding - confirmed via a real Fuseki CONSTRUCT
            # response (`[ rdf:reifies <<( ... )>>; :q :z ] .`) round-tripped
            # through this parser, which produced zero triples with no
            # error at all. The one existing W3C Turtle 1.2 fixture using
            # this shape (turtle12-syntax-inside-01.ttl) is a
            # TestTurtlePositiveSyntax case, which only checks "parses
            # without raising" - never the resulting triples - so this gap
            # had zero test coverage that could have caught it.
            bnode = f'_:sl_{blank_counter[0]}'
            blank_counter[0] += 1
            inner = subj[1:-1].strip()
            if inner:
                inner_fields = extract_fields(f'{bnode} {inner} .', 'triple', blank_counter)
                if inner_fields and 'triple_set' in inner_fields:
                    inner_triples = inner_fields['triple_set']
            subj = bnode
        if subj and rest:
            triple_set = []
            for group in _split_on_delimiter(rest, ';'):
                pred, obj_str = next_token(group)
                if not pred or not obj_str:
                    continue
                for obj in _split_on_delimiter(obj_str, ','):
                    obj_tok, annotations = split_obj_and_annotations(obj)
                    entry = {
                        'subject': subj,
                        'predicate': pred,
                        'object': coerce_object(obj_tok),
                    }
                    if annotations:
                        entry['annotations'] = annotations
                        entry['object_str'] = obj_tok
                    triple_set.append(entry)
            return {'triple_set': inner_triples + triple_set}
        if inner_triples:
            return {'triple_set': inner_triples}
    return {}


def expand_triple_set(triple_set, blank_counter):
    """Expand [ ] blank nodes and ( ) collections into flat triple dicts.

    Args:
        triple_set: A list of triple field dicts, as produced by
            extract_fields() (each with 'subject'/'predicate'/'object' and
            optionally 'annotations'/'object_str').
        blank_counter: A single-element list holding the next fresh
            blank-node suffix counter, shared across calls within one
            parse.

    Returns:
        A new list of triple field dicts with every [ ]/( ) shorthand
        object resolved to a plain blank-node subject/object, recursively
        re-expanded until none remain.
    """
    result = []
    needs_reexpand = False
    subject_lists = {}

    for triple in triple_set:
        subj = triple['subject']
        pred = triple['predicate']
        obj = triple['object']
        obj_s = obj.strip() if isinstance(obj, str) else obj

        # A collection as the SUBJECT ("( 1 2 ) :q 3 .") is valid Turtle; it names the list's first cell. Expand it to
        # that blank node plus the list's own triples, which are expanded again below (GitHub issue #61: it used to
        # become a made-up IRI of the collection's text).
        if isinstance(subj, str) and subj.strip().startswith('(') and subj.strip().endswith(')'):
            elements = _parse_collection_elements(subj.strip()[1:-1].strip())
            if subj in subject_lists:
                triple = {**triple, 'subject': subject_lists[subj]}  # same statement, same list ("( :x ) :q 1 ; :r 2 .")
            elif not elements:
                triple = {**triple, 'subject': 'rdf:nil'}
            else:
                cell = f'_:sl_{blank_counter[0]}'
                blank_counter[0] += 1
                triple = {**triple, 'subject': cell}
                subject_lists[subj] = cell
                current = cell
                for idx, el in enumerate(elements):
                    result.append({'subject': current, 'predicate': 'rdf:first', 'object': coerce_object(el.strip())})
                    if idx < len(elements) - 1:
                        next_cell = f'_:sl_{blank_counter[0]}'
                        blank_counter[0] += 1
                        result.append({'subject': current, 'predicate': 'rdf:rest', 'object': next_cell})
                        current = next_cell
                    else:
                        result.append({'subject': current, 'predicate': 'rdf:rest', 'object': 'rdf:nil'})
                needs_reexpand = True
            subj = triple['subject']

        if isinstance(obj_s, str) and obj_s.startswith('[') and obj_s.endswith(']'):
            bnode = f'_:sl_{blank_counter[0]}'
            blank_counter[0] += 1
            head = {'subject': subj, 'predicate': pred, 'object': bnode}
            if triple.get('annotations'):
                head['annotations'] = triple['annotations']
                head['object_str'] = bnode
            result.append(head)
            inner = obj_s[1:-1].strip()
            if inner:
                inner_fields = extract_fields(f'{bnode} {inner} .', 'triple', blank_counter)
                if inner_fields and 'triple_set' in inner_fields:
                    result.extend(expand_triple_set(inner_fields['triple_set'], blank_counter))

        elif isinstance(obj_s, str) and obj_s.startswith('(') and obj_s.endswith(')'):
            elements = _parse_collection_elements(obj_s[1:-1].strip())
            if not elements:
                head = {'subject': subj, 'predicate': pred, 'object': 'rdf:nil'}
                if triple.get('annotations'):
                    head['annotations'] = triple['annotations']
                    head['object_str'] = 'rdf:nil'
                result.append(head)
                continue
            list_head = f'_:sl_{blank_counter[0]}'
            blank_counter[0] += 1
            head = {'subject': subj, 'predicate': pred, 'object': list_head}
            if triple.get('annotations'):
                head['annotations'] = triple['annotations']
                head['object_str'] = list_head
            result.append(head)
            current = list_head
            for idx, el in enumerate(elements):
                # coerce_object() (not just .strip()) - a bare numeric/boolean
                # collection member (e.g. "( 42 )", "( true false )") needs
                # the same string->Python-value coercion an ordinary
                # (non-list) object already gets in extract_fields(), or
                # _to_node() later rejects it as an "unrecognized term" -
                # confirmed via the W3C SHACL 1.2 test suite's
                # node-expr/shnex/constant.ttl ("mf:result ( 42 )") and
                # several core/ fixtures using "rdf:rest ( 2 )"-shaped lists.
                # A bracket/quote-wrapped member (needing further recursive
                # expansion, e.g. "[ ... ]") never matches coerce_object's
                # true/false/numeric patterns, so this is safe unconditionally.
                result.append({'subject': current, 'predicate': 'rdf:first', 'object': coerce_object(el.strip())})
                if idx < len(elements) - 1:
                    next_bnode = f'_:sl_{blank_counter[0]}'
                    blank_counter[0] += 1
                    result.append({'subject': current, 'predicate': 'rdf:rest', 'object': next_bnode})
                    current = next_bnode
                else:
                    result.append({'subject': current, 'predicate': 'rdf:rest', 'object': 'rdf:nil'})
            needs_reexpand = True

        else:
            result.append(triple)

    return expand_triple_set(result, blank_counter) if needs_reexpand else result


def _parse_collection_elements(inside):
    """Parse space-separated elements from the inside of a ( ... ) collection."""
    elements = []
    buf = ''
    depth = 0
    in_str = False
    str_char = ''
    skip = 0
    for pos, c in enumerate(inside):
        if skip:
            skip -= 1
            buf += c
            continue
        if in_str:
            buf += c
            if c == str_char:
                in_str = False
            continue
        if c in ('"', "'"):
            in_str, str_char = True, c
            buf += c
            continue
        # a reified triple "<<:s :p :o>>" is ONE element though it contains spaces; its << and >> count as brackets
        if inside[pos:pos + 2] == '<<':
            depth += 1
            skip = 1
            buf += c
            continue
        if inside[pos:pos + 2] == '>>':
            depth -= 1
            skip = 1
            buf += c
            continue
        if c in '[(':
            depth += 1
        elif c in '])':
            depth -= 1
        if c.isspace() and depth == 0 and buf.strip():
            elements.append(buf.strip())
            buf = ''
        else:
            buf += c
    if buf.strip():
        elements.append(buf.strip())
    return elements
