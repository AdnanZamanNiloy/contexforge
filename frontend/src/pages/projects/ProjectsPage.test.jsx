import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ProjectsPage from './ProjectsPage'

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function mockProjectsFetch(projects) {
  const fetchMock = vi.fn(async (url) => {
    if (String(url).endsWith('/projects')) {
      return { ok: true, status: 200, json: async () => ({ projects, total: projects.length }) }
    }
    return { ok: true, status: 200, json: async () => ({}) }
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('ProjectsPage', () => {
  it('renders the library with real project cards and metadata', async () => {
    mockProjectsFetch([
      {
        id: 'proj_1',
        name: 'AI Research',
        description: 'Agents and evals',
        category: 'Research',
        cover: 'aurora',
        source_ids: ['s1'],
        source_count: 24,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_opened_at: new Date().toISOString(),
      },
    ])

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your projects/i })).toBeInTheDocument()
    })
    expect(screen.getByText('AI Research')).toBeInTheDocument()
    expect(screen.getByText(/24 sources/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /new project/i })).toBeInTheDocument()
  })

  it('shows the elegant empty state when there are no projects', async () => {
    mockProjectsFetch([])

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/your research starts here/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /create your first project/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /browse templates/i })).toBeInTheDocument()
  })

  it('marks Projects as the active nav item and links to Model Center', async () => {
    mockProjectsFetch([])

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /projects/i, current: 'page' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /model center/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /search projects/i })).not.toBeInTheDocument()
  })
})
