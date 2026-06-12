# 📊 A股多因子选股系统

基于 **多因子模型** 的 A 股量化选股框架，支持基本面因子 + 技术/动量因子联合分析、IC 有效性检验、多因子合成选股、组合回测及可视化。

---

## 📋 目录

- [框架概览](#框架概览)
- [数据源](#数据源)
- [安装](#安装)
- [快速开始](#快速开始)
- [模块详解](#模块详解)
- [因子库](#因子库)
- [实盘跟踪](#实盘跟踪)
- [自定义扩展](#自定义扩展)
- [常见问题](#常见问题)

---

## 框架概览

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  数据获取    │ →  │  因子计算    │ →  │  因子分析    │ →  │  多因子合成   │
│  akshare     │    │  15个因子    │    │  IC/分组收益 │    │  等权/IC加权  │
│  新浪/东方   │    │  基本面/动量 │    │  有效性检验  │    │  打分法选股   │
└─────────────┘    └─────────────┘    └──────────────┘    └──────────────┘
                                                                    │
                                                                    ▼
                                                              ┌──────────────┐
                                                              │  组合回测     │
                                                              │  可视化报告   │
                                                              │  实盘跟踪     │
                                                              └──────────────┘
```

### 核心流程

1. **数据准备** → 获取 A 股日线行情 + 财务指标数据
2. **因子计算** → 计算每个因子在所有股票截面上的值
3. **因子测试** → IC 分析、分组收益检验因子有效性
4. **因子合成** → 多个有效因子组合成综合评分
5. **选股推荐** → 按综合评分排序，输出 Top N 股票

---

## 数据源

本项目使用 **AKShare**（免费开源 Python 库）获取数据，无需 API Key 或付费订阅。

| 数据类型 | 接口 | 源站 | 说明 |
|---------|------|------|------|
| **日线行情** | `ak.stock_zh_a_daily()` | **新浪财经** | 前复权，含开高低收、成交量、换手率 |
| **股票列表** | `ak.stock_info_a_code_name()` | 交易所 | A 股全量股票代码与名称 |
| **财务指标** | `ak.stock_financial_abstract()` | 新浪财经 | 季度 ROE、ROA、毛利率、净利率、EPS、BVPS、营收/利润增长率 |

> **注意：** 新浪财经接口在中国大陆可直接访问。如果遇到东方财富接口 (`stock_zh_a_hist`) 连接失败，系统会自动回退到新浪接口。

---

## 安装

### 环境要求
- Python ≥ 3.8
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install pandas numpy matplotlib seaborn scipy statsmodels akshare openpyxl tqdm pyarrow
```

### 验证安装

```bash
python -c "import akshare; print(f'AKShare v{akshare.__version__} ✅')"
```

---

## 快速开始

### 1. 全流程运行（推荐）

```bash
python factor_pipeline.py --mode full_pipeline
```

一键完成：获取数据 → 计算所有因子 → IC 测试 → 多因子合成 → 选股推荐

输出示例：
```
============================================================
  因子有效性测试
============================================================
  PE_TTM          | IC=-0.1224 | IR=-0.3975 | 期数=40  ★
  ROE             | IC=+0.0486 | IR=0.1462  | 期数=40
  Turn20D         | IC=-0.1802 | IR=-0.6806 | 期数=40  ★

============================================================
  综合选股推荐 (2026-06-12)
============================================================
    排名       股票代码       综合得分
  ----------------------------
     1     600919     0.6964
     2     601009     0.6721
     3     000001     0.6640
```

### 2. 测试单个因子

```bash
python factor_pipeline.py --mode test_single --factor pe_ttm
```

可选因子：`pe_ttm`, `pb`, `roe`, `roe`, `momentum_1m`, `turnover_20d` 等（完整列表见 [因子库](#因子库)）

### 3. 生成可视化报告

```bash
python run_analysis.py
```

在 `charts/` 目录生成 5 张图表：

| 文件 | 内容 |
|------|------|
| `01_ic_timeseries.png` | 各因子 IC 时间序列（看因子稳定性） |
| `02_group_returns.png` | 分组累计收益图（看因子区分度） |
| `03_factor_correlation.png` | 因子相关性热力图（防范多重共线性） |
| `04_top15_stocks.png` | 综合评分 Top15 排行 |
| `05_dashboard.png` | 综合面板（IC对比、多空收益、得分分布） |

### 4. 个股分析

```bash
python analyze_601390.py
```

获取并分析中国中铁（601390）的股价走势、回撤、月度收益热力图。

### 5. 实盘跟踪

```bash
python track.py
```

输出最新一期选股推荐、因子有效性、历史对比。结果保存到 `tracking_result.json` 和 `tracking_history.csv`。

---

## 模块详解

### 📁 项目结构

```
quant-factor/
├── config.py              # 配置文件
├── data_fetcher.py        # 数据获取模块
├── factor_pipeline.py     # 全流程管道
├── analyzer.py            # 因子分析器
├── multi_factor.py        # 多因子模型
├── track.py               # 实盘跟踪脚本
├── run_analysis.py        # 可视化分析脚本
├── analyze_601390.py      # 个股分析示例
├── quick_check.py         # 快捷速查脚本
├── retry_june.py          # 数据重试脚本
├── requirements.txt       # 依赖清单
│
├── factors/               # 因子定义
│   ├── __init__.py        # 因子基类 (BaseFactor)
│   ├── fundamental.py     # 基本面因子
│   └── momentum.py        # 动量与技术因子
│
├── examples/
│   └── tutorial_01_intro.ipynb   # 入门教程 Jupyter
│
├── charts/                # 输出图表目录
│
└── data/                  # 缓存数据目录
```

### `config.py` — 配置中心

所有回测参数和因子清单集中管理：

```python
BACKTEST_CONFIG = {
    "start_date": "2023-01-01",    # 回测起始日
    "end_date": "2026-06-12",      # 回测结束日
    "rebalance_freq": "monthly",   # 调仓频率
    "group_num": 10,               # 分组数量（十分位）
    "benchmark": "000300.SH",      # 基准指数（沪深300）
}

UNIVERSE_CONFIG = {
    "min_market_cap": 1e9,          # 最小市值 10亿
    "exclude_ST": True,             # 排除ST股票
    "exclude_new_stock_days": 60,   # 排除次新股
}

FACTOR_CONFIG = {
    "pe_ttm": {"name": "PE_TTM", "category": "valuation", "direction": -1},
    "roe":    {"name": "ROE",    "category": "quality",   "direction": 1},
    # ... 完整因子清单见下方
}
```

- `direction: 1` 因子值越大越好（正向因子）
- `direction: -1` 因子值越小越好（负向因子，如 PE）

### `data_fetcher.py` — 数据获取

核心类 `AStockDataFetcher`，负责：

- **行情数据**：`get_daily_price(code, start, end)` → 个股日线（新浪接口）
- **批量获取**：`get_all_daily_price(start, end, stock_list)` → 多只股票并发
- **财务数据**：`enrich_with_financial_data(price_df)` → 合并财务指标到行情
- **股票池**：`get_universe(date)` → 全 A 股（排除北交所）

#### 财务数据增强

```python
fetcher = AStockDataFetcher()
price_df = fetcher.get_all_daily_price("2023-01-01", "2026-06-12", stock_list)
price_df = fetcher.enrich_with_financial_data(price_df)
# 新增列: roe, roa, gross_margin, net_margin, eps_ttm, bvps, pe_ttm, pb, revenue_yoy, profit_yoy
```

数据通过 `merge_asof` 前向填充：每个交易日取最近一期的季度财务数据。

### `factors/` — 因子定义

所有因子继承 `BaseFactor` 基类：

```python
class BaseFactor(ABC):
    def calculate(self, price_df, fin_df=None) -> pd.Series:
        """计算因子值，返回 stock_code → 因子值"""
    def standardize(self, factor_values) -> pd.Series:  # Z-score标准化
    def winsorize(self, factor_values) -> pd.Series:     # 缩尾去极值
    def neutralize(self, factor_values) -> pd.Series:    # 中性化（可选）
```

#### 基本面因子 (`factors/fundamental.py`)

| 因子 | 类名 | 类别 | 方向 | 数据来源 |
|------|------|------|------|---------|
| 市盈率 TTM | `PE_TTM` | valuation | ↓ | 财务摘要 → EPS_TTM + 收盘价计算 |
| 市净率 | `PB` | valuation | ↓ | 财务摘要 → BVPS + 收盘价计算 |
| 市销率 TTM | `PS_TTM` | valuation | ↓ | 财务摘要（需额外数据） |
| 净资产收益率 | `ROE` | quality | ↑ | 财务摘要直接提供 |
| 总资产收益率 | `ROA` | quality | ↑ | 财务摘要直接提供 |
| 毛利率 | `GrossMargin` | quality | ↑ | 财务摘要直接提供 |
| 净利率 | `NetMargin` | quality | ↑ | 财务摘要直接提供 |
| 营收增长率 | `RevenueGrowth` | growth | ↑ | 财务摘要同比计算 |
| 净利润增长率 | `ProfitGrowth` | growth | ↑ | 财务摘要同比计算 |

#### 动量 & 技术因子 (`factors/momentum.py`)

| 因子 | 类名 | 类别 | 方向 | 计算方法 |
|------|------|------|------|---------|
| 1月动量 | `Momentum1M` | momentum | ↑ | 过去20日收益率 |
| 3月动量 | `Momentum3M` | momentum | ↑ | 过去60日收益率 |
| 6月动量 | `Momentum6M` | momentum | ↑ | 过去120日收益率（Jegadeesh & Titman 1993） |
| 20日波动率 | `Volatility20D` | risk | ↓ | 日收益率20日滚动标准差 |
| 20日换手率 | `Turnover20D` | liquidity | ↓ | 换手率20日均值 |
| 60日 Alpha | `Alpha60D` | momentum | ↑ | 个股超额收益（相对等权市场） |

### `analyzer.py` — 因子分析

核心类 `FactorAnalyzer`：

- **IC 分析**：`calc_ic(factor_matrix, forward_returns)` → 每期因子与未来收益的 Pearson 相关系数
- **Rank IC**：`calc_rank_ic()` → Spearman 秩相关系数（对极端值更稳健）
- **分组收益**：`calc_group_returns()` → 按因子值分 10 组，看每组表现
- **综合报告**：`full_report()` → IC 均值、ICIR、分组收益、多空组合

### `multi_factor.py` — 多因子模型

核心类 `MultiFactorModel`：

- **等权合成**：`combine_equal_weight()` → 每个因子分位数打分后取平均
- **IC 加权**：`combine_ic_weight(ic_values)` → 按 IC 大小分配权重
- **选股**：`select_top(scores, top_n)` → 每期选得分最高的 N 只
- **回测**：`backtest(selections, returns)` → 简易组合回测（含佣金）

---

## 因子评价指标

| 指标 | 含义 | 判定标准 |
|------|------|---------|
| **IC** | 因子与未来收益的相关系数 | `|IC| > 0.02` 有选股能力 |
| **ICIR** | IC 均值 / IC 标准差 | `ICIR > 0.3` 因子稳定 |
| **Rank IC** | Spearman 秩相关 | 对极端值不敏感 |
| **分组收益** | 按因子值分 10 组 | 最好单调递增/递减 |
| **多空收益** | Group10 - Group1 | 正向持续说明因子有效 |

---

## 实盘跟踪

### 手动运行

```bash
python track.py
```

输出摘要：
- 最新因子 IC 值（带星级标记，`★` = `|IC| > 0.08`）
- 多因子综合选股 Top 10
- 因子有效性统计

### 自动运行

系统已配置每周一 8:35 AM 自动运行（可通过 `.claude/scheduled_tasks.json` 查看）。

### 历史记录

每次运行结果追加到 `tracking_history.csv`：

```csv
date,top1,top1_score,valid_factors
2026-06-12,600919,0.6964,13
```

---

## 自定义扩展

### 添加新因子

1. 在 `factors/` 下创建新文件，继承 `BaseFactor`：

```python
from . import BaseFactor

class MyFactor(BaseFactor):
    def __init__(self):
        super().__init__(name="MyFactor", category="momentum", direction=1)

    def calculate(self, price_df, fin_df=None):
        # 实现因子计算逻辑
        return result_series
```

2. 在 `factor_pipeline.py` 的 `factor_registry` 中注册：

```python
self.factor_registry = {
    ...
    "my_factor": MyFactor(),
}
```

3. （可选）在 `config.py` 的 `FACTOR_CONFIG` 中添加配置

### 修改股票池

编辑 `factor_pipeline.py` 的 `prepare_data()` 方法，替换 `bank_stocks` 列表，或调用 `fetcher.get_universe()` 获取全 A 股。

### 切换数据源

编辑 `data_fetcher.py` 的 `get_daily_price()` 方法：
- 新浪接口（默认）：`ak.stock_zh_a_daily()`
- 东方财富接口：`ak.stock_zh_a_hist()`
- 其他：接入 TuShare、JoinQuant 等

---

## 常见问题

### Q: 出现 `ConnectionError` 无法获取数据？
某些 API 端点（如东方财富）在中国大陆外可能被限制。系统会自动回退到新浪接口，如果仍有问题，请尝试使用 VPN 或代理。

### Q: 如何扩大股票池？
当前演示使用 20 只银行股。要分析全 A 股，修改 `factor_pipeline.py`：

```python
# 替换 prepare_data 中的 bank_stocks
sample = self.fetcher.get_universe()  # 全A股，5200+只
# 然后使用前 N 只
sample = sample[:200]  # 取前200只
```

### Q: PS_TTM 和 ROA 因子为什么失败？
部分财务指标在某些行业（如银行）中空缺。银行股 ROA 极低，PS 无意义，这些因子在特定行业自然无效，属于正常现象。

### Q: 数据缓存在哪里？
所有数据缓存在 `data/` 目录（Parquet 格式）。删除该目录可强制重新获取。

### Q: 为什么使用 `merge_asof` 前向填充财务数据？
财务数据是季度发布的，但每天都需要因子值。`merge_asof(direction='backward')` 确保每个交易日使用最近一期的财务数据，避免了未来信息（look-ahead bias）。

---

## 免责声明

本项目仅用于**学习和研究目的**，不构成任何投资建议。量化模型存在过拟合风险，历史表现不代表未来收益。股市有风险，投资需谨慎。

---

## License

MIT
