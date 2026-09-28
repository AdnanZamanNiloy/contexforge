import { useCallback, useEffect, useState } from 'react'

import ServiceGraph from './ServiceGraph'
import { getTechStack, scanTechStack } from '../services/api'

// The Dependency & Tech Stack view.
//
// Renders a scan of the project's ingested GitHub source: what it is written
// in, which frameworks and tools it declares, and the dependencies each package
// manager resolved.  Versions are reported exactly as the manifest or lockfile
// states them — nothing is resolved against a registry, so an unresolved range
// is shown as written rather than guessed at.
//
// The stored scan is shown on open when one exists, so a repeat visit costs no
// scan at all.  Scanning is explicit, and the whole thing is local server work
// that finishes in milliseconds.
const MAX_ROWS_OPEN = 12

// Category order, most architectural first: what the system is made of, where it
// runs, then what it is built with.  Anything not listed follows, alphabetically.
const KIND_ORDER = [
  'Database',
  'Cloud',
  'Hosting',
  'Container',
  'Infrastructure',
  'CI/CD',
  'AI',
  'Framework',
  'UI framework',
  'Language',
  'Runtime',
  'Testing',
  'Linting',
  'Build',
  'Package manager',
]

function groupByKind(rows) {
  const groups = new Map()
  rows.forEach((row) => {
    const kind = row.kind || 'Other'
    if (!groups.has(kind)) groups.set(kind, [])
    groups.get(kind).push(row)
  })
  return [...groups.entries()].sort(([a], [b]) => {
    const ai = KIND_ORDER.indexOf(a)
    const bi = KIND_ORDER.indexOf(b)
    // An unlisted category sorts after every listed one, not at index -1.
    if (ai === -1 && bi === -1) return a.localeCompare(b)
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
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

function StackIcon() {
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
      <path d="M12 3 3 8l9 5 9-5z" />
      <path d="M3 13l9 5 9-5" />
    </svg>
  )
}

function DependencyTable({ bucket }) {
  const [expanded, setExpanded] = useState(false)
  const deps = bucket.dependencies
  const visible = expanded ? deps : deps.slice(0, MAX_ROWS_OPEN)
  const hidden = deps.length - visible.length
  // A column of em-dashes tells a reader nothing, so Scope only appears when
  // something in this ecosystem is actually scoped.
  const hasScopes = deps.some((dep) => dep.scope && dep.scope !== 'runtime')

  if (!deps.length) {
    return (
      <div className="ts-manifest">
        <span className="ts-manager">{bucket.manager}</span>
        <span className="ts-empty">no dependencies declared</span>
      </div>
    )
  }

  return (
    <div className="ts-manifest">
      <div className="gv-section-head">
        <h5 className="gv-subhead">{bucket.manager}</h5>
        <span className="gv-section-aside">
          {bucket.language} · {deps.length} {deps.length === 1 ? 'package' : 'packages'}
        </span>
      </div>
      <table className="gv-table">
        <thead>
          <tr>
            <th scope="col">Package</th>
            <th scope="col" className="gv-num">
              Version
            </th>
            {hasScopes ? <th scope="col">Scope</th> : null}
          </tr>
        </thead>
        <tbody>
          {visible.map((dep) => (
            <tr key={dep.name}>
              <td className="gv-cell-strong" title={dep.manifest || dep.name}>
                {dep.name}
              </td>
              <td className="gv-num">
                {dep.version ? (
                  <code className="ts-dep-version">{dep.version}</code>
                ) : (
                  <span className="ts-dep-version is-unpinned" title="No version is pinned">
                    unpinned
                  </span>
                )}
              </td>
              {hasScopes ? (
                <td className="gv-cell-muted">
                  {dep.scope !== 'runtime' ? (
                    <span className={`ts-scope is-${dep.scope}`}>{dep.scope}</span>
                  ) : (
                    '—'
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      {hidden > 0 || expanded ? (
        <button type="button" className="ts-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Show fewer' : `Show ${hidden} more`}
        </button>
      ) : null}
    </div>
  )
}

export default function TechStackReport({ projectId, hasGithubSource = true }) {
  const [scan, setScan] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')

  const run = useCallback(
    (refresh) => {
      if (!projectId) return
      setStatus('loading')
      setError('')
      scanTechStack(projectId, { refresh })
        .then((result) => {
          setScan(result)
          setStatus('ready')
        })
        .catch((err) => {
          setError(err?.message || 'The tech stack scan failed — please try again.')
          setStatus('error')
        })
    },
    [projectId],
  )

  useEffect(() => {
    let cancelled = false
    if (!projectId || !hasGithubSource) return undefined

    getTechStack(projectId)
      .then((stored) => {
        if (cancelled) return
        setScan(stored)
        setStatus('ready')
      })
      .catch(() => {
        // 404 just means nothing scanned yet.
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
          <h3>Dependency &amp; Tech Stack</h3>
        </div>
        <div className="ts-stage">
          <span className="ts-empty-icon" aria-hidden="true">
            <StackIcon />
          </span>
          <p className="ts-stage-title">Open a project to scan a repository</p>
          <p className="ts-stage-note">
            The stack is read from the manifests of a GitHub repository attached to a project.
          </p>
        </div>
      </div>
    )
  }

  if (!hasGithubSource) {
    return (
      <div className="rs-view">
        <div className="rs-view-head">
          <h3>Dependency &amp; Tech Stack</h3>
        </div>
        <div className="ts-stage">
          <span className="ts-empty-icon" aria-hidden="true">
            <StackIcon />
          </span>
          <p className="ts-stage-title">No GitHub source in this project</p>
          <p className="ts-stage-note">
            Attach a GitHub repository to the project and it will be indexed. The scan then reads
            its manifests and lockfiles.
          </p>
        </div>
      </div>
    )
  }

  const programming = (scan?.languages || []).filter((row) => row.kind === 'programming')
  const support = (scan?.languages || []).filter((row) => row.kind !== 'programming')

  // Technologies are grouped by category rather than listed flat.  With the
  // database, hosting, CI, cloud and AI rules in play there are a dozen
  // categories, and a single flat list of everything buries the ones a reader
  // is looking for: which database, deployed where, built by what.
  const byKind = groupByKind(scan?.technologies || [])

  return (
    <div className="rs-view ts-root">
      {/* No heading here: the Studio main window already renders the tool
          name as its h2, and repeating it read as a duplicate. */}
      <div className="gv-band ts-head">
        <div className="gv-id">
          <span className="gv-id-repo">{scan?.repository || 'Repository'}</span>
          <span className="gv-id-note">{scan?.cached ? 'cached scan' : 'fresh scan'}</span>
        </div>
        {scan ? (
          <div className="ts-head-right">
            <div className="gv-stats">
              <div className="gv-stat">
                <span className="gv-stat-value">{scan.language_count || 0}</span>
                <span className="gv-stat-label">Languages</span>
              </div>
              <div className="gv-stat">
                <span className="gv-stat-value">{scan.technologies?.length || 0}</span>
                <span className="gv-stat-label">Technologies</span>
              </div>
              <div className="gv-stat">
                <span className="gv-stat-value">{scan.dependency_count || 0}</span>
                <span className="gv-stat-label">Dependencies</span>
              </div>
              <div className="gv-stat">
                <span className="gv-stat-value">{scan.manifest_count || 0}</span>
                <span className="gv-stat-label">Manifests</span>
              </div>
            </div>
            <button
              type="button"
              className="ad-btn"
              onClick={() => run(true)}
              disabled={status === 'loading'}
              title="Re-scan the manifests from scratch"
            >
              <RefreshIcon />
              <span>Rescan</span>
            </button>
          </div>
        ) : null}
      </div>

      {status === 'loading' && !scan ? (
        <div className="ts-stage" aria-live="polite">
          <div className="ad-spinner" aria-hidden="true" />
          <p className="ts-stage-title">Scanning manifests…</p>
          <p className="ts-stage-note">Reading lockfiles and counting languages.</p>
        </div>
      ) : null}

      {scan ? (
        <>
          {scan.summary ? <p className="gv-lead">{scan.summary}</p> : null}

          {programming.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">Languages</h4>
                <span className="gv-section-aside">by file count</span>
              </div>
              <ul className="ts-langs">
                {programming.map((row) => (
                  <li key={row.name} className="ts-lang">
                    <span className="ts-lang-name">{row.name}</span>
                    <span className="ts-lang-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(2, row.share * 100)}%` }} />
                    </span>
                    <span className="ts-lang-share">{Math.round(row.share * 100)}%</span>
                    <span className="ts-lang-files">{row.files}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <ServiceGraph graph={scan.graph} />

          {byKind.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">Technologies</h4>
                <span className="gv-section-aside">
                  {byKind.length === 1 ? byKind[0][0] : `${byKind.length} categories`}
                </span>
              </div>
              {byKind.length === 1 ? (
                // A single category is a label, not a section of its own.
                <div className="gv-chips">
                  {byKind[0][1].map((tool) => (
                    <span
                      key={tool.name}
                      className="gv-chip"
                      title={tool.evidence?.length ? `via ${tool.evidence.join(', ')}` : tool.kind}
                    >
                      {tool.name}
                      {tool.version ? <em className="gv-chip-version">{tool.version}</em> : null}
                    </span>
                  ))}
                </div>
              ) : (
                byKind.map(([kind, rows]) => (
                  <div key={kind} className="ts-kind">
                    <h5 className="gv-subhead">{kind}</h5>
                    <div className="gv-chips">
                      {rows.map((tool) => (
                        <span
                          key={tool.name}
                          className="gv-chip"
                          title={tool.evidence?.length ? `via ${tool.evidence.join(', ')}` : tool.kind}
                        >
                          {tool.name}
                          {tool.version ? <em className="gv-chip-version">{tool.version}</em> : null}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </section>
          ) : null}

          {scan.dependencies?.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">Dependencies</h4>
                <span className="gv-section-aside">
                  {scan.dependencies.length}{' '}
                  {scan.dependencies.length === 1 ? 'ecosystem' : 'ecosystems'}
                </span>
              </div>
              <div className="ts-manifests">
                {scan.dependencies.map((bucket) => (
                  <DependencyTable key={bucket.manager} bucket={bucket} />
                ))}
              </div>
            </section>
          ) : null}

          {support.length ? (
            <section className="gv-section">
              <div className="gv-section-head">
                <h4 className="gv-section-title">Config &amp; data formats</h4>
                <span className="gv-section-aside">by file count</span>
              </div>
              <div className="gv-chips">
                {support.map((row) => (
                  <span key={row.name} className="gv-badge">
                    {row.name}
                    <span className="gv-badge-count">{row.files}</span>
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {scan.manifests?.length ? (
            <details className="gv-disclosure">
              <summary>
                Manifests read
                <span className="gv-badge-count">({scan.manifests.length})</span>
              </summary>
              <ul className="gv-disclosure-list">
                {scan.manifests.map((entry) => (
                  <li key={entry.path}>
                    <code>{entry.path}</code>
                    <span>
                      {entry.manager} · {entry.dependency_count} deps
                      {entry.error ? ' · could not be parsed' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {scan.truncated ? (
            <p className="gv-note gv-note-bordered">
              This repository is large, so the scan used a bounded view of its files.
            </p>
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
