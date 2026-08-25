import { useState } from 'react';

// Repository AI ask box. Streams a repository-grounded answer from the backend
// via `streamAnswer(text, handlers)` (POST /repository/{id}/ask). The answer
// itself is rendered by <RepositoryAnswerPanel/> placed between the tabs and the
// repository visualization, so this component only captures the ask and defers
// to `onAnswer` / `onSources` for the live answer state.
export default function RepositoryAIInput({ suggestedQuestions = [], streamAnswer, onTabHint, onAsk }) {
  const [value, setValue] = useState('');

  const submit = (q) => {
    const text = (q ?? value).trim();
    if (!text) return;
    setValue('');
    onTabHint?.(text);
    onAsk?.(text, streamAnswer);
  };

  return (
    <footer className="repo-ai">
      <form
        className="repo-ai-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <svg className="repo-ai-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z" /><path d="M20 3v3M21.5 4.5h-3" /></svg>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask anything about this repository..."
          spellCheck={false}
        />
        <button type="submit" className="repo-ai-send" disabled={!value.trim()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
        </button>
      </form>

      <div className="repo-ai-suggestions">
        {suggestedQuestions.map((q) => (
          <button key={q} className="repo-ai-chip" onClick={() => submit(q)}>{q}</button>
        ))}
      </div>
    </footer>
  );
}
