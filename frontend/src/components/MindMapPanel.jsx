import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import MindMapCanvas from './MindMapCanvas'
import { SourceGlyph, sourceIconClass } from '../lib/sources'

// The workspace's Mind Map.
//
// A mind map is built from the sources selected in the sidebar, and the
// selection is also editable right here so the user can widen or narrow the
// scope without leaving the workspace.  It covers both modes the project
// workspace supports: one source for a focused map, several for a combined one.
//
// Full screen is a portal to document.body rather than a CSS state on the
// canvas.  The workspace is a three-column grid (sidebar · main · evidence
// rail), so a positioned overlay nested inside the main column could only ever
// fill that column — portalling is what lets the map take the whole viewport
// with the sidebar and rail genuinely out of the way.  Exiting simply unmounts
// the portal, so the normal layout is restored as-is.
export default function MindMapPanel({ sources = [], selectedIds = [], onSelectionChange }) {
  const canvasRef = useRef(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showPicker, setShowPicker] = useState(false)

  const exitFullscreen = useCallback(() => setIsFullscreen(false), [])

  // Escape leaves full screen, and the scope picker closes with it so the menu
  // isn't left floating over the overlay.
  useEffect(() => {
    if (!isFullscreen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setShowPicker(false)
        setIsFullscreen(false)
      }
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

  const isSelected = (id) => selectedIds.includes(id)

  const toggle = (id) => {
    if (isSelected(id)) {
      onSelectionChange(selectedIds.filter((existing) => existing !== id))
    } else {
      onSelectionChange([...selectedIds, id])
    }
  }

  const content = (
    <>
      <div className="mindmap-panel-bar">
        <div className="mindmap-panel-scope">
          <button
            type="button"
            className="mindmap-scope-toggle"
            onClick={() => setShowPicker((open) => !open)}
            aria-expanded={showPicker}
          >
            <span className="mindmap-scope-count">
              {selectedIds.length === 0
                ? 'All sources'
                : selectedIds.length === 1
                  ? '1 source'
                  : `${selectedIds.length} sources`}
            </span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={showPicker ? 'is-open' : ''}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>

          {showPicker ? (
            <div className="mindmap-scope-menu">
              <div className="mindmap-scope-menu-head">
                <span>Sources in this map</span>
                <button type="button" onClick={() => onSelectionChange([])}>
                  Use all
                </button>
              </div>
              {sources.length === 0 ? (
                <p className="mindmap-scope-empty">No sources in this project yet.</p>
              ) : (
                sources.map((source) => (
                  <label key={source.id} className="mindmap-scope-option">
                    <input
                      type="checkbox"
                      checked={isSelected(source.id)}
                      onChange={() => toggle(source.id)}
                    />
                    <span className={sourceIconClass(source.type)}>
                      <SourceGlyph type={source.type} size={14} />
                    </span>
                    <span className="mindmap-scope-option-title">{source.title}</span>
                  </label>
                ))
              )}
            </div>
          ) : null}
        </div>

        <div className="mindmap-panel-actions">
          <button
            type="button"
            className="mindmap-action"
            onClick={() => canvasRef.current?.regenerate?.()}
            disabled={sources.length === 0}
            title="Generate a fresh mind map from the current selection"
          >
            Regenerate
          </button>
          <button
            type="button"
            className="mindmap-action"
            onClick={() => (isFullscreen ? exitFullscreen() : setIsFullscreen(true))}
          >
            {isFullscreen ? 'Exit full screen' : 'Full screen'}
          </button>
        </div>
      </div>

      <div className="mindmap-panel-canvas">
        <MindMapCanvas ref={canvasRef} sourceIds={selectedIds} isFullscreen={isFullscreen} />
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
