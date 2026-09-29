import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import SecurityReport from './SecurityReport'
import * as api from '../services/api'

// The Security & Quality view.  The scan itself is a backend concern; these
// assert the behaviour around it and, more importantly, that the report does
// not overstate what it knows -- a security report that implies total coverage
// is trusted for exactly the cases it cannot see.

const SCAN = {
  repository: 'acme/widgets',
  summary: '2 high and 1 medium issues found across 42 scanned files, including 1 dependency with published advisories.',
  findings: [
    {
      id: 'advisory:GHSA-45hq-cxwh-f6vc',
      title: 'pillow 11.3.0 — GHSA-45hq-cxwh-f6vc',
      severity: 'high',
      category: 'Vulnerable dependency',
      detail: 'Fixed in 12.3.0.',
      location: 'pillow',
      line: null,
      reference: 'https://osv.dev/vulnerability/GHSA-45hq-cxwh-f6vc',
      source: 'dependency',
      confidence: 'high',
      cwe: 'CWE-789',
      snippet: '',
      advisory_id: 'GHSA-45hq-cxwh-f6vc',
    },
    {
      id: 'github-token',
      title: 'GitHub token',
      severity: 'high',
      category: 'Secrets',
      detail: 'A credential-shaped value is committed to the repository.',
      location: 'app/config.py',
      line: 12,
      reference: '',
      source: 'secret',
      confidence: 'high',
      cwe: 'CWE-798',
      snippet: 'ghp_******89',
    },
    {
      id: 'python-weak-hash',
      title: 'Weak hash algorithm',
      severity: 'medium',
      category: 'Cryptography',
      detail: 'md5 and sha1 are broken for signatures and passwords.',
      location: 'app/auth.py',
      line: 40,
      reference: '',
      source: 'code',
      confidence: 'medium',
      cwe: 'CWE-327',
      snippet: 'hashlib.md5(data)',
    },
  ],
  finding_count: 3,
  counts: { high: 2, medium: 1 },
  worst_severity: 'high',
  by_category: [
    { category: 'Vulnerable dependency', count: 1, worst_severity: 'high' },
    { category: 'Secrets', count: 1, worst_severity: 'high' },
    { category: 'Cryptography', count: 1, worst_severity: 'medium' },
  ],
  code: { engine: 'ast-grep', files_scanned: 42, files_available: 42, languages: { python: 42 }, finding_count: 2 },
  dependencies: { checked: 18, vulnerable: 1, unchecked: 3, finding_count: 1 },
  quality: [
    { id: 'ci', title: 'Continuous integration', state: 'ok', detail: 'A CI workflow is committed.' },
    { id: 'lockfile', title: 'Dependency lockfile', state: 'warn', detail: 'No lockfile: installs are not reproducible.' },
  ],
  gate_count: 2,
  limitations: ['Patterns are matched within a single file. A value that reaches a dangerous function through a helper in another file is not traced.'],
  truncated: false,
  fingerprint: 'abc',
  cached: true,
  elapsed_ms: 0,
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('SecurityReport', () => {
  it('shows the summary, the counts and every finding', async () => {
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue({ ...SCAN })
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => {
      expect(screen.getByText(/2 high and 1 medium/i)).toBeInTheDocument()
    })
    expect(document.querySelector('.gv-section-title').textContent).toBe('Findings')
    // A code pattern, a secret and an advisory are all present and distinguishable.
    expect(screen.getByText('Weak hash algorithm')).toBeInTheDocument()
    expect(screen.getByText('GitHub token')).toBeInTheDocument()
    // The advisory id appears in its title and again as the link to its record.
    expect(screen.getAllByText(/GHSA-45hq-cxwh-f6vc/).length).toBeGreaterThan(0)
    // Path and line are rendered together, so the location is one string.
    expect(screen.getByText('app/auth.py:40')).toBeInTheDocument()
  })

  it('shows the file and line a code finding is on', async () => {
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue({ ...SCAN })
    const { container } = render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByText('Weak hash algorithm')).toBeInTheDocument())
    // Path and line are joined, so a reader can go straight to the code.
    expect(container.textContent).toContain('app/auth.py:40')
  })

  it('links an advisory to its OSV record', async () => {
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue({ ...SCAN })
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByText('GHSA-45hq-cxwh-f6vc')).toBeInTheDocument())
    const link = screen.getByRole('link', { name: /GHSA-45hq-cxwh-f6vc/ })
    expect(link).toHaveAttribute('href', 'https://osv.dev/vulnerability/GHSA-45hq-cxwh-f6vc')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('states what the scan did not do', async () => {
    // The most important assertion in the file: a report that hid its blind
    // spot would be trusted for the cross-file cases it cannot see.
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue({ ...SCAN })
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByText(/What this scan did not do/i)).toBeInTheDocument())
    expect(screen.getByText(/not traced/i)).toBeInTheDocument()
  })

  it('presents quality gates as observations rather than findings', async () => {
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue({ ...SCAN })
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByText('Quality gates')).toBeInTheDocument())
    // The aside states that these are observations, not defects, and it is the
    // reason a reader should not read a missing gate as a vulnerability.
    expect(screen.getByText(/facts about the project, not defects/i)).toBeInTheDocument()
    expect(screen.getByText('Continuous integration')).toBeInTheDocument()
    expect(screen.getByText('Dependency lockfile')).toBeInTheDocument()
  })

  it('does not claim a clean result when nothing was found', async () => {
    const clean = {
      ...SCAN,
      findings: [],
      finding_count: 0,
      counts: {},
      worst_severity: 'unknown',
      by_category: [],
      summary: 'Nothing flagged across 42 scanned files.',
    }
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue(clean)
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByText(/Nothing flagged across 42/)).toBeInTheDocument())
    // A clean report and an absent scanner look identical; the wording says which.
    expect(screen.getByText(/not a guarantee/i)).toBeInTheDocument()
  })

  it('caps the visible findings and offers the rest', async () => {
    const many = {
      ...SCAN,
      findings: Array.from({ length: 30 }, (_, i) => ({
        ...SCAN.findings[2],
        id: `f${i}`,
        title: `Finding ${i}`,
        location: `app/f${i}.py`,
        line: i + 1,
      })),
      finding_count: 30,
    }
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue(many)
    const { container } = render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(document.querySelector('.gv-section-title').textContent).toBe('Findings'))
    expect(container.querySelectorAll('.sec-finding')).toHaveLength(25)
    expect(screen.getByRole('button', { name: /Show 5 more/i })).toBeInTheDocument()
  })

  it('shows an unrated advisory as unrated rather than low', async () => {
    const unknown = {
      ...SCAN,
      findings: [{ ...SCAN.findings[0], severity: 'unknown' }],
      counts: { unknown: 1 },
      worst_severity: 'unknown',
    }
    vi.spyOn(api, 'getSecurityScan').mockResolvedValue(unknown)
    const { container } = render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(document.querySelector('.gv-section-title').textContent).toBe('Findings'))
    expect(container.querySelector('.sec-sev').className).toContain('is-unknown')
  })

  it('prompts for a scan when none is stored', async () => {
    vi.spyOn(api, 'getSecurityScan').mockRejectedValue(new Error('404'))
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Rescan/i })).toBeInTheDocument()
    })
    // A 404 is an ordinary state, not an error to shout about.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('surfaces a scan failure', async () => {
    vi.spyOn(api, 'getSecurityScan').mockRejectedValue(new Error('404'))
    vi.spyOn(api, 'scanSecurity').mockRejectedValue(new Error('The security scan timed out.'))
    render(<SecurityReport projectId="p1" sourceId="repo:a/x" />)

    await waitFor(() => expect(screen.getByRole('button', { name: /Rescan/i })).toBeInTheDocument())
    screen.getByRole('button', { name: /Rescan/i }).click()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/timed out/i))
  })

  it('asks for a GitHub source before scanning', async () => {
    render(<SecurityReport projectId="p1" hasGithubSource={false} sourceId="repo:a/x" />)
    expect(screen.getByText(/No GitHub source in this project/i)).toBeInTheDocument()
  })

  it('asks for a project before scanning', () => {
    render(<SecurityReport projectId="" />)
    expect(screen.getByText(/Open a project to scan a repository/i)).toBeInTheDocument()
  })
})
