"""Request and response schemas for the Model Hub endpoints.

The Model Hub lets users register LLM and embedding models (API or local),
group them into fallback chains, and choose which single model / chain the
running ContextForge pipeline actually uses.

Security note: ``api_key`` is accepted on writes but is **never** part of any
response model.  Responses expose only ``has_api_key`` (a boolean), so a key
can never leak through a GET, a log line, or frontend state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "ChainCreate",
    "ChainMember",
    "ChainResponse",
    "ChainUpdate",
    "ModelCreate",
    "ModelResponse",
    "ModelUpdate",
    "ServingMode",
    "ServingResponse",
    "ServingUpdate",
    "TestResponse",
]

ModelType = Literal["llm", "embedding"]
RuntimeKind = Literal["api", "local"]
LocalBackend = Literal["sentence_transformers", "voyage", "openai"]
DeviceKind = Literal["auto", "cpu", "cuda"]

# Providers we model as OpenAI-compatible endpoints.  Anything not in this map
# and not "google" is still allowed as long as it is an "api" model with a
# custom base URL, but the factory cannot construct it and will reject it at
# test time with a clear message.
_OPENAI_COMPAT_DEFAULT_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

KNOWN_PROVIDERS = tuple(sorted({*_OPENAI_COMPAT_DEFAULT_URLS, "google", "custom"}))
KNOWN_LOCAL_BACKENDS = ("sentence_transformers",)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_base_url(value: str | None) -> str | None:
    """Validate a user-provided Base URL.

    Only ``http``/``https`` URLs with a host are accepted; anything else
    (``file://``, javascript, missing scheme, blank) is rejected so the
    server cannot be pointed at a local file or a malformed endpoint.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be a valid http(s) URL with a host")
    return value.rstrip("/")


class _ModelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    model_type: ModelType
    runtime: RuntimeKind
    provider: str = Field(default="custom", max_length=60)
    model_id: str = Field(..., min_length=1, max_length=240)
    base_url: str | None = None
    # Embedding dimension is auto-detected on test; a manual override is only
    # needed when the architecture insists on a fixed size before first use.
    dimension: int | None = Field(default=None, ge=1, le=65536)
    local_backend: LocalBackend | None = None
    device: DeviceKind | None = None

    @field_validator("name", "model_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank or whitespace-only")
        return v.strip()

    @field_validator("provider")
    @classmethod
    def _normalise_provider(cls, v: str) -> str:
        return (v or "custom").strip().lower()

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        return _validate_base_url(v)

    @model_validator(mode="after")
    def _cross_field(self) -> _ModelBase:
        if self.runtime == "local" and not self.local_backend:
            # Default to the only local backend ContextForge ships.
            self.local_backend = "sentence_transformers"
        if self.runtime == "local":
            # A local model has no API base URL or key.
            self.base_url = None
        return self


class ModelCreate(_ModelBase):
    api_key: str | None = Field(default=None, max_length=4096)


class ModelUpdate(BaseModel):
    """Partial update.  Only provided fields are changed.

    ``api_key`` semantics: omitted / ``None`` leaves the stored key untouched;
    an empty string clears it; any non-empty value replaces it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, max_length=60)
    model_id: str | None = Field(default=None, min_length=1, max_length=240)
    base_url: str | None = None
    api_key: str | None = Field(default=None, max_length=4096)
    dimension: int | None = Field(default=None, ge=1, le=65536)
    local_backend: LocalBackend | None = None
    device: DeviceKind | None = None

    @field_validator("name", "model_id")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank or whitespace-only")
        return v.strip() if v is not None else None

    @field_validator("provider")
    @classmethod
    def _normalise_provider(cls, v: str | None) -> str | None:
        return v.strip().lower() if v is not None else None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        # An explicit empty string clears the URL; None means "leave as-is".
        if v is None:
            return None
        if not v.strip():
            return ""
        return _validate_base_url(v)


class ModelResponse(BaseModel):
    """A configured model with the API key redacted."""

    id: str
    name: str
    model_type: ModelType
    runtime: RuntimeKind
    provider: str
    model_id: str
    base_url: str | None = None
    dimension: int | None = None
    local_backend: LocalBackend | None = None
    device: DeviceKind | None = None
    has_api_key: bool = False
    status: Literal["ready", "error", "untested"] = "untested"
    status_detail: str | None = None
    created_at: str
    updated_at: str

    model_config = {"frozen": True}


class TestResponse(BaseModel):
    """Result of testing a single model.

    ``latency_ms`` is the round-trip time of the real network call.  ``response``
    is a short preview of the generated text for LLMs; ``dimension`` is the
    detected vector size for embeddings (auto-detected, not user-entered).
    """

    ok: bool
    latency_ms: float
    response: str | None = None
    dimension: int | None = None
    detail: str | None = None
    model_id: str | None = None

    model_config = {"frozen": True}


class ChainMember(BaseModel):
    model_id: str = Field(..., min_length=1)


class ChainCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    chain_type: ModelType
    model_ids: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank or whitespace-only")
        return v.strip()


class ChainUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    model_ids: list[str] | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank or whitespace-only")
        return v.strip() if v is not None else None


class ChainResponse(BaseModel):
    id: str
    name: str
    chain_type: ModelType
    model_ids: list[str]
    enabled: bool
    created_at: str
    updated_at: str

    model_config = {"frozen": True}


ServingMode = Literal["single", "chain", "disabled"]


class ServingResponse(BaseModel):
    """Current serving configuration for LLM and embedding tiers."""

    llm_mode: ServingMode
    llm_target: str | None = None
    embedding_mode: ServingMode
    embedding_target: str | None = None

    model_config = {"frozen": True}


class ServingUpdate(BaseModel):
    tier: Literal["llm", "embedding"]
    mode: ServingMode
    target: str | None = None

    model_config = {"frozen": True}
