"""中国中铁 2026年表现速查"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import akshare as ak

all_dfs = []
for m in range(1, 7):
    ym = f"2026{m:02d}"
    end = "20260612" if m == 6 else f"2026{m:02d}28"
    try:
        df = ak.stock_zh_a_hist("601390", "daily", f"{ym}01", end, "qfq")
        if not df.empty:
            all_dfs.append(df)
            print(f"{ym}: {len(df)} rows  OK")
        else:
            print(f"{ym}: empty")
    except Exception as e:
        print(f"{ym}: {type(e).__name__}")

if not all_dfs:
    print("无数据")
    exit()

raw = pd.concat(all_dfs, ignore_index=True)
raw.columns = ["date","code","open","close","high","low","vol","amt","amp","pct","chg","turn"]
raw["date"] = pd.to_datetime(raw["date"])

total = (1 + raw["pct"]/100).prod() - 1
print(f"\n中国中铁 (601390) 2026年表现")
print(f"{'='*40}")
print(f"区间:     {raw['date'].min().date()} ~ {raw['date'].max().date()}")
print(f"交易日数: {len(raw)}")
print(f"起始收盘: {raw.iloc[0]['close']:.2f}")
print(f"最新收盘: {raw.iloc[-1]['close']:.2f}")
print(f"累计收益: {total:.2%}")
print(f"区间最高: {raw['high'].max():.2f}")
print(f"区间最低: {raw['low'].min():.2f}")
print(f"涨幅>5%:  {(raw['pct']>5).sum()} 天")
print(f"跌幅>5%:  {(raw['pct']<-5).sum()} 天")

print(f"\n月度明细:")
for ym, g in raw.groupby(raw["date"].dt.to_period("M")):
    ret = (1 + g["pct"]/100).prod() - 1
    cum = (1 + g["pct"]/100).cumprod()
    print(f"  {ym}: {ret:>+6.2%}  "
          f"区间振幅 {g['high'].max()/g['low'].min()-1:.2%}  "
          f"日均量 {g['vol'].mean()/1e8:.1f}亿")

print(f"\n最近5日:")
for _, r in raw.tail(5).iterrows():
    print(f"  {r['date'].date()}  "
          f"收:{r['close']:.2f}  {r['pct']:+.2f}%  "
          f"量:{r['vol']/1e8:.1f}亿")

# 对比沪深300
try:
    hs = ak.stock_zh_index_daily(symbol="sh000300")
    hs = hs[hs["date"] >= "2026-01-01"]
    if len(hs) > 1:
        hs_ret = hs["close"].iloc[-1] / hs["close"].iloc[0] - 1
        print(f"\n同期沪深300: {hs_ret:.2%}")
        print(f"超额收益:    {total - hs_ret:.2%}")
except Exception as e:
    print(f"沪深300对比: {e}")
