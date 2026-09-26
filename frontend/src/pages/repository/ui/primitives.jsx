// Shared UI primitives for Repository Intelligence.
//
// Every repository sub-view is built from this small, opinionated kit so the
// six capabilities read as one product: the same toolbar rhythm, card chrome,
// metric tiles, bars, badges and empty/error states. Pure presentational
// components — no data fetching, no view logic.

// --- Layout -----------------------------------------------------------------

export function ViewShell({ children, className = '' }) {
  return <div className={`intel-view ${className}`.trim()}>{children}</div>
}

export function ViewToolbar({ left, right, className = '' }) {
  return (
    <div className={`rv-toolbar ${className}`.trim()}>
      {left ? <div className="rv-toolbar-left">{left}</div> : null}
      {right ? <div className="rv-toolbar-right">{right}</div> : null}
    </div>
  )
}

export function Card({ title, meta, actions, children, className = '', padded = true }) {
  return (
    <section className={`rv-card ${padded ? '' : 'rv-card-flush'} ${className}`.trim()}>
      {title || actions ? (
        <div className="rv-card-head">
          <div className="rv-card-head-copy">
            {title ? <span className="rv-card-title">{title}</span> : null}
            {meta ? <span className="rv-card-meta">{meta}</span> : null}
          </div>
          {actions ? <div className="rv-card-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

export function Grid({ columns = 'auto', className = '', children }) {
  return <div className={`rv-grid rv-grid-${columns} ${className}`.trim()}>{children}</div>
}

// --- Data display -----------------------------------------------------------

export function StatTile({ label, value, hint, tone = 'default', icon }) {
  return (
    <div className={`rv-stat is-${tone}`}>
      {icon ? <span className="rv-stat-icon">{icon}</span> : null}
      <span className="rv-stat-value">{value ?? '—'}</span>
      <span className="rv-stat-label">{label}</span>
      {hint ? <span className="rv-stat-hint">{hint}</span> : null}
    </div>
  )
}

export function Metric({ label, value }) {
  return (
    <div className="rv-metric">
      <span className="rv-metric-label">{label}</span>
      <span className="rv-metric-value">{value ?? '—'}</span>
    </div>
  )
}

export function StackedBar({ segments = [], className = '' }) {
  const total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 1
  return (
    <div className={`rv-stacked ${className}`.trim()}>
      {segments.map((s) => (
        <span
          key={s.label}
          className="rv-stacked-seg"
          style={{ width: `${((s.value || 0) / total) * 100}%`, background: s.color }}
          title={`${s.label}: ${s.value}`}
        />
      ))}
    </div>
  )
}

export function ProgressBar({ value, max = 100, tone = 'accent', label, trailing }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return (
    <div className="rv-progress">
      {label ? <span className="rv-progress-label">{label}</span> : null}
      <div className="rv-progress-track">
        <span className={`rv-progress-fill is-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {trailing != null ? <span className="rv-progress-trailing">{trailing}</span> : null}
    </div>
  )
}

export function Badge({ children, tone = 'neutral', title }) {
  return (
    <span className={`rv-badge is-${tone}`} title={title}>
      {children}
    </span>
  )
}

export function Legend({ items = [] }) {
  return (
    <div className="rv-legend">
      {items.map((item) => (
        <span key={item.label} className="rv-legend-item">
          <i className="rv-legend-dot" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

// --- States -----------------------------------------------------------------

export function EmptyState({ title, hint, action }) {
  return (
    <div className="rv-state rv-state-empty">
      <span className="rv-state-icon" aria-hidden="true">
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 3v18h18" />
          <path d="M7 15l3-4 3 3 4-6" />
        </svg>
      </span>
      <p className="rv-state-title">{title}</p>
      {hint ? <p className="rv-state-hint">{hint}</p> : null}
      {action}
    </div>
  )
}

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="rv-state rv-state-loading">
      <span className="rv-spinner" aria-hidden="true" />
      <p className="rv-state-hint">{label}</p>
    </div>
  )
}

export function ErrorState({ title = 'Something went wrong', message, action }) {
  return (
    <div className="rv-state rv-state-error">
      <span className="rv-state-icon" aria-hidden="true">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5M12 16h.01" />
        </svg>
      </span>
      <p className="rv-state-title">{title}</p>
      {message ? <p className="rv-state-hint">{message}</p> : null}
      {action}
    </div>
  )
}

// --- Formatting helpers -----------------------------------------------------

export function formatNumber(value) {
  if (value == null) return '—'
  return Number(value).toLocaleString()
}

export function formatCompact(value) {
  if (value == null) return '—'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

export function riskTone(risk) {
  return String(risk || 'low').toLowerCase()
}
