import { repo } from '../../../data/repoIntelligence';

function formatAnalyzed(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

export default function RepositoryHeader({ onSync }) {
  return (
    <header className="repo-header">
      <div className="repo-header-left">
        <div className="repo-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
          </svg>
        </div>
        <div className="repo-identity">
          <div className="repo-line">
            <span className="repo-name">{repo.fullName}</span>
            <span className={`repo-visibility is-${repo.visibility}`}>{repo.visibility === 'public' ? 'Public' : 'Private'}</span>
            <span className="repo-branch">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9" /></svg>
              {repo.branch}
            </span>
          </div>
          <p className="repo-desc">{repo.description}</p>
          <div className="repo-stats">
            <span><b>{repo.files.toLocaleString()}</b> files</span>
            <span><b>{repo.modules}</b> modules</span>
            <span><b>{repo.commits.toLocaleString()}</b> commits</span>
            <span><b>{repo.contributors}</b> contributors</span>
            <span className="repo-analyzed">Analyzed {formatAnalyzed(repo.lastAnalyzed)}</span>
          </div>
        </div>
      </div>

      <div className="repo-header-right">
        <div className="repo-ask-input">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
          <input placeholder="Ask anything about this repository..." spellCheck={false} />
          <span className="repo-ask-kbd">⌘K</span>
        </div>
        <button className="sync-btn" onClick={onSync}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
          Sync
        </button>
      </div>
    </header>
  );
}
