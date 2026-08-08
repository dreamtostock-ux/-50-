import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("contains the finished dashboard and deployable build", async () => {
  const [page, dashboard, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/score-dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    access(new URL("../dist/server/index.js", import.meta.url)),
  ]);
  assert.match(page, /515450 红利低波评分台/);
  assert.match(dashboard, /每日评分记录/);
  assert.match(dashboard, /latest_trading_date/);
  assert.match(dashboard, /isTradingRecord/);
  assert.match(dashboard, /数据可信度/);
  assert.match(css, /@media\(max-width:620px\)/);
  assert.doesNotMatch(`${page}${dashboard}`, /codex-preview|Your site is taking shape|react-loading-skeleton/);
});
