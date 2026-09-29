"""Tests for multi-source scoping shared by the project workspace.

Two features depend on the same idea — restricting a request to a *selection*
of sources rather than a single one:

- ``POST /query`` / ``POST /query/stream`` accept ``source_ids``.
- ``POST /mindmap/generate`` accepts ``source_ids``.

Both funnel through ``RAGOrchestrator._source_exclude_set``, which turns a
selection into an exclusion set over the indexed source list.  These tests pin
that behaviour plus the composite key that makes a multi-source mind map cache
correctly and order-independently.
"""

from __future__ import annotations

import pytest

from app.mindmap.schemas import (
    GenerateRequest,
    composite_key,
    split_composite_key,
)


class _FakeFaiss:
    """Stands in for FaissStore — only the source list is needed here.

    ``get_source_ids_async`` is what the orchestrator uses; it must load the
    store before reporting, which is the behaviour under test (the sync method
    returned an empty set before load and silently disabled scoping).
    """

    def __init__(self, source_ids: set[str]) -> None:
        self._source_ids = source_ids

    def get_source_ids(self) -> set[str]:
        return set(self._source_ids)

    async def get_source_ids_async(self) -> set[str]:
        return set(self._source_ids)


@pytest.fixture
def orchestrator_cls():
    from core.orchestrator import Orchestrator

    return Orchestrator


async def _exclude_set(orchestrator_cls, known, source_id=None, source_ids=None):
    orch = orchestrator_cls.__new__(orchestrator_cls)  # bypass __init__ wiring
    orch._faiss = _FakeFaiss(known)
    return await orch._source_exclude_set(source_id, source_ids)


# --------------------------------------------------------------------------- #
# Scoping a query to a selection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_selection_returns_none(orchestrator_cls):
    known = {"a", "b", "c"}
    assert await _exclude_set(orchestrator_cls, known) is None
    assert await _exclude_set(orchestrator_cls, known, source_id=None) is None
    assert await _exclude_set(orchestrator_cls, known, source_ids=None) is None
    assert await _exclude_set(orchestrator_cls, known, source_ids=[]) is None
    assert await _exclude_set(orchestrator_cls, known, source_ids=["  "]) is None


@pytest.mark.asyncio
async def test_single_source_excludes_everything_else(orchestrator_cls):
    known = {"repo:a/b", "doc:c", "video:d"}
    assert await _exclude_set(orchestrator_cls, known, source_id="doc:c") == {
        "repo:a/b",
        "video:d",
    }


@pytest.mark.asyncio
async def test_multiple_sources_exclude_only_the_rest(orchestrator_cls):
    known = {"repo:a/b", "doc:c", "video:d"}
    assert await _exclude_set(orchestrator_cls, known, source_ids=["repo:a/b", "video:d"]) == {"doc:c"}


@pytest.mark.asyncio
async def test_selecting_everything_excludes_nothing(orchestrator_cls):
    known = {"a", "b"}
    assert await _exclude_set(orchestrator_cls, known, source_ids=["a", "b"]) == set()


@pytest.mark.asyncio
async def test_source_ids_win_over_single_source_id(orchestrator_cls):
    known = {"a", "b", "c"}
    # The workspace sends a set; a legacy single source_id must not win.
    assert await _exclude_set(orchestrator_cls, known, "a", ["b"]) == {"a", "c"}


@pytest.mark.asyncio
async def test_blank_entries_are_dropped_before_scoping(orchestrator_cls):
    known = {"a", "b"}
    assert await _exclude_set(orchestrator_cls, known, source_ids=[" a ", "", None]) == {"b"}


@pytest.mark.asyncio
async def test_blank_single_source_id_is_ignored(orchestrator_cls):
    known = {"a", "b"}
    assert await _exclude_set(orchestrator_cls, known, source_id="   ") is None


@pytest.mark.asyncio
async def test_scoping_uses_the_loaded_source_list(orchestrator_cls):
    """Regression: scoping must not read an unloaded (empty) source list.

    ``_source_exclude_set`` used the synchronous, load-free accessor, which
    returns an empty set at the start of a process.  An empty exclude set means
    "filter nothing", so a query scoped to one source silently retrieved from
    every source — answering about a document the user did not select.
    """

    class _UnloadedBeforeAsyncFaiss:
        def __init__(self) -> None:
            self.loaded = False

        def get_source_ids(self) -> set[str]:
            # What the old code saw: empty until the store is loaded.
            return set() if not self.loaded else {"repo:a/b", "doc:c"}

        async def get_source_ids_async(self) -> set[str]:
            self.loaded = True
            return {"repo:a/b", "doc:c"}

    orch = orchestrator_cls.__new__(orchestrator_cls)
    orch._faiss = _UnloadedBeforeAsyncFaiss()
    # Selecting doc:c must exclude repo:a/b, not return an empty exclude set.
    assert await orch._source_exclude_set(None, ["doc:c"]) == {"repo:a/b"}


# --------------------------------------------------------------------------- #
# QueryRequest validation
# --------------------------------------------------------------------------- #


def test_query_request_accepts_source_ids():
    from app.schemas.query import QueryRequest

    req = QueryRequest(question="What is RRF?", source_ids=["a", "b"])
    assert req.source_ids == ["a", "b"]


def test_query_request_treats_all_blank_source_ids_as_unscoped():
    from app.schemas.query import QueryRequest

    req = QueryRequest(question="Anything?", source_ids=["  ", ""])
    assert req.source_ids is None


def test_query_request_defaults_to_using_the_knowledge_base():
    from app.schemas.query import QueryRequest

    assert QueryRequest(question="Anything?").no_sources is False


def test_query_request_can_disable_the_knowledge_base():
    from app.schemas.query import QueryRequest

    # No source selected: answer from general knowledge, never the corpus.
    assert QueryRequest(question="Tell me about source", no_sources=True).no_sources is True


# --------------------------------------------------------------------------- #
# Mind map selection keys
# --------------------------------------------------------------------------- #


def test_single_source_key_is_the_source_id_for_backwards_compatibility():
    # Maps generated before multi-source support are stored under the raw id,
    # so a single-source key must stay byte-identical or those caches are lost.
    assert composite_key(["repo:AdnanZamanNiloy/contexforge"]) == "repo:AdnanZamanNiloy/contexforge"


def test_multi_source_key_is_sorted_and_prefixed():
    key = composite_key(["video:d", "repo:a/b"])
    assert key == "multi:repo:a/b,video:d"
    assert key.startswith("multi:")


def test_multi_source_key_is_order_independent():
    forward = composite_key(["a", "b", "c"])
    backward = composite_key(["c", "b", "a"])
    assert forward == backward


def test_multi_source_key_deduplicates():
    assert composite_key(["a", "a", "b"]) == composite_key(["a", "b"])


def test_composite_key_roundtrips():
    ids = ["repo:a/b", "doc:c", "video:d"]
    assert sorted(split_composite_key(composite_key(ids))) == sorted(ids)


def test_split_composite_key_passes_through_single_ids():
    assert split_composite_key("repo:a/b") == ["repo:a/b"]


def test_composite_key_rejects_empty_selection():
    with pytest.raises(ValueError):
        composite_key([])
    with pytest.raises(ValueError):
        composite_key(["  "])


# --------------------------------------------------------------------------- #
# GenerateRequest resolution
# --------------------------------------------------------------------------- #


def test_generate_request_resolves_a_legacy_single_source():
    req = GenerateRequest(source_id="  repo:a/b  ")
    assert req.resolved_source_ids() == ["repo:a/b"]
    assert req.key() == "repo:a/b"


def test_generate_request_resolves_a_multi_source_selection():
    req = GenerateRequest(source_ids=[" b ", "a", "a"])
    assert req.resolved_source_ids() == ["b", "a"]
    assert req.key() == "multi:a,b"


def test_generate_request_prefers_source_ids_over_source_id():
    req = GenerateRequest(source_id="a", source_ids=["b", "c"])
    assert req.resolved_source_ids() == ["b", "c"]


def test_generate_request_requires_at_least_one_source():
    with pytest.raises(ValueError):
        GenerateRequest()
    with pytest.raises(ValueError):
        GenerateRequest(source_ids=["  "])


def test_generate_request_rejects_blank_single_source():
    with pytest.raises(ValueError):
        GenerateRequest(source_id="   ")
