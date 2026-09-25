"""Integration tests for the Model Hub HTTP API.

Dependency-overrides a temporary-storage-backed service so no real database or
API key is required, and asserts the HTTP contract — in particular that API
keys never appear in any response body.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_model_hub_service
from app.main import app
from app.model_hub.service import ModelHubService
from app.model_hub.storage import ModelHubStore


@pytest.fixture
def hub_client(tmp_path):
    store = ModelHubStore(db_path=tmp_path / "hub.db")
    service = ModelHubService(store=store)
    app.dependency_overrides[get_model_hub_service] = lambda: service
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_list_and_get_redacts_key(hub_client):
    async with hub_client as client:
        created = await client.post(
            "/models",
            json={
                "name": "GPT",
                "model_type": "llm",
                "runtime": "api",
                "provider": "openai",
                "model_id": "gpt-4o-mini",
                "api_key": "sk-top-secret",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["has_api_key"] is True
        assert "api_key" not in body
        assert "sk-top-secret" not in created.text

        listed = await client.get("/models")
        assert listed.status_code == 200
        assert "sk-top-secret" not in listed.text

        fetched = await client.get(f"/models/{body['id']}")
        assert fetched.status_code == 200
        assert "api_key" not in fetched.json()


@pytest.mark.asyncio
async def test_invalid_base_url_rejected(hub_client):
    async with hub_client as client:
        response = await client.post(
            "/models",
            json={
                "name": "Bad",
                "model_type": "llm",
                "runtime": "api",
                "provider": "custom",
                "model_id": "m",
                "base_url": "file:///etc/passwd",
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_chain_type_mismatch_returns_422(hub_client):
    async with hub_client as client:
        llm = (
            await client.post(
                "/models",
                json={
                    "name": "LLM",
                    "model_type": "llm",
                    "runtime": "api",
                    "provider": "openai",
                    "model_id": "gpt-4o-mini",
                    "api_key": "k",
                },
            )
        ).json()

        response = await client.post(
            "/chains",
            json={"name": "bad", "chain_type": "embedding", "model_ids": [llm["id"]]},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_serving_update_and_get(hub_client, monkeypatch):
    # Avoid touching the real pipeline during the integration test.
    import app.dependencies as deps

    async def noop():
        return None

    monkeypatch.setattr(deps, "apply_serving_configuration", noop)
    monkeypatch.setattr("app.model_hub.routes.apply_serving_configuration", noop, raising=False)

    async with hub_client as client:
        model = (
            await client.post(
                "/models",
                json={
                    "name": "LLM",
                    "model_type": "llm",
                    "runtime": "api",
                    "provider": "openai",
                    "model_id": "gpt-4o-mini",
                    "api_key": "k",
                },
            )
        ).json()

        updated = await client.put(
            "/serving",
            json={"tier": "llm", "mode": "single", "target": model["id"]},
        )
        assert updated.status_code == 200
        config = updated.json()
        assert config["llm_mode"] == "single"
        assert config["llm_target"] == model["id"]

        fetched = await client.get("/serving")
        assert fetched.json()["llm_mode"] == "single"


@pytest.mark.asyncio
async def test_delete_model_returns_ok(hub_client):
    async with hub_client as client:
        model = (
            await client.post(
                "/models",
                json={
                    "name": "LLM",
                    "model_type": "llm",
                    "runtime": "api",
                    "provider": "openai",
                    "model_id": "gpt-4o-mini",
                    "api_key": "k",
                },
            )
        ).json()

        deleted = await client.delete(f"/models/{model['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

        missing = await client.get(f"/models/{model['id']}")
        assert missing.status_code == 404
