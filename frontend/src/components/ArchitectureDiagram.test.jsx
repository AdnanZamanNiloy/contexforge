import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import ArchitectureDiagram from './ArchitectureDiagram'
import * as api from '../services/api'

// The Architecture Diagram view.  Mermaid is dynamically imported inside the
// component, so these tests never load the real library — they assert the
// behaviour around it: which endpoint is called, when, and what the user is told.

// The Architecture Diagram view.
//
// Mermaid is stubbed rather than really rendered.  jsdom does not implement
// SVGTextElement.getComputedTextLength(), which Mermaid's layout needs to size a
// label, so a real render throws there and leaves nothing in the DOM — that is a
// limitation of the test environment, not of the view, and real rendering is
// covered by the browser end-to-end check.  Stubbing it also lets these tests
// assert the behaviour that actually matters here: that the diagram is written
// into the host element again after a full-screen round trip replaces it.
const renderMock = vi.fn(async (id) => ({ svg: `<svg data-render-id="${id}"></svg>` }))

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: (id, source) => renderMock(id, source),
  },
}))

const DIAGRAM = {
  mermaid: 'flowchart TD\n  n_n1["API"]',
  explanation: 'A short summary.',
  node_count: 2,
  edge_count: 1,
  group_count: 1,
  repository: 'acme/widgets',
  branch: 'main',
  fingerprint: 'abc123',
  cached: false,
  elapsed_ms: 1200,
  truncated_paths: 0,
}

beforeEach(() => {
  vi.restoreAllMocks()
  renderMock.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ArchitectureDiagram', () => {
  it('shows a project-required empty state with no project', () => {
    render(<ArchitectureDiagram projectId={null} />)
    expect(screen.getByText(/open a project to map a repository/i)).toBeInTheDocument()
  })

  it('shows a GitHub-source empty state and calls no backend', () => {
    const get = vi.spyOn(api, 'getArchitecture')
    const stream = vi.spyOn(api, 'streamArchitecture')
    render(<ArchitectureDiagram projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
    expect(stream).not.toHaveBeenCalled()
  })

  it('serves a stored diagram without generating a new one', async () => {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })
    const stream = vi.spyOn(api, 'streamArchitecture').mockResolvedValue(undefined)

    render(<ArchitectureDiagram projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })
    // A cached diagram must not cost a model call.
    expect(stream).not.toHaveBeenCalled()
    expect(screen.getByText(/acme\/widgets/)).toBeInTheDocument()
    expect(screen.getByText(/cached/)).toBeInTheDocument()
  })

  it('generates when the project has nothing stored yet', async () => {
    vi.spyOn(api, 'getArchitecture').mockRejectedValue(new Error('404'))
    const stream = vi.spyOn(api, 'streamArchitecture').mockImplementation((_payload, handlers) => {
      handlers.onDiagram(DIAGRAM)
      return Promise.resolve()
    })

    render(<ArchitectureDiagram projectId="p1" />)

    await waitFor(() => {
      expect(stream).toHaveBeenCalledTimes(1)
    })
    expect(stream.mock.calls[0][0]).toMatchObject({ project_id: 'p1', refresh: false })
    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })
  })

  it('surfaces a streamed failure as a readable message', async () => {
    vi.spyOn(api, 'getArchitecture').mockRejectedValue(new Error('404'))
    vi.spyOn(api, 'streamArchitecture').mockImplementation((_payload, handlers) => {
      handlers.onError('The AI provider is at its rate limit.')
      return Promise.resolve()
    })

    render(<ArchitectureDiagram projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/rate limit/i)
    })
  })

  it('regenerates through the dedicated endpoint', async () => {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })
    const regen = vi.spyOn(api, 'regenerateArchitecture').mockImplementation((_id, handlers) => {
      handlers.onDiagram({ ...DIAGRAM, cached: false, explanation: 'Fresh summary.' })
      return Promise.resolve()
    })

    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    render(<ArchitectureDiagram projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })

    await actor.click(screen.getByRole('button', { name: /regenerate/i }))

    await waitFor(() => {
      expect(regen).toHaveBeenCalledWith('p1', expect.any(Object))
    })
    await waitFor(() => {
      expect(screen.getByText('Fresh summary.')).toBeInTheDocument()
    })
  })

  it('copies the Mermaid source to the clipboard', async () => {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })

    // userEvent.setup() installs its own clipboard stub, so the copy is read
    // back through that rather than by replacing navigator here.
    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    render(<ArchitectureDiagram projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /copy mermaid/i })).toBeInTheDocument()
    })
    await actor.click(screen.getByRole('button', { name: /copy mermaid/i }))

    await waitFor(async () => {
      expect(await navigator.clipboard.readText()).toBe(DIAGRAM.mermaid)
    })
    // The button confirms the copy rather than silently doing nothing.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument()
    })
  })

  it('refuses to render a Mermaid source carrying a script directive', async () => {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({
      ...DIAGRAM,
      mermaid: 'flowchart TD\n  n_n1["x"]\n  click n_n1 "javascript:alert(1)"',
    })

    render(<ArchitectureDiagram projectId="p1" />)

    // The payload is rejected outright rather than handed to Mermaid.
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/safely/i)
    })
    expect(screen.queryByRole('region', { name: /architecture diagram/i })).not.toBeInTheDocument()
  })

  it('reports when some node paths could not be verified', async () => {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, truncated_paths: 2 })
    render(<ArchitectureDiagram projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText(/some paths were unverified/i)).toBeInTheDocument()
    })
  })
})

describe('ArchitectureDiagram full screen', () => {
  async function renderDiagram() {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })
    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    const utils = render(<ArchitectureDiagram projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })
    return { actor, ...utils }
  }

  it('offers a full-screen control only once a diagram is on screen', async () => {
    const { rerender } = render(<ArchitectureDiagram projectId="p1" hasGithubSource={false} />)
    expect(screen.queryByRole('button', { name: /full screen/i })).not.toBeInTheDocument()

    await renderDiagram()
    expect(screen.getByRole('button', { name: /full screen/i })).toBeInTheDocument()
    rerender(<ArchitectureDiagram projectId="p2" />)
  })

  it('portals to the body so the sidebars are genuinely out of the way', async () => {
    const { actor } = await renderDiagram()

    // Rendered in place to begin with, inside its column.
    expect(document.querySelector('.ad-root')?.closest('.ad-fullscreen')).toBeNull()

    await actor.click(screen.getByRole('button', { name: /full screen/i }))

    const overlay = document.querySelector('.ad-fullscreen')
    expect(overlay).not.toBeNull()
    // The overlay is a sibling of the app root, not a descendant of the
    // three-column grid, so it can cover the whole viewport.
    expect(overlay?.parentElement).toBe(document.body)
    expect(overlay?.getAttribute('aria-modal')).toBe('true')
  })

  it('exits on the X button', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    expect(document.querySelector('.ad-fullscreen')).not.toBeNull()

    await actor.click(screen.getByRole('button', { name: /exit/i }))
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).toBeNull()
    })
  })

  it('exits on Escape', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    expect(document.querySelector('.ad-fullscreen')).not.toBeNull()

    await actor.keyboard('{Escape}')
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).toBeNull()
    })
  })

  it('releases the body scroll lock when it exits', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    expect(document.body.style.overflow).toBe('hidden')

    await actor.keyboard('{Escape}')
    await waitFor(() => {
      expect(document.body.style.overflow).not.toBe('hidden')
    })
  })

  it('keeps the diagram rendered after a full-screen round trip', async () => {
    const { actor } = await renderDiagram()
    await waitFor(() => {
      expect(document.querySelector('.ad-canvas svg')).not.toBeNull()
    })
    const rendersBefore = renderMock.mock.calls.length

    await actor.click(screen.getByRole('button', { name: /full screen/i }))

    // The portal swap hands the host a brand new element, so the render effect
    // has to run again: the SVG written into the old (now detached) node would
    // otherwise leave the full-screen surface blank.
    await waitFor(() => {
      expect(renderMock.mock.calls.length).toBeGreaterThan(rendersBefore)
    })
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen .ad-canvas svg')).not.toBeNull()
    })

    await actor.keyboard('{Escape}')
    await waitFor(() => {
      expect(document.querySelector('.ad-canvas svg')).not.toBeNull()
    })
  })

  it('hides the full-screen button while already full screen', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).not.toBeNull()
    })
    expect(screen.queryByRole('button', { name: /full screen/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /exit/i })).toBeInTheDocument()
  })
})

describe('ArchitectureDiagram full screen layout', () => {
  async function renderDiagram() {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })
    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    const utils = render(<ArchitectureDiagram projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })
    return { actor, ...utils }
  }

  it('shows the explanation in the normal view', async () => {
    await renderDiagram()
    expect(document.querySelector('.ad-explanation')).not.toBeNull()
  })

  it('drops the explanation in full screen so the diagram gets the room', async () => {
    const { actor } = await renderDiagram()
    expect(document.querySelector('.ad-explanation')).not.toBeNull()

    await actor.click(screen.getByRole('button', { name: /full screen/i }))

    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).not.toBeNull()
    })
    expect(document.querySelector('.ad-explanation')).toBeNull()

    // ...and it comes back on exit rather than being lost for the session.
    await actor.keyboard('{Escape}')
    await waitFor(() => {
      expect(document.querySelector('.ad-explanation')).not.toBeNull()
    })
  })

  it('still identifies the repository in full screen', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).not.toBeNull()
    })
    // Only the prose panel goes; the repo/nodes summary stays.
    expect(document.querySelector('.ad-fullscreen .ad-meta')?.textContent).toContain('acme/widgets')
  })
})

describe('ArchitectureDiagram full screen shell hiding', () => {
  async function renderDiagram() {
    vi.spyOn(api, 'getArchitecture').mockResolvedValue({ ...DIAGRAM, cached: true })
    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    const utils = render(
      <div className="app-layout">
        <ArchitectureDiagram projectId="p1" />
      </div>,
    )
    await waitFor(() => {
      expect(screen.getByText('A short summary.')).toBeInTheDocument()
    })
    return { actor, ...utils }
  }

  it('marks the body so the app shell is hidden, not just covered', async () => {
    const { actor } = await renderDiagram()
    expect(document.body.classList.contains('ad-fullscreen-active')).toBe(false)

    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    await waitFor(() => {
      expect(document.body.classList.contains('ad-fullscreen-active')).toBe(true)
    })

    await actor.keyboard('{Escape}')
    await waitFor(() => {
      expect(document.body.classList.contains('ad-fullscreen-active')).toBe(false)
    })
  })

  it('keeps the overlay outside the hidden shell so it stays visible', async () => {
    const { actor } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    await waitFor(() => {
      expect(document.querySelector('.ad-fullscreen')).not.toBeNull()
    })

    // The shell is display:none, and the overlay is portalled to body, so it is
    // not a descendant of anything that was hidden.
    const overlay = document.querySelector('.ad-fullscreen')
    expect(overlay?.closest('.app-layout')).toBeNull()
    expect(overlay?.parentElement).toBe(document.body)
  })

  it('cleans the body class up on unmount so a closed view cannot leave it set', async () => {
    const { actor, unmount } = await renderDiagram()
    await actor.click(screen.getByRole('button', { name: /full screen/i }))
    await waitFor(() => {
      expect(document.body.classList.contains('ad-fullscreen-active')).toBe(true)
    })

    unmount()
    expect(document.body.classList.contains('ad-fullscreen-active')).toBe(false)
    expect(document.body.style.overflow).not.toBe('hidden')
  })
})
