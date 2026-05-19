import type {
  DecisionDetail,
  GameState,
  GameSummary,
  RunSummary,
  Viewer,
} from "../model/types";

export interface ReplaySource {
  listRuns(): Promise<RunSummary[]>;
  listGames(run: string): Promise<GameSummary[]>;
  loadViewer(run: string, gameId: string): Promise<Viewer>;
  loadState(run: string, gameId: string, ref: string): Promise<GameState>;
  loadDecision(
    run: string,
    gameId: string,
    ref: string,
  ): Promise<DecisionDetail>;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load ${url}: ${res.status}`);
  }
  return (await res.json()) as T;
}

export class LocalFsSource implements ReplaySource {
  constructor(private readonly base = "/data") {}

  private gameUrl(run: string, gameId: string, ref: string) {
    return `${this.base}/${run}/games/${gameId}/${ref}`;
  }

  async listRuns(): Promise<RunSummary[]> {
    const data = await getJson<{ runs: RunSummary[] }>(`${this.base}/index.json`);
    return data.runs;
  }

  async listGames(run: string): Promise<GameSummary[]> {
    const data = await getJson<{ games: GameSummary[] }>(
      `${this.base}/${run}/index.json`,
    );
    return data.games;
  }

  loadViewer(run: string, gameId: string): Promise<Viewer> {
    return getJson<Viewer>(this.gameUrl(run, gameId, "viewer.json"));
  }

  loadState(run: string, gameId: string, ref: string): Promise<GameState> {
    return getJson<GameState>(this.gameUrl(run, gameId, ref));
  }

  loadDecision(
    run: string,
    gameId: string,
    ref: string,
  ): Promise<DecisionDetail> {
    return getJson<DecisionDetail>(this.gameUrl(run, gameId, ref));
  }
}

export const defaultSource = new LocalFsSource();
