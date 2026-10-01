"""Unit tests for the context estimator and depth resolution.

The estimator is the honest-reporting half of this feature: it has to price a
selection and, just as importantly, report how much of that selection would
actually reach the model.  These tests pin both halves, including the cases that
would make the readout a lie — a depth larger than the selection supports, a
source id that is not in the index, and a selection whose per-document cap binds
before the overall chunk cap does.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from app.context.estimator import (
    CONTEXT_DEPTHS,
    estimate_context,
    resolve_context_depth,
)


def _chunk(source_id: str, index: int, text: str = "chunk body text", **metadata):
    return type(
        "FakeChunk",
        (),
        {
            "chunk_id": f"{source_id}:{index}",
            "text": text,
            "metadata": MappingProxyType({"source_id": source_id, **metadata}),
            "source_id": source_id,
        },
    )()


class _FakeIndex:
    """Stands in for the FAISS store; only this method is ever called."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def get_chunks_by_source_id(self, source_id):
        if not source_id:
            return list(self._chunks)
        return [c for c in self._chunks if c.source_id == source_id]


def _index(sources: dict[str, list[int]], body: str = "x" * 200):
    chunks = []
    for sid, count in sources.items():
        for i in range(count):
            chunks.append(_chunk(sid, i, f"{body}{i}"))
    return _FakeIndex(chunks)


class TestDepthResolution:
    def test_resolves_each_known_depth(self):
        for name in CONTEXT_DEPTHS:
            assert resolve_context_depth(name)["top_k_rerank"] == CONTEXT_DEPTHS[name]["top_k_rerank"]

    def test_defaults_to_focused(self):
        assert resolve_context_depth(None) == CONTEXT_DEPTHS["focused"]
        assert resolve_context_depth("nonsense") == CONTEXT_DEPTHS["focused"]

    def test_deeper_depths_retrieve_more(self):
        focused = CONTEXT_DEPTHS["focused"]
        broad = CONTEXT_DEPTHS["broad"]
        assert broad["top_k_retrieval"] > focused["top_k_retrieval"]
        assert broad["top_k_rerank"] > focused["top_k_rerank"]
        assert broad["per_source_cap"] > focused["per_source_cap"]
        assert broad["max_sources"] > focused["max_sources"]


class TestDepthIsAppliedAsAsked:
    """A depth is applied as requested; it is never quietly downgraded.

    The estimator used to clamp a wide depth down to a narrow one whenever few
    sources were selected, reasoning that a wide setting "would behave like a
    narrow one".  That was false — every depth differs in chunk limits as well as
    source count — and it made the control completely inert for a single selected
    document, which is the case a user widens the depth precisely to read more of.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("depth", ["focused", "balanced", "broad"])
    async def test_effective_depth_matches_the_request(self, depth: str) -> None:
        index = _index({"a": 4})
        estimate = await estimate_context(source_ids=["a"], chunk_index=index, depth=depth)

        assert estimate.effective_depth == depth

    @pytest.mark.asyncio
    @pytest.mark.parametrize("depth", ["focused", "balanced", "broad"])
    async def test_a_single_source_still_gets_that_depths_chunk_limits(self, depth: str) -> None:
        # The regression that made the buttons look broken: with one source
        # selected, every depth reported the focused limits.
        index = _index({"a": 30})
        estimate = await estimate_context(source_ids=["a"], chunk_index=index, depth=depth)

        assert estimate.prompt_chunk_limit == CONTEXT_DEPTHS[depth]["top_k_rerank"]
        assert estimate.per_source_cap == CONTEXT_DEPTHS[depth]["per_source_cap"]

    @pytest.mark.asyncio
    async def test_widening_the_depth_never_reads_less(self) -> None:
        index = _index({"a": 30})
        focused = await estimate_context(source_ids=["a"], chunk_index=index, depth="focused")
        balanced = await estimate_context(source_ids=["a"], chunk_index=index, depth="balanced")
        broad = await estimate_context(source_ids=["a"], chunk_index=index, depth="broad")

        assert focused.prompt_token_estimate <= balanced.prompt_token_estimate
        assert balanced.prompt_token_estimate <= broad.prompt_token_estimate

    @pytest.mark.asyncio
    async def test_an_unknown_depth_falls_back_to_focused(self) -> None:
        index = _index({"a": 4})
        estimate = await estimate_context(source_ids=["a"], chunk_index=index, depth="nonsense")

        assert estimate.effective_depth == "focused"

    @pytest.mark.asyncio
    async def test_sources_beyond_the_depth_are_named_not_hidden(self) -> None:
        # Dropping sources is a real ceiling, so it has to be reported — but as a
        # cap, not as the depth being reduced.
        index = _index({f"s{i}": 2 for i in range(10)})
        estimate = await estimate_context(
            source_ids=[f"s{i}" for i in range(10)],
            chunk_index=index,
            depth="focused",
        )

        assert estimate.effective_depth == "focused"
        assert len(estimate.dropped_source_ids) == 10 - CONTEXT_DEPTHS["focused"]["max_sources"]


class TestEstimateContext:
    @pytest.mark.asyncio
    async def test_prices_a_single_source(self):
        index = _index({"a": 4})
        estimate = await estimate_context(source_ids=["a"], chunk_index=index)

        assert estimate.source_count == 1
        assert estimate.sources[0].source_id == "a"
        assert estimate.sources[0].chunk_count == 4
        assert estimate.total_char_count > 0
        assert estimate.total_token_count > 0

    @pytest.mark.asyncio
    async def test_prices_the_whole_knowledge_base_when_nothing_is_selected(self):
        index = _index({"a": 3, "b": 3})
        estimate = await estimate_context(source_ids=[], chunk_index=index)

        assert estimate.source_count == 2
        # An unscoped query really does search everything, so the estimate for
        # "nothing selected" must reflect that rather than looking empty.
        assert estimate.total_token_count > 0

    @pytest.mark.asyncio
    async def test_reports_the_gap_between_available_and_used(self):
        # The central claim: most of what is selected never reaches the model.
        ids = [f"s{i}" for i in range(8)]
        index = _index(dict.fromkeys(ids, 30), body="y" * 400)
        estimate = await estimate_context(source_ids=ids, chunk_index=index)

        assert estimate.total_token_count > estimate.prompt_token_estimate
        assert 0 < estimate.usable_fraction < 1

    @pytest.mark.asyncio
    async def test_usable_fraction_is_one_when_everything_fits(self):
        index = _index({"a": 1}, body="z" * 50)
        estimate = await estimate_context(source_ids=["a"], chunk_index=index)

        assert estimate.usable_fraction == 1.0

    @pytest.mark.asyncio
    async def test_per_source_cap_binds_before_the_chunk_cap(self):
        # One enormous document: the overall chunk ceiling is generous, but the
        # reranker refuses to take more than `per_source_cap` chunks from any
        # single source, so that is the number that must govern.
        index = _index({"big": 40}, body="w" * 500)
        focused = CONTEXT_DEPTHS["focused"]
        estimate = await estimate_context(source_ids=["big"], chunk_index=index, depth="focused")

        per_source_ceiling = focused["per_source_cap"] * 512
        assert estimate.prompt_token_estimate <= per_source_ceiling
        assert estimate.usable_fraction < 1

    @pytest.mark.asyncio
    async def test_names_the_sources_a_depth_would_drop(self):
        index = _index({f"s{i}": 3 for i in range(6)})
        estimate = await estimate_context(source_ids=[f"s{i}" for i in range(6)], chunk_index=index, depth="focused")

        assert len(estimate.dropped_source_ids) == 6 - CONTEXT_DEPTHS["focused"]["max_sources"]
        # Dropped, but still priced: they are in the selection.
        assert estimate.source_count == 6

    @pytest.mark.asyncio
    async def test_reports_a_selected_source_that_is_not_in_the_index(self):
        index = _index({"a": 2})
        estimate = await estimate_context(source_ids=["a", "ghost"], chunk_index=index)

        assert estimate.missing_source_ids == ["ghost"]
        assert estimate.source_count == 1

    @pytest.mark.asyncio
    async def test_flags_a_selection_beyond_diminishing_returns(self):
        index = _index({f"s{i}": 40 for i in range(12)}, body="q" * 500)
        estimate = await estimate_context(source_ids=[f"s{i}" for i in range(12)], chunk_index=index, depth="broad")

        assert estimate.beyond_diminishing_returns is True

    @pytest.mark.asyncio
    async def test_titles_a_repository_by_its_repo(self):
        index = _FakeIndex(
            [
                _chunk(
                    "repo:o/n",
                    0,
                    "text",
                    source_type="github",
                    repo="o/n",
                    title="LICENSE",
                )
            ]
        )
        estimate = await estimate_context(source_ids=["repo:o/n"], chunk_index=index)

        assert estimate.sources[0].title == "o/n"

    @pytest.mark.asyncio
    async def test_handles_an_empty_index(self):
        estimate = await estimate_context(source_ids=[], chunk_index=_FakeIndex([]))

        assert estimate.source_count == 0
        assert estimate.total_token_count == 0
        assert estimate.usable_fraction == 0.0
