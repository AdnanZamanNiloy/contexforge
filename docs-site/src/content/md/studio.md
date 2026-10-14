# Repository Studio

Four repository analyzers. Each targets one repository (resolved from an explicit
request, then the project's remembered tool source, then its first GitHub member)
and caches against a content fingerprint, so an unchanged repository is analysed
once.

| Tool | Route | Output |
|---|---|---|
| Architecture Diagram | `POST /architecture/generate` (SSE) | Mermaid diagram of the real request and domain paths, every code node carrying the exact file path it came from |
| Security & Quality | `POST /security/scan` | Dependency advisories (OSV), code-level findings via `ast-grep`, and quality rules |
| Dependency & Tech Stack | `POST /tech-stack/scan` | Manifest and lockfile inventory with per-service detection |
| Health Score & Hotspots | `POST /health/scan` | Structural risk scoring and ranked hotspots |

Each has a `/rescan` variant that ignores the cache and a `GET /{project_id}`
that returns the stored result.

## Why it is distinct

**Repository Studio.** Architecture diagrams where every code node carries its
file path, OSV advisories, `ast-grep` findings, dependency inventory and ranked
hotspots — analysis a general chat tool does not attempt.

## Dependency advisories

Dependency scanning sends package names and versions to **OSV** (Open Source
Vulnerabilities). Nothing else about the repository leaves your machine for this
step.
