import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createMindMap, getMindMap } from '../services/api';

export default function CreateMindMapButton({ sourceId }) {
  const navigate = useNavigate();
  const [state, setState] = useState('checking');
  const [error, setError] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    let cancelled = false;
    setState('checking');
    setError('');
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
  }, [sourceId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handleClick = useCallback(async () => {
    if (state === 'loading') return;
    if (state === 'ready') {
      navigate(`/mindmap/${encodeURIComponent(sourceId)}`);
      return;
    }
    if (!sourceId) return;
    setState('loading');
    setError('');
    try {
      await createMindMap(sourceId);
      if (mountedRef.current) setState('ready');
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message || 'Failed to create mind map');
        setState('error');
      }
    }
  }, [state, sourceId, navigate]);

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
    </>
  );
}
