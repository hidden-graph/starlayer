"""
starlayergraph.parsers.syntax

Statement-level parsing for Turtle 1.2. Splits raw text into statements,
classifies them, extracts predicate-object fields, and expands blank-node
shorthand and RDF collections into flat triple dicts.
"""

import re

from rdflib import Literal
from rdflib.namespace import XSD

from starlayergraph.parsers.lexer import next_token, split_obj_and_annotations

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
    Confirmed via the W3C SPARQL 1.2 eval-triple-terms/op-2 fixture, whose
    "123e0" was coming out "123.0"^^xsd:decimal instead of xsd:double under
    the old int/float-coercing version of this function.
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
    """Split text on delim at bracket-depth 0, respecting strings."""
    parts = []
    buf = ''
    depth = 0
    in_str = False
    str_char = ''
    for ch in text:
        if in_str:
            buf += ch
            if ch == str_char:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str, str_char = True, ch
            buf += ch
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
    j = i
    while j < len(data):
        c = data[j]
        if in_string:
            if c == string_char:
                if data[j:j+3] == string_char * 3:
                    j += 3
                    in_string = False
                    continue
                elif data[j-1] != '\\':
                    in_string = False
            j += 1
            continue
        if c in ('"', "'"):
            in_string = True
            string_char = c
            if data[j:j+3] == c * 3:
                j += 3
            else:
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
    TurtleSyntaxError in starlayergraph.parsers.errors.
    """
    from starlayergraph.parsers.errors import TurtleSyntaxError

    stmts = []
    buf = ''
    stmt_start = 0
    depth = {'[': 0, '(': 0, '{': 0, '<': 0}
    in_string = False
    string_char = ''
    i = 0
    while i < len(data):
        at_line_start = (i == 0 or data[i-1] in ('\n', '\r'))
        if at_line_start:
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
            buf += c
            if c == string_char:
                if data[i:i+3] == string_char * 3:
                    buf += data[i+1:i+3]
                    i += 2
                    in_string = False
                elif data[i-1] != '\\':
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
        if c in ('"', "'"):
            if data[i:i+3] == c * 3:
                in_string = True
                string_char = c
                buf += c * 3
                i += 3
                continue
            else:
                in_string = True
                string_char = c
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
            # A '.' at depth 0 terminates the statement unless it's the
            # decimal point of a DECIMAL/DOUBLE literal (Turtle grammar:
            # both always have a digit immediately after the '.', e.g.
            # "3.14" or ".5e10" - a statement-terminating '.' never does,
            # since it's followed by whitespace/the next statement/EOF).
            # Previously required the '.' to be immediately followed by a
            # newline instead, which - as a side effect - silently merged
            # any two statements written on the same physical line into
            # one, dropping everything the resulting bad split fed to a
            # regex-based field extractor that just ignores its own
            # unmatched trailing text (worst for a directive: found and
            # fixed together with this same bug).
            next_char = data[i+1] if i + 1 < len(data) else ''
            if not next_char.isdigit():
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
        raise TurtleSyntaxError(why, buf or data[stmt_start:], pos=len(buf or data[stmt_start:]), line=line)

    if buf.strip():
        stmts.append((buf.strip(), stmt_start))
    return stmts


def split_statements(data):
    """Split Turtle text into a list of statement strings.

    See split_statements_with_lines() for the same split with each
    statement's approximate source line number attached.
    """
    return [stmt for stmt, _offset in _split_statements_impl(data)]


def split_statements_with_lines(data):
    """Split Turtle text into a list of (statement, line) pairs, line being
    the 1-based line number in *data* where that statement approximately
    begins (statement-start granularity - see _split_statements_impl).
    Raises TurtleSyntaxError if the document ends with an unterminated
    string or an unclosed bracket.
    """
    return [
        (stmt, data[:offset].count('\n') + 1)
        for stmt, offset in _split_statements_impl(data)
    ]


def classify_statement(stmt):
    """Return 'version', 'prefix', 'base', or 'triple'."""
    s = stmt.strip().lower()
    if s.startswith('@version') or s.startswith('version'):
        return 'version'
    if s.startswith('@prefix') or s.startswith('prefix'):
        return 'prefix'
    if s.startswith('@base') or s.startswith('base'):
        return 'base'
    return 'triple'


def extract_fields(stmt, typ, blank_counter=None):
    """Parse a single statement string into a fields dict."""
    from starlayergraph.parsers.errors import TurtleSyntaxError

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
        raise TurtleSyntaxError(
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
    Returns a new list with all shorthand forms resolved."""
    result = []
    needs_reexpand = False

    for triple in triple_set:
        subj = triple['subject']
        pred = triple['predicate']
        obj = triple['object']
        obj_s = obj.strip() if isinstance(obj, str) else obj

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
    for c in inside:
        if in_str:
            buf += c
            if c == str_char:
                in_str = False
            continue
        if c in ('"', "'"):
            in_str, str_char = True, c
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
