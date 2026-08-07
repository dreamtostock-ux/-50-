import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const dailyScores = sqliteTable("daily_scores", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  asOfDate: text("as_of_date").notNull(),
  recordedAt: text("recorded_at").notNull(),
  lastPrice: real("last_price").notNull(),
  changePct: real("change_pct").notNull(),
  strategicScore: real("strategic_score").notNull(),
  tacticalScore: real("tactical_score").notNull(),
  comprehensiveScore: real("comprehensive_score").notNull(),
  buySignal: real("buy_signal").notNull(),
  sellSignal: real("sell_signal").notNull(),
  intradayTSignal: real("intraday_t_signal").notNull(),
  positionPct: real("position_pct").notNull(),
  oversoldBonus: real("oversold_bonus").notNull().default(0),
  source: text("source").notNull(),
  dataQuality: integer("data_quality").notNull().default(0),
  factorsJson: text("factors_json").notNull().default("{}"),
  diagnosticsJson: text("diagnostics_json").notNull().default("{}"),
}, (table) => [
  uniqueIndex("idx_daily_scores_as_of_date").on(table.asOfDate),
  index("idx_daily_scores_recorded_at").on(table.recordedAt),
]);
