import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { useEffect } from 'react'

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

// The canvas talks to the API on mount; keep it inert here. `canvasBusy` lets a
// test stand in for a canvas that is mid-request, which is the only way to see
// the panel's Regenerate button in its working state.
const { canvasBusy } = vi.hoisted(() => ({ canvasBusy: { current: false } }))

vi.mock('./MindMapCanvas', () => ({
  // Named, not an anonymous arrow: rules-of-hooks cannot recognise a hook inside
  // a function assigned to an object property as a component.
  default: function MockMindMapCanvas({ isFullscreen, onBusyChange }) {
    useEffect(() => {
      onBusyChange?.(canvasBusy.current)
    }, [onBusyChange])
    return <div data-testid="canvas" data-fullscreen={String(Boolean(isFullscreen))} />
  },
}))

function renderPanel(props = {}) {
  const onSourceChange = vi.fn()
  const utils = render(
    <MindMapPanel sources={SOURCES} sourceId="a" onSourceChange={onSourceChange} {...props} />,
  )
  return { ...utils, onSourceChange }
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
})

describe('MindMapPanel source selection', () => {
  it('requires a source and starts on the placeholder', () => {
    renderPanel({ sourceId: '' })
    const select = screen.getByLabelText(/select the source this mind map is built from/i)
    expect(select).toHaveValue('')
    expect(screen.getByRole('option', { name: /select a source/i })).toBeInTheDocument()
  })

  it('disables Regenerate until a source is chosen', () => {
    renderPanel({ sourceId: '' })
    expect(screen.getByRole('button', { name: /regenerate/i })).toBeDisabled()
  })

  it('reports the chosen source and enables Regenerate', () => {
    const { onSourceChange } = renderPanel()
    const select = screen.getByLabelText(/select the source this mind map is built from/i)
    fireEvent.change(select, { target: { value: 'b' } })
    expect(onSourceChange).toHaveBeenCalledWith('b')
    expect(screen.getByRole('button', { name: /regenerate/i })).not.toBeDisabled()
  })
})

// Regenerate used to be silent. The work happens in the canvas child while the
// previous map is still on screen, so the canvas's own loading branch was never
// reached and the button gave no sign anything was running — it also stayed
// enabled, so repeated clicks piled up requests.
describe('Regenerate busy state', () => {
  beforeEach(() => {
    canvasBusy.current = false
  })

  it('shows progress and disables itself while the canvas is busy', async () => {
    canvasBusy.current = true
    renderPanel()

    const button = screen.getByRole('button', { name: /Regenerat/i })
    await act(async () => {
      await Promise.resolve()
    })

    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button.textContent).toMatch(/Regenerating/)
    // The spinner is decorative; the label carries the meaning.
    expect(document.querySelector('.btn-spinner')).toBeTruthy()
  })

  it('is live again once the canvas reports it is free', () => {
    renderPanel()

    const button = screen.getByRole('button', { name: /Regenerat/i })
    expect(button).not.toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'false')
    expect(button.textContent).toMatch(/^Regenerate/)
  })
})
