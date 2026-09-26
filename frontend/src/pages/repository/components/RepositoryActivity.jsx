import { Card } from '../ui/primitives'
import { IconArrowRight, IconCommit } from '../ui/icons'

function timeAgo(iso) {
  try {
    const d = new Date(iso)
    const secs = Math.round((Date.now() - d.getTime()) / 1000)
    if (secs < 60) return 'just now'
    const mins = Math.round(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    const days = Math.round(hrs / 24)
    if (days < 30) return `${days}d ago`
    return d.toLocaleDateString('en-GB')
  } catch {
    return '—'
  }
}

export default function RepositoryActivity({ activity = [], onViewHistory }) {
  return (
    <Card title="Recent Activity" meta={`${activity.length} events`} className="rv-rail-card">
      {activity.length ? (
        <div className="rv-activity-list">
          {activity.map((a) => (
            <div className="rv-activity-row" key={a.id}>
              <span className="rv-activity-icon">
                <IconCommit width={13} height={13} />
              </span>
              <div className="rv-activity-body">
                <div className="rv-activity-msg" title={a.message}>
                  {a.message}
                </div>
                <div className="rv-activity-meta">
                  <code className="rv-hash">{a.hash}</code>
                  <span className="rv-activity-author">{a.author}</span>
                </div>
              </div>
              <span className="rv-activity-time">{timeAgo(a.time)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="rv-muted-block">No recent activity recorded.</p>
      )}

      <button
        type="button"
        className="rv-btn rv-btn-secondary rv-btn-block"
        onClick={onViewHistory}
      >
        View full commit history <IconArrowRight width={14} height={14} />
      </button>
    </Card>
  )
}
