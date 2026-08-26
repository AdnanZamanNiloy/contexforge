import { Routes, Route, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import MindMapPage from './pages/MindMapPage';
import RepositoryIntelligencePage from './pages/repository/RepositoryIntelligencePage';

export default function App() {
  const location = useLocation();
  // Keying the wrapper on the current pathname forces the route subtree to
  // remount on navigation, so the page-transition animation (fade + slide) plays
  // when switching between the chat view and Repository Intelligence instead of
  // snapping abruptly to a blank screen.
  return (
    <div className="page-transition" key={location.pathname}>
      <Routes location={location}>
        <Route path="/" element={<Home />} />
        <Route path="/mindmap/:sourceId" element={<MindMapPage />} />
        <Route path="/repository" element={<RepositoryIntelligencePage />} />
        <Route path="/repository/:repositoryId" element={<RepositoryIntelligencePage />} />
      </Routes>
    </div>
  );
}
