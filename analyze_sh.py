"""
沪市独立分析脚本
只分析上海市场股票（600/601/603/605 + 688科创板）
"""
import sys, os, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime
from config import BACKTEST_CONFIG
from factor_pipeline import FactorPipeline
from multi_factor import MultiFactorModel
from data_fetcher import AStockDataFetcher

fetcher = AStockDataFetcher()
stocks = fetcher.get_stock_list()
all_codes = stocks["stock_code"].tolist()

# 沪市：6开头，排除科创板(688)和北交所
sh_codes = [c for c in all_codes if c.startswith("6") and not c.startswith(("8", "688"))]
print(f"沪市股票: {len(sh_codes)} 只")

pipeline = FactorPipeline()

# 只传沪市股票
price_df = fetcher.get_all_daily_price(
    BACKTEST_CONFIG["start_date"],
    BACKTEST_CONFIG["end_date"],
    stock_list=sh_codes,
    max_stocks=-1,
)
if price_df.empty:
    print("❌ 无数据")
    exit(1)

latest = price_df["date"].max()
print(f"数据: {price_df.shape[0]} 行, {price_df['stock_code'].nunique()} 只, 最新: {latest.date()}")

# 计算未来收益
df = price_df.sort_values(["stock_code", "date"]).copy()
df["fwd_ret"] = df.groupby("stock_code")["close"].transform(lambda x: x.shift(-20) / x - 1)
df["ym"] = df["date"].dt.to_period("M")
fr = pd.DataFrame()
for ym, md in df.groupby("ym")["date"].max().items():
    fr[md.strftime("%Y-%m-%d")] = df[df["date"] == md].set_index("stock_code")["fwd_ret"].dropna()
fr = fr.T
fr.index = pd.to_datetime(fr.index)

# 因子测试
valid = {}
print(f"\n{'='*50}")
print(f"  沪市因子有效性 ({len(sh_codes)}只)")
print(f"{'='*50}")

for name, factor in pipeline.factor_registry.items():
    try:
        matrix = pipeline._build_factor_matrix(factor, price_df)
        if matrix.empty:
            continue
        ic = pipeline.analyzer.calc_ic(matrix, fr)
        ic_mean = ic.mean() if not ic.empty else 0
        ic_std = ic.std() if not ic.empty and len(ic) > 1 else 0
        ic_ir = ic_mean / ic_std if ic_std != 0 else 0
        star = "★" if abs(ic_mean) > 0.08 else " "
        skip = "(跳过)" if abs(ic_mean) <= 0.02 else ""
        print(f"  {star} {factor.name:15s} | IC={ic_mean:+7.4f} | IR={ic_ir:.4f} | {len(ic):2d}期 {skip}")
        if abs(ic_mean) > 0.02:
            valid[name] = {"factor": factor, "ic_mean": ic_mean, "matrix": matrix}
    except Exception:
        continue

print(f"\n  有效因子: {len(valid)} / {len(pipeline.factor_registry)}")

if not valid:
    print("无有效因子")
    exit()

# 多因子合成
model = MultiFactorModel()
for n, i in valid.items():
    vals = {d: i["matrix"].loc[d] for d in i["matrix"].index}
    model.add_factor(n, vals, direction=i["factor"].direction, category=i["factor"].category)
combined = model.combine_equal_weight()

stocks_df = pipeline.fetcher.get_stock_list()
name_map = dict(zip(stocks_df["stock_code"], stocks_df["stock_name"]))

if latest in combined.index:
    scores = combined.loc[latest].dropna().sort_values(ascending=False)

    print(f"\n{'='*55}")
    print(f"  🏆 沪市选股Top 20 ({latest.date()}, {len(sh_codes)}只)")
    print(f"{'='*55}")
    print(f"  {'排名':>4s} {'代码':>8s} {'名称':>12s} {'得分':>7s} {'板块':>6s}")
    print(f"  {'─'*40}")

    for i, (s, sc) in enumerate(scores.head(20).items(), 1):
        sn = name_map.get(s, "")[:10]
        board = "科创板" if s.startswith("688") else "沪主板"
        print(f"  {i:>4d} {s:>8s} {sn:>12s} {sc:>7.4f} {board}")

    # 科创板独立排名
    kcb = [(s, sc) for s, sc in scores.items() if s.startswith("688")]
    if kcb:
        print(f"\n📌 科创板独立排名:")
        for i, (s, sc) in enumerate(sorted(kcb, key=lambda x: -x[1])[:5], 1):
            sn = name_map.get(s, "")[:10]
            print(f"    {i}. {s} {sn} ({sc:.4f})")

    # 沪主板独立排名
    main = [(s, sc) for s, sc in scores.items() if not s.startswith("688")]
    if main:
        print(f"\n📌 沪主板(600/601/603/605)独立排名:")
        for i, (s, sc) in enumerate(sorted(main, key=lambda x: -x[1])[:10], 1):
            sn = name_map.get(s, "")[:10]
            print(f"    {i}. {s} {sn} ({sc:.4f})")

    # 保存结果
    result = {
        "date": str(latest.date()),
        "total_stocks": len(sh_codes),
        "valid_factors": len(valid),
        "top_picks": [{"rank": i, "code": s, "name": name_map.get(s, ""), "score": round(float(sc), 4)}
                      for i, (s, sc) in enumerate(scores.head(20).items(), 1)],
    }
    with open("sh_result.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: sh_result.json")
else:
    print(f"最新日期 {latest.date()} 不在评分矩阵中")
