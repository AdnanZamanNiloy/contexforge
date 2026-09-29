from __future__ import annotations

from core.generation.citations import parse_citations


class TestValidCitations:
    def test_a_single_marker_is_kept(self) -> None:
        result = parse_citations("The model reports 97.06% accuracy [1].", 5)
        assert result.text == "The model reports 97.06% accuracy [1]."
        assert [c.index for c in result.citations] == [0]
        assert result.discarded == ()

    def test_adjacent_and_repeated_markers_deduplicate(self) -> None:
        result = parse_citations("A pipeline [1][2] returns a label [2].", 5)
        assert [c.index for c in result.citations] == [0, 1]
        assert result.text == "A pipeline [1][2] returns a label [2]."

    def test_a_grouped_marker_is_split_into_individuals(self) -> None:
        result = parse_citations("Revenue rose [1, 3] sharply.", 5)
        assert [c.index for c in result.citations] == [0, 2]
        assert result.text == "Revenue rose [1][3] sharply."


class TestOutOfRangeMarkers:
    """A citation to a passage that was never supplied must not reach the user.

    A model asked to cite can cite a number outside the retrieved set. Showing
    it produces a dead reference that reads as authoritative, which spends the
    reader's trust on something that does not exist.
    """

    def test_a_marker_past_the_last_source_is_removed(self) -> None:
        result = parse_citations("A claim citing a missing source [7].", 5)
        assert result.citations == ()
        assert result.discarded == ("[7]",)
        assert "[7]" not in result.text

    def test_removing_a_marker_does_not_leave_a_stray_space(self) -> None:
        result = parse_citations("Revenue was 45% in 2024 [9].", 5)
        assert result.text == "Revenue was 45% in 2024."

    def test_a_trailing_marker_does_not_leave_a_trailing_space(self) -> None:
        result = parse_citations("Ends with a bad ref [9]", 5)
        assert result.text == "Ends with a bad ref"

    def test_a_valid_marker_survives_alongside_a_discarded_one(self) -> None:
        result = parse_citations("Was 45% [1, 9] in 2024.", 5)
        assert [c.index for c in result.citations] == [0]
        # The whole group is reported, not just its bad element: the model
        # emitted "[1, 9]" as one marker, so recording it that way is the
        # faithful diagnostic.
        assert result.discarded == ("[1, 9]",)
        assert result.text == "Was 45% [1] in 2024."

    def test_every_marker_dropped_when_there_are_no_sources(self) -> None:
        # source_count=0 is short-circuited, so nothing is rewritten and the
        # answer is returned untouched rather than mangled.
        result = parse_citations("A claim [1].", 0)
        assert result.text == "A claim [1]."
        assert result.citations == ()


class TestSubscriptsAreNotCitations:
    """Array and code indexing must survive verbatim.

    This product answers questions about code, where "model[0]", "df[1]" and
    "rows[2]" are ordinary content. An earlier version of the matcher turned
    "model[0]" into "model", silently corrupting the answer. A citation stands
    on its own; a subscript is glued to an identifier.
    """

    def test_zero_indexed_array_access_is_preserved(self) -> None:
        text = "Indexing model[0] and df[1] must survive [1]."
        result = parse_citations(text, 5)
        assert "model[0]" in result.text
        assert "df[1]" in result.text
        assert [c.index for c in result.citations] == [0]

    def test_a_bare_index_expression_is_untouched(self) -> None:
        text = "text[0] = 1 and arr[i] and obj[key] intact"
        result = parse_citations(text, 3)
        assert result.text == text
        assert result.citations == ()

    def test_a_subscript_is_not_reported_as_a_discarded_citation(self) -> None:
        # It was never a citation, so counting it as a model miscount would
        # pollute the diagnostic.
        result = parse_citations("The first row is row[0] of the frame.", 3)
        assert result.discarded == ()


class TestNoMarkers:
    def test_an_answer_without_markers_is_returned_unchanged(self) -> None:
        text = "No markers here at all. Just prose about 97.06% and v1.2.3."
        result = parse_citations(text, 5)
        assert result.text == text
        assert result.citations == ()

    def test_bracketed_prose_is_left_alone(self) -> None:
        text = "See the [optional] section and the [first] chapter."
        result = parse_citations(text, 3)
        assert result.text == text
        assert result.citations == ()
