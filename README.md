# 515450 红利低波50ETF 实时评分系统

这是一个可运行的 Python 项目，用双层引擎为 `SH.515450` 输出五类结果：综合评分、买入信号、卖出信号、日内 T 信号和建议仓位。系统只做行情分析与信号输出，不会下单。

> 评分是规则模型，不构成投资建议。每个静态字段都保存来源日期；过期或抓取失败时会降低“数据可信度”，不会静默冒充实时数据。

## 网页仪表板

网页位于 `web/`，提供当前评分、每日历史、战略/战术拆分、因子明细和数据来源状态。历史记录以交易日期为唯一键：盘中可持续覆盖当日记录，跨日后自动新增一天。

```powershell
cd web
npm install
npm run dev
```

打开 `http://localhost:3000`，再从项目根目录启动本地 Futu 采集同步：

```powershell
$env:PYTHONPATH = "src"
python -m dividend_etf_score.sync --site-url http://localhost:3000
```

只记录一次：

```powershell
python -m dividend_etf_score.sync --site-url http://localhost:3000 --once
```

网页使用持久化 SQLite/D1 历史库，不使用浏览器临时存储。若同步到受保护的云端站点，可通过 `OAI_SITES_BYPASS_TOKEN` 提供站点授权；不要把令牌写入配置文件或代码仓库。

## 工作方式

- 战略引擎：默认每日 15:05 进入新的收盘周期并刷新缓存，覆盖 10 年期国债收益率、股债利差、ERP、PB/PE 历史百分位、股息率、日线 RSI14、长期趋势和市场环境。日线 RSI14 采用复权日 K，并与富途口径校验。
- 战术引擎：默认每 30 秒重新读取最新价、分钟 K 线、成交量/额、盘口和 VWAP，计算 MA、EMA、MACD、1 分钟 RSI14、KDJ、BOLL、ATR、波动率以及相对基准异常。
- Futu 优先：`source: auto` 会先连接 Futu OpenD，连接失败则自动切换到可重复测试的模拟行情。
- 超跌奖励：价格低于日线 MA20 时逐级加分，但放量超过阈值时不奖励，避免把异常放量下跌简单视作机会。

当前评分合成：

```text
综合评分 = 战略评分 × 70% + 战术评分 × 30%
```

因子权重、阈值、奖励和仓位档位都可在 `config.yaml` 中调整。

## 安装

建议使用 Python 3.10–3.13；Futu SDK 在非常新的 Python 版本上可能尚未完全适配。

```powershell
cd C:\path\to\515450_realtime_scoring
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[futu,test]"
```

若只使用模拟行情，可不安装 Futu SDK：

```powershell
pip install -e ".[test]"
```

## 配置 Futu OpenD

1. 安装并启动 Futu OpenD，建议版本不低于 `10.4.6408`。
2. 在 OpenD 中登录，并确认拥有 A 股行情权限。
3. 默认连接地址是 `127.0.0.1:11111`。如果不同，可直接修改 `config.yaml`，或设置：

```powershell
$env:FUTU_OPEND_HOST = "127.0.0.1"
$env:FUTU_OPEND_PORT = "11111"
```

项目会订阅主标的的 `QUOTE`、`ORDER_BOOK`、`RT_DATA`、`K_1M`、`K_DAY`，并为沪深 300 和中证红利订阅 `QUOTE`。若盘口不可用，它会安全降级为空值；若主报价或 K 线不可用，`auto` 模式会切换到模拟源。

## 运行

先用模拟数据验证：

```powershell
etf-score --source mock --cycles 3 --interval 1
```

连接 Futu，默认每 30 秒刷新：

```powershell
etf-score --source futu
```

优先 Futu、失败自动模拟：

```powershell
etf-score --source auto
```

只运行一次并输出 JSON：

```powershell
etf-score --source mock --once --json
```

不安装项目也能从项目根目录运行：

```powershell
$env:PYTHONPATH = "src"
python -m dividend_etf_score.cli --source mock --once
```

## 自动估值、份额与可信度数据

Futu 通常不能完整提供 10 年期国债收益率、指数级股息率、ETF 对应指数的 E/P 和可靠的长期估值分位，因此它们由可插拔接口提供。

默认 `trusted_composite` 会自动刷新：

- 中债官方最近工作日的10年期国债收益率。
- Futu `SH.000922` 中证红利指数10年PE/PB历史、当前估值和历史分位（当前可返回约2423个交易日）。
- 盈利收益率由实时PE自动计算：`E/P = 100 / PE`。
- 沪深300和中证红利日K趋势、相对强弱及515450波动率共同生成每日市场环境分。
- Futu基金折溢价，并反推估算IOPV。
- 腾讯实时市值/价格与东方财富ETF总份额交叉查询；每日写入 `data/fund_shares_history.csv`，计算份额变化。

```yaml
as_of: "2026-08-06"
bond_10y_yield_pct: 1.7143
dividend_yield_pct: 5.20
earnings_yield_pct: 7.10  # 自动源失败时的回退值
pb_percentile_pct: 28.0  # 自动源失败时的回退值
pe_percentile_pct: 32.0  # 自动源失败时的回退值
market_environment_score: 62.0  # 自动计算失败时的回退值
source_note: "数据来源与口径说明"
```

当前来源分层：

- 行情、K 线、盘口：Futu OpenD；腾讯财经只作为可扩展的交叉校验备用源。
- 10 年期国债：中央国债登记结算有限责任公司编制的中债国债收益率曲线，工作日日终发布。
- 标的指数与方法：S&P China A-Share LargeCap Low Volatility High Dividend 50 Index 官方资料。
- 基金身份与风险披露：上海证券交易所基金公告。
- PE/PB分位：Futu中证红利10年估值历史代理。515450跟踪的标普指数暂无公开实时估值接口，系统会固定扣除“精确性”分并明确显示代理口径。
- 指数股息率：自动复核带发布日期的公开值；无法取得新的可信发布值时沿用上次值和原始日期，不会伪装成当天数据。

可信度不再使用固定分数，而是逐字段计算：`40%完整性 + 30%时效性 + 30%来源等级 - 精确性扣分`。网页同时展示三项子分、缺失字段和估值代理说明。

所有收益率用“百分数”填写，例如 `1.75` 表示 1.75%。系统自动计算：

```text
股债利差 = 股息率 - 10 年期国债收益率
ERP = 盈利收益率(E/P) - 10 年期国债收益率
```

接入数据库、HTTP API 或内部服务时，实现 `StaticFactorProvider.load()`，并在 `build_static_provider()` 注册即可。建议每日收盘后由计划任务更新源数据，同时保留 `as_of` 和 `source_note` 以便审计。

## 评分含义

- 综合评分：长期配置价值与当下交易时机的合成。
- 买入信号：战略价值为主，结合盘中超跌、VWAP 和相对异常。
- 卖出信号：战略价值偏低且出现 RSI/VWAP/日内涨幅过热时升高。
- 日内 T 信号：聚焦 VWAP 负偏离、相对基准超跌、日内跌幅和盘口失衡。
- 仓位建议：由综合评分映射到配置档位，默认最高 90%，保留现金缓冲。

买入信号与卖出信号不是简单互补：长期价值高但盘中快速拉升时，两者可能同时处于中位区间。

## 测试

```powershell
pytest -q
```

测试覆盖技术指标生成、VWAP、评分边界、模拟行情变化、战略评分日内缓存和可信度分解。

## 项目结构

```text
config.yaml                         权重、阈值、标的和 OpenD 配置
data/static_factors.yaml            自动源失败时的可审计回退因子
data/fund_shares_history.csv        ETF份额每日历史与申赎变化基线
src/dividend_etf_score/
  data_sources.py                   Futu 与模拟行情接口
  indicators.py                     全部技术指标
  static_data.py                    可插拔静态因子接口
  scoring.py                        战略、战术与五类输出
  engine.py                         双层刷新与缓存逻辑
  cli.py                            CLI
tests/                              基本测试
```

## 已知边界

- `SH.000922` 是默认“中证红利”相对基准，可在配置中换成你实际使用且 Futu 支持的红利指数代码。
- 分钟 VWAP 由分钟典型价格与成交量估算；若需要逐笔级 VWAP，可扩展数据源订阅 `TICKER`。
- 战略层当前在进程内按 `strategic_refresh_time`（默认 15:05）切换每日收盘周期，也可调用 `refresh_strategic(force=True)`；若要跨进程持久化，可增加 SQLite/Redis 缓存。
- 标普精确指数估值仍需S&P授权数据、Wind或Choice；当前中证红利代理不会被标记为官方精确值。
