import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MindMap } from '@xiangfa/mindmap';
import '@xiangfa/mindmap/style.css';
import { getMindMap } from '../services/api';

export default function MindMapPage() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const [map, setMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

  return (
    <main className="mindmap-page">
      <header className="mindmap-header">
        <button className="icon-button" onClick={() => navigate('/')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>Back</span>
        </button>
        <div className="mindmap-title">
          <h1>{map?.title || 'Mind Map'}</h1>
          {map?.chunk_count != null ? <span className="muted">{map.chunk_count} chunks</span> : null}
        </div>
      </header>

      <div className="mindmap-container-shell">
        {loading ? (
          <div className="empty">Generating mind map…</div>
        ) : error ? (
          <div className="empty">
            <p>{error}</p>
            <button className="ghost" onClick={() => navigate('/')}>Back to chat</button>
          </div>
        ) : map ? (
          <MindMap markdown={map.markdown} theme="dark" readonly toolbar={{ zoom: true, history: true, search: true }} />
        ) : null}
      </div>
    </main>
  );
}
