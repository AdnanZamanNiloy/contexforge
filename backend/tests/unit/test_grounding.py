from __future__ import annotations

from core.generation.grounding import check_grounding, extract_claims


class TestExtractClaims:
    def test_finds_percentages_versions_and_dates(self) -> None:
        claims = extract_claims("It scored 97.06% on v1.2.3 in 2024-03-15.")
        assert "97.06%" in claims
        assert any("1.2.3" in c for c in claims)
        assert "2024-03-15" in claims

    def test_currency_is_not_double_counted_by_the_decimal_pattern(self) -> None:
        # "$1,200.00" matches the currency pattern as a whole and the
        # multi-decimal pattern from inside it. Counting both would turn one
        # invented figure into two and halve the support ratio.
        claims = extract_claims("Revenue hit $1,200.00.")
        assert claims == ["$1,200.00"]

    def test_repeated_claims_are_deduplicated(self) -> None:
        claims = extract_claims("It is 97.06% accurate, and 97.06% was the final score.")
        assert claims.count("97.06%") == 1

    def test_ignores_small_integers_and_ordinary_prose(self) -> None:
        # Bare integers and general vocabulary are phrased too freely to check,
        # and the prompt deliberately asks for synthesised prose.
        assert extract_claims("It uses 3 libraries and is fast.") == []

    def test_sentence_ending_period_is_not_read_as_a_version(self) -> None:
        assert extract_claims("Released in 2024. It works.") == []


class TestCheckGrounding:
    def test_a_supported_figure_is_grounded(self) -> None:
        chunks = ["The model reports 97.06% accuracy across the test set."]
        report = check_grounding("The Random Forest reports 97.06% accuracy.", chunks)
        assert report.is_grounded
        assert report.support_ratio == 1.0

    def test_an_invented_figure_is_caught(self) -> None:
        chunks = ["The backend exposes a single prediction endpoint."]
        report = check_grounding("Revenue grew 45% in 2024-03-15.", chunks)
        assert not report.is_grounded
        assert set(report.unsupported) == {"45%", "2024-03-15"}

    def test_a_mixed_answer_is_scored_not_rejected(self) -> None:
        chunks = ["The model reports 97.06% accuracy."]
        report = check_grounding("It is 97.06% accurate and released 2024-03-15.", chunks)
        assert not report.is_grounded
        assert report.unsupported == ("2024-03-15",)
        assert report.support_ratio == 0.5

    def test_an_answer_with_nothing_checkable_is_grounded(self) -> None:
        # A refusal must never be penalised: there is nothing to invent.
        report = check_grounding("No information is available on this.", ["irrelevant text"])
        assert report.is_grounded
        assert report.checked == 0
        assert report.support_ratio == 1.0

    def test_refusal_is_never_treated_as_ungrounded(self) -> None:
        for refusal in (
            "No authentication scheme is specified in the material.",
            "The available source contains no recipes or ingredients.",
        ):
            assert check_grounding(refusal, ["some unrelated chunk"]).is_grounded

    def test_matches_across_a_line_break_in_the_source(self) -> None:
        # Figures are frequently split across lines by extraction; collapsing
        # whitespace stops a correct answer being flagged.
        chunks = ["The reported accuracy was\n97.06% on the held out set."]
        assert check_grounding("Accuracy was 97.06%.", chunks).is_grounded

    def test_uses_full_chunk_text_not_a_preview(self) -> None:
        """The figure must be findable beyond the first 200 characters.

        text_preview truncates at 200 chars and a figure commonly sits past
        that, so checking a preview would flag correct answers as invented.
        This is the regression that motivated reading chunk.text directly.
        """
        padding = "Lorem ipsum dolor sit amet. " * 20  # >400 chars
        chunks = [f"{padding}The model reports 97.06% accuracy."]
        assert len(chunks[0]) > 200
        assert chunks[0][:200].find("97.06") == -1, "fixture must place the figure past the preview"
        assert check_grounding("The model reports 97.06% accuracy.", chunks).is_grounded

    def test_a_qualitative_answer_is_never_penalised(self) -> None:
        # The prompt asks for synthesis and interpretation, so answers that
        # share little vocabulary with the source are correct, not hallucinated.
        chunks = ["The API exposes POST /predict and loads a sklearn pipeline at startup."]
        report = check_grounding(
            "The system keeps inference close to the data layer, which keeps round trips short.",
            chunks,
        )
        assert report.is_grounded
