import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Sidebar from './Sidebar'
import { useSourceSelection } from '../../hooks/useSourceSelection'
import { useSources } from '../../hooks/useSources'

// The Sidebar tests elsewhere drive mock callbacks, so they can only prove a
// handler was *called*. This file wires the real hook to the real Sidebar,
// because the reported bug was a state bug: two rows that could not be
// selected and deselected independently.

const WIKI_SOURCES = [
  { id: 'w1', title: 'en.wikipedia.org/wiki/Photosynthesis', type: 'web', status: 'indexed' },
  { id: 'w2', title: 'en.wikipedia.org/wiki/Photosynthesis', type: 'web', status: 'indexed' },
]

const SOURCES = [
  { id: 'a', title: 'Alpha', type: 'pdf', status: 'indexed' },
  { id: 'b', title: 'Bravo', type: 'github', status: 'indexed' },
  { id: 'c', title: 'Charlie', type: 'web', status: 'indexed' },
]

function Harness({ sources }) {
  const selection = useSourceSelection(sources)
  return (
    <MemoryRouter>
      <div data-testid="scope">{JSON.stringify(selection.selectedIds)}</div>
      <Sidebar
        sources={sources}
        selectedSourceIds={selection.selectedIds}
        onSelectSource={selection.select}
        onToggleSource={selection.toggle}
        onSelectAllSources={selection.selectAll}
        onClearSourceSelection={selection.clear}
      />
    </MemoryRouter>
  )
}

function scope() {
  return JSON.parse(screen.getByTestId('scope').textContent)
}

function checkboxFor(title) {
  return screen.getByLabelText(`Use ${title} in the workspace`)
}

function rowFor(title) {
  return screen.getByText(title).closest('.source-item-compact')
}

describe('source selection state', () => {
  it('selecting a row adds exactly that source', () => {
    render(<Harness sources={SOURCES} />)
    fireEvent.click(rowFor('Alpha'))
    expect(scope()).toEqual(['a'])
  })

  it('clicking a selected row again removes it', () => {
    render(<Harness sources={SOURCES} />)
    fireEvent.click(rowFor('Alpha'))
    expect(scope()).toEqual(['a'])
    fireEvent.click(rowFor('Alpha'))
    expect(scope()).toEqual([])
  })

  it('two sources can be selected independently', () => {
    render(<Harness sources={SOURCES} />)
    fireEvent.click(rowFor('Alpha'))
    fireEvent.click(rowFor('Bravo'))
    expect(scope()).toEqual(['a', 'b'])

    fireEvent.click(rowFor('Alpha'))
    expect(scope()).toEqual(['b'])
  })

  it('a row checkbox selects only its own source', () => {
    render(<Harness sources={SOURCES} />)
    fireEvent.click(checkboxFor('Alpha'))
    expect(scope()).toEqual(['a'])
  })

  it('a row checkbox deselects its own source when clicked again', () => {
    render(<Harness sources={SOURCES} />)
    fireEvent.click(checkboxFor('Alpha'))
    expect(scope()).toEqual(['a'])
    fireEvent.click(checkboxFor('Alpha'))
    expect(scope()).toEqual([])
  })

  it('deselecting one of two selected sources leaves the other', () => {
    // The reported symptom: with both rows checked, unchecking one appeared to
    // do nothing because the other stayed checked.
    render(<Harness sources={SOURCES} />)
    fireEvent.click(screen.getByLabelText('Select all sources'))
    expect(scope()).toEqual(['a', 'b', 'c'])

    fireEvent.click(checkboxFor('Alpha'))
    expect([...scope()].sort()).toEqual(['b', 'c'])

    fireEvent.click(checkboxFor('Alpha'))
    expect([...scope()].sort()).toEqual(['a', 'b', 'c'])
  })

  it('the row and its checkbox stay in agreement', () => {
    // The row calls select() and the checkbox calls toggle(); if they disagree
    // the UI reports two different answers for the same state.
    render(<Harness sources={SOURCES} />)
    fireEvent.click(rowFor('Alpha'))
    expect(checkboxFor('Alpha').checked).toBe(true)
    expect(rowFor('Alpha').getAttribute('aria-pressed')).toBe('true')

    fireEvent.click(checkboxFor('Alpha'))
    expect(checkboxFor('Alpha').checked).toBe(false)
    expect(rowFor('Alpha').getAttribute('aria-pressed')).toBe('false')
  })

  it('two rows sharing a title remain independently selectable', () => {
    // The screenshot showed two identically-titled rows that could not be
    // toggled apart. They are distinct sources, so they must not interfere.
    render(<Harness sources={WIKI_SOURCES} />)
    const boxes = screen.getAllByLabelText(/^Use en\.wikipedia\.org.* in the workspace$/)
    expect(boxes).toHaveLength(2)

    fireEvent.click(boxes[0])
    expect(scope()).toEqual(['w1'])
    expect(boxes[0].checked).toBe(true)
    expect(boxes[1].checked).toBe(false)

    fireEvent.click(boxes[1])
    expect(scope()).toEqual(['w1', 'w2'])

    fireEvent.click(boxes[0])
    expect(scope()).toEqual(['w2'])
    expect(boxes[0].checked).toBe(false)
    expect(boxes[1].checked).toBe(true)
  })
})


describe('duplicate source ids', () => {
  // The reported screenshot: two rows rendering the same source, both checked,
  // where unchecking one left the other checked and nothing felt independent.
  // Selection is keyed on id, so one id means one row as far as the user is
  // concerned. useSources now enforces uniqueness on every write; this drives
  // that hook the way an ingest does — optimistic row, then a rewrite of its id
  // onto an id the list already holds.
  it('an optimistic row rewritten onto an existing id does not duplicate', () => {
    // Each step in its own act() so the intermediate state is real. Batching
    // them lets the later write win outright and hides the collision, which is
    // how an earlier version of this test passed against broken code.
    const { result } = renderHook(() => useSources())
    const api = result.current

    act(() => {
      api.addSource({ id: 'web-1', title: 'en.wikipedia.org', type: 'web', status: 'processing' })
    })
    // A refresh lands while the ingest is in flight and brings in the real
    // source, leaving the optimistic row alongside it.
    act(() => {
      api.addSource({ id: 'real-1', title: 'en.wikipedia.org', type: 'web', status: 'indexed' })
    })
    expect(result.current.sources.map((s) => s.id)).toEqual(['real-1', 'web-1'])

    // The ingest resolves and rewrites the optimistic row's id onto the real
    // one, which is already taken.
    act(() => {
      api.updateSource('web-1', { id: 'real-1', status: 'indexed' })
    })

    const ids = result.current.sources.map((s) => s.id)
    expect(new Set(ids).size, `duplicate id in ${ids}`).toBe(ids.length)
  })

  it('refreshing with a repeated id yields one row', () => {
    const { result } = renderHook(() => useSources())
    act(() => {
      result.current.replaceAll([
        { id: 'w1', title: 'en.wikipedia.org/wiki/A', type: 'web', status: 'indexed' },
        { id: 'w1', title: 'en.wikipedia.org/wiki/A', type: 'web', status: 'indexed' },
      ])
    })
    expect(result.current.sources).toHaveLength(1)
  })

  it('two rows sharing an id cannot be toggled apart', () => {
    // Guards the symptom itself, so a regression in the store is caught at the
    // point the user would notice it rather than only in the store's own tests.
    const { result } = renderHook(() => useSources())
    act(() => {
      result.current.replaceAll([
        { id: 'w1', title: 'en.wikipedia.org/wiki/A', type: 'web', status: 'indexed' },
        { id: 'w2', title: 'en.wikipedia.org/wiki/B', type: 'web', status: 'indexed' },
      ])
    })
    const ids = result.current.sources.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
