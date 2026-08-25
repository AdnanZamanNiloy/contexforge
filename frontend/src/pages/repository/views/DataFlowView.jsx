import { useEffect, useMemo, useState } from 'react';
import GraphViewer from '../GraphViewer';
import { repositoryDataFlow } from '../../../services/api';

// Detected execution flow kinds -> label + node colour. Purely data-driven.
const KIND_META = {
  route: { label: 'API / route', color: '#f0b36e' },
  input: { label: 'Entry point', color: '#67e0c8' },
  output: { label: 'Output', color: '#67e0c8' },
  service: { label: 'Service', color: '#7aa2f7' },
  storage: { label: 'Storage / data', color: '#67e0c8' },
  external: { label: 'External API', color: '#f0b36e' },
  llm: { label: 'LLM / model', color: '#c9a7ff' },
  core: { label: 'Core pipeline', color: '#7aa2f7' },
  transport: { label: 'Transport', color: '#f0b36e' },
  module: { label: 'Module', color: '#6f9ff2' },
  file: { label: 'File', color: '#8f7bf5' },
  func: { label: 'Function', color: '#c9a7ff' },
};

const GRAPH_DIMS = { width: 1240, height: 860 };

function accentFor(node) {
  return KIND_META[node.kind]?.color || '#8b94a5';
}

// Layered left-to-right layout: depth (from entry) -> x, sibling index -> y.
function layoutFlow(nodes, edges) {
  if (!nodes.length) return nodes;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map(nodes.map((n) => [n.id, []]));
  const hasParent = new Set();
  edges.forEach((e) => {
    if (byId.has(e.source) && byId.has(e.target)) {
      children.get(e.source)?.push(e.target);
      hasParent.add(e.target);
    }
  });

  const entryId =
    nodes.find((n) => n.entry)?.id ||
    nodes.find((n) => !hasParent.has(n.id))?.id ||
    nodes[0].id;

  const depth = new Map([[entryId, 0]]);
  const levels = new Map([[0, [entryId]]]);
  const queue = [[entryId, 0]];
  while (queue.length) {
    const [cur, d] = queue.shift();
    for (const child of children.get(cur) || []) {
      if (!depth.has(child)) {
        depth.set(child, d + 1);
        if (!levels.has(d + 1)) levels.set(d + 1, []);
        levels.get(d + 1).push(child);
        queue.push([child, d + 1]);
      }
    }
  }

  const DX = 250;
  const ROW_H = 88;
  const positions = {};
  levels.forEach((ids, d) => {
    ids.forEach((id, i) => {
      positions[id] = { x: d * DX + 40, y: i * ROW_H + 60 };
    });
  });
  nodes.filter((n) => !positions[n.id]).forEach((n, i) => {
    positions[n.id] = { x: (levels.size + 1) * DX + 40, y: (i % 12) * ROW_H + 60 };
  });

  return nodes.map((n) => ({ ...n, x: positions[n.id].x, y: positions[n.id].y }));
}

function NodeDetails({ node }) {
  if (!node) return null;
  const kind = KIND_META[node.kind];
  const list = (items) =>
    items && items.length ? items.join(', ') : '—';
  return (
    <div className="flow-detail-card">
      <div className="flow-detail-head">
        <span className="flow-kind-dot" style={{ background: kind?.color }} />
        <b>{node.label}</b>
        <span className="flow-detail-kind">{kind?.label || node.kind}</span>
      </div>
      {node.entry ? <div className="flow-detail-badge">Entry point</div> : null}
      <div className="flow-detail-row"><span>Path</span><code>{node.path || '—'}</code></div>
      <div className="flow-detail-row"><span>Functions</span><code>{list(node.functions)}</code></div>
      <div className="flow-detail-row"><span>Callers</span><code>{list(node.callers)}</code></div>
      <div className="flow-detail-row"><span>Callees</span><code>{list(node.callees)}</code></div>
      <div className="flow-detail-row"><span>Dependencies</span><code>{list(node.dependencies)}</code></div>
      <div className="flow-detail-row"><span>Caller count</span><b>{node.dependents || 0}</b></div>
      <div className="flow-detail-row"><span>Depends on</span><b>{node.deps || 0}</b></div>
      {node.latencyMs != null ? (
        <div className="flow-detail-row"><span>Measured latency</span><b>{node.latencyMs.toFixed(1)} ms</b></div>
      ) : null}
    </div>
  );
}

function FlowGraph({ flow }) {
  const [selected, setSelected] = useState(null);
  const nodes = useMemo(() => layoutFlow(flow.nodes, flow.edges), [flow]);
  const selectedNode = useMemo(
    () => flow.nodes.find((n) => n.id === selected) || null,
    [selected, flow],
  );

  const legend = useMemo(() => {
    const kinds = [...new Set(flow.nodes.map((n) => n.kind))];
    return kinds.filter((k) => KIND_META[k]).map((k) => (
      <span key={k}>
        <i className="legend-dot" style={{ background: KIND_META[k].color }} />
        {KIND_META[k].label}
      </span>
    ));
  }, [flow]);

  return (
    <div className="flow-graph-wrap">
      <div className="arch-legend flow-legend">{legend}</div>
      <GraphViewer
        nodes={nodes}
        edges={flow.edges}
        dims={GRAPH_DIMS}
        selected={selected}
        onSelect={setSelected}
        accentFor={accentFor}
        className="flow-graph"
        height={520}
      />
      <div className="flow-bottlenecks">
        {flow.bottlenecks && flow.bottlenecks.length > 0 ? (
          <>
            <div className="fact-title">Coupling hotspots (from code analysis)</div>
            {flow.bottlenecks.map((b) => (
              <div className="fact-row" key={b.id}>
                <span>{b.path || b.label}</span>
                <b>{b.dependents} caller{b.dependents === 1 ? '' : 's'}</b>
              </div>
            ))}
          </>
        ) : null}
      </div>
      <NodeDetails node={selectedNode} />
    </div>
  );
}

export default function DataFlowView({ analysisId }) {
  const [flows, setFlows] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ok | empty | error
  const [error, setError] = useState('');
  const [activeId, setActiveId] = useState(null);

  useEffect(() => {
    if (!analysisId) {
      setFlows({});
      setStatus('empty');
      return;
    }
    let cancelled = false;
    setStatus('loading');
    setError('');
    repositoryDataFlow(analysisId)
      .then((data) => {
        if (cancelled) return;
        const flowList = data && typeof data === 'object' ? Object.values(data) : [];
        setFlows(flowList);
        setStatus(flowList.length ? 'ok' : 'empty');
        setActiveId((prev) => (flowList.some((f) => f.id === prev) ? prev : flowList[0]?.id || null));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load data flow.');
        setFlows({});
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  const active = useMemo(
    () => (flows || []).find((f) => f.id === activeId) || (flows || [])[0],
    [flows, activeId],
  );

  if (status === 'loading') {
    return (
      <div className="intel-view">
        <div className="intel-view-header">
          <div><h3>Data Flow</h3><p className="intel-subtext">Directional execution flow from repository analysis</p></div>
        </div>
        <div className="intel-state">
          <div className="intel-spinner" />
          <p>Analyzing data flow…</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="intel-view">
        <div className="intel-view-header">
          <div><h3>Data Flow</h3><p className="intel-subtext">Directional execution flow from repository analysis</p></div>
        </div>
        <div className="intel-state">
          <p className="intel-error">Data flow analysis failed</p>
          <p className="intel-subtext">{error}</p>
        </div>
      </div>
    );
  }

  if (status === 'empty' || !active) {
    return (
      <div className="intel-view">
        <div className="intel-view-header">
          <div><h3>Data Flow</h3><p className="intel-subtext">Directional execution flow from repository analysis</p></div>
        </div>
        <div className="intel-state">
          <p className="intel-subtext">No executable flow detected</p>
          <span className="intel-empty-hint">No runnable entry points (routes, CLIs, mains) with a call chain were found in this repository.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Data Flow</h3>
          <p className="intel-subtext">Directional execution flow detected from repository analysis</p>
        </div>
      </div>

      <div className="flow-tabs">
        {(flows || []).map((f) => (
          <button
            key={f.id}
            className={f.id === active?.id ? 'active' : ''}
            onClick={() => setActiveId(f.id)}
            title={f.entry}
          >
            {f.title || f.id}
          </button>
        ))}
      </div>

      <FlowGraph key={active?.id} flow={active} />
    </div>
  );
}
