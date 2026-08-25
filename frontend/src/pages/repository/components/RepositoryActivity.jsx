function timeAgo(iso) {
  try {
    const d = new Date(iso);
    const secs = Math.round((Date.now() - d.getTime()) / 1000);
    if (secs < 60) return 'just now';
    const mins = Math.round(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.round(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return d.toLocaleDateString('en-GB');
  } catch {
    return '—';
  }
}

function kindIcon(kind) {
  if (kind === 'commit') {
    return (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 3v5M12 16v5M3 12h5M16 12h5" /></svg>
    );
  }
  return null;
}

export default function RepositoryActivity({ activity = [], onViewHistory }) {
  return (
    <section className="sidebar-section">
      <div className="sidebar-section-title">Recent Activity</div>
      <div className="activity-list">
        {activity.map((a) => (
          <div className="activity-row" key={a.id}>
            <span className="activity-icon">{kindIcon(a.kind)}</span>
            <div className="activity-body">
              <div className="activity-msg">{a.message}</div>
              <div className="activity-meta">
                <code className="commit-hash">{a.hash}</code>
                <span className="activity-author">{a.author}</span>
              </div>
            </div>
            <span className="activity-time">{timeAgo(a.time)}</span>
          </div>
        ))}
      </div>
      <button className="ghost wide" onClick={onViewHistory}>View Full Commit History →</button>
    </section>
  );
}
