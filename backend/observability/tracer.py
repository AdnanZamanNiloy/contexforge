from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from app.config.settings import settings


logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


try:
    from langfuse.decorators import observe as _observe
except Exception:  # pragma: no cover - optional dependency
    _observe = None


def observe(name: str | None = None) -> Callable[[F], F]:
    if _observe is None:
        def decorator(func: F) -> F:
            return func

        return decorator
    return _observe(name=name)


def configure_logging() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
