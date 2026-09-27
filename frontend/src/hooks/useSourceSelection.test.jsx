import { describe, it, expect } from 'vitest'
import { render, act } from '@testing-library/react'
import { useState } from 'react'

import { useSourceSelection } from './useSourceSelection'

// The sidebar owns source selection and that single selection scopes chat and
// the mind map.  These tests pin the interactions the sidebar depends on:
// single-select, multi-select, clearing, and pruning when a source disappears.

const SOURCES = [
  { id: 'a', title: 'Alpha', type: 'pdf', chunks: 10 },
  { id: 'b', title: 'Bravo', type: 'web', chunks: 20 },
  { id: 'c', title: 'Charlie', type: 'github', chunks: 30 },
]

function mountHook(initialSources = SOURCES) {
  const results = []
  function Probe({ sources }) {
    results.push(useSourceSelection(sources))
    return null
  }
  function Host() {
    const [sources, setSources] = useState(initialSources)
    setSourcesForHost = setSources
    return <Probe sources={sources} />
  }
  let setSourcesForHost
  render(<Host />)
  return {
    latest: () => results[results.length - 1],
    setSources: (next) => act(() => setSourcesForHost(next)),
    all: () => results,
  }
}

describe('useSourceSelection', () => {
  it('starts with nothing selected, meaning every source is in scope', () => {
    const { latest } = mountHook()
    expect(latest().selectedIds).toEqual([])
    expect(latest().count).toBe(0)
    expect(latest().isEmpty).toBe(true)
  })

  it('selects a single source on click', () => {
    const { latest } = mountHook()
    act(() => latest().select('b'))
    expect(latest().selectedIds).toEqual(['b'])
    expect(latest().has).toBe(true)
  })

  it('clears the selection when the only selected source is clicked again', () => {
    const { latest } = mountHook()
    act(() => latest().select('b'))
    act(() => latest().select('b'))
    expect(latest().selectedIds).toEqual([])
  })

  it('accumulates sources in the order they were picked', () => {
    const { latest } = mountHook()
    act(() => latest().select('c'))
    act(() => latest().select('a'))
    expect(latest().selectedIds).toEqual(['c', 'a'])
  })

  it('toggle adds and removes one source without disturbing the rest', () => {
    const { latest } = mountHook()
    act(() => latest().select('a'))
    act(() => latest().select('c'))
    act(() => latest().toggle('b'))
    expect(latest().selectedIds).toEqual(['a', 'c', 'b'])
    act(() => latest().toggle('a'))
    expect(latest().selectedIds).toEqual(['c', 'b'])
  })

  it('selectOnly replaces the whole selection', () => {
    const { latest } = mountHook()
    act(() => latest().select('a'))
    act(() => latest().select('b'))
    act(() => latest().selectOnly('c'))
    expect(latest().selectedIds).toEqual(['c'])
  })

  it('selectAll takes every available source', () => {
    const { latest } = mountHook()
    act(() => latest().selectAll())
    expect(latest().selectedIds).toEqual(['a', 'b', 'c'])
  })

  it('clear empties the selection', () => {
    const { latest } = mountHook()
    act(() => latest().selectAll())
    act(() => latest().clear())
    expect(latest().selectedIds).toEqual([])
  })

  it('replaceAll sets the selection in one shot, de-duplicated', () => {
    const { latest } = mountHook()
    act(() => latest().replaceAll(['a', 'b', 'a']))
    expect(latest().selectedIds).toEqual(['a', 'b'])
  })

  it('drops a selected source that is deleted from the knowledge base', () => {
    const { latest, setSources } = mountHook()
    act(() => latest().select('a'))
    act(() => latest().select('b'))
    setSources(SOURCES.filter((s) => s.id !== 'a'))
    expect(latest().selectedIds).toEqual(['b'])
  })

  it('clears the selection when the project view empties', () => {
    const { latest, setSources } = mountHook()
    act(() => latest().selectAll())
    setSources([])
    expect(latest().selectedIds).toEqual([])
  })

  it('keeps the selection when the source list is replaced with the same ids', () => {
    const { latest, setSources } = mountHook()
    act(() => latest().select('b'))
    // Same ids, new array identity — a re-render must not drop the selection.
    setSources(SOURCES.map((s) => ({ ...s })))
    expect(latest().selectedIds).toEqual(['b'])
  })

  it('ignores a null/undefined source list', () => {
    const { latest } = mountHook(null)
    expect(latest().selectedIds).toEqual([])
  })

  it('ignores selection calls for a missing id', () => {
    const { latest } = mountHook()
    act(() => latest().select(null))
    expect(latest().selectedIds).toEqual([])
  })
})
