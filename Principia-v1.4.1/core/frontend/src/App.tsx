import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { AdminPage } from "./pages/AdminPage";
import { LibraryPage } from "./pages/LibraryPage";
import { LocalPage } from "./pages/LocalPage";
import { MapPage } from "./pages/MapPage";

export function App() {
  return <Routes><Route element={<Shell />}><Route path="/library" element={<LibraryPage />} /><Route path="/map" element={<MapPage />} /><Route path="/local" element={<LocalPage />} /><Route path="/admin" element={<AdminPage />} /><Route path="*" element={<Navigate to="/library" replace />} /></Route></Routes>;
}
