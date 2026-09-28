"""The service graph: what a repository is made of, and what talks to what.

A flat list of dependencies answers "what is in my requirements.txt".  It does
not answer the question a monorepo actually raises, which is where the services
are and what connects them.  This module is a port of the ``Payload`` model from
stack-analyser, which is what its README leads with.

The model is a tree of folders, each of which may stand for a technology rather
than a directory, with three kinds of relationship:

``childs``
    Nesting.  A service that lives inside another service is its child, and a
    service's technologies are its children too.
``edges``
    Dependency.  ``api -> Postgres`` because ``api``'s manifest declares a
    Postgres client, and ``web -> api`` because ``web``'s manifest names
    ``api``.  This mirrors stack-analyser's ``findEdgesInDependencies``,
    including its own caveat that matching a dependency name against a sibling
    service name can produce false positives with generic names.
``inComponent``
    Hosting.  A service deployed to Vercel belongs to the Vercel component
    rather than pointing at it, because a hosting provider contains what it
    hosts instead of being called by it.

What a node is made of follows stack-analyser's ``notAComponent`` rule: a
database or a cloud provider is something a service *connects to*, so it becomes
a node in its own right, while a framework is a property of the service and
stays on the service.  :data:`app.techstack.rules.COMPONENT_KINDS` is that split.

Node ids are derived from the folder path rather than generated, so a rescan of
an unchanged repository produces byte-identical ids and the cached graph stays
comparable between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.techstack.detectors import match_path, match_rules
from app.techstack.manifests import ManifestResult, is_service_manifest
from app.techstack.rules import COMPONENT_KINDS

__all__ = ["GraphEdge", "Payload", "build_graph", "flatten_graph"]

#: Bounds.  A repository with hundreds of services produces a graph nobody can
#: read, so the tree is cut at a size that still shows a monorepo's shape.
MAX_SERVICES = 60
MAX_CHILDREN_PER_NODE = 40
MAX_EDGES = 250

#: A dependency name that is merely a word would match half the services in a
#: monorepo, so sibling-matching needs a name specific enough to be a reference.
_GENERIC_DEPENDENCY = frozenset(
    {
        "app",
        "api",
        "backend",
        "client",
        "common",
        "core",
        "frontend",
        "lib",
        "main",
        "server",
        "shared",
        "types",
        "utils",
        "web",
    }
)


@dataclass
class GraphEdge:
    """A dependency from one payload to another."""

    target: str
    #: stack-analyser records read and write separately for data stores.  A
    #: client library cannot be read that way -- nothing in a manifest says
    #: whether a query writes -- so both are true and nothing is claimed beyond
    #: "depends on".
    read: bool = True
    write: bool = True

    def to_dict(self) -> dict:
        return {"target": self.target, "read": self.read, "write": self.write}


@dataclass
class Payload:
    """One node: a service folder, or a technology that services connect to."""

    id: str
    name: str
    #: Folder path segments.  Empty for the repository root.
    path: tuple[str, ...] = ()
    #: The technology this node stands for, or ``None`` for a plain service.
    tech: str | None = None
    #: The category of that technology, so a client can group a component node
    #: the same way it groups the technologies on a service.
    kind: str | None = None
    #: ``service``, ``component`` or ``root``.
    node_type: str = "service"
    reason: list[str] = field(default_factory=list)
    techs: list[dict] = field(default_factory=list)
    childs: list[Payload] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    #: Name of the hosting component this node sits inside, if any.
    in_component: str | None = None
    languages: list[dict] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)

    def child_names(self) -> set[str]:
        return {child.name for child in self.childs}

    def add_edge(self, target: Payload) -> None:
        if any(edge.target == target.id for edge in self.edges):
            return
        if len(self.edges) >= MAX_EDGES:
            return
        self.edges.append(GraphEdge(target=target.id))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": list(self.path),
            "tech": self.tech,
            "kind": self.kind,
            "node_type": self.node_type,
            "reason": self.reason[:4],
            "techs": self.techs,
            "childs": [child.to_dict() for child in self.childs],
            "edges": [edge.to_dict() for edge in self.edges],
            "in_component": self.in_component,
            "languages": self.languages,
            "manifests": self.manifests,
            "dependency_count": len(self.dependencies),
        }


def _node_id(path: tuple[str, ...], tech: str | None) -> str:
    """A stable id for a node.

    Derived from the folder path so that a rescan yields the same ids, with the
    technology appended for component nodes so two services depending on the
    same database still share one component.
    """
    base = "/".join(path) or "."
    return f"{base}#{tech}" if tech else base


def _service_name(path: tuple[str, ...], repository: str) -> str:
    """A readable name for the service rooted at *path*."""
    if not path:
        return repository or "root"
    return path[-1]


def _detect_for_service(
    results: list[ManifestResult],
    paths: list[str],
) -> tuple[list[dict], list[dict], list[str]]:
    """Technologies, dependencies and manifests for one service folder.

    The same rule matching the scan uses, restricted to this folder, so a
    service's technology list and the repository-wide list cannot disagree.
    """
    techs: dict[str, dict] = {}
    dependencies: list[dict] = []

    for result in results:
        for dep in result.dependencies:
            for rule in match_rules(dep.name, result.manager):
                entry = techs.setdefault(
                    rule.name,
                    {
                        "name": rule.name,
                        "key": rule.key,
                        "kind": rule.kind,
                        "version": dep.version,
                        "managers": [],
                    },
                )
                if result.manager not in entry["managers"]:
                    entry["managers"].append(result.manager)
            dependencies.append({"name": dep.name, "version": dep.version, "manager": result.manager})

    for path in paths:
        for rule in match_path(path):
            techs.setdefault(
                rule.name,
                {"name": rule.name, "key": rule.key, "kind": rule.kind, "version": None, "managers": []},
            )

    return (
        sorted(techs.values(), key=lambda row: (row["kind"], row["name"].lower())),
        dependencies,
        [result.path for result in results],
    )


def _component_for(tech: dict) -> Payload:
    return Payload(
        id=_node_id((), tech["key"]),
        name=tech["name"],
        tech=tech["key"],
        kind=tech["kind"],
        node_type="component",
        reason=["declared by a dependency" if tech["version"] else "declared by a file or dependency"],
    )


def _attach_components(
    node: Payload,
    techs: list[dict],
    existing: dict[str, Payload],
) -> list[Payload]:
    """Give a service child nodes for the technologies it connects to.

    Databases, cloud providers and the rest become nodes; frameworks and testing
    tools do not, because they are properties of the service rather than things
    it talks to.  Components are shared: two services that both declare a
    Postgres client point at one Postgres node.
    """
    created: list[Payload] = []
    for tech in techs:
        if tech["kind"] not in COMPONENT_KINDS:
            continue
        component = existing.get(tech["key"])
        is_new = component is None
        if is_new:
            component = _component_for(tech)
            existing[tech["key"]] = component
            created.append(component)
        if len(node.childs) >= MAX_CHILDREN_PER_NODE:
            break
        # A service does not nest inside its own technology.
        if any(child.id == component.id for child in node.childs):
            continue
        node.childs.append(component)
        if tech["kind"] not in ("Hosting", "Cloud"):
            node.add_edge(component)
        else:
            # Hosting contains its services rather than being called by them.
            node.in_component = component.id
    return created


def _set_hosting(node: Payload, techs: list[dict], components: dict[str, Payload]) -> None:
    """A hosting or cloud technology is the component a service lives inside.

    stack-analyser builds a component for the provider and points the service's
    ``inComponent`` at it.  A provider is not a dependency of the service it
    hosts, so no edge is drawn.
    """
    for tech in techs:
        if tech["kind"] not in ("Hosting", "Cloud"):
            continue
        component = components.get(tech["key"])
        if component is not None:
            node.in_component = component.id


def _service_edges(node: Payload, siblings: dict[str, Payload]) -> None:
    """Edges between services, from dependencies that name another service.

    This is stack-analyser's ``findEdgesInDependencies``.  It reads the
    dependency list rather than the code, so a service referenced by a generic
    name would produce a false positive; the reference is therefore only
    accepted when the name is specific enough to be an intentional reference.
    """
    for dep in node.dependencies:
        name = dep["name"]
        if name.lower() in _GENERIC_DEPENDENCY:
            continue
        # A monorepo package is usually referenced by its published name, which
        # for a scoped package is not its folder name: `@acme/billing` refers to
        # a service in `services/billing`.  The bare last segment is tried as
        # well, and only after the exact name.
        candidates = [name]
        if name.startswith("@") and "/" in name:
            candidates.append(name.rsplit("/", 1)[-1])
        target = None
        for candidate in candidates:
            found = siblings.get(candidate) or siblings.get(candidate.lower())
            if found is not None:
                target = found
                break
        if target is None or target.id == node.id:
            continue
        node.add_edge(target)


def build_graph(
    manifest_results: list[ManifestResult],
    paths: list[str],
    repository: str,
    languages_by_path: dict[str, list[dict]] | None = None,
) -> dict:
    """Build the service graph for a repository.

    A *service* is a folder holding at least one manifest, which is the same
    signal stack-analyser uses: its rules turn a folder containing a
    ``package.json`` into a payload of its own.  Folders with no manifest become
    nothing at all, so a repository of loose scripts yields a single service
    rather than a directory tree of noise.
    """
    languages_by_path = languages_by_path or {}

    # Which folders are services: only a *service* manifest opens one.  A
    # Dockerfile, a `.tf` file or a workflow describes the folder it sits in
    # rather than creating one, so `infra/main.tf` is evidence about the service
    # that owns `infra` and never becomes a service called "infra" itself.
    service_folders = {
        tuple(result.path.split("/")[:-1])
        for result in manifest_results
        if is_service_manifest(result.path)
    }

    if not service_folders:
        return {
            "services": [],
            "components": [],
            "edges": [],
            "service_count": 0,
            "service_total": 0,
            "service_truncated": False,
            "component_count": 0,
            "edge_count": 0,
            "monorepo": False,
        }

    def owner_of(segments: tuple[str, ...]) -> tuple[str, ...] | None:
        """The deepest service folder containing *segments*.

        A service owns its whole subtree, not just the files beside its manifest:
        its CI config, Dockerfile and Terraform usually live in a subdirectory
        (``apps/web/.circleci/config.yml``).  Assigning to the deepest owner
        rather than the shallowest keeps a nested service's own files with it
        instead of folding them into its parent.
        """
        for length in range(len(segments), -1, -1):
            candidate = segments[:length]
            if candidate in service_folders:
                return candidate
        return None

    by_folder: dict[tuple[str, ...], list[ManifestResult]] = {folder: [] for folder in service_folders}
    for result in manifest_results:
        # A Terraform provider or a workflow's actions are still technologies the
        # owning service uses, so every manifest is kept, not just the service's.
        owner = owner_of(tuple(result.path.split("/")[:-1]))
        if owner is not None:
            by_folder[owner].append(result)

    paths_by_folder: dict[tuple[str, ...], list[str]] = {folder: [] for folder in service_folders}
    for path in paths:
        owner = owner_of(tuple(path.split("/")[:-1]))
        if owner is not None:
            paths_by_folder[owner].append(path)

    # Shallow folders first, so a service is built before anything nested in it
    # and the deepest, most numerous folders are the ones dropped when over the
    # cap -- a monorepo's leaves are less informative than its roots.
    ordered = sorted(by_folder, key=lambda folder: (len(folder), folder))
    service_total = len(ordered)
    if len(ordered) > MAX_SERVICES:
        ordered = ordered[:MAX_SERVICES]

    components: dict[str, Payload] = {}
    services: dict[tuple[str, ...], Payload] = {}
    root = Payload(id=_node_id((), None), name=repository or "root", path=(), node_type="root")

    for folder in ordered:
        results = by_folder[folder]
        folder_paths = paths_by_folder.get(folder, [])
        techs, dependencies, manifests = _detect_for_service(results, folder_paths)

        node = Payload(
            id=_node_id(folder, None),
            name=_service_name(folder, repository),
            path=folder,
            node_type="service",
            techs=techs,
            dependencies=dependencies,
            manifests=sorted(manifests),
        )
        if languages_by_path:
            counts: dict[tuple[str, str], int] = {}
            for path in folder_paths:
                for row in languages_by_path.get(path, []):
                    key = (row["name"], row.get("kind", "programming"))
                    counts[key] = counts.get(key, 0) + row.get("files", 0)
            node.languages = [
                {"name": name, "kind": kind, "files": files}
                for (name, kind), files in sorted(counts.items(), key=lambda kv: -kv[1])[:6]
            ]

        # A component is the child of the first service that declared it; later
        # services reach it by edge, which is how stack-analyser keeps one node
        # per technology while several services point at it.
        _attach_components(node, techs, components)
        _set_hosting(node, techs, components)

        services[folder] = node

    # Nest every service under the longest service folder that contains it.  The
    # repository's own manifest makes the root a service, so the tree is rooted
    # there when it exists; a repository whose only manifest is nested has no
    # root service, and then a synthetic root holds the top-level ones.
    tree_root = root
    for folder, node in services.items():
        if folder == ():
            tree_root = node
            break
    for folder, node in services.items():
        if folder == ():
            continue
        parent = tree_root
        for length in range(len(folder) - 1, 0, -1):
            candidate = folder[:length]
            if candidate in services:
                parent = services[candidate]
                break
        parent.childs.append(node)

    # Sibling service references become edges, then deduped.
    top_level = {node.name: node for node in root.childs if node.node_type == "service"}
    for node in services.values():
        siblings = {**top_level, **{n.name: n for n in node.childs if n.node_type == "service"}}
        _service_edges(node, siblings)

    all_components = sorted(components.values(), key=lambda p: p.name.lower())
    service_count = len(services)

    return {
        "services": [node.to_dict() for node in services.values()],
        "components": [node.to_dict() for node in all_components],
        "edges": _edge_list(services, components),
        "service_count": service_count,
        # The real number of manifest folders, which is higher than
        # `service_count` when the tree was capped.  Reporting the capped figure
        # as if it were the whole repository would understate a large monorepo.
        "service_total": service_total,
        "service_truncated": service_total > service_count,
        "component_count": len(all_components),
        "edge_count": sum(len(node.edges) for node in services.values()),
        # A monorepo is a repository with more than one service folder, or one
        # nested below another.  It is worth saying so, because a single-service
        # graph is a fact about the repository rather than a finding.
        "monorepo": service_total > 1,
    }


def _edge_list(services: dict[tuple[str, ...], Payload], components: dict[str, Payload]) -> list[dict]:
    """Every edge as ``{from, to}`` pairs, for clients that draw their own graph."""
    known = {node.id for node in services.values()} | {node.id for node in components.values()}
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    for node in services.values():
        for edge in node.edges:
            if edge.target not in known or (node.id, edge.target) in seen:
                continue
            seen.add((node.id, edge.target))
            rows.append({"from": node.id, "to": edge.target, "read": edge.read, "write": edge.write})
    return rows


def flatten_graph(graph: dict) -> list[dict]:
    """Every node in the tree, depth first.

    stack-analyser flattens before it renders, so a client can lay the graph out
    without walking the nesting itself.
    """
    rows: list[dict] = []

    def walk(node: dict, depth: int) -> None:
        rows.append({**node, "depth": depth})
        for child in node.get("childs") or ():
            walk(child, depth + 1)

    for node in graph.get("services") or ():
        walk(node, 0)
    return rows
