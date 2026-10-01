"""Check the README's curated API list against the live OpenAPI spec.

The README documents a short, curated set of endpoints rather than all 59
operations, because an exhaustive hand-written list is exactly the kind of thing
that rots: the previous list had drifted to 24 of 59 operations, included an
endpoint that did not exist (`DELETE /ingest/clear`), and used `{id}` where the
API takes `{model_id}`, `{chain_id}` and `{key}`.

FastAPI already serves a complete, always-correct reference at ``/docs`` and
``/openapi.json``, so the README's job is only to be *right* about the handful of
calls it does list. This script is what keeps it right: it fails when a
documented route is missing, when a documented method does not exist on a real
path, or when a documented path parameter does not match the spec.

Runs against the app in-process, so it needs no running server. It never touches
``backend/data/``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
README = REPO_ROOT / "README.md"

# The curated section of the README, between its heading and the next one.
_SECTION_START = "## API Reference"
_SECTION_END = "## Development"

# `METHOD /path    optional description`, inside a fenced block.
_ROW = re.compile(r"^(GET|POST|PATCH|PUT|DELETE)\s+(/\S*)", re.MULTILINE)


def documented_rows(text: str) -> list[tuple[str, str]]:
    """Return the (method, path) pairs the README's API section claims exist."""
    if _SECTION_START not in text:
        raise SystemExit(f"{README}: no '{_SECTION_START}' section found")
    start = text.index(_SECTION_START)
    end = text.find(_SECTION_END, start)
    section = text[start:] if end == -1 else text[start:end]

    rows: list[tuple[str, str]] = []
    for method, path in _ROW.findall(section):
        path = path.rstrip(".,;)")
        rows.append((method.upper(), path))
    return rows


def spec_params(path_item: dict) -> set[str]:
    """Parameter names a path template declares, e.g. {"source_id"}."""
    names: set[str] = set()
    for param in path_item.get("parameters", []) or []:
        if param.get("in") == "path" and "name" in param:
            names.add(param["name"])
    return names


def template_names(path: str) -> set[str]:
    return set(re.findall(r"\{([^}]+)\}", path))


def _segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


def suggest(documented: str, known: str) -> bool:
    """True when *known* could be the same route as *documented*.

    Segment-by-segment, with any ``{param}`` matching any ``{param}``. Matching on
    parameter *names* instead would flag every documented route, since the old
    list used a generic ``{id}`` where the API declares specific names.
    """
    a, b = _segments(documented), _segments(known)
    if len(a) != len(b):
        return False
    return all((x.startswith("{") and y.startswith("{")) or x == y for x, y in zip(a, b, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readme",
        default=str(README),
        help="README to check (defaults to the repository README).",
    )
    args = parser.parse_args()

    readme = Path(args.readme).resolve()
    rows = documented_rows(readme.read_text())

    # The script only needs the schema, not a running service, and the app no
    # longer demands a credential to import.
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.main import app

    spec = app.openapi()["paths"]

    problems: list[str] = []
    for method, path in rows:
        if path not in spec:
            close = [p for p in spec if suggest(path, p)]
            hint = f" (did you mean {', '.join(sorted(close))}?)" if close else ""
            problems.append(f"documented but does not exist: {method} {path}{hint}")
            continue

        operations = spec[path]
        if method.lower() not in operations:
            available = ", ".join(sorted(m.upper() for m in operations)) or "none"
            problems.append(f"{method} {path} does not exist; on that path: {available}")

        # Path-level `parameters` live on the path item, not the operation. A
        # spec is allowed to omit them and rely on the template alone, so only
        # flag a mismatch when the spec actually declares them.
        declared = spec_params(spec[path])
        if declared and template_names(path) != declared:
            problems.append(
                f"{method} {path} uses {sorted(template_names(path))}; the spec declares {sorted(declared)}"
            )

    if problems:
        print(f"{readme.name}: {len(problems)} problem(s) in the API section:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nEither fix the README, or regenerate from the live spec at http://localhost:8000/openapi.json",
            file=sys.stderr,
        )
        return 1

    total_ops = sum(len(v) for v in spec.values())
    print(f"OK: {len(rows)} documented endpoints all match the spec ({total_ops} operations total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
