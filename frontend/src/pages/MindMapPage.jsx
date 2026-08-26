import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MindMapViewer } from '@xiangfa/mindmap';
import '@xiangfa/mindmap/style.css';
import { getMindMap } from '../services/api';

export default function MindMapPage() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const [map, setMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const viewerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const data = await getMindMap(sourceId);
        if (cancelled) return;
        setMap(data);
      } catch (err) {
        if (cancelled) return;
        setError(err.message || 'Failed to load mind map');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sourceId]);

  const requestFit = useCallback(() => {
    // Wait a frame so the container has laid out and the viewport has real
    // dimensions before the library measures it; without this the canvas
    // renders at its natural scale and looks tiny.
    requestAnimationFrame(() => viewerRef.current?.fitView?.());
  }, []);

  // Refit once the map content is rendered and whenever the viewport resizes.
  useEffect(() => {
    if (!map) return;
    requestFit();
  }, [map, requestFit]);

  useEffect(() => {
    const onResize = () => requestFit();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [requestFit]);

  // Observe the shell so the fit is recomputed with the canvas's real
  // dimensions. The library computes its initial fit on the first render, at
  // which point the container may not have its final size yet (especially in
  // normal view) — ResizeObserver catches the settled size and re-fits so the
  // graph fills the whole area.
  const shellRef = useRef(null);
  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;
    let rafId = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (map) requestFit();
      });
    });
    observer.observe(shell);
    return () => {
      cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, [map, requestFit]);

  // Refit when re-entering fullscreen (element dimensions change).
  useEffect(() => {
    if (isFullscreen) requestFit();
  }, [isFullscreen, requestFit]);

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

      <div className="mindmap-container-shell" ref={shellRef}>
        {loading ? (
          <div className="empty">Generating mind map…</div>
        ) : error ? (
          <div className="empty">
            <p>{error}</p>
            <button className="ghost" onClick={() => navigate('/')}>Back to chat</button>
          </div>
        ) : map ? (
          <MindMapViewer
            ref={viewerRef}
            markdown={map.markdown}
            theme="dark"
            toolbar={{ zoom: true, history: true, search: true }}
          />
        ) : null}
      </div>

      <div className="mindmap-footer">
        <span className="muted">Scroll to zoom · drag to pan · {map?.chunk_count ?? 0} chunks</span>
      </div>
    </main>
  );
}
