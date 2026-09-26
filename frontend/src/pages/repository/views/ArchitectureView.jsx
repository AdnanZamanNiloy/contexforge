import { useMemo, useState } from 'react'

import GraphViewer from '../GraphViewer'
import InfoPanel from '../components/InfoPanel'
import { ViewShell, ViewHeader, Legend, StatTile } from '../ui/primitives'
import { IconExpand, IconGrid, IconSearch } from '../ui/icons'

const LAYOUTS = [
  { id: 'Hierarchical', label: 'Hierarchy' },
  { id: 'Tree', label: 'Tree' },
  { id: 'Radial', label: 'Radial' },
]

const KIND_LEGEND = [
  { label: 'Repository', color: '#9aa8ff' },
  { label: 'Area', color: '#7aa2f7' },
  { label: 'Directory', color: '#67e0c8' },
  { label: 'Module', color: '#6f9ff2' },
  { label: 'File', color: '#8f7bf5' },
]

export default function ArchitectureView({
  architecture = { nodes: [], edges: [] },
  graphDimensions = { width: 1240, height: 860 },
}) {
  const [selected, setSelected] = useState(null)
  const [layout, setLayout] = useState('Hierarchical')
  const [query, setQuery] = useState('')
  const [fullscreen, setFullscreen] = useState(false)

  const nodes = useMemo(() => architecture.nodes || [], [architecture])
  const edges = useMemo(() => architecture.edges || [], [architecture])

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selected) || null,
    [selected, nodes],
  )

  const highlighted = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return null
    const ids = new Set(
      nodes
        .filter(
          (n) =>
            n.label.toLowerCase().includes(q) ||
            (n.path || n.meta?.path || '').toLowerCase().includes(q),
        )
        .map((n) => n.id),
    )
    return ids.size ? ids : null
  }, [query, nodes])

  const graphNodes = useMemo(() => {
    if (layout === 'Radial') return radialSpread(nodes)
    if (layout === 'Tree') return treeLayout(nodes, edges)
    return nodes
  }, [layout, nodes, edges])

  const matchCount = highlighted ? highlighted.size : null

  const toolbar = (
    <>
      <label className="rv-search">
        <IconSearch width={14} height={14} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search nodes…"
          spellCheck={false}
          aria-label="Search architecture nodes"
        />
        {query ? (
          <button
            type="button"
            className="rv-search-clear"
            onClick={() => setQuery('')}
            aria-label="Clear search"
          >
            ×
          </button>
        ) : null}
      </label>
      {matchCount != null ? (
        <span className="rv-toolbar-note">
          {matchCount} match{matchCount === 1 ? '' : 'es'}
        </span>
      ) : null}
      <div className="rv-segmented" role="group" aria-label="Graph layout">
        {LAYOUTS.map((l) => (
          <button
            key={l.id}
            type="button"
            className={layout === l.id ? 'is-active' : ''}
            onClick={() => setLayout(l.id)}
          >
            {l.label}
          </button>
        ))}
      </div>
    </>
  )

  const isEmpty = nodes.length === 0

  return (
    <ViewShell>
      <ViewHeader
        eyebrow="Architecture"
        title="System structure"
        description="Hierarchical decomposition of the repository from top-level areas down to files."
        actions={
          <button
            type="button"
            className="rv-btn rv-btn-ghost"
            onClick={() => setFullscreen((f) => !f)}
          >
            <IconExpand width={14} height={14} />
            {fullscreen ? 'Exit full screen' : 'Full screen'}
          </button>
        }
      />

      {isEmpty ? (
        <StatTile
          label="Nodes"
          value="0"
          hint="No architecture graph was produced for this repository."
        />
      ) : (
        <>
          <div className="rv-toolbar">
            <div className="rv-toolbar-left">{toolbar}</div>
            <Legend items={KIND_LEGEND} />
          </div>

          <GraphViewer
            nodes={graphNodes}
            edges={edges}
            dims={graphDimensions}
            selected={selected}
            onSelect={setSelected}
            highlight={highlighted}
            fullscreen={fullscreen}
            onToggleFullscreen={() => setFullscreen((f) => !f)}
            className="rv-graph rv-graph-architecture"
            height={560}
          />

          <InfoPanel node={selectedNode} />
        </>
      )}

      {!selected && !isEmpty ? (
        <div className="rv-hint-strip">
          <IconGrid width={15} height={15} />
          Select a node in the graph to inspect its metrics, dependencies and recent changes.
        </div>
      ) : null}
    </ViewShell>
  )
}

// Light radial remapping so the layout control visibly changes the graph
// without a graph-layout dependency.
function radialSpread(nodes) {
  const root = nodes.find((n) => n.kind === 'repo')
  if (!root) return nodes
  const cx = 620
  const cy = 430
  const others = nodes.filter((n) => n.id !== root.id)
  const spread = others.map((n, i) => {
    const radius = 260 + (i % 3) * 40
    const angle = (i / Math.max(1, others.length - 1)) * Math.PI * 2 - Math.PI / 2
    return { ...n, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
  })
  return [{ ...root, x: cx, y: cy }, ...spread]
}

// Tidy rooted tree from the "contains" hierarchy (repo -> area -> dir ->
// module -> file). Depth grows left-to-right; siblings stack vertically.
function treeLayout(nodes, edges) {
  if (!nodes.length) return nodes
  const label = (id) => nodes.find((n) => n.id === id)?.label || id

  const children = new Map(nodes.map((n) => [n.id, []]))
  const hasParent = new Set()
  edges.forEach((e) => {
    if (e.kind !== 'contains') return
    if (children.has(e.source)) {
      children.get(e.source).push(e.target)
      hasParent.add(e.target)
    }
  })
  children.forEach((arr) => arr.sort((a, b) => label(a).localeCompare(label(b))))

  const rootId =
    nodes.find((n) => n.kind === 'repo')?.id || nodes.find((n) => !hasParent.has(n.id))?.id
  if (!rootId) return nodes

  const DX = 240
  const DY = 62
  const pos = new Map()
  let leaf = 0

  const walk = (id, depth) => {
    const kids = children.get(id) || []
    if (!kids.length) {
      pos.set(id, { x: depth * DX, y: leaf * DY })
      leaf += 1
      return
    }
    kids.forEach((k) => walk(k, depth + 1))
    const avgY = kids.reduce((s, k) => s + pos.get(k).y, 0) / kids.length
    pos.set(id, { x: depth * DX, y: avgY })
  }
  walk(rootId, 0)

  const maxDepth = Math.max(
    0,
    ...nodes.filter((n) => pos.has(n.id)).map((n) => Math.round(pos.get(n.id).x / DX)),
  )
  nodes
    .filter((n) => !pos.has(n.id))
    .forEach((n, i) => {
      const col = Math.floor(i / 10)
      pos.set(n.id, { x: (maxDepth + 1) * DX + col * 220, y: (i % 10) * DY })
    })

  return nodes.map((n) => {
    const p = pos.get(n.id)
    return { ...n, x: p.x, y: p.y }
  })
}
