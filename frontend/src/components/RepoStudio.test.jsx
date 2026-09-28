import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import RepoStudio, { STUDIO_TOOLS, StudioView } from './RepoStudio'

async function user() {
  const { default: userEvent } = await import('@testing-library/user-event')
  return userEvent.setup()
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RepoStudio rail', () => {
  it('renders all five repository tools with the repo name', () => {
    render(<RepoStudio repoName="owner/repo" active={null} onSelect={vi.fn()} />)

    expect(screen.getByText('owner/repo')).toBeInTheDocument()
    for (const label of [
      'Architecture Diagram',
      'Security & Quality',
      'Dependency & Tech Stack',
      'Health Score & Hotspots',
      'Repo Chat',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    // The rail itself holds no outputs — they render in the main window.
    expect(screen.queryByText(/module map of the repository/i)).not.toBeInTheDocument()
  })

  it('notifies the parent on selection and highlights the active tool', async () => {
    const onSelect = vi.fn()
    const u = await user()
    const { rerender } = render(
      <RepoStudio repoName="owner/repo" active={null} onSelect={onSelect} />,
    )

    await u.click(screen.getByRole('button', { name: 'Health Score & Hotspots' }))
    expect(onSelect).toHaveBeenCalledWith('health')

    rerender(<RepoStudio repoName="owner/repo" active="health" onSelect={onSelect} />)
    expect(screen.getByRole('button', { name: 'Health Score & Hotspots' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('routes Repo Chat to the main composer instead of a separate view', async () => {
    const onSelect = vi.fn()
    const u = await user()
    render(<RepoStudio repoName="owner/repo" active={null} onSelect={onSelect} />)

    await u.click(screen.getByRole('button', { name: 'Repo Chat' }))
    expect(onSelect).toHaveBeenCalledWith('chat')
  })

  it('exposes one tool entry per rail button', () => {
    expect(STUDIO_TOOLS.map((t) => t.id).sort()).toEqual(
      ['architecture', 'chat', 'health', 'security', 'stack'].sort(),
    )
  })
})

describe('StudioView (main window)', () => {
  it('routes the security tool to the real scan view', async () => {
    // Every Studio tool is a real generator now, and each has its own tests.
    // With no project the security view must ask for one rather than falling
    // back to a static preview of results that were never computed.
    render(<StudioView tool="security" />)
    expect(screen.getByText('Open a project to scan a repository')).toBeInTheDocument()
  })

  it('routes the architecture tool to the real diagram generator', async () => {
    // No project means nothing to map, and the generator must say so rather
    // than fall back to the old placeholder sketch.
    render(<StudioView tool="architecture" projectId={null} />)
    expect(screen.getByText(/open a project to map a repository/i)).toBeInTheDocument()
    expect(screen.queryByText(/module map of the repository/i)).not.toBeInTheDocument()
  })

  it('shows an empty state when the project has no GitHub source', async () => {
    render(<StudioView tool="architecture" projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
  })

  it('routes the stack tool to the real scanner, not the placeholder', async () => {
    render(<StudioView tool="stack" projectId={null} />)
    expect(screen.getByText(/open a project to scan a repository/i)).toBeInTheDocument()
    // The old hardcoded chips are gone.
    expect(screen.queryByText('PostgreSQL')).not.toBeInTheDocument()
    expect(screen.queryByText(/dependency graph between modules/i)).not.toBeInTheDocument()
  })

  it('shows the scanner empty state when the project has no GitHub source', async () => {
    render(<StudioView tool="stack" projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
  })
})

describe('StudioView generator routing', () => {
  it('routes the health tool to the real scanner, not the placeholder', async () => {
    render(<StudioView tool="health" projectId={null} />)
    expect(screen.getByText(/open a project to analyse a repository/i)).toBeInTheDocument()
    // The old hardcoded "82 / Good" ring and hotspot list are gone.
    expect(screen.queryByText('Good')).not.toBeInTheDocument()
    expect(screen.queryByText('High churn')).not.toBeInTheDocument()
  })

  it('shows the scanner empty state when the project has no GitHub source', async () => {
    render(<StudioView tool="health" projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
  })
})
