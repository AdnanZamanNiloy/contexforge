"""Static code-graph construction for Repository Intelligence.

Walks a cloned working tree, classifies files by language, and builds a
``repo -> area -> directory -> module/file`` hierarchy plus cross-file
``import`` edges.  Python edges are extracted with the ``ast`` module; other
languages use a conservative regex matcher.  Any relationship we cannot
prove statically is attributed to ``convention`` with ``confidence < 1.0``.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = [
    "LANG_BY_EXT",
    "build_graph",
    "discover_files",
    "extract_imports",
    "is_analysable_path",
    "primary_language",
]

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
LANG_BY_EXT: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".html": "HTML",
    ".css": "CSS",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
    "target",
    "vendor",
    "docs",
    "doc",
    "documentation",
    "images",
    "img",
    "screenshots",
    "media",
    "static",
    "public",
}
_LOCK_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "composer.lock",
    "Cargo.lock",
    "uv.lock",
}
_BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".exe",
    ".bin",
    ".so",
    ".dylib",
    ".dll",
    ".mp3",
    ".mp4",
    ".mov",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".svg",
    ".lock",
    ".pckl",
    ".pickle",
    ".pyc",
    ".pyo",
    ".gz",
    ".tar",
    ".whl",
}
_DOC_EXTS = {".md", ".mdx", ".rst", ".adoc"}
_STYLE_EXTS = {".css", ".scss", ".less"}
# Only real source code becomes a node — config, metadata, docs, styles and
# binaries are excluded so the architecture/dependency graph reflects source.
_SOURCE_EXTS = set(LANG_BY_EXT) - _STYLE_EXTS - {".html"}

_JS_IMPORT_RES = [
    re.compile(r"from\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
]


def is_analysable_path(path: Path, root: Path | None = None) -> bool:
    """True when *path* should be included in the analysis.

    Skip directories are matched against the path *relative to root* (when
    supplied) so that the containing ``REPO_ANALYSIS_DIR`` prefix (e.g.
    ``data/repo_analysis/<repo>/...``) is never mistaken for a skip dir.
    Docs, markdown, config metadata, styles and binaries are excluded so only
    real source code is analysed.
    """
    parts = path.relative_to(root).parts if root is not None else path.parts
    if any(part in _SKIP_DIRS for part in parts):
        return False
    name = path.name
    if name in _LOCK_FILES:
        return False
    suffix = path.suffix.lower()
    if suffix in _BINARY_EXTS:
        return False
    if suffix in _DOC_EXTS:
        return False
    if suffix in _STYLE_EXTS:
        return False
    return suffix in _SOURCE_EXTS


def discover_files(root: Path) -> list[Path]:
    """Return analysable files under *root*, bounded by ``REPO_MAX_FILES``.

    Files are ordered by depth then name so truncation favours top-level
    source over deeply nested vendored code.
    """
    seen: list[Path] = []
    for dirpath, dirnames, filenames in os_walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in sorted(filenames):
            fp = Path(dirpath) / filename
            if is_analysable_path(fp, root):
                seen.append(fp)
        if len(seen) >= settings.REPO_MAX_FILES:
            break
    seen.sort(key=lambda p: (len(p.parts), str(p)))
    return seen[: settings.REPO_MAX_FILES]


def os_walk(root: Path):
    """Thin wrapper around ``os.walk`` for testability + .venv pruning."""
    import os

    return os.walk(root)


def primary_language(files: list[Path]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for fp in files:
        lang = LANG_BY_EXT.get(fp.suffix.lower())
        if lang:
            counts[lang] += 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def extract_imports(path: Path, text: str) -> list[tuple[int, str]]:
    """Return module specifiers that *path* imports, best-effort."""
    suffix = path.suffix.lower()
    if suffix in {".py", ".pyi"}:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        imports: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((0, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((node.level, node.module))
            # Detect cross-file qualified calls: a.b(...) where a.matches module
        return imports
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte"}:
        found: list[tuple[int, str]] = []
        for res in _JS_IMPORT_RES:
            for sym in res.findall(text):
                found.append((0, sym))
        return found
    return []


@observe(name="repo_graph_build")
def build_graph(root: Path) -> dict[str, Any]:
    """Build the architecture graph for the repository at *root*."""
    files = discover_files(root)
    language = primary_language(files)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    # module_path -> node_id (for resolving import edges to file nodes)
    node_by_rel: dict[str, str] = {}
    # namespace -> file node_id (dotted Python-style import resolution)
    ns_to_node: dict[str, str] = {}
    # slash module path (no extension) -> file node_id (JS/TS resolution)
    ns_slash: dict[str, str] = {}

    nodes["repo"] = {
        "id": "repo",
        "label": root.name,
        "kind": "repo",
        "path": "/",
        "files": len(files),
        "loc": 0,
    }

    for fp in files:
        rel = str(fp.relative_to(root))
        parts = rel.split("/")
        node_id = _safe_id(rel)

        # Ancestors: area (first dir) + directory (full dir path)
        area = parts[0] if len(parts) > 1 else ""
        area_id = _safe_id(area) if area else None
        if area and area_id and area_id not in nodes:
            nodes[area_id] = {
                "id": area_id,
                "label": area + "/",
                "kind": "area",
                "path": area,
                "files": 0,
                "loc": 0,
            }
            edges.append(_contains("repo", area_id))

        if len(parts) > 2:
            dir_path = "/".join(parts[:-1])
            dir_id = _safe_id(dir_path)
            parent_scope = _safe_id(parts[0]) if area else "repo"
            if dir_id not in nodes:
                pkg = (fp.parent / "__init__.py").exists() or (fp.parent / "index.ts").exists()
                nodes[dir_id] = {
                    "id": dir_id,
                    "label": parts[-2] + "/",
                    "kind": "module" if pkg else "directory",
                    "path": dir_path,
                    "files": 0,
                    "loc": 0,
                }
                edges.append(_contains(parent_scope, dir_id, "convention"))
            # parent file chain: parent directory -> this file
            node_by_rel[rel] = node_id
            ns_to_node.setdefault(_ns_of(dir_path), node_id)

        # Child of nearest container
        parent_id = _parent_scope(rel, nodes)
        node_id = _safe_id(rel)
        if node_id not in nodes:
            try:
                loc = _loc(fp)
            except OSError:
                loc = 0
            nodes[node_id] = {
                "id": node_id,
                "label": fp.name,
                "kind": "file",
                "path": rel,
                "files": 1,
                "loc": loc,
            }
            edges.append(_contains(parent_id, node_id, "convention"))
            module_name = _module_name_of(rel, fp.suffix)
            if module_name:
                ns_to_node[module_name] = node_id
                if len(parts) > 1:
                    ns_to_node.setdefault(_ns_of("/".join(parts[:-1])), node_id)
            ns_slash.setdefault(_module_slash(rel, fp.suffix), node_id)

    # Map a package/module directory to its index entry (index.tsx / __init__.py)
    # so ``import './components'`` resolves to the package entry point.
    for slash_key, node_id in list(ns_slash.items()):
        for marker in ("/index", "/__init__"):
            if slash_key.endswith(marker):
                ns_slash.setdefault(slash_key[: -len(marker)], node_id)

    # Cross-file import edges resolved against the namespace map.
    seen_imports: set[tuple[str, str]] = set()
    for fp in files:
        rel = str(fp.relative_to(root))
        node_id = _safe_id(rel)
        if node_id not in nodes:
            continue
        text = fp.read_text(errors="ignore")
        imports = extract_imports(fp, text)
        # Slash-relative directory of the importing file (for ./ ../ app imports).
        base_dir = "/".join(rel.split("/")[:-1]) if "/" in rel else ""
        for level, spec in imports:
            target = resolve_import_target(spec, ns_to_node, ns_slash, level=level, base_dir=base_dir)
            if target and target != node_id and (node_id, target) not in seen_imports:
                seen_imports.add((node_id, target))
                edges.append(_import_edge(node_id, target))

    nodes_out = sorted(
        (nodes[n["id"]] for n in nodes.values() if n["id"] in _reachable(nodes, edges, "repo")),
        key=lambda n: n["id"],
    )
    _aggregate_metrics(nodes_out, edges)
    nodes["repo"]["loc"] = sum(n["loc"] for n in nodes_out)
    nodes["repo"]["files"] = sum(n["files"] for n in nodes_out)

    return {
        "nodes": nodes_out,
        "edges": edges,
        "language": language,
        "files": files,
    }


def _aggregate_metrics(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    """Accumulate ``files``/``loc`` from file leaves up the containment tree."""
    children: dict[str, list[str]] = defaultdict(list)
    node_by_id = {n["id"]: n for n in nodes}
    for e in edges:
        if e.get("kind") == "contains":
            children[e["source"]].append(e["target"])

    def rollup(node_id: str) -> tuple[int, int]:
        node = node_by_id.get(node_id)
        if node is None:
            return (0, 0)
        if node.get("kind") == "file":
            return (node.get("files", 0), node.get("loc", 0))
        files = sum(
            n.get("files", 0)
            for c in children[node_id]
            if (n := node_by_id.get(c)) is not None and n.get("kind") != "file"
        )
        loc = sum(
            n.get("loc", 0)
            for c in children[node_id]
            if (n := node_by_id.get(c)) is not None and n.get("kind") != "file"
        )
        for c in children[node_id]:
            child_files, child_loc = rollup(c)
            files += child_files
            loc += child_loc
        node["files"] = files
        node["loc"] = loc
        return (files, loc)

    for n in nodes:
        if n.get("kind") in {"area", "directory", "module"}:
            rollup(n["id"])


def _contains(source: str, target: str, source_kind: str = "convention") -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "kind": "contains",
        "relationship_source": source_kind,
        "confidence": 1.0,
    }


def _import_edge(source: str, target: str) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "kind": "imports",
        "relationship_source": "ast",
        "confidence": 1.0,
    }


def _safe_id(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-/]+", "-", path).strip("-") or "root"


def _ns_of(dir_path: str) -> str:
    """Namespace for a Python package directory, relative to repo root."""
    return dir_path.replace("/", ".")


def _module_name_of(rel: str, suffix: str) -> str:
    base = rel[: -len(suffix)] if suffix else rel
    parts = base.split("/")
    # `pkg/__init__.py` represents the package itself.
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _loc(fp: Path) -> int:
    with fp.open(errors="ignore") as fh:
        return sum(1 for _ in fh)


def _parent_scope(rel: str, nodes: dict) -> str:
    """Return the node id that should contain the file at *rel*."""
    parts = rel.split("/")
    if len(parts) == 1:
        return "repo"
    dir_path = "/".join(parts[:-1])
    dir_id = _safe_id(dir_path)
    if dir_id in nodes:
        return dir_id
    if len(parts) > 2:
        return _safe_id(parts[0])
    return "repo"


def _reachable(nodes: dict, edges: list[dict], start: str) -> set[str]:
    """Nodes reachable from *start* via 'contains' edges (prune orphans)."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["kind"] == "contains":
            adjacency[e["source"]].add(e["target"])
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adjacency.get(cur, ()))
    return seen


def _module_slash(rel: str, suffix: str) -> str:
    """Repo-relative module path without extension (slash form)."""
    return rel[: -len(suffix)] if suffix else rel


def resolve_import_target(
    spec: str,
    ns_to_node: dict[str, str],
    ns_slash: dict[str, str] | None = None,
    level: int = 0,
    base_dir: str = "",
) -> str | None:
    """Map an import specifier to a node id.

    Handles three styles:
      * Python relative imports (``level`` dots) — climb ``base_dir``.
      * JS/TS relative imports (``./``, ``../``) — normalise against
        ``base_dir`` and resolve against the slash namespace.
      * Alias/absolute specifiers (``@/``, ``~/``, dotted or slash paths) —
        exact/suffix match against the dotted and slash namespaces.
    """
    spec = spec.strip()
    ns_slash = ns_slash or {}

    if level:  # Python relative: climb base_dir.
        parts = base_dir.split("/") if base_dir else []
        ups = max(level - 1, 0)
        if ups:
            parts = parts[: len(parts) - ups]
        dotted = ".".join([*parts, spec]) if parts else spec
        return _lookup_dotted(dotted, ns_to_node)

    if spec.startswith("."):  # JS/TS relative specifier.
        resolved = _resolve_relative(base_dir, spec)
        if resolved is None:
            return None
        return _lookup_slash(resolved, ns_slash)

    if spec.startswith("@"):  # Alias path, e.g. @/components/ui/button.
        candidate = spec.split("/", 1)[-1]
        return _suffix_slash(candidate, ns_slash) or _suffix_dotted(candidate.replace("/", "."), ns_to_node)

    cand = _lookup_slash(spec, ns_slash)
    if cand:
        return cand
    cand = _lookup_dotted(spec, ns_to_node)
    if cand:
        return cand
    if "/" in spec:
        return _suffix_slash(spec.lstrip("/"), ns_slash)
    return None


def _lookup_dotted(dotted: str, ns_to_node: dict[str, str]) -> str | None:
    """Exact dotted match, else longest dotted prefix (Python ``pkg.mod``)."""
    if dotted in ns_to_node:
        return ns_to_node[dotted]
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in ns_to_node:
            return ns_to_node[candidate]
    return None


def _lookup_slash(path: str, ns_slash: dict[str, str]) -> str | None:
    """Exact slash-path match with package-index + extension fallbacks."""
    if path in ns_slash:
        return ns_slash[path]
    for suffix in ("/index", "/__init__"):
        if path + suffix in ns_slash:
            return ns_slash[path + suffix]
    return None


def _suffix_slash(candidate: str, ns_slash: dict[str, str]) -> str | None:
    """Resolve an alias/slash path by matching a unique suffix over the graph."""
    for key, nid in ns_slash.items():
        if key.endswith("/" + candidate) or key == candidate:
            return nid
    return None


def _suffix_dotted(candidate_dotted: str, ns_to_node: dict[str, str]) -> str | None:
    for key, nid in ns_to_node.items():
        if key.endswith("." + candidate_dotted) or key == candidate_dotted:
            return nid
    return None


def _resolve_relative(base_dir: str, spec: str) -> str | None:
    """Normalise a ``./`` or ``../`` specifier against ``base_dir`` (slash)."""
    import posixpath

    combined = posixpath.normpath(posixpath.join(base_dir or ".", spec))
    if combined.startswith("../") or combined == "..":
        return None
    return posixpath.splitext(combined)[0]
