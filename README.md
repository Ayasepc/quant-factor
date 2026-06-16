# 📊 A股多因子选股系统

基于 **多因子模型** 的 A 股量化选股框架，支持基本面因子 + 动量因子 + 板块轮动因子 + 宏观因子联合分析、IC 有效性检验、多因子合成选股、增量缓存及可视化。

---

## 📋 目录

- [框架概览](#框架概览)
- [数据源](#数据源)
- [安装](#安装)
- [快速开始](#快速开始)
- [模块详解](#模块详解)
- [因子库（20个因子）](#因子库20个因子)
- [增量缓存机制](#增量缓存机制)
- [实盘跟踪](#实盘跟踪)
- [自定义扩展](#自定义扩展)
- [常见问题](#常见问题)

---

## 框架概览

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  数据获取    │ →  │  因子计算    │ →  │  因子分析    │ →  │  多因子合成   │
│  akshare     │    │  20个因子    │    │  IC/分组收益 │    │  等权/IC加权  │
│  新浪财经    │    │  基本面/动量 │    │  有效性检验  │    │  打分法选股   │
│  增量缓存    │    │  板块/宏观   │    │              │    │              │
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

1. **数据准备** → 增量缓存获取 A 股日线行情 + 财务指标数据
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
| **股票列表** | 新浪财经 API 分页获取 | 新浪财经 | 全 A 股（5206 只），沪市+深市 |
| **财务指标** | `ak.stock_financial_abstract()` | 新浪财经 | 季度 ROE、ROA、毛利率、净利率、EPS、BVPS、营收/利润增长率 |
| **行业分类** | `ak.stock_board_industry_name_ths()` | 同花顺 | 90 个行业板块分类 |
| **行业指数** | `ak.stock_board_industry_index_ths()` | 同花顺 | 行业指数历史数据 |
| **大盘指数** | `ak.stock_zh_index_daily()` | 新浪财经 | 沪深300、上证综指等 |

> **注意：** 新浪/同花顺接口在中国大陆可直接访问。东方财富接口在某些网络环境下可能被限制，系统会自动回退到新浪接口。

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

### 1. 全流程运行

```bash
python factor_pipeline.py --mode full_pipeline
```

一键完成：获取数据 → 计算所有因子 → IC 测试 → 多因子合成 → 选股推荐

### 2. 沪市独立分析

```bash
python analyze_sh.py
```

只分析上海市场（不含科创板），结果保存到 `sh_result.json`。

### 3. 测试单个因子

```bash
python factor_pipeline.py --mode test_single --factor roe
```

可选因子：完整列表见 [因子库](#因子库20个因子)

### 4. 生成可视化报告

```bash
python run_analysis.py
```

在 `charts/` 目录生成 IC 时序、分组收益、相关性热力图、Top15 排行、Dashboard。

### 5. 实盘跟踪

```bash
python track.py
```

### 6. 批量补数据

```bash
python batch_fetch.py              # 获取所有剩余股票
python batch_fetch.py --batch 500  # 只获取500只
```

---

## 模块详解

### 📁 项目结构

```
quant-factor/
├── config.py              # 配置文件
├── data_fetcher.py        # 数据获取（增量缓存）
├── factor_pipeline.py     # 全流程管道
├── analyzer.py            # 因子分析器
├── multi_factor.py        # 多因子模型
├── track.py               # 实盘跟踪脚本
├── analyze_sh.py          # 沪市独立分析
├── batch_fetch.py         # 批量数据获取（断点续传）
├── run_analysis.py        # 可视化分析脚本
├── analyze_601390.py      # 个股分析示例
├── quick_check.py         # 快捷速查脚本
├── requirements.txt       # 依赖清单
│
├── factors/               # 因子定义
│   ├── __init__.py        # 因子基类 (BaseFactor)
│   ├── fundamental.py     # 基本面因子 (9个)
│   ├── momentum.py        # 动量与技术因子 (6个)
│   ├── sector.py          # 板块轮动因子 (2个)
│   └── macro.py           # 宏观因子 (3个)
│
├── examples/
│   └── tutorial_01_intro.ipynb
│
├── charts/                # 输出图表
│
└── data/                  # 缓存数据
    ├── prices/            # 个股日线（增量缓存）
    ├── fin_cache/         # 财务数据缓存
    └── stock_list.parquet # 股票列表
```

### `data_fetcher.py` — 增量缓存机制

核心类 `AStockDataFetcher`，缓存文件 `data/prices/{code}.parquet` 累积存储：

```python
# 第一次：API拉取全量
df = fetcher.get_daily_price("600036", "2026-06-01", "2026-06-10")  # ~0.7s

# 同范围：直接读缓存
df = fetcher.get_daily_price("600036", "2026-06-01", "2026-06-10")  # ~0.2s

# 扩展日期：只拉取增量
df = fetcher.get_daily_price("600036", "2026-06-01", "2026-06-22")  # ~0.5s
# 内部：发现缓存到06-15，只拉06-16~06-22
```

### `factors/` — 20个因子

#### 基本面 (9个)
PE_TTM, PB, PS_TTM, ROE, ROA, GrossMargin, NetMargin, RevenueGrowth, ProfitGrowth

#### 动量/技术 (6个)
Momentum1M, Momentum3M, Momentum6M, Volatility20D, Turnover20D, Alpha60D

#### 板块轮动 (2个) 🆕
SectorBoardMomentum（板块动量）, SectorIndexMomentum（轮动强度）

#### 宏观因子 (3个) 🆕
MarketTiming（大盘择时）, USMarketCorrelation（外资情绪）, HS300Momentum（蓝筹动量）

---

## 增量缓存机制

缓存文件按股票代码独立存储（`data/prices/{code}.parquet`），累积所有历史数据。

### 工作原理

```
请求06-01~06-10 → API拉取 → 存储完整 → 返回
请求06-01~06-10 → 直接读缓存 (0.2s)
请求06-01~06-22 → 发现缓存到06-15 → 只拉06-16~06-22 → 合并返回
```

### 优势
- **更新日期零成本**：后续扩展只需增量获取
- **断点续传**：中断后自动跳过已缓存股票
- **删除缓存**：`rm -rf data/prices/` 后自动全量重拉

---

## 常见问题

### Q: 出现 ConnectionError？
系统会自动回退数据源。如仍有问题请检查网络。

### Q: 如何包含科创板？
修改 `data_fetcher.py` 中 `get_universe()` 移除 `startswith("688")` 过滤。

### Q: 数据缓存在哪里？
- 行情：`data/prices/{code}.parquet`（增量累积）
- 财务：`data/fin_cache/{code}.parquet`
- 列表：`data/stock_list.parquet`
