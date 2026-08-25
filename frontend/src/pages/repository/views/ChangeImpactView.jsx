import { useMemo, useState } from 'react';
import GraphViewer from '../GraphViewer';

const RISK_TONE = {
  LOW: 'is-low',
  MEDIUM: 'is-medium',
  HIGH: 'is-high',
  CRITICAL: 'is-critical',
};

export default function ChangeImpactView({ changeImpact = { nodes: [], blastRadius: { nodes: [], edges: [] }, estimated: {} } }) {
  const [selected, setSelected] = useState(null);

  const selectedNode = useMemo(
    () => changeImpact.nodes.find((n) => n.id === selected) || null,
    [selected],
  );

  const estimate = selectedNode || changeImpact.nodes[0];
  const risk = String(estimate?.risk || changeImpact.risk || 'MEDIUM').toUpperCase();

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Change Impact</h3>
          <p className="intel-subtext">Blast radius for <code className="inline-code">{changeImpact.selection}</code></p>
        </div>
        <div className={`impact-risk ${RISK_TONE[risk] || 'is-medium'}`}>
          <span className="impact-risk-dot" />
          <span>Risk: {risk}</span>
        </div>
      </div>

      <div className="impact-estimates">
        <div className="estimate">
          <span className="estimate-value">{changeImpact.estimated.affectedFiles}</span>
          <span className="estimate-label">Affected Files</span>
        </div>
        <div className="estimate">
          <span className="estimate-value">{changeImpact.estimated.affectedModules}</span>
          <span className="estimate-label">Affected Modules</span>
        </div>
        <div className="estimate">
          <span className="estimate-value">{changeImpact.estimated.affectedApis}</span>
          <span className="estimate-label">Affected APIs</span>
        </div>
        <div className="estimate">
          <span className="estimate-value">{changeImpact.estimated.affectedTests}</span>
          <span className="estimate-label">Affected Tests</span>
        </div>
        <div className="estimate">
          <span className="estimate-value">{changeImpact.estimated.affectedDependencies}</span>
          <span className="estimate-label">Affected Dependencies</span>
        </div>
      </div>

      <div className="impact-meta">
        <span className="impact-legend-item"><i className="legend-dot" style={{ background: '#f0b36e' }} /> Direct impact</span>
        <span className="impact-legend-item"><i className="legend-dot" style={{ background: '#8b94a5' }} /> Indirect impact</span>
      </div>

      <GraphViewer
        nodes={changeImpact.blastRadius.nodes}
        edges={changeImpact.blastRadius.edges}
        selected={selected}
        onSelect={setSelected}
        accentFor={(n) => (n.direct ? '#f0b36e' : '#8b94a5')}
        className="blast-graph"
        height={440}
      />

      <div className="impact-table">
        <div className="impact-table-head">
          <span>Node</span><span>Files</span><span>Modules</span><span>APIs</span><span>Tests</span><span>Risk</span>
        </div>
        {changeImpact.nodes.map((n) => (
          <button className={`impact-table-row ${selected === n.id ? 'active' : ''}`} key={n.id} onClick={() => setSelected(n.id)}>
            <span className="impact-node-label">{n.label}</span>
            <span>{n.files}</span><span>{n.modules}</span><span>{n.apis}</span><span>{n.tests}</span>
            <span><span className={`risk-badge is-${(n.risk || 'Low').toLowerCase()}`}>{n.risk}</span></span>
          </button>
        ))}
      </div>
    </div>
  );
}
