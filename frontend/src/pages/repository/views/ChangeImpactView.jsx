import { useMemo, useState } from 'react'

import GraphViewer from '../GraphViewer'
import { ViewShell, Card, StatTile, Badge, Legend, EmptyState } from '../ui/primitives'

const RISK_TONE = { LOW: 'ok', MEDIUM: 'caution', HIGH: 'warn', CRITICAL: 'critical' }

const IMPACT_LEGEND = [
  { label: 'Direct impact', color: '#4377FD' },
  { label: 'Indirect impact', color: '#8b949e' },
]

export default function ChangeImpactView({
  changeImpact = { nodes: [], blastRadius: { nodes: [], edges: [] }, estimated: {} },
}) {
  const [selected, setSelected] = useState(null)

  const nodes = changeImpact.nodes || []
  const blast = changeImpact.blastRadius || { nodes: [], edges: [] }

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selected) || null, [nodes])
  const estimate = selectedNode || nodes[0]
  const risk = String(estimate?.risk || changeImpact.risk || 'MEDIUM').toUpperCase()
  const estimated = changeImpact.estimated || {}

  const estimates = [
    { label: 'Affected files', value: estimated.affectedFiles },
    { label: 'Affected modules', value: estimated.affectedModules },
    { label: 'Affected APIs', value: estimated.affectedApis },
    { label: 'Affected tests', value: estimated.affectedTests },
    { label: 'Affected dependencies', value: estimated.affectedDependencies },
  ]

  const hasBlast = blast.nodes.length > 0

  return (
    <ViewShell>
      <div className="rv-grid rv-grid-5">
        {estimates.map((e) => (
          <StatTile key={e.label} label={e.label} value={e.value ?? '—'} />
        ))}
      </div>

      {hasBlast ? (
        <>
          <div className="rv-toolbar">
            <div className="rv-toolbar-left">
              <Legend items={IMPACT_LEGEND} />
            </div>
            <div className="rv-toolbar-right">
              <span className={`rv-risk-pill is-${RISK_TONE[risk] || 'caution'}`}>
                <span className="rv-risk-dot" />
                Risk: {risk}
              </span>
            </div>
          </div>
          <GraphViewer
            nodes={blast.nodes}
            edges={blast.edges}
            selected={selected}
            onSelect={setSelected}
            accentFor={(n) => (n.direct ? '#4377FD' : '#8b949e')}
            className="rv-graph rv-graph-impact"
            height={440}
          />
        </>
      ) : (
        <EmptyState
          title="No blast radius available"
          hint="A change-impact graph has not been generated for this repository yet."
        />
      )}

      {nodes.length ? (
        <Card title="Impact by node" padded={false}>
          <div className="rv-table">
            <div className="rv-table-head">
              <span>Node</span>
              <span>Files</span>
              <span>Modules</span>
              <span>APIs</span>
              <span>Tests</span>
              <span>Risk</span>
            </div>
            {nodes.map((n) => (
              <button
                type="button"
                className={`rv-table-row ${selected === n.id ? 'is-active' : ''}`}
                key={n.id}
                onClick={() => setSelected(n.id)}
              >
                <span className="rv-table-node">{n.label}</span>
                <span>{n.files}</span>
                <span>{n.modules}</span>
                <span>{n.apis}</span>
                <span>{n.tests}</span>
                <span>
                  <Badge tone={RISK_TONE[String(n.risk || 'LOW').toUpperCase()] || 'neutral'}>
                    {n.risk}
                  </Badge>
                </span>
              </button>
            ))}
          </div>
        </Card>
      ) : null}
    </ViewShell>
  )
}
