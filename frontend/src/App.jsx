import { Routes, Route, useLocation } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import Home from './pages/Home'
import RepositoryIntelligencePage from './pages/repository/RepositoryIntelligencePage'
import ModelHubPage from './pages/modelhub/ModelHubPage'
import ProjectsPage from './pages/projects/ProjectsPage'

export default function App() {
  const location = useLocation()
  // Keying the wrapper on the current pathname forces the route subtree to
  // remount on navigation, so the page-transition animation (fade + slide) plays
  // when switching between the landing page, the project workspace and
  // Repository Intelligence instead of snapping abruptly to a blank screen.
  return (
    <div className="page-transition" key={location.pathname}>
      <Routes location={location}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        {/* The project workspace is the only workspace: sources are selected
            here, in the sidebar, rather than opened in a page of their own. */}
        <Route path="/projects/:projectId" element={<Home />} />
        <Route path="/workspace" element={<Home />} />
        <Route path="/repository" element={<RepositoryIntelligencePage />} />
        <Route path="/repository/:repositoryId" element={<RepositoryIntelligencePage />} />
        <Route path="/models" element={<ModelHubPage />} />
        {/* Removed source workspaces: /sources/:sourceId and /mindmap/:sourceId.
            Anything unrecognised falls back to the workspace. */}
        <Route path="*" element={<Home />} />
      </Routes>
    </div>
  )
}
