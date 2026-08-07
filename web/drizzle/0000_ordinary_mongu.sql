CREATE TABLE `daily_scores` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`as_of_date` text NOT NULL,
	`recorded_at` text NOT NULL,
	`last_price` real NOT NULL,
	`change_pct` real NOT NULL,
	`strategic_score` real NOT NULL,
	`tactical_score` real NOT NULL,
	`comprehensive_score` real NOT NULL,
	`buy_signal` real NOT NULL,
	`sell_signal` real NOT NULL,
	`intraday_t_signal` real NOT NULL,
	`position_pct` real NOT NULL,
	`oversold_bonus` real DEFAULT 0 NOT NULL,
	`source` text NOT NULL,
	`data_quality` integer DEFAULT 0 NOT NULL,
	`factors_json` text DEFAULT '{}' NOT NULL,
	`diagnostics_json` text DEFAULT '{}' NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_daily_scores_as_of_date` ON `daily_scores` (`as_of_date`);--> statement-breakpoint
CREATE INDEX `idx_daily_scores_recorded_at` ON `daily_scores` (`recorded_at`);