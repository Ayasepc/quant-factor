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
from typing import Optional
from datetime import datetime, timedelta
from functools import wraps
import akshare as ak
from config import UNIVERSE_CONFIG


# 请求间隔（秒），避免触发 API 限流
REQUEST_INTERVAL = 1.0


def retry(max_attempts=3, delay=2):
    """API 调用重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, max_attempts + 1):
                try:
                    time.sleep(REQUEST_INTERVAL)  # 请求间隔
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)
                    continue
            raise last_err
        return wrapper
    return decorator


class AStockDataFetcher:
    """A股数据获取器"""

    def __init__(self, cache_dir: str = "data"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ──────────────────────────────────────────
    # 1. 股票列表 & 行情
    # ──────────────────────────────────────────

    @retry(max_attempts=3)
    def get_stock_list(self) -> pd.DataFrame:
        """获取全A股股票列表"""
        cache_path = os.path.join(self.cache_dir, "stock_list.parquet")
        if os.path.exists(cache_path):
            return pd.read_parquet(cache_path)

        df = ak.stock_info_a_code_name()
        df.columns = ["stock_code", "stock_name"]
        df.to_parquet(cache_path)
        return df

    @retry(max_attempts=3)
    def get_daily_price(
        self, stock_code: str, start_date: str, end_date: str,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """获取个股日线行情 (带缓存)"""
        cache_path = os.path.join(
            self.cache_dir, f"price_{stock_code}_{start_date}_{end_date}.parquet"
        )
        if use_cache and os.path.exists(cache_path):
            return pd.read_parquet(cache_path)

        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
        if df.empty:
            return pd.DataFrame()

        df.columns = [
            "date", "stock_code", "open", "close", "high", "low",
            "volume", "amount", "amplitude", "pct_change",
            "change", "turnover",
        ]
        df["date"] = pd.to_datetime(df["date"])
        # API 已返回 stock_code，确保统一
        df["stock_code"] = stock_code

        if use_cache:
            df.to_parquet(cache_path)
        return df

    def get_all_daily_price(
        self, start_date: str, end_date: str,
        stock_list: Optional[list] = None,
        max_stocks: int = 10,  # 演示默认只取10只
    ) -> pd.DataFrame:
        """
        批量获取多只股票日线行情

        Args:
            max_stocks: 最大股票数，-1 表示不限制
        """
        if stock_list is None:
            stocks = self.get_stock_list()
            stock_list = stocks["stock_code"].tolist()

        # 过滤无效代码
        stock_list = [
            c for c in stock_list
            if not (c.startswith("8") or c.startswith("4") or c.startswith("9"))
        ]

        if max_stocks > 0 and len(stock_list) > max_stocks:
            stock_list = stock_list[:max_stocks]

        total = len(stock_list)
        all_dfs = []
        failed = []

        for i, code in enumerate(stock_list, 1):
            try:
                df = self.get_daily_price(code, start_date, end_date)
                if not df.empty:
                    all_dfs.append(df)
                    print(f"  [{i}/{total}] {code} ✅")
                else:
                    print(f"  [{i}/{total}] {code} ⏭️ (空数据)")
            except Exception as e:
                failed.append(code)
                print(f"  [{i}/{total}] {code} ❌ {type(e).__name__}")

        if all_dfs:
            result = pd.concat(all_dfs, ignore_index=True)
            print(f"\n成功: {len(all_dfs)} / {total} 只股票")
            if failed:
                print(f"失败: {len(failed)} 只: {failed[:5]}...")
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
        """获取符合筛选条件的股票池 (仅简单排除北交所)"""
        stocks = self.get_stock_list()
        codes = stocks["stock_code"].tolist()

        result = []
        for code in codes:
            if code.startswith("8") or code.startswith("4") or code.startswith("9"):
                continue
            result.append(code)

        print(f"股票池: {len(result)} 只 (已排除北交所)")
        return result

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
