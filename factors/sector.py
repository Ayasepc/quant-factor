"""
板块轮动因子
基于板块分类计算相对强弱，捕捉板块轮动效应

因东方财富/同花顺行业成分股接口受限，使用以下替代方案:
1. SectorBoardMomentum — 按交易板块粗分类（沪主板/深主板/创业板等）计算动量
2. SectorIndexMomentum — 同花顺行业指数动量（行业级别，所有股票共享同一行业得分）
"""

import pandas as pd
import numpy as np
import time
from factors import BaseFactor


class SectorBoardMomentum(BaseFactor):
    """
    板块动量因子（按交易板块分类）

    将股票分为5大板块，计算各板块相对强弱:
    - 沪市主板 (600xxx)
    - 深市主板/中小板 (000xxx, 002xxx)
    - 创业板 (300xxx)
    - 科创板 (688xxx)

    板块内个股获得相同的板块动量得分。
    当资金在板块间流动时，该因子能捕捉到板块轮动。
    """

    def __init__(self, lookback: int = 20):
        super().__init__(
            name=f"BoardMom{lookback}D",
            category="sector",
            direction=1,
        )
        self.lookback = lookback

    @staticmethod
    def _get_board(code: str) -> str:
        if code.startswith("688"):
            return "STAR"         # 科创板
        elif code.startswith("6"):
            return "SH_Main"      # 沪市主板
        elif code.startswith("3"):
            return "ChiNext"      # 创业板
        elif code.startswith("0"):
            return "SZ_Main"      # 深市主板
        elif code.startswith("2"):
            return "SME"          # 中小板
        return "Other"

    def calculate(self, price_df: pd.DataFrame, fin_df=None) -> pd.Series:
        df = price_df.sort_values(["stock_code", "date"]).copy()
        df["board"] = df["stock_code"].apply(self._get_board)

        # 计算个股收益率
        df["stock_ret"] = df.groupby("stock_code")["close"].transform(
            lambda x: x.pct_change(self.lookback)
        )

        latest = df[df["date"] == df["date"].max()].copy()
        # 计算各板块平均收益
        board_ret = latest.groupby("board")["stock_ret"].mean()

        # 用板块均值 > 全市场均值来区分"热门"vs"冷门"板块
        market_avg = latest["stock_ret"].mean()
        board_factor = (board_ret - market_avg).to_dict()

        # 给每个股票赋板块得分
        latest["factor"] = latest["board"].map(board_factor)
        result = latest.set_index("stock_code")["factor"].dropna()
        return result


class SectorIndexMomentum(BaseFactor):
    """
    同花顺行业指数动量因子

    直接使用同花顺行业指数历史数据计算各行业动量，
    作为资金流向的代理指标。
    所有股票共享行业动量得分 - 这是一个市场层面的因子。

    注: 由于获取所有个股的行业映射需要大量API调用，
    当前实现为市场整体行业轮动强度信号。
    """

    def __init__(self, top_n: int = 5):
        super().__init__(
            name=f"SectorRotation",
            category="sector",
            direction=1,
        )
        self.top_n = top_n

    def calculate(self, price_df: pd.DataFrame, fin_df=None) -> pd.Series:
        import akshare as ak

        try:
            industries = ak.stock_board_industry_name_ths()
            ind_list = industries["name"].tolist()
        except Exception:
            return pd.Series(dtype=float)

        # 计算各行业指数近期收益
        sector_rets = {}
        for ind in ind_list[:50]:  # 取前50个行业
            try:
                idx_df = ak.stock_board_industry_index_ths(symbol=ind)
                if idx_df.empty:
                    continue
                idx_df["date"] = pd.to_datetime(idx_df["date"])
                idx_df = idx_df.sort_values("date")
                close_col = "收盘价" if "收盘价" in idx_df.columns else "close"
                prices = idx_df[close_col].values
                if len(prices) >= 21:
                    ret_1m = prices[-1] / prices[-21] - 1  # 1月动量
                    sector_rets[ind] = ret_1m
                time.sleep(0.25)
            except Exception:
                continue

        if len(sector_rets) < 5:
            return pd.Series(dtype=float)

        # 计算标准差作为轮动强度
        rets = list(sector_rets.values())
        rotation = float(np.std(rets)) * 100  # 放大到易读范围

        all_codes = price_df["stock_code"].unique()
        return pd.Series(rotation, index=all_codes, name=self.name)

