const STEP_BASE = 'tool-btn';

export default function RepositoryTabs({ active, onChange }) {
  const tabs = [
    { id: 'architecture', label: 'Architecture' },
    { id: 'dependencies', label: 'Dependencies' },
    { id: 'data-flow', label: 'Data Flow' },
    { id: 'git-history', label: 'Git History' },
    { id: 'ownership', label: 'Ownership' },
    { id: 'change-impact', label: 'Change Impact' },
  ];

  return (
    <nav className="repo-tabs">
      <div className="repo-tabs-track">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={active === tab.id ? 'repo-tab active' : 'repo-tab'}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="repo-tabs-actions">
        <button className="tool-btn">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>
          Filter
        </button>
      </div>
    </nav>
  );
}
