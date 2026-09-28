"""Architecture graph validation and Mermaid compilation.

Ported in reduced form from GitDiagram's ``src/server/generate/graph.ts``: the
path-validation rules, the total text escaping and the deterministic AST ->
Mermaid compiler are kept because they are the correctness boundary of the whole
feature, while its video/quotas/storage layers are not.

The graph itself is model output, so nothing here trusts it.  Every node path is
checked against the set of paths that actually exist in the ingested repository,
and every piece of text is escaped before it can reach a Mermaid label.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

__all__ = [
    "ArchitectureGraph",
    "GraphEdge",
    "GraphGroup",
    "GraphIssue",
    "GraphNode",
    "ValidationResult",
    "compile_mermaid",
    "parse_graph",
    "strip_unknown_paths",
    "validate_graph",
]

# Bounds.  Deliberately small: the diagram is meant to be readable at a glance
# and the whole generation has a 60s budget on modest hardware.
MAX_NODES = 16
MAX_EDGES = 24
MAX_GROUPS = 6
MAX_LABEL_CHARS = 48

# A node id is interpolated straight into Mermaid as an identifier, so it is
# restricted to a conservative charset rather than merely escaped.
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")

_ALLOWED_SHAPES = {"box", "database", "circle", "hexagon", "queue", "document"}


@dataclass(frozen=True)
class GraphGroup:
    id: str
    label: str


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    path: str | None = None
    group: str | None = None
    shape: str = "box"


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    label: str | None = None
    dashed: bool = False


@dataclass
class ArchitectureGraph:
    groups: list[GraphGroup] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(frozen=True)
class GraphIssue:
    category: str
    where: str
    message: str


@dataclass
class ValidationResult:
    issues: list[GraphIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues

    def only_bad_paths(self) -> bool:
        """True when every issue is an unresolvable node path.

        A path only drives a node's "open on GitHub" link, so such a graph is
        structurally fine and is repaired in place instead of spending a second
        model call to rebuild it.
        """
        return bool(self.issues) and all(issue.category == "missing_repository_path" for issue in self.issues)


# ---------------------------------------------------------------------------
# Parsing — model output to graph
# ---------------------------------------------------------------------------


def _clean_text(value: Any, limit: int = MAX_LABEL_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed


def _clean_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _ID_RE.match(candidate) else None


def parse_graph(raw: str) -> tuple[ArchitectureGraph | None, list[GraphIssue]]:
    """Parse the model's JSON into a graph, or report why it could not be read.

    Tolerates a fenced code block and leading prose, because models wrap JSON in
    those even when told not to.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, [GraphIssue("invalid_json", "graph", "No JSON object in the response.")]
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, [GraphIssue("invalid_json", "graph", f"Malformed JSON: {exc.msg}")]
    if not isinstance(payload, dict):
        return None, [GraphIssue("invalid_json", "graph", "Response was not a JSON object.")]

    raw_graph = payload.get("graph")
    if not isinstance(raw_graph, dict):
        return None, [GraphIssue("invalid_json", "graph", "Response has no 'graph' object.")]

    graph = ArchitectureGraph()
    for entry in (raw_graph.get("groups") or [])[:MAX_GROUPS]:
        if not isinstance(entry, dict):
            continue
        gid = _clean_id(entry.get("id"))
        if not gid:
            continue
        graph.groups.append(GraphGroup(id=gid, label=_clean_text(entry.get("label")) or gid))

    for entry in (raw_graph.get("nodes") or [])[:MAX_NODES]:
        if not isinstance(entry, dict):
            continue
        nid = _clean_id(entry.get("id"))
        if not nid:
            continue
        shape = str(entry.get("shape") or "box").strip().lower()
        graph.nodes.append(
            GraphNode(
                id=nid,
                label=_clean_text(entry.get("label")) or nid,
                path=_clean_text(entry.get("path"), limit=200) or None,
                group=_clean_id(entry.get("group")),
                shape=shape if shape in _ALLOWED_SHAPES else "box",
            )
        )

    node_ids = {n.id for n in graph.nodes}
    for entry in (raw_graph.get("edges") or [])[:MAX_EDGES]:
        if not isinstance(entry, dict):
            continue
        source = _clean_id(entry.get("from"))
        target = _clean_id(entry.get("to"))
        # An edge pointing at a node the model never emitted is dropped here
        # rather than reported: it is the single most common model slip and it
        # cannot be repaired without a second call.
        if not source or not target or source not in node_ids or target not in node_ids:
            continue
        style = str(entry.get("style") or "").strip().lower()
        graph.edges.append(
            GraphEdge(
                source=source,
                target=target,
                label=_clean_text(entry.get("label"), limit=32) or None,
                dashed=style == "dashed",
            )
        )

    if not graph.nodes:
        return None, [GraphIssue("no_nodes", "graph", "The graph contained no usable nodes.")]
    return graph, []


# ---------------------------------------------------------------------------
# Validation against the real repository tree
# ---------------------------------------------------------------------------


def validate_graph(graph: ArchitectureGraph, known_paths: set[str]) -> ValidationResult:
    """Check ids, group references and — critically — that paths really exist."""
    result = ValidationResult()
    group_ids = {g.id for g in graph.groups}
    seen_nodes: set[str] = set()
    seen_groups: set[str] = set()

    for group in graph.groups:
        if group.id in seen_groups:
            result.issues.append(GraphIssue("duplicate_group_id", f"groups.{group.id}", "Duplicate group id."))
        seen_groups.add(group.id)

    for index, node in enumerate(graph.nodes):
        if node.id in seen_nodes:
            result.issues.append(GraphIssue("duplicate_node_id", f"nodes.{index}.id", "Duplicate node id."))
        seen_nodes.add(node.id)

        if node.group and node.group not in group_ids:
            result.issues.append(
                GraphIssue("unknown_group_id", f"nodes.{index}.group", f"Unknown group '{node.group}'.")
            )

        if node.path and node.path not in known_paths:
            result.issues.append(
                GraphIssue(
                    "missing_repository_path",
                    f"nodes.{index}.path",
                    f"Path '{node.path}' does not exist in the repository.",
                )
            )

    return result


def strip_unknown_paths(graph: ArchitectureGraph, known_paths: set[str]) -> tuple[ArchitectureGraph, int]:
    """Drop unresolvable node paths, keeping an otherwise-correct graph.

    A path only powers a node's GitHub link, so losing one is cosmetic while a
    regeneration would cost another model call and risk a worse graph.
    """
    stripped = 0
    nodes = []
    for node in graph.nodes:
        if node.path and node.path not in known_paths:
            stripped += 1
            nodes.append(GraphNode(id=node.id, label=node.label, path=None, group=node.group, shape=node.shape))
        else:
            nodes.append(node)
    return ArchitectureGraph(groups=graph.groups, nodes=nodes, edges=graph.edges), stripped


# ---------------------------------------------------------------------------
# Mermaid compilation
# ---------------------------------------------------------------------------


def escape_mermaid_text(value: str) -> str:
    """Escape a label so no Mermaid metacharacter can break the diagram.

    Mermaid decodes its own ``#nn;`` entity codes inside label text, so a bare
    ``#`` would reintroduce characters the other rules just removed, and a label
    opening with a backtick turns the whole quoted string into a markdown string
    that fails to lex and takes the entire diagram down.  Newlines are folded
    away for the same reason: a line break inside a quoted label ends the
    declaration, so control characters are removed here rather than trusted to
    have been stripped by the parser.
    """
    collapsed = " ".join((value or "").split())
    escaped = "".join(ch for ch in collapsed if ch.isprintable())
    for char, entity in (
        ("&", "&amp;"),
        ("#", "&#35;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("`", "&#96;"),
        ("\\", "&#92;"),
        ("|", "&#124;"),
        ("[", "&#91;"),
        ("]", "&#93;"),
        ("{", "&#123;"),
        ("}", "&#125;"),
        ("(", "&#40;"),
        (")", "&#41;"),
    ):
        escaped = escaped.replace(char, entity)
    return escaped.strip() or "Unnamed"


def _mermaid_id(node_id: str) -> str:
    return f"n_{node_id}"


def _github_url(owner: str, repo: str, branch: str, path: str) -> str:
    # The path is already a real repository path, but it still comes from model
    # output, so every segment is encoded before it is placed in a URL.
    kind = "blob" if "." in path.rsplit("/", 1)[-1] else "tree"
    encoded = "/".join(quote(segment, safe="") for segment in path.split("/"))
    return (
        f"https://github.com/{quote(owner, safe='')}/{quote(repo, safe='')}/{kind}/{quote(branch, safe='')}/{encoded}"
    )


# Dark palette so the diagram sits on ContextForge's dark canvas without a
# light-mode flash. One tone per subsystem, assigned by group order.
_TONE_CLASSES = (
    "toneBlue",
    "toneMint",
    "toneAmber",
    "toneRose",
    "toneIndigo",
    "toneTeal",
)

_TONE_DEFS = (
    "classDef toneBlue fill:#16233d,stroke:#4d7cfe,stroke-width:1.5px,color:#dce6ff",
    "classDef toneMint fill:#10302a,stroke:#2f9e6e,stroke-width:1.5px,color:#cdf5e3",
    "classDef toneAmber fill:#33280f,stroke:#c9971f,stroke-width:1.5px,color:#f7e6bd",
    "classDef toneRose fill:#341a22,stroke:#c8536c,stroke-width:1.5px,color:#f8d5dd",
    "classDef toneIndigo fill:#221d40,stroke:#7b6cf0,stroke-width:1.5px,color:#ded9ff",
    "classDef toneTeal fill:#0e2b30,stroke:#2b8f9e,stroke-width:1.5px,color:#c8eef4",
)


def _tone_for(node: GraphNode, group_index: dict[str, int]) -> str:
    index = group_index.get(node.group or "")
    if index is not None:
        return _TONE_CLASSES[index % len(_TONE_CLASSES)]
    # Grouping is optional, so a meaningful colour is a compiler guarantee: an
    # ungrouped node is still toned by what it is.
    words = f"{node.label} {node.shape}".lower()
    if node.shape == "database" or re.search(r"database|storage|cache|postgres|sqlite|redis", words):
        return "toneAmber"
    if re.search(r"queue|worker|background|scheduler|job|task", words):
        return "toneRose"
    if re.search(r"client|browser|user|frontend|view|screen", words):
        return "toneBlue"
    if re.search(r"api|server|route|request|handler|webhook", words):
        return "toneMint"
    if not node.path or re.search(r"model|inference|provider|llm|integration", words):
        return "toneIndigo"
    return "toneTeal"


def compile_mermaid(
    graph: ArchitectureGraph,
    *,
    owner: str,
    repo: str,
    branch: str,
) -> str:
    """Compile a validated graph into Mermaid flowchart source.

    Deterministic: the same graph always produces byte-identical Mermaid, so the
    cached artifact is exactly what the client renders.
    """
    lines: list[str] = ["flowchart TD"]
    group_index = {group.id: i for i, group in enumerate(graph.groups)}
    assignments: dict[str, list[str]] = {}
    placed: set[str] = set()

    def emit(node: GraphNode, indent: str = "") -> None:
        label = escape_mermaid_text(node.label)
        node_id = _mermaid_id(node.id)
        if node.shape == "database":
            declaration = f'{node_id}[("{label}")]'
        elif node.shape == "circle":
            declaration = f'{node_id}(("{label}"))'
        elif node.shape == "hexagon":
            declaration = f'{node_id}{{"{label}"}}'
        else:
            declaration = f'{node_id}["{label}"]'
        lines.append(f"{indent}{declaration}")
        tone = _tone_for(node, group_index)
        assignments.setdefault(tone, []).append(node.id)

    for group in graph.groups:
        members = [n for n in graph.nodes if n.group == group.id]
        if not members:
            continue
        lines.append("")
        lines.append(f'subgraph g_{group.id}["{escape_mermaid_text(group.label)}"]')
        for node in members:
            emit(node, "  ")
            placed.add(node.id)
        lines.append("end")

    loose = [n for n in graph.nodes if n.id not in placed]
    if loose:
        lines.append("")
        for node in loose:
            emit(node)

    if graph.edges:
        lines.append("")
        for edge in graph.edges:
            arrow = "-.->" if edge.dashed else "-->"
            source = _mermaid_id(edge.source)
            target = _mermaid_id(edge.target)
            if edge.label:
                lines.append(f'{source} {arrow}|"{escape_mermaid_text(edge.label)}"| {target}')
            else:
                lines.append(f"{source} {arrow} {target}")

    links = [n for n in graph.nodes if n.path]
    if links:
        lines.append("")
        for node in links:
            lines.append(f'click {_mermaid_id(node.id)} "{_github_url(owner, repo, branch, node.path)}"')

    lines.append("")
    lines.extend(_TONE_DEFS)
    for tone, ids in assignments.items():
        if ids:
            lines.append(f"class {','.join(_mermaid_id(i) for i in ids)} {tone}")

    return "\n".join(lines).strip()
