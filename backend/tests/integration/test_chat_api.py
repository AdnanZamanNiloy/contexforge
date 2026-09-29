"""HTTP contract tests for persisted chat sessions and messages.

Exercises the real SQLite stores (isolated to ``tmp_path`` by the autouse
fixture), so these also prove that project deletion cascades to sessions,
messages and their per-message source selections.
"""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.fixture
def client():
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _create_project(c, name="Chat Project"):
    response = await c.post("/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_session_lifecycle_and_per_message_sources(client):
    async with client as c:
        project_id = await _create_project(c)

        created = await c.post(f"/projects/{project_id}/sessions", json={"title": "First"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert created.json()["project_id"] == project_id

        # Turn one scoped to a single source.
        first = await c.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "text": "Q1", "source_ids": ["src-a"]},
        )
        assert first.status_code == 201
        assert first.json()["source_ids"] == ["src-a"]

        # Turn two scoped to a different set — history keeps both.
        await c.post(
            f"/sessions/{session_id}/messages",
            json={
                "role": "assistant",
                "text": "A1",
                "source_ids": ["src-a", "src-b"],
                "status": "done",
            },
        )

        detail = await c.get(f"/sessions/{session_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["message_count"] == 2
        assert [m["source_ids"] for m in body["messages"]] == [["src-a"], ["src-a", "src-b"]]

        listed = await c.get(f"/projects/{project_id}/sessions")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1


@pytest.mark.asyncio
async def test_messages_preserve_turn_order_on_refresh(client):
    """A reopened session loads user → assistant → user → assistant."""
    async with client as c:
        project_id = await _create_project(c, "Ordering")
        session_id = (await c.post(f"/projects/{project_id}/sessions", json={})).json()["id"]

        for role, text in [
            ("user", "Q1"),
            ("assistant", "A1"),
            ("user", "Q2"),
            ("assistant", "A2"),
        ]:
            await c.post(
                f"/sessions/{session_id}/messages",
                json={"role": role, "text": text, "status": "done", "source_ids": ["src-a"]},
            )

        # Reopening the session (fresh GET) must return the exact sequence.
        detail = await c.get(f"/sessions/{session_id}")
        assert [(m["role"], m["text"]) for m in detail.json()["messages"]] == [
            ("user", "Q1"),
            ("assistant", "A1"),
            ("user", "Q2"),
            ("assistant", "A2"),
        ]


@pytest.mark.asyncio
async def test_session_for_unknown_project_is_404(client):
    async with client as c:
        response = await c.post("/projects/proj_missing/sessions", json={"title": "x"})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_session_is_404(client):
    async with client as c:
        assert (await c.get("/sessions/chat_missing")).status_code == 404
        assert (await c.post("/sessions/chat_missing/messages", json={"role": "user", "text": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_project_cascades_to_sessions_and_messages(client):
    async with client as c:
        project_id = await _create_project(c, "Doomed")
        other_id = await _create_project(c, "Survivor")

        doomed = (await c.post(f"/projects/{project_id}/sessions", json={})).json()["id"]
        survivor = (await c.post(f"/projects/{other_id}/sessions", json={})).json()["id"]
        await c.post(
            f"/sessions/{doomed}/messages",
            json={"role": "user", "text": "bye", "source_ids": ["src-a"]},
        )
        await c.post(
            f"/sessions/{survivor}/messages",
            json={"role": "user", "text": "hi", "source_ids": ["src-b"]},
        )

        deleted = await c.delete(f"/projects/{project_id}")
        assert deleted.status_code == 204

        # Sessions for the deleted project are gone...
        assert (await c.get(f"/projects/{project_id}/sessions")).status_code == 404
        assert (await c.get(f"/sessions/{doomed}")).status_code == 404
        # ...while the other project's session and message remain intact.
        assert (await c.get(f"/sessions/{survivor}")).status_code == 200
        kept = await c.get(f"/sessions/{survivor}/messages")
        assert kept.json()[0]["source_ids"] == ["src-b"]


@pytest.mark.asyncio
async def test_deleting_a_session_removes_its_messages(client):
    async with client as c:
        project_id = await _create_project(c, "Session delete")
        session_id = (await c.post(f"/projects/{project_id}/sessions", json={})).json()["id"]
        await c.post(f"/sessions/{session_id}/messages", json={"role": "user", "text": "x"})

        assert (await c.delete(f"/sessions/{session_id}")).status_code == 204
        assert (await c.get(f"/sessions/{session_id}")).status_code == 404
        assert (await c.get(f"/sessions/{session_id}/messages")).status_code == 404


@pytest.mark.asyncio
async def test_rename_session(client):
    async with client as c:
        project_id = await _create_project(c, "Rename")
        session_id = (await c.post(f"/projects/{project_id}/sessions", json={})).json()["id"]
        renamed = await c.patch(f"/sessions/{session_id}", json={"title": "Renamed"})
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renamed"


@pytest.mark.asyncio
async def test_update_message_records_streaming_result(client):
    async with client as c:
        project_id = await _create_project(c, "Stream")
        session_id = (await c.post(f"/projects/{project_id}/sessions", json={})).json()["id"]
        message = (
            await c.post(
                f"/sessions/{session_id}/messages",
                json={"role": "assistant", "text": "", "status": "streaming"},
            )
        ).json()

        updated = await c.patch(
            f"/messages/{message['id']}",
            json={"text": "final answer", "status": "done"},
        )
        assert updated.status_code == 200
        assert updated.json()["text"] == "final answer"
        assert updated.json()["status"] == "done"

