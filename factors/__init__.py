"""因子基类 - 所有因子需继承此类"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class BaseFactor(ABC):
    """因子基类"""

    def __init__(self, name: str, category: str, direction: int = 1):
        """
        Args:
            name: 因子名称
            category: 因子类别 (valuation/quality/growth/momentum/risk/liquidity)
            direction: 因子方向, 1=越大越好, -1=越小越好
        """
        self.name = name
        self.category = category
        self.direction = direction

    @abstractmethod
    def calculate(self, price_df: pd.DataFrame, fin_df: pd.DataFrame = None) -> pd.Series:
        """
        计算因子值

        Args:
            price_df: 日线行情 DataFrame (含 date, stock_code, close, volume...)
            fin_df:   财务数据 DataFrame (可选)

        Returns:
            因子值 Series, index=stock_code
        """
        ...

    def neutralize(self, factor_values: pd.Series, market_cap: pd.Series = None) -> pd.Series:
        """
        因子中性化处理 (可选，子类可覆盖)
        默认不做处理
        """
        return factor_values

    def standardize(self, factor_values: pd.Series) -> pd.Series:
        """
        Z-score 标准化
        """
        vals = factor_values.copy()
        mean, std = vals.mean(), vals.std()
        if std == 0:
            return pd.Series(0, index=vals.index)
        vals = (vals - mean) / std
        # 截断 ±3σ 去极值
        vals = vals.clip(-3, 3)
        return vals

    def winsorize(self, factor_values: pd.Series, limits: tuple = (0.01, 0.01)) -> pd.Series:
        """
        极值处理: 缩尾 (winsorization)
        """
        vals = factor_values.copy()
        lower, upper = vals.quantile(limits[0]), vals.quantile(1 - limits[1])
        vals = vals.clip(lower, upper)
        return vals
