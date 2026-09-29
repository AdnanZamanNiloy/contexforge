import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchSources, updateSourceTitle } from '../services/api'
import { normalizeSource } from '../lib/sources'

// Shared source store for the ContextForge workspace.  Every page — the
// workspace, chat and the mind map — consumes the same source list so
// navigation and source representation are identical no matter which
// capability is in focus.
// Every row carries `id={source.id}` as its React key, and selection is keyed
// on that id. A list holding the same id twice therefore renders two rows that
// are one row as far as selection is concerned: both light up together and
// clicking either toggles both, which reads as "select and deselect do the
// same thing".
//
// Duplicates arise naturally. Ingest inserts an optimistic row under a
// temporary id and then rewrites that id to the server's real one; if a
// refresh lands in between, the real source is already in the list and the
// rewrite makes the optimistic row collide with it.
//
// Enforced on every write rather than at the call sites, so the invariant
// holds no matter which path mutated the list.
function dedupeById(list) {
  const seen = new Set()
  const out = []
  for (const source of list) {
    if (!source || seen.has(source.id)) continue
    seen.add(source.id)
    out.push(source)
  }
  return out
}

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
      setSources(data?.sources?.length ? dedupeById(data.sources.map(normalizeSource)) : [])
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
    // Prepending can collide with a row already in the list when a refresh
    // raced the optimistic insert.
    setSources((prev) => dedupeById([payload, ...prev]))
  }, [])

  const updateSource = useCallback((id, patch) => {
    setSources((prev) =>
      dedupeById(prev.map((item) => (item.id === id ? { ...item, ...patch } : item))),
    )
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
    setSources(dedupeById(next))
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
