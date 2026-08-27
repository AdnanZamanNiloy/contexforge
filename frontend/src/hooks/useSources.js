import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchSources } from '../services/api'
import { normalizeSource } from '../lib/sources'

// Shared source store for the ContextForge workspace.  Every page — the
// workspace, source exploration, chat and Repository Intelligence — consumes
// the same source list so navigation and source representation are identical
// no matter which capability is in focus.
export function useSources() {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchSources()
      if (!mountedRef.current) return
      setSources(data?.sources?.length ? data.sources.map(normalizeSource) : [])
    } catch {
      if (mountedRef.current) setSources([])
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const addSource = useCallback((payload) => {
    setSources((prev) => [payload, ...prev])
  }, [])

  const updateSource = useCallback((id, patch) => {
    setSources((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }, [])

  const removeSource = useCallback((id) => {
    setSources((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const replaceAll = useCallback((next) => {
    setSources(next)
  }, [])

  const getById = useCallback((id) => sources.find((s) => s.id === id) || null, [sources])

  return {
    sources,
    loading,
    refresh,
    addSource,
    updateSource,
    removeSource,
    replaceAll,
    getById,
  }
}
