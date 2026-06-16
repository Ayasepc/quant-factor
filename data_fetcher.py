"""
A股数据获取模块
使用 AKShare (免费开源) 获取股票行情、财务数据
增加: 重试机制、请求间隔、本地缓存
"""

import os
import time
import json
import pandas as pd
import numpy as np
from typing import Optional, Callable
from datetime import datetime, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import akshare as ak
from config import UNIVERSE_CONFIG


# 请求间隔（秒）
REQUEST_INTERVAL = 0.2
# 并发线程数（AKShare V8 引擎限制，3以下较安全）
CONCURRENT_WORKERS = 3


def retry(max_attempts=3, delay=2):
    """API 调用重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, max_attempts + 1):
                try:
                    time.sleep(REQUEST_INTERVAL)
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)
                    continue
            raise last_err
        return wrapper
    return decorator


def _batch_fetch(codes: list, fetch_func: Callable, label: str,
                 max_workers: int = None) -> tuple:
    """
    并发批量获取数据

    Args:
        codes: 待获取的股票代码列表
        fetch_func: 单只股票获取函数 fn(code) -> DataFrame
        label: 进度标签

    Returns:
        (成功DataFrame列表, 失败代码列表)
    """
    if max_workers is None:
        max_workers = CONCURRENT_WORKERS

    total = len(codes)
    results = [None] * total
    errors = []
    _lock = threading.Lock()
    _counter = [0]

    def worker(idx, code):
        try:
            time.sleep(0.15)  # 小间隔防限流
            df = fetch_func(code)
            with _lock:
                _counter[0] += 1
                done = _counter[0]
                if df is not None and not df.empty:
                    results[idx] = df
                    print(f"  [{done}/{total}] {code} ✅", flush=True)
                else:
                    print(f"  [{done}/{total}] {code} ⏭️", flush=True)
        except Exception as e:
            with _lock:
                _counter[0] += 1
                done = _counter[0]
                errors.append(code)
                print(f"  [{done}/{total}] {code} ❌ {type(e).__name__}", flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(worker, i, code) for i, code in enumerate(codes)]
        for f in as_completed(futures):
            f.result()  # 触发异常

    success = [df for df in results if df is not None]
    return success, errors


class AStockDataFetcher:
    """A股数据获取器"""

    def __init__(self, cache_dir: str = "data"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ──────────────────────────────────────────
    # 1. 股票列表 & 行情
    # ──────────────────────────────────────────

    @retry(max_attempts=2)
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全A股股票列表（沪市+深市）

        通过新浪财经 API 分页获取，覆盖所有 A 股（含主板、创业板）
        """
        cache_path = os.path.join(self.cache_dir, "stock_list.parquet")
        if os.path.exists(cache_path):
            return pd.read_parquet(cache_path)

        records = []
        import requests as req

        for node in ["sh_a", "sz_a"]:
            page = 1
            while True:
                url = (
                    f"http://vip.stock.finance.sina.com.cn/quotes_service"
                    f"/api/json_v2.php/Market_Center.getHQNodeData"
                    f"?page={page}&num=100&sort=symbol&asc=1&node={node}"
                )
                try:
                    r = req.get(url, timeout=10)
                    data = json.loads(r.text)
                    if not data or (isinstance(data, list) and len(data) == 0):
                        break
                    for item in data:
                        records.append({
                            "stock_code": item["code"],
                            "stock_name": item.get("name", ""),
                        })
                    if len(data) < 100:
                        break
                    page += 1
                    time.sleep(0.3)
                except Exception:
                    break

        df = pd.DataFrame(records).drop_duplicates(subset="stock_code")
        if df.empty:
            raise RuntimeError("无法获取股票列表，请检查网络连接")
        df.to_parquet(cache_path)
        sh_count = sum(1 for c in df["stock_code"] if c.startswith("6"))
        sz_count = sum(1 for c in df["stock_code"] if c.startswith(("0", "3", "2")))
        print(f"  股票列表: {len(df)} 只 (沪{sh_count} + 深{sz_count})")
        return df

    @staticmethod
    def _code_to_sina_symbol(code: str) -> str:
        """将6位股票代码转为新浪前缀格式"""
        if code.startswith("6") or code.startswith("9"):
            return f"sh{code}"
        elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
            return f"sz{code}"
        elif code.startswith("4") or code.startswith("8"):
            return f"bj{code}"
        return code

    @retry(max_attempts=3)
    def get_daily_price(
        self, stock_code: str, start_date: str, end_date: str,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取个股日线行情（增量缓存）

        首次获取全量，后续只拉取缺失日期的新数据合并。
        缓存文件: data/prices/{code}.parquet（累积，无日期范围）
        """
        prices_dir = os.path.join(self.cache_dir, "prices")
        os.makedirs(prices_dir, exist_ok=True)
        cache_path = os.path.join(prices_dir, f"{stock_code}.parquet")

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        # 尝试加载已有缓存
        existing = None
        if use_cache and os.path.exists(cache_path):
            try:
                existing = pd.read_parquet(cache_path)
                existing["date"] = pd.to_datetime(existing["date"])
                existing = existing.sort_values("date")
            except Exception:
                existing = None

        # 确定需要获取的日期范围
        need_fetch = True
        if existing is not None and not existing.empty:
            cached_min = existing["date"].min()
            cached_max = existing["date"].max()

            if cached_min <= start_dt and cached_max >= end_dt:
                # 缓存已覆盖请求范围，直接返回子集
                return existing[(existing["date"] >= start_dt) & (existing["date"] <= end_dt)].copy()
            elif cached_max >= end_dt:
                # 需要更早的数据（start_date 提前了）
                fetch_start = start_date
                fetch_end = (cached_min - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # 需要更新的数据（end_date 延后了）
                fetch_start = (cached_max + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                fetch_end = end_date
        else:
            fetch_start = start_date
            fetch_end = end_date

        # 拉取新数据
        try:
            symbol = self._code_to_sina_symbol(stock_code)
            new_df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=fetch_start.replace("-", ""),
                end_date=fetch_end.replace("-", ""),
                adjust="qfq",
            )
        except Exception:
            try:
                new_df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    start_date=fetch_start.replace("-", ""),
                    end_date=fetch_end.replace("-", ""),
                    adjust="qfq",
                )
            except Exception as e:
                raise e

        if new_df.empty and existing is None:
            return pd.DataFrame()

        # 合并新旧数据
        parts = []
        if existing is not None:
            parts.append(existing)
        if not new_df.empty:
            # 统一列名
            new_df["stock_code"] = stock_code
            new_df["date"] = pd.to_datetime(new_df["date"])
            # 计算衍生指标
            new_df["pct_change"] = new_df.groupby("stock_code")["close"].transform("pct_change") * 100
            new_df["pct_change"] = new_df["pct_change"].fillna(0)
            new_df["amplitude"] = (new_df["high"] - new_df["low"]) / new_df["low"] * 100
            new_df["change"] = new_df["close"] - new_df["open"]
            parts.append(new_df)

        combined = pd.concat(parts, ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

        # 保存完整缓存
        combined.to_parquet(cache_path, index=False)

        return combined[(combined["date"] >= start_dt) & (combined["date"] <= end_dt)].copy()

    def get_all_daily_price(
        self, start_date: str, end_date: str,
        stock_list: Optional[list] = None,
        max_stocks: int = 10,
    ) -> pd.DataFrame:
        """
        批量获取多只股票日线行情（并发版）

        Args:
            max_stocks: 最大股票数，-1 表示不限制
        """
        if stock_list is None:
            stocks = self.get_stock_list()
            stock_list = stocks["stock_code"].tolist()

        stock_list = [
            c for c in stock_list
            if not (c.startswith("8") or c.startswith("4") or c.startswith("9"))
        ]
        if max_stocks > 0 and len(stock_list) > max_stocks:
            stock_list = stock_list[:max_stocks]

        total = len(stock_list)
        if total == 0:
            return pd.DataFrame()

        print(f"  并发获取 {total} 只股票行情...")

        def fetch_one(code):
            return self.get_daily_price(code, start_date, end_date)

        # 检查增量缓存：只拉取缺失的
        prices_dir = os.path.join(self.cache_dir, "prices")
        all_dfs = []
        remaining = []
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        for code in stock_list:
            cache_path = os.path.join(prices_dir, f"{code}.parquet")
            if os.path.exists(cache_path):
                try:
                    meta = pd.read_parquet(cache_path)
                    if not meta.empty:
                        meta_date = pd.to_datetime(meta["date"])
                        if meta_date.min() <= start_dt and meta_date.max() >= end_dt:
                            subset = meta[(meta_date >= start_dt) & (meta_date <= end_dt)]
                            if not subset.empty:
                                all_dfs.append(subset)
                                continue
                except Exception:
                    pass
            remaining.append(code)

        if remaining:
            print(f"  缓存命中 {len(all_dfs)}/{total}，仍需获取 {len(remaining)} 只")
            success, failed = _batch_fetch(
                remaining,
                fetch_one,
                "行情",
                max_workers=CONCURRENT_WORKERS,
            )
            all_dfs.extend(success)
        else:
            print(f"  全部缓存命中! {len(all_dfs)}/{total}")

        if all_dfs:
            result = pd.concat(all_dfs, ignore_index=True)
            print(f"\n成功: {len(all_dfs)} / {total} 只股票")
            return result
        return pd.DataFrame()

    # ──────────────────────────────────────────
    # 2. 财务数据
    # ──────────────────────────────────────────

    def get_financial_data(
        self, stock_code: str, start_year: int = 2019
    ) -> dict:
        """获取个股主要财务指标"""
        try:
            income = ak.stock_financial_report_sina(
                stock=stock_code, symbol="利润表"
            )
            balance = ak.stock_financial_report_sina(
                stock=stock_code, symbol="资产负债表"
            )
            if income.empty or balance.empty:
                return {}

            return {
                "report_date": income["报告期"].iloc[0],
                "revenue": self._safe_extract(income, "营业收入"),
                "cost": self._safe_extract(income, "营业成本"),
                "net_profit": self._safe_extract(income, "净利润"),
                "total_assets": self._safe_extract(balance, "资产总计"),
                "equity": self._safe_extract(balance, "股东权益合计"),
            }
        except Exception:
            return {}

    def get_financial_indicators(self, stock_code: str) -> pd.DataFrame:
        """获取个股常用财务指标"""
        try:
            return ak.stock_financial_abstract(symbol=stock_code)
        except Exception:
            return pd.DataFrame()

    # ──────────────────────────────────────────
    # 3. 股票池筛选
    # ──────────────────────────────────────────

    def get_universe(self, date: str = None) -> list:
        """获取符合筛选条件的股票池 (排除北交所、科创板)"""
        stocks = self.get_stock_list()
        codes = stocks["stock_code"].tolist()

        result = []
        for code in codes:
            if code.startswith("8") or code.startswith("4") or code.startswith("9") or code.startswith("688"):
                continue
            result.append(code)

        print(f"股票池: {len(result)} 只 (排除北交所、科创板)")
        return result

    # ──────────────────────────────────────────
    # 4. 财务数据增强 (合并到行情DataFrame)
    # ──────────────────────────────────────────

    def enrich_with_financial_data(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        获取财务指标并合并到行情数据中（并发版）

        Returns:
            新增列: roe, roa, gross_margin, net_margin,
                    eps_ttm, bvps, pe_ttm, pb, revenue_yoy, profit_yoy
        """
        stock_codes = price_df["stock_code"].unique()
        total = len(stock_codes)
        print(f"\n[财务] 并发获取 {total} 只股票的财务数据...")

        # 预分组：按股票代码切分 price_df
        stock_groups = {
            code: g.sort_values("date")
            for code, g in price_df.groupby("stock_code")
        }

        fin_cache_dir = os.path.join(self.cache_dir, "fin_cache")
        os.makedirs(fin_cache_dir, exist_ok=True)

        def fetch_and_merge(code):
            """获取单只股票的财务数据并合并"""
            stock_data = stock_groups[code]
            cache_path = os.path.join(fin_cache_dir, f"{code}.parquet")
            if os.path.exists(cache_path):
                merged = pd.read_parquet(cache_path)
                # 只取与原始数据日期范围匹配的行
                merged = merged[merged["date"].isin(stock_data["date"])]
                if not merged.empty:
                    return merged

            try:
                time.sleep(0.15)
                fin_raw = ak.stock_financial_abstract(symbol=code)
                if fin_raw.empty:
                    return stock_data

                fin_ts = self._parse_financial_to_ts(fin_raw)
                if fin_ts.empty:
                    return stock_data

                merged = pd.merge_asof(
                    stock_data,
                    fin_ts.sort_values("report_date"),
                    left_on="date",
                    right_on="report_date",
                    direction="backward",
                )
                merged = self._calc_derived_factors(merged)
                for col in ["report_date", "eps", "revenue", "net_profit"]:
                    if col in merged.columns:
                        merged.drop(columns=[col], inplace=True)

                merged.to_parquet(cache_path, index=False)
                return merged
            except Exception:
                return stock_data

        success, errors = _batch_fetch(
            list(stock_codes),
            fetch_and_merge,
            "财务",
            max_workers=min(CONCURRENT_WORKERS, 8),
        )

        if errors:
            # 失败的用原始价格数据兜底
            for code in errors:
                success.append(stock_groups[code])

        result = pd.concat(success, ignore_index=True)
        print(f"\n  [财务] 已合并: {result.shape[0]} 行 × {result.shape[1]} 列 ({total} 只)")
        return result

    def _parse_financial_to_ts(self, fin_df: pd.DataFrame) -> pd.DataFrame:
        """
        将 stock_financial_abstract 转为时间序列
        返回: DataFrame(report_date, roe, roa, gross_margin, net_margin,
                        eps, bvps, revenue, net_profit)
        """
        ind_map = {}
        for _, row in fin_df.iterrows():
            ind_map[row["指标"]] = row

        date_cols = [c for c in fin_df.columns if c not in ["选项", "指标"]]
        date_cols = sorted(date_cols)

        records = []
        prev_row = {}  # 上一期的财务数，用于计算TTM

        for date_str in date_cols:
            date = pd.to_datetime(date_str)
            rec = {"report_date": date}

            for key, col_name in [
                ("roe", "净资产收益率(ROE)"),
                ("roa", "总资产报酬率(ROA)"),
                ("gross_margin", "毛利率"),
                ("net_margin", "销售净利率"),
                ("eps", "基本每股收益"),
                ("bvps", "每股净资产"),
            ]:
                if col_name in ind_map:
                    rec[key] = self._safe_float(ind_map[col_name].get(date_str, None))

            # 净利润和营收（用于 YoY 计算）
            for key, col_name in [("net_profit", "净利润"), ("revenue", "营业总收入")]:
                if col_name in ind_map:
                    rec[key] = self._safe_float(ind_map[col_name].get(date_str, None))

            # 计算 YoY 增长率（与上年同期对比）
            for key in ["revenue", "net_profit"]:
                if key in rec and key in prev_row:
                    prev_val = prev_row.get(key)
                    curr_val = rec[key]
                    if prev_val and prev_val != 0 and curr_val is not None:
                        rec[f"{key}_yoy"] = (curr_val / prev_val - 1) * 100

            records.append(rec)
            prev_row = rec.copy()  # 存作下期对比基准（简化为同比）

        if not records:
            return pd.DataFrame()

        ts = pd.DataFrame(records)

        # 计算 TTM EPS（最近4个季度的EPS之和）
        ts["eps_ttm"] = ts["eps"].rolling(4, min_periods=1).sum()
        # 若无4期数据，用年化估算
        mask = ts["eps_ttm"].isna()
        if mask.any():
            for idx in ts[mask].index:
                q = len(ts) - idx  # 可用期数
                if ts.loc[idx, "eps"] and q > 0:
                    ts.loc[idx, "eps_ttm"] = ts.loc[idx, "eps"] * (4 / max(q, 1))

        return ts

    @staticmethod
    def _calc_derived_factors(df: pd.DataFrame) -> pd.DataFrame:
        """从基础数据计算 PE/PB 等衍生因子"""
        # PE_TTM = 价格 / TTM每股收益
        if "eps_ttm" in df.columns and "close" in df.columns:
            eps = df["eps_ttm"].replace(0, np.nan)
            df["pe_ttm"] = df["close"] / eps

        # PB = 价格 / 每股净资产
        if "bvps" in df.columns and "close" in df.columns:
            bv = df["bvps"].replace(0, np.nan)
            df["pb"] = df["close"] / bv

        # 营收增长率重命名
        if "revenue_yoy" in df.columns:
            df["revenue_yoy"] = df["revenue_yoy"]
        if "net_profit_yoy" in df.columns:
            df["profit_yoy"] = df["net_profit_yoy"]

        return df

    # ──────────────────────────────────────────
    # 内部辅助
    # ──────────────────────────────────────────

    @staticmethod
    def _safe_extract(df: pd.DataFrame, keyword: str) -> float:
        mask = df.iloc[:, 0].astype(str).str.contains(keyword, na=False)
        if mask.any():
            val = df.loc[mask, df.columns[-1]].iloc[0]
            try:
                return float(val)
            except (ValueError, TypeError):
                return np.nan
        return np.nan

    @staticmethod
    def _safe_float(val) -> float:
        """安全转 float，失败返回 nan"""
        try:
            return float(val) if val is not None and val != "" else np.nan
        except (ValueError, TypeError):
            return np.nan
