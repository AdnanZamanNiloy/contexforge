import { overviewStats } from '../../../data/repoIntelligence';

export default function RepositoryStats() {
  const items = [
    { label: 'Files', value: overviewStats.files },
    { label: 'Modules', value: overviewStats.modules },
    { label: 'Commits', value: overviewStats.commits },
    { label: 'Contributors', value: overviewStats.contributors },
    { label: 'Branches', value: overviewStats.branches },
    { label: 'Pull Requests', value: overviewStats.pullRequests },
    { label: 'Issues', value: overviewStats.issues },
  ];

  return (
    <section className="sidebar-section">
      <div className="sidebar-section-title">Repository Overview</div>
      <div className="stat-grid">
        {items.map((item) => (
          <div className="stat-cell" key={item.label}>
            <span className="stat-value">{item.value.toLocaleString()}</span>
            <span className="stat-label">{item.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
