import { env } from "cloudflare:workers";

let ready = false;

export async function ensureScoreSchema() {
  if (ready) return;
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS daily_scores (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      as_of_date TEXT NOT NULL,
      recorded_at TEXT NOT NULL,
      last_price REAL NOT NULL,
      change_pct REAL NOT NULL,
      strategic_score REAL NOT NULL,
      tactical_score REAL NOT NULL,
      comprehensive_score REAL NOT NULL,
      buy_signal REAL NOT NULL,
      sell_signal REAL NOT NULL,
      intraday_t_signal REAL NOT NULL,
      position_pct REAL NOT NULL,
      oversold_bonus REAL NOT NULL DEFAULT 0,
      source TEXT NOT NULL,
      data_quality INTEGER NOT NULL DEFAULT 0,
      factors_json TEXT NOT NULL DEFAULT '{}',
      diagnostics_json TEXT NOT NULL DEFAULT '{}'
    )`),
    env.DB.prepare("CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_scores_as_of_date ON daily_scores(as_of_date)"),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_daily_scores_recorded_at ON daily_scores(recorded_at)"),
  ]);
  ready = true;
}
