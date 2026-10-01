import { useEffect, useMemo, useState } from 'react'

import { estimateContext } from '../services/api'

// What the current source selection actually costs, and how much of it will be
// used.
//
// Selecting sources is the workspace's primary control, but it used to do almost
// nothing visible: retrieval pulled a fixed 20 candidates and kept the best 5, so
// adding a fourth document changed the prompt very little. On a real corpus the
// whole knowledge base is ~71k tokens while a single answer is built from ~2.5k —
// a user selecting documents to reason across them was mostly selecting
// exclusions, without any way to see that.
//
// This makes the gap legible and gives it a lever:
//   * the readout shows selected material against material used, because the
//     ratio is the thing that was previously invisible;
//   * depth changes real retrieval limits, so "I want more context" does
//     something. It is clamped to what the selection can justify, and reports
//     the depth actually in force rather than the one requested.
//
// Costs nothing to run: the estimator makes no embedding, retrieval, rerank or
// generation call, so it is safe to re-run on every selection change.

const DEPTHS = [
  {
    id: 'focused',
    label: 'Focused',
    hint: 'A few chunks from one or two sources. Fastest, and right when one document holds the answer.',
  },
  {
    id: 'balanced',
    label: 'Balanced',
    hint: 'More sources and more of each, so several documents can be reasoned across.',
  },
  {
    id: 'broad',
    label: 'Broad',
    hint: 'As much of the selection as the prompt will hold. Slowest.',
  },
]

function formatTokens(count) {
  if (!count || count < 0) return '0'
  if (count < 1000) return String(count)
  return `${(count / 1000).toFixed(count < 10000 ? 1 : 0)}k`
}

export default function ContextMeter({
  sourceIds = [],
  depth = 'focused',
  onDepthChange,
  disabled = false,
  className = '',
}) {
  const [loaded, setLoaded] = useState(null)
  const [expanded, setExpanded] = useState(false)

  // Sorted so re-selecting the same sources in a different order does not
  // re-request; the estimate depends on the set, not the sequence.
  const selectionKey = useMemo(() => [...sourceIds].sort().join(' '), [sourceIds])
  const requestedIds = useMemo(() => selectionKey.split(' ').filter(Boolean), [selectionKey])

  useEffect(() => {
    if (disabled) return undefined

    let cancelled = false

    // Debounced: clicking through several sources would otherwise fire a burst
    // of requests, and the answer only matters once the user settles.
    const timer = setTimeout(async () => {
      try {
        const data = await estimateContext(requestedIds, depth)
        // The effect cleanup already cancels superseded requests; this guard
        // covers a response that lands after a newer one within the same effect.
        if (cancelled) return
        setLoaded({ key: selectionKey, depth, data })
      } catch {
        // A failed estimate must never block asking a question, so the meter
        // simply disappears rather than showing an error in the composer.
        if (cancelled) return
        setLoaded(null)
      }
    }, 250)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [requestedIds, selectionKey, depth, disabled])

  // A payload for a different selection or depth is ignored rather than shown,
  // which is also what keeps a stale estimate on screen while a new one loads.
  const fresh = loaded && loaded.key === selectionKey && loaded.depth === depth ? loaded : null
  const estimate = fresh?.data ?? null

  if (disabled) return null
  // A reserved-height placeholder keeps the composer from jumping when the
  // estimate arrives, and disappears entirely if the request failed.
  if (!estimate)
    return <div className={`context-meter is-loading ${className}`} aria-hidden="true" />

  const usablePct = Math.round((estimate.usable_fraction || 0) * 100)
  // Sources the depth will not read. This is a real ceiling on breadth, and it
  // is worth naming — but it is not a rejection of the setting the user picked,
  // so it is reported as a cap rather than as the depth being "reduced".
  const droppedCount = (estimate.dropped_source_ids || []).length

  return (
    <div className={`context-meter ${className}`}>
      <button
        type="button"
        className="context-meter-summary"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label="Context details"
      >
        <span className="context-meter-gauge" aria-hidden="true">
          <span
            className="context-meter-gauge-fill"
            style={{ width: `${Math.max(3, usablePct)}%` }}
          />
        </span>
        <span className="context-meter-numbers">
          <strong>{formatTokens(estimate.prompt_token_estimate)}</strong>
          <span className="context-meter-of">
            of {formatTokens(estimate.total_token_count)} tokens used
          </span>
        </span>
        <span className="context-meter-chevron" aria-hidden="true">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          >
            <path d={expanded ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
          </svg>
        </span>
      </button>

      {expanded ? (
        <div className="context-meter-detail">
          <p className="context-meter-explainer">
            “{DEPTHS.find((d) => d.id === estimate.depth)?.label}” reads the best{' '}
            {estimate.prompt_chunk_limit} chunks overall, and at most{' '}
            {estimate.per_source_cap} from any one source. A larger selection is
            therefore sampled rather than read whole. Widen the depth to read more
            of it.
          </p>

          <ul className="context-meter-sources">
            {estimate.sources.map((source) => {
              const dropped = estimate.dropped_source_ids.includes(source.source_id)
              return (
                <li
                  key={source.source_id}
                  className={`context-meter-source${dropped ? ' is-dropped' : ''}`}
                >
                  <span className="context-meter-source-title">{source.title}</span>
                  <span className="context-meter-source-meta">
                    {formatTokens(source.token_count)} tokens
                    {dropped ? ' · not used at this depth' : ''}
                  </span>
                </li>
              )
            })}
          </ul>

          {estimate.missing_source_ids.length ? (
            <p className="context-meter-warning">
              {estimate.missing_source_ids.length} selected source
              {estimate.missing_source_ids.length === 1 ? '' : 's'} no longer exist and will be
              ignored.
            </p>
          ) : null}

          {droppedCount > 0 ? (
            <p className="context-meter-warning">
              {droppedCount} of {estimate.source_count} selected source
              {estimate.source_count === 1 ? '' : 's'} exceed what “
              {DEPTHS.find((d) => d.id === estimate.depth)?.label}” reads, and will not be
              used. Widen the depth to include {droppedCount === 1 ? 'it' : 'them'}.
            </p>
          ) : null}

          {estimate.beyond_diminishing_returns ? (
            <p className="context-meter-warning">
              This selection is very large. Past roughly 60k tokens, widening the depth is unlikely
              to change the answer much.
            </p>
          ) : null}

          <div className="context-meter-depths" role="group" aria-label="Context depth">
            {DEPTHS.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`context-meter-depth${option.id === estimate.depth ? ' is-active' : ''}`}
                onClick={() => onDepthChange?.(option.id)}
                title={option.hint}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

