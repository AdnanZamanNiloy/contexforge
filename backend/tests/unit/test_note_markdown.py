"""Tests for note normalisation.

Generation latency for a note is output-bound: the prompt input is capped, but
the prose the model writes was not, so request time scaled with however much the
model felt like writing.  These tests pin the normalisation backstop that bounds
the stored note regardless of what comes back, and the citation filter that
stops an invented passage reference from reaching the reader.
"""

from __future__ import annotations

from app.notes.service import (
    MAX_NOTE_LINES,
    MAX_SECTIONS,
    _normalize_note,
    _shorten_title,
)

GOOD_NOTE = (
    "# Retrieval pipeline\n"
    "\n"
    "The pipeline chunks, embeds and indexes every ingested document.\n"
    "\n"
    "## Stages\n"
    "\n"
    "Chunks are 512 tokens with 50 tokens of overlap.\n"
    "\n"
    "## Limits\n"
    "\n"
    "Retrieval returns at most 25 chunks."
)


def _note(sections: int, paragraphs: int = 2, lines_per_section: int = 1) -> str:
    body = ["# Subject"]
    for s in range(sections):
        body.append(f"## Section {s}")
        for p in range(paragraphs):
            for _ in range(lines_per_section):
                body.append(f"Body text for section {s} paragraph {p}.")
    return "\n\n".join(body)


# --- title handling -------------------------------------------------------


def test_the_h1_is_returned_as_the_title_and_leaves_the_body():
    title, body = _normalize_note(GOOD_NOTE, "Fallback")
    assert title == "Retrieval pipeline"
    assert not body.lstrip().startswith("#")
    assert "## Stages" in body


def test_a_missing_h1_falls_back_to_the_derived_title():
    title, body = _normalize_note("## Stages\n\nSomething happened.", "My repo")
    assert title == "My repo"
    assert body.startswith("## Stages")


def test_a_second_h1_is_demoted_rather_than_duplicating_the_title():
    _, body = _normalize_note("# One\n\nText.\n\n# Two\n\nMore.", "Fallback")
    # No line is still an H1 — the second title came back down to a section.
    assert not [ln for ln in body.splitlines() if ln.startswith("# ")]
    assert "## Two" in body


def test_an_enclosing_code_fence_is_unwrapped():
    fenced = f"```markdown\n{GOOD_NOTE}\n```"
    title, body = _normalize_note(fenced, "Fallback")
    assert title == "Retrieval pipeline"
    assert "```" not in body


def test_a_fenced_block_inside_the_note_survives_intact():
    note = "# T\n\n## Install\n\n```bash\npip install x\n```\n"
    _, body = _normalize_note(note, "Fallback")
    assert "pip install x" in body
    assert body.count("```") == 2


def test_a_long_title_is_shortened_on_a_word_boundary():
    title = "a very long title " * 10
    assert len(_shorten_title(title)) <= 80
    assert _shorten_title(title).endswith("...")


# --- budget enforcement ---------------------------------------------------


def test_a_note_inside_budget_is_left_untouched():
    title, body = _normalize_note(GOOD_NOTE, "Fallback")
    assert title == "Retrieval pipeline"
    assert body.count("##") == 2


def test_section_count_is_capped():
    _, body = _normalize_note(_note(sections=MAX_SECTIONS + 10), "Fallback")
    assert body.count("\n## ") + body.startswith("## ") <= MAX_SECTIONS


def test_line_count_is_capped():
    _, body = _normalize_note(_note(sections=3, lines_per_section=80), "Fallback")
    assert len([ln for ln in body.splitlines() if ln.strip()]) <= MAX_NOTE_LINES


def test_headings_beyond_three_levels_are_flattened():
    _, body = _normalize_note("# T\n\n## A\n\n#### Too deep\n\n#### Deeper", "F")
    assert "####" not in body
    assert "### Too deep" in body


def test_a_note_with_no_content_is_reported_as_empty():
    _, body = _normalize_note("", "Fallback")
    assert body == ""


def test_a_truncated_note_ends_on_a_complete_paragraph():
    """The cut must not land mid-sentence — that reads as a rendering bug."""
    text = "\n\n".join(
        [f"## Section {s}" + "\n" + "\n".join(f"Line {i} of section {s}." for i in range(40)) for s in range(3)]
    )
    _, body = _normalize_note(f"# T\n\n{text}", "F")
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert lines[-1].endswith(".")
    assert len(lines) <= MAX_NOTE_LINES


def test_a_note_of_one_unbroken_block_is_still_capped():
    """No paragraph break to back off to, yet the budget still has to hold."""
    _, body = _normalize_note("# T\n\n" + "\n".join(f"Line {i}." for i in range(300)), "F")
    assert len([ln for ln in body.splitlines() if ln.strip()]) <= MAX_NOTE_LINES


def test_the_prompt_asks_for_no_passage_markers():
    """Citations were dropped from the note; the prompt must not request them."""
    from app.notes.service import _SYSTEM_PROMPT

    assert "Cite" not in _SYSTEM_PROMPT
    assert "citation" not in _SYSTEM_PROMPT.lower()
