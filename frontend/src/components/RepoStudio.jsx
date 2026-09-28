// Repository Studio — a GitHub-project-only rail of compact analysis tools.
//
// Frontend UI + local interactions only: every tool renders a clearly-labelled
// placeholder preview.  No backend calls, no data processing.  Document and
// web projects never see this panel (see Home's project-type gate).
//
// Original ContextForge visuals; NotebookLM's Studio is UX inspiration only.

function DiagramIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
      <path d="M10 6.5h5.5a2 2 0 0 1 2 2V14" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  )
}

function StackIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3l9 5-9 5-9-5z" />
      <path d="M3 13l9 5 9-5" />
    </svg>
  )
}

function GaugeIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M5 19a9 9 0 1 1 14 0" />
      <path d="M12 13l4-4" />
      <circle cx="12" cy="13" r="1.4" fill="currentColor" />
    </svg>
  )
}

function ChatIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

const TOOLS = [
  {
    id: 'architecture',
    label: 'Architecture Diagram',
    hint: 'Module map at a glance',
    Icon: DiagramIcon,
  },
  {
    id: 'security',
    label: 'Security & Quality',
    hint: 'Secrets & dependency checks',
    Icon: ShieldIcon,
  },
  {
    id: 'stack',
    label: 'Dependency & Tech Stack',
    hint: 'Languages & frameworks',
    Icon: StackIcon,
  },
  {
    id: 'health',
    label: 'Health Score & Hotspots',
    hint: 'Score, churn & hotspots',
    Icon: GaugeIcon,
  },
  { id: 'chat', label: 'Repo Chat', hint: 'Ask about the repo', Icon: ChatIcon },
]

function ArchitectureView() {
  return (
    <div className="rs-view">
      <div className="rs-view-head">
        <h3>Architecture Diagram</h3>
      </div>
      <svg className="rs-diagram" viewBox="0 0 300 176" role="img" aria-label="Module map sketch">
        <rect x="14" y="14" width="82" height="36" rx="10" />
        <rect x="109" y="14" width="82" height="36" rx="10" />
        <rect x="204" y="14" width="82" height="36" rx="10" />
        <rect x="14" y="92" width="82" height="36" rx="10" />
        <rect x="109" y="92" width="82" height="36" rx="10" />
        <rect x="204" y="92" width="82" height="36" rx="10" />
        <path d="M96 32h13M191 32h13M55 50v26a8 8 0 0 0 8 8h-8M150 50v26a8 8 0 0 0 8 8h-8M245 50v26M96 110h13M191 110h13" />
        <circle cx="150" cy="152" r="3.5" className="rs-diagram-dot" />
        <path d="M150 128v16" />
        <text x="55" y="36">
          client
        </text>
        <text x="150" y="36">
          api
        </text>
        <text x="245" y="36">
          db
        </text>
        <text x="55" y="114">
          auth
        </text>
        <text x="150" y="114">
          core
        </text>
        <text x="245" y="114">
          jobs
        </text>
        <text x="150" y="170">
          entry
        </text>
      </svg>
      <p className="rs-view-hint">
        Module map of the repository — areas, dependencies and entry points at a glance.
      </p>
    </div>
  )
}

function SecurityView() {
  const rows = [
    { state: 'ok', label: 'No hardcoded secrets detected', detail: 'Clean' },
    { state: 'warn', label: '2 outdated dependencies', detail: 'Review' },
    { state: 'ok', label: 'Branch protection on main', detail: 'On' },
    { state: 'info', label: 'License file present', detail: 'MIT' },
  ]
  return (
    <div className="rs-view">
      <div className="rs-view-head">
        <h3>Security & Quality</h3>
      </div>
      <ul className="rs-checks">
        {rows.map((row) => (
          <li key={row.label} className={`rs-check is-${row.state}`}>
            <span className="rs-dot" aria-hidden="true" />
            <span className="rs-check-file">{row.label}</span>
            <span className="rs-check-note">{row.detail}</span>
          </li>
        ))}
      </ul>
      <p className="rs-view-hint">Secrets, vulnerable packages and quality gates per module.</p>
    </div>
  )
}

function StackView() {
  const stack = ['Python', 'Docker', 'React', 'PostgreSQL']
  return (
    <div className="rs-view">
      <div className="rs-view-head">
        <h3>Dependency & Tech Stack</h3>
      </div>
      <div className="rs-chips">
        {stack.map((name) => (
          <span key={name} className="rs-chip">
            {name}
          </span>
        ))}
      </div>
      <ul className="rs-checks">
        {[
          { file: 'fastapi', note: 'web framework', level: 'info' },
          { file: 'sqlalchemy', note: 'data layer', level: 'info' },
          { file: 'httpx', note: 'http client', level: 'info' },
        ].map((item) => (
          <li key={item.file} className={`rs-check is-${item.level}`}>
            <span className="rs-dot" aria-hidden="true" />
            <span className="rs-check-file">{item.file}</span>
            <span className="rs-check-note">{item.note}</span>
          </li>
        ))}
      </ul>
      <p className="rs-view-hint">
        Languages, frameworks and the dependency graph between modules.
      </p>
    </div>
  )
}

function HealthView() {
  const score = 82
  const radius = 34
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (circumference * score) / 100
  const hotspots = [
    { file: 'auth.py', note: 'High churn', level: 'warn' },
    { file: 'legacy.py', note: 'No tests', level: 'warn' },
    { file: 'utils.py', note: 'Complex', level: 'info' },
  ]
  return (
    <div className="rs-view">
      <div className="rs-view-head">
        <h3>Health Score & Hotspots</h3>
      </div>
      <div className="rs-health-top">
        <svg className="rs-ring" viewBox="0 0 84 84" aria-hidden="true">
          <circle cx="42" cy="42" r={radius} className="rs-ring-track" />
          <circle
            cx="42"
            cy="42"
            r={radius}
            className="rs-ring-value"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="rs-health-number">
          <strong>{score}</strong>
          <span>Good</span>
        </div>
      </div>
      <ul className="rs-checks">
        {hotspots.map((item) => (
          <li key={item.file} className={`rs-check is-${item.level}`}>
            <span className="rs-dot" aria-hidden="true" />
            <span className="rs-check-file">{item.file}</span>
            <span className="rs-check-note">{item.note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function RepoStudio({ repoName, active, onSelect }) {
  return (
    <div className="repo-studio">
      <div className="rs-head">
        <span className="ev-eyebrow">Studio</span>
        <h3 className="rs-title" title={repoName}>
          {repoName || 'Repository'}
        </h3>
      </div>

      <div className="rs-grid" role="group" aria-label="Repository tools">
        {TOOLS.slice(0, 4).map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className={`rs-tool${active === id ? ' is-active' : ''}`}
            aria-pressed={active === id}
            onClick={() => onSelect?.(id)}
          >
            <span className={`rs-tool-icon is-${id}`} aria-hidden="true">
              <Icon />
            </span>
            <span>{label}</span>
          </button>
        ))}
        <button
          type="button"
          className={`rs-tool is-wide${active === 'chat' ? ' is-active' : ''}`}
          aria-pressed={active === 'chat'}
          onClick={() => onSelect?.('chat')}
        >
          <span className="rs-tool-icon is-chat" aria-hidden="true">
            <ChatIcon />
          </span>
          <span>Repo Chat</span>
        </button>
      </div>

      <span className="rs-footnote">Outputs open in the main window.</span>
    </div>
  )
}

export const STUDIO_TOOLS = TOOLS.map(({ id, label, hint, Icon }) => ({
  id,
  label,
  hint,
  Icon,
}))

export function StudioView({ tool }) {
  switch (tool) {
    case 'security':
      return <SecurityView />
    case 'stack':
      return <StackView />
    case 'health':
      return <HealthView />
    case 'architecture':
    default:
      return <ArchitectureView />
  }
}
