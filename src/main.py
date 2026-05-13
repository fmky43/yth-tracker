"""
main.py - 年初来高値トラッカー エントリーポイント
"""
import argparse
import logging
import os
import sys
from datetime import date

from analyzer import compute_stats, get_ranking, load_history, update_history
from fetcher import fetch_ytd_highs
from sheets import SheetsClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="年初来高値トラッカー（日本株）")
    parser.add_argument(
        "--date",
        help="対象日 YYYY-MM-DD（省略時は今日）",
        default=None,
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="JPX CSV取得を試みず日経225フォールバックを使用",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sheetsへの書き込みを行わず結果を標準出力のみ",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 対象日の決定
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error(f"日付形式が不正です: {args.date}（YYYY-MM-DD 形式で指定）")
            sys.exit(1)
    else:
        target_date = date.today()

    logger.info(f"=== 年初来高値トラッカー 開始: {target_date} ===")

    # 1. データ取得
    new_highs, is_market_closed = fetch_ytd_highs(
        target_date=target_date,
        use_fallback=args.fallback,
    )

    if is_market_closed:
        logger.info("休場日のため処理をスキップします")
        sys.exit(0)

    if not new_highs:
        logger.info("年初来高値更新銘柄なし（または取得エラー）")
        sys.exit(0)

    logger.info(f"年初来高値更新: {len(new_highs)} 銘柄")
    for r in new_highs[:10]:
        logger.info(f"  {r['code']} {r['name']} ¥{r['close']:,.0f}")
    if len(new_highs) > 10:
        logger.info(f"  ... 他 {len(new_highs) - 10} 銘柄")

    if args.dry_run:
        logger.info("--dry-run モード: Sheets書き込みをスキップ")
        sys.exit(0)

    # 2. 認証情報の取得
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")

    if not creds_json or not spreadsheet_id:
        logger.error("環境変数 GOOGLE_CREDENTIALS_JSON と SPREADSHEET_ID を設定してください")
        sys.exit(1)

    # 3. Sheetsクライアント初期化
    try:
        client = SheetsClient(creds_json, spreadsheet_id)
    except Exception as e:
        logger.error(f"Sheets初期化失敗: {e}")
        sys.exit(1)

    # 4. 履歴の読み込みと更新
    logger.info("履歴データ読み込み中...")
    history = load_history(client)
    updated_history = update_history(history, new_highs, target_date)
    logger.info(f"履歴レコード数: {len(updated_history)}")

    # 5. 統計計算
    stats = compute_stats(updated_history, target_date)
    ranking = get_ranking(stats)
    logger.info(f"アクティブ銘柄（ランキング対象）: {len(ranking)} 件")

    # 6. Sheets書き込み
    logger.info("シート①「今日の更新銘柄」書き込み中...")
    client.write_today(new_highs, stats, target_date)

    logger.info("シート②「ランキング」書き込み中...")
    client.write_ranking(ranking)

    logger.info("シート③「ウォッチリスト」更新中...")
    client.update_watchlist(stats)

    logger.info("シート④「履歴」書き込み中...")
    client.write_history(updated_history)

    logger.info(f"=== 完了: {len(new_highs)} 銘柄が年初来高値を更新 ===")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        with open(summary_path, "a") as f:
            f.write(f"- 年初来高値更新銘柄数: **{len(new_highs)} 銘柄**\n")
            f.write(f"- スプレッドシート: {sheet_url}\n")


if __name__ == "__main__":
    main()
