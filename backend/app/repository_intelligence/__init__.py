"""app.repository_intelligence — Repository Intelligence subsystem.

Layered as:  route -> service -> analyzer -> storage.

Every module here is deliberately *isolated* from ``core.orchestrator``:
Repository Intelligence has its own pipeline (clone, git, AST graph, risk)
and must not add fan-out to the already large orchestrator god-object.
"""

from __future__ import annotations

__all__: list[str] = []
