import { moduleDetails, riskExplanations } from '../../../data/repoIntelligence';

function RiskBadge({ risk }) {
  if (!risk) return null;
  return <span className={`risk-badge is-${risk.toLowerCase()}`}>{risk}</span>;
}

function Metric({ label, value }) {
  return (
    <div className="inspector-metric">
      <span className="inspector-metric-value">{value}</span>
      <span className="inspector-metric-label">{label}</span>
    </div>
  );
}

export default function RepositoryInspector({ node, activeTab }) {
  // When nothing is selected, show a default module deep-dive.
  const selection = node
    ? { label: node.label, meta: node.meta }
    : { label: 'Core', meta: moduleDetails };

  const meta = selection.meta || {};

  return (
    <aside className="repo-inspector">
      <div className="inspector-head">
        <div className="inspector-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg>
        </div>
        <div className="inspector-title-wrap">
          <div className="inspector-title">{selection.label}</div>
          <code className="inspector-path">{meta.path || moduleDetails.path}</code>
        </div>
        <RiskBadge risk={meta.risk} />
      </div>
      <div className="inspector-kind">{meta.type || 'Module'}</div>

      <div className="inspector-metrics">
        <Metric label="Files" value={meta.files} />
        <Metric label="Lines of Code" value={meta.loc ? meta.loc.toLocaleString() : null} />
        <Metric label="Dependencies" value={meta.deps} />
        <Metric label="Dependents" value={meta.dependents} />
        <Metric label="Test Coverage" value={meta.coverage != null ? `${meta.coverage}%` : null} />
        <Metric label="Last Changed" value={meta.changed} />
      </div>

      {meta.risk ? (
        <div className="inspector-block">
          <div className="inspector-block-title">Why is this high risk?</div>
          <p className="inspector-risk-text">{riskExplanations[meta.risk] || riskExplanations.Medium}</p>
        </div>
      ) : null}

      <div className="inspector-block">
        <div className="inspector-block-title">Contributors</div>
        <div className="inspector-avatars">
          {(meta.contributors || moduleDetails.contributors).slice(0, 6).map((c) => (
            <span className="mini-avatar" key={c} title={c}>{(c[0] || '').toUpperCase()}</span>
          ))}
          {meta.contributors?.length > 6 ? <span className="info-avatar-count">+{meta.contributors.length - 6}</span> : null}
        </div>
      </div>

      <div className="inspector-block">
        <div className="inspector-block-title">Top Dependencies</div>
        <div className="inspector-deps">
          {(meta.topDependencies || moduleDetails.topDependencies).map((d) => <code key={d} className="inline-code">{d}</code>)}
        </div>
      </div>

      <div className="inspector-block">
        <div className="inspector-block-title">Recent Changes</div>
        <div className="inspector-changes">
          {(meta.recentChanges || moduleDetails.recentChanges).map((c) => (
            <div className="inspector-change" key={c.hash}>
              <code className="commit-hash">{c.hash}</code>
              <span className="inspector-change-msg">{c.message}</span>
              <span className="inspector-change-time">{c.time}</span>
            </div>
          ))}
        </div>
      </div>

      <button className="change-impact-link" onClick={() => window.dispatchEvent(new CustomEvent('repo-intel:change-impact'))}>
        View Change Impact <span className="arrow">→</span>
      </button>
    </aside>
  );
}
