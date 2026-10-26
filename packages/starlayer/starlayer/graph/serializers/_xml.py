"""Shared helpers for the XML writers (RDF/XML 1.2, TriX 1.2)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager

# XML 1.0 Char: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_ILLEGAL_XML_CHAR = re.compile('[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')

# XML NCName (no colon): NameStartChar without ':' then NameChar without ':'
_NAME_START = 'A-Z_a-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02ff\u0370-\u037d\u037f-\u1fff\u200c-\u200d\u2070-\u218f\u2c00-\u2fef\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufffd\U00010000-\U000effff'
_NAME_CHAR = _NAME_START + '\\-.0-9\u00b7\u0300-\u036f\u203f-\u2040'
_NCNAME = re.compile(f'[{_NAME_START}][{_NAME_CHAR}]*')


def is_ncname(name: str) -> bool:
    """True if ``name`` is an XML NCName that may be a namespace prefix (``xml`` and ``xmlns`` are reserved)."""
    return bool(_NCNAME.fullmatch(name)) and name.lower() not in ('xml', 'xmlns') and not re.fullmatch(r'ns\d+', name)


def check_xml_characters(root: ET.Element) -> None:
    """Raise ``ValueError`` if any text or attribute value in the tree has a character XML 1.0 cannot carry.

    XML 1.0 has no way to write U+0000-U+0008, U+000B, U+000C, U+000E-U+001F (not even as a character reference), so the
    document could not be read back; failing at the write is better than a saved file that does not load (GitHub issue #133)."""
    for el in root.iter():
        for value in (el.text, el.tail, *el.attrib.values()):
            if value:
                m = _ILLEGAL_XML_CHAR.search(value)
                if m:
                    raise ValueError(
                        f'cannot write U+{ord(m.group()):04X} in XML: it is not a legal XML 1.0 character '
                        f'(in {value[:40]!r}); use a format that can carry it, such as N-Triples or Turtle'
                    )


@contextmanager
def private_namespace_map() -> Iterator[None]:
    """Run with a copy of ElementTree's (process-wide) namespace map and put the original back afterwards, so the prefixes
    one document registered do not leak into the next (a rebound prefix kept its old name)."""
    saved = dict(ET._namespace_map)
    try:
        yield
    finally:
        ET._namespace_map.clear()
        ET._namespace_map.update(saved)
