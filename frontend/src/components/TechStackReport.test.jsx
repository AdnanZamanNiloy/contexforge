import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import TechStackReport from './TechStackReport'
import * as api from '../services/api'

// The Dependency & Tech Stack view.  The scan itself is a backend concern; these
// assert the behaviour around it — which endpoint is called when, and what the
// user is shown for each outcome.

const SCAN = {
  repository: 'acme/widgets',
  summary: 'Written primarily in Python; using FastAPI; dependencies managed by pip.',
  languages: [
    { name: 'Python', kind: 'programming', files: 42, share: 0.7 },
    { name: 'YAML', kind: 'data', files: 6, share: 0.1 },
  ],
  frameworks: [{ name: 'FastAPI', kind: 'Framework', version: '0.115.0', managers: ['pip'] }],
  technologies: [
    { name: 'FastAPI', kind: 'Framework', version: '0.115.0', managers: ['pip'] },
    { name: 'pytest', kind: 'Testing', version: '8.3.0', managers: ['pip'] },
    { name: 'pip', kind: 'Package manager', version: null, managers: ['pip'] },
  ],
  package_managers: [{ name: 'pip', dependency_count: 2 }],
  dependencies: [
    {
      manager: 'pip',
      language: 'Python',
      count: 2,
      dependencies: [
        { name: 'fastapi', version: '0.115.0', scope: 'runtime', manifest: 'requirements.txt' },
        { name: 'pytest', version: null, scope: 'dev', manifest: 'requirements.txt' },
      ],
    },
  ],
  manifests: [
    {
      path: 'requirements.txt',
      manager: 'pip',
      language: 'Python',
      dependency_count: 2,
      error: null,
    },
  ],
  skipped: 0,
  manifest_count: 1,
  dependency_count: 2,
  language_count: 1,
  fingerprint: 'abc123',
  cached: false,
  elapsed_ms: 12,
  truncated: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('TechStackReport', () => {
  it('shows a project-required empty state with no project', () => {
    render(<TechStackReport projectId={null} />)
    expect(screen.getByText(/open a project to scan a repository/i)).toBeInTheDocument()
  })

  it('shows a GitHub-source empty state and calls no backend', () => {
    const get = vi.spyOn(api, 'getTechStack')
    const scan = vi.spyOn(api, 'scanTechStack')
    render(<TechStackReport projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
    expect(scan).not.toHaveBeenCalled()
  })

  it('serves a stored scan without rescanning', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const scan = vi.spyOn(api, 'scanTechStack').mockResolvedValue(SCAN)

    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/written primarily in python/i)).toBeInTheDocument()
    })
    // A stored scan must not cost a re-scan.
    expect(scan).not.toHaveBeenCalled()
    expect(screen.getByText(/cached/)).toBeInTheDocument()
  })

  it('scans when nothing is stored yet', async () => {
    vi.spyOn(api, 'getTechStack').mockRejectedValue(new Error('404'))
    const scan = vi.spyOn(api, 'scanTechStack').mockResolvedValue(SCAN)

    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith('p1', { refresh: false })
    })
    await waitFor(() => {
      expect(screen.getByText(/written primarily in python/i)).toBeInTheDocument()
    })
  })

  it('rescans on demand with refresh set', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const scan = vi.spyOn(api, 'scanTechStack').mockResolvedValue({ ...SCAN, cached: false })

    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/written primarily in python/i)).toBeInTheDocument()
    })
    await actor.click(screen.getByRole('button', { name: /rescan/i }))

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith('p1', { refresh: true })
    })
  })

  it('groups dependencies by package manager and shows versions', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(
      Array.from(document.querySelectorAll('.gv-section-title')).map((el) => el.textContent),
    ).toContain('Dependencies')
    })
    // Scoped to the dependency section: a name and version can legitimately
    // appear in both the framework chips and the dependency list.
    const table = container.querySelector('.ts-manifests')
    expect(table).not.toBeNull()
    expect(table.querySelector('.gv-subhead').textContent).toBe('pip')
    expect(table.textContent).toContain('fastapi')
    expect(table.textContent).toContain('0.115.0')
    // A dependency with no pinned version says so rather than showing a blank.
    expect(table.textContent).toContain('unpinned')
    expect(table.textContent).toContain('dev')
  })

  it('lists recognised technologies under their category, with versions', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(
        Array.from(document.querySelectorAll('.gv-section-title')).map((el) => el.textContent),
      ).toContain('Technologies')
    })
    // Grouped by category rather than one flat list: with the database, hosting,
    // CI, cloud and AI rules in play there are a dozen categories, and a single
    // list buries the one a reader is looking for.  A single category is the
    // section's aside rather than a heading of its own -- three levels of chrome
    // for one chip is chrome for its own sake.
    expect(screen.getByText('Framework')).toBeInTheDocument()

    const chips = container.querySelectorAll('.gv-chip')
    const labels = Array.from(chips).map((chip) => chip.textContent)
    expect(labels.some((label) => label.includes('FastAPI'))).toBe(true)
    expect(labels.some((label) => label.includes('pytest'))).toBe(true)
    expect(labels.some((label) => label.includes('0.115.0'))).toBe(true)
  })

  it('gives each category its own subheading when there are several', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({
      ...SCAN,
      cached: true,
      technologies: [
        { name: 'Django', kind: 'Framework', version: '5.2', managers: ['pip'] },
        { name: 'Postgres', kind: 'Database', version: null, managers: [] },
        { name: 'Vercel', kind: 'Hosting', version: null, managers: [] },
      ],
    })
    const { container } = render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(container.querySelectorAll('.ts-kind').length).toBeGreaterThan(0)
    })
    const subheads = Array.from(container.querySelectorAll('.ts-kind .gv-subhead')).map(
      (el) => el.textContent,
    )
    // Architectural categories sort ahead of build-time ones.
    expect(subheads).toEqual(['Database', 'Hosting', 'Framework'])
  })

  it('shows languages with a file count', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('Python')).toBeInTheDocument()
    })
    // YAML is a data format, so it is reported in its own section, not as a
    // language the project is written in.
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText(/config & data formats/i)).toBeInTheDocument()
  })

  it('surfaces a scan failure as a readable message', async () => {
    vi.spyOn(api, 'getTechStack').mockRejectedValue(new Error('404'))
    vi.spyOn(api, 'scanTechStack').mockRejectedValue(
      new Error('This project has no GitHub source to scan.'),
    )

    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/no github source to scan/i)
    })
  })

  it('reveals the manifests it read', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/manifests read/i)).toBeInTheDocument()
    })
    expect(screen.getByText('(1)')).toBeInTheDocument()
    await actor.click(screen.getByText(/manifests read/i))
    expect(screen.getByText('requirements.txt')).toBeInTheDocument()
  })

  it('notes when the repository was too large for a full view', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true, truncated: true })
    render(<TechStackReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText(/bounded view of its files/i)).toBeInTheDocument()
    })
  })
})

describe('TechStackReport counts', () => {
  it('pluralises the header counts', async () => {
    vi.spyOn(api, 'getTechStack').mockResolvedValue({ ...SCAN, cached: true })
    const { rerender } = render(<TechStackReport projectId="p1" />)

    await waitFor(() => {
      expect(
        Array.from(document.querySelectorAll('.gv-section-title')).map((el) => el.textContent),
      ).toContain('Dependencies')
    })
    // Singular, not "1 ecosystems" / "1 manifests".
    expect(screen.getByText('1 ecosystem')).toBeInTheDocument()
    expect(screen.queryByText(/1 ecosystems/)).not.toBeInTheDocument()

    rerender(<TechStackReport projectId="p2" />)
    vi.mocked(api.getTechStack).mockResolvedValue({
      ...SCAN,
      cached: true,
      manifest_count: 3,
      dependency_count: 1,
    })
  })
})
