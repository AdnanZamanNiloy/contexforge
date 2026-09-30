"""Request/response schemas for context budgeting.

Two things the client needs that the source list cannot tell it: what the
current selection costs, and whether the depth in force is actually doing
anything.  Both are reported together because the interesting number is the gap
between them — how much material was selected versus how much will reach the
model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.context.estimator import CONTEXT_DEPTHS

__all__ = [
    "ContextDepthName",
    "ContextEstimateRequest",
    "ContextEstimateResponse",
    "ContextSourceCost",
]

ContextDepthName = Literal["focused", "balanced", "broad"]

_DEPTH_VALUES = tuple(CONTEXT_DEPTHS)


class ContextEstimateRequest(BaseModel):
    """Body for ``POST /context/estimate``.

    An empty ``source_ids`` means the whole knowledge base, which is how a query
    with no scope is interpreted downstream — so the estimate for "nothing
    selected" is the honest estimate for what that query will cost.
    """

    source_ids: list[str] | None = Field(
        default=None,
        description="The current workspace selection. Null or empty means everything.",
    )
    depth: ContextDepthName | None = Field(
        default=None,
        description="Context depth in force. Omitted means the pipeline default.",
    )

    model_config = {"frozen": True}


class ContextSourceCost(BaseModel):
    """One source's contribution to the available material."""

    source_id: str
    title: str
    chunk_count: int = Field(ge=0)
    char_count: int = Field(ge=0)
    token_count: int = Field(ge=0)

    model_config = {"frozen": True}


class ContextEstimateResponse(BaseModel):
    """What a selection costs, and how much of it will be used."""

    source_count: int = Field(
        ge=0,
        description="Sources found in the index among those selected.",
    )
    sources: list[ContextSourceCost] = Field(default_factory=list)

    total_char_count: int = Field(ge=0, description="Size of all available material.")
    total_token_count: int = Field(ge=0, description="Tokens in all available material.")

    prompt_token_estimate: int = Field(
        ge=0,
        description=(
            "Tokens of material that would actually reach the model, given the "
            "current depth's chunk limits. The gap against ``total_token_count`` "
            "is how much of the selection is discarded before the prompt."
        ),
    )
    prompt_chunk_limit: int = Field(
        ge=1,
        description="Maximum chunks the reranker will keep at this depth.",
    )
    per_source_cap: int = Field(
        ge=1,
        description=(
            "Maximum chunks drawn from any one source at this depth. This is the "
            "limit that governs a single selected document, so it is what makes "
            "widening the depth read more of one source."
        ),
    )
    usable_fraction: float = Field(
        ge=0.0,
        le=1.0,
        description="Share of the selection that reaches the model, 0–1.",
    )

    depth: ContextDepthName = Field(description="The depth requested.")
    effective_depth: ContextDepthName = Field(
        description=(
            "The depth actually in force. Always equal to ``depth``: a depth is "
            "applied as asked, and the caps it carries are hard limits that bound "
            "the prompt rather than an approximation of it."
        ),
    )

    over_budget: bool = Field(
        default=False,
        description="True when the selection exceeds what this depth can use.",
    )
    beyond_diminishing_returns: bool = Field(
        default=False,
        description=("True when the selection is so large that raising the depth is unlikely to change the answer."),
    )

    dropped_source_ids: list[str] = Field(
        default_factory=list,
        description="Selected sources this depth would not use.",
    )
    missing_source_ids: list[str] = Field(
        default_factory=list,
        description="Selected sources absent from the index.",
    )

    model_config = {"frozen": True}
