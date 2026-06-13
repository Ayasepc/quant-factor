"""
宏观/消息面因子
利用可用数据源构建宏观因子，弥补东方财富接口受限的影响

因子清单:
1. USMarketImpact  - 美股/A股联动因子（通过指数数据间接推断）
2. MarketTiming    - 大盘择时因子（市场整体情绪）
3. HotThemeFactor  - 热门主题因子（概念板块）
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from factors import BaseFactor


class MarketTiming(BaseFactor):
    """
    大盘择时因子

    通过市场整体表现判断风险偏好:
    - 大盘上涨时，高beta股票更受益
    - 大盘下跌时，防御型股票更抗跌

    因子值 = 个股近期收益 - 市场近期收益 (类似于Alpha)
    """

    def __init__(self, lookback: int = 20):
        super().__init__(
            name=f"MarketAlpha{lookback}D",
            category="macro",
            direction=1,
        )
        self.lookback = lookback

    def calculate(self, price_df: pd.DataFrame, fin_df=None) -> pd.Series:
        df = price_df.sort_values(["stock_code", "date"]).copy()

        # 计算市场收益（所有股票等权）
        df["stock_ret"] = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(self.lookback)
        )

        market_ret = df.groupby("date")["stock_ret"].transform("mean")

        # 超额收益 = 个股收益 - 市场收益
        df["excess_ret"] = df["stock_ret"] - market_ret

        latest = df[df["date"] == df["date"].max()]
        result = latest.set_index("stock_code")["excess_ret"].dropna()
        return result


class USMarketCorrelation(BaseFactor):
    """
    美股联动因子

    计算美股（通过沪深300与全球指数相关性作为代理）对A股的影响。
    当美股趋势明显时，外资重仓股（大盘蓝筹）受影响更大。

    由于无法直接获取美股数据，使用沪深300走势与市场整体走势的
    背离程度作为「外资情绪」的代理。
    """

    def __init__(self, lookback: int = 20):
        super().__init__(
            name=f"USCorr{lookback}D",
            category="macro",
            direction=1,
        )
        self.lookback = lookback

    def calculate(self, price_df: pd.DataFrame, fin_df=None) -> pd.Series:
        df = price_df.sort_values(["stock_code", "date"]).copy()

        # 沪深300 vs 全市场: 大盘股相对强度
        # 如果沪深300跑赢全市场 → 可能外资流入 → 利好蓝筹
        # 如果沪深300跑输全市场 → 可能外资流出

        # 计算每只股票的收益率
        df["stock_ret"] = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(self.lookback)
        )

        # 全市场平均
        market_ret = df.groupby("date")["stock_ret"].transform("mean")

        # 判断哪些是"蓝筹股"（用市值代理，没有市值用价格*成交量）
        df["value_proxy"] = df["close"] * df["volume"]
        df["is_large"] = df.groupby("date")["value_proxy"].transform(
            lambda x: x > x.quantile(0.8)
        )

        # 大盘股平均收益
        large_ret = df[df["is_large"]].groupby("date")["stock_ret"].transform("mean")

        # 蓝筹超额 = 大盘股收益 - 全市场收益
        df["large_excess"] = large_ret - market_ret

        latest = df[df["date"] == df["date"].max()].copy()
        # 对大盘股赋予正向因子，小盘股负向
        latest["factor"] = latest["large_excess"]
        latest.loc[~latest["is_large"], "factor"] = -latest.loc[~latest["is_large"], "large_excess"].abs() if (~latest["is_large"]).any() else 0

        result = latest.set_index("stock_code")["factor"].dropna()
        return result


class HS300Momentum(BaseFactor):
    """
    沪深300动量因子

    大盘蓝筹趋势跟踪 - 沪深300的近期表现作为市场风向标
    每只股票获得相同的沪深300动量得分（市场系统性因子）
    """

    def __init__(self, lookback: int = 20):
        super().__init__(
            name=f"HS300Mom{lookback}D",
            category="macro",
            direction=1,
        )
        self.lookback = lookback

    def calculate(self, price_df: pd.DataFrame, fin_df=None) -> pd.Series:
        import akshare as ak
        try:
            df = ak.stock_zh_index_daily(symbol="sh000300")
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            prices = df["close"].values
            if len(prices) < self.lookback + 1:
                return pd.Series(dtype=float)

            ret = prices[-1] / prices[-(self.lookback + 1)] - 1
            all_codes = price_df["stock_code"].unique()
            return pd.Series(ret, index=all_codes, name=self.name)
        except Exception:
            return pd.Series(dtype=float)
