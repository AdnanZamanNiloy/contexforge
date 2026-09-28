import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import ArchitectureDiagram from './ArchitectureDiagram'
import * as api from '../services/api'

// The Architecture Diagram view.  Mermaid is dynamically imported inside the
// component, so these tests never load the real library — they assert the
// behaviour around it: which endpoint is called, when, and what the user is told.

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
