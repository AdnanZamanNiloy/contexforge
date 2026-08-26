import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import MindMapCanvas from '../components/MindMapCanvas';

export default function MindMapPage() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const [map, setMap] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [error, setError] = useState('');

  const handleReady = useCallback((data) => {
    setMap(data);
    setError('');
  }, []);

  const handleError = useCallback((msg) => {
    setError(msg);
  }, []);

  const requestFit = useCallback(() => {
    window.dispatchEvent(new Event('resize'));
  }, []);

  // Escape exits fullscreen.
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e) => {
      if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen]);

  return (
    <main className={`mindmap-page${isFullscreen ? ' is-fullscreen' : ''}`}>
      <header className="mindmap-header">
        <button className="icon-button" onClick={() => navigate(-1)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>Back</span>
        </button>

        <div className="mindmap-title">
          <h1>{map?.title || 'Mind Map'}</h1>
          {map?.chunk_count != null ? <span className="muted">{map.chunk_count} chunks</span> : null}
        </div>

        <div className="mindmap-actions">
          <button className="icon-button" onClick={requestFit} title="Fit to screen">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
            </svg>
            <span>Fit</span>
          </button>
          <button
            className="icon-button"
            onClick={() => setIsFullscreen((v) => !v)}
            title={isFullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {isFullscreen ? (
                <path d="M4 8h4V4M20 8h-4V4M4 16h4v4M20 16h-4v4" />
              ) : (
                <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
              )}
            </svg>
            <span>{isFullscreen ? 'Exit' : 'Full'}</span>
          </button>
        </div>
      </header>

      <div className="mindmap-container-shell">
        {error ? (
          <div className="empty">
            <p>{error}</p>
            <button className="ghost" onClick={() => navigate('/')}>Back to chat</button>
          </div>
        ) : (
          <MindMapCanvas sourceId={sourceId} isFullscreen={isFullscreen} onReady={handleReady} onError={handleError} />
        )}
      </div>

      <div className="mindmap-footer">
        <span className="muted">Scroll to zoom · drag to pan · {map?.chunk_count ?? 0} chunks</span>
      </div>
    </main>
  );
}
