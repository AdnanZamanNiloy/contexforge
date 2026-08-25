// Repository AI answer panel. Renders the active question, the streamed
// answer, and references — as an in-flow, bounded section that sits above the
// repository visualization and pushes it downward rather than overlaying it.
export default function RepositoryAnswerPanel({ question, answer, sources = [], loading = false, error = '' }) {
  if (!question && !loading && !answer && !error) return null;

  return (
    <section className="repo-answer-panel" aria-live="polite">
      <div className="repo-answer-question">
        <span className="repo-answer-q-label">Question</span>
        <span className="repo-answer-q-text">{question}</span>
      </div>

      <div className="repo-answer-body">
        {loading ? (
          <div className="repo-answer-loading">
            <span className="repo-answer-spinner" aria-hidden="true" />
            <span>Analyzing repository… Generating answer…</span>
          </div>
        ) : error ? (
          <div className="repo-answer-error">{error}</div>
        ) : (
          <div className="repo-answer-text">{answer}</div>
        )}
      </div>

      {!loading && !error && sources.length ? (
        <div className="repo-answer-sources">
          {sources.slice(0, 6).map((s, i) => (
            <span className="repo-answer-chip" key={s.chunk_id || i}>
              {s.display || s.chunk_id}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
