"""
批量补充股票数据
优先科创板，支持断点续传（缓存）

用法:
  python batch_fetch.py              # 获取所有剩余股票
  python batch_fetch.py --batch 500  # 只获取500只
"""
import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows GBK 兼容：设置控制台输出编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from data_fetcher import AStockDataFetcher, REQUEST_INTERVAL

START = "2026-01-01"
END = "2026-06-15"


def get_missing_stocks(fetcher, priority_prefix="688"):
    """获取未缓存股票列表，按优先级排序"""
    stocks = fetcher.get_stock_list()
    codes = stocks["stock_code"].tolist()
    codes = [c for c in codes if not c.startswith(("8", "4", "9", "688"))]  # 排除北交所、科创板

    cached = set()
    import glob
    prices_dir = os.path.join(fetcher.cache_dir, "prices")
    if os.path.isdir(prices_dir):
        for path in glob.glob(os.path.join(prices_dir, "*.parquet")):
            cached.add(os.path.splitext(os.path.basename(path))[0])

    missing = [c for c in codes if c not in cached]
    priority = [c for c in missing if c.startswith(priority_prefix)]
    others = [c for c in missing if not c.startswith(priority_prefix)]
    print(f"已缓存: {len(cached)}, 待获取: {len(missing)}")
    print(f"  优先: {len(priority)} 只({priority_prefix}xxx)")
    print(f"  其余: {len(others)} 只")
    return priority + others


def fetch_batch(fetcher, codes, start, end, batch_size=200):
    """按批次串行获取（AKShare V8引擎不支持并发）"""
    total = len(codes)
    fetched = 0
    failed = []

    for i, code in enumerate(codes, 1):
        try:
            df = fetcher.get_daily_price(code, start, end)
            if not df.empty:
                fetched += 1
            print(f"  [{i}/{total}] {code} {'✅' if not df.empty else '⏭️'}")
        except Exception as e:
            failed.append(code)
            print(f"  [{i}/{total}] {code} ❌ {type(e).__name__}")
            time.sleep(2)  # 出错后多等等

        # 进度报告
        if i % 50 == 0 or i == total:
            print(f"  进度: {i}/{total} (成功{fetched}, 失败{len(failed)})")

    return fetched, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量获取股票行情")
    parser.add_argument("--batch", type=int, default=0, help="本次获取数量, 0=全部")
    parser.add_argument("--priority", type=str, default="688", help="优先前缀")
    args = parser.parse_args()

    fetcher = AStockDataFetcher()
    missing = get_missing_stocks(fetcher, args.priority)

    if args.batch > 0:
        missing = missing[:args.batch]

    if not missing:
        print("✅ 所有股票已缓存，无需获取")
        sys.exit(0)

    print(f"\n开始获取 {len(missing)} 只股票...")
    t0 = time.time()
    ok, fail = fetch_batch(fetcher, missing, START, END)
    elapsed = time.time() - t0
    print(f"\n{'='*40}")
    print(f"完成! 成功{ok}, 失败{len(fail)}, 耗时{elapsed:.0f}s")
    if fail:
        print(f"失败列表(前10): {fail[:10]}")
    print(f"下次命令继续: python batch_fetch.py")
