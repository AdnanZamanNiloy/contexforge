import { useMemo, useState } from 'react';
import GraphViewer from '../GraphViewer';
import InfoPanel from '../components/InfoPanel';
import { architecture, graphDimensions } from '../../../data/repoIntelligence';

const LAYOUTS = ['Hierarchical', 'Cluster', 'Radial'];

export default function ArchitectureView({ onSelectChange }) {
  const [selected, setSelected] = useState(null);
  const [layout, setLayout] = useState('Hierarchical');
  const [query, setQuery] = useState('');
  const [fitKey, setFitKey] = useState(0);

  const selectedNode = useMemo(
    () => architecture.nodes.find((n) => n.id === selected) || null,
    [selected],
  );

  const highlighted = useMemo(() => {
    if (!query.trim() || query.length < 2) return null;
    const q = query.toLowerCase();
    const ids = new Set(
      architecture.nodes.filter((n) => n.label.toLowerCase().includes(q) || (n.path || '').toLowerCase().includes(q)).map((n) => n.id),
    );
    return ids.size ? ids : null;
  }, [query]);

  const handleSelect = (id) => {
    setSelected(id);
    onSelectChange?.(id ? architecture.nodes.find((n) => n.id === id) : null);
  };

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>System Architecture</h3>
          <p className="intel-subtext">High-level structure of the repository</p>
        </div>
        <div className="arch-toolbar">
          <div className="graph-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search nodes..."
              spellCheck={false}
            />
            {query ? <button className="search-clear" onClick={() => setQuery('')}>×</button> : null}
          </div>
          <div className="layout-select">
            <span>Layout</span>
            <select value={layout} onChange={(e) => setLayout(e.target.value)}>
              {LAYOUTS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <button className="tool-btn" onClick={() => setFitKey((k) => k + 1)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9V5a2 2 0 0 1 2-2h4M15 3h4a2 2 0 0 1 2 2v4M21 15v4a2 2 0 0 1-2 2h-4M9 21H5a2 2 0 0 1-2-2v-4" /></svg>
            Fit
          </button>
        </div>
      </div>

      <div className="arch-legend">
        <span><i className="legend-dot" style={{ background: '#9aa8ff' }} /> Repository</span>
        <span><i className="legend-dot" style={{ background: '#7aa2f7' }} /> Area</span>
        <span><i className="legend-dot" style={{ background: '#67e0c8' }} /> Directory</span>
        <span><i className="legend-dot" style={{ background: '#6f9ff2' }} /> Module</span>
        <span><i className="legend-dot" style={{ background: '#8f7bf5' }} /> File</span>
      </div>

      <GraphViewer
        nodes={layout === 'Radial' ? radialSpread(architecture.nodes) : architecture.nodes}
        edges={architecture.edges}
        dims={graphDimensions}
        selected={selected}
        onSelect={handleSelect}
        highlight={highlighted}
        fitKey={fitKey}
        className="arch-graph"
        height={560}
      />

      <InfoPanel node={selectedNode} />
    </div>
  );
}

// Very light "radial" remapping so the layout control visibly changes the graph
// without a graph-layout dependency. Real backend data would supply positions.
function radialSpread(nodes) {
  const root = nodes.find((n) => n.kind === 'repo');
  if (!root) return nodes;
  const cx = 620;
  const cy = 430;
  const others = nodes.filter((n) => n.id !== root.id);
  const spread = others.map((n, i) => {
    const radius = 260 + (i % 3) * 40;
    const angle = (i / Math.max(1, others.length - 1)) * Math.PI * 2 - Math.PI / 2;
    return { ...n, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  });
  return [{ ...root, x: cx, y: cy }, ...spread];
}
