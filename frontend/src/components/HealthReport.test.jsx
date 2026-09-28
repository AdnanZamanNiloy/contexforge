import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import HealthReport from './HealthReport'
import * as api from '../services/api'

// The Health Score & Hotspots view. The measurement lives in the backend; these
// assert the behaviour around it — which endpoint is called when, and that the
// report states its own coverage limits rather than implying more than it knows.

const SCAN = {
  repository: 'acme/widgets',
  health: 72,
  band: 'high',
  summary: 'Health 72/100 across 12 functions in 8 indexed files, including 1 high.',
  weights: { cc: 1.0, nd: 0.8, fo: 0.6, ns: 0.7 },
  band_counts: { low: 8, moderate: 3, high: 1, critical: 0 },
  hotspots: [
    {
      name: 'tangled',
      kind: 'function',
      path: 'app/core.py',
      loc: 42,
      cc: 14,
      nd: 4,
      fo: 6,
      ns: 3,
      r_cc: 3.9,
      r_nd: 3.2,
      r_fo: 2.6,
      r_ns: 2.1,
      lrs: 8.42,
      band: 'high',
      band_label: 'High',
      test: false,
    },
    {
      name: 'UserForm',
      kind: 'class',
      path: 'app/forms.py',
      loc: 2,
      cc: 1,
      nd: 0,
      fo: 0,
      ns: 0,
      r_cc: 1,
      r_nd: 0,
      r_fo: 0,
      r_ns: 0,
      lrs: 1,
      band: 'low',
      band_label: 'Low',
      test: false,
    },
  ],
  files: [],
  largest_files: [
    { path: 'app/core.py', chars: 12345, measured: true },
    { path: 'assets/bundle.js', chars: 9000, measured: false },
  ],
  symbol_count: 12,
  file_count: 8,
  measured_languages: ['Python'],
  coverage_note:
    'Per-function risk is measured for Python only. Other files are listed by size. Change frequency is not available: no git history is indexed.',
  fingerprint: 'abc123',
  cached: false,
  elapsed_ms: 4,
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('HealthReport', () => {
  it('shows a project-required empty state with no project', () => {
    render(<HealthReport projectId={null} />)
    expect(screen.getByText(/open a project to analyse a repository/i)).toBeInTheDocument()
  })

  it('shows a GitHub-source empty state and calls no backend', () => {
    const get = vi.spyOn(api, 'getHealthScan')
    const scan = vi.spyOn(api, 'scanHealth')
    render(<HealthReport projectId="p1" hasGithubSource={false} />)
    expect(screen.getByText(/no github source in this project/i)).toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
    expect(scan).not.toHaveBeenCalled()
  })

  it('serves a stored scan without rescanning', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const scan = vi.spyOn(api, 'scanHealth').mockResolvedValue(SCAN)

    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/health 72\/100 across 12 functions/i)).toBeInTheDocument()
    })
    // A stored scan must not cost a re-measurement.
    expect(scan).not.toHaveBeenCalled()
    expect(screen.getByText(/cached/)).toBeInTheDocument()
  })

  it('scans when nothing is stored yet', async () => {
    vi.spyOn(api, 'getHealthScan').mockRejectedValue(new Error('404'))
    const scan = vi.spyOn(api, 'scanHealth').mockResolvedValue(SCAN)

    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith('p1', { refresh: false })
    })
  })

  it('rescans on demand with refresh set', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const scan = vi.spyOn(api, 'scanHealth').mockResolvedValue({ ...SCAN, cached: false })

    const { default: userEvent } = await import('@testing-library/user-event')
    const actor = userEvent.setup()
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/health 72\/100/i)).toBeInTheDocument()
    })
    await actor.click(screen.getByRole('button', { name: /rescan/i }))

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith('p1', { refresh: true })
    })
  })

  it('shows the score, its band and the band distribution', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('72')).toBeInTheDocument()
    })
    // Scoped to the ring: the header stat tiles carry other numbers, so a bare
    // query for the score would now be ambiguous.
    // The headline band follows the worst code, not the average — so "High" is
    // shown both as the ring's label and as a legend entry.
    expect(screen.getAllByText('High').length).toBeGreaterThan(0)
    for (const label of ['Low', 'Moderate', 'Critical']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    // Counts come from the band distribution, read inside the legend.
    const bands = document.querySelector('.hs-bands')
    expect(bands.textContent).toContain('8')
  })

  it('lists hotspots with their raw metrics and score', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('Hotspots')).toBeInTheDocument()
    })
    const rows = container.querySelectorAll('.hs-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('tangled')
    expect(rows[0].textContent).toContain('app/core.py')
    // The four raw metrics and the score that came from them, in one grouped
    // cell so the symbol keeps its width.
    const metrics = rows[0].querySelector('.hs-metrics-cell')
    expect(Array.from(metrics.children).map((cell) => cell.textContent)).toEqual(['14', '4', '6', '3'])
    expect(rows[0].querySelector('.hs-lrs-cell').textContent).toContain('8.42')
  })

  it('publishes the formula and weights so the score is reproducible', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/LRS =/)).toBeInTheDocument()
    })
    const formula = screen.getByText(/LRS =/).textContent
    expect(formula).toContain('0.8·ND')
    expect(formula).toContain('critical above')
  })

  it('marks unmeasured files as size-only', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('assets/bundle.js')).toBeInTheDocument()
    })
    expect(screen.getByText(/size only/)).toBeInTheDocument()
  })

  it('states its coverage limits rather than implying full coverage', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/change frequency is not available/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/measured for python only/i)).toBeInTheDocument()
  })

  it('reports honestly when nothing could be measured', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({
      ...SCAN,
      health: 100,
      band: 'low',
      symbol_count: 0,
      summary: 'No per-function risk could be measured across 4 indexed files.',
      band_counts: { low: 0, moderate: 0, high: 0, critical: 0 },
      hotspots: [],
      measured_languages: [],
    })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText(/no per-function risk could be measured/i)).toBeInTheDocument()
    })
    expect(screen.queryByText('Hotspots')).not.toBeInTheDocument()
    expect(document.querySelector('.hs-table')).toBeNull()
    // The worst-score tile falls back to a dash rather than claiming a 0.
    expect(screen.getByText('Worst LRS').previousSibling).toHaveTextContent('—')
  })

  it('surfaces a scan failure as a readable message', async () => {
    vi.spyOn(api, 'getHealthScan').mockRejectedValue(new Error('404'))
    vi.spyOn(api, 'scanHealth').mockRejectedValue(new Error('This project has no GitHub source.'))

    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/no github source/i)
    })
  })
})

describe('HealthReport unmeasured state', () => {
  it('shows "not measured" rather than a score when nothing could be measured', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({
      ...SCAN,
      health: null,
      band: 'low',
      symbol_count: 0,
      summary: 'No per-function risk could be measured across 12 indexed files.',
      band_counts: { low: 0, moderate: 0, high: 0, critical: 0 },
      hotspots: [],
    })
    render(<HealthReport projectId="p1" />)

    await waitFor(() => {
      expect(screen.getByText('Not measured')).toBeInTheDocument()
    })
    // A perfect score would be a claim the data does not support.
    expect(screen.queryByText('100')).not.toBeInTheDocument()
    expect(screen.queryByText('72')).not.toBeInTheDocument()
  })
})

describe('HealthReport presentation', () => {
  it('does not repeat the tool name that the main window already shows', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText(/health 72\/100/i)).toBeInTheDocument()
    })
    // The Studio main window renders the tool label as its own h2; repeating it
    // inside the view read as a duplicated heading.
    expect(container.querySelector('.hs-root h3')).toBeNull()
  })

  it('shows the file tail, so no path is displayed truncated', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText('Hotspots')).toBeInTheDocument()
    })
    const path = container.querySelector('.hs-hotspot-path')
    expect(path.textContent).toBe('app/core.py')
    // The full path is still available on hover.
    expect(path.getAttribute('title')).toBe('app/core.py')
  })

  it('labels whether a row is a function or a class', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText('Hotspots')).toBeInTheDocument()
    })
    // Two same-named classes in one file are otherwise indistinguishable.
    const kinds = Array.from(container.querySelectorAll('.hs-hotspot-kind')).map(
      (n) => n.textContent,
    )
    expect(kinds).toContain('function')
    expect(kinds).toContain('class')
  })

  it('collapses the largest-files list by default', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...SCAN, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText(/largest indexed files/i)).toBeInTheDocument()
    })
    const details = container.querySelector('.gv-disclosure')
    expect(details).not.toBeNull()
    expect(details.hasAttribute('open')).toBe(false)
  })

  it('hides the band legend when nothing was measured', async () => {
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({
      ...SCAN,
      health: null,
      symbol_count: 0,
      band_counts: { low: 0, moderate: 0, high: 0, critical: 0 },
      hotspots: [],
    })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(screen.getByText('Not measured')).toBeInTheDocument()
    })
    // A row of zeros is noise, not information.
    expect(container.querySelector('.hs-bands')).toBeNull()
  })

  it('gives same-named symbols in one file distinct keys', async () => {
    // One file can declare several nested `Meta` classes; identical
    // path+name keys made React drop rows and warn.
    const dupes = {
      ...SCAN,
      hotspots: [
        { ...SCAN.hotspots[0], name: 'Meta', path: 'app/forms.py' },
        { ...SCAN.hotspots[0], name: 'Meta', path: 'app/forms.py', loc: 4 },
      ],
    }
    vi.spyOn(api, 'getHealthScan').mockResolvedValue({ ...dupes, cached: true })
    const { container } = render(<HealthReport projectId="p1" />)
    await waitFor(() => {
      expect(container.querySelectorAll('.hs-table tbody tr')).toHaveLength(2)
    })
  })
})
