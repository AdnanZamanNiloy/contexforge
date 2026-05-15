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

export default function SourceViewer({ sources = [], latency = {} }) {
  const hasSources = sources.length > 0;
  const confidence = Math.min(99, Math.max(60, 70 + sources.length * 3));
  return (
    <aside className="evidence">
      <div className="evidence-tabs">
        <button className="tab active">Evidence</button>
        <button className="tab">Debug</button>
        <button className="tab">Statistics</button>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3>Top Retrieved Chunks</h3>
          <span className="muted">{hasSources ? `${sources.length} sources` : 'No sources yet'}</span>
        </div>
        <div className="chunk-list">
          {hasSources ? (
            sources.map((item) => (
              <article className="chunk" key={item.chunk_id}>
                <div className="chunk-icon">{formatSourceType(item)}</div>
                <div className="chunk-body">
                  <div className="chunk-title">{formatSourceTitle(item)}</div>
                  <div className="chunk-meta">{formatSourceMeta(item)}</div>
                  <p className="chunk-text">{item.text_preview}</p>
                </div>
                <div className="chunk-score">{item.score.toFixed(2)}</div>
              </article>
            ))
          ) : (
            <div className="empty">Ask a question to populate sources.</div>
          )}
        </div>
        <button className="ghost wide">View all retrieved chunks</button>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>Confidence & Coverage</h3>
        </div>
        <div className="confidence">
          <div className="donut">
            <svg viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="46" className="track" />
              <circle
                cx="60"
                cy="60"
                r="46"
                className="value"
                strokeDasharray="289"
                strokeDashoffset={289 - (289 * confidence) / 100}
              />
            </svg>
            <div className="donut-value">
              <strong>{confidence}%</strong>
              <span>{hasSources ? 'Confidence' : 'Awaiting data'}</span>
            </div>
          </div>
          <div className="confidence-list">
            <div>
              <span>Answer Confidence</span>
              <strong>{confidence}%</strong>
            </div>
            <div>
              <span>Source Coverage</span>
              <strong>{hasSources ? 'High' : 'Pending'}</strong>
            </div>
            <div>
              <span>Sources Used</span>
              <strong>{hasSources ? sources.length : 0}</strong>
            </div>
            <div>
              <span>Retrieved Chunks</span>
              <strong>{hasSources ? sources.length : 0}</strong>
            </div>
            <div>
              <span>Retrieval Time</span>
              <strong>{latency.retrieve_ms ? `${latency.retrieve_ms.toFixed(0)} ms` : '-'}</strong>
            </div>
          </div>
        </div>
      </section>
    </aside>
  );
}
