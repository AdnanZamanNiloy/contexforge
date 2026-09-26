import { IconFlow, IconGitMerge, IconGrid, IconLayers, IconShield, IconUsers } from '../ui/icons'

// Primary capability navigation. Rendered as a proper tablist so keyboard and
// screen-reader users get the same affordance the pointer gets.
const TABS = [
  { id: 'architecture', label: 'Architecture', icon: IconGrid },
  { id: 'dependencies', label: 'Dependencies', icon: IconLayers },
  { id: 'data-flow', label: 'Data Flow', icon: IconFlow },
  { id: 'git-history', label: 'Git History', icon: IconGitMerge },
  { id: 'ownership', label: 'Ownership', icon: IconUsers },
  { id: 'change-impact', label: 'Change Impact', icon: IconShield },
]

export default function RepositoryTabs({ active, onChange }) {
  return (
    <nav className="rv-tabs" role="tablist" aria-label="Repository intelligence views">
      {TABS.map((tab) => {
        const Icon = tab.icon
        const isActive = active === tab.id
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`rv-tab${isActive ? ' is-active' : ''}`}
            onClick={() => onChange(tab.id)}
          >
            <Icon width={15} height={15} />
            <span>{tab.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
