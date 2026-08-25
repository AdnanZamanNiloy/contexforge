import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import GraphViewer from '../GraphViewer';
import { getRepositoryDependencies } from '../../../services/api';

const COUPLE_LIMIT = 3;
const RISK_LIMIT = 3;
const DEPTH = 3;

export default function DependencyView({ analysisId, dependencyGraph = { nodes: [], edges: [] } }) {
  const [selected, setSelected] = useState(null);
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const lastAnalysisId = useRef(null);

  // Reset the selection whenever a new analysis is loaded so we never point at
  // a node that does not exist in the fresh graph.
  useEffect(() => {
    if (lastAnalysisId.current && lastAnalysisId.current !== analysisId) {
      setSelected(null);
    }
    lastAnalysisId.current = analysisId;
  }, [analysisId]);

  // Fetch the dependency subgraph from the backend for the current selection.
  useEffect(() => {
    if (!analysisId) {
      setGraph(dependencyGraph || { nodes: [], edges: [] });
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const data = await getRepositoryDependencies(analysisId, { selected, depth: DEPTH });
        if (!cancelled) setGraph(data || { nodes: [], edges: [] });
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load dependencies.');
          setGraph(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [analysisId, selected, dependencyGraph]);

  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const label = useCallback((id) => (nodeById.get(id)?.label || nodeById.get(id)?.meta?.path || id), [nodeById]);

  const selectedMeta = useMemo(() => {
    const n = nodeById.get(selected);
    return {
      deps: n?.meta?.deps ?? 0,
      dependents: n?.meta?.dependents ?? 0,
    };
  }, [selected, nodeById]);

  const summary = useMemo(() => {
    const linkEdges = edges.filter((e) => e.kind !== 'contains');
    const outgoing = linkEdges.filter((e) => e.source === selected);
    const incoming = linkEdges.filter((e) => e.target === selected);
    return { outgoing, incoming };
  }, [selected, edges]);

  const facts = useMemo(() => ({
    coupled: coupledModules(nodes, edges, label, COUPLE_LIMIT),
    cycles: findCycles(nodes, edges),
    risky: riskyDependencies(nodes, edges, RISK_LIMIT),
  }), [nodes, edges, label]);

  const empty = !loading && !error && nodes.length === 0;

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Dependencies</h3>
          <p className="intel-subtext">Incoming, outgoing and coupling between modules</p>
        </div>
        <div className="dep-breakdown">
          {selected ? (
            <>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#7aa2f7' }} /> Fan-in <b>{selectedMeta.dependents}</b></span>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#67e0c8' }} /> Fan-out <b>{selectedMeta.deps}</b></span>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#8f7bf5' }} /> Incoming <b>{summary.incoming.length}</b></span>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#f0b36e' }} /> Outgoing <b>{summary.outgoing.length}</b></span>
            </>
          ) : (
            <>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#7aa2f7' }} /> Source files <b>{nodes.length}</b></span>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#67e0c8' }} /> Edges <b>{edges.length}</b></span>
              <span className="dep-chip"><i className="legend-dot" style={{ background: '#f0b36e' }} /> Cycles <b>{facts.cycles.length}</b></span>
            </>
          )}
        </div>
      </div>

      {loading ? (
        <div className="dep-state"><div className="intel-spinner" /><p>Building dependency graph…</p></div>
      ) : error ? (
        <div className="dep-state is-error"><p>{error}</p></div>
      ) : empty ? (
        <div className="dep-state"><p>No source dependencies could be extracted from this repository.</p></div>
      ) : (
        <GraphViewer
          nodes={nodes}
          edges={edges}
          selected={selected}
          onSelect={setSelected}
          className="dep-graph"
          height={460}
        />
      )}

      <div className="dep-panel-strip">
        <div className="dep-left">
          <div className="dep-block-title">Incoming dependencies</div>
          {summary.incoming.length ? (
            <div className="dep-tag-list">
              {summary.incoming.map((e) => (
                <button key={`in-${e.source}-${e.kind}`} className="dep-tag is-in" onClick={() => setSelected(e.source)}>
                  {label(e.source)}
                </button>
              ))}
            </div>
          ) : (
            <div className="dep-empty">{selected ? 'No incoming deps' : 'Select a node'}</div>
          )}
        </div>
        <div className="dep-right">
          <div className="dep-block-title">Outgoing dependencies</div>
          {summary.outgoing.length ? (
            <div className="dep-tag-list">
              {summary.outgoing.map((e) => (
                <button key={`out-${e.target}-${e.kind}`} className="dep-tag is-out" onClick={() => setSelected(e.target)}>
                  {label(e.target)}
                </button>
              ))}
            </div>
          ) : (
            <div className="dep-empty">{selected ? 'No outgoing deps' : 'Select a node'}</div>
          )}
        </div>
      </div>

      <div className="dep-facts">
        <div className="fact-card">
          <div className="fact-title">Highly coupled modules</div>
          <div className="fact-list">
            {facts.coupled.length ? facts.coupled.map((c) => (
              <div className="fact-row" key={`${c.a}-${c.b}`}>
                <span>{label(c.a)} ↔ {label(c.b)}</span>
                <b>{c.count} links</b>
              </div>
            )) : (
              <div className="fact-row"><span className="ok-text">No significant couples detected</span></div>
            )}
          </div>
        </div>
        <div className="fact-card">
          <div className="fact-title">Circular dependencies</div>
          <div className="fact-list">
            {facts.cycles.length ? facts.cycles.map((cycle, i) => (
              <div className="fact-row" key={`cycle-${i}`}>
                <span className="has-warn">{cycle.map((id) => label(id)).join(' → ')}</span>
                <b className="warn-text">detected</b>
              </div>
            )) : (
              <div className="fact-row"><span className="ok-text">No cycles found</span><b className="ok-text">stable</b></div>
            )}
          </div>
        </div>
        <div className="fact-card">
          <div className="fact-title">Risky dependencies</div>
          <div className="fact-list">
            {facts.risky.length ? facts.risky.map((r) => (
              <div className="fact-row" key={`risk-${r.id}`}>
                <span>{label(r.id)}</span>
                <b className={r.risk === 'Critical' || r.risk === 'High' ? 'warn-text' : 'ok-text'}>{r.risk}</b>
              </div>
            )) : (
              <div className="fact-row"><span className="ok-text">No high-risk modules</span><b className="ok-text">stable</b></div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Top module pairs by number of edges between them (both directions).
function coupledModules(nodes, edges, label, limit) {
  const pairs = new Map();
  edges.forEach((e) => {
    if (e.kind === 'contains') return;
    const a = e.source, b = e.target;
    if (a === b) return;
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    pairs.set(key, (pairs.get(key) || 0) + 1);
  });
  return [...pairs.entries()]
    .map(([key, count]) => {
      const [a, b] = key.split('|');
      return { a, b, count };
    })
    .sort((x, y) => y.count - x.count || label(y.a).localeCompare(label(x.a)))
    .slice(0, limit);
}

// A representative cycle path (a -> x -> ... -> a) per detected cycle.
function findCycles(nodes, edges) {
  const adj = new Map();
  edges.forEach((e) => {
    if (e.kind === 'contains') return;
    if (!adj.has(e.source)) adj.set(e.source, []);
    adj.get(e.source).push(e.target);
  });

  const GRAY = 1, BLACK = 2;
  const color = new Map();
  const stack = [];
  const cycles = [];

  function dfs(u) {
    color.set(u, GRAY);
    stack.push(u);
    for (const v of adj.get(u) || []) {
      if (!color.has(v)) {
        if (dfs(v)) return true;
      } else if (color.get(v) === GRAY) {
        const idx = stack.indexOf(v);
        cycles.push([...stack.slice(idx), v]);
        return true;
      }
    }
    stack.pop();
    color.set(u, BLACK);
    return false;
  }

  for (const n of nodes) {
    if (!color.has(n.id)) {
      if (dfs(n.id)) break;
    }
  }
  return cycles;
}

// Highest-risk modules/files by dependency weight (risk from meta, weight from
// deps + dependents). Falls back to low-confidence edges when no node risk set.
function riskyDependencies(nodes, edges, limit) {
  const withRisk = nodes
    .map((n) => ({
      id: n.id,
      risk: n.meta?.risk || 'Low',
      weight: (n.meta?.deps || 0) + (n.meta?.dependents || 0),
    }))
    .filter((n) => n.risk === 'High' || n.risk === 'Critical')
    .sort((a, b) => b.weight - a.weight);

  if (withRisk.length) return withRisk.slice(0, limit);

  return edges
    .filter((e) => e.kind !== 'contains' && (e.relationshipSource !== 'ast' || (e.confidence ?? 1) < 0.8))
    .map((e) => ({ id: e.target, risk: 'Medium' }))
    .slice(0, limit);
}
