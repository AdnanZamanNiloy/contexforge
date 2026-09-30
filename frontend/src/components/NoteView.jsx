import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { createNote, getNote } from '../services/api'

// Reusable note view.  Owns loading, generation and error state for a note
// written from ONE OR MORE selected sources.
//
// `sourceIds` is the selection as a list, because a note is the first feature
// here that is not scoped to a single source: the backend keys a note by the
// selection (a lone id, or a sorted composite of several), so the view asks for
// one whenever the selection changes and shows a prompt until the user picks.
//
// The parent drives regeneration through the ref (`regenerate()`), which forces
// a fresh generation rather than a re-fetch of the cached note.
const NoteView = forwardRef(function NoteView({ sourceIds = [], onReady, onError }, ref) {
  const [note, setNote] = useState(null)
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const docRef = useRef(null)

  // The scope identity the note on screen belongs to.  Order-independent, since
  // the backend keys a multi-source selection by a *sorted* composite — picking
  // the same two sources in the opposite order is the same note, and must not
  // throw the rendered one away.
  const scopeKey = useMemo(
    () => [...new Set(sourceIds.filter(Boolean))].sort().join(' '),
    [sourceIds],
  )
  // Bumped on every successful load so an in-flight fetch that resolved after the
  // user changed selection is discarded rather than painted.
  const [loadedScope, setLoadedScope] = useState(scopeKey)

  // A different selection means the note on screen no longer answers to it.
  useEffect(() => {
    if (scopeKey === loadedScope) return
    setNote(null)
    setError('')
    setLoading(false)
  }, [scopeKey, loadedScope])

  useEffect(() => {
    if (!scopeKey) {
      setNote(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const data = await getNote(scopeKey.split(' '))
        if (cancelled) return
        setNote(data)
        setLoadedScope(scopeKey)
        onReady?.(data)
      } catch (err) {
        if (cancelled) return
        setError(err.message || 'Failed to load note')
        onError?.(err.message || 'Failed to load note')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [scopeKey, onReady, onError])

  const create = useCallback(
    async (force) => {
      if (creating || !scopeKey) return
      setCreating(true)
      setError('')
      try {
        const data = await createNote(scopeKey.split(' '), { refresh: force })
        const next = data && data.markdown ? data : await getNote(scopeKey.split(' '))
        setNote(next)
        setLoadedScope(scopeKey)
        onReady?.(next)
      } catch (err) {
        setError(err.message || 'Failed to write note')
      } finally {
        setCreating(false)
      }
    },
    [creating, scopeKey, onReady],
  )

  useImperativeHandle(
    ref,
    () => ({
      // Write the note if there isn't one, or force a fresh generation.
      regenerate: () => create(true),
      create: () => create(false),
    }),
    [create],
  )

  if (!scopeKey) {
    return (
      <div className="note-doc is-empty">
        <p className="note-empty-title">Select sources</p>
        <p className="note-empty-sub">
          Choose one source, or several to write a note that spans them.
        </p>
      </div>
    )
  }

  return (
    <div className="note-doc" ref={docRef}>
      {loading ? (
        <div className="note-state">{creating ? 'Writing note…' : 'Loading note…'}</div>
      ) : error ? (
        <div className="note-state is-error">
          <p>{error}</p>
        </div>
      ) : note ? (
        <article className="markdown-body note-markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Keep a link from navigating the workspace out from under the
              // note, the same way the chat bubble does.
              a: ({ node: _node, ...props }) => (
                <a {...props} target="_blank" rel="noopener noreferrer" />
              ),
            }}
          >
            {note.markdown || ''}
          </ReactMarkdown>
        </article>
      ) : (
        <div className="note-state is-empty">
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
            <path d="M5 3.5h9.5L19 8v12.5H5z" />
            <path d="M14 3.5V8h5" />
            <path d="M8 12.5h8M8 16h5" />
          </svg>
          <p className="note-empty-title">No note yet</p>
          <p className="note-empty-sub">Write one from the selected sources.</p>
          <button className="primary" onClick={() => create(false)} disabled={creating}>
            {creating ? 'Writing note…' : 'Create Note'}
          </button>
        </div>
      )}
    </div>
  )
})

export default NoteView
