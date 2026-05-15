export default function RepoInput({ onIngest, isLoading, repos }) {
  const handleSubmit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const url = form.elements.repo?.value || '';
    if (url.trim()) {
      onIngest(url.trim());
      form.reset();
    }
  };

  return (
    <section className="panel">
      <h3>GitHub Repos</h3>
      <form className="input-row" onSubmit={handleSubmit}>
        <input
          className="text-input"
          placeholder="https://github.com/user/repo"
          aria-label="GitHub repo URL"
          name="repo"
        />
        <button className="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'Adding...' : 'Add'}
        </button>
      </form>
      <div className="pill-row">
        {repos.map((repo) => (
          <span className="pill" key={repo}>
            {repo}
          </span>
        ))}
      </div>
    </section>
  );
}
