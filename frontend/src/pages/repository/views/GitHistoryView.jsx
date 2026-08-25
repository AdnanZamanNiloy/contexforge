import { useState } from 'react';
import { gitHistory } from '../../../data/repoIntelligence';

const RANGES = ['7 days', '30 days', '90 days', '1 year'];

export default function GitHistoryView() {
  const [range, setRange] = useState('30 days');
  const maxTimeline = Math.max(...gitHistory.timeline.map((t) => t.commits));
  const maxChurn = Math.max(...gitHistory.fileChurn.map((f) => f.value));

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
              <span className="git-card-meta">{gitHistory.range}</span>
            </div>
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
          </div>

          <div className="git-card">
            <div className="git-card-head">
              <span>File churn</span>
            </div>
            <div className="churn-list">
              {gitHistory.fileChurn.map((f) => (
                <div className="churn-row" key={f.name}>
                  <code className="churn-path">{f.name}</code>
                  <div className="churn-bar"><i style={{ width: `${(f.value / maxChurn) * 100}%` }} /></div>
                  <span className="churn-val">{f.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="git-side">
          <div className="git-card">
            <div className="git-card-head"><span>Branches</span></div>
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
          </div>

          <div className="git-card">
            <div className="git-card-head"><span>Recent commits</span></div>
            <div className="recent-commits">
              {gitHistory.commits.map((c) => (
                <button className="commit-row" key={c.hash}>
                  <code className="commit-hash">{c.hash}</code>
                  <span className="commit-msg">{c.message}</span>
                  <span className="commit-author">{c.author}</span>
                  <span className="commit-time">{c.time}</span>
                  <span className="commit-diff">+{c.inserts} −{c.deletes}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
