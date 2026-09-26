import { IconBranch, IconGlobe, IconLock, IconSync } from '../ui/icons'
import { formatNumber } from '../ui/primitives'

function formatAnalyzed(iso) {
  if (!iso) return 'Never'
  try {
    return new Date(iso).toLocaleString('en-GB', {
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

// Repository identity bar. The source explore header already carries the
// GitHub URL, so this bar focuses on what the analysis actually needs: identity,
// visibility, branch, headline counts and the analyze/sync action.
export default function RepositoryHeader({ repo = {}, onSync, syncing = false }) {
  const fullName = repo.fullName || repo.name || 'Repository'
  const visibility = repo.visibility === 'private' ? 'private' : 'public'
  const branch = repo.branch || repo.defaultBranch || '—'
  const language = repo.language

  const facts = [
    { label: 'Files', value: formatNumber(repo.files) },
    { label: 'Modules', value: formatNumber(repo.modules) },
    { label: 'Commits', value: formatNumber(repo.commits) },
    { label: 'Contributors', value: formatNumber(repo.contributors) },
  ]

  return (
    <header className="rv-repo-header">
      <div className="rv-repo-identity">
        <span className="rv-repo-mark" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
          </svg>
        </span>
        <div className="rv-repo-name-block">
          <div className="rv-repo-name-row">
            <span className="rv-repo-name">{fullName}</span>
            <span className={`rv-visibility is-${visibility}`}>
              {visibility === 'private' ? (
                <IconLock width={11} height={11} />
              ) : (
                <IconGlobe width={11} height={11} />
              )}
              {visibility}
            </span>
            {language ? <span className="rv-language">{language}</span> : null}
          </div>
          <div className="rv-repo-meta-row">
            <span className="rv-repo-branch">
              <IconBranch width={12} height={12} />
              {branch}
            </span>
            <span className="rv-meta-dot" />
            <span className="rv-repo-analyzed">Analyzed {formatAnalyzed(repo.lastAnalyzed)}</span>
          </div>
        </div>
      </div>

      <div className="rv-repo-header-right">
        <dl className="rv-repo-facts">
          {facts.map((f) => (
            <div className="rv-repo-fact" key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
        <button
          type="button"
          className={`rv-btn rv-btn-secondary${syncing ? ' is-busy' : ''}`}
          onClick={onSync}
          disabled={syncing}
        >
          <IconSync width={15} height={15} className={syncing ? 'rv-spin' : ''} />
          {syncing ? 'Syncing' : 'Sync'}
        </button>
      </div>
    </header>
  )
}
