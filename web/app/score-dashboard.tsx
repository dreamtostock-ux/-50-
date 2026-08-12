"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type FactorMap = Record<string, number>;
type DiagnosticMap = Record<string, unknown>;
export type ScoreRow = {
  asOfDate: string;
  recordedAt: string;
  lastPrice: number;
  changePct: number;
  strategicScore: number;
  tacticalScore: number;
  comprehensiveScore: number;
  buySignal: number;
  sellSignal: number;
  intradayTSignal: number;
  positionPct: number;
  oversoldBonus: number;
  source: string;
  dataQuality: number;
  factors: FactorMap;
  diagnostics: DiagnosticMap;
};

const VERIFIED_SOURCES = [
  { name: "Futu OpenD", role: "实时价 / K线 / 盘口", grade: "实时", tone: "live" },
  { name: "中债估值中心", role: "10年期国债收益率", grade: "T-1 官方", tone: "official" },
  { name: "Futu 十年估值", role: "中证红利 PE / PB 历史代理", grade: "2423日", tone: "official" },
  { name: "腾讯 / 东财", role: "ETF份额交叉校验", grade: "每日", tone: "backup" },
];

const INITIAL_SCORE: ScoreRow = {
  asOfDate: "2026-08-07",
  recordedAt: "2026-08-07T15:05:00+08:00",
  lastPrice: 1.391,
  changePct: -1.07,
  strategicScore: 73.2,
  tacticalScore: 45.4,
  comprehensiveScore: 64.8,
  buySignal: 61.1,
  sellSignal: 12.1,
  intradayTSignal: 62.7,
  positionPct: 45,
  oversoldBonus: 2,
  source: "Futu OpenD · 本地实测",
  dataQuality: 74,
  factors: {
    dividend_spread: 82.5,
    erp: 79.1,
    pb_percentile: 72,
    pe_percentile: 68,
    dividend_yield: 85.5,
    daily_rsi: 57.1,
    long_trend: 52.6,
    market_environment: 62,
  },
  diagnostics: {
    bond_10y_yield_pct: 1.7143,
    dividend_yield_pct: 5.2,
    dividend_spread_pct: 3.4857,
    earnings_yield_pct: 7.1,
    erp_pct: 5.3857,
    pb_percentile_pct: 28,
    pe_percentile_pct: 32,
    vwap_deviation_pct: -0.47,
    relative_change_pct: -1.45,
    daily_rsi14: 46.457,
    intraday_rsi14: 50.8,
    rsi14: 50.8,
    static_as_of: "2026-08-06 / 2026-06-29",
  },
};

const scoreMeta = [
  { key: "comprehensiveScore", label: "综合评分", helper: "长期价值 × 市场状态", accent: "lime" },
  { key: "buySignal", label: "估值吸引力", helper: "价值与偏离状态", accent: "green" },
  { key: "sellSignal", label: "过热风险", helper: "估值与短线温度", accent: "rose" },
  { key: "intradayTSignal", label: "日内波动状态", helper: "VWAP 与相对波动", accent: "amber" },
] as const;

function scoreLabel(value: number) {
  if (value >= 80) return "强";
  if (value >= 65) return "偏强";
  if (value >= 50) return "中性";
  if (value >= 35) return "偏弱";
  return "弱";
}

function strategicHeadline(value: number) {
  if (value >= 80) return "长期价值评价较强";
  if (value >= 65) return "长期价值评价偏强";
  if (value >= 50) return "长期价值评价中性";
  if (value >= 35) return "长期价值评价偏弱";
  return "长期价值评价较弱";
}

function tacticalHeadline(value: number) {
  if (value >= 80) return "盘中市场状态较强";
  if (value >= 65) return "盘中市场状态偏强";
  if (value >= 50) return "盘中市场状态中性";
  if (value >= 35) return "盘中市场状态偏弱";
  return "盘中市场状态较弱";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(`${value}T00:00:00+08:00`));
}

function isTradingRecord(row: ScoreRow) {
  const latestTradingDate = row.diagnostics.latest_trading_date;
  if (typeof latestTradingDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(latestTradingDate)) {
    return latestTradingDate === row.asOfDate;
  }
  const weekday = new Date(`${row.asOfDate}T12:00:00+08:00`).getUTCDay();
  return weekday !== 0 && weekday !== 6;
}

function shanghaiClock(now: Date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(now);
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? "00";
  return {
    date: `${value("year")}-${value("month")}-${value("day")}`,
    minutes: Number(value("hour")) * 60 + Number(value("minute")),
  };
}

function parseRecordedAt(value: string) {
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}+08:00`;
  return new Date(withZone);
}

function marketState(latest: ScoreRow, now: Date) {
  const clock = shanghaiClock(now);
  const latestTradingDate = String(latest.diagnostics.latest_trading_date ?? latest.asOfDate);
  const isCurrentTradingDay = latestTradingDate === clock.date;
  const morningOpen = clock.minutes >= 570 && clock.minutes < 690;
  const afternoonOpen = clock.minutes >= 780 && clock.minutes < 900;
  const isOpenSession = morningOpen || afternoonOpen;
  const ageMs = now.getTime() - parseRecordedAt(latest.recordedAt).getTime();

  if (clock.minutes < 570) return { label: isCurrentTradingDay ? "未开盘" : "等待开盘", tone: "paused" };
  if (isOpenSession) {
    if (!isCurrentTradingDay || ageMs > 180_000) return { label: "行情更新延迟", tone: "delayed" };
    return { label: "交易中", tone: "open" };
  }
  if (clock.minutes >= 690 && clock.minutes < 780) return { label: isCurrentTradingDay ? "午间休市" : "休市", tone: "paused" };
  return { label: isCurrentTradingDay ? "交易已收盘" : "休市", tone: "closed" };
}

function formatRecordedTime(row: ScoreRow) {
  const recorded = parseRecordedAt(row.recordedAt);
  if (Number.isNaN(recorded.getTime())) return row.asOfDate;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(recorded);
}

const DECISION_GUIDES = [
  {
    key: "comprehensiveScore" as const,
    title: "综合评分",
    note: "综合描述战略与战术层的模型状态，不代表收益预测",
    thresholds: [35, 50, 65, 80],
    bands: ["0–34｜模型评价较弱", "35–49｜模型评价偏弱", "50–64｜模型评价中性", "65–79｜模型评价偏强", "80–100｜模型评价较强"],
  },
  {
    key: "buySignal" as const,
    title: "估值吸引力",
    note: "描述当前估值、股债利差与价格偏离的合成状态",
    thresholds: [50, 65, 80, 90],
    bands: ["0–49｜吸引力较低", "50–64｜吸引力中性", "65–79｜吸引力偏高", "80–89｜吸引力较高", "90–100｜吸引力极高，需先核验数据"],
  },
  {
    key: "sellSignal" as const,
    title: "过热风险",
    note: "描述估值、动量与短线偏离所反映的过热程度",
    thresholds: [50, 65, 80, 90],
    bands: ["0–49｜过热风险较低", "50–64｜过热风险中性", "65–79｜过热风险偏高", "80–89｜过热风险较高", "90–100｜过热风险极高，需先核验异常"],
  },
  {
    key: "intradayTSignal" as const,
    title: "日内波动状态",
    note: "描述 VWAP 偏离、相对波动与盘中动量的活跃程度",
    thresholds: [50, 65, 80, 90],
    bands: ["0–49｜波动状态平缓", "50–64｜波动状态一般", "65–79｜波动状态活跃", "80–89｜波动状态较高", "90–100｜波动状态极高，需核验行情与流动性"],
  },
];

function decisionBandIndex(value: number, thresholds: number[]) {
  const index = thresholds.findIndex((threshold) => value < threshold);
  return index === -1 ? thresholds.length : index;
}

export function ScoreDashboard({ initialRows = [] }: { initialRows?: ScoreRow[] }) {
  const seededRows = initialRows.filter(isTradingRecord);
  const initialHistory = seededRows.length ? seededRows : [INITIAL_SCORE];
  const [rows, setRows] = useState<ScoreRow[]>(initialHistory);
  const [selectedDate, setSelectedDate] = useState(initialHistory[0].asOfDate);
  const [range, setRange] = useState<7 | 30 | 90>(30);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [clock, setClock] = useState(() => new Date());

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await fetch(`/api/scores?days=${range}`, { cache: "no-store" });
      if (!response.ok) throw new Error("history unavailable");
      const data = (await response.json()) as { scores?: ScoreRow[] };
      const tradingRows = data.scores?.filter(isTradingRecord) ?? [];
      if (tradingRows.length) {
        setRows(tradingRows);
        setSelectedDate((current) => tradingRows.some((row) => row.asOfDate === current) ? current : tradingRows[0].asOfDate);
        setNotice("");
      }
    } catch {
      setNotice("正在显示最近一次本地实测记录；启动采集器后会自动写入每日数据。");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      setClock(new Date());
      void load(true);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const current = rows.find((row) => row.asOfDate === selectedDate) ?? rows[0] ?? INITIAL_SCORE;
  const latest = rows[0] ?? current;
  const session = marketState(latest, clock);
  const quality = (current.diagnostics.quality_detail ?? {}) as Record<string, number>;
  const chronological = useMemo(() => [...rows].reverse(), [rows]);
  const factorRows = [
    ["股债利差", Number(current.diagnostics.dividend_spread_pct), "%", current.factors.dividend_spread],
    ["ERP", Number(current.diagnostics.erp_pct), "%", current.factors.erp],
    ["股息率", Number(current.diagnostics.dividend_yield_pct), "%", current.factors.dividend_yield],
    ["PB 历史分位", Number(current.diagnostics.pb_percentile_pct), "%", current.factors.pb_percentile],
    ["PE 历史分位", Number(current.diagnostics.pe_percentile_pct), "%", current.factors.pe_percentile],
    ["日线 RSI14", Number(current.diagnostics.daily_rsi14 ?? 50), "", current.factors.daily_rsi ?? 50],
  ] as Array<[string, number | string, string, number]>;

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="返回顶部">
          <span className="brand-mark">50</span>
          <span><b>红利低波评分台</b><small>SH · 515450</small></span>
        </a>
        <div className={`market-state ${session.tone}`}><i />{session.label} <span>数据截至 {formatRecordedTime(latest)}</span></div>
        <button className="refresh-button" onClick={() => void load()} disabled={loading} aria-label="刷新评分">
          {loading ? "同步中" : "刷新数据"}
        </button>
      </header>

      <aside className="research-disclaimer" role="note" aria-label="研究用途与数据延迟提示">
        <div className="disclaimer-mark">!</div>
        <div>
          <strong>仅供非商业研究使用 · 数据可能延迟</strong>
          <p>本页展示的是模型状态，不构成证券投资咨询、个性化建议或收益承诺。本站不收费、不接受打赏、不提供会员提醒或交易导流；行情与估值数据可能延迟、缺失或有误，请以交易所、基金管理人及数据源正式披露为准。</p>
        </div>
      </aside>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">S&amp;P CHINA A-SHARE · LOW VOL / HIGH DIVIDEND</p>
          <h1>{strategicHeadline(current.strategicScore)}，<br /><em>{tacticalHeadline(current.tacticalScore)}。</em></h1>
          <p className="hero-note">战略分每日收盘更新，战术分随价格变化。所有宏观与估值数据均显示来源日期，过期数据自动降低可信度。</p>
        </div>
        <div className="price-panel">
          <div><span>最新价</span><strong>{current.lastPrice.toFixed(4)}</strong></div>
          <div className={current.changePct >= 0 ? "positive" : "negative"}>{current.changePct >= 0 ? "+" : ""}{current.changePct.toFixed(2)}%</div>
          <p>{current.source}</p>
        </div>
      </section>

      {notice && <div className="notice">{notice}</div>}

      <section className="score-grid" aria-label="核心评分">
        <article className="main-score-card">
          <div className="card-heading"><span>今日综合评分</span><b>{scoreLabel(current.comprehensiveScore)}</b></div>
          <div className="score-orbit" style={{ "--score": current.comprehensiveScore } as React.CSSProperties}>
            <strong>{current.comprehensiveScore.toFixed(1)}</strong><span>/ 100</span>
          </div>
          <div className="split-score"><span>战略 <b>{current.strategicScore.toFixed(1)}</b></span><span>战术 <b>{current.tacticalScore.toFixed(1)}</b></span></div>
        </article>
        <div className="signal-grid">
          {scoreMeta.slice(1).map((meta) => {
            const value = current[meta.key];
            return <article className={`signal-card ${meta.accent}`} key={meta.key}>
              <div><span>{meta.label}</span><small>{meta.helper}</small></div>
              <strong>{value.toFixed(1)}</strong>
              <div className="score-bar"><i style={{ width: `${value}%` }} /></div>
              <b>{scoreLabel(value)}</b>
            </article>;
          })}
          <article className="position-card">
            <span>模型仓位示例</span><strong>{current.positionPct.toFixed(0)}<small>%</small></strong>
            <p>仅演示评分映射 · 不构成仓位建议</p>
          </article>
        </div>
      </section>

      <section className="history-section">
        <div className="section-title">
          <div><p className="eyebrow">DAILY ARCHIVE</p><h2>每日评分记录</h2></div>
          <div className="range-tabs" aria-label="选择历史范围">
            {([7, 30, 90] as const).map((days) => <button className={range === days ? "active" : ""} onClick={() => setRange(days)} key={days}>{days}日</button>)}
          </div>
        </div>
        <div className="history-card">
          <div className="chart-head"><span>综合评分趋势</span><small>点击柱形查看当日明细</small></div>
          <div className="bar-chart" role="list" aria-label="每日综合评分图">
            {chronological.map((row) => <button key={row.asOfDate} className={row.asOfDate === selectedDate ? "selected" : ""} onClick={() => setSelectedDate(row.asOfDate)} role="listitem" aria-label={`${row.asOfDate} 综合评分 ${row.comprehensiveScore}`}>
              <span className="bar-value">{row.comprehensiveScore.toFixed(0)}</span>
              <i style={{ height: `${Math.max(row.comprehensiveScore, 8)}%` }} />
              <small>{formatDate(row.asOfDate)}</small>
            </button>)}
            {chronological.length === 1 && <div className="empty-history"><b>从今天开始积累</b><span>采集器每天收盘后覆盖当日记录，不生成虚假历史。</span></div>}
          </div>
        </div>
      </section>

      <section className="detail-grid">
        <article className="factor-card">
          <div className="card-heading"><span>战略估值与技术因子</span><b>70% 权重</b></div>
          <div className="factor-list">
            {factorRows.map(([label, value, unit, score]) => <div className="factor-row" key={label}>
              <span>{label}</span><strong>{Number(value).toFixed(2)}{unit}</strong>
              <div><i style={{ width: `${score}%` }} /></div><small>{score.toFixed(0)} 分</small>
            </div>)}
          </div>
        </article>
        <article className="tactical-card">
          <div className="card-heading"><span>盘中战术读数</span><b>30% 权重</b></div>
          <div className="metric-tiles">
            <div><span>VWAP 偏离</span><strong>{Number(current.diagnostics.vwap_deviation_pct).toFixed(2)}%</strong><small>价格相对盘中均价的偏离</small></div>
            <div><span>相对异常</span><strong>{Number(current.diagnostics.relative_change_pct).toFixed(2)}%</strong><small>相对基准的强弱差异</small></div>
            <div><span>1分钟 RSI14</span><strong>{Number(current.diagnostics.intraday_rsi14 ?? current.diagnostics.rsi14).toFixed(1)}</strong><small>盘中动量，仅用于战术层</small></div>
            <div><span>超跌调整项</span><strong>+{current.oversoldBonus.toFixed(0)}</strong><small>放量下跌时不计入</small></div>
            <div><span>估算 IOPV</span><strong>{Number(current.diagnostics.iopv ?? current.lastPrice).toFixed(4)}</strong><small>由富途折溢价反推</small></div>
            <div><span>实时折溢价</span><strong>{Number(current.diagnostics.premium_pct ?? 0).toFixed(3)}%</strong><small>负值表示折价</small></div>
            <div><span>ETF 总份额</span><strong>{(Number(current.diagnostics.fund_shares ?? 0) / 1e8).toFixed(2)}亿</strong><small>每日记录用于识别申赎</small></div>
            <div><span>份额变化</span><strong>{Number(current.diagnostics.fund_share_change_pct ?? 0).toFixed(2)}%</strong><small>相对上一有效记录</small></div>
          </div>
        </article>
      </section>

      <section className="quality-section">
        <div className="quality-score"><span>数据可信度</span><strong>{current.dataQuality}<small>/100</small></strong><p>按来源等级、数据新鲜度和字段完整度动态计算</p>
          <div className="quality-breakdown"><i>完整 {Number(quality.completeness ?? 0).toFixed(0)}</i><i>时效 {Number(quality.freshness ?? 0).toFixed(0)}</i><i>来源 {Number(quality.source_quality ?? 0).toFixed(0)}</i></div>
        </div>
        <div className="source-list">
          {VERIFIED_SOURCES.map((source) => <div key={source.name}><i className={source.tone} /><span><b>{source.name}</b><small>{source.role}</small></span><em>{source.grade}</em></div>)}
        </div>
        <div className="quality-note">
          <b>本日数据说明</b>
          <p>10年期国债采用中债官方最近有效日。PE/PB 使用 {String(current.diagnostics.valuation_proxy ?? "SH.000922")} 红利指数代理的十年历史，共 {Number(current.diagnostics.valuation_history_count ?? 0).toFixed(0)} 个交易日；精确标普指数估值暂无公开实时接口，因此不会标记为官方精确值。</p>
        </div>
      </section>

      <section className="decision-section" aria-labelledby="decision-title">
        <div className="decision-intro">
          <p className="eyebrow">SCORE INTERPRETATION</p>
          <h2 id="decision-title">分数区间状态说明</h2>
          <p>分数只用于描述模型在对应维度上的相对状态，不是对未来价格或收益的预测，也不对应任何必须采取的交易动作。使用前应先核验来源日期、字段完整度与数据可信度。</p>
        </div>
        <div className="decision-grid">
          {DECISION_GUIDES.map((guide) => {
            const value = current[guide.key];
            const activeBand = decisionBandIndex(value, guide.thresholds);
            return <article className="decision-card" key={guide.key}>
              <div className="decision-card-head">
                <span>{guide.title}</span><strong>{value.toFixed(1)}</strong>
              </div>
              <p>{guide.note}</p>
              <ol>
                {guide.bands.map((band, index) => <li className={index === activeBand ? "active" : ""} key={band}>
                  <i /> <span>{band}</span>{index === activeBand && <b>当前</b>}
                </li>)}
              </ol>
            </article>;
          })}
        </div>
        <div className="decision-rules">
          <b>阅读提示</b>
          <span>优先查看数据可信度</span>
          <span>结合各维度，不只看综合分</span>
          <span>核对数据源与更新时间</span>
          <span>模型结果可能失真或失效</span>
        </div>
      </section>

      <footer><span>双层评分模型 v0.3</span><p>非商业研究工具 · 不收费、不接受打赏、不提供会员提醒或交易导流 · 不构成任何投资建议。</p><a href="https://www.spglobal.com/spdji/en/indices/dividends-factors/sp-china-a-share-largecap-low-volatility-high-dividend-50-index/" target="_blank" rel="noreferrer">标的指数资料 ↗</a></footer>
    </main>
  );
}
