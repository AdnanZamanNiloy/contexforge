import { useNavigate } from 'react-router-dom';

import { GithubMark, SOURCE_STATUS, SourceGlyph, formatSourceMeta, sourceIconClass } from '../../lib/sources';

function Brand() {
  const navigate = useNavigate();
  return (
    <button className="brand brand-link" onClick={() => navigate('/')} title="ContextForge workspace">
      <div className="brand-mark" aria-hidden="true">
        <img src="/logos/project_logo.png" alt="ContextForge" />
      </div>
      <div className="brand-text">
        <span className="brand-title">
          Context<span className="brand-title-accent">Forge</span>
        </span>
        <small>Grounded AI Workspace</small>
      </div>
    </button>
  );
}

// The shared knowledge navigator.  Every page renders the same sidebar so the
// brand, the workspace entry point, the knowledge-base categories and the source
// list are identical across the whole product.
export default function Sidebar({
  sources = [],
  loading = false,
  activeSourceId = null,
  onAddSource,
  onSelectSource,
  onDeleteSource,
  onClearKB,
  header,
}) {
  const indexedCount = sources.filter((s) => s.status === 'indexed').length;
  const processingCount = sources.filter((s) => s.status === 'processing').length;
  const pdfCount = sources.filter((s) => s.type === 'pdf').length;
  const webCount = sources.filter((s) => s.type === 'web').length;
  const githubCount = sources.filter((s) => s.type === 'github').length;
  const youtubeCount = sources.filter((s) => s.type === 'youtube').length;

  const kbRows = [
    { id: 'all', label: 'All Documents', count: sources.length, icon: <SourceGlyph type="text" size={16} /> },
    { id: 'pdf', label: 'PDFs', count: pdfCount, icon: <SourceGlyph type="pdf" size={16} /> },
    { id: 'web', label: 'Web Pages', count: webCount, icon: <SourceGlyph type="web" size={16} /> },
    { id: 'github', label: 'GitHub Repos', count: githubCount, icon: <GithubMark size={16} /> },
    { id: 'youtube', label: 'YouTube Videos', count: youtubeCount, icon: <SourceGlyph type="youtube" size={16} /> },
  ];

  return (
    <aside className="sidebar-shell">
      <Brand />

      <button className="add-knowledge-btn" onClick={onAddSource}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span>Add Source</span>
      </button>

      {header}

      <section className="kb-section">
        <div className="section-title">Knowledge Base</div>
        <div className="kb-rows">
          {kbRows.map((row) => (
            <div className="kb-row" key={row.id}>
              {row.icon}
              <span className="kb-label">{row.label}</span>
              <span className="kb-count">{row.count}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="sources-section">
        <div className="section-title">
          <span>My Sources</span>
        </div>
        <div className="source-list">
          {loading && sources.length === 0 ? (
            <div className="empty-source">Loading sources…</div>
          ) : sources.length === 0 ? (
            <div className="empty-source">No sources added yet.</div>
          ) : (
            sources.map((source) => {
              const status = SOURCE_STATUS[source.status] || SOURCE_STATUS.processing;
              const active = source.id === activeSourceId;
              return (
                <div
                  className={`source-item-compact${active ? ' is-active' : ''}`}
                  key={source.id}
                  onClick={() => onSelectSource?.(source.id)}
                  role="button"
                  tabIndex={0}
                >
                  <div className={sourceIconClass(source.type)}>
                    <SourceGlyph type={source.type} size={16} />
                  </div>
                  <div className="source-item-body">
                    <div className="source-item-title">{source.title}</div>
                    <div className="source-item-meta">{formatSourceMeta(source)}</div>
                  </div>
                  <div className="source-item-status">
                    <span className={status.dot} title={status.label} />
                  </div>
                  <button
                    className="source-item-delete"
                    title="Delete"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteSource?.(source.id);
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              );
            })
          )}
        </div>
      </section>

      <div className="sidebar-spacer" />

      <div className="status-card">
        <div className="status-card-header">Processing Status</div>
        <div className="status-card-body">
          <div className="status-card-row">
            <span className="status-dot is-indexed" />
            <span>{indexedCount} sources indexed</span>
          </div>
          <div className="status-card-row">
            <span className={`status-dot ${processingCount > 0 ? 'is-processing' : 'is-indexed'}`} />
            <span>{processingCount > 0 ? `${processingCount} processing` : 'All idle'}</span>
          </div>
        </div>
        <button
          className="clear-kb-btn"
          onClick={onClearKB}
        >
          Clear Knowledge Base
        </button>
      </div>
    </aside>
  );
}
