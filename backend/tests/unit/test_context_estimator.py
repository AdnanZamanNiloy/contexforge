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
    clamp_depth_for_selection,
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


class TestDepthClamping:
    def test_broad_over_two_sources_reduces_to_something_runnable(self):
        # "broad" over two small sources cannot deliver a broad context, and
        # reporting it as broad would be the exact dishonesty this prevents.
        effective = clamp_depth_for_selection("broad", selected_count=2)

        assert effective in CONTEXT_DEPTHS
        assert CONTEXT_DEPTHS[effective]["max_sources"] <= 2

    def test_broad_over_many_sources_is_kept(self):
        assert clamp_depth_for_selection("broad", selected_count=15) == "broad"

    def test_unknown_depth_reduces_to_focused(self):
        assert clamp_depth_for_selection("nonsense", selected_count=50) == "focused"
        assert clamp_depth_for_selection(None, selected_count=50) == "focused"

    def test_never_raises_above_the_requested_depth(self):
        for name in CONTEXT_DEPTHS:
            for count in range(0, 30):
                assert (
                    CONTEXT_DEPTHS[clamp_depth_for_selection(name, selected_count=count)]["max_sources"]
                    <= CONTEXT_DEPTHS[name]["max_sources"]
                )


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
    async def test_reports_over_budget_when_the_depth_cannot_cope(self):
        index = _index({f"s{i}": 20 for i in range(10)})
        estimate = await estimate_context(source_ids=[f"s{i}" for i in range(10)], chunk_index=index, depth="focused")

        assert estimate.over_budget is True

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
