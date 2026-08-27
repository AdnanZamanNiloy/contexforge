from __future__ import annotations

import warnings

from core.orchestrator import Orchestrator as IngestionPipeline

warnings.warn(
    "pipeline.py and IngestionPipeline are deprecated. Use Orchestrator.ingest() instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["IngestionPipeline"]
