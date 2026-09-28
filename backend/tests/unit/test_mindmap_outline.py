"""Tests for the mind map output budget.

Generation latency here is output-bound, not input-bound: the prompt input is
capped, but the outline the model writes was not, so request time scaled with
however many branches it chose to emit.  These tests pin the normalisation
backstop that bounds the stored map regardless of what the model returns.
"""

from __future__ import annotations

import pytest

from app.mindmap.service import MAX_OUTLINE_LINES, _normalize_markdown


def _outline(roots: int, children: int, grandchildren: int = 0) -> str:
    lines = ["- Root"]
    for r in range(roots):
        lines.append(f"  - Branch {r}")
        for c in range(children):
            lines.append(f"    - Leaf {r}.{c}")
            for g in range(grandchildren):
                lines.append(f"      - Detail {r}.{c}.{g}")
    return "\n".join(lines)


def test_a_small_outline_is_left_untouched():
    text = _outline(2, 2)
    assert _normalize_markdown(text) == text


def test_branch_count_is_capped():
    # 30 roots would otherwise produce 61 lines.
    trimmed = _normalize_markdown(_outline(30, 1))
    assert len([ln for ln in trimmed.splitlines() if ln.strip()]) <= MAX_OUTLINE_LINES


def test_total_lines_are_capped():
    trimmed = _normalize_markdown(_outline(12, 4, 2))
    assert len([ln for ln in trimmed.splitlines() if ln.strip()]) <= MAX_OUTLINE_LINES


def test_depth_beyond_three_levels_is_dropped():
    trimmed = _normalize_markdown(_outline(1, 1, 3))
    # A fourth level would be 6+ spaces of indent.
    assert all((len(ln) - len(ln.lstrip())) < 6 for ln in trimmed.splitlines() if ln.strip())


def test_the_root_survives_trimming():
    trimmed = _normalize_markdown(_outline(30, 2))
    assert trimmed.splitlines()[0].strip() == "- Root"


def test_a_stub_is_rejected_in_favour_of_the_full_answer():
    # If trimming would leave nothing but a root, keep what the model produced
    # rather than storing a useless stub.
    over_budget = _outline(40, 0)
    trimmed = _normalize_markdown(over_budget)
    assert len([ln for ln in trimmed.splitlines() if ln.strip()]) >= 2


def test_empty_input_stays_empty():
    assert _normalize_markdown("") == ""
    assert _normalize_markdown("   ") == ""


def test_code_fences_and_headings_are_stripped():
    raw = "```markdown\n### Heading\n- Root\n  - Leaf\n```"
    assert _normalize_markdown(raw) == "- Root\n  - Leaf"


@pytest.mark.parametrize("garbage", [None, 0, []])
def test_non_string_input_is_tolerated(garbage):
    assert _normalize_markdown(garbage) == ""
