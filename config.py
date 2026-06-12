"""A股因子选股系统配置"""

# 回测参数
BACKTEST_CONFIG = {
    "start_date": "2020-01-01",
    "end_date": "2025-12-31",
    "rebalance_freq": "monthly",  # 调仓频率
    "group_num": 10,              # 分组数量 (十分位)
    "benchmark": "000300.SH",     # 基准: 沪深300
}

# 股票池筛选
UNIVERSE_CONFIG = {
    "min_market_cap": 1e9,          # 最小市值 (10亿)
    "exclude_ST": True,              # 排除ST股票
    "exclude_new_stock_days": 60,    # 排除上市不足60天
}

# 因子库
FACTOR_CONFIG = {
    # --- 基本面因子 ---
    "pe_ttm": {"name": "PE_TTM", "category": "valuation", "direction": -1},
    "pb": {"name": "PB", "category": "valuation", "direction": -1},
    "ps_ttm": {"name": "PS_TTM", "category": "valuation", "direction": -1},
    "pcf_ttm": {"name": "PCF_TTM", "category": "valuation", "direction": -1},

    "roe": {"name": "ROE", "category": "quality", "direction": 1},
    "roa": {"name": "ROA", "category": "quality", "direction": 1},
    "gross_margin": {"name": "GrossMargin", "category": "quality", "direction": 1},
    "net_margin": {"name": "NetMargin", "category": "quality", "direction": 1},

    "revenue_yoy": {"name": "RevYoY", "category": "growth", "direction": 1},
    "profit_yoy": {"name": "ProfitYoY", "category": "growth", "direction": 1},

    # --- 技术/动量因子 ---
    "momentum_1m": {"name": "Mom1M", "category": "momentum", "direction": 1},
    "momentum_3m": {"name": "Mom3M", "category": "momentum", "direction": 1},
    "momentum_6m": {"name": "Mom6M", "category": "momentum", "direction": 1},
    "volatility_20d": {"name": "Vol20D", "category": "risk", "direction": -1},
    "turnover_20d": {"name": "Turn20D", "category": "liquidity", "direction": -1},
    "alpha_60d": {"name": "Alpha60D", "category": "momentum", "direction": 1},
}
