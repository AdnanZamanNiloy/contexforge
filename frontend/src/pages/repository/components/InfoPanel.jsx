// Shared node-detail panel shown below the architecture graph.
// Renders a compact multi-column metric layout for the currently selected node
// based on the data available in its `meta` object.

function RiskBadge({ risk }) {
  if (!risk) return null
  const tone = risk.toLowerCase()
  return <span className={`risk-badge is-${tone}`}>{risk}</span>
}

function Metric({ label, value }) {
  return (
    <div className="info-metric">
      <span className="info-metric-label">{label}</span>
      <span className="info-metric-value">{value ?? '—'}</span>
    </div>
  )
}

function Avatar({ name }) {
  const initials = (name || '?')
    .split(/[-_\s]/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span className="mini-avatar" title={name}>
      {initials}
    </span>
  )
}

export default function InfoPanel({ node = null }) {
  if (!node) {
    return (
      <div className="info-panel">
        <div className="info-empty">
          Select a node in the graph to inspect its architecture, dependencies and recent changes.
        </div>
      </div>
    )
  }

  const meta = node.meta || {}
  const path = meta.path || 'unknown path'

  return (
    <div className="info-panel">
      <div className="info-panel-head">
        <div className="info-title">
          <span className="info-name">{node.label}</span>
          <code className="info-path">{path}</code>
        </div>
        <div className="info-head-right">
          <span className="info-kind">{meta.type || node.kind || 'node'}</span>
          <RiskBadge risk={meta.risk} />
        </div>
      </div>

      <div className="info-metrics">
        <Metric label="Files" value={meta.files} />
        <Metric
          label="Lines of Code"
          value={
            meta.loc != null && meta.loc > 100000 ? `${(meta.loc / 1000).toFixed(1)}k` : meta.loc
          }
        />
        <Metric label="Dependencies" value={meta.deps} />
        <Metric label="Dependents" value={meta.dependents} />
        <Metric label="Test Coverage" value={meta.coverage != null ? `${meta.coverage}%` : null} />
        <Metric label="Last Changed" value={meta.changed} />
      </div>

      {meta.contributors?.length ? (
        <div className="info-row">
          <span className="info-row-label">Contributors</span>
          <div className="info-avatars">
            {meta.contributors.slice(0, 5).map((c) => (
              <Avatar key={c} name={c} />
            ))}
            <span className="info-avatar-count">+{Math.max(0, meta.contributors.length - 5)}</span>
          </div>
        </div>
      ) : null}

      {meta.topDependencies?.length ? (
        <div className="info-row">
          <span className="info-row-label">Top Dependencies</span>
          <div className="info-deps">
            {meta.topDependencies.map((d) => (
              <code key={d} className="inline-code">
                {d}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {meta.recentChanges?.length ? (
        <div className="info-changes">
          <div className="info-row-label">Recent Changes</div>
          {meta.recentChanges.map((c) => (
            <div className="info-change" key={c.hash}>
              <code className="commit-hash">{c.hash}</code>
              <span className="info-change-msg">{c.message}</span>
              <span className="info-change-time">{c.time}</span>
            </div>
          ))}
        </div>
      ) : null}

      <button
        className="change-impact-link"
        onClick={() => window.dispatchEvent(new CustomEvent('repo-intel:change-impact'))}
      >
        View Change Impact <span className="arrow">→</span>
      </button>
    </div>
  )
}
