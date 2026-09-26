import { useEffect, useMemo, useState } from 'react'

import GraphViewer from '../GraphViewer'
import { repositoryDataFlow } from '../../../services/api'
import {
  ViewShell,
  ViewToolbar,
  Card,
  Metric,
  Badge,
  Legend,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../ui/primitives'

// Detected execution flow kinds -> label + node colour. Purely data-driven.
const KIND_META = {
  route: { label: 'API / route', color: '#8b949e' },
  input: { label: 'Entry point', color: '#2f5fe0' },
  output: { label: 'Output', color: '#2f5fe0' },
  service: { label: 'Service', color: '#4377FD' },
  storage: { label: 'Storage / data', color: '#2f5fe0' },
  external: { label: 'External API', color: '#8b949e' },
  llm: { label: 'LLM / model', color: '#6b92ff' },
  core: { label: 'Core pipeline', color: '#4377FD' },
  transport: { label: 'Transport', color: '#8b949e' },
  module: { label: 'Module', color: '#4377FD' },
  file: { label: 'File', color: '#6b92ff' },
  func: { label: 'Function', color: '#2f5fe0' },
}

const GRAPH_DIMS = { width: 1240, height: 860 }

const accentFor = (node) => KIND_META[node.kind]?.color || '#8b949e'

// Layered left-to-right layout: depth (from entry) -> x, sibling index -> y.
function layoutFlow(nodes, edges) {
  if (!nodes.length) return nodes
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const children = new Map(nodes.map((n) => [n.id, []]))
  const hasParent = new Set()
  edges.forEach((e) => {
    if (byId.has(e.source) && byId.has(e.target)) {
      children.get(e.source)?.push(e.target)
      hasParent.add(e.target)
    }
  })

  const entryId =
    nodes.find((n) => n.entry)?.id || nodes.find((n) => !hasParent.has(n.id))?.id || nodes[0].id

  const depth = new Map([[entryId, 0]])
  const levels = new Map([[0, [entryId]]])
  const queue = [[entryId, 0]]
  while (queue.length) {
    const [cur, d] = queue.shift()
    for (const child of children.get(cur) || []) {
      if (!depth.has(child)) {
        depth.set(child, d + 1)
        if (!levels.has(d + 1)) levels.set(d + 1, [])
        levels.get(d + 1).push(child)
        queue.push([child, d + 1])
      }
    }
  }

  const DX = 250
  const ROW_H = 88
  const positions = {}
  levels.forEach((ids, d) => {
    ids.forEach((id, i) => {
      positions[id] = { x: d * DX + 40, y: i * ROW_H + 60 }
    })
  })
  nodes
    .filter((n) => !positions[n.id])
    .forEach((n, i) => {
      positions[n.id] = { x: (levels.size + 1) * DX + 40, y: (i % 12) * ROW_H + 60 }
    })

  return nodes.map((n) => ({ ...n, x: positions[n.id].x, y: positions[n.id].y }))
}

function NodeDetails({ node }) {
  if (!node) {
    return (
      <Card title="Node details">
        <p className="rv-muted-block">
          Select a node in the flow to inspect paths, callers and dependencies.
        </p>
      </Card>
    )
  }
  const kind = KIND_META[node.kind]
  const list = (items) => (items && items.length ? items.join(', ') : '—')
  return (
    <Card
      title="Node details"
      actions={
        <div className="rv-inline-badges">
          <Badge tone="neutral">{kind?.label || node.kind}</Badge>
          {node.entry ? <Badge tone="teal">Entry point</Badge> : null}
        </div>
      }
    >
      <div className="rv-node-head">
        <span className="rv-node-dot" style={{ background: kind?.color }} />
        <code className="rv-code-strong">{node.label}</code>
      </div>
      <div className="rv-metric-grid">
        <Metric label="Path" value={<code className="rv-code">{node.path || '—'}</code>} />
        <Metric label="Functions" value={<code className="rv-code">{list(node.functions)}</code>} />
        <Metric label="Callers" value={<code className="rv-code">{list(node.callers)}</code>} />
        <Metric label="Callees" value={<code className="rv-code">{list(node.callees)}</code>} />
        <Metric
          label="Dependencies"
          value={<code className="rv-code">{list(node.dependencies)}</code>}
        />
        <Metric label="Caller count" value={node.dependents || 0} />
        <Metric label="Depends on" value={node.deps || 0} />
        {node.latencyMs != null ? (
          <Metric label="Measured latency" value={`${node.latencyMs.toFixed(1)} ms`} />
        ) : null}
      </div>
    </Card>
  )
}

function FlowGraph({ flow }) {
  const [selected, setSelected] = useState(null)
  const nodes = useMemo(() => layoutFlow(flow.nodes, flow.edges), [flow])
  const selectedNode = useMemo(
    () => flow.nodes.find((n) => n.id === selected) || null,
    [selected, flow],
  )

  const legend = useMemo(() => {
    const kinds = [...new Set(flow.nodes.map((n) => n.kind))]
    return kinds
      .filter((k) => KIND_META[k])
      .map((k) => ({ label: KIND_META[k].label, color: KIND_META[k].color }))
  }, [flow])

  return (
    <>
      <Legend items={legend} />
      <GraphViewer
        nodes={nodes}
        edges={flow.edges}
        dims={GRAPH_DIMS}
        selected={selected}
        onSelect={setSelected}
        accentFor={accentFor}
        className="rv-graph rv-graph-flow"
        height={520}
      />
      <div className="rv-grid rv-grid-2">
        <NodeDetails node={selectedNode} />
        <Card title="Coupling hotspots" meta="From code analysis">
          {flow.bottlenecks && flow.bottlenecks.length ? (
            <div className="rv-fact-list">
              {flow.bottlenecks.map((b) => (
                <div className="rv-fact-row" key={b.id}>
                  <span className="rv-fact-main">{b.path || b.label}</span>
                  <b>
                    {b.dependents} caller{b.dependents === 1 ? '' : 's'}
                  </b>
                </div>
              ))}
            </div>
          ) : (
            <p className="rv-muted-block is-ok">No coupling hotspots detected in this flow.</p>
          )}
        </Card>
      </div>
    </>
  )
}

export default function DataFlowView({ analysisId }) {
  const [flows, setFlows] = useState([])
  const [status, setStatus] = useState('loading') // loading | ok | empty | error
  const [error, setError] = useState('')
  const [activeId, setActiveId] = useState(null)

  useEffect(() => {
    if (!analysisId) {
      setFlows([])
      setStatus('empty')
      return
    }
    let cancelled = false
    setStatus('loading')
    setError('')
    repositoryDataFlow(analysisId)
      .then((data) => {
        if (cancelled) return
        const flowList = data && typeof data === 'object' ? Object.values(data) : []
        setFlows(flowList)
        setStatus(flowList.length ? 'ok' : 'empty')
        setActiveId((prev) =>
          flowList.some((f) => f.id === prev) ? prev : flowList[0]?.id || null,
        )
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message || 'Failed to load data flow.')
        setFlows([])
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [analysisId])

  const active = useMemo(() => flows.find((f) => f.id === activeId) || flows[0], [flows, activeId])

  const flowSwitcher = (
    <div className="rv-flow-switcher" role="tablist" aria-label="Detected flows">
      {flows.map((f) => (
        <button
          key={f.id}
          type="button"
          role="tab"
          aria-selected={f.id === active?.id}
          className={f.id === active?.id ? 'is-active' : ''}
          onClick={() => setActiveId(f.id)}
          title={f.entry}
        >
          {f.title || f.id}
        </button>
      ))}
    </div>
  )
  const showSwitcher = status === 'ok' && flows.length > 1

  if (status === 'loading') {
    return (
      <ViewShell>
        <LoadingState label="Analyzing data flow…" />
      </ViewShell>
    )
  }

  if (status === 'error') {
    return (
      <ViewShell>
        <ErrorState title="Data flow analysis failed" message={error} />
      </ViewShell>
    )
  }

  if (status === 'empty' || !active) {
    return (
      <ViewShell>
        <EmptyState
          title="No executable flow detected"
          hint="No runnable entry points (routes, CLIs, mains) with a call chain were found in this repository."
        />
      </ViewShell>
    )
  }

  return (
    <ViewShell>
      {showSwitcher ? <ViewToolbar left={flowSwitcher} /> : null}
      <FlowGraph key={active?.id} flow={active} />
    </ViewShell>
  )
}
