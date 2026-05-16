function formatSourceTitle(source) {
  const meta = source.metadata || {};
  return meta.filename || meta.title || source.source_id || 'Unknown source';
}

function formatSourceType(source) {
  const meta = source.metadata || {};
  return meta.source_type || meta.type || 'doc';
}

function chunkIcon(type) {
  switch (type) {
    case 'pdf':
    case 'docx':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <rect x="2" y="2" width="20" height="20" rx="4" fill="#EF4444" />
          <rect x="2" y="2" width="13" height="7" rx="4" fill="#DC2626" />
          <text x="12" y="16" textAnchor="middle" fill="white" fontSize="7" fontWeight="bold" fontFamily="Arial,sans-serif">PDF</text>
        </svg>
      );
    case 'web':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
      );
    case 'github':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
        </svg>
      );
    default:
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      );
  }
}

function iconClass(type) {
  switch (type) {
    case 'pdf': return 'chunk-icon is-pdf';
    case 'web': return 'chunk-icon is-web';
    case 'github': return 'chunk-icon is-github';
    default: return 'chunk-icon';
  }
}

function extractDomain(url) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

function formatChunkMeta(source) {
  const meta = source.metadata || {};
  const type = formatSourceType(source);

  if (type === 'web' && meta.url) {
    const domain = extractDomain(meta.url);
    return domain || meta.url;
  }
  if (type === 'github') {
    return meta.repo || meta.title || 'GitHub Repository';
  }
  if (meta.page) {
    return `Page ${meta.page}`;
  }
  return `Chunk ${source.rank}`;
}

function formatTypeLabel(type) {
  switch (type) {
    case 'pdf': return 'PDF';
    case 'web': return 'Web';
    case 'github': return 'GitHub';
    default: return type.toUpperCase();
  }
}

function Skeleton({ width, height }) {
  return (
    <div
      className="skeleton-pulse"
      style={{ width: width || '100%', height: height || '14px', borderRadius: '4px' }}
    />
  );
}

// FIX: accept confidence prop from the backend; default to null for loading state
export default function SourceViewer({ sources = [], latency = {}, isStreaming, confidence = null }) {
  const hasSources = sources.length > 0;
  const isLoading = isStreaming && !hasSources;

  // FIX: use server-side confidence — no sigmoid math in the frontend
  const displayConfidence = confidence
    ? Math.round(confidence.answer_confidence * 100)
    : 0;
  const coverage = confidence?.source_coverage ?? 'Pending';
  const sourcesUsed = confidence?.sources_used ?? 0;
  const retrievedChunks = confidence?.retrieved_chunks ?? sources.length;
  const retrieveMs = latency?.retrieve_ms;

  const showEmpty = !isLoading && !hasSources;

  const circumference = 2 * Math.PI * 46;
  const offset = circumference - (circumference * Math.min(displayConfidence, 100)) / 100;

  return (
    <aside className="evidence">
      <div className="evidence-tabs">
        <button className="tab active">Evidence</button>
        <button className="tab">Debug</button>
        <button className="tab">Statistics</button>
      </div>

      <section className="panel panel-scroll">
        <div className="panel-head">
          <h3>Top Retrieved Chunks</h3>
          <span className="muted">
            {isLoading ? (
              <Skeleton width="80px" height="14px" />
            ) : hasSources ? (
              `${sources.length} sources`
            ) : (
              'No sources yet'
            )}
          </span>
        </div>
        <div className="chunk-list">
          {isLoading ? (
            <div className="empty" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[1, 2, 3].map((i) => (
                <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                  <Skeleton width="32px" height="32px" />
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <Skeleton width="60%" height="14px" />
                    <Skeleton width="35%" height="10px" />
                    <Skeleton width="90%" height="10px" />
                  </div>
                </div>
              ))}
            </div>
          ) : hasSources ? (
              sources.map((item) => {
              const type = formatSourceType(item);
              return (
                <article className="chunk" key={item.chunk_id}>
                  <div className={iconClass(type)}>
                    {chunkIcon(type)}
                  </div>
                  <div className="chunk-title">{formatSourceTitle(item)}</div>
                  <div className="chunk-type">{formatTypeLabel(type)}</div>
                  <div className="chunk-meta">{formatChunkMeta(item)}</div>
                  {item.text_preview ? (
                    <p className="chunk-text">{item.text_preview}</p>
                  ) : null}
                </article>
              );
            })
          ) : (
            <div className="empty">Ask a question to populate sources.</div>
          )}
        </div>
        {hasSources && <button className="ghost wide">View all retrieved chunks</button>}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>Confidence & Coverage</h3>
        </div>
        {isLoading || showEmpty ? (
          <div className="confidence">
            {isLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', alignItems: 'center' }}>
                <Skeleton width="120px" height="120px" style={{ borderRadius: '50%' }} />
                <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Skeleton width="100px" height="14px" />
                      <Skeleton width="50px" height="14px" />
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="empty" style={{ textAlign: 'center', padding: '20px 0' }}>
                No retrieval data
              </div>
            )}
          </div>
        ) : (
          <div className="confidence">
            <div className="donut">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="46" className="track" />
                <circle
                  cx="60"
                  cy="60"
                  r="46"
                  className="value"
                  strokeDasharray={circumference}
                  strokeDashoffset={offset}
                />
              </svg>
              <div className="donut-value">
                <strong>{displayConfidence}%</strong>
                <span>Confidence</span>
              </div>
            </div>
            <div className="confidence-list">
              <div>
                <span>Answer Confidence</span>
                <strong>{displayConfidence}%</strong>
              </div>
              <div>
                <span>Source Coverage</span>
                <strong>{coverage}</strong>
              </div>
              <div>
                <span>Sources Used</span>
                <strong>{sourcesUsed}</strong>
              </div>
              <div>
                <span>Retrieved Chunks</span>
                <strong>{retrievedChunks}</strong>
              </div>
              <div>
                <span>Retrieval Time</span>
                <strong>{retrieveMs != null ? `${retrieveMs.toFixed(0)} ms` : '-'}</strong>
              </div>
            </div>
          </div>
        )}
      </section>
    </aside>
  );
}
