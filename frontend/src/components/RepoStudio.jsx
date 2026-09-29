// Repository Studio — a GitHub-project-only rail of compact analysis tools.
//
// The rail itself is buttons only; every tool's output renders in the main
// window (see `StudioView`).  Architecture Diagram, Dependency & Tech Stack and
// Health Score & Hotspots are backed by real generators — Security & Quality is
// still a placeholder with no backend.  Document and web projects never see this
// (see Home's project-type gate).
//
// Original ContextForge visuals; NotebookLM's Studio is UX inspiration only.

import ArchitectureDiagram from './ArchitectureDiagram'
import HealthReport from './HealthReport'
import SecurityReport from './SecurityReport'
import TechStackReport from './TechStackReport'

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

export default function RepoStudio({ repoName, active, onSelect }) {
  return (
    <div className="repo-studio">
      <div className="rs-head">
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

// Each analysis tool targets a single source; `sourceId`, `sources` and
// `onSourceChange` are threaded straight through so the tool's header can offer
// a picker.  Repo Chat is the exception and is not rendered here.
export function StudioView({
  tool,
  projectId,
  hasGithubSource,
  sourceId,
  sources,
  onSourceChange,
}) {
  const shared = {
    projectId,
    hasGithubSource,
    sourceId,
    sources,
    onSourceChange,
  }
  switch (tool) {
    case 'architecture':
      return <ArchitectureDiagram {...shared} />
    case 'security':
      return <SecurityReport {...shared} />
    case 'stack':
      return <TechStackReport {...shared} />
    case 'health':
      return <HealthReport {...shared} />
    default:
      return null
  }
}
