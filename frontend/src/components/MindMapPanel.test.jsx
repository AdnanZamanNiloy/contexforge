import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

import MindMapPanel from './MindMapPanel'

// Full screen has to escape the workspace's three-column grid (sidebar · main ·
// evidence rail) to cover the whole viewport.  It does that by portalling to
// document.body.  These tests pin that it mounts there, that the dialog is
// reachable while active, and that unmounting restores everything — including
// the body scroll lock, which must not be left behind.

const SOURCES = [
  { id: 'a', title: 'Alpha', type: 'pdf' },
  { id: 'b', title: 'Bravo', type: 'github' },
]

// The canvas talks to the API on mount; keep it inert here.
vi.mock('./MindMapCanvas', () => ({
  default: ({ isFullscreen }) => (
    <div data-testid="canvas" data-fullscreen={String(Boolean(isFullscreen))} />
  ),
}))

function renderPanel(props = {}) {
  const onSelectionChange = vi.fn()
  const utils = render(
    <MindMapPanel
      sources={SOURCES}
      selectedIds={['a']}
      onSelectionChange={onSelectionChange}
      {...props}
    />,
  )
  return { ...utils, onSelectionChange }
}

function enterFullscreen() {
  fireEvent.click(screen.getByRole('button', { name: /full screen/i }))
}

describe('MindMapPanel full screen', () => {
  beforeEach(() => {
    document.body.style.overflow = ''
  })

  afterEach(() => {
    document.body.style.overflow = ''
  })

  it('renders inline in the workspace by default', () => {
    renderPanel()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByTestId('canvas').dataset.fullscreen).toBe('false')
    expect(document.querySelector('.mindmap-panel').className).not.toContain('is-fullscreen')
  })

  it('portals the panel into document.body when full screen is on', () => {
    renderPanel()
    enterFullscreen()
    // The overlay is a direct child of <body>, not nested inside the panel's
    // original position in the workspace grid.
    const overlay = document.querySelector('body > .mindmap-fullscreen')
    expect(overlay).not.toBeNull()
  })

  it('marks the panel full screen and flags the canvas', () => {
    renderPanel()
    enterFullscreen()
    expect(document.querySelector('.mindmap-panel').className).toContain('is-fullscreen')
    expect(screen.getByTestId('canvas').dataset.fullscreen).toBe('true')
  })

  it('exposes the overlay as a modal dialog labelled Mind map', () => {
    renderPanel()
    enterFullscreen()
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-label')).toBe('Mind map')
  })

  it('locks page scroll while full screen is active', () => {
    renderPanel()
    expect(document.body.style.overflow).toBe('')
    enterFullscreen()
    expect(document.body.style.overflow).toBe('hidden')
  })

  it('exits with the button and restores the inline layout', () => {
    renderPanel()
    enterFullscreen()
    fireEvent.click(screen.getByRole('button', { name: /exit full screen/i }))
    expect(document.querySelector('body > .mindmap-fullscreen')).toBeNull()
    expect(document.querySelector('.mindmap-panel').className).not.toContain('is-fullscreen')
    expect(screen.getByTestId('canvas').dataset.fullscreen).toBe('false')
  })

  it('releases the scroll lock on exit', () => {
    document.body.style.overflow = 'scroll'
    renderPanel()
    enterFullscreen()
    fireEvent.click(screen.getByRole('button', { name: /exit full screen/i }))
    expect(document.body.style.overflow).toBe('scroll')
  })

  it('exits with Escape', () => {
    renderPanel()
    enterFullscreen()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(document.querySelector('body > .mindmap-fullscreen')).toBeNull()
    expect(document.body.style.overflow).toBe('')
  })

  it('restores the previous scroll value when the panel unmounts while full screen', () => {
    document.body.style.overflow = 'auto'
    const { unmount } = renderPanel()
    enterFullscreen()
    expect(document.body.style.overflow).toBe('hidden')
    // Navigating away mid-fullscreen must not strand the page unscrollable.
    act(() => unmount())
    expect(document.body.style.overflow).toBe('auto')
  })

  it('keeps the scope picker usable in full screen', () => {
    renderPanel()
    enterFullscreen()
    fireEvent.click(screen.getByRole('button', { name: /1 source/i }))
    expect(document.querySelector('.mindmap-scope-menu')).not.toBeNull()
    fireEvent.click(screen.getByLabelText('Bravo'))
    expect(screen.getByTestId('canvas')).toBeTruthy()
  })

  it('closes the scope picker on Escape along with full screen', () => {
    renderPanel()
    enterFullscreen()
    fireEvent.click(screen.getByRole('button', { name: /1 source/i }))
    expect(document.querySelector('.mindmap-scope-menu')).not.toBeNull()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(document.querySelector('.mindmap-scope-menu')).toBeNull()
    expect(document.querySelector('body > .mindmap-fullscreen')).toBeNull()
  })
})
