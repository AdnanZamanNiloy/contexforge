from __future__ import annotations

import warnings

warnings.warn(
    "pipeline.py and IngestionPipeline are deprecated. "
    "Use Orchestrator.ingest() instead.",
    DeprecationWarning,
    stacklevel=2,
)

from core.orchestrator import Orchestrator as IngestionPipeline  # noqa: E402, F401

__all__ = ["IngestionPipeline"]