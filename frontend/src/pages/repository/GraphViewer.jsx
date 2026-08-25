import { useMemo, useRef, useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

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
const MIN_ZOOM = 0.05;
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
  fullscreen: fullscreenProp,
  onToggleFullscreen,
  toolbar,
}) {
  const viewportRef = useRef(null);
  const [view, setView] = useState({ scale: 1, x: 40, y: 40 });
  const [isPanning, setIsPanning] = useState(false);
  const [fullscreen, setFullscreen] = useState(!!fullscreenProp);
  const [viewAnim, setViewAnim] = useState(false);
  const viewTimer = useRef(null);
  const panStart = useRef(null);
  const svgRef = useRef(null);

  // Controlled mode: parent drives fullscreen via props.
  const isControlled = typeof onToggleFullscreen === 'function';
  const isFullscreen = isControlled ? !!fullscreenProp : fullscreen;
  const setFull = isControlled ? onToggleFullscreen : setFullscreen;

  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  // Unique node colors drive per-color radial gradient defs.
  const nodeColors = useMemo(() => {
    const set = new Set();
    nodes.forEach((n) => set.add(kindColor(n.kind, accentFor?.(n))));
    return [...set];
  }, [nodes, accentFor]);

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
    applyView(fitScale(clientWidth, clientHeight), true);
  }, [fitScale]);

  const applyView = useCallback((next, animate = false) => {
    setView(next);
    setViewAnim(animate);
    if (viewTimer.current) clearTimeout(viewTimer.current);
    if (animate) {
      viewTimer.current = setTimeout(() => setViewAnim(false), 500);
    }
  }, []);

  useEffect(() => {
    // Re-fit whenever the graph changes or enters/exits fullscreen.
    // Wait a frame so the portal/viewport has laid out before measuring.
    const raf = requestAnimationFrame(() => autoFit());
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, nodes.length, isFullscreen]);

  // Escape closes the fullscreen overlay.
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e) => {
      if (e.key === 'Escape') setFull(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen, isControlled, fullscreenProp, setFull]);

  useEffect(() => {
    if (dims && selected) {
      const n = nodeMap.get(selected);
      if (n) {
        // gently center selected node
        const el = viewportRef.current;
        if (!el) return;
        const { clientWidth, clientHeight } = el;
        applyView({ ...view, x: clientWidth / 2 - n.x * view.scale, y: clientHeight / 2 - n.y * view.scale + 20 }, true);
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

  const graphBody = (
    <div className="graph-frame">
      {toolbar ? <div className="graph-toolbar">{toolbar}</div> : null}
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
          <rect width="100%" height="100%" fill="url(#dotGrid)" />
          <g
            style={{
              transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
              transition: viewAnim ? 'transform 0.5s cubic-bezier(0.22, 1, 0.36, 1)' : 'none',
            }}
          >
            {edges.map((edge, i) => {
              const s = nodeMap.get(edge.source);
              const t = nodeMap.get(edge.target);
              if (!s || !t) return null;
              const active = isEdgeActive(edge);
              const color = kindColor(edge.kind === 'direct' ? 'route' : edge.kind === 'indirect' ? 'func' : 'module');
              const dx = t.x - s.x;
              const dy = t.y - s.y;
              const bend = 14 + Math.min(28, Math.abs(dx) * 0.18);
              const cx = s.x + dx * 0.5;
              const cy = s.y + dy * 0.5 - bend;
              return (
                <g key={`e${i}`} opacity={active ? 1 : 0.1}>
                  <path
                    d={`M ${s.x} ${s.y} C ${cx} ${s.y} ${cx} ${t.y} ${t.x} ${t.y}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={active ? 1.6 : 1}
                    strokeLinecap="round"
                    strokeDasharray={edge.kind === 'imports' || edge.kind === 'indirect' ? '5 5' : edge.kind === 'writes' || edge.kind === 'reads' ? '2 5' : undefined}
                    strokeOpacity={active ? 0.7 : 0.35}
                    markerEnd={active ? 'url(#graphArrow)' : undefined}
                    filter={active ? 'url(#edgeGlow)' : undefined}
                    className={active ? 'graph-edge-active' : undefined}
                  />
                </g>
              );
            })}
            {nodes.map((node) => {
              const dimmed = isDimmed(node.id);
              const isSel = selected === node.id;
              const color = kindColor(node.kind, accentFor?.(node));
              const grad = `url(#grad-${color.replace('#', '')})`;
              const r = node.kind === 'repo' ? 22 : node.kind === 'area' ? 18 : 14;
              return (
                <g
                  key={node.id}
                  className="graph-node"
                  data-id={node.id}
                  transform={`translate(${node.x},${node.y})`}
                  onClick={(e) => handleNodeClick(e, node.id)}
                  opacity={dimmed ? 0.15 : 1}
                  style={{ cursor: 'pointer' }}
                >
                  {isSel ? (
                    <circle r={r + 6} className="graph-node-pulse" fill="none" stroke={color} strokeWidth={1.6} />
                  ) : null}
                  <circle
                    r={r}
                    fill={grad}
                    stroke={color}
                    strokeWidth={isSel ? 2.4 : 1.4}
                    className={isSel ? 'graph-node-circle graph-node-circle-selected' : 'graph-node-bubble'}
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
          <rect width="100%" height="100%" fill="url(#vignette)" pointerEvents="none" />
          <defs>
            <pattern id="dotGrid" width="26" height="26" patternUnits="userSpaceOnUse">
              <circle cx="1.5" cy="1.5" r="1.5" fill="rgba(255,255,255,0.05)" />
            </pattern>
            <radialGradient id="vignette" cx="50%" cy="50%" r="78%">
              <stop offset="68%" stopColor="rgba(0,0,0,0)" />
              <stop offset="100%" stopColor="rgba(0,0,0,0.45)" />
            </radialGradient>
            {nodeColors.map((c) => {
              const gid = `grad-${c.replace('#', '')}`;
              return (
                <radialGradient key={gid} id={gid} cx="32%" cy="30%" r="80%">
                  <stop offset="0%" stopColor={shade(c, 0.55)} />
                  <stop offset="46%" stopColor={c} />
                  <stop offset="100%" stopColor={shade(c, -0.5)} />
                </radialGradient>
              );
            })}
            <filter id="edgeGlow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="2.6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker id="graphArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(170,198,255,0.95)" />
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
        {!isControlled ? (
          <button title="Full screen" onClick={() => setFull(!isFullscreen)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" /></svg>
          </button>
        ) : null}
      </div>
    </div>
  );

  if (isFullscreen) {
    return createPortal(
      <div className="graph-fullscreen">
        <button className="graph-fullscreen-close" title="Exit full screen (Esc)" onClick={() => setFull(false)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
        <div className="graph-viewer graph-fullscreen-body">
          {graphBody}
        </div>
      </div>,
      document.body,
    );
  }

  return (
    <div className={`graph-viewer ${className}`} style={{ height }}>
      {graphBody}
    </div>
  );
}

function clampZoom(z) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

// Lighten (amt > 0) or darken (amt < 0) a hex color, amt in [-1, 1].
function shade(hex, amt) {
  const c = hex.replace('#', '');
  const num = parseInt(c, 16);
  let r = (num >> 16) & 255, g = (num >> 8) & 255, b = num & 255;
  const t = amt < 0 ? 0 : 255;
  const a = Math.abs(amt);
  r = Math.round((t - r) * a + r);
  g = Math.round((t - g) * a + g);
  b = Math.round((t - b) * a + b);
  return `rgb(${r},${g},${b})`;
}
