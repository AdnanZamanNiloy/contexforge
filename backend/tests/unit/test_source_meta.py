"""Tests for persisted source title overrides.

A source's title is derived from chunk metadata held in FAISS/BM25.  Renaming
records an override in a small side store that ``GET /ingest/sources`` layers
over the derived title.  These tests pin that behaviour: the override persists,
it wins over the derived title, and it is cleaned up when the source goes away.
"""

from __future__ import annotations

import pytest

from app.sources.schemas import UpdateSourceRequest
from app.sources.storage import SourceMetaStore


@pytest.fixture
def store(tmp_path):
    return SourceMetaStore(db_path=tmp_path / "sources.db")


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_overrides_initially(store):
    assert await store.all_titles() == {}


@pytest.mark.asyncio
async def test_set_title_persists(store):
    await store.set_title("repo:a/b", "Payments runbook")
    assert await store.all_titles() == {"repo:a/b": "Payments runbook"}


@pytest.mark.asyncio
async def test_renaming_replaces_the_previous_title(store):
    await store.set_title("a", "First")
    await store.set_title("a", "Second")
    assert await store.all_titles() == {"a": "Second"}


@pytest.mark.asyncio
async def test_overrides_are_per_source(store):
    await store.set_title("a", "Alpha")
    await store.set_title("b", "Bravo")
    assert await store.all_titles() == {"a": "Alpha", "b": "Bravo"}


@pytest.mark.asyncio
async def test_clear_drops_one_override(store):
    await store.set_title("a", "Alpha")
    await store.set_title("b", "Bravo")
    await store.clear("a")
    assert await store.all_titles() == {"b": "Bravo"}


@pytest.mark.asyncio
async def test_clear_on_an_unknown_source_is_a_no_op(store):
    await store.set_title("a", "Alpha")
    await store.clear("does-not-exist")
    assert await store.all_titles() == {"a": "Alpha"}


@pytest.mark.asyncio
async def test_clear_all_drops_every_override(store):
    await store.set_title("a", "Alpha")
    await store.set_title("b", "Bravo")
    await store.clear_all()
    assert await store.all_titles() == {}


@pytest.mark.asyncio
async def test_overrides_survive_a_new_store_instance(tmp_path):
    path = tmp_path / "sources.db"
    await SourceMetaStore(db_path=path).set_title("a", "Persisted")
    # A fresh instance stands in for a process restart.
    assert await SourceMetaStore(db_path=path).all_titles() == {"a": "Persisted"}


@pytest.mark.asyncio
async def test_source_id_with_a_slash_round_trips(store):
    await store.set_title("repo:owner/name", "Contexforge")
    assert await store.all_titles() == {"repo:owner/name": "Contexforge"}


# --------------------------------------------------------------------------- #
# Request validation
# --------------------------------------------------------------------------- #


def test_title_is_trimmed():
    assert UpdateSourceRequest(title="  Payments  ").title == "Payments"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_blank_title_is_rejected(bad):
    with pytest.raises(ValueError):
        UpdateSourceRequest(title=bad)


def test_overlong_title_is_rejected():
    with pytest.raises(ValueError):
        UpdateSourceRequest(title="x" * 500)
