"""
中国中铁 (601390) 个股分析
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

from data_fetcher import AStockDataFetcher

f = AStockDataFetcher()
OUTPUT = "charts"
os.makedirs(OUTPUT, exist_ok=True)

print("=" * 50)
print("中国中铁 (601390) 行情分析")
print("=" * 50)

# 获取数据
df = f.get_daily_price("601390", "2020-01-01", "2025-12-31", use_cache=False)
if df.empty:
    print("❌ 直接获取失败，尝试akshare...")
    import akshare as ak
    raw = ak.stock_zh_a_hist(
        symbol="601390", period="daily",
        start_date="20200101", end_date="20251231", adjust="qfq",
    )
    if not raw.empty:
        raw.columns = [
            "date","stock_code","open","close","high","low",
            "volume","amount","amplitude","pct_change","change","turnover",
        ]
        raw["date"] = pd.to_datetime(raw["date"])
        df = raw

if df.empty:
    print("❌ 无法获取中国中铁数据")
    exit(1)

df["year"] = df["date"].dt.year
print(f"\n数据区间: {df['date'].min().date()} ~ {df['date'].max().date()}")
print(f"总交易天数: {len(df)}")

# 年度收益
total_ret = (1 + df["pct_change"] / 100).prod() - 1
sharpe = df["pct_change"].mean() / df["pct_change"].std() * np.sqrt(252)
cum = (1 + df["pct_change"] / 100).cumprod()
dd = cum / cum.cummax() - 1
max_dd = dd.min()
win_rate = (df["pct_change"] > 0).mean()
yr = df.groupby("year").apply(
    lambda g: (1 + g["pct_change"] / 100).prod() - 1
)

print(f"\n{'─'*40}")
print(f"  累计收益 (2020-2025):   {total_ret:>8.2%}")
print(f"  年化波动率:            {df['pct_change'].std()*np.sqrt(252):>8.2%}")
print(f"  夏普比率:              {sharpe:>8.2f}")
print(f"  最大回撤:              {max_dd:>8.2%}")
print(f"  日胜率:                {win_rate:>8.2%}")
print(f"  最新收盘价:            {df.iloc[-1]['close']:>8.2f}")
print(f"  52周最高:              {df[-252:]['close'].max():>8.2f}")
print(f"  52周最低:              {df[-252:]['close'].min():>8.2f}")
print(f"{'─'*40}")

# 年度收益
print(f"\n年度收益:")
for y, r in yr.items():
    print(f"  {y}: {r:>+8.2%}")

# 对比沪深300 (简单同比)
import akshare as ak
try:
    hs300 = ak.stock_zh_index_daily(symbol="sh000300")
    hs300 = hs300[hs300["date"] >= df["date"].min()]
    hs300["pct"] = hs300["close"].pct_change()
    hs300["year"] = hs300["date"].dt.year
    hs300_yr = hs300.groupby("year").apply(
        lambda g: (1 + g["pct"]).prod() - 1
    )
    print(f"\n同期沪深300年度收益:")
    for y, r in hs300_yr.items():
        diff = (1 + yr.get(y, 0)) / (1 + r) - 1 if y in yr.index and r != -1 else 0
        print(f"  {y}: {r:>+8.2%}   中国中铁: {yr.get(y, 0):>+8.2%}   超额: {diff:>+8.2%}")
except Exception as e:
    print(f"  (沪深300对比跳过: {e})")

# ── 绘制股价走势图 ──
print(f"\n[1/3] 绘制股价走势图...")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

ax1.plot(df["date"], df["close"], color="#1f77b4", linewidth=1, label="收盘价")
# 填充
ax1.fill_between(df["date"], df["close"], alpha=0.1, color="#1f77b4")
# MA60
ma60 = df["close"].rolling(60).mean()
ax1.plot(df["date"], ma60, color="orange", linewidth=1, alpha=0.7, label="MA60")
# 高/低点标注
peak_idx = df["close"].idxmax()
trough_idx = df["close"].idxmin()
ax1.annotate(f"最高 {df.loc[peak_idx,'close']:.2f}",
             (df.loc[peak_idx,"date"], df.loc[peak_idx,"close"]),
             xytext=(10, 10), textcoords="offset points", fontsize=9,
             color="red", arrowprops=dict(arrowstyle="->", color="red", alpha=0.6))
ax1.annotate(f"最低 {df.loc[trough_idx,'close']:.2f}",
             (df.loc[trough_idx,"date"], df.loc[trough_idx,"close"]),
             xytext=(10, -15), textcoords="offset points", fontsize=9,
             color="green", arrowprops=dict(arrowstyle="->", color="green", alpha=0.6))

ax1.set_title("中国中铁 (601390) 股价走势", fontsize=14, fontweight="bold")
ax1.set_ylabel("价格 (元)")
ax1.legend()
ax1.grid(alpha=0.3)

# 成交量
colors_v = ["red" if c >= 0 else "green" for c in df["pct_change"]]
ax2.bar(df["date"], df["volume"] / 1e8, color=colors_v, alpha=0.5, width=1)
ax2.set_ylabel("成交量 (亿)")
ax2.set_xlabel("日期")
ax2.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUTPUT}/601390_price.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ {OUTPUT}/601390_price.png")

# ── 回撤图 ──
print(f"[2/3] 绘制回撤图...")
fig, ax = plt.subplots(figsize=(14, 6))
ax.fill_between(df["date"], 0, dd * 100, color="red", alpha=0.3, label="回撤")
ax.plot(df["date"], dd * 100, color="red", linewidth=0.5, alpha=0.5)
# 标记最大回撤
md_idx = dd.idxmin()
ax.annotate(f"最大回撤 {max_dd:.2%}",
            (df.loc[md_idx,"date"], dd.min() * 100),
            xytext=(20, 20), textcoords="offset points", fontsize=10,
            color="darkred", arrowprops=dict(arrowstyle="->", color="darkred"))

ax.axhline(0, color="black", linewidth=0.5)
ax.set_title("中国中铁 回撤曲线", fontsize=14, fontweight="bold")
ax.set_ylabel("回撤 (%)")
ax.set_xlabel("日期")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUTPUT}/601390_drawdown.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ {OUTPUT}/601390_drawdown.png")

# ── 月度热力图 ──
print(f"[3/3] 绘制月度收益热力图...")
df["month"] = df["date"].dt.month
monthly_ret = df.groupby(["year", "month"])["pct_change"].sum() / 100

pivot = monthly_ret.unstack(level="month")
pivot.columns = ["1月","2月","3月","4月","5月","6月",
                 "7月","8月","9月","10月","11月","12月"]

fig, ax = plt.subplots(figsize=(12, 5))
sns_heatmap = __import__("seaborn").heatmap(
    pivot * 100, annot=True, fmt=".1f", cmap="RdYlGn",
    center=0, linewidths=0.5, ax=ax,
    cbar_kws={"label": "月收益 (%)"},
)
ax.set_title("中国中铁 月度收益热力图 (%)", fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(f"{OUTPUT}/601390_monthly_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ {OUTPUT}/601390_monthly_heatmap.png")

print(f"\n{'='*50}")
print(f"分析完成！图表已保存到 {OUTPUT}/ 目录")
print(f"{'='*50}")
