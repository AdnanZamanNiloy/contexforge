import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import NoteView from './NoteView'

// The workspace's Note.
//
// A note is written from a *selection* of sources — one, or several at once.
// Unlike the mind map's single-source dropdown, this needs multi-select, so the
// picker is a checkbox list behind a disclosure button: with a dozen sources in
// the sidebar, a list of toggles stays legible where a multi-select <select>
// would not.  This selection is independent of the chat sidebar selection.
//
// The note is generated once per selection and then cached server-side, so
// switching back to a selection the user already wrote shows it immediately.
export default function NotePanel({ sources = [], selectedSourceIds = [], onSelectionChange }) {
  const viewRef = useRef(null)
  const menuRef = useRef(null)
  const [note, setNote] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  // Mirrors the view's own in-flight state, for the same reason as the mind map:
  // the button lives here and the work happens in the child.
  const [busy, setBusy] = useState(false)

  const selected = useMemo(
    () => [...new Set(selectedSourceIds.filter(Boolean))],
    [selectedSourceIds],
  )
  const hasSelection = selected.length > 0

  const toggle = useCallback(
    (id) => {
      const next = selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]
      onSelectionChange?.(next)
    },
    [selected, onSelectionChange],
  )

  // Escape closes the picker; a click outside it does too, so the menu never
  // sits open over the note the user is trying to read.
  useEffect(() => {
    if (!menuOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    const onPointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [menuOpen])

  // "Copied" is a transient confirmation; without this it sticks on forever.
  useEffect(() => {
    if (!copied) return undefined
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const onCopy = useCallback(async () => {
    if (!note?.markdown) return
    try {
      await navigator.clipboard.writeText(note.markdown)
      setCopied(true)
    } catch {
      // Clipboard access can be refused (insecure context, permissions).  The
      // note is still on screen and downloadable, so failing quietly beats
      // replacing the document with an error.
    }
  }, [note])

  const onDownload = useCallback(() => {
    if (!note?.markdown) return
    const slug =
      (note.title || 'note')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 60) || 'note'
    const url = URL.createObjectURL(
      new Blob([note.markdown], { type: 'text/markdown;charset=utf-8' }),
    )
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${slug}.md`
    anchor.click()
    URL.revokeObjectURL(url)
  }, [note])

  return (
    <div className="note-panel">
      <div className="note-panel-bar">
        <div className="note-scope" ref={menuRef}>
          <span className="note-scope-label">Sources</span>
          <button
            type="button"
            className="note-scope-toggle"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-haspopup="true"
          >
            {hasSelection ? `${selected.length} selected` : 'Select sources'}
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {menuOpen ? (
            <div className="note-scope-menu" role="group" aria-label="Sources to write from">
              {sources.length === 0 ? (
                <p className="note-scope-empty">No sources in this project yet.</p>
              ) : (
                <ul className="note-scope-list">
                  {sources.map((source) => {
                    const checked = selected.includes(source.id)
                    return (
                      <li key={source.id}>
                        <label className="note-scope-option">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggle(source.id)}
                          />
                          <span className="note-scope-option-text">{source.title}</span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}
        </div>

        <div className="note-panel-actions">
          <button
            type="button"
            className={`note-action${busy ? ' is-busy' : ''}`}
            onClick={() => viewRef.current?.regenerate?.()}
            disabled={!hasSelection || busy}
            title="Write a fresh note from the selected sources"
            aria-busy={busy}
          >
            {busy ? <span className="btn-spinner" aria-hidden="true" /> : null}
            {busy ? 'Regenerating…' : 'Regenerate'}
          </button>
          <button type="button" className="note-action" onClick={onCopy} disabled={!note || busy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button type="button" className="note-action" onClick={onDownload} disabled={!note}>
            Download
          </button>
        </div>
      </div>

      <div className="note-panel-body">
        <NoteView
          ref={viewRef}
          sourceIds={selected}
          onReady={setNote}
          onBusyChange={setBusy}
        />
        {/* Rendered here rather than inside NoteView because .note-doc is the
            scroll container: an overlay placed in there would scroll away with
            the text instead of holding still over it. */}
        {busy ? (
          <div className="panel-busy" role="status" aria-live="polite">
            <div className="panel-spinner" aria-hidden="true" />
            <p className="panel-busy-title">Rewriting the note…</p>
            <p className="panel-busy-note">
              The current note stays readable until the new one replaces it.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
