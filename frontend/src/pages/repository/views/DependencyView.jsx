import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import GraphViewer from '../GraphViewer'
import { getRepositoryDependencies } from '../../../services/api'
import {
  ViewShell,
  ViewHeader,
  Card,
  StatTile,
  Badge,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../ui/primitives'

const COUPLE_LIMIT = 3
const RISK_LIMIT = 3
const DEPTH = 3

export default function DependencyView({ analysisId, dependencyGraph = { nodes: [], edges: [] } }) {
  const [selected, setSelected] = useState(null)
  const [graph, setGraph] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const lastAnalysisId = useRef(null)

  // Reset the selection whenever a new analysis loads so we never point at a
  // node that does not exist in the fresh graph.
  useEffect(() => {
    if (lastAnalysisId.current && lastAnalysisId.current !== analysisId) {
      setSelected(null)
    }
    lastAnalysisId.current = analysisId
  }, [analysisId])

  useEffect(() => {
    if (!analysisId) {
      setGraph(dependencyGraph || { nodes: [], edges: [] })
      return
    }
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await getRepositoryDependencies(analysisId, { selected, depth: DEPTH })
        if (!cancelled) setGraph(data || { nodes: [], edges: [] })
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load dependencies.')
          setGraph(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [analysisId, selected, dependencyGraph])

  const nodes = useMemo(() => graph?.nodes || [], [graph])
  const edges = useMemo(() => graph?.edges || [], [graph])
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const label = useCallback(
    (id) => nodeById.get(id)?.label || nodeById.get(id)?.meta?.path || id,
    [nodeById],
  )

  const selectedNode = nodeById.get(selected)
  const selectedMeta = {
    deps: selectedNode?.meta?.deps ?? 0,
    dependents: selectedNode?.meta?.dependents ?? 0,
  }

  const summary = useMemo(() => {
    const linkEdges = edges.filter((e) => e.kind !== 'contains')
    return {
      outgoing: linkEdges.filter((e) => e.source === selected),
      incoming: linkEdges.filter((e) => e.target === selected),
    }
  }, [selected, edges])

  const facts = useMemo(
    () => ({
      coupled: coupledModules(nodes, edges, label, COUPLE_LIMIT),
      cycles: findCycles(nodes, edges),
      risky: riskyDependencies(nodes, edges, RISK_LIMIT),
    }),
    [nodes, edges, label],
  )

  const isEmpty = !loading && !error && nodes.length === 0
  const linkCount = edges.filter((e) => e.kind !== 'contains').length

  return (
    <ViewShell>
      <ViewHeader
        eyebrow="Dependencies"
        title="Module coupling"
        description="Incoming, outgoing and circular relationships between the repository's modules."
        actions={
          <div className="rv-inline-stats">
            <span className="rv-inline-stat">
              <b>{nodes.length}</b> nodes
            </span>
            <span className="rv-inline-stat">
              <b>{linkCount}</b> edges
            </span>
            <span className="rv-inline-stat">
              <b>{facts.cycles.length}</b> cycles
            </span>
          </div>
        }
      />

      {loading ? (
        <LoadingState label="Building dependency graph…" />
      ) : error ? (
        <ErrorState title="Dependency analysis failed" message={error} />
      ) : isEmpty ? (
        <EmptyState
          title="No source dependencies found"
          hint="No import relationships could be extracted from this repository."
        />
      ) : (
        <>
          <GraphViewer
            nodes={nodes}
            edges={edges}
            selected={selected}
            onSelect={setSelected}
            className="rv-graph rv-graph-dependency"
            height={440}
          />

          <div className="rv-grid rv-grid-2">
            <Card
              title="Incoming"
              meta={selected ? label(selected) : 'Select a node'}
              actions={<Badge tone="accent">{summary.incoming.length}</Badge>}
            >
              <DepTagList
                empty={selected ? 'No incoming dependencies' : 'Select a node in the graph'}
                edges={summary.incoming}
                direction="in"
                label={label}
                onSelect={setSelected}
              />
            </Card>

            <Card
              title="Outgoing"
              meta={selected ? label(selected) : 'Select a node'}
              actions={<Badge tone="teal">{summary.outgoing.length}</Badge>}
            >
              <DepTagList
                empty={selected ? 'No outgoing dependencies' : 'Select a node in the graph'}
                edges={summary.outgoing}
                direction="out"
                label={label}
                onSelect={setSelected}
              />
            </Card>
          </div>

          {selected ? (
            <div className="rv-grid rv-grid-3">
              <StatTile
                label="Fan-in"
                value={selectedMeta.dependents}
                hint="Modules that depend on this"
              />
              <StatTile label="Fan-out" value={selectedMeta.deps} hint="Modules this depends on" />
              <StatTile
                label="Risk"
                value={selectedNode?.meta?.risk || 'Low'}
                tone={riskStatTone(selectedNode?.meta?.risk)}
                hint="Heuristic coupling risk"
              />
            </div>
          ) : null}

          <div className="rv-grid rv-grid-3">
            <FactCard title="Highly coupled modules" empty="No significant coupling detected">
              {facts.coupled.map((c) => (
                <div className="rv-fact-row" key={`${c.a}-${c.b}`}>
                  <span className="rv-fact-main">
                    {label(c.a)} <span className="rv-fact-arrow">↔</span> {label(c.b)}
                  </span>
                  <b>{c.count} links</b>
                </div>
              ))}
            </FactCard>

            <FactCard
              title="Circular dependencies"
              empty="No cycles found"
              tone={facts.cycles.length ? 'warn' : 'ok'}
            >
              {facts.cycles.map((cycle, i) => (
                <div className="rv-fact-row" key={`cycle-${i}`}>
                  <span className="rv-fact-main is-warn">
                    {cycle.map((id) => label(id)).join(' → ')}
                  </span>
                  <Badge tone="warn">cycle</Badge>
                </div>
              ))}
            </FactCard>

            <FactCard title="Risky dependencies" empty="No high-risk modules">
              {facts.risky.map((r) => (
                <div className="rv-fact-row" key={`risk-${r.id}`}>
                  <span className="rv-fact-main">{label(r.id)}</span>
                  <Badge tone={r.risk === 'Critical' || r.risk === 'High' ? 'warn' : 'neutral'}>
                    {r.risk}
                  </Badge>
                </div>
              ))}
            </FactCard>
          </div>
        </>
      )}
    </ViewShell>
  )
}

function DepTagList({ edges, direction, label, onSelect, empty }) {
  if (!edges.length) return <p className="rv-muted-block">{empty}</p>
  const keyName = direction === 'in' ? 'source' : 'target'
  return (
    <div className="rv-tag-list">
      {edges.map((e) => (
        <button
          key={`${direction}-${e.source}-${e.target}-${e.kind}`}
          type="button"
          className={`rv-tag is-${direction}`}
          onClick={() => onSelect(e[keyName])}
        >
          {label(e[keyName])}
        </button>
      ))}
    </div>
  )
}

function FactCard({ title, children, empty, tone = 'default' }) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children)
  return (
    <Card title={title} className={`rv-fact-card is-${tone}`}>
      {hasChildren ? children : <p className="rv-muted-block is-ok">{empty}</p>}
    </Card>
  )
}

function riskStatTone(risk) {
  const v = String(risk || '').toLowerCase()
  if (v === 'critical' || v === 'high') return 'warn'
  if (v === 'medium') return 'caution'
  return 'ok'
}

// Top module pairs by number of edges between them (both directions).
function coupledModules(nodes, edges, label, limit) {
  const pairs = new Map()
  edges.forEach((e) => {
    if (e.kind === 'contains') return
    const { source: a, target: b } = e
    if (a === b) return
    const key = a < b ? `${a}|${b}` : `${b}|${a}`
    pairs.set(key, (pairs.get(key) || 0) + 1)
  })
  return [...pairs.entries()]
    .map(([key, count]) => {
      const [a, b] = key.split('|')
      return { a, b, count }
    })
    .sort((x, y) => y.count - x.count || label(y.a).localeCompare(label(x.a)))
    .slice(0, limit)
}

// A representative cycle path (a -> x -> ... -> a) per detected cycle.
function findCycles(nodes, edges) {
  const adj = new Map()
  edges.forEach((e) => {
    if (e.kind === 'contains') return
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source).push(e.target)
  })

  const GRAY = 1,
    BLACK = 2
  const color = new Map()
  const stack = []
  const cycles = []

  function dfs(u) {
    color.set(u, GRAY)
    stack.push(u)
    for (const v of adj.get(u) || []) {
      if (!color.has(v)) {
        if (dfs(v)) return true
      } else if (color.get(v) === GRAY) {
        const idx = stack.indexOf(v)
        cycles.push([...stack.slice(idx), v])
        return true
      }
    }
    stack.pop()
    color.set(u, BLACK)
    return false
  }

  for (const n of nodes) {
    if (!color.has(n.id)) {
      if (dfs(n.id)) break
    }
  }
  return cycles
}

// Highest-risk modules by dependency weight; falls back to low-confidence edges.
function riskyDependencies(nodes, edges, limit) {
  const withRisk = nodes
    .map((n) => ({
      id: n.id,
      risk: n.meta?.risk || 'Low',
      weight: (n.meta?.deps || 0) + (n.meta?.dependents || 0),
    }))
    .filter((n) => n.risk === 'High' || n.risk === 'Critical')
    .sort((a, b) => b.weight - a.weight)

  if (withRisk.length) return withRisk.slice(0, limit)

  return edges
    .filter(
      (e) => e.kind !== 'contains' && (e.relationshipSource !== 'ast' || (e.confidence ?? 1) < 0.8),
    )
    .map((e) => ({ id: e.target, risk: 'Medium' }))
    .slice(0, limit)
}
