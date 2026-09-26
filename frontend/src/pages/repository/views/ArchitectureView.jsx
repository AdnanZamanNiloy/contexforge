import { useMemo, useState } from 'react'

import GraphViewer from '../GraphViewer'
import InfoPanel from '../components/InfoPanel'
import { ViewShell, Legend, StatTile } from '../ui/primitives'
import { IconExpand, IconSearch } from '../ui/icons'

const LAYOUTS = [
  { id: 'Hierarchical', label: 'Hierarchy' },
  { id: 'Tree', label: 'Tree' },
  { id: 'Radial', label: 'Radial' },
]

const KIND_LEGEND = [
  { label: 'Repository', color: '#2fd6a1' },
  { label: 'File', color: '#10b981' },
]

export default function ArchitectureView({
  architecture = { nodes: [], edges: [] },
  graphDimensions = { width: 1240, height: 860 },
}) {
  const [selected, setSelected] = useState(null)
  const [layout, setLayout] = useState('Hierarchical')
  const [query, setQuery] = useState('')
  const [fullscreen, setFullscreen] = useState(false)

  const sourceNodes = useMemo(() => architecture.nodes || [], [architecture])
  const sourceEdges = useMemo(() => architecture.edges || [], [architecture])

  // The backend emits repo → area → directory → module → file. Collapse that to
  // two layers — the repository root and its files hanging directly beneath it.
  const { nodes, edges } = useMemo(
    () => flattenHierarchy(sourceNodes, sourceEdges),
    [sourceNodes, sourceEdges],
  )

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
    return twoLayerLayout(nodes, graphDimensions)
  }, [layout, nodes, edges, graphDimensions])

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
            <div className="rv-toolbar-right">
              <Legend items={KIND_LEGEND} />
              <button
                type="button"
                className="rv-btn rv-btn-ghost"
                onClick={() => setFullscreen((f) => !f)}
              >
                <IconExpand width={14} height={14} />
                {fullscreen ? 'Exit full screen' : 'Full screen'}
              </button>
            </div>
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
    </ViewShell>
  )
}

// Collapse the backend's multi-level hierarchy (repo → area → directory →
// module → file) down to two layers: the repository root plus every leaf
// (file), re-parented straight to the root. Intermediate containers only add
// rows and labels the graph doesn't need.
function flattenHierarchy(nodes, edges) {
  if (!nodes.length) return { nodes: [], edges: [] }
  const root = nodes.find((n) => n.kind === 'repo') || nodes[0]
  const hasChildren = new Set(edges.filter((e) => e.kind === 'contains').map((e) => e.source))
  const leaves = nodes
    .filter((n) => n.id !== root.id && !hasChildren.has(n.id))
    .sort((a, b) =>
      (a.path || a.meta?.path || a.label || '').localeCompare(
        b.path || b.meta?.path || b.label || '',
      ),
    )
  return {
    nodes: [root, ...leaves],
    edges: leaves.map((n) => ({ source: root.id, target: n.id, kind: 'contains' })),
  }
}

// Two-row arrangement: the root centred on the top row, its files evenly
// spaced on the row beneath it.
function twoLayerLayout(nodes, dims) {
  const root = nodes.find((n) => n.kind === 'repo') || nodes[0]
  if (!root) return nodes
  const children = nodes.filter((n) => n.id !== root.id)
  const width = dims?.width || 1240
  const cx = width / 2
  if (!children.length) return [{ ...root, x: cx, y: 260 }]

  const gap = Math.min(200, Math.max(96, (width - 160) / Math.max(1, children.length - 1)))
  const startX = cx - (gap * (children.length - 1)) / 2
  return [
    { ...root, x: cx, y: 130 },
    ...children.map((n, i) => ({ ...n, x: startX + i * gap, y: 440 })),
  ]
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

// Tidy rooted tree from the "contains" hierarchy (root on the left, files
// stacked to its right). Depth grows left-to-right; siblings stack vertically.
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
