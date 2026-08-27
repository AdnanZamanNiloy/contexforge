function formatAnalyzed(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '—'
  }
}

// Compact repository context bar. The repository name, GitHub identity and sync
// action are already presented by the source explore header above, so this only
// surfaces the fields Repository Intelligence actually needs: name · visibility
// · branch · essential metadata · Sync.
export default function RepositoryHeader({ repo = {}, onSync }) {
  const fullName = repo.fullName || repo.name || 'Repository'
  const visibility = repo.visibility || 'public'
  const branch = repo.branch || '—'
  const files = repo.files || 0
  const commits = repo.commits || 0

  return (
    <header className="repo-header">
      <div className="repo-context">
        <span className="repo-name">{fullName}</span>
        <span className={`repo-visibility is-${visibility}`}>
          {visibility === 'private' ? 'Private' : 'Public'}
        </span>
        <span className="repo-branch">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9" />
          </svg>
          {branch}
        </span>
      </div>

      <div className="repo-header-right">
        <span className="repo-meta">
          <span>
            <b>{files.toLocaleString()}</b> files
          </span>
          <span className="repo-meta-sep">·</span>
          <span>
            <b>{commits.toLocaleString()}</b> commits
          </span>
          <span className="repo-meta-sep">·</span>
          <span className="repo-analyzed">Analyzed {formatAnalyzed(repo.lastAnalyzed)}</span>
        </span>
        <button className="sync-btn" onClick={onSync}>
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Sync
        </button>
      </div>
    </header>
  )
}
