import { describe, it, expect, vi } from 'vitest'
import { forwardRef, useImperativeHandle } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'

import NotePanel from './NotePanel'

// The note is scoped by a *selection* of sources — one or several — which the
// mind map's single-source dropdown cannot express.  These tests pin the three
// behaviours that follow from that: sources toggle independently, an empty
// selection cannot generate, and the panel never silently invents a scope.

const SOURCES = [
  { id: 'a', title: 'Alpha', type: 'pdf' },
  { id: 'b', title: 'Bravo', type: 'github' },
  { id: 'c', title: 'Charlie', type: 'web' },
]

// The view talks to the API on mount; keep it inert and expose the ref calls.
vi.mock('./NoteView', () => ({
  default: forwardRef(function MockNoteView({ sourceIds }, ref) {
    useImperativeHandle(ref, () => ({
      regenerate: () => {
        document.body.dataset.regenerated = (sourceIds || []).join(',')
      },
      create: () => {},
    }))
    return <div data-testid="note-view" data-scope={(sourceIds || []).join(',')} />
  }),
}))

function renderPanel(props = {}) {
  const onSelectionChange = vi.fn()
  const utils = render(
    <NotePanel
      sources={SOURCES}
      selectedSourceIds={[]}
      onSelectionChange={onSelectionChange}
      {...props}
    />,
  )
  return { ...utils, onSelectionChange }
}

function openPicker() {
  fireEvent.click(screen.getByRole('button', { name: /select sources|selected/i }))
}

describe('NotePanel source selection', () => {
  it('starts with nothing selected rather than defaulting to everything', () => {
    renderPanel()
    expect(screen.getByTestId('note-view').dataset.scope).toBe('')
    expect(screen.getByRole('button', { name: /select sources/i })).toBeTruthy()
  })

  it('lists every source when the picker is opened', () => {
    renderPanel()
    openPicker()
    expect(screen.getAllByRole('checkbox')).toHaveLength(SOURCES.length)
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.getByText('Charlie')).toBeTruthy()
  })

  it('adds a source to the selection when its box is ticked', () => {
    const { onSelectionChange } = renderPanel({ selectedSourceIds: ['a'] })
    openPicker()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bravo' }))
    expect(onSelectionChange).toHaveBeenCalledWith(['a', 'b'])
  })

  it('removes a source when its box is unticked', () => {
    const { onSelectionChange } = renderPanel({ selectedSourceIds: ['a', 'b'] })
    openPicker()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Alpha' }))
    expect(onSelectionChange).toHaveBeenCalledWith(['b'])
  })

  it('counts the selection on the toggle', () => {
    renderPanel({ selectedSourceIds: ['a', 'b'] })
    expect(screen.getByRole('button', { name: /2 selected/i })).toBeTruthy()
  })

  it('closes the picker on Escape', () => {
    renderPanel()
    openPicker()
    expect(screen.getAllByRole('checkbox')).toHaveLength(SOURCES.length)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('handles a project with no sources at all', () => {
    renderPanel({ sources: [] })
    openPicker()
    expect(screen.getByText(/no sources in this project/i)).toBeTruthy()
  })
})

describe('NotePanel actions', () => {
  it('cannot regenerate without a selection', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: /regenerate/i }).disabled).toBe(true)
  })

  it('regenerates against the current selection', () => {
    renderPanel({ selectedSourceIds: ['a', 'c'] })
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }))
    expect(document.body.dataset.regenerated).toBe('a,c')
  })

  it('passes the selection down to the note view', () => {
    renderPanel({ selectedSourceIds: ['b'] })
    expect(screen.getByTestId('note-view').dataset.scope).toBe('b')
  })
})
