import { useState } from 'react';
import Home from './pages/Home';
import RepositoryIntelligencePage from './pages/repository/RepositoryIntelligencePage';

export default function App() {
  const [view, setView] = useState('home');

  if (view === 'repo-intel') {
    return <RepositoryIntelligencePage onExit={() => setView('home')} />;
  }

  return <Home onOpenRepositoryIntelligence={() => setView('repo-intel')} />;
}
