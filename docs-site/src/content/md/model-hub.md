# Model Hub

There is **no built-in provider order.** You register models in the UI, then
serve either a single model or an ordered fallback chain.

## Failover semantics

```text
Request ──► provider in cooldown? ──yes──► try next in chain
                   │ no
                   ▼
              call provider ──429──► cooldown honouring Retry-After ──► next
                   │
                   ├── fails before first token ──► next in chain
                   ├── fails mid-stream ──► re-raise (never switch under the user)
                   └── tokens flowing ──► stream to client
```

A provider returning `429` is put in cooldown (honouring `Retry-After`) and the
next one in the chain answers; providers that fail before emitting a single token
fall through, and one that fails mid-stream re-raises rather than switching
underneath the user.

## Providers

Nine hosted providers are configurable — OpenAI, Google Gemini, Groq, OpenRouter,
Cerebras, NVIDIA NIM, Together, Mistral, DeepSeek — plus any local
OpenAI-compatible server (llama.cpp, Ollama, vLLM, LM Studio).

## Credential handling

Keys are **encrypted at rest** with Fernet when `CREDENTIAL_ENCRYPTION_KEY` is
set. Ciphertexts are self-describing (`enc:v1:`), so a database holding a mix of
plaintext and encrypted rows reads correctly row by row. An undecryptable key
reports `has_api_key: false` and asks for the key again, rather than returning
garbage that `bool()` would treat as usable. Keys never appear in a response.

## Endpoints

- `GET|POST /models` — list and add models (keys redacted on read).
- `POST /models/{id}/test` — a real call, not a mock. An embedding probe also
  auto-detects and persists the vector dimension.
- `GET|POST /chains` — ordered fallback chains.
- `GET|PUT /serving` — select the served model or chain (applies live).
