import { useMemo, useState } from 'react'

import { ViewShell, ViewHeader, Card, StatTile, ProgressBar, riskTone } from '../ui/primitives'

function Avatar({ name, color, size = 24 }) {
  const initials = (name || '?')
    .split(/[-_\s]/)
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span
      className="rv-avatar"
      style={{
        width: size,
        height: size,
        background: color,
        fontSize: size <= 24 ? '0.62rem' : '0.68rem',
      }}
      title={name}
    >
      {initials}
    </span>
  )
}

const busFactorTone = (bf) => (bf <= 1 ? 'warn' : bf <= 2 ? 'caution' : 'ok')

const EMPTY_OWNERSHIP = { modules: [], contributors: [], concentration: {} }

export default function OwnershipView({ ownership = EMPTY_OWNERSHIP }) {
  const contributors = useMemo(() => ownership.contributors || [], [ownership])
  const modules = useMemo(() => ownership.modules || [], [ownership])
  const concentration = ownership.concentration || {}

  const [activeModule, setActiveModule] = useState(modules[0]?.name || null)

  const selected = modules.find((m) => m.name === activeModule) || modules[0]
  const maxPercent = useMemo(
    () => Math.max(1, ...contributors.map((c) => c.percent)),
    [contributors],
  )
  const maxModulePercent = useMemo(() => Math.max(1, ...modules.map((m) => m.percent)), [modules])

  return (
    <ViewShell>
      <ViewHeader
        eyebrow="Ownership"
        title="Contributors & stewardship"
        description="Who owns the code, how concentrated that ownership is, and where the bus-factor risk lies."
        actions={
          <div className="rv-inline-stats">
            <span className="rv-inline-stat">
              <b>{contributors.length}</b> contributors
            </span>
            <span className="rv-inline-stat">
              <b>{modules.length}</b> modules
            </span>
          </div>
        }
      />

      <div className="rv-grid rv-grid-3">
        <StatTile
          label="Bus factor"
          value={concentration.busFactor ?? '—'}
          tone={busFactorTone(concentration.busFactor)}
          hint="Minimum contributors to lose"
        />
        <StatTile
          label="Top contributor"
          value={`${Math.round(concentration.top1 ?? 0)}%`}
          hint="Share of commits"
        />
        <StatTile
          label="Concentration risk"
          value={concentration.risk || 'Low'}
          tone={
            riskTone(concentration.risk) === 'high' || riskTone(concentration.risk) === 'critical'
              ? 'warn'
              : 'ok'
          }
          hint="Overall ownership risk"
        />
      </div>

      <div className="rv-grid rv-grid-2">
        <div className="rv-stack">
          <Card title="Contributors" meta={`${contributors.length} total`}>
            {contributors.length ? (
              <div className="rv-contrib-list">
                {contributors.map((c) => (
                  <div className="rv-contrib-row" key={c.name}>
                    <Avatar name={c.name} color={c.color} />
                    <span className="rv-contrib-name" title={c.name}>
                      {c.name}
                    </span>
                    <ProgressBar value={c.percent} max={maxPercent} tone="custom" />
                    <span className="rv-contrib-pct">{c.percent}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No contributor data available.</p>
            )}
          </Card>

          <Card title="Ownership heatmap" meta="Per module">
            {modules.length ? (
              <div className="rv-heat-grid">
                {modules.map((m) => (
                  <button
                    type="button"
                    className={`rv-heat-cell ${heatClass(m.percent)}`}
                    key={m.name}
                    title={`${m.name} — ${m.percent}% ${m.owner}`}
                    onClick={() => setActiveModule(m.name)}
                  >
                    <code>{m.name}</code>
                    <span>{m.percent}%</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No module ownership detected.</p>
            )}
          </Card>
        </div>

        <div className="rv-stack">
          <Card title="Module stewardship" meta="Click to inspect">
            {modules.length ? (
              <div className="rv-module-owner-list">
                {modules.map((m) => {
                  const top = m.contributors?.[0]
                  return (
                    <button
                      type="button"
                      className={`rv-module-owner-row ${activeModule === m.name ? 'is-active' : ''}`}
                      key={m.name}
                      onClick={() => setActiveModule(m.name)}
                    >
                      <div className="rv-module-owner-head">
                        <code className="rv-code">{m.name}</code>
                        <ProgressBar value={m.percent} max={maxModulePercent} />
                        <span className="rv-module-owner-pct">{m.percent}%</span>
                      </div>
                      <div className="rv-module-owner-meta">
                        {top ? <Avatar name={top.name} color={top.color} size={20} /> : null}
                        <span className="rv-module-owner-lead">{top?.name || m.owner}</span>
                        <span className="rv-module-owner-files">{m.files} files</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <p className="rv-muted-block">No module stewardship data.</p>
            )}
          </Card>

          {selected ? (
            <Card
              title="Shared ownership"
              actions={<code className="rv-code">{selected.name}</code>}
            >
              <div className="rv-share-list">
                {selected.contributors?.map((c) => (
                  <div className="rv-share-row" key={c.name}>
                    <Avatar name={c.name} color={c.color} size={22} />
                    <span className="rv-share-name">{c.name}</span>
                    <ProgressBar value={c.percent} />
                    <span className="rv-contrib-pct">{c.percent}%</span>
                  </div>
                ))}
              </div>
              <p className="rv-note">
                Modules with a single primary owner (≥50%) carry high bus-factor risk — consider
                cross-training reviewers.
              </p>
            </Card>
          ) : null}
        </div>
      </div>
    </ViewShell>
  )
}

function heatClass(percent) {
  if (percent > 50) return 'is-hot'
  if (percent > 40) return 'is-warm'
  return 'is-cool'
}
