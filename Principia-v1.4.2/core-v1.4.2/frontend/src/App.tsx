import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./components/Shell";
import { LibraryPage } from "./pages/LibraryPage";
import { MapPage } from "./pages/MapPage";

const ResearchWorkspacePage = lazy(async () => {
  const module = await import("./pages/ResearchWorkspacePage");
  return { default: module.ResearchWorkspacePage };
});

function ResearchWorkspaceRoute() {
  const location = useLocation();
  return (
    <Suspense
      fallback={
        <main className="route-loading" role="status" aria-live="polite">
          <span className="route-loading-mark" aria-hidden="true" />
          <strong>Opening your research workspace…</strong>
          <span>Restoring the project map and saved run.</span>
        </main>
      }
    >
      <ResearchWorkspacePage key={location.pathname} />
    </Suspense>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/research/new" element={<ResearchWorkspaceRoute />} />
        <Route path="/research/:sessionId" element={<ResearchWorkspaceRoute />} />
        <Route path="/library" element={<Navigate to="/research/new" replace />} />
        <Route path="/map" element={<MapPage />} />
        <Route
          path="/local"
          element={<Navigate to="/research/new?settings=local" replace />}
        />
        <Route path="/legacy/library" element={<LibraryPage />} />
        <Route path="*" element={<Navigate to="/research/new" replace />} />
      </Route>
    </Routes>
  );
}
