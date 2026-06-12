"""
基本面因子
估值类: PE_TTM, PB, PS_TTM, PCF_TTM
质量类: ROE, ROA, 毛利率, 净利率
成长类: 营收同比, 利润同比
"""

import pandas as pd
import numpy as np
from . import BaseFactor


# ═══════════════════════════════════════════
# 估值因子 (Valuation)
# ═══════════════════════════════════════════

class PE_TTM(BaseFactor):
    """市盈率 TTM: 市值 / 近12个月净利润"""

    def __init__(self):
        super().__init__(name="PE_TTM", category="valuation", direction=-1)

    def calculate(self, price_df, fin_df=None):
        """
        使用行情数据 + 财务数据计算
        PE = 总市值 / 净利润(TTM)
        """
        if "pe" in price_df.columns:
            return price_df.groupby("stock_code")["pe"].last()
        raise ValueError("缺少 PE 数据，请先获取估值数据")


class PB(BaseFactor):
    """市净率: 市值 / 净资产"""

    def __init__(self):
        super().__init__(name="PB", category="valuation", direction=-1)

    def calculate(self, price_df, fin_df=None):
        if "pb" in price_df.columns:
            return price_df.groupby("stock_code")["pb"].last()
        raise ValueError("缺少 PB 数据")


class PS_TTM(BaseFactor):
    """市销率 TTM: 市值 / 营业收入 TTM"""

    def __init__(self):
        super().__init__(name="PS_TTM", category="valuation", direction=-1)

    def calculate(self, price_df, fin_df=None):
        # 从行情数据获取 PS 估值
        if "ps" in price_df.columns:
            return price_df.groupby("stock_code")["ps"].last()
        raise ValueError("缺少 PS 数据")


# ═══════════════════════════════════════════
# 质量因子 (Quality)
# ═══════════════════════════════════════════

class ROE(BaseFactor):
    """净资产收益率: 净利润 / 净资产
    巴菲特最看重的指标之一
    """

    def __init__(self):
        super().__init__(name="ROE", category="quality", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is not None and "roe" in fin_df.columns:
            return fin_df.groupby("stock_code")["roe"].last()
        raise ValueError("缺少 ROE 数据")


class ROA(BaseFactor):
    """总资产收益率: 净利润 / 总资产"""

    def __init__(self):
        super().__init__(name="ROA", category="quality", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is not None and "roa" in fin_df.columns:
            return fin_df.groupby("stock_code")["roa"].last()
        raise ValueError("缺少 ROA 数据")


class GrossMargin(BaseFactor):
    """毛利率: (营业收入 - 营业成本) / 营业收入"""

    def __init__(self):
        super().__init__(name="GrossMargin", category="quality", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is None:
            raise ValueError("毛利率计算需要财务数据")
        revenue = fin_df.get("revenue", np.nan)
        cost = fin_df.get("cost", np.nan)
        if pd.isna(revenue) or pd.isna(cost) or revenue == 0:
            return np.nan
        return (revenue - cost) / revenue


class NetMargin(BaseFactor):
    """净利率: 净利润 / 营业收入"""

    def __init__(self):
        super().__init__(name="NetMargin", category="quality", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is None:
            raise ValueError("净利率计算需要财务数据")
        profit = fin_df.get("net_profit", np.nan)
        revenue = fin_df.get("revenue", np.nan)
        if pd.isna(profit) or pd.isna(revenue) or revenue == 0:
            return np.nan
        return profit / revenue


# ═══════════════════════════════════════════
# 成长因子 (Growth)
# ═══════════════════════════════════════════

class RevenueGrowth(BaseFactor):
    """营收同比增长率"""

    def __init__(self):
        super().__init__(name="RevYoY", category="growth", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is not None and "revenue_yoy" in fin_df.columns:
            return fin_df.groupby("stock_code")["revenue_yoy"].last()
        raise ValueError("缺少营收增长率数据")


class ProfitGrowth(BaseFactor):
    """净利润同比增长率"""

    def __init__(self):
        super().__init__(name="ProfitYoY", category="growth", direction=1)

    def calculate(self, price_df, fin_df=None):
        if fin_df is not None and "profit_yoy" in fin_df.columns:
            return fin_df.groupby("stock_code")["profit_yoy"].last()
        raise ValueError("缺少净利润增长率数据")
