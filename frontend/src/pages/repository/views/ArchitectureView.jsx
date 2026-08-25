import { useMemo, useState } from 'react';
import GraphViewer from '../GraphViewer';
import InfoPanel from '../components/InfoPanel';

const LAYOUTS = ['Hierarchical', 'Tree', 'Radial'];

export default function ArchitectureView({ architecture = { nodes: [], edges: [] }, graphDimensions = { width: 1240, height: 860 } }) {
  const [selected, setSelected] = useState(null);
  const [layout, setLayout] = useState('Hierarchical');
  const [query, setQuery] = useState('');
  const [fullscreen, setFullscreen] = useState(false);

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
  };

  const graphNodes = useMemo(() => {
    if (layout === 'Radial') return radialSpread(architecture.nodes);
    if (layout === 'Tree') return treeLayout(architecture.nodes, architecture.edges);
    return architecture.nodes;
  }, [layout, architecture]);

  const graphToolbar = (
    <>
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
    </>
  );

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>System Architecture</h3>
          <p className="intel-subtext">High-level structure of the repository</p>
        </div>
        <div className="arch-toolbar">
          <button className="tool-btn" title="Toggle full screen" onClick={() => setFullscreen((f) => !f)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" /></svg>
            Full screen
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
        nodes={graphNodes}
        edges={architecture.edges}
        dims={graphDimensions}
        selected={selected}
        onSelect={handleSelect}
        highlight={highlighted}
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen((f) => !f)}
        toolbar={graphToolbar}
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

// Tidy rooted tree from the "contains" hierarchy (repo -> area -> dir ->
// module -> file). Depth grows left-to-right; siblings stack vertically.
function treeLayout(nodes, edges) {
  if (!nodes.length) return nodes;
  const label = (id) => nodes.find((n) => n.id === id)?.label || id;

  const children = new Map(nodes.map((n) => [n.id, []]));
  const hasParent = new Set();
  edges.forEach((e) => {
    if (e.kind !== 'contains') return;
    if (children.has(e.source)) {
      children.get(e.source).push(e.target);
      hasParent.add(e.target);
    }
  });
  children.forEach((arr) => arr.sort((a, b) => label(a).localeCompare(label(b))));

  const rootId =
    nodes.find((n) => n.kind === 'repo')?.id ||
    nodes.find((n) => !hasParent.has(n.id))?.id;
  if (!rootId) return nodes;

  const DX = 240;
  const DY = 62;
  const pos = new Map();
  let leaf = 0;

  const walk = (id, depth) => {
    const kids = children.get(id) || [];
    if (!kids.length) {
      pos.set(id, { x: depth * DX, y: leaf * DY });
      leaf += 1;
      return;
    }
    kids.forEach((k) => walk(k, depth + 1));
    const avgY = kids.reduce((s, k) => s + pos.get(k).y, 0) / kids.length;
    pos.set(id, { x: depth * DX, y: avgY });
  };
  walk(rootId, 0);

  const maxDepth = Math.max(0, ...nodes.filter((n) => pos.has(n.id)).map((n) => Math.round(pos.get(n.id).x / DX)));
  nodes.filter((n) => !pos.has(n.id)).forEach((n, i) => {
    const col = Math.floor(i / 10);
    pos.set(n.id, { x: (maxDepth + 1) * DX + col * 220, y: (i % 10) * DY });
  });

  return nodes.map((n) => {
    const p = pos.get(n.id);
    return { ...n, x: p.x, y: p.y };
  });
}
