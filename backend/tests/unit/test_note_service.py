"""Tests for the note service.

The note is generated once per *selection* and reused afterwards, so the two
behaviours worth pinning are that a repeat request is served from the store
rather than the model, and that two selections differing only in the order the
user picked their sources address the same note.
"""

from __future__ import annotations

import pytest

from app.notes.schemas import composite_key, split_composite_key
from app.notes.service import MAX_CHUNKS, NoteError, NoteService

pytestmark = pytest.mark.asyncio

REPLY = "# Widgets\n\n## What they do\n\nThey count things.\n"


class FakeChunk:
    def __init__(self, text: str, source_id: str, index: int) -> None:
        self.text = text
        self.source_id = source_id
        self.metadata = {"filename": f"{source_id}-part{index}.txt"}


class FakeFaiss:
    """Serves chunks per source id, and remembers what it was asked for."""

    def __init__(self, by_source: dict[str, list[FakeChunk]]) -> None:
        self._by_source = by_source
        self.asked: list[str] = []

    async def get_chunks_by_source_id(self, source_id: str | None) -> list[FakeChunk]:
        self.asked.append(source_id)
        return list(self._by_source.get(source_id, []))


class ScriptedLLM:
    def __init__(self, replies: list[str] | None = None) -> None:
        self._replies = list(replies or [REPLY])
        self.calls: list[str] = []

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls.append(prompt)
        return self._replies.pop(0) if self._replies else REPLY


def _service(tmp_path, faiss: FakeFaiss, llm: ScriptedLLM) -> NoteService:
    from app.notes.storage import NoteStore

    return NoteService(
        store=NoteStore(tmp_path / "notes.db"),
        faiss=faiss,
        llm=llm,
    )


def _two_sources() -> FakeFaiss:
    return FakeFaiss(
        {
            "doc:a": [FakeChunk("Alpha content.", "doc:a", 0)],
            "doc:b": [FakeChunk("Beta content.", "doc:b", 0)],
        }
    )


async def test_a_generated_note_is_persisted_and_returned(tmp_path):
    llm = ScriptedLLM()
    service = _service(tmp_path, _two_sources(), llm)

    note = await service.generate("doc:a")

    assert note["title"] == "Widgets"
    assert note["markdown"].startswith("# Widgets")
    assert note["chunk_count"] == 1
    assert await service.get("doc:a") is not None


async def test_a_repeat_request_is_served_from_the_store(tmp_path):
    llm = ScriptedLLM()
    service = _service(tmp_path, _two_sources(), llm)

    first = await service.generate("doc:a")
    second = await service.generate("doc:a")

    assert len(llm.calls) == 1, "a cached note must not call the model again"
    assert first["markdown"] == second["markdown"]


async def test_refresh_bypasses_the_cache(tmp_path):
    llm = ScriptedLLM([REPLY, "# Fresh\n\n## New\n\nRewritten.\n"])
    service = _service(tmp_path, _two_sources(), llm)

    await service.generate("doc:a")
    refreshed = await service.generate("doc:a", refresh=True)

    assert len(llm.calls) == 2
    assert refreshed["title"] == "Fresh"


async def test_source_order_does_not_change_the_cache_entry(tmp_path):
    llm = ScriptedLLM()
    service = _service(tmp_path, _two_sources(), llm)

    forward = await service.generate(["doc:a", "doc:b"])
    reversed_ = await service.generate(["doc:b", "doc:a"])

    assert forward["source_id"] == reversed_["source_id"]
    assert len(llm.calls) == 1


async def test_the_multi_source_prompt_carries_every_source(tmp_path):
    llm = ScriptedLLM()
    service = _service(tmp_path, _two_sources(), llm)

    note = await service.generate(["doc:a", "doc:b"])
    prompt = llm.calls[0]

    assert "Alpha content." in prompt
    assert "Beta content." in prompt
    assert "Group sections by theme" in prompt
    assert note["chunk_count"] == 2
    assert split_composite_key(note["source_id"]) == ["doc:a", "doc:b"]


async def test_the_prompt_asks_for_no_passage_markers(tmp_path):
    """Passages are no longer numbered, so the note carries no ``[n]`` markers."""
    faiss = FakeFaiss({"doc:a": [FakeChunk(f"Body {i}.", "doc:a", i) for i in range(4)]})
    llm = ScriptedLLM(["# T\n\n## A\n\nSays 25 items.\n"])
    service = _service(tmp_path, faiss, llm)

    saved = await service.generate("doc:a")

    assert not [ln for ln in llm.calls[0].splitlines() if ln.startswith("[")]
    assert "[n]" not in saved["markdown"]
    assert "25 items." in saved["markdown"]


async def test_a_missing_source_does_not_sink_the_note(tmp_path):
    llm = ScriptedLLM()
    service = _service(tmp_path, _two_sources(), llm)

    note = await service.generate(["doc:a", "doc:deleted"])

    assert note["chunk_count"] == 1


async def test_an_empty_selection_is_rejected(tmp_path):
    service = _service(tmp_path, _two_sources(), ScriptedLLM())
    with pytest.raises(NoteError):
        await service.generate([])


async def test_a_selection_with_no_indexed_content_is_rejected(tmp_path):
    service = _service(tmp_path, FakeFaiss({}), ScriptedLLM())
    with pytest.raises(NoteError):
        await service.generate("doc:missing")


async def test_a_large_source_is_sampled_rather_than_sent_whole(tmp_path):
    faiss = FakeFaiss({"repo:acme/big": [FakeChunk(f"Body {i}.", "repo:acme/big", i) for i in range(500)]})
    llm = ScriptedLLM()
    service = _service(tmp_path, faiss, llm)

    note = await service.generate("repo:acme/big")

    assert note["chunk_count"] == MAX_CHUNKS
    assert llm.calls[0].count("Body ") == MAX_CHUNKS


async def test_the_selection_key_is_shared_with_the_mind_map(tmp_path):
    """A note and a map over the same selection must resolve to one cache entry."""
    from app.mindmap.schemas import composite_key as mindmap_key

    ids = ["doc:b", "doc:a"]
    assert composite_key(ids) == mindmap_key(ids)
    assert composite_key(["doc:a"]) == "doc:a"
    assert split_composite_key("multi:doc:a,doc:b") == ["doc:a", "doc:b"]


async def test_an_unrelated_legacy_notes_table_does_not_break_the_store(tmp_path):
    """Regression: a pre-existing ``notes`` table must not shadow this one.

    ``CREATE TABLE IF NOT EXISTS`` silently accepts a table of any shape, so
    sharing the name with the older project-notes table meant every query failed
    with ``no such column: source_id`` on an existing database.
    """
    import sqlite3

    db = tmp_path / "notes.db"
    legacy = sqlite3.connect(str(db))
    legacy.execute(
        """
        CREATE TABLE notes (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL DEFAULT '',
            origin     TEXT NOT NULL DEFAULT 'human',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    legacy.execute(
        "INSERT INTO notes (id, project_id, title, content, origin, created_at, updated_at) "
        "VALUES ('note_x', 'p1', 'Mine', 'body', 'human', 'now', 'now')"
    )
    legacy.commit()
    legacy.close()

    service = _service(tmp_path, _two_sources(), ScriptedLLM())
    saved = await service.generate("doc:a")
    assert saved["title"] == "Widgets"
    assert await service.get("doc:a") is not None

    # The old rows are untouched, not migrated away or dropped.
    check = sqlite3.connect(str(db))
    assert check.execute("SELECT title FROM notes").fetchall() == [("Mine",)]
    assert check.execute("SELECT COUNT(*) FROM generated_notes").fetchone()[0] == 1
    check.close()
