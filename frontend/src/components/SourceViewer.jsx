function formatSourceTitle(source) {
  const meta = source.metadata || {};
  return meta.filename || meta.title || source.source_id || 'Unknown source';
}

function formatSourceType(source) {
  const meta = source.metadata || {};
  return meta.source_type || meta.type || 'DOC';
}

function formatSourceMeta(source) {
  const meta = source.metadata || {};
  if (meta.page) {
    return `Page ${meta.page}`;
  }
  if (meta.url) {
    return meta.url;
  }
  return `Chunk ${source.rank}`;
}

function Skeleton({ width, height }) {
  return (
    <div
      className="skeleton-pulse"
      style={{ width: width || '100%', height: height || '14px', borderRadius: '4px' }}
    />
  );
}

export default function SourceViewer({ sources = [], latency = {}, isStreaming }) {
  const hasSources = sources.length > 0;
  const isLoading = isStreaming && !hasSources;

  const scores = sources.map(s => s.score).filter(s => s != null);
  const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
  const confidence = Math.round(avgScore * 100);

  let coverage = 'Pending';
  if (hasSources) {
    if (avgScore > 0.75) coverage = 'High';
    else if (avgScore > 0.5) coverage = 'Medium';
    else coverage = 'Low';
  }

  const uniqueSourceIds = new Set(sources.map(s => s.source_id || s.metadata?.source_id));
  const sourcesUsed = uniqueSourceIds.size;
  const retrievedChunks = sources.length;
  const retrieveMs = latency?.retrieve_ms;

  const showEmpty = !isLoading && !hasSources;

  const circumference = 2 * Math.PI * 46;
  const offset = circumference - (circumference * Math.min(confidence, 100)) / 100;

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
            <div className="empty" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[1, 2, 3].map((i) => (
                <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                  <Skeleton width="28px" height="28px" />
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <Skeleton width="60%" height="14px" />
                    <Skeleton width="40%" height="10px" />
                    <Skeleton width="90%" height="10px" />
                  </div>
                  <Skeleton width="30px" height="14px" />
                </div>
              ))}
            </div>
          ) : hasSources ? (
            sources.map((item) => (
              <article className="chunk" key={item.chunk_id}>
                <div className="chunk-icon">{formatSourceType(item)}</div>
                <div className="chunk-body">
                  <div className="chunk-title">{formatSourceTitle(item)}</div>
                  <div className="chunk-meta">{formatSourceMeta(item)}</div>
                  <p className="chunk-text">{item.text_preview}</p>
                </div>
                <div className="chunk-score">{item.score ? item.score.toFixed(2) : '-'}</div>
              </article>
            ))
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
                <strong>{confidence}%</strong>
                <span>Confidence</span>
              </div>
            </div>
            <div className="confidence-list">
              <div>
                <span>Answer Confidence</span>
                <strong>{confidence}%</strong>
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
