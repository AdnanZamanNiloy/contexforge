import { useState } from 'react'

export default function OwnershipView({
  ownership = { modules: [], contributors: [], concentration: {} },
}) {
  const [activeModule, setActiveModule] = useState(ownership.modules[0]?.name || null)

  const selected = ownership.modules.find((m) => m.name === activeModule)
  const maxPercent = Math.max(...ownership.contributors.map((c) => c.percent))
  const maxModulePercent = Math.max(...ownership.modules.map((m) => m.percent))

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Ownership</h3>
          <p className="intel-subtext">Contribution and stewardship across the repository</p>
        </div>
        <div className="ownership-concentration">
          <span>
            Bus-factor <b>{ownership.concentration.busFactor}</b>
          </span>
          <span className="risk-text is-medium">Risk: {ownership.concentration.risk}</span>
        </div>
      </div>

      <div className="ownership-grid">
        <div className="ownership-col">
          <div className="git-card">
            <div className="git-card-head">
              <span>Contributors</span>
            </div>
            <div className="contrib-list">
              {ownership.contributors.map((c) => (
                <div className="contrib-row" key={c.name}>
                  <span className="contrib-avatar" style={{ background: c.color }}>
                    {(c.name[0] || '').toUpperCase()}
                  </span>
                  <span className="contrib-name">{c.name}</span>
                  <div className="contrib-bar">
                    <i
                      style={{ width: `${(c.percent / maxPercent) * 100}%`, background: c.color }}
                    />
                  </div>
                  <span className="contrib-pct">{c.percent}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="git-card">
            <div className="git-card-head">
              <span>Ownership heatmap</span>
            </div>
            <div className="heat-grid">
              {ownership.modules.map((m) => (
                <div
                  className={`heat-cell ${m.percent > 50 ? 'is-hot' : m.percent > 40 ? 'is-warm' : 'is-cool'}`}
                  key={m.name}
                  title={`${m.name} — ${m.percent}% ${m.owner}`}
                >
                  <code>{m.name}</code>
                  <span>{m.percent}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="ownership-col is-modules">
          <div className="git-card">
            <div className="git-card-head">
              <span>Module stewardship</span>
              <span className="git-card-meta">click to inspect</span>
            </div>
            <div className="module-owner-list">
              {ownership.modules.map((m) => {
                const top = m.contributors[0]
                return (
                  <button
                    className={`module-owner-row ${activeModule === m.name ? 'active' : ''}`}
                    key={m.name}
                    onClick={() => setActiveModule(m.name)}
                  >
                    <div className="module-owner-head">
                      <code className="churn-path">{m.name}</code>
                      <div className="module-owner-bar">
                        <i style={{ width: `${(m.percent / maxModulePercent) * 100}%` }} />
                      </div>
                      <span className="churn-val">{m.percent}%</span>
                    </div>
                    <div className="module-owner-meta">
                      <span className="mini-avatar" title={top.name}>
                        {(top.name[0] || '').toUpperCase()}
                      </span>
                      <span className="module-owner-lead">{top.name}</span>
                      <span className="module-owner-cols">{m.files} files</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {selected ? (
            <div className="git-card">
              <div className="git-card-head">
                <span>Shared ownership</span>
                <code className="churn-path">{selected.name}</code>
              </div>
              <div className="share-list">
                {selected.contributors.map((c) => (
                  <div className="share-row" key={c.name}>
                    <span className="mini-avatar" title={c.name}>
                      {(c.name[0] || '').toUpperCase()}
                    </span>
                    <span className="share-name">{c.name}</span>
                    <div className="contrib-bar">
                      <i style={{ width: `${c.percent}%` }} />
                    </div>
                    <span className="contrib-pct">{c.percent}%</span>
                  </div>
                ))}
              </div>
              <div className="ownership-note">
                Single-primary-owner modules (<span>≥50%</span>) have a high bus-factor risk;
                consider cross-training reviewers.
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
