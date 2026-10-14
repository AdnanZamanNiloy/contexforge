# Context control

Selecting sources is the workspace's primary control, and it reports what it
costs instead of being a silent one. The sidebar prices the current selection
against the prompt budget on every change — and the estimator makes **no**
embedding, retrieval, rerank or generation call, so it is free to re-run.

## Depth presets

Three depths map to concrete retrieval limits, so widening the depth does
something measurable:

| Depth | Max sources | Retrieved | Reranked to | Per-source cap |
|---|---|---|---|---|
| `focused` | 2 | 20 | 5 | 4 |
| `balanced` | 6 | 40 | 12 | 6 |
| `broad` | 25 | 80 | 25 | 10 |

Start at `focused` for one large document; go `broad` when the answer needs to
span several.

## Nothing is smoothed over

The reported numbers are deliberately candid:

- A depth the selection cannot justify is **reduced and the response says so**.
- Sources the depth will not read are **named and struck through**.
- Selected ids missing from the index are **reported separately** from sources
  found — "I selected it" and "it is contributing" are different facts.

## Endpoints

- `POST /context/estimate` — price a selection against the prompt budget.
- `GET /query` accepts `context_depth`.

## History that stays true

Chat sessions persist per project in SQLite, and **each message records the exact
source selection it was answered with** — so re-reading history after you change
the workspace selection shows the answer you actually got, not the answer the
current selection would produce.
