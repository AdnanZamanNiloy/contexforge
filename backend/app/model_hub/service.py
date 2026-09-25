"""Application service for the Model Hub.

Owns the business rules that must not live in the route layer:

- API keys never leave this layer (all responses go through ``_public_model``).
- An LLM model can never be a member of an embedding chain, and vice versa.
- Embedding-chain members must share a vector dimension with the chain's
  primary model, so the existing FAISS/RAG index is never silently fed
  incompatible vectors.
- ``test`` actually performs a live call and auto-detects embedding dimension.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.model_hub import factory
from app.model_hub.schemas import (
    ChainCreate,
    ChainUpdate,
    ModelCreate,
    ModelUpdate,
)
from app.model_hub.storage import ModelHubStore

__all__ = ["ModelHubError", "ModelHubService"]

logger = logging.getLogger(__name__)


class ModelHubError(ValueError):
    """A user-facing validation or configuration error."""


# Columns that may be persisted from a create/update payload.
_MODEL_FIELDS = (
    "name",
    "model_type",
    "runtime",
    "provider",
    "model_id",
    "base_url",
    "api_key",
    "dimension",
    "local_backend",
    "device",
    "status",
    "status_detail",
)


class ModelHubService:
    def __init__(self, store: ModelHubStore) -> None:
        self._store = store

    # ------------------------------------------------------------------ #
    # Models
    # ------------------------------------------------------------------ #

    async def list_models(self) -> list[dict[str, Any]]:
        rows = await self._store.list_models()
        return [self._public_model(r) for r in rows]

    async def get_model(self, model_id: str) -> dict[str, Any]:
        row = await self._store.get_model(model_id)
        if row is None:
            raise ModelHubError(f"Model '{model_id}' not found.")
        return self._public_model(row)

    async def create_model(self, payload: ModelCreate) -> dict[str, Any]:
        fields = payload.model_dump()
        # A registered API key is stripped before any read-back happens.
        fields["api_key"] = fields.get("api_key") or None
        row = await self._store.create_model(fields)
        return self._public_model(row)

    async def update_model(self, model_id: str, payload: ModelUpdate) -> dict[str, Any]:
        existing = await self._store.get_model(model_id)
        if existing is None:
            raise ModelHubError(f"Model '{model_id}' not found.")

        changes: dict[str, Any] = {}
        for key, value in payload.model_dump(exclude_unset=True).items():
            if key not in _MODEL_FIELDS:
                continue
            if key == "api_key":
                if value is None:
                    continue  # leave the stored key untouched
                changes[key] = value or None  # "" clears, non-empty replaces
                continue
            if key == "base_url" and value == "":
                changes[key] = None
                continue
            changes[key] = value

        if "model_id" in changes or "provider" in changes or "runtime" in changes:
            # Any change that affects how the model is built invalidates its
            # previous test result.
            changes.setdefault("status", "untested")
            changes.setdefault("status_detail", None)

        row = await self._store.update_model(model_id, changes)
        if row is None:
            raise ModelHubError(f"Model '{model_id}' not found.")
        return self._public_model(row)

    async def delete_model(self, model_id: str) -> None:
        removed = await self._store.delete_model(model_id)
        if not removed:
            raise ModelHubError(f"Model '{model_id}' not found.")

    # ------------------------------------------------------------------ #
    # Testing (live calls)
    # ------------------------------------------------------------------ #

    async def test_model(self, model_id: str) -> dict[str, Any]:
        """Perform a real call to *model_id* and record its status.

        For LLMs: sends a tiny prompt and returns a short response preview.
        For embeddings: embeds a probe string and auto-detects the vector
        dimension, persisting it on the model.
        """
        row = await self._store.get_model(model_id)
        if row is None:
            raise ModelHubError(f"Model '{model_id}' not found.")

        started = time.perf_counter()
        try:
            if row["model_type"] == "embedding":
                result = await self._test_embedding(row)
            else:
                result = await self._test_llm(row)
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000
            logger.warning("model test failed: id=%s error=%s", model_id, exc)
            await self._store.update_model(
                model_id,
                {"status": "error", "status_detail": str(exc)[:500]},
            )
            return {
                "ok": False,
                "latency_ms": round(latency, 2),
                "detail": str(exc),
                "model_id": model_id,
            }

        latency = (time.perf_counter() - started) * 1000
        updates: dict[str, Any] = {"status": "ready", "status_detail": None}
        if result.get("dimension"):
            updates["dimension"] = result["dimension"]
        await self._store.update_model(model_id, updates)
        result.update({"ok": True, "latency_ms": round(latency, 2), "model_id": model_id})
        return result

    async def _test_llm(self, row: dict[str, Any]) -> dict[str, Any]:
        llm = factory.build_llm(row)
        try:
            text = await llm.generate("Reply with the single word: ready")
        finally:
            close = getattr(llm, "aclose", None)
            if close is not None:
                await close()
        return {"response": (text or "").strip()[:200]}

    async def _test_embedding(self, row: dict[str, Any]) -> dict[str, Any]:
        embedder = factory.build_embedder(row)
        try:
            vectors = await embedder.embed_texts(["dimension probe"], input_type="query")
        finally:
            close = getattr(embedder, "aclose", None)
            if close is not None:
                await close()
        if not vectors or not vectors[0]:
            raise RuntimeError("Embedding model returned no vector.")
        return {"dimension": len(vectors[0])}

    # ------------------------------------------------------------------ #
    # Chains
    # ------------------------------------------------------------------ #

    async def list_chains(self) -> list[dict[str, Any]]:
        return await self._store.list_chains()

    async def get_chain(self, chain_id: str) -> dict[str, Any]:
        row = await self._store.get_chain(chain_id)
        if row is None:
            raise ModelHubError(f"Chain '{chain_id}' not found.")
        return row

    async def create_chain(self, payload: ChainCreate) -> dict[str, Any]:
        await self._validate_chain_members(payload.chain_type, payload.model_ids)
        fields = payload.model_dump()
        if not fields["model_ids"]:
            raise ModelHubError("A chain requires at least one model.")
        return await self._store.create_chain(fields)

    async def update_chain(self, chain_id: str, payload: ChainUpdate) -> dict[str, Any]:
        existing = await self._store.get_chain(chain_id)
        if existing is None:
            raise ModelHubError(f"Chain '{chain_id}' not found.")
        changes = payload.model_dump(exclude_unset=True)
        if "model_ids" in changes and changes["model_ids"] is not None:
            if not changes["model_ids"]:
                raise ModelHubError("A chain requires at least one model.")
            await self._validate_chain_members(existing["chain_type"], changes["model_ids"])
        row = await self._store.update_chain(chain_id, changes)
        if row is None:
            raise ModelHubError(f"Chain '{chain_id}' not found.")
        return row

    async def delete_chain(self, chain_id: str) -> None:
        removed = await self._store.delete_chain(chain_id)
        if not removed:
            raise ModelHubError(f"Chain '{chain_id}' not found.")

    async def test_chain(self, chain_id: str) -> dict[str, Any]:
        """Test each member of a chain in order and report per-model results."""
        chain = await self.get_chain(chain_id)
        results: list[dict[str, Any]] = []
        first_success: dict[str, Any] | None = None
        for member_id in chain["model_ids"]:
            result = await self.test_model(member_id)
            result["model_id"] = member_id
            results.append(result)
            if result["ok"] and first_success is None:
                first_success = result
                break
        return {
            "ok": first_success is not None,
            "chain_id": chain_id,
            "results": results,
            "used_model_id": first_success.get("model_id") if first_success else None,
        }

    async def _validate_chain_members(self, chain_type: str, model_ids: list[str]) -> None:
        """Enforce same-type membership and embedding-dimension compatibility."""
        dims: list[tuple[str, int | None]] = []
        for model_id in model_ids:
            row = await self._store.get_model(model_id)
            if row is None:
                raise ModelHubError(f"Model '{model_id}' not found.")
            if row["model_type"] != chain_type:
                raise ModelHubError(
                    f"Model '{row['name']}' is a {row['model_type']} model and cannot "
                    f"be used in a {chain_type} chain."
                )
            if chain_type == "embedding":
                dims.append((row["name"], row.get("dimension")))

        if chain_type == "embedding" and dims:
            # The existing FAISS index is dimension-locked.  Fallback models
            # must produce the same vector size as the primary, otherwise a
            # fallback would corrupt retrieval silently — reject instead.
            known = [d for _, d in dims if d]
            if known and len(set(known)) > 1:
                detail = ", ".join(f"{name}={d or 'unknown'}" for name, d in dims)
                raise ModelHubError(
                    "Embedding chain members have incompatible vector dimensions "
                    f"({detail}). Test each embedding model to detect its dimension, "
                    "then only chain models with the same dimension."
                )

    # ------------------------------------------------------------------ #
    # Serving configuration
    # ------------------------------------------------------------------ #

    async def get_serving(self) -> dict[str, Any]:
        cfg = await self._store.get_serving()
        return {
            "llm_mode": cfg["llm"]["mode"],
            "llm_target": cfg["llm"]["target"],
            "embedding_mode": cfg["embedding"]["mode"],
            "embedding_target": cfg["embedding"]["target"],
        }

    async def update_serving(self, tier: str, mode: str, target: str | None) -> dict[str, Any]:
        if mode == "disabled":
            await self._store.set_serving(tier, "disabled", None)
        elif mode == "single":
            if not target:
                raise ModelHubError("Select a model to serve.")
            row = await self._store.get_model(target)
            if row is None:
                raise ModelHubError(f"Model '{target}' not found.")
            if row["model_type"] != tier:
                raise ModelHubError(
                    f"Model '{row['name']}' is a {row['model_type']} model and cannot "
                    f"be served as the {tier} model."
                )
            await self._store.set_serving(tier, "single", target)
        elif mode == "chain":
            if not target:
                raise ModelHubError("Select a chain to serve.")
            chain = await self._store.get_chain(target)
            if chain is None:
                raise ModelHubError(f"Chain '{target}' not found.")
            if chain["chain_type"] != tier:
                raise ModelHubError(
                    f"Chain '{chain['name']}' is a {chain['chain_type']} chain and "
                    f"cannot be served as the {tier} chain."
                )
            await self._store.set_serving(tier, "chain", target)
        else:
            raise ModelHubError(f"Unknown serving mode: {mode}")
        return await self.get_serving()

    # ------------------------------------------------------------------ #
    # Runtime resolution (used by dependencies.py)
    # ------------------------------------------------------------------ #

    async def resolve_llm_configs(self) -> list[dict[str, Any]] | None:
        """Return the ordered LLM configs the active serving tier selects.

        ``None`` means "no Model Hub override — use the env-driven chain".
        """
        return await self._resolve("llm")

    async def resolve_embedding_config(self) -> dict[str, Any] | None:
        cfg = await self._resolve("embedding")
        if not cfg:
            return None
        return cfg[0]

    async def _resolve(self, tier: str) -> list[dict[str, Any]] | None:
        cfg = await self._store.get_serving()
        entry = cfg.get(tier, {"mode": "disabled", "target": None})
        mode = entry.get("mode")
        target = entry.get("target")
        if mode == "disabled" or not target:
            return None
        if mode == "single":
            row = await self._store.get_model(target)
            return [row] if row else None
        if mode == "chain":
            chain = await self._store.get_chain(target)
            if not chain or not chain.get("enabled"):
                return None
            configs = []
            for member_id in chain["model_ids"]:
                row = await self._store.get_model(member_id)
                if row:
                    configs.append(row)
            return configs or None
        return None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _public_model(row: dict[str, Any]) -> dict[str, Any]:
        """Strip the API key and expose only a ``has_api_key`` flag."""
        return {
            "id": row["id"],
            "name": row["name"],
            "model_type": row["model_type"],
            "runtime": row["runtime"],
            "provider": row.get("provider") or "custom",
            "model_id": row["model_id"],
            "base_url": row.get("base_url"),
            "dimension": row.get("dimension"),
            "local_backend": row.get("local_backend"),
            "device": row.get("device"),
            "has_api_key": bool(row.get("api_key")),
            "status": row.get("status") or "untested",
            "status_detail": row.get("status_detail"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
