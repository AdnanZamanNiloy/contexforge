// Timing helpers for the retrieval panel.
//
// The server reports retrieval as several separate legs — query expansion,
// embedding, the vector/BM25 lookup, and the cross-encoder rerank. Each leg is
// individually tiny except the rerank, which is the largest retrieval cost by a
// wide margin. Displaying only the lookup leg therefore reported figures like
// "3 ms" for a turn that actually spent ~190 ms retrieving, and a user who saw
// that had no way to tell where their wait had gone.

// The legs that make up "finding the passages". `generate_ms` is excluded: it is
// the model's own time, surfaced separately, and folding it in here would make
// retrieval look slow for a reason that has nothing to do with retrieval.
export const RETRIEVAL_LATENCY_KEYS = ['hyde_ms', 'embed_ms', 'retrieve_ms', 'rerank_ms']

// Human labels for the tooltip, in the order they occur.
const KEY_LABELS = {
  hyde_ms: 'query expansion',
  embed_ms: 'embedding',
  retrieve_ms: 'vector + keyword search',
  rerank_ms: 'reranking',
}

/**
 * Sum the given latency legs, ignoring legs the server did not report.
 *
 * @param {object} latency  The `latency_ms` payload from the server.
 * @param {string[]} keys   Legs to include.
 * @returns {number|null}  Total in milliseconds, or null when nothing was
 *   reported — so the caller can show a dash rather than a misleading 0 ms.
 */
export function sumLatency(latency, keys) {
  if (!latency || typeof latency !== 'object') {
    return null
  }
  let total = 0
  let seen = false
  for (const key of keys) {
    const value = latency[key]
    if (typeof value === 'number' && Number.isFinite(value)) {
      total += value
      seen = true
    }
  }
  return seen ? total : null
}

/**
 * A short per-leg breakdown for the tooltip, e.g.
 * "embedding 1 ms + vector + keyword search 3 ms + reranking 186 ms".
 *
 * Only legs worth naming are included: a sub-millisecond expansion adds noise
 * without explaining anything.
 */
export function retrievalBreakdownText(latency, keys) {
  if (!latency || typeof latency !== 'object') {
    return null
  }
  const parts = []
  for (const key of keys) {
    const value = latency[key]
    if (typeof value === 'number' && Number.isFinite(value) && value >= 1) {
      parts.push(`${KEY_LABELS[key] || key} ${value.toFixed(0)} ms`)
    }
  }
  return parts.length ? parts.join(' + ') : null
}
