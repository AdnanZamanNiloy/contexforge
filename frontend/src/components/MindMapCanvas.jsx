import { useCallback, useEffect, useRef, useState } from 'react'
import { MindMapViewer } from '@xiangfa/mindmap'
import '@xiangfa/mindmap/style.css'

import { createMindMap, getMindMap } from '../services/api'

// Reusable mind-map canvas.  Owns loading, error, fit-to-screen and fullscreen
// behaviour for a source's mind map, so it can live either as a dedicated page
// (MindMapPage) or inside the source-explore shell.  When no mind map has been
// created yet it shows a "Create Mind Map" prompt and reveals the map inline
// once it has been generated.
export default function MindMapCanvas({ sourceId, isFullscreen = false, onReady, onError }) {
  const [map, setMap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const viewerRef = useRef(null)
  const shellRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const data = await getMindMap(sourceId)
        if (cancelled) return
        setMap(data)
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
  }, [sourceId, onReady, onError])

  const handleCreate = useCallback(async () => {
    if (creating) return
    setCreating(true)
    setError('')
    try {
      const data = await createMindMap(sourceId)
      setMap(data && data.markdown ? data : await getMindMap(sourceId))
      onReady?.(data)
    } catch (err) {
      setError(err.message || 'Failed to create mind map')
    } finally {
      setCreating(false)
    }
  }, [sourceId, creating, onReady])

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
      ) : (
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
          <p className="mindmap-empty-sub">Generate a visual summary from this source.</p>
          <button className="primary" onClick={handleCreate} disabled={creating}>
            {creating ? 'Creating mind map…' : 'Create Mind Map'}
          </button>
        </div>
      )}
    </div>
  )
}
