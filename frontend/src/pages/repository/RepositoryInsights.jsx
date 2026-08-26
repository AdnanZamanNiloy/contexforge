import RepositoryStats from './components/RepositoryStats';
import RepositoryHealth from './components/RepositoryHealth';
import RepositoryActivity from './components/RepositoryActivity';

// The right-hand insight rail for Repository Intelligence, rendered inside the
// shared product shell.  Purely informational — the same source is shown in the
// main header, so nothing here duplicates product chrome.
export default function RepositoryInsights({ analysis, onViewHistory }) {
  const repo = analysis?.repository || {};
  const health = analysis?.health || {};
  const rankedModules = analysis?.rankedModules || [];
  const activity = analysis?.activity || [];

  return (
    <>
      <RepositoryStats stats={repo} />
      <RepositoryHealth health={health} rankedModules={rankedModules} />
      <RepositoryActivity activity={activity} onViewHistory={onViewHistory} />
    </>
  );
}
