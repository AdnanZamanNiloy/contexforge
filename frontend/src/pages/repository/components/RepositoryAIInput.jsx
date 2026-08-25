import { useState } from 'react';
import { suggestedQuestions } from '../../../data/repoIntelligence';

export default function RepositoryAIInput({ onAsk }) {
  const [value, setValue] = useState('');
  const [thinking, setThinking] = useState(false);

  const submit = (q) => {
    const text = (q ?? value).trim();
    if (!text) return;
    setThinking(true);
    // Simulate analysis dispatch; backend wiring comes later.
    setTimeout(() => {
      setThinking(false);
      onAsk?.(text);
    }, 650);
    setValue('');
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
          disabled={thinking}
        />
        <button type="submit" className="repo-ai-send" disabled={thinking || !value.trim()}>
          {thinking ? (
            <span className="ai-thinking"><i /><i /><i /></span>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
          )}
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
