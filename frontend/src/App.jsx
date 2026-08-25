import { Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import RepositoryIntelligencePage from './pages/repository/RepositoryIntelligencePage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/repository" element={<RepositoryIntelligencePage />} />
      <Route path="/repository/:repositoryId" element={<RepositoryIntelligencePage />} />
    </Routes>
  );
}
