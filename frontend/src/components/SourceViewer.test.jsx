import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'

import SourceViewer from './SourceViewer'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

function chunk(rank) {
  return {
    source_id: 'src-1',
    rank,
    score: 0.03,
    text: `passage ${rank}`,
    metadata: { title: 'Jashore University of Science and Technology' },
  }
}

// The exact payload the app produced for "give me details about it" against
// the JUST article: 15% confidence, a 3 ms lookup and a 186 ms rerank.
const LOW_CONFIDENCE = {
  answer_confidence: 0.15,
  source_coverage: 'Weak',
  sources_used: 1,
  retrieved_chunks: 5,
  low_confidence_reason: 'This question has no topic words of its own.',
}

const REAL_LATENCY = {
  hyde_ms: 0.0089,
  embed_ms: 0.92,
  retrieve_ms: 3.01,
  rerank_ms: 185.68,
  generate_ms: 3827.13,
  total_ms: 4016.75,
}

function renderPanel(props = {}) {
  return render(
    <SourceViewer
      sources={[chunk(1), chunk(2), chunk(3)]}
      latency={REAL_LATENCY}
      confidence={LOW_CONFIDENCE}
      {...props}
    />,
  )
}

describe('Confidence & Coverage', () => {
  it('reports the full retrieval cost, not just the lookup leg', () => {
    renderPanel()
    // 3 ms on its own understated a ~190 ms retrieval and implied the cost was
    // somewhere else entirely.
    expect(screen.getByTestId('retrieval-time').textContent).toBe('190 ms')
  })

  it('breaks the retrieval time down on hover', () => {
    renderPanel()
    const breakdown = screen.getByTestId('retrieval-time').getAttribute('title')
    expect(breakdown).toContain('reranking 186 ms')
    expect(breakdown).toContain('vector + keyword search 3 ms')
  })

  it('shows a dash rather than 0 ms when no timing was reported', () => {
    renderPanel({ latency: {} })
    expect(screen.getByTestId('retrieval-time').textContent).toBe('-')
  })

  it('explains a low score so the number is actionable', () => {
    renderPanel()
    expect(screen.getByTestId('confidence-reason').textContent).toContain('no topic words')
  })

  it('omits the explanation when confidence is healthy', () => {
    renderPanel({
      confidence: { ...LOW_CONFIDENCE, answer_confidence: 0.97, source_coverage: 'Excellent', low_confidence_reason: null },
    })
    expect(screen.queryByTestId('confidence-reason')).toBeNull()
  })

  it('renders the server figures verbatim', () => {
    renderPanel()
    expect(screen.getByText('15%')).toBeTruthy()
    expect(screen.getByText('Weak')).toBeTruthy()
    expect(screen.getByText('5')).toBeTruthy()
  })

  it('shows a skeleton while streaming rather than a misleading zero', () => {
    render(<SourceViewer sources={[]} latency={REAL_LATENCY} isStreaming />)
    // No sources yet, so the panel must not claim retrieval was instant.
    expect(screen.queryByTestId('retrieval-time')).toBeNull()
    expect(screen.queryByTestId('confidence-reason')).toBeNull()
  })

  it('prompts for a question when nothing has been retrieved', () => {
    render(<SourceViewer sources={[]} latency={{}} />)
    expect(screen.getByText(/Awaiting retrieval/i)).toBeTruthy()
    expect(screen.queryByTestId('retrieval-time')).toBeNull()
  })
})
