function Donut({ score = 0 }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const off = c - (c * score) / 100;
  return (
    <div className="health-donut">
      <svg viewBox="0 0 80 80" width="80" height="80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <circle
          cx="40" cy="40" r={r} fill="none"
          stroke="url(#healthGrad)" strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={off}
          transform="rotate(-90 40 40)"
        />
        <defs>
          <linearGradient id="healthGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#67e0c8" />
            <stop offset="100%" stopColor="#7aa2f7" />
          </linearGradient>
        </defs>
      </svg>
      <div className="health-score">
        <strong>{score}</strong>
        <span>/ 100</span>
      </div>
    </div>
  );
}

const MAX_RANK = 100;

export default function RepositoryHealth({ health = {}, rankedModules = [] }) {
  return (
    <section className="sidebar-section">
      <div className="sidebar-section-title">Repository Health</div>
      <div className="health-card">
        <Donut score={health.score} />
        <div className="health-dimensions">
          {(health.dimensions || []).map((d) => (
            <div className="health-dim" key={d.label}>
              <div className="health-dim-head">
                <span>{d.label}</span>
                <b className={d.tone}>{d.value}</b>
              </div>
              <div className="health-dim-bar"><i className={d.tone} style={{ width: `${d.value}%` }} /></div>
            </div>
          ))}
        </div>
      </div>

      <div className="sidebar-subtitle">Most active / complex modules</div>
      <div className="ranked-modules">
        {(rankedModules || []).map((m) => (
          <div className="ranked-row" key={m.name}>
            <code className="ranked-name">{m.name}</code>
            <div className="ranked-bar"><i style={{ width: `${(m.value / MAX_RANK) * 100}%` }} /></div>
            <span className="ranked-val">{m.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
