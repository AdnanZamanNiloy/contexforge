import { useMemo, useState } from 'react';
import GraphViewer from '../GraphViewer';
import { dependencyGraph } from '../../../data/repoIntelligence';

export default function DependencyView() {
  const [selected, setSelected] = useState(null);

  const selectedNode = useMemo(
    () => dependencyGraph.nodes.find((n) => n.id === selected) || null,
    [selected],
  );

  const summary = useMemo(() => {
    const outgoing = dependencyGraph.edges.filter((e) => e.source === selected);
    const incoming = dependencyGraph.edges.filter((e) => e.target === selected);
    return { outgoing, incoming };
  }, [selected]);

  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Dependencies</h3>
          <p className="intel-subtext">Incoming, outgoing and coupling between modules</p>
        </div>
        <div className="dep-breakdown">
          <span className="dep-chip"><i className="legend-dot" style={{ background: '#7aa2f7' }} /> Incoming <b>{summary.incoming.length}</b></span>
          <span className="dep-chip"><i className="legend-dot" style={{ background: '#67e0c8' }} /> Outgoing <b>{summary.outgoing.length}</b></span>
        </div>
      </div>

      <GraphViewer
        nodes={dependencyGraph.nodes}
        edges={dependencyGraph.edges}
        selected={selected}
        onSelect={setSelected}
        className="dep-graph"
        height={460}
      />

      <div className="dep-panel-strip">
        <div className="dep-left">
          <div className="dep-block-title">Incoming dependencies</div>
          {summary.incoming.length ? (
            <div className="dep-tag-list">
              {summary.incoming.map((e) => (
                <button key={`in-${e.source}`} className="dep-tag is-in" onClick={() => setSelected(e.source)}>
                  {dependencyGraph.nodes.find((n) => n.id === e.source)?.label}
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
                <button key={`out-${e.target}`} className="dep-tag is-out" onClick={() => setSelected(e.target)}>
                  {dependencyGraph.nodes.find((n) => n.id === e.target)?.label}
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
            <div className="fact-row"><span>core-retrieval ↔ orchestrator</span><b>9 links</b></div>
            <div className="fact-row"><span>hybrid_retriever ↔ faiss</span><b>7 links</b></div>
            <div className="fact-row"><span>query_service ↔ routes</span><b>6 links</b></div>
          </div>
        </div>
        <div className="fact-card">
          <div className="fact-title">Circular dependencies</div>
          <div className="fact-list">
            <div className="fact-row"><span className="has-warn">retrieval → generation → retrieval</span><b className="warn-text">detected</b></div>
            <div className="fact-row"><span className="ok-text">No other cycles found</span><b className="ok-text">stable</b></div>
          </div>
        </div>
        <div className="fact-card">
          <div className="fact-title">Risky dependencies</div>
          <div className="fact-list">
            <div className="fact-row"><span>@crypto/unstable-*</span><b className="warn-text">high</b></div>
            <div className="fact-row"><span>faiss-cpu (binary)</span><b className="warn-text">medium</b></div>
            <div className="fact-row"><span>tiktoken</span><b className="ok-text">current</b></div>
          </div>
        </div>
      </div>
    </div>
  );
}
