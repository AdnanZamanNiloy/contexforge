export default function RepositoryStats({ stats = {} }) {
  const items = [
    { label: 'Files', value: stats.files },
    { label: 'Modules', value: stats.modules },
    { label: 'Commits', value: stats.commits },
    { label: 'Contributors', value: stats.contributors },
    { label: 'Branches', value: stats.branches },
    { label: 'Pull Requests', value: stats.pullRequests },
    { label: 'Issues', value: stats.issues },
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
