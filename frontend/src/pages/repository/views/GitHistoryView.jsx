import { useState } from 'react';

const RANGES = ['7 days', '30 days', '90 days', 'full history'];

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return iso || '';
  }
}

export default function GitHistoryView({ gitHistory = { timeline: [], fileChurn: [], branches: [], commits: [] } }) {
  const [range, setRange] = useState('30 days');
  const maxTimeline = Math.max(1, ...gitHistory.timeline.map((t) => t.commits));
  const maxChurn = Math.max(1, ...gitHistory.fileChurn.map((f) => f.value));

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Git History</h3>
          <p className="intel-subtext">Repository evolution across branches and files</p>
        </div>
        <div className="range-toggle">
          {RANGES.map((r) => (
            <button key={r} className={range === r ? 'active' : ''} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
      </div>

      <div className="git-grid">
        <div className="git-main">
          <div className="git-card">
            <div className="git-card-head">
              <span>Commit activity</span>
              <span className="git-card-meta">{gitHistory.range === 'all' ? 'Full history' : gitHistory.range}</span>
            </div>
            {gitHistory.timeline.length ? (
              <div className="commit-bars">
                {gitHistory.timeline.map((t) => (
                  <div className="commit-col" key={t.week}>
                    <div className="commit-bar-wrap">
                      <div className="commit-bar" style={{ height: `${(t.commits / maxTimeline) * 100}%` }} />
                    </div>
                    <span className="commit-week">{t.week}</span>
                    <span className="commit-num">{t.commits}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="intel-empty">No commit activity in this period.</p>
            )}
          </div>

          <div className="git-card">
            <div className="git-card-head">
              <span>File churn</span>
            </div>
            {gitHistory.fileChurn.length ? (
              <div className="churn-list">
                {gitHistory.fileChurn.map((f) => (
                  <div className="churn-row" key={f.name}>
                    <code className="churn-path">{f.name}</code>
                    <div className="churn-bar"><i style={{ width: `${(f.value / maxChurn) * 100}%` }} /></div>
                    <span className="churn-val">{f.value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="intel-empty">No file churn recorded.</p>
            )}
          </div>
        </div>

        <div className="git-side">
          <div className="git-card">
            <div className="git-card-head"><span>Branches</span></div>
            {gitHistory.branches.length ? (
              <div className="branch-list">
                {gitHistory.branches.map((b) => (
                  <div className="branch-row" key={b.name}>
                    <span className="branch-dot" style={{ background: b.color }} />
                    <code className="branch-name">{b.name}</code>
                    <span className="branch-count">{b.commits}</span>
                    {b.active ? <span className="branch-active">HEAD</span> : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="intel-empty">No branches detected.</p>
            )}
          </div>

          <div className="git-card">
            <div className="git-card-head"><span>Recent commits</span></div>
            {gitHistory.commits.length ? (
              <div className="recent-commits">
                {gitHistory.commits.map((c) => (
                  <button className="commit-row" key={c.hash}>
                    <code className="commit-hash">{c.hash}</code>
                    <span className="commit-msg">{c.message}</span>
                    <span className="commit-author">{c.author}</span>
                    <span className="commit-time">{fmtTime(c.time)}</span>
                    <span className="commit-diff">+{c.inserts} −{c.deletes}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="intel-empty">No commits in this window.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
