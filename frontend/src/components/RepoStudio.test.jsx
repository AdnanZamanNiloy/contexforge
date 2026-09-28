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
  it('renders each placeholder view without any backend', async () => {
    const { rerender } = render(<StudioView tool="architecture" />)
    expect(screen.getByText(/module map of the repository/i)).toBeInTheDocument()

    rerender(<StudioView tool="health" />)
    expect(screen.getByText('High churn')).toBeInTheDocument()

    rerender(<StudioView tool="security" />)
    expect(screen.getByText('No hardcoded secrets detected')).toBeInTheDocument()

    rerender(<StudioView tool="stack" />)
    expect(screen.getByText('Dependency & Tech Stack')).toBeInTheDocument()
  })
})
