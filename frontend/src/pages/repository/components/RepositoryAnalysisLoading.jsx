// Repository Intelligence loading view. A staged, animated progress experience
// that mirrors the destination layout (identity bar + tabs + content skeleton)
// so the transition into Repository Intelligence reads as intentional.
import { useEffect, useMemo, useState } from 'react'
import { IconCheck } from '../ui/icons'

const STAGES = [
  { at: 0, label: 'Queued', detail: 'Preparing the analysis run' },
  { at: 5, label: 'Cloning repository', detail: 'Fetching the latest commit' },
  { at: 30, label: 'Mapping structure', detail: 'Walking the file tree and modules' },
  { at: 55, label: 'Analyzing architecture', detail: 'Resolving dependencies and data flow' },
  { at: 80, label: 'Scoring risk & health', detail: 'Churn, complexity, ownership, coverage' },
  { at: 100, label: 'Finalizing', detail: 'Building the visualization' },
]

export default function RepositoryAnalysisLoading({
  progress = 0,
  status = 'queued',
  name = 'repository',
  embedded = false,
}) {
  const [visible, setVisible] = useState(() => Math.max(0, Math.min(100, Math.round(progress))))

  useEffect(() => {
    const target = Math.max(0, Math.min(100, Math.round(progress || 0)))
    const timer = setInterval(() => {
      setVisible((prev) => {
        if (prev >= target) return prev
        return Math.min(target, prev + Math.max(1, Math.round((target - prev) / 6)))
      })
    }, 90)
    return () => clearInterval(timer)
  }, [progress])

  const activeStage = useMemo(() => {
    let idx = 0
    STAGES.forEach((s, i) => {
      if (visible >= s.at) idx = i
    })
    return STAGES[idx] || STAGES[0]
  }, [visible])

  const card = (
    <div
      className={`rv-analyzing${embedded ? ' is-embedded' : ''}`}
      role="status"
      aria-live="polite"
    >
      <div className="rv-analyzing-card">
        <header className="rv-analyzing-head">
          <div className="rv-analyzing-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
            </svg>
          </div>
          <div className="rv-analyzing-identity">
            <div className="rv-analyzing-title">Repository Intelligence</div>
            <div className="rv-analyzing-sub">{name}</div>
          </div>
          <div className="rv-analyzing-pill">
            <span className="rv-analyzing-dot" />
            <span>{status === 'queued' ? 'Queued' : 'Analyzing'}</span>
          </div>
        </header>

        <div className="rv-analyzing-progress">
          <div className="rv-analyzing-bar">
            <span className="rv-analyzing-fill" style={{ width: `${visible}%` }} />
          </div>
          <div className="rv-analyzing-percent">{visible}%</div>
        </div>

        <div className="rv-analyzing-stage">
          <div className="rv-analyzing-stage-label">{activeStage.label}</div>
          <div className="rv-analyzing-stage-detail">{activeStage.detail}</div>
        </div>

        <ul className="rv-analyzing-steps" aria-hidden="true">
          {STAGES.map((s) => {
            const state = visible > s.at ? 'done' : visible >= s.at ? 'active' : 'pending'
            return (
              <li key={s.label} className={`rv-analyzing-step is-${state}`}>
                <span className="rv-analyzing-step-index">
                  {state === 'done' ? <IconCheck width={11} height={11} strokeWidth={3} /> : null}
                </span>
                <span className="rv-analyzing-step-label">{s.label}</span>
              </li>
            )
          })}
        </ul>
      </div>

      <div className="rv-analyzing-skeleton" aria-hidden="true">
        <div className="rv-skeleton-head">
          <span className="rv-skeleton w-40" />
          <span className="rv-skeleton w-24" />
        </div>
        <div className="rv-skeleton-tabs">
          <span className="rv-skeleton-pill" />
          <span className="rv-skeleton-pill" />
          <span className="rv-skeleton-pill" />
        </div>
        <span className="rv-skeleton h-40 w-full" />
        <span className="rv-skeleton h-24 w-3/4" />
      </div>
    </div>
  )

  if (embedded) return card
  return <main className="app-shell rv-analyzing-shell">{card}</main>
}
