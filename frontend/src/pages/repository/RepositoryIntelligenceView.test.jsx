// Smoke tests for Repository Intelligence. These render the shell and each
// capability view against a realistic analysis bundle so a regression in the
// data shape or a broken sub-view fails loudly rather than at runtime.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import RepositoryIntelligenceView from './RepositoryIntelligenceView'

vi.mock('../../services/api', () => ({
  getRepositoryDependencies: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
  repositoryDataFlow: vi.fn().mockResolvedValue({}),
}))

const analysis = {
  repository: {
    owner: 'acme',
    name: 'widgets',
    fullName: 'acme/widgets',
    visibility: 'public',
    branch: 'main',
    language: 'Python',
    files: 128,
    modules: 22,
    commits: 940,
    contributors: 12,
    branches: 4,
    pullRequests: 31,
    issues: 7,
    lastAnalyzed: '2026-09-20T10:00:00Z',
  },
  health: {
    score: 82,
    dimensions: [{ label: 'Complexity', value: 74, tone: 'good', detail: 'ok' }],
  },
  rankedModules: [{ name: 'core/engine.py', value: 91, reason: 'churn' }],
  activity: [
    {
      id: 'a1',
      hash: 'abc1234',
      message: 'Fix parser',
      time: '2026-09-20T09:00:00Z',
      author: 'ada',
      kind: 'commit',
    },
  ],
  architecture: {
    nodes: [
      { id: 'repo', label: 'acme/widgets', kind: 'repo', x: 0, y: 0 },
      { id: 'area', label: 'core/', kind: 'area', x: 60, y: 80 },
      {
        id: 'mod',
        label: 'engine',
        kind: 'module',
        x: 100,
        y: 160,
        meta: { path: 'core/engine.py', files: 3, deps: 2, dependents: 4, risk: 'High', loc: 1200 },
      },
    ],
    edges: [
      { source: 'repo', target: 'area', kind: 'contains' },
      { source: 'area', target: 'mod', kind: 'contains' },
    ],
  },
  dependencies: { nodes: [], edges: [] },
  gitHistory: {
    range: '30 days',
    timeline: [{ week: 'W1', commits: 5 }],
    fileChurn: [{ name: 'core/engine.py', value: 12 }],
    branches: [{ name: 'main', commits: 900, color: '#7aa2f7', active: true }],
    commits: [
      {
        hash: 'abc1234',
        message: 'Fix parser',
        author: 'ada',
        time: '2026-09-20T09:00:00Z',
        inserts: 10,
        deletes: 2,
      },
    ],
  },
  ownership: {
    contributors: [{ name: 'ada', commits: 500, percent: 55, color: '#7aa2f7' }],
    modules: [
      {
        name: 'core/engine.py',
        owner: 'ada',
        percent: 60,
        files: 3,
        contributors: [{ name: 'ada', commits: 60, percent: 60, color: '#7aa2f7' }],
      },
    ],
    concentration: { top1: 55, top3: 80, busFactor: 2, risk: 'Medium' },
  },
  changeImpact: {
    selection: 'core/engine.py',
    estimated: {
      affectedFiles: 4,
      affectedModules: 2,
      affectedApis: 1,
      affectedTests: 3,
      affectedDependencies: 2,
    },
    risk: 'High',
    // Blast-radius nodes intentionally carry no coordinates: the backend can
    // return them without x/y and the graph must still lay them out rather than
    // emit translate(null,null).
    blastRadius: {
      nodes: [
        { id: 'n1', label: 'api', direct: true, x: null, y: null },
        { id: 'n2', label: 'db', direct: false, x: null, y: null },
      ],
      edges: [{ source: 'n1', target: 'n2', kind: 'calls' }],
    },
    nodes: [
      {
        id: 'n1',
        label: 'api',
        files: 2,
        modules: 1,
        apis: 1,
        tests: 1,
        risk: 'High',
        direct: true,
      },
    ],
  },
}

describe('RepositoryIntelligenceView', () => {
  it('renders all six capability tabs and the default architecture view', () => {
    render(<RepositoryIntelligenceView analysis={analysis} analysisId="r1" reanalyze={() => {}} />)
    const tablist = screen.getByRole('tablist', { name: /repository intelligence views/i })
    expect(tablist.querySelectorAll('[role="tab"]')).toHaveLength(6)
    expect(screen.getByText('Node inspector')).toBeInTheDocument()
  })

  it('flattens the architecture to two rows: repository root and files', () => {
    const { container } = render(
      <RepositoryIntelligenceView analysis={analysis} analysisId="r1" reanalyze={() => {}} />,
    )
    const nodeEls = [...container.querySelectorAll('.graph-node')]
    const labels = nodeEls.map((n) => n.querySelector('.graph-node-label')?.textContent)
    expect(labels).toEqual(['acme/widgets', 'engine'])
    // Exactly two distinct y positions: root row + file row.
    const rows = new Set(nodeEls.map((n) => n.getAttribute('transform')?.match(/,[^)]+/)?.[0]))
    expect(rows.size).toBe(2)
    // Legend names only the two layers.
    expect(container.querySelector('.rv-legend')?.textContent).toBe('RepositoryFile')
  })

  it('surfaces a retry affordance on error', () => {
    render(
      <RepositoryIntelligenceView
        analysis={null}
        analysisId={null}
        reanalyze={() => {}}
        error="boom"
      />,
    )
    expect(screen.getByText(/repository analysis failed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry analysis/i })).toBeInTheDocument()
  })

  // Each tab is identified by content unique to that view rather than a title
  // block, since the views no longer render their own headers.
  const TABS = [
    ['Architecture', /node inspector/i],
    ['Dependencies', /no source dependencies found/i],
    ['Data Flow', /no executable flow detected/i],
    ['Git History', /commit activity/i],
    ['Ownership', /bus factor/i],
    ['Change Impact', /blast radius|risk:/i],
  ]

  it.each(TABS)('renders the %s view without crashing', async (tabLabel, marker) => {
    render(<RepositoryIntelligenceView analysis={analysis} analysisId="r1" reanalyze={() => {}} />)
    fireEvent.click(screen.getByRole('tab', { name: tabLabel }))
    expect(await screen.findByText(marker)).toBeInTheDocument()
  })

  it('lays out graph nodes that arrive without coordinates', () => {
    const { container } = render(
      <RepositoryIntelligenceView analysis={analysis} analysisId="r1" reanalyze={() => {}} />,
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Change Impact' }))
    const transforms = [...container.querySelectorAll('.graph-node')].map((n) =>
      n.getAttribute('transform'),
    )
    expect(transforms.length).toBeGreaterThan(0)
    transforms.forEach((t) => expect(t).not.toMatch(/null|NaN|undefined/))
  })
})
