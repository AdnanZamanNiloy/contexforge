import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'

import ContextMeter from './ContextMeter'
import { estimateContext } from '../services/api'

// The context meter makes the gap between "material selected" and "material
// actually read" visible, and gives that gap a lever via depth. The tests pin
// the honesty of the readout: it must not overstate what will reach the model,
// must name sources the depth will not read, and must never show a stale
// estimate under a new selection.

vi.mock('../services/api', () => ({
  estimateContext: vi.fn(),
}))

function response(overrides = {}) {
  return {
    source_count: 3,
    sources: [
      { source_id: 'a', title: 'Alpha', chunk_count: 10, char_count: 800, token_count: 200 },
      { source_id: 'b', title: 'Bravo', chunk_count: 10, char_count: 800, token_count: 200 },
      { source_id: 'c', title: 'Charlie', chunk_count: 40, char_count: 9000, token_count: 2000 },
    ],
    total_char_count: 10600,
    total_token_count: 2400,
    prompt_token_estimate: 240,
    prompt_chunk_limit: 5,
    per_source_cap: 5,
    usable_fraction: 0.1,
    depth: 'focused',
    effective_depth: 'focused',
    over_budget: false,
    beyond_diminishing_returns: false,
    dropped_source_ids: [],
    missing_source_ids: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(estimateContext).mockReset()
  vi.mocked(estimateContext).mockResolvedValue(response())
})

async function renderMeter(props = {}) {
  const utils = render(<ContextMeter sourceIds={['a', 'b']} onDepthChange={() => {}} {...props} />)
  // The estimate is debounced, so tests wait for the request rather than racing it.
  await waitFor(() => expect(estimateContext).toHaveBeenCalled())
  await act(async () => {
    await Promise.resolve()
  })
  return utils
}

describe('ContextMeter readout', () => {
  it('shows how much of the selection will be used', async () => {
    await renderMeter()
    // The gap is the point: 240 of 2400 tokens.
    expect(screen.getByText('240')).toBeInTheDocument()
    expect(screen.getByText(/of 2\.4k tokens used/i)).toBeInTheDocument()
  })

  it('explains that a large selection is sampled', async () => {
    await renderMeter()
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.getByText(/best 5 chunks overall/i)).toBeInTheDocument()
  })

  it('requests the estimate with the current selection and depth', async () => {
    await renderMeter({ sourceIds: ['a', 'b'], depth: 'balanced' })

    expect(vi.mocked(estimateContext)).toHaveBeenCalledWith(['a', 'b'], 'balanced')
  })

  it('treats an empty selection as the whole knowledge base', async () => {
    await renderMeter({ sourceIds: [] })

    expect(vi.mocked(estimateContext)).toHaveBeenCalledWith([], 'focused')
  })

  it('does not re-request when the same sources are reordered', async () => {
    const { rerender } = render(<ContextMeter sourceIds={['a', 'b']} onDepthChange={() => {}} />)
    await waitFor(() => expect(estimateContext).toHaveBeenCalledTimes(1))
    await act(async () => {
      await Promise.resolve()
    })

    rerender(<ContextMeter sourceIds={['b', 'a']} onDepthChange={() => {}} />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(estimateContext).toHaveBeenCalledTimes(1)
  })
})

describe('ContextMeter depth control', () => {
  it('offers all three depths and marks the active one', async () => {
    vi.mocked(estimateContext).mockResolvedValue(
      response({ depth: 'balanced', effective_depth: 'balanced' }),
    )
    await renderMeter({ depth: 'balanced' })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.getByRole('button', { name: 'Focused' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Broad' })).toBeInTheDocument()
    // The active button tracks what will actually run.
    expect(screen.getByRole('button', { name: 'Balanced' }).className).toContain('is-active')
  })

  it('reports the chosen depth', async () => {
    const onDepthChange = vi.fn()
    await renderMeter({ onDepthChange })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    fireEvent.click(screen.getByRole('button', { name: 'Broad' }))

    expect(onDepthChange).toHaveBeenCalledWith('broad')
  })

  it('marks the depth that was requested, even when sources are capped', async () => {
    vi.mocked(estimateContext).mockResolvedValue(
      response({ depth: 'broad', effective_depth: 'broad', dropped_source_ids: ['c'] }),
    )
    await renderMeter({ depth: 'broad' })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    // A click must always visibly register. The button used to track a clamped
    // "effective" depth, so choosing Broad left Focused highlighted and the
    // control read as broken.
    expect(screen.getByRole('button', { name: 'Broad' }).className).toContain('is-active')
    expect(screen.getByRole('button', { name: 'Focused' }).className).not.toContain('is-active')
  })

  it('never claims a depth was reduced', async () => {
    // There is no reduction to report any more: a depth is applied as asked and
    // the caps it carries are hard limits.
    vi.mocked(estimateContext).mockResolvedValue(
      response({ depth: 'broad', effective_depth: 'broad', dropped_source_ids: ['c'] }),
    )
    await renderMeter({ depth: 'broad' })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.queryByText(/is reduced to/i)).not.toBeInTheDocument()
  })

  it('reports a cap on breadth as a cap, with a way out', async () => {
    vi.mocked(estimateContext).mockResolvedValue(
      response({ depth: 'focused', effective_depth: 'focused', dropped_source_ids: ['c'] }),
    )
    await renderMeter({ depth: 'focused' })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    // 1 of 3 sources is dropped, so the user is told which and how to include it.
    expect(screen.getByText(/1 of 3 selected sources exceed/i)).toBeInTheDocument()
    expect(screen.getByText(/widen the depth to include it/i)).toBeInTheDocument()
  })

  it('states both limits so a single source is not silently capped', async () => {
    vi.mocked(estimateContext).mockResolvedValue(
      response({ depth: 'broad', effective_depth: 'broad', prompt_chunk_limit: 25, per_source_cap: 12 }),
    )
    await renderMeter({ depth: 'broad' })
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.getByText(/best 25 chunks overall/i)).toBeInTheDocument()
    expect(screen.getByText(/at most 12 from any one source/i)).toBeInTheDocument()
  })
})

describe('ContextMeter honesty', () => {
  it('names sources the depth will not read', async () => {
    vi.mocked(estimateContext).mockResolvedValue(
      response({ dropped_source_ids: ['c'], over_budget: true }),
    )
    await renderMeter()
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    const dropped = screen.getByText(/not used at this depth/i)
    expect(dropped).toBeInTheDocument()
    // Named, not hidden: the selection count and the answer must reconcile.
    expect(screen.getByText('Charlie')).toBeInTheDocument()
  })

  it('warns about selected sources that no longer exist', async () => {
    vi.mocked(estimateContext).mockResolvedValue(response({ missing_source_ids: ['gone'] }))
    await renderMeter()
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.getByText(/no longer exist/i)).toBeInTheDocument()
  })

  it('warns when a selection is past the point of diminishing returns', async () => {
    vi.mocked(estimateContext).mockResolvedValue(response({ beyond_diminishing_returns: true }))
    await renderMeter()
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.getByText(/unlikely to change the answer/i)).toBeInTheDocument()
  })

  it('shows no warning for a selection that fits', async () => {
    await renderMeter()
    fireEvent.click(screen.getByRole('button', { name: /context details/i }))

    expect(screen.queryByText(/no longer exist/i)).toBeNull()
    expect(screen.queryByText(/is reduced to/i)).toBeNull()
  })
})

describe('ContextMeter resilience', () => {
  it('renders nothing when disabled', () => {
    render(<ContextMeter sourceIds={['a']} disabled onDepthChange={() => {}} />)

    expect(screen.queryByRole('button', { name: /context details/i })).toBeNull()
    expect(estimateContext).not.toHaveBeenCalled()
  })

  it('never blocks the composer when the estimate fails', async () => {
    vi.mocked(estimateContext).mockRejectedValue(new Error('offline'))
    render(<ContextMeter sourceIds={['a']} onDepthChange={() => {}} />)

    await waitFor(() => expect(estimateContext).toHaveBeenCalled())
    // A failed estimate must not surface an error where the user is typing.
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.queryByText(/offline/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /context details/i })).toBeNull()
  })

  it('never shows one selection’s estimate under another', async () => {
    let resolveFirst
    vi.mocked(estimateContext).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = () => resolve(response({ total_token_count: 9999 }))
        }),
    )

    const { rerender } = render(<ContextMeter sourceIds={['a']} onDepthChange={() => {}} />)
    await waitFor(() => expect(estimateContext).toHaveBeenCalledTimes(1))

    rerender(<ContextMeter sourceIds={['a', 'b', 'c']} onDepthChange={() => {}} />)
    act(() => {
      resolveFirst?.()
    })
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.queryByText(/9\.9k/)).toBeNull()
  })
})
