import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import { MindMapViewer } from '@xiangfa/mindmap'
import '@xiangfa/mindmap/style.css'

import { createMindMap, getMindMap } from '../services/api'

// Reusable mind-map canvas.  Owns loading, error, fit-to-screen and fullscreen
// behaviour for a mind map built from the workspace's current source selection.
//
// `sourceIds` is a list: one entry behaves exactly like the original
// single-source case, several produce one combined map.  When no mind map exists
// yet the canvas shows a prompt and reveals the map inline once generated.
//
// The parent drives regeneration through the ref (`regenerate()`), which forces
// a fresh generation rather than a re-fetch of the cached outline.
const MindMapCanvas = forwardRef(function MindMapCanvas(
  { sourceIds = [], isFullscreen = false, onReady, onError },
  ref,
) {
  const [map, setMap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const viewerRef = useRef(null)
  const shellRef = useRef(null)

  // The scope identity the map on screen belongs to.  `sourceIds` is a fresh
  // array on every render, so compare a derived, order-independent string.
  const scopeKey = useMemo(() => joinScope(sourceIds), [sourceIds])
  // Bumped on every successful load so an in-flight fetch that resolved after the
  // user changed selection is discarded rather than painted.
  const [loadedScope, setLoadedScope] = useState(scopeKey)

  // A different selection means the map on screen no longer answers to it.
  useEffect(() => {
    if (scopeKey === loadedScope) return
    setMap(null)
    setError('')
    setLoading(false)
  }, [scopeKey, loadedScope])

  useEffect(() => {
    if (!scopeKey) {
      setMap(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const data = await getMindMap(sourceIds)
        if (cancelled) return
        setMap(data)
        setLoadedScope(scopeKey)
        onReady?.(data)
      } catch (err) {
        if (cancelled) return
        setError(err.message || 'Failed to load mind map')
        onError?.(err.message || 'Failed to load mind map')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey, onReady, onError])

  const requestFit = useCallback(() => {
    requestAnimationFrame(() => viewerRef.current?.fitView?.())
  }, [])

  useEffect(() => {
    if (!map) return
    requestFit()
  }, [map, requestFit])

  useEffect(() => {
    const onResize = () => requestFit()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [requestFit])

  // Observe the shell so the fit is recomputed once the container settles and
  // the graph fills the available area.
  useEffect(() => {
    const shell = shellRef.current
    if (!shell) return
    let rafId = 0
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        if (map) requestFit()
      })
    })
    observer.observe(shell)
    return () => {
      cancelAnimationFrame(rafId)
      observer.disconnect()
    }
  }, [map, requestFit])

  useEffect(() => {
    if (isFullscreen) requestFit()
  }, [isFullscreen, requestFit])

  const create = useCallback(
    async (force) => {
      if (creating || !scopeKey) return
      setCreating(true)
      setError('')
      try {
        const data = await createMindMap(sourceIds, { refresh: force })
        const next = data && data.markdown ? data : await getMindMap(sourceIds)
        setMap(next)
        setLoadedScope(scopeKey)
        onReady?.(next)
      } catch (err) {
        setError(err.message || 'Failed to create mind map')
      } finally {
        setCreating(false)
      }
    },
    [creating, scopeKey, sourceIds, onReady],
  )

  useImperativeHandle(
    ref,
    () => ({
      // Create the map if there isn't one, or force a fresh generation.
      regenerate: () => create(true),
      create: () => create(false),
    }),
    [create],
  )

  return (
    <div className={`mindmap-canvas${isFullscreen ? ' is-fullscreen' : ''}`} ref={shellRef}>
      {loading ? (
        <div className="empty">{creating ? 'Creating mind map…' : 'Generating mind map…'}</div>
      ) : error ? (
        <div className="empty">
          <p>{error}</p>
        </div>
      ) : map ? (
        <MindMapViewer
          ref={viewerRef}
          markdown={map.markdown}
          theme="dark"
          toolbar={{ zoom: true, history: true, search: true }}
        />
      ) : scopeKey ? (
        <div className="mindmap-empty">
          <svg
            width="34"
            height="34"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="6" cy="5" r="2.2" />
            <circle cx="18" cy="7" r="2.2" />
            <circle cx="8" cy="19" r="2.2" />
            <path d="M8.2 5.8l7.6 1M7 7.1l.8 9.7M17 9.2l-7 8" />
          </svg>
          <p className="mindmap-empty-title">No mind map yet</p>
          <p className="mindmap-empty-sub">
            Build a visual summary from the selected source
            {sourceIds.length > 1 ? 's' : ''}.
          </p>
          <button className="primary" onClick={() => create(false)} disabled={creating}>
            {creating ? 'Creating mind map…' : 'Create Mind Map'}
          </button>
        </div>
      ) : (
        <div className="mindmap-empty">
          <p className="mindmap-empty-title">No sources selected</p>
          <p className="mindmap-empty-sub">
            Pick one or more sources in the sidebar to build a mind map from them.
          </p>
        </div>
      )}
    </div>
  )
})

// Order-independent identity for a source selection.
function joinScope(sourceIds) {
  return [...new Set((sourceIds || []).filter(Boolean))].sort().join('|')
}

export default MindMapCanvas
