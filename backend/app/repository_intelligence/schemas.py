"""App-repository schemas for Repository Intelligence.

These are the *frozen* response contracts shared by every view of the
Repository Intelligence page.  Field names match the shapes the frontend
already consumes (see ``frontend/src/data/repoIntelligence.js``) so the API
can replace the mock data without a frontend rewrite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


def to_camel(value: str) -> str:
    """snake_case -> camelCase alias generator for the API contract.

    The frontend consumes camelCase field names (see
    ``frontend/src/data/repoIntelligence.js``) while the analysis pipeline
    builds snake_case dicts.  ``populate_by_name=True`` lets builders keep
    passing snake_case kwargs; FastAPI serialises with the camelCase aliases.
    """
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


_CAMEL = {
    "frozen": True,
    "populate_by_name": True,
    "alias_generator": to_camel,
}

__all__ = [
    "ActivityItem",
    "AnalysisStatus",
    "AnalysisSummary",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "BlastRadius",
    "ChangeImpact",
    "CommitItem",
    "DataFlow",
    "DependencyGraph",
    "FileChurn",
    "FlowEdge",
    "FlowNode",
    "GitBranch",
    "GitHistory",
    "HealthDimension",
    "ImpactEstimated",
    "ImpactNode",
    "ModuleDetails",
    "ModuleOwner",
    "NodeKind",
    "Ownership",
    "OwnershipConcentration",
    "OwnershipContributor",
    "RankedModule",
    "RelationshipSource",
    "Repository",
    "RepositoryAnalysis",
    "RepositoryEdge",
    "RepositoryHealth",
    "RepositoryNode",
    "RiskExplanations",
    "RiskLevel",
    "SuggestedQuestions",
    "TimelineBucket",
]

RiskLevel = Literal["Low", "Medium", "High", "Critical"]
NodeKind = Literal[
    "repo",
    "area",
    "directory",
    "module",
    "file",
    "func",
    "route",
    "service",
    "core",
    "llm",
    "storage",
    "transport",
    "output",
    "input",
]
RelationshipSource = Literal["ast", "import_statement", "configuration", "convention"]

tone = Literal["good", "warn", "critical"]


class Repository(BaseModel):
    """Repository header card + overview stats."""

    owner: str
    name: str
    full_name: str
    description: str = ""
    visibility: str = "public"
    branch: str
    default_branch: str
    language: str = ""
    files: int = 0
    modules: int = 0
    commits: int = 0
    contributors: int = 0
    branches: int = 0
    pull_requests: int = 0
    issues: int = 0
    last_analyzed: datetime | None = None

    model_config = _CAMEL


class RepositoryNode(BaseModel):
    """A single node in the architecture / dependency graph.

    The frontend reads its metrics from the nested ``meta`` object
    (``meta.path``, ``meta.files``, ``meta.loc``, ``meta.deps``,
    ``meta.dependents``, ``meta.risk``, ``meta.coverage``, ``meta.changed``),
    while ``x``/``y`` are the graph layout coordinates at the top level.
    """

    id: str
    label: str
    kind: NodeKind
    x: float | None = None
    y: float | None = None
    meta: dict = Field(default_factory=dict)

    model_config = _CAMEL


class RepositoryEdge(BaseModel):
    """Directed edge between two graph nodes.

    ``relationship_source`` records *how* the edge was discovered so every
    dependency claim is auditable.  ``confidence`` encodes how strongly the
    evidence supports the edge (1.0 for hard AST evidence, lower for the
    convention / configuration based inference).
    """

    source: str
    target: str
    kind: str = "imports"
    relationship_source: RelationshipSource = "ast"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = _CAMEL


class HealthDimension(BaseModel):
    label: str
    value: float = Field(ge=0, le=100)
    tone: tone = "good"
    detail: str = ""

    model_config = _CAMEL


class RepositoryHealth(BaseModel):
    score: float = Field(ge=0, le=100)
    dimensions: list[HealthDimension]

    model_config = _CAMEL


class RankedModule(BaseModel):
    name: str
    value: float = Field(ge=0, le=100)
    reason: str = ""

    model_config = _CAMEL


class ActivityItem(BaseModel):
    id: str
    hash: str
    message: str
    time: datetime
    author: str
    kind: str = "commit"

    model_config = _CAMEL


class SuggestedQuestions(BaseModel):
    questions: list[str]

    model_config = _CAMEL


class DependencyGraph(BaseModel):
    nodes: list[RepositoryNode]
    edges: list[RepositoryEdge]

    model_config = _CAMEL


class FlowNode(BaseModel):
    """A single node in a detected execution flow.

    Everything here is derived from the actual repository: ``path`` is the
    repo-relative file, ``functions`` are functions/classes defined in that
    file, ``callers``/``callees`` are repo-relative paths linked by real
    ``imports``/``calls`` edges, and ``dependencies`` are third-party imports.
    ``latency_ms`` stays ``None`` unless a real measurement source is wired in
    — no fabricated timings are ever returned.
    """

    id: str
    label: str
    kind: NodeKind = "module"
    path: str = ""
    entry: bool = False
    functions: list[str] = Field(default_factory=list)
    callers: list[str] = Field(default_factory=list)
    callees: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    deps: int = 0
    dependents: int = 0
    latency_ms: float | None = None

    model_config = _CAMEL


class FlowEdge(BaseModel):
    """Directional edge between two flow nodes (``calls`` or ``imports``)."""

    source: str
    target: str
    kind: str = "calls"
    relationship_source: RelationshipSource = "ast"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = _CAMEL


class DataFlow(BaseModel):
    """A detected execution/data flow: a directional graph from an entry point.

    ``nodes``/``edges`` form the real flow.  ``bottlenecks`` carries only code-
    measured coupling hotspots (callers / dependents) — it never fabricates
    durations.
    """

    id: str = ""
    title: str = ""
    kind: str = "route"
    entry: str = ""
    nodes: list[FlowNode] = Field(default_factory=list)
    edges: list[FlowEdge] = Field(default_factory=list)
    bottlenecks: list[FlowNode] = Field(default_factory=list)

    model_config = _CAMEL


class GitBranch(BaseModel):
    name: str
    commits: int
    color: str = "#7aa2f7"
    active: bool = False

    model_config = _CAMEL


class TimelineBucket(BaseModel):
    week: str
    commits: int

    model_config = _CAMEL


class FileChurn(BaseModel):
    name: str
    value: int

    model_config = _CAMEL


class CommitItem(BaseModel):
    hash: str
    message: str
    author: str
    time: datetime
    files: int = 0
    inserts: int = 0
    deletes: int = 0

    model_config = _CAMEL


class GitHistory(BaseModel):
    range: str
    branches: list[GitBranch]
    timeline: list[TimelineBucket]
    file_churn: list[FileChurn]
    commits: list[CommitItem]

    model_config = _CAMEL


class OwnershipContributor(BaseModel):
    name: str
    commits: int = Field(default=0, ge=0)
    percent: float
    color: str = "#7aa2f7"

    model_config = _CAMEL


class ModuleOwner(BaseModel):
    name: str
    owner: str
    percent: float
    files: int
    contributors: list[OwnershipContributor]

    model_config = _CAMEL


class OwnershipConcentration(BaseModel):
    top1: float
    top3: float
    bus_factor: int
    risk: RiskLevel

    model_config = _CAMEL


class Ownership(BaseModel):
    contributors: list[OwnershipContributor]
    modules: list[ModuleOwner]
    concentration: OwnershipConcentration

    model_config = _CAMEL


class ImpactEstimated(BaseModel):
    affected_files: int
    affected_modules: int
    affected_apis: int
    affected_tests: int
    affected_dependencies: int

    model_config = _CAMEL


class ImpactNode(BaseModel):
    id: str
    label: str
    kind: NodeKind = "file"
    files: int = 0
    modules: int = 0
    apis: int = 0
    tests: int = 0
    deps: int = 0
    risk: RiskLevel = "Low"
    direct: bool = False
    x: float | None = None
    y: float | None = None

    model_config = _CAMEL


class BlastRadius(BaseModel):
    nodes: list[ImpactNode]
    edges: list[RepositoryEdge]

    model_config = _CAMEL


class ChangeImpact(BaseModel):
    selection: str
    estimated: ImpactEstimated
    risk: RiskLevel
    blast_radius: BlastRadius
    nodes: list[ImpactNode]

    model_config = _CAMEL


class RiskExplanations(BaseModel):
    Low: str = ""
    Medium: str = ""
    High: str = ""
    Critical: str = ""

    model_config = _CAMEL


class ModuleDetails(BaseModel):
    path: str
    type: str
    files: int = 0
    loc: int = 0
    deps: int = 0
    dependents: int = 0
    risk: RiskLevel = "Low"
    coverage: float = 0.0
    changed: str = ""
    contributors: list[str] = Field(default_factory=list)
    top_dependencies: list[str] = Field(default_factory=list)
    recent_changes: list[ActivityItem] = Field(default_factory=list)

    model_config = _CAMEL


class AnalysisStatus(BaseModel):
    id: str
    repo_url: str
    owner: str
    name: str
    branch: str
    status: Literal["queued", "running", "complete", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    commit: str | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    model_config = _CAMEL


class AnalysisSummary(BaseModel):
    id: str
    commit: str | None
    status: Literal["queued", "running", "complete", "failed"]
    repository: Repository
    generated_at: datetime
    sha256: str

    model_config = _CAMEL


class AnalyzeResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    incremental: bool = False
    reused_commit: str | None = None

    model_config = _CAMEL


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="Public GitHub repository URL (e.g. https://github.com/owner/repo).",
        examples=["https://github.com/anthropics/anthropic-sdk-python"],
    )
    branch: str | None = Field(default=None, description="Branch to analyse.")
    force: bool = Field(default=False, description="Ignore cached results.")

    model_config = _CAMEL


class RepositoryAnalysis(BaseModel):
    """Full analysis bundle returned by ``GET /repository/{id}``."""

    summary: AnalysisSummary
    repository: Repository
    health: RepositoryHealth | None = None
    architecture: DependencyGraph
    dependencies: DependencyGraph
    data_flows: dict[str, DataFlow]
    git_history: GitHistory
    ownership: Ownership
    change_impact: ChangeImpact | None = None
    risk_explanations: RiskExplanations
    ranked_modules: list[RankedModule]
    activity: list[ActivityItem]
    suggested_questions: list[str] = Field(default_factory=list)

    model_config = _CAMEL
