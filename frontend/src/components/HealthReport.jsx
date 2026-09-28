import { useCallback, useEffect, useState } from 'react'

import { getHealthScan, scanHealth } from '../services/api'

// The Health Score & Hotspots view.
//
// Shows deterministic structural risk: every function is measured for
// cyclomatic complexity, nesting depth, fan-out and non-structured exits,
// combined by a fixed published formula into a Local Risk Score.  There is no
// model in this path, so every number is reproducible from the metrics shown
// next to it.
//
// Two limits are stated in the report rather than hidden: only Python sources
// are measured per function (other files are listed by size), and change
// frequency is not available because no git history is indexed.  The defining
// idea behind hotspot analysis is complexity *and* churn, so saying so is more
// useful than a score that quietly implies both were measured.
const BAND_LABELS = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  critical: 'Critical',
}

function RefreshIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </svg>
  )
}

function GaugeIcon() {
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
      <path d="M5 19a9 9 0 1 1 14 0" />
      <path d="M12 13l4-4" />
      <circle cx="12" cy="13" r="1.4" fill="currentColor" />
    </svg>
  )
}

function ScoreRing({ score, band }) {
  // A null score means nothing was measurable. Showing 0 or 100 there would be a
  // claim the data does not support, so the ring is replaced by the reason.
  if (score === null || score === undefined) {
    return (
      <div className="hs-ring-wrap is-none">
        <div className="hs-ring-none">
          <strong>—</strong>
          <span>Not measured</span>
        </div>
      </div>
    )
  }
  const radius = 34
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (circumference * score) / 100
  return (
    <div className={`hs-ring-wrap is-${band}`}>
      <svg className="hs-ring" viewBox="0 0 84 84" aria-hidden="true">
        <circle cx="42" cy="42" r={radius} className="hs-ring-track" />
        <circle
          cx="42"
          cy="42"
          r={radius}
          className="hs-ring-value"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="hs-ring-number">
        <strong>{score}</strong>
        <span>{BAND_LABELS[band] || band}</span>
      </div>
    </div>
  )
}

function BandDot({ band }) {
  return <span className={`hs-band-dot is-${band}`} aria-hidden="true" />
}

function MetricCells({ row }) {
  return (
    <span className="hs-metrics">
      <span title="Cyclomatic complexity">CC {row.cc}</span>
      <span title="Maximum nesting depth">ND {row.nd}</span>
      <span title="Distinct call targets (fan-out)">FO {row.fo}</span>
      <span title="Non-structured exits">NS {row.ns}</span>
    </span>
  )
}

function HotspotRow({ row }) {
  // Only the tail of the path is shown. The symbol is already on the left, so
  // `accounts/views.py` is what identifies the file, and it fits without being
  // elided — an earlier version truncated the head, which displayed a path
  // that read as a different, wrong one.
  const tail = row.path.split('/').slice(-2).join('/')
  return (
    <li className="hs-hotspot">
      <BandDot band={row.band} />
      <span className="hs-hotspot-name">
        <code>{row.name}</code>
        <span className="hs-hotspot-kind">{row.kind}</span>
        <span className="hs-hotspot-path" title={row.path}>
          {tail}
        </span>
      </span>
      <MetricCells row={row} />
      <span className="hs-lrs" title="Local Risk Score">
        {row.lrs}
      </span>
    </li>
  )
}

export default function HealthReport({ projectId, hasGithubSource = true }) {
  const [scan, setScan] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')

  const run = useCallback(
    (refresh) => {
      if (!projectId) return
      setStatus('loading')
      setError('')
      scanHealth(projectId, { refresh })
        .then((result) => {
          setScan(result)
          setStatus('ready')
        })
        .catch((err) => {
          setError(err?.message || 'The health scan failed — please try again.')
          setStatus('error')
        })
    },
    [projectId],
  )

  useEffect(() => {
    let cancelled = false
    if (!projectId || !hasGithubSource) return undefined

    getHealthScan(projectId)
      .then((stored) => {
        if (cancelled) return
        setScan(stored)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) run(false)
      })

    return () => {
      cancelled = true
    }
  }, [projectId, hasGithubSource, run])

  if (!projectId) {
    return (
      <div className="rs-view">
        <div className="rs-view-head">
          <h3>Health Score &amp; Hotspots</h3>
        </div>
        <div className="hs-stage">
          <span className="hs-empty-icon" aria-hidden="true">
            <GaugeIcon />
          </span>
          <p className="hs-stage-title">Open a project to analyse a repository</p>
          <p className="hs-stage-note">
            Structural risk is measured from the indexed source of a GitHub repository attached to a
            project.
          </p>
        </div>
      </div>
    )
  }

  if (!hasGithubSource) {
    return (
      <div className="rs-view">
        <div className="rs-view-head">
          <h3>Health Score &amp; Hotspots</h3>
        </div>
        <div className="hs-stage">
          <span className="hs-empty-icon" aria-hidden="true">
            <GaugeIcon />
          </span>
          <p className="hs-stage-title">No GitHub source in this project</p>
          <p className="hs-stage-note">
            Attach a GitHub repository to the project and it will be indexed. The scan then measures
            its functions.
          </p>
        </div>
      </div>
    )
  }

  const bandCounts = scan?.band_counts || {}
  const weights = scan?.weights || {}

  return (
    <div className="rs-view hs-root">
      {scan ? (
        <div className="rs-view-head hs-head">
          <p className="ad-meta hs-meta">
            {scan.repository}
            {scan.cached ? ' · cached' : ''}
            {scan.symbol_count
              ? ` · ${scan.symbol_count} ${scan.symbol_count === 1 ? 'function' : 'functions'}`
              : ''}
          </p>
          <button
            type="button"
            className="ad-btn"
            onClick={() => run(true)}
            disabled={status === 'loading'}
            title="Re-measure from the current source"
          >
            <RefreshIcon />
            <span>Rescan</span>
          </button>
        </div>
      ) : null}

      {status === 'loading' && !scan ? (
        <div className="hs-stage" aria-live="polite">
          <div className="ad-spinner" aria-hidden="true" />
          <p className="hs-stage-title">Measuring structural risk…</p>
          <p className="hs-stage-note">Parsing indexed functions. No model is involved.</p>
        </div>
      ) : null}

      {scan ? (
        <>
          <div className="hs-overview">
            <ScoreRing score={scan.health} band={scan.band} />
            <div className="hs-overview-body">
              <p className="hs-summary">{scan.summary}</p>
              {/* A row of zeros is noise, not information. Only shown once
                  something has actually been measured. */}
              {scan.symbol_count ? (
                <ul className="hs-bands">
                  {Object.entries(BAND_LABELS).map(([key, label]) => (
                    <li key={key} className={`hs-band is-${key}`}>
                      <BandDot band={key} />
                      <span className="hs-band-label">{label}</span>
                      <span className="hs-band-count">{bandCounts[key] || 0}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>

          {scan.hotspots?.length ? (
            <section className="hs-section">
              <h4 className="hs-section-title">Hotspots</h4>
              <ul className="hs-hotspots">
                {scan.hotspots.map((row, index) => (
                  // A path and a name are not unique together: one file can
                  // declare several same-named classes (nested `Meta`, `Config`).
                  // The index keeps the key stable and unique for this list.
                  <HotspotRow key={`${row.path}:${row.name}:${index}`} row={row} />
                ))}
              </ul>
              <p className="hs-formula">
                LRS = {weights.cc}·log₂(CC+1) + {weights.nd}·ND + {weights.fo}·log₂(FO+1) +{' '}
                {weights.ns}·NS, each term capped. Bands: low &lt; 3, moderate &lt; 6, high &lt; 9,
                critical above.
              </p>
            </section>
          ) : null}

          {/* Collapsed by default: it is supporting detail, and when nothing
              could be measured it was the only thing on screen, which made the
              report look like a file listing rather than a health scan. */}
          {scan.largest_files?.length ? (
            <details className="hs-details">
              <summary>
                Largest indexed files{' '}
                <span className="hs-details-count">({scan.largest_files.length})</span>
              </summary>
              <ul className="hs-files">
                {scan.largest_files.map((row) => (
                  <li key={row.path}>
                    <code>{row.path}</code>
                    <span className="hs-file-size">
                      {row.chars.toLocaleString()} chars{row.measured ? '' : ' · size only'}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {scan.coverage_note ? <p className="hs-note">{scan.coverage_note}</p> : null}
        </>
      ) : null}

      {status === 'loading' && scan ? (
        <p className="ad-rebuilding" aria-live="polite">
          Re-measuring…
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
