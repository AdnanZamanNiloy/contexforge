import { useCallback, useEffect, useMemo, useState } from 'react'

import { fetchSourceContent, fetchSourceDetail } from '../services/api'

// Source inspection.
//
// The workspace lets a user list, rename and delete a source, but nothing let
// them confirm the extraction itself. That gap matters more than it sounds: a
// scanned PDF yields no text, a DOCX drops its tables, and a bad fetch captures
// an article's navigation instead of its body — and in every one of those cases
// the source still appears in the sidebar, still gets cited, and still answers
// questions as though it had been read.
//
// So this shows what actually landed in the index: the labelled provenance, the
// extraction counts, and the chunk text retrieval would quote. Where that
// extraction was empty or partial, the panel says so in words rather than
// leaving the user to infer it from a blank box.
//
// The original upload is not offered as a download. ContextForge indexes uploads
// without retaining the bytes, so the panel reports that plainly instead of
// rendering a control that cannot work.

const PREVIEW_CHARS = 320
const TYPE_LABELS = {
  web: 'Web page',
  pdf: 'PDF',
  docx: 'Word document',
  github: 'Repository',
  youtube: 'YouTube video',
  text: 'Pasted text',
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value ?? 0)
}

function formatBytesish(chars) {
  if (chars < 1000) return `${formatNumber(chars)} characters`
  return `${formatNumber(chars)} characters (~${Math.round(chars / 1000)}k)`
}

// Why a source looks the way it does.  Ordered by how badly each would mislead
// the reader about whether their document was read.
function extractionWarning(detail) {
  if (!detail) return null
  if (detail.char_count === 0) {
    return {
      tone: 'danger',
      title: 'No text was extracted',
      body: 'This source is indexed but holds no readable text, so it cannot answer questions. A scanned document with no text layer is the usual cause — re-upload a text-based copy, or a version that has been OCR’d.',
    }
  }
  if (detail.is_scanned && detail.non_empty_pages !== null && detail.page_count) {
    const missing = detail.page_count - detail.non_empty_pages
    if (missing > 0) {
      return {
        tone: 'warn',
        title: `${missing} of ${detail.page_count} pages had no text`,
        body: 'Only part of this document was readable. Answers will cover the pages that carried a text layer.',
      }
    }
  }
  if (detail.char_count < 500) {
    return {
      tone: 'warn',
      title: 'Very little text was extracted',
      body: 'This source yielded only a small amount of text. If you uploaded a full document, the extraction may have missed most of it.',
    }
  }
  return null
}

function ProvenanceRow({ label, children }) {
  return (
    <div className="source-detail-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

export default function SourceDetailPanel({ sourceId, sourceTitle = '', onClose }) {
  // Everything loaded is stored together with the id it belongs to, so the panel
  // knows a payload is stale instead of clearing state inside the fetch effect.
  // That is what stops one source's chunks appearing under the next source while
  // its request is still in flight.
  const [loaded, setLoaded] = useState(null)
  const [showAllChunks, setShowAllChunks] = useState(false)

  useEffect(() => {
    if (!sourceId) return undefined
    let cancelled = false

    // Detail and content are two requests, but the panel is unusable without the
    // provenance, so a content failure alone must not blank the whole view.
    ;(async () => {
      try {
        const [detail, content] = await Promise.all([
          fetchSourceDetail(sourceId),
          fetchSourceContent(sourceId).catch((err) => ({ error: err.message })),
        ])
        if (cancelled) return
        // A content failure keeps the provenance and records why the text is
        // missing, rather than discarding a usable view of the source.
        setLoaded({
          sourceId,
          detail,
          content: content?.chunks ? content : null,
          error: content?.error || '',
        })
      } catch (err) {
        if (cancelled) return
        setLoaded({
          sourceId,
          detail: null,
          content: null,
          error: err.message || 'Could not load this source',
        })
      }
    })()

    return () => {
      cancelled = true
    }
  }, [sourceId])

  // A payload for a different source is ignored outright rather than rendered.
  const fresh = loaded && loaded.sourceId === sourceId ? loaded : null
  const detail = fresh?.detail ?? null
  const content = fresh?.content ?? null
  const error = fresh?.error ?? ''
  const status = !fresh ? 'loading' : fresh.error && !fresh.detail ? 'error' : 'ready'

  useEffect(() => {
    if (!sourceId) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [sourceId, onClose])

  const warning = useMemo(() => extractionWarning(detail), [detail])

  const chunks = content?.chunks
  const shownChunks = useMemo(
    () => (showAllChunks ? chunks || [] : (chunks || []).slice(0, 3)),
    [chunks, showAllChunks],
  )

  const handleClose = useCallback(() => onClose?.(), [onClose])

  if (!sourceId) return null

  const heading = detail?.title || sourceTitle || 'Source'

  return (
    <div
      className="source-detail"
      role="dialog"
      aria-modal="true"
      aria-label={`Details for ${heading}`}
      onClick={handleClose}
    >
      <div className="source-detail-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="source-detail-head">
          <div className="source-detail-heading">
            <p className="source-detail-eyebrow">
              {detail?.source_type
                ? TYPE_LABELS[detail.source_type] || detail.source_type
                : 'Source'}
            </p>
            <h2 className="source-detail-title">{heading}</h2>
          </div>
          <button
            type="button"
            className="source-detail-close"
            onClick={handleClose}
            aria-label="Close source details"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="source-detail-body">
          {status === 'loading' ? (
            <p className="source-detail-status">Loading what was indexed…</p>
          ) : null}

          {status === 'error' ? (
            <div className="source-detail-alert is-danger">
              <strong>{error}</strong>
            </div>
          ) : null}

          {detail ? (
            <>
              {warning ? (
                <div className={`source-detail-alert is-${warning.tone}`}>
                  <strong>{warning.title}</strong>
                  <p>{warning.body}</p>
                </div>
              ) : null}

              <dl className="source-detail-facts">
                <ProvenanceRow label="Indexed">
                  {formatNumber(detail.chunk_count)} {detail.chunk_count === 1 ? 'chunk' : 'chunks'}
                </ProvenanceRow>
                <ProvenanceRow label="Text">{formatBytesish(detail.char_count)}</ProvenanceRow>
                {detail.language ? (
                  <ProvenanceRow label="Language">{detail.language}</ProvenanceRow>
                ) : null}
                {detail.page_count ? (
                  <ProvenanceRow label="Pages">
                    {formatNumber(detail.non_empty_pages ?? 0)} of {formatNumber(detail.page_count)}{' '}
                    with text
                  </ProvenanceRow>
                ) : null}
                {detail.renamed ? (
                  <ProvenanceRow label="Title">Renamed from “{detail.derived_title}”</ProvenanceRow>
                ) : null}
                <ProvenanceRow label="Original file">
                  Not retained — ContextForge indexes uploads without keeping the source file.
                </ProvenanceRow>
              </dl>

              {detail.url ? (
                <p className="source-detail-url">
                  <a href={detail.url} target="_blank" rel="noreferrer noopener">
                    {detail.url}
                  </a>
                </p>
              ) : null}

              {detail.file_paths?.length ? (
                <section className="source-detail-section">
                  <h3>Indexed files ({formatNumber(detail.file_paths.length)})</h3>
                  <ul className="source-detail-paths">
                    {detail.file_paths.slice(0, 12).map((path) => (
                      <li key={path} title={path}>
                        {path}
                      </li>
                    ))}
                  </ul>
                  {detail.file_paths.length > 12 ? (
                    <p className="source-detail-more">
                      and {formatNumber(detail.file_paths.length - 12)} more
                    </p>
                  ) : null}
                </section>
              ) : null}

              {detail.keywords?.length ? (
                <section className="source-detail-section">
                  <h3>Keywords detected</h3>
                  <div className="source-detail-tags">
                    {detail.keywords.slice(0, 12).map((keyword) => (
                      <span key={keyword} className="source-detail-tag">
                        {keyword}
                      </span>
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          ) : null}

          {error && status === 'ready' ? (
            <p className="source-detail-status">Indexed text unavailable: {error}</p>
          ) : null}

          {shownChunks.length ? (
            <section className="source-detail-section">
              <h3>
                Indexed text
                {content?.truncated ? (
                  <span className="source-detail-truncated">
                    {' '}
                    (first {formatNumber(content.chunk_count)} of{' '}
                    {formatNumber(content.total_chunks)} chunks)
                  </span>
                ) : null}
              </h3>
              <ol className="source-detail-chunks">
                {shownChunks.map((chunk) => (
                  <li key={chunk.chunk_id} className="source-detail-chunk">
                    <div className="source-detail-chunk-head">
                      <span className="source-detail-chunk-index">
                        {chunk.path ? chunk.path : `Chunk ${(chunk.chunk_index ?? 0) + 1}`}
                      </span>
                      <span className="source-detail-chunk-size">
                        {formatNumber(chunk.text.length)} chars
                      </span>
                    </div>
                    <pre className="source-detail-chunk-text">
                      {showAllChunks || chunk.text.length <= PREVIEW_CHARS
                        ? chunk.text
                        : `${chunk.text.slice(0, PREVIEW_CHARS)}…`}
                    </pre>
                  </li>
                ))}
              </ol>
              {chunks.length > 3 ? (
                <button
                  type="button"
                  className="source-detail-toggle"
                  onClick={() => setShowAllChunks((value) => !value)}
                >
                  {showAllChunks ? 'Show less' : `Show all ${formatNumber(chunks.length)} chunks`}
                </button>
              ) : null}
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}
