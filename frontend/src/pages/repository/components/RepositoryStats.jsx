import { Card, formatNumber } from '../ui/primitives'

// Repository overview stats shown in the right-hand insight rail.
const ITEMS = [
  { label: 'Files', key: 'files' },
  { label: 'Modules', key: 'modules' },
  { label: 'Commits', key: 'commits' },
  { label: 'Contributors', key: 'contributors' },
  { label: 'Branches', key: 'branches' },
  { label: 'Pull requests', key: 'pullRequests' },
  { label: 'Issues', key: 'issues' },
]

export default function RepositoryStats({ stats = {} }) {
  return (
    <Card title="Repository Overview" className="rv-rail-card">
      <div className="rv-stat-grid">
        {ITEMS.map((item) => (
          <div className="rv-stat-cell" key={item.label}>
            <span className="rv-stat-cell-value">{formatNumber(stats[item.key])}</span>
            <span className="rv-stat-cell-label">{item.label}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
