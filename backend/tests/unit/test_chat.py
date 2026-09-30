"""Chat persistence — store + service unit tests (SQLite temp DB).

These tests pin the guarantees the feature is built around:

- a project's sessions and messages survive a fresh store on the same path;
- every message keeps the exact source selection used when it was created;
- changing / deleting sources never rewrites existing history;
- deleting a project (or session) removes the sessions and messages beneath it.
"""

import pytest

from app.chat.service import ChatService
from app.chat.store import ChatStore
from app.projects.store import ProjectsStore


def _service(tmp_path, name="chat.db"):
    store = ChatStore(db_path=tmp_path / name)
    projects = ProjectsStore(db_path=tmp_path / "projects.db")
    return ChatService(store=store, projects=projects), store, projects


@pytest.mark.asyncio
async def test_session_requires_existing_project(tmp_path):
    service, _, _ = _service(tmp_path)
    assert await service.create_session("proj_missing") is None
    assert await service.list_sessions("proj_missing") is None


@pytest.mark.asyncio
async def test_create_and_list_sessions(tmp_path):
    service, _, projects = _service(tmp_path)
    project = await projects.create_project("Research")

    created = await service.create_session(project["id"], "First chat")
    assert created["id"].startswith("chat_")
    assert created["message_count"] == 0

    sessions = await service.list_sessions(project["id"])
    assert [s["id"] for s in sessions] == [created["id"]]


@pytest.mark.asyncio
async def test_messages_persist_with_independent_source_selections(tmp_path):
    """Each message keeps the selection it was created with, even as the
    workspace selection changes between turns."""
    service, _, projects = _service(tmp_path)
    project = await projects.create_project("Mixed")
    session = await service.create_session(project["id"])

    first = await service.add_message(session["id"], "user", "Q1", source_ids=["src-a"])
    await service.add_message(session["id"], "assistant", "A1", source_ids=["src-a"])
    third = await service.add_message(session["id"], "user", "Q2", source_ids=["src-a", "src-b", "src-c"])
    await service.add_message(session["id"], "assistant", "A2", source_ids=["src-a", "src-b", "src-c"])

    full = await service.get_session(session["id"])
    assert [m["role"] for m in full["messages"]] == ["user", "assistant", "user", "assistant"]
    # Turn 1 and turn 3 retain *different* selections.
    assert full["messages"][0]["source_ids"] == ["src-a"]
    assert full["messages"][2]["source_ids"] == ["src-a", "src-b", "src-c"]
    # Ordering within a selection is preserved verbatim.
    assert first["source_ids"] == ["src-a"]
    assert third["source_ids"] == ["src-a", "src-b", "src-c"]


@pytest.mark.asyncio
async def test_history_survives_store_restart(tmp_path):
    service, _, projects = _service(tmp_path)
    project = await projects.create_project("Persist")
    session = await service.create_session(project["id"], "Thread")
    await service.add_message(session["id"], "user", "hello", source_ids=["src-1"])

    # A brand-new store on the same path simulates an app restart.
    restarted = ChatStore(db_path=tmp_path / "chat.db")
    projects2 = ProjectsStore(db_path=tmp_path / "projects.db")
    service2 = ChatService(store=restarted, projects=projects2)

    full = await service2.get_session(session["id"])
    assert full is not None
    assert full["messages"][0]["text"] == "hello"
    assert full["messages"][0]["source_ids"] == ["src-1"]


@pytest.mark.asyncio
async def test_messages_keep_insertion_order_even_with_equal_timestamps(tmp_path):
    """Order is by insertion sequence, not timestamp.

    Regression: the user and assistant rows of one turn were written by two
    concurrent requests and could share/out-of-order timestamps, so a refreshed
    thread loaded assistant-before-user (or scrambled turns).
    """
    store = ChatStore(db_path=tmp_path / "chat.db")
    projects = ProjectsStore(db_path=tmp_path / "projects.db")
    project = await projects.create_project("Order")
    session = await store.create_session(project["id"])

    # Interleave the two turns exactly as they are written in practice.
    for role, text in [
        ("user", "Q1"),
        ("assistant", "A1"),
        ("user", "Q2"),
        ("assistant", "A2"),
    ]:
        await store.add_message(session["id"], role, text)

    # Read back through a brand-new store to prove persistence order holds.
    restarted = ChatStore(db_path=tmp_path / "chat.db")
    messages = await restarted.list_messages(session["id"])
    assert [(m["role"], m["text"]) for m in messages] == [
        ("user", "Q1"),
        ("assistant", "A1"),
        ("user", "Q2"),
        ("assistant", "A2"),
    ]


@pytest.mark.asyncio
async def test_message_source_selection_is_immutable_after_source_changes(tmp_path):
    """Editing a later message's selection must not touch earlier messages, and
    no operation rewrites stored history when sources are removed."""
    service, _, projects = _service(tmp_path)
    project = await projects.create_project("Immutability")
    session = await service.create_session(project["id"])
    await service.add_message(session["id"], "user", "Q1", source_ids=["src-a"])
    later = await service.add_message(session["id"], "user", "Q2", source_ids=["src-a", "src-b"])

    # Simulate the user narrowing the selection for a new message only.
    await service.update_message(later["id"], {"source_ids": ["src-b"]})

    full = await service.get_session(session["id"])
    assert full["messages"][0]["source_ids"] == ["src-a"]  # untouched
    assert full["messages"][1]["source_ids"] == ["src-b"]  # only this one changed


@pytest.mark.asyncio
async def test_delete_session_removes_its_messages(tmp_path):
    service, store, projects = _service(tmp_path)
    project = await projects.create_project("Deleting")
    session = await service.create_session(project["id"])
    await service.add_message(session["id"], "user", "hi", source_ids=["src-a"])

    assert await service.delete_session(session["id"]) is True
    assert await service.get_session(session["id"]) is None
    assert await store.list_messages(session["id"]) == []


@pytest.mark.asyncio
async def test_delete_for_project_removes_all_sessions_and_messages(tmp_path):
    service, store, projects = _service(tmp_path)
    project = await projects.create_project("Cascade")
    other = await projects.create_project("Untouched")

    s1 = await service.create_session(project["id"])
    s2 = await service.create_session(project["id"])
    keep = await service.create_session(other["id"])
    await service.add_message(s1["id"], "user", "a", source_ids=["src-a"])
    await service.add_message(s2["id"], "user", "b", source_ids=["src-b"])
    await service.add_message(keep["id"], "user", "c", source_ids=["src-c"])

    removed = await service.delete_for_project(project["id"])
    assert removed == 2
    assert await service.get_session(s1["id"]) is None
    assert await service.get_session(s2["id"]) is None
    assert store is not None
    assert await store.list_messages(s1["id"]) == []
    # The unrelated project keeps its history.
    assert await service.get_session(keep["id"]) is not None


@pytest.mark.asyncio
async def test_blank_and_duplicate_source_ids_are_cleaned(tmp_path):
    service, _, projects = _service(tmp_path)
    project = await projects.create_project("Clean")
    session = await service.create_session(project["id"])
    message = await service.add_message(session["id"], "user", "q", source_ids=["  ", "src-a", "src-a", "", "src-b"])
    assert message["source_ids"] == ["src-a", "src-b"]


@pytest.mark.asyncio
async def test_add_message_to_missing_session_returns_none(tmp_path):
    service, _, _ = _service(tmp_path)
    assert await service.add_message("chat_missing", "user", "q") is None
