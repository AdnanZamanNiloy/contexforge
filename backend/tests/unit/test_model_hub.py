"""Unit tests for the Model Hub service and store.

These tests use a temporary SQLite database and stub the live provider calls,
so no network access or API keys are needed.  They verify the security and
compatibility invariants that matter most:

- API keys are never exposed on read.
- LLM models cannot join embedding chains (and vice versa).
- Embedding chains reject incompatible vector dimensions.
- Serving selection resolves to the right runtime config.
"""

from __future__ import annotations

import pytest

from app.model_hub import factory
from app.model_hub.schemas import (
    ChainCreate,
    ModelCreate,
    ModelUpdate,
)
from app.model_hub.service import ModelHubError, ModelHubService
from app.model_hub.storage import ModelHubStore


@pytest.fixture
def service(tmp_path):
    store = ModelHubStore(db_path=tmp_path / "model_hub.db")
    return ModelHubService(store=store)


def _api_model(**overrides):
    base = {
        "name": "GPT test",
        "model_type": "llm",
        "runtime": "api",
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "api_key": "sk-secret-value",
    }
    base.update(overrides)
    return ModelCreate(**base)


def _embedding_model(**overrides):
    base = {
        "name": "Embed test",
        "model_type": "embedding",
        "runtime": "api",
        "provider": "openai",
        "model_id": "text-embedding-3-small",
        "api_key": "sk-embed-secret",
    }
    base.update(overrides)
    return ModelCreate(**base)


@pytest.mark.asyncio
async def test_api_key_is_never_returned(service):
    created = await service.create_model(_api_model())
    assert created["has_api_key"] is True
    assert "api_key" not in created
    assert "sk-secret-value" not in str(created)

    listed = await service.list_models()
    assert "sk-secret-value" not in str(listed)

    fetched = await service.get_model(created["id"])
    assert "api_key" not in fetched


@pytest.mark.asyncio
async def test_update_can_clear_and_replace_key(service):
    created = await service.create_model(_api_model())

    # Omitted key leaves it untouched.
    updated = await service.update_model(created["id"], ModelUpdate(name="Renamed"))
    assert updated["has_api_key"] is True

    # Empty string clears it.
    cleared = await service.update_model(created["id"], ModelUpdate(api_key=""))
    assert cleared["has_api_key"] is False

    # Non-empty replaces it.
    replaced = await service.update_model(created["id"], ModelUpdate(api_key="new-key"))
    assert replaced["has_api_key"] is True


@pytest.mark.asyncio
async def test_base_url_validation(service):
    with pytest.raises(ValueError):
        _api_model(base_url="file:///etc/passwd")
    with pytest.raises(ValueError):
        _api_model(base_url="not-a-url")

    created = await service.create_model(_api_model(base_url="https://api.openai.com/v1/"))
    assert created["base_url"] == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_chain_type_isolation(service):
    llm = await service.create_model(_api_model())
    emb = await service.create_model(_embedding_model())

    # LLM in an embedding chain → rejected.
    with pytest.raises(ModelHubError):
        await service.create_chain(
            ChainCreate(name="bad", chain_type="embedding", model_ids=[llm["id"]])
        )

    # Embedding in an LLM chain → rejected.
    with pytest.raises(ModelHubError):
        await service.create_chain(
            ChainCreate(name="bad", chain_type="llm", model_ids=[emb["id"]])
        )

    # Valid chains succeed.
    chain = await service.create_chain(
        ChainCreate(name="good", chain_type="llm", model_ids=[llm["id"]])
    )
    assert chain["chain_type"] == "llm"


@pytest.mark.asyncio
async def test_embedding_chain_dimension_compatibility(service):
    first = await service.create_model(_embedding_model(name="emb-1"))
    second = await service.create_model(_embedding_model(name="emb-2"))

    store = service._store
    await store.update_model(first["id"], {"dimension": 1536})
    await store.update_model(second["id"], {"dimension": 768})

    with pytest.raises(ModelHubError, match="incompatible vector dimensions"):
        await service.create_chain(
            ChainCreate(
                name="emb",
                chain_type="embedding",
                model_ids=[first["id"], second["id"]],
            )
        )

    await store.update_model(second["id"], {"dimension": 1536})
    chain = await service.create_chain(
        ChainCreate(name="emb", chain_type="embedding", model_ids=[first["id"], second["id"]])
    )
    assert chain["model_ids"] == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_serving_single_and_chain(service):
    llm = await service.create_model(_api_model())
    chain = await service.create_chain(
        ChainCreate(name="llm chain", chain_type="llm", model_ids=[llm["id"]])
    )

    await service.update_serving("llm", "single", llm["id"])
    cfg = await service.resolve_llm_configs()
    assert cfg and cfg[0]["id"] == llm["id"]

    await service.update_serving("llm", "chain", chain["id"])
    cfg = await service.resolve_llm_configs()
    assert cfg and cfg[0]["id"] == llm["id"]

    # Serving an embedding chain as the LLM tier is rejected.
    emb_chain = await service.create_chain(
        ChainCreate(
            name="emb chain",
            chain_type="embedding",
            model_ids=[(await service.create_model(_embedding_model()))["id"]],
        )
    )
    with pytest.raises(ModelHubError):
        await service.update_serving("llm", "chain", emb_chain["id"])


@pytest.mark.asyncio
async def test_delete_model_prunes_chains_and_serving(service):
    llm = await service.create_model(_api_model())
    chain = await service.create_chain(
        ChainCreate(name="llm chain", chain_type="llm", model_ids=[llm["id"]])
    )
    await service.update_serving("llm", "single", llm["id"])

    await service.delete_model(llm["id"])

    updated_chain = await service.get_chain(chain["id"])
    assert updated_chain["model_ids"] == []
    serving = await service.get_serving()
    assert serving["llm_mode"] == "disabled"


@pytest.mark.asyncio
async def test_serving_disabled_by_default(service):
    assert await service.resolve_llm_configs() is None
    assert await service.resolve_embedding_config() is None


def test_factory_builds_openai_compat_llm():
    llm = factory.build_llm(
        {
            "runtime": "api",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": "k",
            "base_url": "https://api.example.com/v1",
        }
    )
    assert llm._model == "gpt-4o-mini"


def test_factory_requires_base_url_for_unknown_provider():
    with pytest.raises(factory.ModelHubError):
        factory.build_llm(
            {
                "runtime": "api",
                "provider": "custom",
                "model_id": "m",
                "api_key": "k",
            }
        )


def test_factory_builds_local_embedder():
    embedder = factory.build_embedder(
        {"runtime": "local", "model_id": "BAAI/bge-small-en-v1.5", "device": "cpu"}
    )
    assert embedder.__class__.__name__ == "LocalEmbedder"
