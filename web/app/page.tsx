import type { Metadata } from "next";
import { ScoreDashboard, type ScoreRow } from "./score-dashboard";

export const metadata: Metadata = {
  title: "515450 红利低波评分台",
  description: "基于实时行情、估值与股债利差的双层评分仪表板",
};

async function loadLatestScores(): Promise<ScoreRow[]> {
  try {
    const response = await fetch("https://score.dreamtofly.top/api/scores?days=90", {
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return [];
    const data = await response.json() as { scores?: ScoreRow[] };
    return data.scores ?? [];
  } catch {
    return [];
  }
}

export default async function Home() {
  const initialRows = await loadLatestScores();
  return <ScoreDashboard initialRows={initialRows} />;
}
