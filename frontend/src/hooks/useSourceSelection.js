import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// Which sources the workspace is currently working with.
//
// The project workspace is the only workspace: sources are picked here, in the
// sidebar, and that single selection drives Chat, Mind Map and every other AI
// capability.  NotebookLM-style behaviour is supported — pick one source for
// focused analysis, or several to reason across them together.
//
// The selection is pruned whenever the available sources change so a deleted or
// no-longer-visible source can never linger in the scope and silently empty a
// query.
export function useSourceSelection(availableSources) {
  // Order of insertion, so the selection reads the way the user built it.
  const [selectedIds, setSelectedIds] = useState([])

  // An empty selection is falsy, so callers only need to test for null/undefined.
  // Memoised so the identity is stable and the effects below don't re-run on
  // every render.
  const sourceList = useMemo(() => availableSources || [], [availableSources])

  const availableKey = useMemo(() => sourceList.map((s) => s.id).join(' '), [sourceList])
  // Read through a ref only inside handlers, never during render.
  const availableRef = useRef(sourceList)
  useEffect(() => {
    availableRef.current = sourceList
  }, [sourceList])

  // Drop selections whose source disappeared (deleted, or filtered out of the
  // current project's view).  React's documented pattern for adjusting state
  // when inputs change is to do it during render and re-render immediately,
  // rather than in an effect which would paint one stale frame first.
  const [prunedAgainst, setPrunedAgainst] = useState(availableKey)
  if (prunedAgainst !== availableKey) {
    setPrunedAgainst(availableKey)
    const allowed = new Set(sourceList.map((s) => s.id))
    setSelectedIds((prev) => {
      const next = prev.filter((id) => allowed.has(id))
      return next.length === prev.length ? prev : next
    })
  }

  const isSelected = useCallback((id) => selectedIds.includes(id), [selectedIds])

  // Plain click: the primary gesture. Re-clicking the only selected source
  // clears it, so a click always leaves a predictable state.
  const select = useCallback((id) => {
    if (!id) return
    setSelectedIds((prev) => {
      if (prev.length === 1 && prev[0] === id) return []
      if (prev.includes(id)) return prev.filter((existing) => existing !== id)
      return [...prev, id]
    })
  }, [])

  // Secondary gesture (the row's checkbox / modifier click): add or remove one
  // source without disturbing the rest of the selection.
  const toggle = useCallback((id) => {
    if (!id) return
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id],
    )
  }, [])

  const selectOnly = useCallback((id) => {
    setSelectedIds(id ? [id] : [])
  }, [])

  const selectAll = useCallback(() => {
    setSelectedIds(availableRef.current.map((s) => s.id))
  }, [])

  const clear = useCallback(() => setSelectedIds([]), [])

  // Replace the whole selection in one shot — used by the Mind Map tab's
  // in-tab picker, which owns the same selection as the sidebar.
  const replaceAll = useCallback((ids) => {
    const next = (ids || []).filter(Boolean)
    setSelectedIds([...new Set(next)])
  }, [])

  return {
    selectedIds,
    isSelected,
    select,
    toggle,
    selectOnly,
    selectAll,
    clear,
    replaceAll,
    count: selectedIds.length,
    isEmpty: selectedIds.length === 0,
    has: selectedIds.length > 0,
  }
}
