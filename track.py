"""
实盘跟踪脚本
每周运行: python track.py
输出最新选股推荐 + 持仓分析
"""

import sys, os, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime
from config import BACKTEST_CONFIG
from factor_pipeline import FactorPipeline
from data_fetcher import AStockDataFetcher

OUTPUT_FILE = "tracking_result.json"

# ═══════════════════════════════════════════
# 1. 获取最新数据并跑全流程
# ═══════════════════════════════════════════

print("=" * 55)
print("  实盘跟踪 - 最新一期选股")
print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 55)

pipeline = FactorPipeline()
price_df, stock_list = pipeline.prepare_data(
    start_date="2026-01-01",
    end_date=BACKTEST_CONFIG["end_date"],
    max_stocks=200,
    with_financial=True,
)

if price_df.empty:
    print("❌ 无数据，无法分析")
    exit(1)

latest_date = price_df["date"].max()
print(f"\n最新数据日: {latest_date.date()}")
print(f"股票数量: {price_df['stock_code'].nunique()}")
print(f"数据行数: {len(price_df)}")

# ═══════════════════════════════════════════
# 2. 因子有效性测试
# ═══════════════════════════════════════════

print(f"\n{'─'*50}")
print("  因子有效性 (最新截面)")
print(f"{'─'*50}")

forward_ret = pipeline._calc_forward_returns(price_df, hold_days=20)
valid_factors = {}

for name, factor in pipeline.factor_registry.items():
    try:
        factor_matrix = pipeline._build_factor_matrix(factor, price_df)
        if factor_matrix.empty:
            continue

        ic = pipeline.analyzer.calc_ic(factor_matrix, forward_ret)
        ic_mean = ic.mean() if not ic.empty else 0
        ic_std = ic.std() if not ic.empty and len(ic) > 1 else 0
        ic_ir = ic_mean / ic_std if ic_std != 0 else 0

        if abs(ic_mean) > 0.02:
            valid_factors[name] = {"factor": factor, "ic_mean": ic_mean, "ic_ir": ic_ir}
            direction = "↑" if factor.direction == 1 else "↓"
            star = "★" if abs(ic_mean) > 0.08 else " "
            print(f"  {star} {factor.name:15s} IC={ic_mean:+.4f}  IR={ic_ir:.4f}  {direction}")
        else:
            print(f"    {factor.name:15s} IC={ic_mean:+.4f}  (弱，跳过)")
    except Exception:
        continue

print(f"\n  有效因子: {len(valid_factors)} / {len(pipeline.factor_registry)}")

# ═══════════════════════════════════════════
# 3. 多因子合成选股
# ═══════════════════════════════════════════

if valid_factors:
    from multi_factor import MultiFactorModel
    model = MultiFactorModel()
    for name, info in valid_factors.items():
        factor_matrix = pipeline._build_factor_matrix(info["factor"], price_df)
        if not factor_matrix.empty:
            values_dict = {d: factor_matrix.loc[d] for d in factor_matrix.index}
            model.add_factor(name, values_dict, direction=info["factor"].direction,
                             category=info["factor"].category)

    combined = model.combine_equal_weight()

    if latest_date in combined.index:
        scores = combined.loc[latest_date].dropna().sort_values(ascending=False)
        top10 = scores.head(10)

        print(f"\n{'='*50}")
        print(f"  🏆 综合选股推荐 ({latest_date.date()})")
        print(f"{'='*50}")
        print(f"  {'排名':>4s} {'代码':>8s} {'得分':>8s}")
        print(f"  {'─'*22}")
        for i, (stock, score) in enumerate(top10.items(), 1):
            print(f"  {i:>4d} {stock:>8s} {score:>8.4f}")

        # 保存结果
        result = {
            "date": str(latest_date.date()),
            "timestamp": datetime.now().isoformat(),
            "valid_factors": len(valid_factors),
            "top_picks": [{"rank": i, "stock": s, "score": round(float(score), 4)}
                          for i, (s, score) in enumerate(top10.items(), 1)],
            "factor_summary": {name: {"ic": round(info["ic_mean"], 4),
                                       "ir": round(info["ic_ir"], 4)}
                               for name, info in valid_factors.items()},
        }
        with open(OUTPUT_FILE, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存: {OUTPUT_FILE}")

        # 对比上次结果
        history_file = "tracking_history.csv"
        if os.path.exists(history_file):
            history = pd.read_csv(history_file)
            last_top = history.iloc[-1]["top1"] if len(history) > 0 else "N/A"
            print(f"\n  上次Top1: {last_top}")
        else:
            print(f"\n  首次运行，无历史对比")

        # 追加到历史
        row = {"date": str(latest_date.date()), "top1": list(top10.keys())[0],
               "top1_score": round(float(top10.iloc[0]), 4), "valid_factors": len(valid_factors)}
        pd.DataFrame([row]).to_csv(history_file, mode="a",
                                    header=not os.path.exists(history_file), index=False)

    else:
        print(f"\n⚠️ 最新日期 {latest_date.date()} 不在评分矩阵中")
else:
    print("\n⚠️ 没有有效因子")

print(f"\n{'='*50}")
print(f"✅ 跟踪完成")
print(f"{'='*50}")
