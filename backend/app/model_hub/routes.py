"""HTTP routes for the Model Hub.

Prefix: ``/models``.

- ``GET    /models``                    list configured models (keys redacted)
- ``POST   /models``                    create a model
- ``GET    /models/{id}``               get one model
- ``PATCH  /models/{id}``               update a model
- ``DELETE /models/{id}``               delete a model
- ``POST   /models/{id}/test``          live-test a model
- ``GET    /chains``                    list fallback chains
- ``POST   /chains``                    create a chain
- ``GET    /chains/{id}``               get one chain
- ``PATCH  /chains/{id}``               update a chain
- ``DELETE /chains/{id}``               delete a chain
- ``POST   /chains/{id}/test``          test a chain end-to-end
- ``GET    /serving``                   current serving configuration
- ``PUT    /serving``                   update a serving tier

Note: API keys are never present in any response — the service redacts them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_model_hub_service
from app.model_hub.schemas import (
    ChainCreate,
    ChainResponse,
    ChainUpdate,
    ModelCreate,
    ModelResponse,
    ModelUpdate,
    ServingResponse,
    ServingUpdate,
    TestResponse,
)
from app.model_hub.service import ModelHubError, ModelHubService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["model-hub"])


def _get_service() -> ModelHubService:
    return get_model_hub_service()


def _handle(exc: ModelHubError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _not_found(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Model '{model_id}' not found.",
    )


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


@router.get("/models", response_model=list[ModelResponse], summary="List configured models")
async def list_models(service: ModelHubService = Depends(_get_service)) -> list[ModelResponse]:
    return [ModelResponse(**m) for m in await service.list_models()]


@router.post(
    "/models",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a model",
)
async def create_model(
    payload: ModelCreate,
    service: ModelHubService = Depends(_get_service),
) -> ModelResponse:
    try:
        model = await service.create_model(payload)
    except ModelHubError as exc:
        raise _handle(exc) from exc
    return ModelResponse(**model)


@router.get("/models/{model_id}", response_model=ModelResponse, summary="Get a model")
async def get_model(
    model_id: str,
    service: ModelHubService = Depends(_get_service),
) -> ModelResponse:
    try:
        model = await service.get_model(model_id)
    except ModelHubError as exc:
        raise _not_found(model_id) from exc
    return ModelResponse(**model)


@router.patch("/models/{model_id}", response_model=ModelResponse, summary="Update a model")
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    service: ModelHubService = Depends(_get_service),
) -> ModelResponse:
    try:
        model = await service.update_model(model_id, payload)
    except ModelHubError as exc:
        raise _not_found(model_id) from exc
    return ModelResponse(**model)


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a model",
)
async def delete_model(
    model_id: str,
    service: ModelHubService = Depends(_get_service),
) -> dict:
    try:
        await service.delete_model(model_id)
    except ModelHubError as exc:
        raise _not_found(model_id) from exc
    return {"id": model_id, "deleted": True}


@router.post(
    "/models/{model_id}/test",
    response_model=TestResponse,
    summary="Test a model with a real call",
)
async def test_model(
    model_id: str,
    service: ModelHubService = Depends(_get_service),
) -> TestResponse:
    try:
        result = await service.test_model(model_id)
    except ModelHubError as exc:
        raise _not_found(model_id) from exc
    return TestResponse(**result)


# --------------------------------------------------------------------------- #
# Chains
# --------------------------------------------------------------------------- #


@router.get("/chains", response_model=list[ChainResponse], summary="List fallback chains")
async def list_chains(service: ModelHubService = Depends(_get_service)) -> list[ChainResponse]:
    return [ChainResponse(**c) for c in await service.list_chains()]


@router.post(
    "/chains",
    response_model=ChainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chain",
)
async def create_chain(
    payload: ChainCreate,
    service: ModelHubService = Depends(_get_service),
) -> ChainResponse:
    try:
        chain = await service.create_chain(payload)
    except ModelHubError as exc:
        raise _handle(exc) from exc
    return ChainResponse(**chain)


@router.get("/chains/{chain_id}", response_model=ChainResponse, summary="Get a chain")
async def get_chain(
    chain_id: str,
    service: ModelHubService = Depends(_get_service),
) -> ChainResponse:
    try:
        chain = await service.get_chain(chain_id)
    except ModelHubError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChainResponse(**chain)


@router.patch("/chains/{chain_id}", response_model=ChainResponse, summary="Update a chain")
async def update_chain(
    chain_id: str,
    payload: ChainUpdate,
    service: ModelHubService = Depends(_get_service),
) -> ChainResponse:
    try:
        chain = await service.update_chain(chain_id, payload)
    except ModelHubError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChainResponse(**chain)


@router.delete(
    "/chains/{chain_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a chain",
)
async def delete_chain(
    chain_id: str,
    service: ModelHubService = Depends(_get_service),
) -> dict:
    try:
        await service.delete_chain(chain_id)
    except ModelHubError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"id": chain_id, "deleted": True}


@router.post("/chains/{chain_id}/test", summary="Test a chain")
async def test_chain(
    chain_id: str,
    service: ModelHubService = Depends(_get_service),
) -> dict:
    try:
        return await service.test_chain(chain_id)
    except ModelHubError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Serving configuration
# --------------------------------------------------------------------------- #


@router.get("/serving", response_model=ServingResponse, summary="Get serving configuration")
async def get_serving(service: ModelHubService = Depends(_get_service)) -> ServingResponse:
    return ServingResponse(**await service.get_serving())


@router.put("/serving", response_model=ServingResponse, summary="Update serving configuration")
async def update_serving(
    payload: ServingUpdate,
    service: ModelHubService = Depends(_get_service),
) -> ServingResponse:
    try:
        result = await service.update_serving(payload.tier, payload.mode, payload.target)
    except ModelHubError as exc:
        raise _handle(exc) from exc
    # Push the new selection into the live pipeline so the change takes effect
    # immediately rather than at the next process restart.
    from app.dependencies import apply_serving_configuration

    await apply_serving_configuration()
    return ServingResponse(**result)
