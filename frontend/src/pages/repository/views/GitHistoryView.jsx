import { useMemo, useState } from 'react'

import { ViewShell, ViewToolbar, Card, StatTile, ProgressBar, Badge } from '../ui/primitives'

const RANGES = ['7 days', '30 days', '90 days', 'Full history']

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return iso || ''
  }
}

const EMPTY_HISTORY = { timeline: [], fileChurn: [], branches: [], commits: [] }

export default function GitHistoryView({ gitHistory = EMPTY_HISTORY }) {
  const [range, setRange] = useState('30 days')

  const timeline = useMemo(() => gitHistory.timeline || [], [gitHistory])
  const fileChurn = useMemo(() => gitHistory.fileChurn || [], [gitHistory])
  const branches = useMemo(() => gitHistory.branches || [], [gitHistory])
  const commits = useMemo(() => gitHistory.commits || [], [gitHistory])

  const maxTimeline = useMemo(() => Math.max(1, ...timeline.map((t) => t.commits)), [timeline])
  const maxChurn = useMemo(() => Math.max(1, ...fileChurn.map((f) => f.value)), [fileChurn])
  const totalCommits = useMemo(() => timeline.reduce((s, t) => s + t.commits, 0), [timeline])

  return (
    <ViewShell>
      <ViewToolbar
        right={
          <div className="rv-segmented" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                className={range === r ? 'is-active' : ''}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        }
      />

      <div className="rv-grid rv-grid-3">
        <StatTile label="Commits" value={totalCommits} hint={`Across ${timeline.length} buckets`} />
        <StatTile label="Branches" value={branches.length} hint="Detected in repository" />
        <StatTile
          label="Active branch"
          value={branches.find((b) => b.active)?.name || gitHistory.range || '—'}
          hint="Current HEAD"
        />
      </div>

      <div className="rv-grid rv-grid-main-side">
        <div className="rv-stack">
          <Card
            title="Commit activity"
            meta={gitHistory.range === 'all' ? 'Full history' : gitHistory.range}
          >
            {timeline.length ? (
              <div className="rv-commit-bars">
                {timeline.map((t) => (
                  <div className="rv-commit-col" key={t.week}>
                    <div className="rv-commit-bar-wrap" title={`${t.commits} commits`}>
                      <span
                        className="rv-commit-bar"
                        style={{ height: `${Math.max(4, (t.commits / maxTimeline) * 100)}%` }}
                      />
                    </div>
                    <span className="rv-commit-week">{t.week}</span>
                    <span className="rv-commit-num">{t.commits}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No commit activity in this period.</p>
            )}
          </Card>

          <Card title="File churn" meta={`${fileChurn.length} files`}>
            {fileChurn.length ? (
              <div className="rv-churn-list">
                {fileChurn.map((f) => (
                  <div className="rv-churn-row" key={f.name}>
                    <code className="rv-churn-path" title={f.name}>
                      {f.name}
                    </code>
                    <ProgressBar value={f.value} max={maxChurn} trailing={f.value} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No file churn recorded.</p>
            )}
          </Card>
        </div>

        <div className="rv-stack">
          <Card title="Branches">
            {branches.length ? (
              <div className="rv-branch-list">
                {branches.map((b) => (
                  <div className="rv-branch-row" key={b.name}>
                    <span className="rv-branch-dot" style={{ background: b.color }} />
                    <code className="rv-branch-name">{b.name}</code>
                    <span className="rv-branch-count">{b.commits}</span>
                    {b.active ? <Badge tone="accent">HEAD</Badge> : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No branches detected.</p>
            )}
          </Card>

          <Card title="Recent commits" meta={`${commits.length} shown`}>
            {commits.length ? (
              <div className="rv-commit-list">
                {commits.map((c) => (
                  <div className="rv-commit-row" key={c.hash}>
                    <div className="rv-commit-row-main">
                      <code className="rv-hash">{c.hash}</code>
                      <span className="rv-commit-msg" title={c.message}>
                        {c.message}
                      </span>
                    </div>
                    <div className="rv-commit-row-meta">
                      <span className="rv-commit-author">{c.author}</span>
                      <span className="rv-commit-time">{fmtTime(c.time)}</span>
                      <span className="rv-commit-diff">
                        <b className="is-add">+{c.inserts}</b>{' '}
                        <b className="is-del">−{c.deletes}</b>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rv-muted-block">No commits in this window.</p>
            )}
          </Card>
        </div>
      </div>
    </ViewShell>
  )
}
