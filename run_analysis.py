"""
因子选股可视化分析
生成 IC时序、分组收益、因子相关性等图表
"""

import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # 无GUI后端，直接保存图片
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
import seaborn as sns

from factor_pipeline import FactorPipeline
from config import BACKTEST_CONFIG

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")

COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
OUTPUT_DIR = "charts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("🚀 加载数据并计算因子...")
pipeline = FactorPipeline()
price_df, _ = pipeline.prepare_data(max_stocks=20)
forward_ret = pipeline._calc_forward_returns(price_df, hold_days=20)

# ──────────────────────────────────────────
# 只分析动量/技术因子（不需要财务数据）
# ──────────────────────────────────────────
factor_names = ["momentum_1m", "momentum_3m", "volatility_20d", "turnover_20d", "alpha_60d"]
factor_objs = [pipeline.factor_registry[n] for n in factor_names]

factor_matrices = {}
for name, obj in zip(factor_names, factor_objs):
    print(f"  计算 {obj.name}...")
    m = pipeline._build_factor_matrix(obj, price_df)
    if not m.empty:
        factor_matrices[name] = m

print(f"\n计算完成，共 {len(factor_matrices)} 个有效因子\n")

# ═══════════════════════════════════════════
# 1. IC 时序图
# ═══════════════════════════════════════════
print("[1/5] IC 时序图...")
fig, axes = plt.subplots(3, 2, figsize=(16, 10))
axes = axes.flatten()

for idx, (name, mat) in enumerate(factor_matrices.items()):
    if idx >= len(axes):
        break
    ax = axes[idx]
    ic = pipeline.analyzer.calc_ic(mat, forward_ret)

    if not ic.empty:
        ax.plot(ic.index, ic.values, color=COLORS[idx % len(COLORS)],
                alpha=0.7, linewidth=0.8)
        ax.axhline(0, color="red", linestyle="--", alpha=0.4, linewidth=0.8)
        mean_ic = ic.mean()
        ax.axhline(mean_ic, color="green", linestyle="--", alpha=0.5, linewidth=1)
        ax.fill_between(ic.index, 0, ic.values, alpha=0.1, color=COLORS[idx % len(COLORS)])

        # 标注统计量
        pos_ratio = (ic > 0).mean()
        text = (f"IC均值={mean_ic:.3f}  IC>0={pos_ratio:.0%}\n"
                f"ICIR={mean_ic/ic.std():.2f}  期数={len(ic)}")
        ax.text(0.02, 0.95, text, transform=ax.transAxes, fontsize=9,
                verticalalignment="top", bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    ax.set_title(f"{pipeline.factor_registry[name].name}", fontsize=12, fontweight="bold")
    ax.set_ylabel("IC")

# 隐藏多余子图
for idx in range(len(factor_matrices), len(axes)):
    axes[idx].set_visible(False)

fig.suptitle("因子 IC 时间序列 (2020-2025)", fontsize=15, fontweight="bold", y=1.01)
fig.tight_layout()
fig.savefig(f"{OUTPUT_DIR}/01_ic_timeseries.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ 已保存: {OUTPUT_DIR}/01_ic_timeseries.png")

# ═══════════════════════════════════════════
# 2. 分组累计收益图
# ═══════════════════════════════════════════
print("[2/5] 分组累计收益图...")
fig, axes = plt.subplots(3, 2, figsize=(16, 10))
axes = axes.flatten()

for idx, (name, mat) in enumerate(factor_matrices.items()):
    if idx >= len(axes):
        break
    ax = axes[idx]
    group_ret = pipeline.analyzer.calc_group_returns(mat, forward_ret)

    cmap = plt.cm.RdYlGn_r
    colors_g = [cmap(i / 10) for i in range(10)]

    for g in range(10):
        if g in group_ret:
            cum = (1 + group_ret[g]).cumprod()
            ax.plot(cum.index, cum.values, label=f"G{g+1}",
                    color=colors_g[g], alpha=0.7, linewidth=0.8)

    # 多空
    if 10 in group_ret:
        ls = (1 + group_ret[10]).cumprod()
        ax.plot(ls.index, ls.values, label="多空", color="black",
                linewidth=1.5, linestyle="--")

    ax.set_title(f"{pipeline.factor_registry[name].name}", fontsize=12, fontweight="bold")
    ax.axhline(1, color="gray", alpha=0.3, linewidth=0.5)
    ax.set_ylabel("累计收益")

    # 只有第一个和最后一个子图显示图例
    if idx == 0 or idx == len(factor_matrices) - 1:
        ax.legend(fontsize=7, ncol=2)

# 隐藏多余
for idx in range(len(factor_matrices), len(axes)):
    axes[idx].set_visible(False)

fig.suptitle("因子分组累计收益 (Group 1=因子最小, Group 10=因子最大)", fontsize=14, fontweight="bold", y=1.01)
fig.tight_layout()
fig.savefig(f"{OUTPUT_DIR}/02_group_returns.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ 已保存: {OUTPUT_DIR}/02_group_returns.png")

# ═══════════════════════════════════════════
# 3. 因子相关性热力图
# ═══════════════════════════════════════════
print("[3/5] 因子相关性热力图...")

# 取最近一期截面
latest_date = list(factor_matrices.values())[0].index[-1]
cross_section = {}
for name, mat in factor_matrices.items():
    if latest_date in mat.index:
        cross_section[pipeline.factor_registry[name].name] = mat.loc[latest_date].dropna()

cross_df = pd.DataFrame(cross_section)

fig, ax = plt.subplots(figsize=(8, 6))
mask = np.triu(np.ones_like(cross_df.corr(), dtype=bool), k=1)
sns.heatmap(cross_df.corr(), annot=True, fmt=".3f", cmap="RdBu_r",
            center=0, vmin=-1, vmax=1, mask=mask,
            linewidths=0.5, square=True, ax=ax,
            cbar_kws={"shrink": 0.8, "label": "相关系数"})
ax.set_title(f"因子截面相关性 ({latest_date.date()})", fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(f"{OUTPUT_DIR}/03_factor_correlation.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ 已保存: {OUTPUT_DIR}/03_factor_correlation.png")

# ═══════════════════════════════════════════
# 4. 综合打分 Top20 排行
# ═══════════════════════════════════════════
print("[4/5] 综合打分排行图...")

from multi_factor import MultiFactorModel

model = MultiFactorModel()
for name in factor_matrices:
    mat = factor_matrices[name]
    obj = pipeline.factor_registry[name]
    values_dict = {d: mat.loc[d] for d in mat.index}
    model.add_factor(name, values_dict, direction=obj.direction, category=obj.category)

combined = model.combine_equal_weight()

if latest_date in combined.index:
    scores = combined.loc[latest_date].dropna().sort_values(ascending=False)
    top15 = scores.head(15)

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(range(len(top15)), top15.values[::-1], color=plt.cm.Blues(0.3 + 0.7 * top15.values[::-1]))
    ax.set_yticks(range(len(top15)))
    ax.set_yticklabels(top15.index[::-1])
    ax.set_xlabel("综合得分")
    ax.set_title(f"多因子综合选股 Top15 ({latest_date.date()})", fontsize=13, fontweight="bold")

    for i, (v, label) in enumerate(zip(top15.values[::-1], top15.index[::-1])):
        ax.text(v + 0.01, i, f"{v:.3f}", va="center", fontsize=9)

    ax.set_xlim(0, 1.0)
    fig.tight_layout()
    fig.savefig(f"{OUTPUT_DIR}/04_top15_stocks.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ 已保存: {OUTPUT_DIR}/04_top15_stocks.png")

# ═══════════════════════════════════════════
# 5. 综合面板图 (Dashboard)
# ═══════════════════════════════════════════
print("[5/5] 综合面板图...")
fig = plt.figure(figsize=(20, 16))
gs = fig.add_gridspec(4, 4, hspace=0.35, wspace=0.3)

# — A: IC 对比条形图 —
ax1 = fig.add_subplot(gs[0, :2])
ic_values = {}
for name, mat in factor_matrices.items():
    ic = pipeline.analyzer.calc_ic(mat, forward_ret)
    ic_values[pipeline.factor_registry[name].name] = ic.mean() if not ic.empty else 0

names_list = list(ic_values.keys())
vals_list = list(ic_values.values())
colors_bar = ["#d62728" if v < 0 else "#2ca02c" for v in vals_list]
bars = ax1.bar(names_list, vals_list, color=colors_bar, alpha=0.8, edgecolor="gray", linewidth=0.5)
ax1.axhline(0, color="black", linewidth=0.8)
ax1.set_title("因子 IC 均值对比", fontsize=13, fontweight="bold")
ax1.set_ylabel("IC")
for bar, v in zip(bars, vals_list):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (0.005 if v >= 0 else -0.025),
             f"{v:.3f}", ha="center", fontsize=9)
ax1.tick_params(axis="x", rotation=30)

# — B: 多空累计收益对比 —
ax2 = fig.add_subplot(gs[0, 2:])
for idx, (name, mat) in enumerate(factor_matrices.items()):
    group_ret = pipeline.analyzer.calc_group_returns(mat, forward_ret)
    if 10 in group_ret:
        ls = (1 + group_ret[10]).cumprod()
        ax2.plot(ls.index, ls.values, label=pipeline.factor_registry[name].name,
                 color=COLORS[idx], linewidth=1.2)
ax2.axhline(1, color="gray", alpha=0.3, linestyle="--")
ax2.set_title("多空组合累计收益对比", fontsize=13, fontweight="bold")
ax2.legend(fontsize=8, ncol=2)
ax2.set_ylabel("累计收益")

# — C: 最新截面得分分布 —
ax3 = fig.add_subplot(gs[1, :2])
if latest_date in combined.index:
    all_scores = combined.loc[latest_date].dropna()
    ax3.hist(all_scores.values, bins=20, color="steelblue", edgecolor="white", alpha=0.8)
    ax3.axvline(all_scores.mean(), color="red", linestyle="--", label=f"均值={all_scores.mean():.3f}")
    ax3.axvline(all_scores.median(), color="green", linestyle="--", label=f"中位数={all_scores.median():.3f}")
    ax3.set_title("综合得分分布", fontsize=13, fontweight="bold")
    ax3.set_xlabel("综合得分")
    ax3.set_ylabel("股票数量")
    ax3.legend(fontsize=9)

# — D: 各因子贡献雷达图 —
ax4 = fig.add_subplot(gs[1, 2:], projection="polar")
if latest_date in combined.index:
    stock_scores_all = combined.loc[latest_date].dropna()
    top_stock = stock_scores_all.idxmax()
    bottom_stock = stock_scores_all.idxmin()

    # 看Top1和末位的因子构成
    if top_stock in cross_df.index and bottom_stock in cross_df.index:
        top_vals = cross_df.loc[top_stock].values
        bottom_vals = cross_df.loc[bottom_stock].values
        labels = cross_df.columns
        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        top_vals = np.concatenate((top_vals, [top_vals[0]]))
        bottom_vals = np.concatenate((bottom_vals, [bottom_vals[0]]))
        angles += angles[:1]

        ax4.plot(angles, top_vals, "o-", linewidth=2, label=f"Top: {top_stock}", color="green")
        ax4.fill(angles, top_vals, alpha=0.1, color="green")
        ax4.plot(angles, bottom_vals, "o-", linewidth=2, label=f"Bottom: {bottom_stock}", color="red")
        ax4.set_xticks(angles[:-1])
        ax4.set_xticklabels(labels, fontsize=8)
        ax4.set_title("Top vs Bottom 因子雷达图", fontsize=13, fontweight="bold")
        ax4.legend(fontsize=8, loc="upper right", bbox_to_anchor=(1.3, 1.0))

# — E: 累计IC和(累计收益) —
ax5 = fig.add_subplot(gs[2, :])
for idx, (name, mat) in enumerate(factor_matrices.items()):
    ic = pipeline.analyzer.calc_ic(mat, forward_ret)
    if not ic.empty:
        cum_ic = ic.cumsum()
        ax5.plot(ic.index, cum_ic.values, label=pipeline.factor_registry[name].name,
                 color=COLORS[idx], linewidth=0.8)
ax5.axhline(0, color="black", linewidth=0.5)
ax5.set_title("累计 IC (累积和)", fontsize=13, fontweight="bold")
ax5.legend(fontsize=8, ncol=3)
ax5.set_ylabel("累计IC")

# — F: 策略摘要表 —
ax6 = fig.add_subplot(gs[3, :])
ax6.axis("off")

summary_data = []
for name, mat in factor_matrices.items():
    ic = pipeline.analyzer.calc_ic(mat, forward_ret)
    if not ic.empty:
        group_ret = pipeline.analyzer.calc_group_returns(mat, forward_ret)
        ls_ret = (1 + group_ret.get(10, pd.Series(dtype=float))).prod() - 1 if 10 in group_ret else 0
        summary_data.append({
            "因子": pipeline.factor_registry[name].name,
            "类别": pipeline.factor_registry[name].category,
            "方向": "↑" if pipeline.factor_registry[name].direction == 1 else "↓",
            "IC均值": f"{ic.mean():.3f}",
            "ICIR": f"{ic.mean()/ic.std():.2f}",
            "IC>0": f"{(ic > 0).mean():.0%}",
            "多空收益": f"{ls_ret:.1%}",
            "期数": len(ic),
        })

summary_df = pd.DataFrame(summary_data)
col_labels = summary_df.columns.tolist()
cell_text = summary_df.values.tolist()
table = ax6.table(cellText=cell_text, colLabels=col_labels,
                  cellLoc="center", loc="center",
                  colWidths=[0.12]*len(col_labels))
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1, 1.6)
for key, cell in table.get_celld().items():
    if key[0] == 0:
        cell.set_facecolor("#2c3e50")
        cell.set_text_props(color="white", fontweight="bold")

ax6.set_title("因子分析摘要", fontsize=13, fontweight="bold", pad=20)

fig.suptitle("📊 A股多因子选股分析报告", fontsize=18, fontweight="bold", y=0.98)
fig.savefig(f"{OUTPUT_DIR}/05_dashboard.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✅ 已保存: {OUTPUT_DIR}/05_dashboard.png")

print(f"\n{'='*50}")
print(f"🎉 所有图表已保存到 {OUTPUT_DIR}/ 目录:")
print(f"{'='*50}")
for f in sorted(os.listdir(OUTPUT_DIR)):
    size = os.path.getsize(f"{OUTPUT_DIR}/{f}") / 1024
    print(f"  📈 {f}  ({size:.0f} KB)")
print(f"\n现在可以用图片查看器打开这些文件查看。")
