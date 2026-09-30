import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'

import ContextForgeMark from '../ContextForgeMark'
import {
  GithubMark,
  SOURCE_STATUS,
  SOURCE_TYPE_LABEL,
  SourceGlyph,
  sourceIconClass,
} from '../../lib/sources'

function Brand() {
  const navigate = useNavigate()
  return (
    <button
      className="brand brand-link"
      onClick={() => navigate('/workspace')}
      title="ContextForge workspace"
    >
      <div className="brand-mark" aria-hidden="true">
        <ContextForgeMark size={40} />
      </div>
      <div className="brand-text">
        <span className="brand-title">
          Context<span className="brand-title-accent">Forge</span>
        </span>
        <small>Grounded AI Workspace</small>
      </div>
    </button>
  )
}

// Per-source action menu.  Opens a popover anchored to the row's ⋮ button.
//
// The popover is portalled to <body> and positioned with fixed coordinates
// measured from the trigger.  It has to be: the sidebar has four nested
// clipping ancestors — the row itself (overflow: hidden), the source-list
// scroller (overflow-y: auto / overflow-x: hidden), the sources section and the
// sidebar shell (both overflow: hidden).  An absolutely positioned menu inside
// the row is hard-clipped by all four, and no z-index can rescue it, because
// z-index only orders siblings within one clipping context.  Portalling escapes
// every ancestor, and measuring the trigger gives true viewport coordinates.
//
// It only ever manages a source (rename, remove) and never changes the
// workspace selection, so every interaction stops propagation and the trigger
// sits outside the row's own click handler.
//
// `open` is owned by the Sidebar so at most one menu in the list can be open —
// two overlapping popovers would be ambiguous and awkward to dismiss.
// Positions a portalled popover against its trigger.
//
// Placement is applied straight to the node's style/class rather than held in
// state: the only input is the trigger's viewport rect, so re-rendering on every
// scroll tick would be pure waste.  Reading layout must happen after mount, which
// is what the layout effect below is for.
function usePopoverPlacement(
  open,
  { triggerRef, menuRef, width, minHeight, gap = 6, margin = 8, align = 'left' },
) {
  useLayoutEffect(() => {
    const menu = menuRef.current
    const trigger = triggerRef.current
    if (!open || !menu || !trigger) return undefined

    const place = () => {
      const rect = trigger.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      const openUp = spaceBelow < minHeight + margin && rect.top > spaceBelow
      const top = openUp ? rect.top - minHeight - gap : rect.bottom + gap
      // 'right' hugs the trigger's right edge (row menus); 'left' its left edge
      // (the toolbar menu).  Either way it is clamped inside the viewport.
      const desired = align === 'right' ? rect.right - width : rect.left
      const maxLeft = window.innerWidth - width - margin
      const left = Math.max(margin, Math.min(desired, maxLeft))
      menu.style.top = `${top}px`
      menu.style.left = `${left}px`
      menu.classList.toggle('is-up', openUp)
    }

    place()
    window.addEventListener('resize', place)
    // Capture phase so scrolling any ancestor (the source list) is caught too.
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, triggerRef, menuRef, width, minHeight, gap, margin, align])
}

// Sort popover.  Portalled for the same reason as the row action menu: the
// sidebar clips its own descendants (overflow: hidden on the row, list, section
// and shell), so an in-flow dropdown would be cut off.
const SORT_MENU_WIDTH = 168
const SORT_MENU_MIN_HEIGHT = 132

const SORT_OPTIONS = [
  { id: 'recent', label: 'Recent' },
  { id: 'title', label: 'Title' },
  { id: 'type', label: 'Type' },
]

function SourcesSortMenu({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef(null)
  const menuRef = useRef(null)

  usePopoverPlacement(open, {
    triggerRef,
    menuRef,
    width: SORT_MENU_WIDTH,
    minHeight: SORT_MENU_MIN_HEIGHT,
  })

  useEffect(() => {
    if (!open) return undefined
    const isInside = (node) =>
      (triggerRef.current && triggerRef.current.contains(node)) ||
      (menuRef.current && menuRef.current.contains(node))
    const onPointerDown = (event) => {
      if (!isInside(event.target)) setOpen(false)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const pick = useCallback(
    (id) => {
      onChange?.(id)
      setOpen(false)
    },
    [onChange],
  )

  return (
    <div className="sources-sort" ref={triggerRef}>
      <button
        type="button"
        className={`sources-sort-trigger${open ? ' is-open' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Sort sources"
        title="Sort sources"
        onClick={() => setOpen((prev) => !prev)}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M4 6h13" />
          <path d="M4 12h9" />
          <path d="M4 18h5" />
        </svg>
      </button>

      {open
        ? createPortal(
            <div className="sources-sort-menu" role="menu" aria-label="Sort sources" ref={menuRef}>
              {SORT_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={value === option.id}
                  className={`sources-sort-item${value === option.id ? ' is-active' : ''}`}
                  onClick={() => pick(option.id)}
                >
                  <span>{option.label}</span>
                  {value === option.id ? (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  ) : null}
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}

const MENU_WIDTH = 176
// Three items plus the popover's padding and border.
const MENU_HEIGHT = 132
const MENU_GAP = 6
const VIEWPORT_MARGIN = 8

function SourceActionsMenu({ source, open, onToggle, onClose, onRename, onRemove, onInspect }) {
  const triggerRef = useRef(null)
  const menuRef = useRef(null)

  usePopoverPlacement(open, {
    triggerRef,
    menuRef,
    width: MENU_WIDTH,
    minHeight: MENU_HEIGHT,
    gap: MENU_GAP,
    margin: VIEWPORT_MARGIN,
    align: 'right',
  })

  // Dismiss on outside click or Escape — the two ways a popover is expected to
  // close.  The portalled menu is a sibling of the trigger in the DOM, so both
  // refs have to be consulted or clicking an item would close it first.
  useEffect(() => {
    if (!open) return undefined
    const isInside = (node) =>
      (triggerRef.current && triggerRef.current.contains(node)) ||
      (menuRef.current && menuRef.current.contains(node))
    const onPointerDown = (event) => {
      if (!isInside(event.target)) onClose()
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  const run = useCallback(
    (action) => {
      onClose()
      if (action === 'inspect') onInspect?.(source)
      else if (action === 'rename') onRename?.(source)
      else onRemove?.(source)
    },
    [onClose, onInspect, onRename, onRemove, source],
  )

  return (
    <div className="source-item-menu" ref={triggerRef}>
      <button
        type="button"
        className={`source-item-menu-trigger${open ? ' is-open' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${source.title}`}
        title="Source actions"
        onClick={(event) => {
          event.stopPropagation()
          onToggle()
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="12" cy="5" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="12" cy="19" r="1.8" />
        </svg>
      </button>

      {open
        ? createPortal(
            <div className="source-action-menu" role="menu" ref={menuRef}>
              <button
                type="button"
                role="menuitem"
                className="source-action-item"
                onClick={(event) => {
                  event.stopPropagation()
                  run('inspect')
                }}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                <span>View source details</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="source-action-item"
                onClick={(event) => {
                  event.stopPropagation()
                  run('rename')
                }}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                </svg>
                <span>Rename source</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="source-action-item is-danger"
                onClick={(event) => {
                  event.stopPropagation()
                  run('remove')
                }}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M3 6h18" />
                  <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                </svg>
                <span>Remove source</span>
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}

// The shared knowledge navigator.  Every page renders the same sidebar so the
// brand, the workspace entry point, the knowledge-base categories and the source
// list are identical across the whole product.
//
// The project workspace is the only workspace, so selecting a row here does not
// navigate anywhere — it scopes the workspace instead.  Clicking a row selects
// it; the small checkbox adds or removes one source without disturbing the rest
// of the selection, and the ⋮ menu manages the source without touching the
// selection.
export default function Sidebar({
  sources = [],
  loading = false,
  onAddSource,
  onSelectSource,
  onToggleSource,
  onSelectAllSources,
  onClearSourceSelection,
  selectedSourceIds = [],
  onInspectSource,
  onRenameSource,
  onDeleteSource,
  header,
  // Restricts the Knowledge Base rows to a project source family, e.g.
  // ['pdf', 'docx', 'web', 'text'].  Null/undefined keeps every row.
  scopeTypes = null,
}) {
  // Display order only — the selection and the workspace both work by source id,
  // so re-ordering the list cannot change what is selected or retrieved.
  const [sortKey, setSortKey] = useState('recent')
  const sortedSources = useMemo(() => {
    const list = [...sources]
    if (sortKey === 'title') {
      list.sort((a, b) => (a.title || '').localeCompare(b.title || ''))
    } else if (sortKey === 'type') {
      list.sort((a, b) => {
        const at = SOURCE_TYPE_LABEL[a.type] || a.type || ''
        const bt = SOURCE_TYPE_LABEL[b.type] || b.type || ''
        const byType = at.localeCompare(bt)
        // Break ties by title so equal types don't shuffle between renders.
        return byType !== 0 ? byType : (a.title || '').localeCompare(b.title || '')
      })
    }
    return list
  }, [sources, sortKey])

  // "Select all" is checked only when every source is in the selection, so the
  // header checkbox doubles as the clear-all affordance.
  //
  // Membership, not a count comparison. `selectedIds.length === sources.length`
  // is true for any two same-sized lists, so a selection holding an id that is
  // no longer displayed would light the header while leaving a visible row
  // unselected — and clicking it would then clear the scope instead of
  // selecting the missing row.
  const allSelected =
    sources.length > 0 && sources.every((source) => selectedSourceIds.includes(source.id))

  // Which source's ⋮ menu is open, if any.  Null when all are closed.
  const [openMenuId, setOpenMenuId] = useState(null)
  const closeMenu = useCallback(() => setOpenMenuId(null), [])
  const toggleMenu = useCallback((id) => {
    setOpenMenuId((current) => (current === id ? null : id))
  }, [])

  const pdfCount = sources.filter((s) => s.type === 'pdf').length
  const webCount = sources.filter((s) => s.type === 'web').length
  const githubCount = sources.filter((s) => s.type === 'github').length
  const youtubeCount = sources.filter((s) => s.type === 'youtube').length
  const textCount = sources.filter((s) => s.type === 'text').length
  const docxCount = sources.filter((s) => s.type === 'docx').length

  const kbRows = [
    {
      id: 'all',
      type: 'all',
      label: 'All Documents',
      count: sources.length,
      icon: <SourceGlyph type="text" size={14} />,
    },
    {
      id: 'pdf',
      type: 'pdf',
      label: 'PDFs',
      count: pdfCount,
      icon: <SourceGlyph type="pdf" size={14} />,
    },
    {
      id: 'docx',
      type: 'docx',
      label: 'Word Docs',
      count: docxCount,
      icon: <SourceGlyph type="docx" size={14} />,
    },
    {
      id: 'web',
      type: 'web',
      label: 'Web Pages',
      count: webCount,
      icon: <SourceGlyph type="web" size={14} />,
    },
    {
      id: 'github',
      type: 'github',
      label: 'GitHub Repos',
      count: githubCount,
      icon: <GithubMark size={14} />,
    },
    {
      id: 'youtube',
      type: 'youtube',
      label: 'YouTube Videos',
      count: youtubeCount,
      icon: <SourceGlyph type="youtube" size={14} />,
    },
    {
      id: 'text',
      type: 'text',
      label: 'Text',
      count: textCount,
      icon: <SourceGlyph type="text" size={14} />,
    },
  ]

  // A scoped project only lists its own family.  The "All Documents" rollup
  // is kept only when several types remain — otherwise it duplicates the
  // single row.
  const visibleRows = scopeTypes
    ? kbRows.filter((row) =>
        row.type === 'all' ? scopeTypes.length > 1 : scopeTypes.includes(row.type),
      )
    : kbRows

  return (
    <aside className="sidebar-shell">
      <Brand />

      <button className="add-knowledge-btn" onClick={onAddSource}>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span>Add Source</span>
      </button>

      {header}

      <section className="kb-section">
        <div className="section-title">Knowledge Base</div>
        <div className="kb-rows">
          {visibleRows.map((row) => (
            <div className="kb-row" key={row.id}>
              {row.icon}
              <span className="kb-label">{row.label}</span>
              <span className="kb-count">{row.count}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="sources-section" aria-label="Sources">
        {/* Compact toolbar: sort control on the left, "Select all" with its
            checkbox on the right.  There is deliberately no "My Sources"
            heading — the section carries an aria-label instead, so the name is
            still available to a screen reader. */}
        <div className="sources-toolbar">
          <SourcesSortMenu value={sortKey} onChange={setSortKey} />
          {sources.length > 0 ? (
            <label
              className="sources-select-all"
              title={
                allSelected
                  ? 'Clear the selection — search every source'
                  : 'Select every source in this project'
              }
            >
              <span>Select all</span>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => (allSelected ? onClearSourceSelection?.() : onSelectAllSources?.())}
                aria-label="Select all sources"
              />
            </label>
          ) : null}
        </div>
        <div className="source-list">
          {loading && sources.length === 0 ? (
            <div className="empty-source">Loading sources…</div>
          ) : sources.length === 0 ? (
            <div className="empty-source">No sources added yet.</div>
          ) : (
            sortedSources.map((source) => {
              const status = SOURCE_STATUS[source.status] || SOURCE_STATUS.processing
              const active = selectedSourceIds.includes(source.id)
              return (
                <div
                  className={`source-item-compact${active ? ' is-active' : ''}`}
                  key={source.id}
                  onClick={() => onSelectSource?.(source.id)}
                  role="button"
                  tabIndex={0}
                  aria-pressed={active}
                  title={
                    active
                      ? 'Selected — click to remove from the workspace scope'
                      : 'Click to use this source in the workspace'
                  }
                >
                  <div className={sourceIconClass(source.type)}>
                    <SourceGlyph type={source.type} size={16} />
                  </div>
                  <div className="source-item-body">
                    <span className="source-item-title">{source.title}</span>
                    <span className="source-item-type">
                      · {SOURCE_TYPE_LABEL[source.type] || source.type || 'Source'}
                    </span>
                  </div>
                  {/* Indexed is the normal state, so the dot only appears when
                      there is something to act on. */}
                  {source.status !== 'indexed' ? (
                    <div className="source-item-status">
                      <span className={status.dot} title={status.label} />
                    </div>
                  ) : null}
                  <SourceActionsMenu
                    source={source}
                    open={openMenuId === source.id}
                    onToggle={() => toggleMenu(source.id)}
                    onClose={closeMenu}
                    onInspect={onInspectSource}
                    onRename={onRenameSource}
                    onRemove={onDeleteSource}
                  />
                  <label
                    className="source-item-check"
                    title="Add or remove this source from the selection"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() => onToggleSource?.(source.id)}
                      aria-label={`Use ${source.title} in the workspace`}
                    />
                  </label>
                </div>
              )
            })
          )}
        </div>
      </section>
    </aside>
  )
}
