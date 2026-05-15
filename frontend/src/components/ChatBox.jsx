import MessageBubble from './MessageBubble';

export default function ChatBox({
  messages,
  input,
  onInputChange,
  onSend,
  isStreaming,
  error,
  suggestions,
  onSuggestion,
  onRetry,
  uploadHint,
}) {
  const handleSubmit = (event) => {
    event.preventDefault();
    onSend(input);
  };

  return (
    <section className="chat">
      <div className="chat-stream">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            role={message.role}
            title="ContextForge"
            text={message.text}
            sources={message.sources}
            status={message.status}
          />
        ))}
      </div>

      {error ? (
        <div className="error-banner">
          <span>{error}</span>
          <button className="ghost" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}

      {uploadHint ? (
        <div className="upload-hint">
          <div className="upload-hint-title">No sources were used for this answer.</div>
          <p className="upload-hint-body">
            For grounded answers, upload a PDF or DOCX, paste a URL, or link a GitHub repo. Once
            sources are added, I can also generate a study guide or a podcast-style audio overview.
          </p>
          <div className="upload-hint-actions">
            <span className="upload-hint-tag">PDF</span>
            <span className="upload-hint-tag">DOCX</span>
            <span className="upload-hint-tag">URL</span>
            <span className="upload-hint-tag">GitHub Repo</span>
          </div>
        </div>
      ) : null}

      <div className="chat-actions">
        {suggestions.map((item) => (
          <button
            className="chip"
            key={item}
            onClick={() => onSuggestion(item)}
            disabled={isStreaming}
          >
            {item}
          </button>
        ))}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <input
          className="composer-input"
          placeholder="Ask anything about your documents..."
          aria-label="Composer"
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          disabled={isStreaming}
        />
        <button className="send" type="submit" disabled={isStreaming}>
          <span>{isStreaming ? 'Streaming' : 'Send'}</span>
          <span className="send-icon">↗</span>
        </button>
      </form>
      <div className="disclaimer">ContextForge can make mistakes. Please verify important information.</div>
    </section>
  );
}
