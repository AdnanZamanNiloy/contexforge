import { useCallback, useEffect, useState } from 'react'

import { getSecurityScan, scanSecurity } from '../services/api'
import ToolSourcePicker from './ToolSourcePicker'

// The Security & Quality view.
//
// Three kinds of evidence, kept visually apart because they do not carry the
// same weight and a reader needs to tell them apart at a glance:
//
//   * a code pattern or a credential shape, with a file and a line;
//   * a published advisory for a version the repository actually declares;
//   * a repository gate -- no CI, no lockfile, no licence.
//
// The last is an observation, not a defect, and is presented as a checklist
// rather than as a count.  Presenting "no CI" as a security finding is how a
// report gets ignored.
//
// `limitations` is rendered, not hidden.  This scan matches patterns within one
// file and does not trace data across files, so a value that reaches a dangerous
// function through a helper elsewhere is invisible to it.  Saying so is what
// makes the findings worth reading: a scanner that implied total coverage would
// be trusted for precisely the cases it cannot see.
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'unknown']

const MAX_VISIBLE = 25

function ShieldIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3 5 6v6c0 4.5 3 8 7 9 4-1 7-4.5 7-9V6z" />
    </svg>
  )
}

function severityTone(severity) {
  if (severity === 'critical' || severity === 'high') return 'is-high'
  if (severity === 'medium') return 'is-medium'
  if (severity === 'low') return 'is-low'
  return 'is-unknown'
}

function FindingRow({ finding }) {
  const where = finding.line ? `${finding.location}:${finding.line}` : finding.location
  // A dependency finding's title already reads `pillow 11.3.0 — GHSA-…`, so
  // repeating `pillow` on a line of its own added a row per advisory for
  // nothing. The location is only worth its own line when it says something the
  // title does not: a file and a line number.
  const showWhere = Boolean(finding.line) || !finding.title.startsWith(finding.location || '\u0000')
  return (
    <li className={`sec-finding ${severityTone(finding.severity)}`}>
      <span className={`sec-sev ${severityTone(finding.severity)}`}>{finding.severity}</span>
      <div className="sec-finding-body">
        <p className="sec-finding-title">
          {finding.title}
          {finding.cwe ? <em className="sec-cwe">{finding.cwe}</em> : null}
        </p>
        {finding.detail ? <p className="sec-finding-detail">{finding.detail}</p> : null}
        {showWhere ? (
          <p className="sec-finding-where">
            <code>{where}</code>
            {finding.snippet ? <span className="sec-snippet">{finding.snippet}</span> : null}
          </p>
        ) : null}
        {finding.reference ? (
          <a className="sec-ref" href={finding.reference} target="_blank" rel="noreferrer">
            {finding.advisory_id || finding.reference}
          </a>
        ) : null}
      </div>
    </li>
  )
}

function SeveritySummary({ counts, worstSeverity }) {
  const present = SEVERITIES.filter((severity) => counts?.[severity])
  if (!present.length) return null
  return (
    <div className="sec-counts" role="list" aria-label="Findings by severity">
      {present.map((severity) => (
        <span key={severity} role="listitem" className={`sec-count ${severityTone(severity)}`}>
          <strong>{counts[severity]}</strong> {severity}
        </span>
      ))}
      <span className={`sec-count ${severityTone(worstSeverity)}`}>
        <strong>Worst</strong> {worstSeverity}
      </span>
    </div>
  )
}

function QualityChecklist({ gates }) {
  if (!gates?.length) return null
  return (
    <section className="gv-section">
      <div className="gv-section-head">
        <h4 className="gv-section-title">Quality gates</h4>
        <span className="gv-section-aside">facts about the project, not defects</span>
      </div>
      <ul className="sec-gates">
        {gates.map((gate) => (
          <li key={gate.id} className={`sec-gate is-${gate.state}`}>
            <span className="sec-gate-dot" aria-hidden="true" />
            <span className="sec-gate-title">{gate.title}</span>
            <span className="sec-gate-detail">{gate.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function SecurityReport({
  projectId,
  hasGithubSource = true,
  sourceId = '',
  sources = [],
  onSourceChange,
}) {
  const [scan, setScan] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(async () => {
    // A source must be explicitly selected before a tool runs.
    if (!projectId || !sourceId) return
    setStatus('loading')
    setError('')
    try {
      setScan(await getSecurityScan(projectId, sourceId))
      setStatus('ready')
    } catch {
      // A 404 just means this project/source has not been scanned yet, which is
      // an ordinary state rather than an error worth shouting about.
      setScan(null)
      setStatus('idle')
    }
  }, [projectId, sourceId])

  // Switching sources swaps to that source's stored scan (or an empty state);
  // each source keeps its own result.  Nothing happens until a source is chosen.
  useEffect(() => {
    setScan(null)
    if (!sourceId) {
      setStatus('idle')
      return
    }
    if (projectId) load()
  }, [projectId, sourceId, load])

  const run = useCallback(
    async (refresh = false) => {
      // A source must be explicitly selected before a tool runs.
      if (!projectId || !sourceId) return
      setStatus('loading')
      setError('')
      try {
        setScan(await scanSecurity(projectId, { sourceId, refresh }))
        setStatus('ready')
      } catch (err) {
        setError(err?.message || 'The security scan failed.')
        setStatus('error')
      }
    },
    [projectId, sourceId],
  )

  if (!projectId) {
    return (
      <div className="sec-root">
        <div className="sec-stage">
          <ShieldIcon />
          <p className="sec-stage-title">Open a project to scan a repository</p>
        </div>
      </div>
    )
  }

  if (!hasGithubSource) {
    return (
      <div className="sec-root">
        <div className="sec-stage">
          <ShieldIcon />
          <p className="sec-stage-title">No GitHub source in this project</p>
          <p className="sec-stage-note">
            Attach a GitHub repository to the project and it will be indexed. The scan then reads
            its source and its manifests.
          </p>
        </div>
      </div>
    )
  }

  // A source must be chosen before the tool can run.
  if (!sourceId) {
    return (
      <div className="sec-root">
        <div className="gv-band sec-head">
          <div className="gv-id">
            <span className="gv-id-repo">Repository</span>
          </div>
          <div className="sec-head-right">
            <ToolSourcePicker sources={sources} value={sourceId} onChange={onSourceChange} />
          </div>
        </div>
        <div className="sec-stage">
          <ShieldIcon />
          <p className="sec-stage-title">Select a source to scan</p>
          <p className="sec-stage-note">
            Choose one of this project's sources to scan its code and manifests.
          </p>
        </div>
      </div>
    )
  }

  const findings = scan?.findings || []
  const visible = showAll ? findings : findings.slice(0, MAX_VISIBLE)
  const hidden = findings.length - visible.length

  return (
    <div className="sec-root">
      <div className="gv-band sec-head">
        <div className="gv-id">
          <span className="gv-id-repo">{scan?.repository || 'Repository'}</span>
          <span className="gv-id-note">
            {scan?.cached ? 'cached scan' : 'fresh scan'}
            {scan?.code?.files_scanned ? ` · ${scan.code.files_scanned} files scanned` : ''}
            {scan?.dependencies?.checked
              ? ` · ${scan.dependencies.checked} dependencies checked`
              : ''}
          </span>
        </div>
        <div className="sec-head-right">
          <ToolSourcePicker sources={sources} value={sourceId} onChange={onSourceChange} />
          {scan ? (
            <div className="gv-stats">
              <div className="gv-stat is-accent">
                <span className="gv-stat-value">{scan.finding_count || 0}</span>
                <span className="gv-stat-label">Findings</span>
              </div>
              <div className={`gv-stat${scan.dependencies?.vulnerable ? ' is-danger' : ''}`}>
                <span className="gv-stat-value">{scan.dependencies?.vulnerable || 0}</span>
                <span className="gv-stat-label">Vulnerable deps</span>
              </div>
              <div className="gv-stat">
                <span className="gv-stat-value">{scan.gate_count || 0}</span>
                <span className="gv-stat-label">Gates</span>
              </div>
            </div>
          ) : null}
          <button
            type="button"
            className="ad-btn"
            onClick={() => run(true)}
            disabled={status === 'loading'}
            title="Re-run the scan"
          >
            <span>Rescan</span>
          </button>
        </div>
      </div>

      {status === 'loading' && !scan ? (
        <div className="sec-stage" aria-live="polite">
          <div className="ad-spinner" aria-hidden="true" />
          <p className="sec-stage-title">Scanning…</p>
          <p className="sec-stage-note">Matching code patterns and checking advisories.</p>
        </div>
      ) : null}

      {scan ? (
        <>
          {scan.summary ? <p className="sec-summary">{scan.summary}</p> : null}

          <SeveritySummary counts={scan.counts} worstSeverity={scan.worst_severity} />

          {findings.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">Findings</h4>
                <span className="gv-section-aside">worst first</span>
              </div>
              <ul className="sec-findings">
                {visible.map((finding) => (
                  <FindingRow
                    key={`${finding.id}-${finding.location}-${finding.line ?? ''}`}
                    finding={finding}
                  />
                ))}
              </ul>
              {hidden > 0 ? (
                <button type="button" className="sec-more" onClick={() => setShowAll(true)}>
                  Show {hidden} more
                </button>
              ) : null}
            </section>
          ) : (
            <p className="sec-note">
              Nothing flagged. That is a statement about the {scan.code?.files_scanned ?? 0} files
              scanned, not a guarantee — see the coverage notes below.
            </p>
          )}

          {scan.by_category?.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">By category</h4>
                <span className="gv-section-aside">worst severity per category</span>
              </div>
              <div className="gv-chips">
                {scan.by_category.map((row) => (
                  <span
                    key={row.category}
                    className={`sec-chip ${severityTone(row.worst_severity)}`}
                  >
                    {row.category}
                    <span className="gv-badge-count">{row.count}</span>
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          <QualityChecklist gates={scan.quality} />

          {/* What the scan could not do is the last thing a reader needs and
              the first thing they should find if they go looking, so it is
              rendered open rather than collapsed behind a summary. */}
          {scan.limitations?.length ? (
            <details className="gv-disclosure" open>
              <summary>
                What this scan did not do
                <span className="gv-badge-count">({scan.limitations.length})</span>
              </summary>
              <ul className="gv-disclosure-list">
                {scan.limitations.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : null}

      {status === 'loading' && scan ? (
        <p className="ad-rebuilding" aria-live="polite">
          Re-scanning…
        </p>
      ) : null}

      {error ? (
        <p className="ad-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}
