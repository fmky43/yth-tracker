"""
analyzer.py - 累計更新回数・連続更新日数の集計ロジック
"""
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

import jpholiday
import pandas as pd

if TYPE_CHECKING:
    from sheets import SheetsClient

logger = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 5  # アクティブ判定の営業日数


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def prev_business_day(d: date) -> date:
    """d の直前の営業日"""
    prev = d - timedelta(days=1)
    while not is_business_day(prev):
        prev -= timedelta(days=1)
    return prev


def business_days_between(start: date, end: date) -> int:
    """start から end までの営業日数（端点含む）"""
    count = 0
    cur = start
    while cur <= end:
        if is_business_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


def load_history(client: "SheetsClient") -> pd.DataFrame:
    """
    履歴シートから全レコードを読み込む。
    Returns: DataFrame[date, code, name, close]
    """
    try:
        records = client.read_history()
        if not records:
            return pd.DataFrame(columns=["date", "code", "name", "close"])

        df = pd.DataFrame(records, columns=["date", "code", "name", "close"])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df
    except Exception as e:
        logger.error(f"履歴読み込みエラー: {e}")
        return pd.DataFrame(columns=["date", "code", "name", "close"])


def update_history(
    history: pd.DataFrame, new_highs: list[dict], target_date: date
) -> pd.DataFrame:
    """
    今日の更新銘柄を履歴に追加する。
    同日・同銘柄の重複は上書き（再実行時の冪等性確保）。
    """
    if not new_highs:
        return history

    new_rows = pd.DataFrame(
        [
            {
                "date": r["date"],
                "code": r["code"],
                "name": r["name"],
                "close": r["close"],
            }
            for r in new_highs
        ]
    )

    # 同日の既存レコードを削除してから追加（再実行対応）
    mask = history["date"] == target_date
    history_without_today = history[~mask].copy()

    updated = pd.concat([history_without_today, new_rows], ignore_index=True)
    updated = updated.sort_values(["date", "code"]).reset_index(drop=True)
    return updated


def calc_consecutive_days(
    code_dates: list[date], target_date: date
) -> int:
    """
    連続更新日数を計算。
    target_date から遡って営業日ベースで連続している日数を返す。
    """
    date_set = set(code_dates)

    if target_date not in date_set:
        return 0

    consecutive = 1
    current = target_date

    while True:
        prev = prev_business_day(current)
        if prev in date_set:
            consecutive += 1
            current = prev
        else:
            break

    return consecutive


def compute_stats(
    history: pd.DataFrame, target_date: date
) -> dict[str, dict]:
    """
    全銘柄の統計情報を計算する。
    Returns:
        {code: {"name", "cumulative", "consecutive", "last_date", "market_cap"}}
    """
    if history.empty:
        return {}

    year_start = date(target_date.year, 1, 1)
    year_history = history[history["date"] >= year_start].copy()

    stats: dict[str, dict] = {}

    for code, group in year_history.groupby("code"):
        dates = sorted(group["date"].tolist())
        name = group["name"].iloc[-1]

        last_date = max(dates)
        cumulative = len(dates)
        consecutive = calc_consecutive_days(dates, last_date)

        # 最終更新日から経過営業日数
        days_elapsed = 0
        cur = last_date
        while cur < target_date:
            cur = cur + timedelta(days=1)
            if is_business_day(cur):
                days_elapsed += 1

        stats[str(code)] = {
            "name": name,
            "cumulative": cumulative,
            "consecutive": consecutive,
            "last_date": last_date,
            "days_elapsed": days_elapsed,
            "is_active": days_elapsed <= ACTIVE_WINDOW_DAYS,
        }

    return stats


def get_ranking(
    stats: dict[str, dict],
    market_caps: dict[str, Optional[int]] = None,
) -> list[dict]:
    """
    アクティブ銘柄を累計更新回数順で返す。
    """
    if market_caps is None:
        market_caps = {}

    active = [
        {
            "code": code,
            "name": s["name"],
            "cumulative": s["cumulative"],
            "consecutive": s["consecutive"],
            "last_date": s["last_date"],
            "market_cap": market_caps.get(code),
            "is_active": s["is_active"],
        }
        for code, s in stats.items()
        if s["is_active"]
    ]

    active.sort(key=lambda x: (-x["cumulative"], -x["consecutive"]))

    for i, row in enumerate(active, 1):
        row["rank"] = i

    return active
