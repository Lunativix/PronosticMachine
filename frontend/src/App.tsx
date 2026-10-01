import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SlipProvider } from "./slip";
import { BacktestPage } from "./pages/BacktestPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ConfigPage } from "./pages/ConfigPage";
import { CoveragePage } from "./pages/CoveragePage";
import { MatchAnalysisPage } from "./pages/MatchAnalysisPage";
import { ModelsPage } from "./pages/ModelsPage";
import { PropositionsPage } from "./pages/PropositionsPage";
import { UpcomingPage } from "./pages/UpcomingPage";

export default function App() {
  return (
    <SlipProvider>
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<PropositionsPage />} />
        <Route path="/matches" element={<UpcomingPage />} />
        <Route path="/signals" element={<PropositionsPage />} />
        <Route path="/combinations" element={<PropositionsPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/coverage" element={<CoveragePage />} />
        <Route path="/matches/:matchId" element={<MatchAnalysisPage />} />
        <Route path="/backtests" element={<BacktestPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/config" element={<ConfigPage />} />
      </Route>
    </Routes>
    </SlipProvider>
  );
}
