import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchSources, updateSourceTitle } from '../services/api'
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

  // Persist a new display title, then reflect it locally.  A failed rename
  // leaves the previous title in place so the row never shows a name the
  // server did not accept.
  const renameSource = useCallback(async (id, title) => {
    const clean = (title || '').trim()
    if (!clean) throw new Error('Source name cannot be empty.')
    await updateSourceTitle(id, clean)
    setSources((prev) => prev.map((item) => (item.id === id ? { ...item, title: clean } : item)))
    return clean
  }, [])

  const removeSource = useCallback((id) => {
    setSources((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const replaceAll = useCallback((next) => {
    setSources(next)
  }, [])

  return {
    sources,
    loading,
    refresh,
    addSource,
    updateSource,
    renameSource,
    removeSource,
    replaceAll,
  }
}
