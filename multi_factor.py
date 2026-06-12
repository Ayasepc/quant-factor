"""
多因子选股模型
支持:
1. 等权合成
2. IC加权合成 (ICIR加权)
3. 打分法 (分位数打分)
4. 组合优化 (风险调整)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Union, Optional, Callable
from dataclasses import dataclass


@dataclass
class FactorExposure:
    """单期因子暴露"""
    date: str
    values: pd.DataFrame  # index=股票, columns=因子名


class MultiFactorModel:
    """
    多因子选股模型

    使用流程:
    1. 注册因子: add_factor(name, values_per_date)
    2. 因子合成: combine(weight_method)
    3. 选股: select_top(N)
    """

    def __init__(self):
        # {日期: {因子名: Series(股票→因子值)}}
        self.factor_data: Dict[str, Dict[str, pd.Series]] = {}
        # 因子配置
        self.factor_config: Dict[str, dict] = {}

    def add_factor(
        self,
        name: str,
        values: Dict[str, pd.Series],
        direction: int = 1,
        category: str = "other"
    ):
        """
        添加因子

        Args:
            name: 因子名称
            values: {日期: 因子值Series(index=股票)}
            direction: 方向, 1=越大越好, -1=越小越好
            category: 因子类别
        """
        self.factor_config[name] = {
            "direction": direction,
            "category": category,
        }

        for date, series in values.items():
            if date not in self.factor_data:
                self.factor_data[date] = {}
            # 统一方向：将因子值统一为"越大越好"
            adjusted = series * direction
            self.factor_data[date][name] = adjusted

    # ──────────────────────────────────────────
    # 因子预处理
    # ──────────────────────────────────────────

    @staticmethod
    def _standardize(series: pd.Series) -> pd.Series:
        """Z-score标准化"""
        s = (series - series.mean()) / series.std()
        return s.clip(-3, 3)

    @staticmethod
    def _rank_score(series: pd.Series) -> pd.Series:
        """分位数打分 [0, 1]"""
        ranks = series.rank()
        return (ranks - 1) / (ranks.max() - 1)

    @staticmethod
    def _percentile_score(series: pd.Series) -> pd.Series:
        """百分位打分"""
        sorted_vals = series.sort_values()
        pct = pd.Series(
            np.linspace(0, 1, len(sorted_vals)),
            index=sorted_vals.index
        )
        return pct[series.index]

    # ──────────────────────────────────────────
    # 因子合成
    # ──────────────────────────────────────────

    def combine_equal_weight(self, dates: Optional[list] = None) -> pd.DataFrame:
        """
        等权合成

        Returns:
            DataFrame: index=日期, columns=股票, values=综合得分
        """
        if dates is None:
            dates = sorted(self.factor_data.keys())

        scores = []
        for date in dates:
            if date not in self.factor_data:
                continue
            factors = self.factor_data[date]
            if not factors:
                continue

            # 标准化并求和
            combined = None
            for name, series in factors.items():
                norm = self._rank_score(series)
                if combined is None:
                    combined = norm
                else:
                    # 对齐索引
                    combined = combined.add(norm, fill_value=0)

            if combined is not None:
                combined = combined / len(factors)  # 平均
                score_df = combined.to_frame(date).T
                scores.append(score_df)

        return pd.concat(scores) if scores else pd.DataFrame()

    def combine_ic_weight(
        self,
        ic_values: Dict[str, float],
        dates: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        IC加权合成
        使用因子过去一段时间的IC均值作为权重

        Args:
            ic_values: {因子名: IC均值}

        Returns:
            DataFrame: 日期×股票 综合得分
        """
        if dates is None:
            dates = sorted(self.factor_data.keys())

        # 归一化IC权重
        total_ic = sum(abs(v) for v in ic_values.values())
        if total_ic == 0:
            return self.combine_equal_weight(dates)

        weights = {k: abs(v) / total_ic for k, v in ic_values.items()}

        scores = []
        for date in dates:
            if date not in self.factor_data:
                continue
            factors = self.factor_data[date]
            if not factors:
                continue

            combined = None
            for name, series in factors.items():
                if name not in weights:
                    continue
                norm = self._rank_score(series)
                weighted = norm * weights[name]
                if combined is None:
                    combined = weighted
                else:
                    combined = combined.add(weighted, fill_value=0)

            if combined is not None:
                score_df = combined.to_frame(date).T
                scores.append(score_df)

        return pd.concat(scores) if scores else pd.DataFrame()

    # ──────────────────────────────────────────
    # 选股
    # ──────────────────────────────────────────

    def select_top(
        self,
        combined_scores: pd.DataFrame,
        top_n: int = 50,
        exclude_stocks: Optional[list] = None,
    ) -> Dict[str, list]:
        """
        根据综合得分选股

        Args:
            combined_scores: combine方法输出的评分
            top_n: 每期选股数量
            exclude_stocks: 排除的股票列表

        Returns:
            {日期: [股票代码列表]}
        """
        selections = {}
        exclude_set = set(exclude_stocks or [])

        for date in combined_scores.index:
            scores = combined_scores.loc[date].dropna()
            scores = scores[~scores.index.isin(exclude_set)]
            top_stocks = scores.nlargest(top_n).index.tolist()
            selections[date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)] = top_stocks

        return selections

    # ──────────────────────────────────────────
    # 组合回测 (简易)
    # ──────────────────────────────────────────

    def backtest(
        self,
        selections: Dict[str, list],
        stock_returns: pd.DataFrame,  # 日期×股票 收益矩阵
        initial_capital: float = 1_000_000,
        commission: float = 0.0003,  # 万三佣金
    ) -> pd.DataFrame:
        """
        简易组合回测

        Returns:
            DataFrame: 逐日持仓市值、收益、累计收益
        """
        dates = sorted(selections.keys())
        daily_records = []

        position = {}  # {股票: 仓位}
        capital = initial_capital

        for i, date in enumerate(dates):
            # 调仓日
            if i > 0:
                # 先计算上个周期持仓在今天卖出
                prev_date = dates[i - 1]
                prev_returns = stock_returns.loc[
                    prev_date:date
                ] if date in stock_returns.index else pd.DataFrame()

                sell_value = 0
                for stock, shares in list(position.items()):
                    if stock in stock_returns.columns and date in stock_returns.index:
                        price_change = 1 + stock_returns.loc[date, stock]
                        sell_value += shares * price_change
                    else:
                        sell_value += shares

                # 扣除佣金
                capital = sell_value * (1 - commission)
                position = {}

            # 调仓: 买入选中的股票
            if date in stock_returns.index:
                available = capital / len(selections[date])
                for stock in selections[date]:
                    if stock in stock_returns.columns:
                        position[stock] = available

                # 扣除佣金
                capital = 0  # 全部买入，以持仓形式存在
                daily_records.append({
                    "date": date,
                    "position_value": sum(position.values()),
                    "cash": 0,
                    "total": sum(position.values()),
                    "action": "rebalance",
                })

        return pd.DataFrame(daily_records)
