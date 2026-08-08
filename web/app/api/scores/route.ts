import { desc, gte } from "drizzle-orm";
import { getDb } from "../../../db";
import { ensureScoreSchema } from "../../../db/ensure";
import { dailyScores } from "../../../db/schema";

type IncomingScore = Record<string, unknown>;

function value(body: IncomingScore, camel: string, snake: string) {
  return body[camel] ?? body[snake];
}

function number(body: IncomingScore, camel: string, snake: string) {
  const parsed = Number(value(body, camel, snake));
  if (!Number.isFinite(parsed)) throw new Error(`${snake} must be numeric`);
  return parsed;
}

function boundScore(n: number, name: string) {
  if (n < 0 || n > 100) throw new Error(`${name} must be between 0 and 100`);
  return n;
}

function parseJson(text: string) {
  try { return JSON.parse(text) as Record<string, unknown>; } catch { return {}; }
}

function present(row: typeof dailyScores.$inferSelect) {
  return {
    asOfDate: row.asOfDate, recordedAt: row.recordedAt, lastPrice: row.lastPrice,
    changePct: row.changePct, strategicScore: row.strategicScore,
    tacticalScore: row.tacticalScore, comprehensiveScore: row.comprehensiveScore,
    buySignal: row.buySignal, sellSignal: row.sellSignal,
    intradayTSignal: row.intradayTSignal, positionPct: row.positionPct,
    oversoldBonus: row.oversoldBonus, source: row.source, dataQuality: row.dataQuality,
    factors: parseJson(row.factorsJson), diagnostics: parseJson(row.diagnosticsJson),
  };
}

function isTradingRecord(row: typeof dailyScores.$inferSelect) {
  const diagnostics = parseJson(row.diagnosticsJson);
  const latestTradingDate = diagnostics.latest_trading_date;
  if (typeof latestTradingDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(latestTradingDate)) {
    return latestTradingDate === row.asOfDate;
  }
  const weekday = new Date(`${row.asOfDate}T12:00:00+08:00`).getUTCDay();
  return weekday !== 0 && weekday !== 6;
}

export async function GET(request: Request) {
  try {
    await ensureScoreSchema();
    const days = Math.min(365, Math.max(1, Number(new URL(request.url).searchParams.get("days") ?? 30)));
    const cutoff = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
    const rows = await getDb().select().from(dailyScores).where(gte(dailyScores.asOfDate, cutoff)).orderBy(desc(dailyScores.asOfDate)).limit(Math.min(365, days + 16));
    return Response.json({ scores: rows.filter(isTradingRecord).slice(0, days).map(present) }, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to read scores" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const expectedKey = process.env.INGEST_KEY;
    if (expectedKey && request.headers.get("x-ingest-key") !== expectedKey) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }
    const body = await request.json() as IncomingScore;
    const recordedAt = String(value(body, "recordedAt", "timestamp") ?? new Date().toISOString());
    const asOfDate = String(value(body, "asOfDate", "as_of_date") ?? recordedAt.slice(0, 10));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(asOfDate)) throw new Error("as_of_date must use YYYY-MM-DD");
    const diagnostics = (body.diagnostics ?? {}) as Record<string, unknown>;
    const latestTradingDate = diagnostics.latest_trading_date;
    if (typeof latestTradingDate === "string" && latestTradingDate !== asOfDate) {
      return Response.json({ skipped: true, reason: "non_trading_day", latestTradingDate }, { status: 202 });
    }

    const payload: typeof dailyScores.$inferInsert = {
      asOfDate, recordedAt,
      lastPrice: number(body, "lastPrice", "last_price"), changePct: number(body, "changePct", "change_pct"),
      strategicScore: boundScore(number(body, "strategicScore", "strategic_score"), "strategic_score"),
      tacticalScore: boundScore(number(body, "tacticalScore", "tactical_score"), "tactical_score"),
      comprehensiveScore: boundScore(number(body, "comprehensiveScore", "comprehensive_score"), "comprehensive_score"),
      buySignal: boundScore(number(body, "buySignal", "buy_signal"), "buy_signal"),
      sellSignal: boundScore(number(body, "sellSignal", "sell_signal"), "sell_signal"),
      intradayTSignal: boundScore(number(body, "intradayTSignal", "intraday_t_signal"), "intraday_t_signal"),
      positionPct: boundScore(number(body, "positionPct", "position_pct"), "position_pct"),
      oversoldBonus: Number(value(body, "oversoldBonus", "oversold_bonus") ?? 0),
      source: String(body.source ?? "unknown"),
      dataQuality: Math.round(boundScore(Number(value(body, "dataQuality", "data_quality") ?? 0), "data_quality")),
      factorsJson: JSON.stringify(body.factors ?? {}), diagnosticsJson: JSON.stringify(diagnostics),
    };
    await ensureScoreSchema();
    const db = getDb();
    await db.insert(dailyScores).values(payload).onConflictDoUpdate({
      target: dailyScores.asOfDate,
      set: { ...payload },
    });
    const [saved] = await db.select().from(dailyScores).where(gte(dailyScores.asOfDate, asOfDate)).orderBy(desc(dailyScores.asOfDate)).limit(1);
    return Response.json({ score: present(saved) }, { status: 201 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to save score" }, { status: 400 });
  }
}
