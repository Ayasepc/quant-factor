"""
因子选股全流程管道

一站式完成:
  数据准备 → 因子计算 → 因子测试 → 多因子合成 → 选股推荐

使用示例:
  python factor_pipeline.py --mode test_single --factor pe_ttm
  python factor_pipeline.py --mode full_pipeline
"""

import pandas as pd
import numpy as np
import traceback
import warnings
from datetime import datetime, timedelta

from config import BACKTEST_CONFIG, UNIVERSE_CONFIG, FACTOR_CONFIG
from data_fetcher import AStockDataFetcher
from factors.fundamental import (
    PE_TTM, PB, PS_TTM,
    ROE, ROA, GrossMargin, NetMargin,
    RevenueGrowth, ProfitGrowth,
)
from factors.momentum import (
    Momentum1M, Momentum3M, Momentum6M,
    Volatility20D, Turnover20D, Alpha60D,
)
from analyzer import FactorAnalyzer
from multi_factor import MultiFactorModel

warnings.filterwarnings("ignore")


class FactorPipeline:
    """因子选股全流程"""

    def __init__(self):
        self.fetcher = AStockDataFetcher()
        self.analyzer = FactorAnalyzer(group_num=BACKTEST_CONFIG["group_num"])

        # 注册所有可用因子
        self.factor_registry = {
            # 估值
            "pe_ttm": PE_TTM(),
            "pb": PB(),
            "ps_ttm": PS_TTM(),
            # 质量
            "roe": ROE(),
            "roa": ROA(),
            "gross_margin": GrossMargin(),
            "net_margin": NetMargin(),
            # 成长
            "revenue_yoy": RevenueGrowth(),
            "profit_yoy": ProfitGrowth(),
            # 动量
            "momentum_1m": Momentum1M(),
            "momentum_3m": Momentum3M(),
            "momentum_6m": Momentum6M(),
            # 风险
            "volatility_20d": Volatility20D(),
            # 流动性
            "turnover_20d": Turnover20D(),
            # 技术
            "alpha_60d": Alpha60D(),
        }

    # ═══════════════════════════════════════════
    # 1. 数据准备
    # ═══════════════════════════════════════════

    def prepare_data(
        self, start_date: str = None, end_date: str = None,
        max_stocks: int = 200, with_financial: bool = True,
    ):
        """
        准备分析所需数据

        Args:
            max_stocks: 最大股票数，-1 表示全市场
            with_financial: 是否获取财务数据并合并
        """
        start = start_date or BACKTEST_CONFIG["start_date"]
        end = end_date or BACKTEST_CONFIG["end_date"]

        print(f"[1/3] 获取全A股股票池...")
        full_list = self.fetcher.get_universe(end)
        # 过滤科创板 (688) 和北交所
        filtered = [c for c in full_list if not c.startswith("688")]
        print(f"  全市场 {len(full_list)} 只, 过滤后 {len(filtered)} 只")

        if max_stocks > 0:
            sample = filtered[:max_stocks]
            print(f"  取前 {len(sample)} 只作为样本")
        else:
            sample = filtered
            print(f"  全市场选股: {len(sample)} 只")

        print(f"[2/3] 获取行情数据 ({start} ~ {end})...")
        price_df = self.fetcher.get_all_daily_price(
            start, end, sample, max_stocks=-1,
        )
        if not price_df.empty and with_financial:
            print(f"[2.5/3] 获取财务数据并合并...")
            price_df = self.fetcher.enrich_with_financial_data(price_df)

        print(f"[3/3] 数据准备完成: {price_df.shape[0]} 行 × {price_df.shape[1]} 列 ({len(sample)} 只股票)")
        return price_df, sample

    # ═══════════════════════════════════════════
    # 2. 单因子测试
    # ═══════════════════════════════════════════

    def test_single_factor(
        self, factor_name: str, price_df: pd.DataFrame, plot: bool = True
    ):
        """
        对单个因子进行完整分析

        步骤:
        1. 计算因子值 → 2. 计算未来收益 → 3. IC分析 → 4. 分组收益
        """
        if factor_name not in self.factor_registry:
            print(f"未知因子: {factor_name}")
            print(f"可用因子: {list(self.factor_registry.keys())}")
            return None

        factor = self.factor_registry[factor_name]
        print(f"\n开始测试因子: {factor.name} ({factor.category})")

        # Step 1: 计算因子值 (最新截面)
        print("  计算因子值...")
        factor_values = factor.calculate(price_df)

        # Step 2: 计算未来收益 (持有20个交易日)
        print("  计算未来收益...")
        forward_ret = self._calc_forward_returns(price_df, hold_days=20)

        # Step 3: 准备截面数据格式
        # 取最新交易日
        latest_date = price_df["date"].max()

        # 构建因子矩阵 (多期)
        factor_matrix = self._build_factor_matrix(factor, price_df)

        # Step 4: 运行分析
        if not factor_matrix.empty and not forward_ret.empty:
            result = self.analyzer.full_report(
                factor_name=factor.name,
                factor_category=factor.category,
                factor_direction=factor.direction,
                factor_values=factor_matrix,
                forward_returns=forward_ret,
                plot=plot,
            )

            # 输出选股示例
            if latest_date in factor_matrix.index:
                values = factor_matrix.loc[latest_date].dropna().sort_values(
                    ascending=(factor.direction == -1)
                )
                top10 = values.head(10)
                print(f"\n  📋 最新截面 ({latest_date.date()}):")
                print(f"     推荐前三: {top10.index[:3].tolist()}")
                print(f"     因子值范围: {values.min():.2f} ~ {values.max():.2f}")

            return result

        return None

    # ═══════════════════════════════════════════
    # 3. 全流程管道
    # ═══════════════════════════════════════════

    def full_pipeline(self):
        """
        完整因子选股流程:
        计算多个因子 → 因子测试筛选 → 多因子合成 → 选股推荐
        """
        print("=" * 60)
        print("  A股多因子选股系统 - 全流程运行")
        print("=" * 60)

        # Step 1: 获取数据
        price_df, stock_list = self.prepare_data()
        latest_date = price_df["date"].max()

        # Step 2: 计算未来收益矩阵
        forward_ret = self._calc_forward_returns(price_df, hold_days=20)

        # Step 3: 对每个因子做测试
        print(f"\n{'='*60}")
        print("  因子有效性测试")
        print(f"{'='*60}")

        valid_factors = {}
        for name, factor in self.factor_registry.items():
            try:
                factor_matrix = self._build_factor_matrix(factor, price_df)
                if factor_matrix.empty:
                    continue

                ic = self.analyzer.calc_ic(factor_matrix, forward_ret)
                ic_mean = ic.mean() if not ic.empty else 0
                ic_std = ic.std() if not ic.empty and len(ic) > 1 else 0
                ic_ir = ic_mean / ic_std if ic_std != 0 else 0
                print(f"  {factor.name:15s} | IC={ic_mean:.4f} | IR={ic_ir:.4f} | 期数={len(ic)}")

                # 筛选有效因子: |IC| > 0.02
                if abs(ic_mean) > 0.02:
                    valid_factors[name] = {
                        "factor": factor,
                        "ic_mean": ic_mean,
                        "matrix": factor_matrix,
                    }
            except Exception as e:
                print(f"  {factor.name:15s} | 失败: {e}")
                print(f"    {traceback.format_exc()[:300]}")

        print(f"\n  有效因子: {len(valid_factors)} / {len(self.factor_registry)}")

        if not valid_factors:
            print("  没有有效因子，尝试扩大数据量")
            return

        # Step 4: 多因子合成
        print(f"\n{'='*60}")
        print("  多因子合成选股")
        print(f"{'='*60}")

        model = MultiFactorModel()
        for name, info in valid_factors.items():
            # 以字典形式传入每期因子值
            dates = info["matrix"].index
            values_dict = {}
            for date in dates:
                values_dict[date] = info["matrix"].loc[date]

            model.add_factor(
                name=name,
                values=values_dict,
                direction=info["factor"].direction,
                category=info["factor"].category,
            )

        # 等权合成
        combined = model.combine_equal_weight()

        if not combined.empty and latest_date in combined.index:
            top_scores = combined.loc[latest_date].dropna().sort_values(ascending=False)
            top20 = top_scores.head(20)

            print(f"\n  📋 综合选股推荐 ({latest_date.date()}):")
            print(f"  {'排名':>4s} {'股票代码':>10s} {'综合得分':>10s}")
            print(f"  {'-'*28}")
            for i, (stock, score) in enumerate(top20.items(), 1):
                print(f"  {i:>4d} {stock:>10s} {score:>10.4f}")

        # Step 5: 输出配置
        print(f"\n{'='*60}")
        print(f"  配置参数")
        print(f"{'='*60}")
        print(f"  回测区间: {BACKTEST_CONFIG['start_date']} ~ {BACKTEST_CONFIG['end_date']}")
        print(f"  调仓频率: {BACKTEST_CONFIG['rebalance_freq']}")
        print(f"  股票池规模: {len(stock_list)}")
        print(f"  数据集最后一期: {latest_date.date()}")
        print(f"{'='*60}")

    # ═══════════════════════════════════════════
    # 内部辅助函数
    # ═══════════════════════════════════════════

    def _build_factor_matrix(self, factor, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        构建多期因子矩阵

        按月计算因子值，每个计算点使用过去N个月的历史数据
        返回: DataFrame(日期×股票)
        """
        df = price_df.sort_values("date").copy()

        # 按月分组，取每组最后一天作为因子计算日
        df["year_month"] = df["date"].dt.to_period("M")
        month_ends = df.groupby("year_month")["date"].max().reset_index()
        month_ends = month_ends.sort_values("date")

        # 需要多少历史数据（取所有因子最大需求，约6个月 = 120交易日）
        MIN_HISTORY = 250  # 约1年

        records = []
        errors = []
        for _, row in month_ends.iterrows():
            ym = row["year_month"]
            end_date = row["date"]
            start_date = end_date - pd.Timedelta(days=MIN_HISTORY)

            # 取从 start_date 到 end_date 的数据
            window = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            if window.empty:
                continue

            try:
                vals = factor.calculate(window)
                if isinstance(vals, pd.Series) and not vals.empty:
                    vals = factor.winsorize(vals)
                    vals = factor.standardize(vals)
                    records.append((end_date, vals))
            except Exception as e:
                errors.append(f"{ym}: {e}")
                continue

        if errors and not records:
            # 只显示非基本面因子的错误（基本面因子需要财务数据）
            if factor.category not in ("valuation", "quality", "growth"):
                short = str(errors[0])[:150]
                print(f"  {factor.name:15s} | 全部月份失败: {short}")

        if not records:
            return pd.DataFrame()

        # 统一使用月末日期作为索引
        matrix = pd.DataFrame({d.strftime("%Y-%m-%d"): s for d, s in records})
        matrix = matrix.T
        matrix.index = pd.to_datetime(matrix.index)
        matrix.index.name = "date"
        return matrix

    def _calc_forward_returns(
        self, price_df: pd.DataFrame, hold_days: int = 20
    ) -> pd.DataFrame:
        """计算未来 N 日收益（按月频，月末对齐 _build_factor_matrix）"""
        df = price_df.sort_values(["stock_code", "date"]).copy()
        df["fwd_ret"] = df.groupby("stock_code")["close"].transform(
            lambda x: x.shift(-hold_days) / x - 1
        )

        # 取每个月最后一个交易日
        df["year_month"] = df["date"].dt.to_period("M")
        month_last = df.groupby("year_month").apply(
            lambda g: g.loc[g.groupby("stock_code")["date"].idxmax()]
        ).reset_index(drop=True)

        records = []
        for ym, group in month_last.groupby("year_month"):
            rets = group.set_index("stock_code")["fwd_ret"].dropna()
            if not rets.empty:
                # 用该月最后一个交易日作为日期索引
                last_date = group["date"].max()
                records.append((last_date, rets))

        if not records:
            return pd.DataFrame()

        matrix = pd.DataFrame({d.strftime("%Y-%m-%d"): s for d, s in records})
        matrix = matrix.T
        matrix.index = pd.to_datetime(matrix.index)
        matrix.index.name = "date"
        return matrix


# ═══════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A股多因子选股系统")
    parser.add_argument(
        "--mode", type=str, default="full_pipeline",
        choices=["test_single", "full_pipeline"],
        help="运行模式"
    )
    parser.add_argument(
        "--factor", type=str, default="pe_ttm",
        help="因子名称 (test_single模式)"
    )

    args = parser.parse_args()
    pipeline = FactorPipeline()

    if args.mode == "test_single":
        price_df, _ = pipeline.prepare_data()
        pipeline.test_single_factor(args.factor, price_df)
    else:
        pipeline.full_pipeline()
