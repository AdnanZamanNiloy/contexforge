import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import MindMapCanvas from './MindMapCanvas'

// The workspace's Mind Map.
//
// A mind map is built from ONE source chosen right here — the user must pick a
// specific source before a map is generated, so there is no "all sources"
// default and no multi-source map.  This selection is independent of the chat
// sidebar selection.
//
// Full screen is a portal to document.body rather than a CSS state on the
// canvas.  The workspace is a three-column grid (sidebar · main · evidence
// rail), so a positioned overlay nested inside the main column could only ever
// fill that column — portalling is what lets the map take the whole viewport
// with the sidebar and rail genuinely out of the way.  Exiting simply unmounts
// the portal, so the normal layout is restored as-is.
export default function MindMapPanel({ sources = [], sourceId = '', onSourceChange }) {
  const canvasRef = useRef(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const exitFullscreen = useCallback(() => setIsFullscreen(false), [])
  const hasSource = Boolean(sourceId)

  // Escape leaves full screen.
  useEffect(() => {
    if (!isFullscreen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setIsFullscreen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isFullscreen])

  // The page behind the overlay must not scroll or the fixed layer would let it
  // slide underneath.
  useEffect(() => {
    if (!isFullscreen) return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [isFullscreen])

  const content = (
    <>
      <div className="mindmap-panel-bar">
        <div className="mindmap-panel-scope">
          <label className="mindmap-source-picker">
            <span className="mindmap-source-label">Source</span>
            <select
              className="mindmap-source-select"
              value={sourceId}
              onChange={(event) => onSourceChange?.(event.target.value)}
              aria-label="Select the source this mind map is built from"
            >
              <option value="" disabled>
                Select a source
              </option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.title}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mindmap-panel-actions">
          <button
            type="button"
            className="mindmap-action"
            onClick={() => canvasRef.current?.regenerate?.()}
            disabled={!hasSource}
            title="Generate a fresh mind map from the selected source"
          >
            Regenerate
          </button>
          <button
            type="button"
            className="mindmap-action"
            onClick={() => (isFullscreen ? exitFullscreen() : setIsFullscreen(true))}
            disabled={!hasSource}
          >
            {isFullscreen ? 'Exit full screen' : 'Full screen'}
          </button>
        </div>
      </div>

      <div className="mindmap-panel-canvas">
        <MindMapCanvas ref={canvasRef} sourceId={sourceId} isFullscreen={isFullscreen} />
      </div>
    </>
  )

  if (!isFullscreen) {
    return <div className="mindmap-panel">{content}</div>
  }

  return createPortal(
    <div className="mindmap-fullscreen" role="dialog" aria-modal="true" aria-label="Mind map">
      <div className="mindmap-panel is-fullscreen">{content}</div>
    </div>,
    document.body,
  )
}
