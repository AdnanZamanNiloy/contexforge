import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import Sidebar from './Sidebar'

// The ⋮ menu manages a source; it must never touch the workspace selection.
// These tests pin that separation: opening/using the menu leaves the selection
// callbacks untouched, and the actions it exposes are rename + remove.

const SOURCES = [
  { id: 'a', title: 'Alpha', type: 'pdf', status: 'indexed', chunks: 10 },
  { id: 'b', title: 'Bravo', type: 'github', status: 'indexed', chunks: 20 },
  { id: 'c', title: 'Charlie', type: 'web', status: 'indexed', chunks: 5 },
]

// Deliberately out of alphabetical order so sorting is observable.
const UNSORTED = [
  { id: 'c', title: 'Charlie', type: 'web', status: 'indexed' },
  { id: 'a', title: 'Alpha', type: 'pdf', status: 'indexed' },
  { id: 'b', title: 'Bravo', type: 'github', status: 'indexed' },
]

function renderSidebar(props = {}) {
  const onSelectSource = vi.fn()
  const onToggleSource = vi.fn()
  const onSelectAllSources = vi.fn()
  const onClearSourceSelection = vi.fn()
  const onRenameSource = vi.fn()
  const onDeleteSource = vi.fn()
  const utils = render(
    <MemoryRouter>
      <Sidebar
        sources={SOURCES}
        onSelectSource={onSelectSource}
        onToggleSource={onToggleSource}
        onSelectAllSources={onSelectAllSources}
        onClearSourceSelection={onClearSourceSelection}
        onRenameSource={onRenameSource}
        onDeleteSource={onDeleteSource}
        {...props}
      />
    </MemoryRouter>,
  )
  return {
    ...utils,
    onSelectSource,
    onToggleSource,
    onSelectAllSources,
    onClearSourceSelection,
    onRenameSource,
    onDeleteSource,
  }
}

// A real click is mousedown → mouseup → click; the mousedown is what dismisses
// any other open menu, so drive the full sequence.
// jsdom performs no layout, so getBoundingClientRect() is all zeros. Position
// the trigger explicitly so the flip logic can be exercised deterministically.
function mockTriggerRect(rect) {
  const spy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    top: rect.top,
    bottom: rect.bottom,
    left: 0,
    right: rect.right,
    width: 24,
    height: 24,
    x: 0,
    y: rect.top,
    toJSON: () => {},
  })
  afterEachCleanup(spy)
}

const pendingSpies = []
function afterEachCleanup(spy) {
  pendingSpies.push(spy)
}
afterEach(() => {
  pendingSpies.splice(0).forEach((spy) => spy.mockRestore())
})

function clickTrigger(name) {
  const trigger = screen.getByLabelText(`Actions for ${name}`)
  fireEvent.mouseDown(trigger)
  fireEvent.click(trigger)
}

function openMenuFor(name) {
  clickTrigger(name)
}

describe('Sidebar source action menu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('is closed until the trigger is clicked', () => {
    renderSidebar()
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('exposes rename and remove for a source', () => {
    renderSidebar()
    openMenuFor('Alpha')
    expect(screen.getByRole('menuitem', { name: /rename source/i })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: /remove source/i })).toBeTruthy()
  })

  it('does not change the selection when opened', () => {
    const { onSelectSource, onToggleSource } = renderSidebar()
    openMenuFor('Alpha')
    expect(onSelectSource).not.toHaveBeenCalled()
    expect(onToggleSource).not.toHaveBeenCalled()
  })

  it('does not change the selection when an action is used', () => {
    const { onSelectSource, onToggleSource } = renderSidebar()
    openMenuFor('Alpha')
    fireEvent.click(screen.getByRole('menuitem', { name: /rename source/i }))
    expect(onSelectSource).not.toHaveBeenCalled()
    expect(onToggleSource).not.toHaveBeenCalled()
  })

  it('calls rename with the source and closes the menu', () => {
    const { onRenameSource } = renderSidebar()
    openMenuFor('Alpha')
    fireEvent.click(screen.getByRole('menuitem', { name: /rename source/i }))
    expect(onRenameSource).toHaveBeenCalledWith(SOURCES[0])
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('calls remove with the source and closes the menu', () => {
    const { onDeleteSource } = renderSidebar()
    openMenuFor('Bravo')
    fireEvent.click(screen.getByRole('menuitem', { name: /remove source/i }))
    expect(onDeleteSource).toHaveBeenCalledWith(SOURCES[1])
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('toggles closed when the trigger is clicked again', () => {
    renderSidebar()
    openMenuFor('Alpha')
    expect(screen.queryByRole('menu')).not.toBeNull()
    clickTrigger('Alpha')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes on Escape', () => {
    renderSidebar()
    openMenuFor('Alpha')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes on an outside click', () => {
    renderSidebar()
    openMenuFor('Alpha')
    fireEvent.mouseDown(screen.getByText('Knowledge Base'))
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('only opens the menu for the clicked source', () => {
    const { onRenameSource } = renderSidebar()
    openMenuFor('Alpha')
    openMenuFor('Bravo')
    fireEvent.click(screen.getByRole('menuitem', { name: /rename source/i }))
    expect(onRenameSource).toHaveBeenCalledWith(SOURCES[1])
  })

  it('still selects a source when its row is clicked', () => {
    const { onSelectSource } = renderSidebar()
    fireEvent.click(screen.getByText('Alpha'))
    expect(onSelectSource).toHaveBeenCalledWith('a')
  })

  it('still toggles selection via the row checkbox', () => {
    const { onToggleSource } = renderSidebar()
    fireEvent.click(screen.getByLabelText('Use Alpha in the workspace'))
    expect(onToggleSource).toHaveBeenCalledWith('a')
  })

  it('marks selected sources in the row', () => {
    renderSidebar({ selectedSourceIds: ['b'] })
    const row = screen.getByText('Bravo').closest('.source-item-compact')
    expect(row.className).toContain('is-active')
  })
  it('portals the menu to document.body so no sidebar ancestor can clip it', () => {
    const { container } = renderSidebar()
    openMenuFor('Alpha')
    const menu = screen.getByRole('menu')
    // A direct child of <body>, not nested inside the row / scroller / section.
    expect(menu.parentElement).toBe(document.body)
    expect(container.contains(menu)).toBe(false)
  })

  it('positions the menu with measured viewport coordinates', () => {
    renderSidebar()
    openMenuFor('Alpha')
    const menu = screen.getByRole('menu')
    // Measured coordinates, not a CSS offset — this is what lets the menu escape
    // the sidebar's overflow:hidden ancestors.
    expect(menu.style.top).toMatch(/px$/)
    expect(menu.style.left).toMatch(/px$/)
    expect(Number.parseFloat(menu.style.top)).toBeGreaterThanOrEqual(0)
    expect(Number.parseFloat(menu.style.left)).toBeGreaterThanOrEqual(0)
  })

  it('keeps the menu inside the viewport horizontally', () => {
    renderSidebar()
    openMenuFor('Alpha')
    const menu = screen.getByRole('menu')
    const left = Number.parseFloat(menu.style.left)
    expect(left).toBeGreaterThanOrEqual(0)
    expect(left + 176).toBeLessThanOrEqual(window.innerWidth)
  })

  it('stays open when pressing down inside the portalled menu', () => {
    const { onRenameSource } = renderSidebar()
    openMenuFor('Alpha')
    const item = screen.getByRole('menuitem', { name: /rename source/i })
    // A real press fires mousedown before click.  The menu lives outside the
    // trigger's DOM subtree, so this must not be mistaken for an outside click.
    fireEvent.mouseDown(item)
    expect(screen.queryByRole('menu')).not.toBeNull()
    fireEvent.click(item)
    expect(onRenameSource).toHaveBeenCalledWith(SOURCES[0])
  })

  it('flips above the trigger when there is no room below', () => {
    // jsdom does no layout, so place the trigger explicitly near the bottom.
    mockTriggerRect({ top: 700, bottom: 724, right: 200 })
    renderSidebar()
    openMenuFor('Alpha')
    expect(screen.getByRole('menu').className).toContain('is-up')
  })

  it('opens below the trigger when there is room', () => {
    mockTriggerRect({ top: 200, bottom: 224, right: 200 })
    renderSidebar()
    openMenuFor('Alpha')
    expect(screen.getByRole('menu').className).not.toContain('is-up')
  })
  it('shows a "Select all" label with a checkbox in the section header', () => {
    renderSidebar()
    const label = screen.getByText('Select all').closest('label')
    expect(label).not.toBeNull()
    expect(label.querySelector('input[type="checkbox"]')).not.toBeNull()
  })

  it('checks "Select all" only when every source is selected', () => {
    const { rerender } = renderSidebar()
    const box = () => screen.getByLabelText('Select all sources')
    expect(box().checked).toBe(false)
    rerender(
      <MemoryRouter>
        <Sidebar sources={SOURCES} selectedSourceIds={['a']} />
      </MemoryRouter>,
    )
    expect(box().checked).toBe(false)
    rerender(
      <MemoryRouter>
        <Sidebar sources={SOURCES} selectedSourceIds={['a', 'b', 'c']} />
      </MemoryRouter>,
    )
    expect(box().checked).toBe(true)
  })

  it('selects every source when "Select all" is ticked', () => {
    const { onSelectAllSources } = renderSidebar()
    fireEvent.click(screen.getByLabelText('Select all sources'))
    expect(onSelectAllSources).toHaveBeenCalled()
  })

  it('clears the selection when "Select all" is unticked', () => {
    const onSelectAllSources = vi.fn()
    const onClearSourceSelection = vi.fn()
    render(
      <MemoryRouter>
        <Sidebar
          sources={SOURCES}
          selectedSourceIds={['a', 'b', 'c']}
          onSelectAllSources={onSelectAllSources}
          onClearSourceSelection={onClearSourceSelection}
        />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByLabelText('Select all sources'))
    expect(onClearSourceSelection).toHaveBeenCalled()
    expect(onSelectAllSources).not.toHaveBeenCalled()
  })

  it('renders the name and type on a single line, type untruncated', () => {
    renderSidebar()
    const body = screen.getByText('Alpha').closest('.source-item-body')
    expect(body.className).toContain('source-item-body')
    // The type is a sibling inside the same single-line body, not a second row.
    expect(body.querySelector('.source-item-type').textContent).toContain('PDF')
    expect(body.querySelector('.source-item-meta')).toBeNull()
  })

  it('gives every row the same structure: icon, body, checkbox', () => {
    renderSidebar()
    for (const source of SOURCES) {
      const row = screen.getByText(source.title).closest('.source-item-compact')
      expect(row.querySelector('.source-item-icon')).not.toBeNull()
      expect(row.querySelector('.source-item-body')).not.toBeNull()
      expect(row.querySelector('.source-item-check input')).not.toBeNull()
    }
  })

  it('hides the status dot for indexed sources but shows it when work is pending', () => {
    const { rerender } = render(
      <MemoryRouter>
        <Sidebar sources={[{ ...SOURCES[0], status: 'indexed' }]} />
      </MemoryRouter>,
    )
    expect(document.querySelector('.source-item-status')).toBeNull()
    rerender(
      <MemoryRouter>
        <Sidebar sources={[{ ...SOURCES[0], status: 'processing' }]} />
      </MemoryRouter>,
    )
    expect(document.querySelector('.source-item-status')).not.toBeNull()
  })
  it('orders row children icon, name, menu, checkbox', () => {
    const { container } = renderSidebar()
    const row = container.querySelector('.source-item-compact')
    const order = [...row.children].map((c) => c.className.split(' ')[0])
    // The checkbox is last so it sits flush right, and the ⋮ menu sits just
    // inside it, matching the reference row.
    expect(order).toEqual([
      'source-item-icon',
      'source-item-body',
      'source-item-menu',
      'source-item-check',
    ])
  })
  it('renders a compact toolbar above the list, not the old section heading', () => {
    const { container } = renderSidebar()
    expect(container.querySelector('.sources-toolbar')).not.toBeNull()
    // The uppercase, letter-spaced .section-title is gone from this section.
    expect(container.querySelector('.sources-section .section-title')).toBeNull()
  })

  it('drops the "My Sources" label entirely', () => {
    renderSidebar()
    expect(screen.queryByText(/my sources/i)).toBeNull()
  })

  it('keeps the section labelled for assistive tech', () => {
    const { container } = renderSidebar()
    expect(container.querySelector('.sources-section').getAttribute('aria-label')).toBe('Sources')
  })

  it('shows a sort control on the left of the toolbar', () => {
    renderSidebar()
    const trigger = screen.getByLabelText('Sort sources')
    expect(trigger).toBeTruthy()
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(trigger.querySelector('svg').getAttribute('aria-hidden')).toBe('true')
  })

  it('hides the Select all control when there are no sources', () => {
    render(
      <MemoryRouter>
        <Sidebar sources={[]} />
      </MemoryRouter>,
    )
    // The toolbar (and its sort control) still renders; only Select all is
    // conditional, since there is nothing to select.
    expect(screen.getByLabelText('Sort sources')).toBeTruthy()
    expect(screen.queryByLabelText('Select all sources')).toBeNull()
  })
  it('opens the sort popover with Recent, Title and Type', () => {
    renderSidebar()
    fireEvent.click(screen.getByLabelText('Sort sources'))
    expect(screen.getByRole('menu', { name: 'Sort sources' })).toBeTruthy()
    for (const label of ['Recent', 'Title', 'Type']) {
      expect(screen.getByRole('menuitemradio', { name: new RegExp(label) })).toBeTruthy()
    }
  })

  it('portals the sort popover to document.body', () => {
    const { container } = renderSidebar()
    fireEvent.click(screen.getByLabelText('Sort sources'))
    const menu = screen.getByRole('menu', { name: 'Sort sources' })
    expect(menu.parentElement).toBe(document.body)
    expect(container.contains(menu)).toBe(false)
  })

  it('marks Recent as the default sort', () => {
    renderSidebar()
    fireEvent.click(screen.getByLabelText('Sort sources'))
    expect(
      screen.getByRole('menuitemradio', { name: /recent/i }).getAttribute('aria-checked'),
    ).toBe('true')
  })

  it('sorts the list by title when Title is chosen', () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar sources={UNSORTED} />
      </MemoryRouter>,
    )
    const titles = () =>
      [...container.querySelectorAll('.source-item-title')].map((n) => n.textContent)
    // "Recent" keeps the order the store returned them in.
    expect(titles()).toEqual(['Charlie', 'Alpha', 'Bravo'])

    fireEvent.click(screen.getByLabelText('Sort sources'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /title/i }))
    expect(titles()).toEqual(['Alpha', 'Bravo', 'Charlie'])
  })

  it('sorts the list by type and breaks ties by title', () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar sources={UNSORTED} />
      </MemoryRouter>,
    )
    const titles = () =>
      [...container.querySelectorAll('.source-item-title')].map((n) => n.textContent)

    fireEvent.click(screen.getByLabelText('Sort sources'))
    expect(screen.getByRole('menuitemradio', { name: /type/i }).getAttribute('aria-checked')).toBe(
      'false',
    )
    fireEvent.click(screen.getByRole('menuitemradio', { name: /type/i }))
    // GitHub < PDF < Web by SOURCE_TYPE_LABEL, then alphabetical within a type.
    expect(titles()).toEqual(['Bravo', 'Alpha', 'Charlie'])

    // Re-opening shows Type as the checked option and Recent as unchecked.
    fireEvent.click(screen.getByLabelText('Sort sources'))
    expect(screen.getByRole('menuitemradio', { name: /type/i }).getAttribute('aria-checked')).toBe(
      'true',
    )
    expect(
      screen.getByRole('menuitemradio', { name: /recent/i }).getAttribute('aria-checked'),
    ).toBe('false')
  })

  it('closes the sort popover after choosing an option', () => {
    renderSidebar()
    fireEvent.click(screen.getByLabelText('Sort sources'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /title/i }))
    expect(screen.queryByRole('menu', { name: 'Sort sources' })).toBeNull()
  })

  it('closes the sort popover on Escape', () => {
    renderSidebar()
    fireEvent.click(screen.getByLabelText('Sort sources'))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu', { name: 'Sort sources' })).toBeNull()
  })

  it('keeps the selection intact when the order changes', () => {
    const onToggleSource = vi.fn()
    const { container } = render(
      <MemoryRouter>
        <Sidebar sources={UNSORTED} selectedSourceIds={['c']} onToggleSource={onToggleSource} />
      </MemoryRouter>,
    )
    const activeRow = () =>
      container.querySelector('.source-item-compact.is-active .source-item-title')?.textContent
    expect(activeRow()).toBe('Charlie')

    fireEvent.click(screen.getByLabelText('Sort sources'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /type/i }))
    // Sorting is display-only: the same source stays selected.
    expect(activeRow()).toBe('Charlie')
  })
  it('no longer renders the scope hint text', () => {
    renderSidebar({ selectedSourceIds: ['a'] })
    expect(screen.queryByText(/chat and mind map use/i)).toBeNull()
  })

  it('renders no hint for a multi-source selection either', () => {
    renderSidebar({ selectedSourceIds: ['a', 'b', 'c'] })
    expect(screen.queryByText(/these 3 sources/i)).toBeNull()
  })
})
