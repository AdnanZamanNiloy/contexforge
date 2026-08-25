import { useCallback, useEffect, useRef, useState } from 'react';

import { repositoryGet, repositoryLatest, repositoryStatus, reanalyzeRepository } from '../services/api';

// Hydrates a Repository Intelligence analysis from the backend.
//
// Resolves the analysis id (from the URL param, or by looking up the latest
// completed analysis for a given repo URL), then polls /status until the run
// is complete or failed, and finally fetches the full bundle from
// GET /repository/{id}.
export function useRepository({ repositoryId, repoUrl }) {
  const [id, setId] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const idRef = useRef(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let pollTimer = null;

    async function run() {
      setLoading(true);
      setError('');
      try {
        let resolved = idRef.current;
        if (!resolved && repositoryId) resolved = repositoryId;
        if (!resolved && repoUrl) {
          const latest = await repositoryLatest(repoUrl);
          resolved = latest && latest.id;
        }
        if (!resolved) {
          throw new Error('No repository analysis available. Ingest a GitHub repository first.');
        }
        idRef.current = resolved;
        setId(resolved);

        const fetchStatus = async () => {
          const s = await repositoryStatus(resolved);
          if (cancelled) return;
          setStatus(s);
          if (s.status === 'complete') {
            const bundle = await repositoryGet(resolved);
            if (cancelled) return;
            setAnalysis(bundle);
            setLoading(false);
          } else if (s.status === 'failed') {
            setError(s.error || 'Repository analysis failed.');
            setLoading(false);
          } else {
            pollTimer = setTimeout(fetchStatus, 3000);
          }
        };

        await fetchStatus();
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load repository analysis.');
          setLoading(false);
        }
      }
    }

    run();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [repositoryId, repoUrl, reloadKey]);

  const reanalyze = useCallback(async () => {
    if (!idRef.current) return;
    setLoading(true);
    setError('');
    try {
      const res = await reanalyzeRepository(idRef.current);
      if (res?.analysis_id) {
        idRef.current = res.analysis_id;
        setId(res.analysis_id);
      } else {
        setReloadKey((k) => k + 1);
      }
      setStatus((s) => (s ? { ...s, status: 'queued' } : s));
      setAnalysis(null);
      // re-run the loader now that a fresh run id is in place
      if (res?.analysis_id) setReloadKey((k) => k + 1);
    } catch (err) {
      setError(err.message || 'Failed to re-run repository analysis.');
      setLoading(false);
    }
  }, []);

  return { id, analysis, status, loading, error, reanalyze };
}
