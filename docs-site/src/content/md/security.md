# Security & privacy

## What leaves your machine

ContextForge is local-first, not offline-only. Exactly what is sent, and to whom,
depends on the models you configure:

| Action | What is sent | To |
|---|---|---|
| Ingest a file | Text chunks | Your **embedding** model (nothing leaves if it is local) |
| Ask a question | The question, plus the retrieved passages | Your **chat** model or chain (nothing leaves if it is local) |
| HyDE *(optional)* | The question | Your chat model |
| Reranking | Nothing | Runs locally |
| Ingest a web page, YouTube video or GitHub repository | A request for that resource | The target site, YouTube, or the GitHub REST API |
| Dependency scan (Studio) | Package names and versions | OSV |
| Tracing *(optional)* | Trace data | `LANGFUSE_HOST` (cloud by default) |

With a local embedder, a local chat server, and tracing off, the only outbound
traffic is whatever you ask it to fetch.

## Credential handling

- Provider keys are entered in the Model Hub, never read from the environment,
  and **never returned in an API response**.
- With `CREDENTIAL_ENCRYPTION_KEY` set, keys are encrypted at rest with Fernet.
  Ciphertexts are self-describing (`enc:v1:`), so mixed plaintext and encrypted
  rows read correctly.
- Without the key, keys are stored in plaintext and the app warns once. Set it.
- A key that cannot be decrypted is reported as absent (`false`) rather than used.

## Threat model in brief

- **In scope:** keeping provider credentials out of logs, responses and source
  control; making clear what is sent where.
- **Out of scope today:** user authentication, per-user data isolation and
  network-level protection. Treat the backend as a trusted-network service, as
  described under [Deployment](/docs/deployment).
- **Untrusted content:** ingested documents and web pages are data, but they are
  passed to an LLM. Treat answers derived from sources you do not control with the
  same care you would give the sources themselves.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Use GitHub's
private vulnerability reporting (the **Security** tab of the repository). Include
the version or commit, reproduction steps, and the impact you believe it has.
