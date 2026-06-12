"""
动量与技术因子
动量类: N个月收益率
风险类: 波动率
流动性类: 换手率
"""

import pandas as pd
import numpy as np
from . import BaseFactor


class Momentum1M(BaseFactor):
    """1个月动量: 过去20个交易日收益率"""

    def __init__(self):
        super().__init__(name="Mom1M", category="momentum", direction=1)

    def calculate(self, price_df, fin_df=None):
        df = price_df.sort_values("date")
        # 计算每个股票20日收益率
        mom = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(20)
        )
        result = df.groupby("stock_code")[mom.name].last()
        return result.dropna()


class Momentum3M(BaseFactor):
    """3个月动量: 过去60个交易日收益率"""

    def __init__(self):
        super().__init__(name="Mom3M", category="momentum", direction=1)

    def calculate(self, price_df, fin_df=None):
        df = price_df.sort_values("date")
        mom = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(60)
        )
        result = df.groupby("stock_code")[mom.name].last()
        return result.dropna()


class Momentum6M(BaseFactor):
    """6个月动量: 过去120个交易日收益率
    经典 Jegadeesh & Titman (1993) 动量策略
    """

    def __init__(self):
        super().__init__(name="Mom6M", category="momentum", direction=1)

    def calculate(self, price_df, fin_df=None):
        df = price_df.sort_values("date")
        mom = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(120)
        )
        result = df.groupby("stock_code")[mom.name].last()
        return result.dropna()


class Volatility20D(BaseFactor):
    """20日波动率 (风险因子)
    高波动股票通常表现较差 (低风险异象)
    """

    def __init__(self):
        super().__init__(name="Vol20D", category="risk", direction=-1)

    def calculate(self, price_df, fin_df=None):
        df = price_df.sort_values("date")
        vol = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change().rolling(20).std()
        )
        result = df.groupby("stock_code")[vol.name].last()
        return result.dropna()


class Turnover20D(BaseFactor):
    """平均换手率 (流动性因子)
    低换手率 = 流动性溢价
    """

    def __init__(self):
        super().__init__(name="Turn20D", category="liquidity", direction=-1)

    def calculate(self, price_df, fin_df=None):
        if "turnover" not in price_df.columns:
            raise ValueError("缺少换手率数据")
        df = price_df.sort_values("date")
        avg_turn = df.groupby("stock_code")["turnover"].transform(
            lambda x: x.rolling(20).mean()
        )
        result = df.groupby("stock_code")[avg_turn.name].last()
        return result.dropna()


class Alpha60D(BaseFactor):
    """60日Alpha: 相对于等权市场的超额收益
    捕捉个股独立于大盘的表现
    """

    def __init__(self):
        super().__init__(name="Alpha60D", category="momentum", direction=1)

    def calculate(self, price_df, fin_df=None):
        df = price_df.sort_values(["date", "stock_code"]).copy()

        # 计算市场收益 (等权)
        market_ret = df.groupby("date")["close"].apply(
            lambda x: x.pct_change().mean()
        ).reset_index()
        market_ret.columns = ["date", "market_ret"]

        # 计算个股收益
        df["stock_ret"] = df.groupby("stock_code")["close"].transform("pct_change")

        # 合并
        df = df.merge(market_ret, on="date")

        # 滚动回归: 个股收益 ~ 市场收益
        # Alpha = 截距项 × 60
        def calc_alpha(group):
            if len(group) < 30:
                return np.nan
            y = group["stock_ret"].values
            x = group["market_ret"].values
            # 简单方法: Alpha = mean(超额收益)
            excess = y - x
            return np.mean(excess[-60:]) if len(excess) >= 60 else np.mean(excess)

        alpha = df.groupby("stock_code").apply(calc_alpha)
        return alpha.dropna()
