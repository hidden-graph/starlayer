"""Unit tests for codekg.extractor.docstrings.parse_docstring().

Includes the plan's own canonical worked example (encoding.py::term_key's
AFTER-cleanup docstring, quoted verbatim from the plan document) as a
literal fixture, plus a second fixture built the same way for tt_hash -
the plan names tt_hash as getting "the same treatment" as term_key but
only spells out term_key's AFTER text verbatim, so tt_hash's fixture here
is constructed following that exact same Args:/Returns: grammar rather
than quoted from the plan directly.
"""

from codekg.extractor.docstrings import parse_docstring


class TestNoneAndEmpty:
    def test_none_input(self):
        assert parse_docstring(None) == {"summary": "", "params": {}, "returns": None}

    def test_empty_string_input(self):
        assert parse_docstring("") == {"summary": "", "params": {}, "returns": None}


class TestPlainProseOnly:
    def test_single_line_summary_only(self):
        result = parse_docstring("Just a short summary, nothing else.")
        assert result == {
            "summary": "Just a short summary, nothing else.",
            "params": {},
            "returns": None,
        }

    def test_multi_paragraph_summary_only(self):
        raw = """Top paragraph of prose.

        Second paragraph, still just prose, no Args/Returns at all.
        """
        result = parse_docstring(raw)
        assert result["params"] == {}
        assert result["returns"] is None
        assert result["summary"] == (
            "Top paragraph of prose.\n\nSecond paragraph, still just prose, no Args/Returns at all."
        )


class TestSummaryArgsReturns:
    def test_summary_two_params_one_wrapped_and_returns(self):
        raw = '''Canonicalize something useful.

        Longer explanation of why this exists.

        Args:
            term: The RDF term to canonicalize.
            other: A second parameter whose description
                wraps onto a continuation line.

        Returns:
            The canonicalized string form.
        '''
        result = parse_docstring(raw)
        assert result["summary"] == "Canonicalize something useful.\n\nLonger explanation of why this exists."
        assert result["params"] == {
            "term": "The RDF term to canonicalize.",
            "other": "A second parameter whose description wraps onto a continuation line.",
        }
        assert result["returns"] == "The canonicalized string form."


class TestReturnsWithoutArgs:
    def test_returns_with_no_args_section(self):
        raw = """Return something.

        Returns:
            A plain description with no Args section at all.
        """
        result = parse_docstring(raw)
        assert result["summary"] == "Return something."
        assert result["params"] == {}
        assert result["returns"] == "A plain description with no Args section at all."


class TestUnrecognizedTrailingSection:
    def test_stray_raises_section_after_returns_not_absorbed(self):
        raw = """Do a risky thing.

        Returns:
            The result of doing the risky thing.

        Raises:
            ValueError: if something goes wrong.
        """
        result = parse_docstring(raw)
        assert result["summary"] == "Do a risky thing."
        assert result["returns"] == "The result of doing the risky thing."
        assert "ValueError" not in (result["returns"] or "")
        assert "Raises" not in (result["returns"] or "")

    def test_stray_section_after_args_before_returns(self):
        raw = """Do a thing.

        Args:
            x: The input value.

        Raises:
            ValueError: if x is bad.

        Returns:
            Nothing useful.
        """
        result = parse_docstring(raw)
        assert result["params"] == {"x": "The input value."}
        # The stray "Raises:" section, sitting between Args and Returns,
        # ends the Args section (column-0 non-blank line) - its own
        # content is dropped rather than absorbed into either section.
        assert "ValueError" not in result["params"].get("x", "")


class TestPlanCanonicalExamples:
    def test_term_key_after_version_from_plan(self):
        # Quoted verbatim from the plan document (clever-napping-mountain.md).
        raw = '''Canonical string form of an RDF term for use as one of tt_hash's
        three inputs.

        Uses .n3(), not plain str() - str(Literal(...)) always returns just
        the lexical form, dropping language tag/datatype, so two distinct
        literals can collide. Checks isinstance(term, Node) rather than
        isinstance(term, str) because every rdflib term type is itself a
        str subclass.

        Args:
            term: The RDF term (must be a Node, not a bare str).

        Returns:
            The term's N3-serialized canonical string form.
        '''
        result = parse_docstring(raw)
        assert result["summary"] == (
            "Canonical string form of an RDF term for use as one of tt_hash's\n"
            "three inputs.\n\n"
            "Uses .n3(), not plain str() - str(Literal(...)) always returns just\n"
            "the lexical form, dropping language tag/datatype, so two distinct\n"
            "literals can collide. Checks isinstance(term, Node) rather than\n"
            "isinstance(term, str) because every rdflib term type is itself a\n"
            "str subclass."
        )
        assert result["params"] == {"term": "The RDF term (must be a Node, not a bare str)."}
        assert result["returns"] == "The term's N3-serialized canonical string form."

    def test_tt_hash_after_version_constructed_same_grammar(self):
        # Not quoted from the plan (which only spells out term_key's AFTER
        # text verbatim) - constructed following the identical Args:/
        # Returns: grammar the plan describes "the same treatment"
        # applying to tt_hash, based on tt_hash's own real current
        # docstring content in encoding.py.
        raw = '''Return a 16-hex-char content-addressed ID for a triple term.

        Inputs are the canonical string representations of the resolved
        nodes (full URIs, bnode IDs, or literal N3 strings). 16 hex chars
        = 64 bits, keeping birthday-bound collision risk negligible even
        for graphs with heavy reification.

        Args:
            s_str: Canonical string form of the triple's subject.
            p_str: Canonical string form of the triple's predicate.
            o_str: Canonical string form of the triple's object.

        Returns:
            A 16-character hex string uniquely identifying this
            (s, p, o) triple.
        '''
        result = parse_docstring(raw)
        assert result["params"] == {
            "s_str": "Canonical string form of the triple's subject.",
            "p_str": "Canonical string form of the triple's predicate.",
            "o_str": "Canonical string form of the triple's object.",
        }
        assert result["returns"] == "A 16-character hex string uniquely identifying this (s, p, o) triple."
        assert result["summary"].startswith("Return a 16-hex-char content-addressed ID for a triple term.")


class TestDefensiveFallback:
    def test_malformed_args_entry_does_not_crash(self):
        # A param line that doesn't match the exact 4-space grammar - no
        # exception, just ignored/handled gracefully.
        raw = """Summary.

        Args:
          not_properly_indented: oops only 2 spaces

        Returns:
            Fine.
        """
        result = parse_docstring(raw)
        assert result["returns"] == "Fine."

    def test_no_exception_on_arbitrary_text(self):
        # Never raises, regardless of structure.
        parse_docstring("Args:\nReturns:\n    weird\nArgs:\n    x: y\n")
