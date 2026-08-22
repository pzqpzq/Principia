import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { LibraryPage } from "./pages/LibraryPage";
import { MapPage } from "./pages/MapPage";
import { ResearchWorkspacePage } from "./pages/ResearchWorkspacePage";

export function App() {
  return <Routes><Route element={<Shell />}><Route path="/research/new" element={<ResearchWorkspacePage />} /><Route path="/research/:sessionId" element={<ResearchWorkspacePage />} /><Route path="/library" element={<Navigate to="/research/new" replace />} /><Route path="/map" element={<MapPage />} /><Route path="/local" element={<Navigate to="/research/new?settings=local" replace />} /><Route path="/legacy/library" element={<LibraryPage />} /><Route path="*" element={<Navigate to="/research/new" replace />} /></Route></Routes>;
}
