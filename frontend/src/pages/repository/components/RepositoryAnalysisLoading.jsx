// Repository Intelligence loading view — replaces the old bare "Analyzing
// repository…" spinner with a staged, animated progress experience that mirrors
// the real layout (header chrome + tabs + content skeleton), so the transition
// into Repository Intelligence feels intentional rather than a blank screen.
import { useEffect, useMemo, useState } from 'react';

const STAGES = [
  { at: 0, label: 'Queued', detail: 'Preparing the analysis run' },
  { at: 5, label: 'Cloning repository', detail: 'Fetching the latest commit' },
  { at: 30, label: 'Mapping structure', detail: 'Walking the file tree and modules' },
  { at: 55, label: 'Analyzing architecture', detail: 'Resolving dependencies and data flow' },
  { at: 80, label: 'Scoring risk & health', detail: 'Churn, complexity, ownership, coverage' },
  { at: 100, label: 'Finalizing', detail: 'Building the visualization' },
];

export default function RepositoryAnalysisLoading({ progress = 0, status = 'queued', name = 'repository' }) {
  const [visible, setVisible] = useState(() => Math.max(0, Math.min(100, Math.round(progress))));
  const [elapsed, setElapsed] = useState(0);

  // Smoothly approach the server-reported progress so the bar never jumps.
  useEffect(() => {
    const target = Math.max(0, Math.min(100, Math.round(progress || 0)));
    const timer = setInterval(() => {
      setVisible((prev) => {
        if (prev >= target) return prev;
        return Math.min(target, prev + Math.max(1, Math.round((target - prev) / 6)));
      });
    }, 90);
    return () => clearInterval(timer);
  }, [progress]);

  // Gentle timer so the UI always feels alive even when a stage stalls.
  useEffect(() => {
    const timer = setInterval(() => setElapsed((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const activeStage = useMemo(() => {
    let idx = 0;
    for (const s of STAGES) {
      if (visible >= s.at) idx = STAGES.indexOf(s);
    }
    return STAGES[idx] || STAGES[0];
  }, [visible]);

  const completed = STAGES.filter((s) => visible > s.at);
  const pending = STAGES.filter((s) => visible < s.at);

  return (
    <main className="app-shell intel-shell">
      <div className="intel-analyzing" role="status" aria-live="polite">
        <div className="intel-analyzing-card">
          <header className="intel-analyzing-head">
            <div className="intel-analyzing-icon" aria-hidden="true">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
              </svg>
            </div>
            <div className="intel-analyzing-identity">
              <div className="intel-analyzing-title">Repository Intelligence</div>
              <div className="intel-analyzing-sub">{name}</div>
            </div>
            <div className="intel-analyzing-pill">
              <span className="intel-analyzing-dot" />
              <span>{status === 'queued' ? 'Queued' : 'Analyzing'}</span>
            </div>
          </header>

          <div className="intel-analyzing-progress">
            <div className="intel-analyzing-bar">
              <span className="intel-analyzing-fill" style={{ width: `${visible}%` }} />
            </div>
            <div className="intel-analyzing-percent">{visible}%</div>
          </div>

          <div className="intel-analyzing-stage">
            <div className="intel-analyzing-stage-label">{activeStage.label}</div>
            <div className="intel-analyzing-stage-detail">{activeStage.detail}</div>
            <div className="intel-analyzing-meta">
              {status !== 'queued' ? (
                <span className="intel-analyzing-live">
                  <span className="intel-analyzing-live-dot" />
                  Working… {elapsed}s
                </span>
              ) : null}
            </div>
          </div>

          <ul className="intel-steps" aria-hidden="true">
            {STAGES.map((s) => {
              const state = visible > s.at ? 'done' : visible >= s.at ? 'active' : 'pending';
              return (
                <li key={s.label} className={`intel-step is-${state}`}>
                  <span className="intel-step-index">
                    {state === 'done' ? (
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                    ) : null}
                  </span>
                  <span className="intel-step-label">{s.label}</span>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Skeleton preview of the layout so the destination reads as imminent. */}
        <div className="intel-skeleton" aria-hidden="true">
          <div className="intel-skeleton-header">
            <span className="skeleton-block w-40" />
            <span className="skeleton-block w-24" />
          </div>
          <div className="intel-skeleton-tabs">
            <span className="skeleton-pill" />
            <span className="skeleton-pill" />
            <span className="skeleton-pill" />
          </div>
          <div className="intel-skeleton-body">
            <span className="skeleton-block h-10 w-full" />
            <span className="skeleton-block h-40 w-full" />
            <span className="skeleton-block h-32 w-3/4" />
          </div>
        </div>
      </div>
    </main>
  );
}
