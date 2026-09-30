import { describe, it, expect } from 'vitest'

import { RETRIEVAL_LATENCY_KEYS, retrievalBreakdownText, sumLatency } from './latency'

// The payload from a real turn against the JUST article. `retrieve_ms` is 3 ms
// while the cross-encoder rerank took 186 ms — displaying the lookup leg alone
// told the user retrieval was effectively free, which it was not.
const REAL = {
  hyde_ms: 0.0089,
  embed_ms: 0.92,
  retrieve_ms: 3.01,
  rerank_ms: 185.68,
  generate_ms: 3827.13,
  total_ms: 4016.75,
}

describe('sumLatency', () => {
  it('includes every retrieval leg, not just the lookup', () => {
    // ~190 ms, not the 3 ms `retrieve_ms` alone.
    expect(sumLatency(REAL, RETRIEVAL_LATENCY_KEYS)).toBeCloseTo(189.62, 1)
  })

  it('excludes generation, which is reported separately', () => {
    const total = sumLatency(REAL, RETRIEVAL_LATENCY_KEYS)
    expect(total).toBeLessThan(500)
    expect(RETRIEVAL_LATENCY_KEYS).not.toContain('generate_ms')
  })

  it('returns null when nothing was reported', () => {
    // Null renders as a dash; 0 would read as an instant, successful retrieval.
    expect(sumLatency({}, RETRIEVAL_LATENCY_KEYS)).toBeNull()
    expect(sumLatency(null, RETRIEVAL_LATENCY_KEYS)).toBeNull()
    expect(sumLatency(undefined, RETRIEVAL_LATENCY_KEYS)).toBeNull()
  })

  it('ignores missing and non-numeric legs', () => {
    expect(sumLatency({ rerank_ms: 120 }, RETRIEVAL_LATENCY_KEYS)).toBe(120)
    expect(sumLatency({ rerank_ms: null, retrieve_ms: 4 }, RETRIEVAL_LATENCY_KEYS)).toBe(4)
    expect(sumLatency({ rerank_ms: 'fast' }, RETRIEVAL_LATENCY_KEYS)).toBeNull()
  })
})

describe('retrievalBreakdownText', () => {
  it('names each leg worth showing', () => {
    const text = retrievalBreakdownText(REAL, RETRIEVAL_LATENCY_KEYS)
    expect(text).toContain('vector + keyword search 3 ms')
    expect(text).toContain('reranking 186 ms')
  })

  it('omits sub-millisecond legs that would only add noise', () => {
    expect(retrievalBreakdownText(REAL, RETRIEVAL_LATENCY_KEYS)).not.toContain('query expansion')
  })

  it('returns null when there is nothing worth saying', () => {
    expect(retrievalBreakdownText({ hyde_ms: 0.1 }, RETRIEVAL_LATENCY_KEYS)).toBeNull()
    expect(retrievalBreakdownText(null, RETRIEVAL_LATENCY_KEYS)).toBeNull()
  })
})
