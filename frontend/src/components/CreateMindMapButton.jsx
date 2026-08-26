import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createMindMap, getMindMap } from '../services/api';

const NO_SOURCE_MESSAGE = 'Select a source to get started, then create a mind map from it.';

export default function CreateMindMapButton({ sourceId }) {
  const navigate = useNavigate();
  const [state, setState] = useState('checking');
  const [error, setError] = useState('');
  const [showPrompt, setShowPrompt] = useState(false);
  const mountedRef = useRef(true);
  const promptTimerRef = useRef(null);

  const dismissPrompt = useCallback(() => {
    if (promptTimerRef.current) clearTimeout(promptTimerRef.current);
    promptTimerRef.current = null;
    setShowPrompt(false);
  }, []);

  const showPromptMessage = useCallback(() => {
    setShowPrompt(true);
    if (promptTimerRef.current) clearTimeout(promptTimerRef.current);
    promptTimerRef.current = setTimeout(() => setShowPrompt(false), 4500);
  }, []);

  useEffect(() => () => {
    if (promptTimerRef.current) clearTimeout(promptTimerRef.current);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState('checking');
    setError('');
    dismissPrompt();
    if (!sourceId) {
      setState('idle');
      return;
    }
    (async () => {
      try {
        const map = await getMindMap(sourceId);
        if (cancelled) return;
        setState(map ? 'ready' : 'idle');
      } catch {
        if (cancelled) return;
        setState('idle');
      }
    })();
    return () => { cancelled = true; };
  }, [sourceId, dismissPrompt]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handleClick = useCallback(async () => {
    if (state === 'loading') return;
    if (state === 'ready' && sourceId) {
      navigate(`/mindmap/${encodeURIComponent(sourceId)}`);
      return;
    }
    if (!sourceId) {
      showPromptMessage();
      setError('');
      return;
    }
    setState('loading');
    setError('');
    dismissPrompt();
    try {
      await createMindMap(sourceId);
      if (mountedRef.current) setState('ready');
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message || 'Failed to create mind map');
        setState('error');
      }
    }
  }, [state, sourceId, navigate, showPromptMessage, dismissPrompt]);

  let label = 'Create Mind Map';
  if (state === 'checking') label = 'Checking…';
  else if (state === 'loading') label = 'Creating mind map…';
  else if (state === 'ready') label = 'View Mind Map';

  return (
    <>
      <button
        className="mindmap-cta"
        onClick={handleClick}
        disabled={state === 'loading' || state === 'checking'}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="6" cy="5" r="2.2" />
          <circle cx="18" cy="7" r="2.2" />
          <circle cx="8" cy="19" r="2.2" />
          <path d="M8.2 5.8l7.6 1M7 7.1l.8 9.7M17 9.2l-7 8" />
        </svg>
        <span>{label}</span>
      </button>
      {state === 'error' && error ? <p className="mindmap-error">{error}</p> : null}
      {showPrompt && (sourceId ? null : (
        <div className="mindmap-prompt" role="status">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4-2.4 5.4-.9 1-.9 2-.9 2.6h-1.7a1 1 0 0 1-1-1v-.4c0-1.2.4-2 1.2-3.1.9-1.2 1.8-2.2 1.8-3.5a4 4 0 0 0-8 0c0 1.3.9 2.3 1.8 3.5.8 1.1 1.2 1.9 1.2 3.1v.4a1 1 0 0 1-1 1H9.3c0-.6 0-1.6-.9-2.6C7.2 13.9 6 12.4 6 10a6 6 0 0 1 6-8z" />
            <line x1="12" y1="20" x2="12" y2="22" />
          </svg>
          <span>{NO_SOURCE_MESSAGE}</span>
        </div>
      ))}
    </>
  );
}
