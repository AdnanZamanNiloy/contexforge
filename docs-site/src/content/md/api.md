# API reference

**The complete, always-current API reference is generated from the running
application** and served by FastAPI — it cannot drift from the code:

| | |
|---|---|
| **http://localhost:8000/docs** | Swagger UI — try every endpoint from the browser |
| **http://localhost:8000/redoc** | ReDoc — better for reading top to bottom |
| **http://localhost:8000/openapi.json** | The raw OpenAPI 3.1 spec |

This page is deliberately **curated, not exhaustive** — the calls you are likely
to make by hand. Everything else is one click away at `/docs`.

```text
Health
GET  /health                              Liveness check

Ingest
POST /ingest/source                       Ingest a URL or GitHub repo
POST /ingest/file                         Upload a PDF or DOCX
GET  /ingest/sources                      List indexed sources
GET  /ingest/source/{source_id}           Extraction verdict and provenance
GET  /ingest/source/{source_id}/content   The indexed chunk text
PATCH /ingest/source/{source_id}          Rename a source
DELETE /ingest/source/{source_id}         Remove a source and its chunks

Ask
POST /query                               Answer (JSON: passages, scores, confidence)
POST /query/stream                        Stream answer tokens over SSE
POST /context/estimate                    Price a selection against the prompt budget

Turn a selection into something
POST /mindmap/generate                    Generate or fetch the cached mind map
GET  /mindmap/{key}                       Fetch a stored mind map
POST /note/generate                       Generate or fetch the cached note
GET  /note/{key}                          Fetch a stored note

Projects
GET  /projects                            List projects
POST /projects                            Create a project
GET  /projects/{project_id}               One project
POST /projects/{project_id}/sources       Attach a source to a project

Studio (repository analyzers)
POST /architecture/generate               Architecture diagram (SSE)
POST /security/scan                       Security and quality scan
POST /tech-stack/scan                     Dependency and tech stack
POST /health/scan                         Structural health and hotspots

Model Hub
GET  /models                              List configured models (keys redacted)
POST /models                              Add a model (LLM or embedding, API or local)
POST /models/{model_id}/test              Live-test a model
GET  /serving                             Current serving configuration
PUT  /serving                             Select the served model or chain (applies live)
```

> The list above is checked against the live spec in CI — see
> `backend/scripts/check_readme_api.py`. Adding an endpoint without updating this
> curated set, or documenting one that does not exist, fails the build.
