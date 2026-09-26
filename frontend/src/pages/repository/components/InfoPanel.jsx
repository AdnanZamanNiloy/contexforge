import { Card, Metric, Badge, riskTone } from '../ui/primitives'
import { IconArrowRight } from '../ui/icons'

// Shared node-detail panel shown below the architecture graph. Renders a compact
// metric grid for the selected node from the data available in its `meta`.

function Avatar({ name }) {
  const initials = (name || '?')
    .split(/[-_\s]/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span className="rv-avatar" style={{ width: 26, height: 26 }} title={name}>
      {initials}
    </span>
  )
}

export default function InfoPanel({ node = null }) {
  if (!node) {
    return (
      <Card title="Node inspector">
        <p className="rv-muted-block">
          Select a node in the graph to inspect its architecture, dependencies and recent changes.
        </p>
      </Card>
    )
  }

  const meta = node.meta || {}
  const path = meta.path || 'unknown path'
  const risk = meta.risk

  return (
    <Card
      title="Node inspector"
      actions={
        <div className="rv-inline-badges">
          <Badge tone="neutral">{meta.type || node.kind || 'node'}</Badge>
          {risk ? <Badge tone={riskTone(risk)}>{risk}</Badge> : null}
        </div>
      }
    >
      <div className="rv-node-head">
        <span className="rv-node-name">{node.label}</span>
        <code className="rv-code">{path}</code>
      </div>

      <div className="rv-metric-grid">
        <Metric label="Files" value={meta.files} />
        <Metric
          label="Lines of code"
          value={
            meta.loc != null && meta.loc > 100000 ? `${(meta.loc / 1000).toFixed(1)}k` : meta.loc
          }
        />
        <Metric label="Dependencies" value={meta.deps} />
        <Metric label="Dependents" value={meta.dependents} />
        <Metric label="Test coverage" value={meta.coverage != null ? `${meta.coverage}%` : null} />
        <Metric label="Last changed" value={meta.changed} />
      </div>

      {meta.contributors?.length ? (
        <div className="rv-info-row">
          <span className="rv-info-row-label">Contributors</span>
          <div className="rv-avatars">
            {meta.contributors.slice(0, 5).map((c) => (
              <Avatar key={c} name={c} />
            ))}
            {meta.contributors.length > 5 ? (
              <span className="rv-avatar-more">+{meta.contributors.length - 5}</span>
            ) : null}
          </div>
        </div>
      ) : null}

      {meta.topDependencies?.length ? (
        <div className="rv-info-row">
          <span className="rv-info-row-label">Top dependencies</span>
          <div className="rv-chip-list">
            {meta.topDependencies.map((d) => (
              <code key={d} className="rv-code">
                {d}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {meta.recentChanges?.length ? (
        <div className="rv-info-row">
          <span className="rv-info-row-label">Recent changes</span>
          <div className="rv-change-list">
            {meta.recentChanges.map((c) => (
              <div className="rv-change-row" key={c.hash}>
                <code className="rv-hash">{c.hash}</code>
                <span className="rv-change-msg" title={c.message}>
                  {c.message}
                </span>
                <span className="rv-change-time">{c.time}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <button
        type="button"
        className="rv-btn rv-btn-link"
        onClick={() => window.dispatchEvent(new CustomEvent('repo-intel:change-impact'))}
      >
        View change impact <IconArrowRight width={14} height={14} />
      </button>
    </Card>
  )
}
