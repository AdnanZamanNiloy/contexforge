export default function MessageBubble({ role, title, text, sources = [], status }) {
  if (role === 'user') {
    return (
      <article className="bubble user">
        <div className="bubble-title">You</div>
        <p className="bubble-text">{text}</p>
      </article>
    );
  }

  return (
    <article className={`bubble ${role}`}>
      <div className="bubble-head">
        <div className="orb" />
        <div>
          <div className="bubble-title">{title}</div>
          <div className="bubble-subtitle">{status === 'streaming' ? 'Streaming reply' : 'RAG response'}</div>
        </div>
      </div>
      <p className="bubble-text">{text || (status === 'streaming' ? 'Thinking...' : '')}</p>
      {sources.length > 0 ? (
        <div className="bubble-sources">
          <span>Sources</span>
          <div className="source-tags">
            {sources.map((source) => (
              <span className="tag" key={source}>
                {source}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}
