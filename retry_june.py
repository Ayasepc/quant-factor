"""Retry June data"""
import akshare as ak, time
for i in range(3):
    try:
        df = ak.stock_zh_a_hist("601390","daily","20260601","20260612","qfq")
        print(f"OK: {len(df)} rows")
        if not df.empty:
            df.columns = ["date","code","open","close","high","low","vol","amt","amp","pct","chg","turn"]
            print(f"latest: {df.iloc[-1]['date']} close={df.iloc[-1]['close']} pct={df.iloc[-1]['pct']}")
        break
    except Exception as e:
        print(f"attempt {i+1}: {type(e).__name__}")
        time.sleep(2)
