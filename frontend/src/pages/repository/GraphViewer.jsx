import { useMemo, useRef, useState, useEffect, useCallback } from 'react';

// Shared interactive SVG node-and-edge graph viewer.
// Responsive: zooms/pans/fits, supports search, hover + selection with
// relationship highlighting, and suppresses unrelated nodes when a node is
// selected. Accepts plain data so it can be wired to real backend analysis.
//
// Props:
//   nodes: [{ id, label, kind?, x, y, meta? }]
//   edges: [{ source, target, kind? }]
//   selected, onSelect
//   dims: { width, height }
//   accentFor(kind): node color hint
//   highlight?: Set<string> | null  — show only these + their connectors

const DEFAULT_DIMS = { width: 1240, height: 860 };
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 2.5;

function kindColor(kind, accentOverride) {
  if (accentOverride) return accentOverride;
  switch (kind) {
    case 'repo': return '#9aa8ff';
    case 'area': return '#7aa2f7';
    case 'directory': return '#67e0c8';
    case 'module': return '#6f9ff2';
    case 'file': return '#8f7bf5';
    case 'func': return '#c9a7ff';
    case 'route': return '#f0b36e';
    case 'input':
    case 'output': return '#67e0c8';
    case 'service': return '#7aa2f7';
    case 'llm': return '#c9a7ff';
    case 'storage': return '#67e0c8';
    case 'transport': return '#f0b36e';
    case 'core': return '#7aa2f7';
    default: return '#8b94a5';
  }
}

export default function GraphViewer({
  nodes,
  edges,
  selected,
  onSelect,
  dims = DEFAULT_DIMS,
  accentFor,
  highlight = null,
  fitKey,
  className = '',
  height = 560,
}) {
  const viewportRef = useRef(null);
  const [view, setView] = useState({ scale: 1, x: 40, y: 40 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef(null);
  const svgRef = useRef(null);

  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const fitScale = useCallback((w, h) => {
    if (!nodes.length) return { scale: 1, x: 40, y: 40 };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach((n) => {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
    });
    const pad = 160;
    const bw = maxX - minX + pad;
    const bh = maxY - minY + pad;
    const scale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, 0.9 * Math.min(w / bw, h / bh)));
    return {
      scale,
      x: (w - (maxX - minX) * scale) / 2 - minX * scale,
      y: (h - (maxY - minY) * scale) / 2 - minY * scale,
    };
  }, [nodes]);

  const autoFit = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const { clientWidth, clientHeight } = el;
    setView(fitScale(clientWidth, clientHeight));
  }, [fitScale]);

  useEffect(() => {
    autoFit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, nodes.length]);

  useEffect(() => {
    if (dims && selected) {
      const n = nodeMap.get(selected);
      if (n) {
        // gently center selected node
        const el = viewportRef.current;
        if (!el) return;
        const { clientWidth, clientHeight } = el;
        setView((v) => ({ ...v, x: clientWidth / 2 - n.x * v.scale, y: clientHeight / 2 - n.y * v.scale + 20 }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, dims]);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    const rect = viewportRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    setView((v) => {
      const next = clampZoom(v.scale * (e.deltaY < 0 ? 1.1 : 0.9));
      const k = next / v.scale;
      return { scale: next, x: px - k * (px - v.x), y: py - k * (py - v.y) };
    });
  }, []);

  const onPointerDown = useCallback((e) => {
    setIsPanning(true);
    panStart.current = { x: e.clientX - view.x, y: e.clientY - view.y };
    viewportRef.current.setPointerCapture(e.pointerId);
  }, [view]);

  const onPointerMove = useCallback((e) => {
    if (!isPanning) return;
    setView((v) => ({
      ...v,
      x: e.clientX - panStart.current.x,
      y: e.clientY - panStart.current.y,
    }));
  }, [isPanning]);

  const onPointerUp = useCallback((e) => {
    setIsPanning(false);
    if (viewportRef.current?.hasPointerCapture(e.pointerId)) {
      viewportRef.current.releasePointerCapture(e.pointerId);
    }
  }, []);

  // Adjacency sets used to dim unrelated nodes when a node is selected.
  const adjacency = useMemo(() => {
    const adj = new Map();
    nodes.forEach((n) => adj.set(n.id, new Set()));
    edges.forEach((e) => {
      adj.get(e.source)?.add(e.target);
      adj.get(e.target)?.add(e.source);
    });
    return adj;
  }, [nodes, edges]);

  const isDimmed = useCallback((id) => {
    if (highlight) return !highlight.has(id);
    if (selected === id) return false;
    if (selected && adjacency.get(selected)?.has(id)) return false;
    return Boolean(selected);
  }, [highlight, selected, adjacency]);

  const isEdgeActive = useCallback((e) => {
    if (highlight) return highlight.has(e.source) && highlight.has(e.target);
    if (!selected) return true;
    return e.source === selected || e.target === selected;
  }, [highlight, selected]);

  const handleNodeClick = (e, id) => {
    e.stopPropagation();
    onSelect?.(id);
  };

  return (
    <div className={`graph-viewer ${className}`} style={{ height }}>
      <div
        ref={viewportRef}
        className="graph-viewport"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={() => onSelect?.(null)}
      >
        <svg ref={svgRef} width="100%" height="100%" className="graph-svg">
          <g transform={`translate(${view.x},${view.y}) scale(${view.scale})`}>
            {edges.map((edge, i) => {
              const s = nodeMap.get(edge.source);
              const t = nodeMap.get(edge.target);
              if (!s || !t) return null;
              const active = isEdgeActive(edge);
              const color = kindColor(edge.kind === 'direct' ? 'route' : edge.kind === 'indirect' ? 'func' : 'module');
              const dx = t.x - s.x;
              const dy = t.y - s.y;
              const cx = s.x + dx * 0.5;
              const cy = s.y + dy * 0.5 - 14;
              return (
                <g key={`e${i}`} opacity={active ? 1 : 0.12}>
                  <path
                    d={`M ${s.x} ${s.y} C ${cx} ${s.y} ${cx} ${t.y} ${t.x} ${t.y}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={active ? 1.4 : 1}
                    strokeDasharray={edge.kind === 'imports' || edge.kind === 'indirect' ? '4 4' : edge.kind === 'writes' || edge.kind === 'reads' ? '2 4' : undefined}
                    strokeOpacity={active ? 0.5 : 0.3}
                    markerEnd={active ? 'url(#graphArrow)' : undefined}
                  />
                </g>
              );
            })}
            {nodes.map((node) => {
              const dimmed = isDimmed(node.id);
              const isSel = selected === node.id;
              const color = kindColor(node.kind, accentFor?.(node));
              return (
                <g
                  key={node.id}
                  className="graph-node"
                  data-id={node.id}
                  transform={`translate(${node.x},${node.y})`}
                  onClick={(e) => handleNodeClick(e, node.id)}
                  opacity={dimmed ? 0.18 : 1}
                  style={{ cursor: 'pointer' }}
                >
                  {isSel ? (
                    <circle r={34} fill={color} fillOpacity={0.14} stroke={color} strokeWidth={1.5} className="graph-node-halo" />
                  ) : null}
                  <circle
                    r={node.kind === 'repo' ? 22 : node.kind === 'area' ? 18 : 14}
                    fill={isSel ? color : 'rgba(34,38,43,0.95)'}
                    stroke={isSel ? color : color}
                    strokeWidth={isSel ? 2 : 1.2}
                    className="graph-node-circle"
                  />
                  <text
                    x={0}
                    y={node.kind === 'repo' ? -34 : -30}
                    textAnchor="middle"
                    className="graph-node-label"
                    style={{ fill: isSel ? '#eaf1ff' : '#b9c0cc' }}
                  >
                    {node.label}
                  </text>
                  <title>{node.path || node.label}</title>
                </g>
              );
            })}
          </g>
          <defs>
            <marker id="graphArrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L8,3 z" fill="rgba(122,162,247,0.7)" />
            </marker>
          </defs>
        </svg>
        <div className="graph-view-footer">{nodes.length} nodes · {edges.length} connections</div>
      </div>

      <div className="graph-controls">
        <button title="Zoom out" onClick={() => setView((v) => ({ ...v, scale: clampZoom(v.scale * 0.85) }))}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M5 12h14" /></svg>
        </button>
        <button title="Zoom in" onClick={() => setView((v) => ({ ...v, scale: clampZoom(v.scale * 1.15) }))}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
        </button>
        <button title="Fit to screen" onClick={autoFit}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9V5a2 2 0 0 1 2-2h4M15 3h4a2 2 0 0 1 2 2v4M21 15v4a2 2 0 0 1-2 2h-4M9 21H5a2 2 0 0 1-2-2v-4" /></svg>
        </button>
      </div>
    </div>
  );
}

function clampZoom(z) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}
