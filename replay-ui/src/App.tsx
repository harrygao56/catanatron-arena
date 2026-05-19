import { BrowserRouter, Route, Routes } from "react-router-dom";
import { RunsIndex } from "./pages/RunsIndex";
import { GamesIndex } from "./pages/GamesIndex";
import { GameReplay } from "./pages/GameReplay";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RunsIndex />} />
        <Route path="/r/:run" element={<GamesIndex />} />
        <Route path="/r/:run/g/:gameId" element={<GameReplay />} />
      </Routes>
    </BrowserRouter>
  );
}
