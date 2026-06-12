"""
因子分析模块
核心功能:
1. IC分析 (Information Coefficient) - 因子与未来收益的相关性
2. Rank IC 分析 - 因子的排序选股能力
3. 分组回测 - 按因子值分组看各组表现
4. 累积累计收益可视化
"""

import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional
from dataclasses import dataclass


@dataclass
class FactorReport:
    """因子测试报告"""
    name: str
    category: str
    direction: int
    ic_mean: float          # IC均值
    ic_std: float            # IC标准差
    ic_ir: float             # IC信息比 (IC均值 / IC标准差)
    ic_positive_ratio: float # IC>0的比例
    rank_ic_mean: float      # Rank IC均值
    rank_ic_ir: float        # Rank IC信息比
    groups_return: dict      # 各组累计收益
    long_short_return: float # 多空组合收益


class FactorAnalyzer:
    """
    因子分析器

    使用流程:
    1. 准备因子值矩阵 (日期×股票)
    2. 准备未来收益矩阵 (日期×股票)
    3. 计算IC/分组收益
    """

    def __init__(self, group_num: int = 10):
        """
        Args:
            group_num: 分组数量 (默认10组，即十分位)
        """
        self.group_num = group_num

    # ──────────────────────────────────────────
    # IC 分析
    # ──────────────────────────────────────────

    def calc_ic(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
        method: str = "pearson",
        min_common: int = 5,
    ) -> pd.Series:
        """
        计算截面IC时间序列

        Args:
            factor_values:    因子值矩阵, index=日期, columns=股票
            forward_returns:  未来收益矩阵, index=日期, columns=股票
            method:           'pearson' 或 'spearman' (Rank IC)
            min_common:       最小股票数要求 (小样本调低)

        Returns:
            每个交易日的IC值 (时间序列)
        """
        dates = factor_values.index
        ic_list = []

        for date in dates:
            if date not in forward_returns.index:
                continue
            fv = factor_values.loc[date].dropna()
            fr = forward_returns.loc[date].dropna()

            common = fv.index.intersection(fr.index)
            if len(common) < min_common:
                continue

            x = fv[common].values
            y = fr[common].values

            if method == "spearman":
                corr, _ = stats.spearmanr(x, y)
            else:
                corr, _ = stats.pearsonr(x, y)

            ic_list.append({"date": date, "ic": corr})

        if not ic_list:
            return pd.Series(dtype=float, name="ic")

        ic_series = pd.DataFrame(ic_list).set_index("date")["ic"]
        return ic_series

    def calc_rank_ic(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame
    ) -> pd.Series:
        """简便方法: 直接调用 calc_ic 使用 spearman"""
        return self.calc_ic(factor_values, forward_returns, method="spearman")

    def report_ic(self, ic_series: pd.Series) -> dict:
        """IC统计报告"""
        if ic_series.empty:
            return {
                "ic_mean": 0, "ic_std": 0, "ic_ir": 0,
                "ic_positive_ratio": 0, "ic_last": None,
            }
        return {
            "ic_mean": ic_series.mean(),
            "ic_std": ic_series.std(),
            "ic_ir": ic_series.mean() / ic_series.std() if ic_series.std() != 0 else 0,
            "ic_positive_ratio": (ic_series > 0).mean(),
            "ic_last": ic_series.iloc[-1] if not ic_series.empty else None,
        }

    # ──────────────────────────────────────────
    # 分组收益分析
    # ──────────────────────────────────────────

    def calc_group_returns(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame
    ) -> dict:
        """
        分组收益计算

        每期按因子值排序分成 self.group_num 组
        计算每组等权持有一期的收益

        Returns:
            {group_id: 每期收益Series}
        """
        dates = factor_values.index
        groups_returns = {i: [] for i in range(self.group_num + 1)}
        groups_dates = []

        for date in dates:
            if date not in forward_returns.index:
                continue

            fv = factor_values.loc[date].dropna()
            fr = forward_returns.loc[date].dropna()

            common = fv.index.intersection(fr.index)
            if len(common) < self.group_num * 5:
                continue

            # 排序分组
            fv_sorted = fv[common].sort_values()
            group_size = len(fv_sorted) // self.group_num

            groups_dates.append(date)
            for g in range(self.group_num):
                start = g * group_size
                end = start + group_size if g < self.group_num - 1 else len(fv_sorted)
                group_stocks = fv_sorted.iloc[start:end].index
                ret = fr[group_stocks].mean()
                groups_returns[g].append(ret)

            # 多空: 做多组10, 做空组1
            long_stocks = fv_sorted.iloc[-group_size:].index if group_size > 0 else fv_sorted.index
            short_stocks = fv_sorted.iloc[:group_size].index if group_size > 0 else fv_sorted.index
            groups_returns[self.group_num].append(
                fr[long_stocks].mean() - fr[short_stocks].mean()
            )

        result = {}
        for g in range(self.group_num + 1):
            result[g] = pd.Series(groups_returns[g], index=groups_dates)
        return result

    # ──────────────────────────────────────────
    # 可视化
    # ──────────────────────────────────────────

    def plot_ic_series(
        self, ic_series: pd.Series, title: str = "IC Time Series", figsize=(12, 4)
    ):
        """IC时间序列图"""
        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(ic_series.index, ic_series.values, label="IC", alpha=0.7)
        ax.axhline(0, color="red", linestyle="--", alpha=0.5)
        ax.axhline(ic_series.mean(), color="green", linestyle="--",
                   label=f"Mean IC={ic_series.mean():.4f}")
        ax.set_title(title)
        ax.legend()
        fig.tight_layout()
        return fig

    def plot_group_cum_return(
        self, group_returns: dict, title: str = "Group Cumulative Return",
        figsize=(12, 6)
    ):
        """分组累计收益图"""
        fig, ax = plt.subplots(figsize=figsize)

        colors = plt.cm.RdYlGn(np.linspace(0, 1, self.group_num))
        for g in range(self.group_num):
            cum_ret = (1 + group_returns[g]).cumprod()
            ax.plot(cum_ret.index, cum_ret.values,
                    label=f"Group {g+1}", color=colors[g], alpha=0.8)

        # 多空收益
        if self.group_num in group_returns:
            ls = (1 + group_returns[self.group_num]).cumprod()
            ax.plot(ls.index, ls.values, label="Long-Short",
                    color="black", linewidth=2, linestyle="--")

        ax.set_title(title)
        ax.legend(loc="upper left")
        ax.axhline(1, color="gray", linestyle="-", alpha=0.3)
        fig.tight_layout()
        return fig

    # ──────────────────────────────────────────
    # 综合报告
    # ──────────────────────────────────────────

    def full_report(
        self,
        factor_name: str,
        factor_category: str,
        factor_direction: int,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
        plot: bool = True,
    ) -> FactorReport:
        """生成因子完整分析报告"""

        # IC分析
        ic = self.calc_ic(factor_values, forward_returns)
        rank_ic = self.calc_rank_ic(factor_values, forward_returns)
        ic_stats = self.report_ic(ic)

        # 分组收益
        group_ret = self.calc_group_returns(factor_values, forward_returns)

        report = FactorReport(
            name=factor_name,
            category=factor_category,
            direction=factor_direction,
            ic_mean=ic_stats["ic_mean"],
            ic_std=ic_stats["ic_std"],
            ic_ir=ic_stats["ic_ir"],
            ic_positive_ratio=ic_stats["ic_positive_ratio"],
            rank_ic_mean=rank_ic.mean(),
            rank_ic_ir=rank_ic.mean() / rank_ic.std() if rank_ic.std() != 0 else 0,
            groups_return={str(k): v for k, v in group_ret.items()},
            long_short_return=(1 + group_ret.get(self.group_num, pd.Series(dtype=float))).prod() - 1,
        )

        if plot:
            print(f"\n{'='*50}")
            print(f"因子分析: {factor_name} ({factor_category})")
            print(f"{'='*50}")
            print(f"IC均值:       {report.ic_mean:.4f}")
            print(f"IC标准差:     {report.ic_std:.4f}")
            print(f"IC信息比:     {report.ic_ir:.4f}")
            print(f"IC>0比例:     {report.ic_positive_ratio:.2%}")
            print(f"Rank IC均值:  {report.rank_ic_mean:.4f}")
            print(f"多空累计收益: {report.long_short_return:.2%}")

        return report
