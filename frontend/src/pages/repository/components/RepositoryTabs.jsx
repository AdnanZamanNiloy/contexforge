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
    </nav>
  );
}
