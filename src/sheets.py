"""
sheets.py - Google Sheets 読み書き
"""
import json
import logging
import time
from datetime import date
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# シート名定数
SHEET_TODAY = "今日の更新銘柄"
SHEET_RANKING = "ランキング"
SHEET_WATCHLIST = "ウォッチリスト"
SHEET_HISTORY = "履歴"

# ヘッダー定義
HEADERS_TODAY = ["銘柄コード", "銘柄名", "終値", "累計更新回数", "連続更新日数", "最終更新日"]
HEADERS_RANKING = ["順位", "銘柄コード", "銘柄名", "累計更新回数", "連続更新日数", "最終更新日", "時価総額"]
HEADERS_WATCHLIST = ["銘柄コード", "銘柄名", "累計更新回数", "連続更新日数", "最終更新日", "メモ"]
HEADERS_HISTORY = ["日付", "銘柄コード", "銘柄名", "終値"]

WRITE_DELAY = 1.2  # Sheets API レート制限対策（秒）


def _fmt_date(d) -> str:
    if isinstance(d, date):
        return d.strftime("%Y/%m/%d")
    return str(d) if d else ""


def _fmt_cap(mc: Optional[int]) -> str:
    if mc is None:
        return ""
    return f"{mc / 1_000_000_000:.0f}億円"


class SheetsClient:
    def __init__(self, credentials_json: str, spreadsheet_id: str):
        """
        credentials_json: サービスアカウントJSON文字列（環境変数から）
        spreadsheet_id: スプレッドシートID
        """
        creds_dict = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        self._gc = gspread.authorize(creds)
        self._ss = self._gc.open_by_key(spreadsheet_id)
        self._ensure_sheets()

    # ------------------------------------------------------------------ #
    # シート初期化
    # ------------------------------------------------------------------ #

    def _ensure_sheets(self):
        """必要なシートが存在しない場合は作成してヘッダーを書き込む"""
        existing = {ws.title for ws in self._ss.worksheets()}
        configs = [
            (SHEET_TODAY, HEADERS_TODAY),
            (SHEET_RANKING, HEADERS_RANKING),
            (SHEET_WATCHLIST, HEADERS_WATCHLIST),
            (SHEET_HISTORY, HEADERS_HISTORY),
        ]
        for name, headers in configs:
            if name not in existing:
                ws = self._ss.add_worksheet(title=name, rows=10000, cols=len(headers) + 2)
                ws.append_row(headers)
                logger.info(f"シート作成: {name}")
                time.sleep(WRITE_DELAY)

    def _get_sheet(self, name: str) -> gspread.Worksheet:
        return self._ss.worksheet(name)

    # ------------------------------------------------------------------ #
    # シート①: 今日の更新銘柄
    # ------------------------------------------------------------------ #

    def write_today(
        self,
        new_highs: list[dict],
        stats: dict[str, dict],
        target_date: date,
    ):
        """今日の更新銘柄シートを上書き"""
        ws = self._get_sheet(SHEET_TODAY)
        ws.clear()
        time.sleep(WRITE_DELAY)

        rows = [HEADERS_TODAY]
        for r in new_highs:
            code = r["code"]
            s = stats.get(code, {})
            rows.append([
                code,
                r["name"],
                r["close"],
                s.get("cumulative", 1),
                s.get("consecutive", 1),
                _fmt_date(target_date),
            ])

        ws.update(rows, value_input_option="USER_ENTERED")
        logger.info(f"今日の更新銘柄: {len(new_highs)} 件書き込み")
        time.sleep(WRITE_DELAY)

    # ------------------------------------------------------------------ #
    # シート②: ランキング
    # ------------------------------------------------------------------ #

    def write_ranking(self, ranking: list[dict]):
        """ランキングシートを上書き"""
        ws = self._get_sheet(SHEET_RANKING)
        ws.clear()
        time.sleep(WRITE_DELAY)

        rows = [HEADERS_RANKING]
        for r in ranking:
            rows.append([
                r["rank"],
                r["code"],
                r["name"],
                r["cumulative"],
                r["consecutive"],
                _fmt_date(r["last_date"]),
                _fmt_cap(r.get("market_cap")),
            ])

        ws.update(rows, value_input_option="USER_ENTERED")
        logger.info(f"ランキング: {len(ranking)} 件書き込み")
        time.sleep(WRITE_DELAY)

    # ------------------------------------------------------------------ #
    # シート③: ウォッチリスト
    # ------------------------------------------------------------------ #

    def update_watchlist(self, stats: dict[str, dict]):
        """
        ウォッチリストの既存銘柄コードに対して統計情報を更新する。
        ユーザーが入力したメモ（列F）は保持。
        """
        ws = self._get_sheet(SHEET_WATCHLIST)
        all_values = ws.get_all_values()

        if len(all_values) <= 1:
            # ヘッダーのみ or 空 → 何もしない
            return

        updates = []
        for row_idx, row in enumerate(all_values[1:], start=2):  # 1-indexed, row 1 = header
            if not row or not row[0].strip():
                continue
            code = row[0].strip().zfill(4)
            s = stats.get(code)
            if s is None:
                continue

            # B列〜F列を更新（メモ列=G は触らない）
            updates.append({
                "range": f"B{row_idx}:F{row_idx}",
                "values": [[
                    s["name"],
                    s["cumulative"],
                    s["consecutive"],
                    _fmt_date(s["last_date"]),
                    row[5] if len(row) > 5 else "",  # メモ列を保持
                ]],
            })

        if updates:
            # バッチ更新
            ws.batch_update(updates, value_input_option="USER_ENTERED")
            logger.info(f"ウォッチリスト更新: {len(updates)} 件")
            time.sleep(WRITE_DELAY)

    # ------------------------------------------------------------------ #
    # シート④: 履歴（内部管理）
    # ------------------------------------------------------------------ #

    def read_history(self) -> list[list]:
        """履歴シートから全レコードを取得（ヘッダー除く）"""
        ws = self._get_sheet(SHEET_HISTORY)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return []
        return rows[1:]  # ヘッダー除去

    def write_history(self, history_df):
        """
        履歴シートを完全上書き（DataFrameを受け取る）。
        差分更新より全上書きの方が冪等性が保ちやすい。
        """
        ws = self._get_sheet(SHEET_HISTORY)
        ws.clear()
        time.sleep(WRITE_DELAY)

        rows = [HEADERS_HISTORY]
        for _, row in history_df.iterrows():
            rows.append([
                _fmt_date(row["date"]),
                str(row["code"]).zfill(4),
                row["name"],
                row["close"],
            ])

        # 大量データは 500行単位でバッチ書き込み
        CHUNK = 500
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i : i + CHUNK]
            start_row = i + 1
            ws.update(
                f"A{start_row}",
                chunk,
                value_input_option="USER_ENTERED",
            )
            time.sleep(WRITE_DELAY)

        logger.info(f"履歴書き込み完了: {len(rows) - 1} 件")
