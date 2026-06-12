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


# 请求间隔（秒），AKShare 限流约 3 次/秒
REQUEST_INTERVAL = 0.35


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
        """获取全A股股票列表（上交所+深交所）"""
        cache_path = os.path.join(self.cache_dir, "stock_list.parquet")
        if os.path.exists(cache_path):
            return pd.read_parquet(cache_path)

        records = []
        # 上交所
        try:
            sh = ak.stock_info_sh_name_code()
            for _, r in sh.iterrows():
                records.append({"stock_code": str(r["证券代码"]), "stock_name": r["证券简称"]})
        except Exception:
            pass
        # 深交所
        try:
            sz = ak.stock_info_sz_name_code(symbol="A股列表")
            for _, r in sz.iterrows():
                records.append({"stock_code": str(r["A股代码"]), "stock_name": r["A股简称"]})
        except Exception:
            pass

        df = pd.DataFrame(records)
        if df.empty:
            raise RuntimeError("无法获取股票列表，请检查网络连接")
        df.to_parquet(cache_path)
        print(f"  股票列表: {len(df)} 只 (上证{len(sh) if 'sh' in dir() else 0} + 深证{len(sz) if 'sz' in dir() else 0})")
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
        """获取个股日线行情 (带缓存，使用新浪接口)"""
        cache_path = os.path.join(
            self.cache_dir, f"price_{stock_code}_{start_date}_{end_date}.parquet"
        )
        if use_cache and os.path.exists(cache_path):
            return pd.read_parquet(cache_path)

        try:
            symbol = self._code_to_sina_symbol(stock_code)
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
        except Exception:
            # 回退到东方财富接口
            try:
                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adjust="qfq",
                )
            except Exception as e:
                raise e

        if df.empty:
            return pd.DataFrame()

        # 统一列名（新浪接口列名不同）
        df["stock_code"] = stock_code
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={
            "volume": "volume",
            "outstanding_share": "outstanding_share",
        })
        # 计算涨跌幅
        df["pct_change"] = df.groupby("stock_code")["close"].transform("pct_change") * 100
        df["pct_change"] = df["pct_change"].fillna(0)
        # 计算振幅
        df["amplitude"] = (df["high"] - df["low"]) / df["low"] * 100
        # 计算涨跌额
        df["change"] = df["close"] - df["open"]

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
    # 4. 财务数据增强 (合并到行情DataFrame)
    # ──────────────────────────────────────────

    def enrich_with_financial_data(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        获取财务指标并合并到行情数据中

        为每个股票获取季度财务报告，前向填充到每个交易日，
        合并为带财务指标的完整DataFrame

        Returns:
            新增列: roe, roa, gross_margin, net_margin,
                    eps_ttm, bvps, pe_ttm, pb,
                    revenue_yoy, profit_yoy
        """
        stock_codes = price_df["stock_code"].unique()
        print(f"\n[财务] 获取 {len(stock_codes)} 只股票的财务数据...")
        all_parts = []

        for i, code in enumerate(stock_codes, 1):
            stock_data = price_df[price_df["stock_code"] == code].sort_values("date").copy()
            try:
                fin_raw = self.get_financial_indicators(code)
                if fin_raw.empty:
                    all_parts.append(stock_data)
                    continue

                fin_ts = self._parse_financial_to_ts(fin_raw)
                if fin_ts.empty:
                    all_parts.append(stock_data)
                    continue

                # 使用 merge_asof 前向填充：每个交易日取最新季度数据
                merged = pd.merge_asof(
                    stock_data,
                    fin_ts.sort_values("report_date"),
                    left_on="date",
                    right_on="report_date",
                    direction="backward",
                )
                # 计算 PE/PB 等衍生指标
                merged = self._calc_derived_factors(merged)
                # 删除冗余字段
                for col in ["report_date", "eps", "revenue", "net_profit"]:
                    if col in merged.columns:
                        merged.drop(columns=[col], inplace=True)

                all_parts.append(merged)
                print(f"  [财务/{i}/{len(stock_codes)}] {code} ✅")
            except Exception as e:
                all_parts.append(stock_data)
                print(f"  [财务/{i}/{len(stock_codes)}] {code} ⚠️ {type(e).__name__}")
                continue

        result = pd.concat(all_parts, ignore_index=True)
        print(f"  [财务] 已合并: {result.shape[0]} 行, {result.shape[1]} 列")
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
