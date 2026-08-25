import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { dataFlows } from '../../../data/repoIntelligence';

const FLOW_KIND_ICON = {
  input: 'arrow',
  output: 'terminal',
  service: 'box',
  core: 'cog',
  module: 'module',
  llm: 'spark',
  transport: 'wifi',
  storage: 'database',
};

function FlowIcon({ kind }) {
  switch (kind) {
    case 'input':
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg>;
    case 'output':
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 9l3 3-3 3M13 15h4" /></svg>;
    case 'llm':
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z" /></svg>;
    case 'transport':
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1.4 9a16 16 0 0 1 21.2 0M5 12.5a11 11 0 0 1 14 0M8.5 16a6 6 0 0 1 7 0" /><circle cx="12" cy="19.5" r="1" /></svg>;
    case 'storage':
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0" /></svg>;
    case 'service':
    default:
      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="3" /></svg>;
  }
}

function Pipelines() {
  const [animKey, setAnimKey] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setAnimKey((k) => k + 1), 9000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="pipe-row">
      {(Object.values(dataFlows)).map((flow) => (
        <div className="pipeline" key={animKey + flow.title}>
          <div className="pipeline-title">{flow.title}</div>
          <div className="pipeline-bodies">
            {flow.steps.map((step, i) => (
              <div className="pipe-segment" key={step.id}>
                <motion.div
                  className={`pipe-node ${step.kind}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.06 }}
                >
                  <span className="pipe-node-icon"><FlowIcon kind={step.kind} /></span>
                  <span className="pipe-node-label">{step.label}</span>
                </motion.div>
                {i < flow.steps.length - 1 ? (
                  <div className="pipe-connector">
                    <motion.span
                      className="pipe-dot"
                      animate={{ left: ['0%', '100%'] }}
                      transition={{ duration: 2.2, repeat: Infinity, ease: 'linear', delay: i * 0.12 }}
                    />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DataFlowView() {
  const [active, setActive] = useState('both');
  return (
    <div className="intel-view">
      <div className="intel-view-header">
        <div>
          <h3>Data Flow</h3>
          <p className="intel-subtext">Directional execution and ingestion pipelines</p>
        </div>
        <div className="flow-toggle">
          <button className={active !== 'ingestion' ? 'active' : ''} onClick={() => setActive('query')}>Query</button>
          <button className={active !== 'query' ? 'active' : ''} onClick={() => setActive('ingestion')}>Ingestion</button>
          <button className={active === 'both' ? 'active' : ''} onClick={() => setActive('both')}>Both</button>
        </div>
      </div>

      <div className="flow-summary">
        <span><b>Question</b> → <b>QueryService</b> → <b>Orchestrator</b> → <b>HyDE</b> → <b>Hybrid Retrieval</b> → <b>RRF</b> → <b>Reranker</b> → <b>Prompt Builder</b> → <b>LLM</b> → <b>SSE</b> → <b>Frontend</b></span>
      </div>

      <div className="flow-canvas">
        <Pipelines />
      </div>

      <div className="flow-notes">
        <div className="fact-card">
          <div className="fact-title">Query path heat</div>
          <div className="fact-list">
            <div className="fact-row"><span>Hybrid Retrieval</span><div className="mini-bar"><i style={{ width: '94%' }} /></div></div>
            <div className="fact-row"><span>Reranker</span><div className="mini-bar"><i style={{ width: '72%' }} /></div></div>
            <div className="fact-row"><span>LLM</span><div className="mini-bar"><i style={{ width: '58%' }} /></div></div>
          </div>
        </div>
        <div className="fact-card">
          <div className="fact-title">Bottlenecks</div>
          <div className="fact-list">
            <div className="fact-row"><span>Embedding API latency</span><b className="warn-text">8.2s avg</b></div>
            <div className="fact-row"><span>Cross-encoder rerank</span><b className="warn-text">0.4s</b></div>
            <div className="fact-row"><span>LLM generation</span><b className="ok-text">streamed</b></div>
          </div>
        </div>
      </div>
    </div>
  );
}
