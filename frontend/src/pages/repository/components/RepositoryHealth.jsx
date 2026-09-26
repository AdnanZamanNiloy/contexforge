import { Card, ProgressBar } from '../ui/primitives'

function Donut({ score = 0 }) {
  const r = 34
  const c = 2 * Math.PI * r
  const off = c - (c * Math.min(100, Math.max(0, score))) / 100
  return (
    <div className="rv-donut">
      <svg
        viewBox="0 0 80 80"
        width="88"
        height="88"
        role="img"
        aria-label={`Health score ${score} out of 100`}
      >
        <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke="url(#rvHealthGrad)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
          transform="rotate(-90 40 40)"
        />
        <defs>
          <linearGradient id="rvHealthGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#2f5fe0" />
            <stop offset="100%" stopColor="#4377FD" />
          </linearGradient>
        </defs>
      </svg>
      <div className="rv-donut-score">
        <strong>{Math.round(score)}</strong>
        <span>/ 100</span>
      </div>
    </div>
  )
}

export default function RepositoryHealth({ health = {}, rankedModules = [] }) {
  const dimensions = health.dimensions || []
  return (
    <Card title="Repository Health" className="rv-rail-card">
      <div className="rv-health">
        <Donut score={health.score || 0} />
        {dimensions.length ? (
          <div className="rv-health-dims">
            {dimensions.map((d) => (
              <div className="rv-health-dim" key={d.label}>
                <div className="rv-health-dim-head">
                  <span title={d.detail || undefined}>{d.label}</span>
                  <b className={`is-${d.tone}`}>{Math.round(d.value)}</b>
                </div>
                <ProgressBar
                  value={d.value}
                  tone={d.tone === 'warn' ? 'caution' : d.tone === 'critical' ? 'warn' : 'teal'}
                />
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {rankedModules.length ? (
        <div className="rv-ranked">
          <span className="rv-rail-subtitle">Most active / complex modules</span>
          {rankedModules.map((m) => (
            <div className="rv-ranked-row" key={m.name}>
              <code className="rv-ranked-name" title={m.reason || m.name}>
                {m.name}
              </code>
              <ProgressBar value={m.value} />
              <span className="rv-ranked-val">{Math.round(m.value)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  )
}
