"""
fetcher.py - 東証上場銘柄の年初来高値データ取得
"""
import io
import logging
import time
from datetime import date, timedelta
from typing import Optional

import jpholiday
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

JPX_CSV_URL = (
    "https://www.jpx.co.jp/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_j.csv"
)

EXCLUDE_KEYWORDS = [
    "ETF", "ＥＴＦ", "投信", "ファンド", "FUND", "ＦＵＮＤ",
    "REIT", "リート", "インフラファンド", "上場投資信託",
    "ＥＴＮ", "ETN", "J-REIT",
]

MARKET_CAP_THRESHOLD = 100_000_000_000  # 1000億円

# 東証個別株対象市場
TSE_INDIVIDUAL_MARKETS = [
    "プライム（内国株式）",
    "スタンダード（内国株式）",
    "グロース（内国株式）",
]

# 日経225フォールバック（4桁コード）
NIKKEI225_CODES = [
    1301, 1332, 1333, 1605, 1721, 1801, 1802, 1803, 1808, 1812,
    1925, 1928, 1963, 2002, 2269, 2282, 2413, 2502, 2503, 2531,
    2768, 2801, 2802, 2871, 2914, 3086, 3088, 3099, 3289, 3382,
    3401, 3402, 3405, 3407, 3436, 3659, 3861, 3863, 4004, 4005,
    4021, 4042, 4043, 4061, 4062, 4063, 4151, 4183, 4188, 4204,
    4208, 4324, 4452, 4502, 4503, 4506, 4507, 4519, 4523, 4543,
    4568, 4578, 4631, 4689, 4704, 4751, 4755, 4901, 4902, 4911,
    5019, 5020, 5101, 5108, 5201, 5202, 5214, 5232, 5233, 5301,
    5332, 5333, 5401, 5406, 5411, 5541, 5631, 5703, 5706, 5707,
    5711, 5713, 5714, 5715, 5802, 5803, 5901, 6098, 6103, 6113,
    6146, 6178, 6197, 6201, 6269, 6273, 6301, 6302, 6305, 6326,
    6361, 6367, 6370, 6383, 6412, 6417, 6471, 6472, 6473, 6479,
    6501, 6503, 6504, 6506, 6526, 6586, 6594, 6645, 6674, 6701,
    6702, 6703, 6723, 6724, 6752, 6753, 6758, 6762, 6770, 6841,
    6857, 6861, 6902, 6903, 6952, 6954, 6963, 6971, 6976, 6981,
    7003, 7004, 7011, 7012, 7013, 7186, 7201, 7202, 7203, 7205,
    7211, 7261, 7267, 7269, 7270, 7272, 7731, 7733, 7735, 7741,
    7751, 7752, 7762, 7832, 7911, 7912, 7951, 7974, 8001, 8002,
    8003, 8004, 8005, 8006, 8015, 8028, 8031, 8035, 8053, 8058,
    8233, 8252, 8253, 8267, 8303, 8304, 8306, 8308, 8309, 8316,
    8331, 8354, 8355, 8411, 8473, 8601, 8604, 8630, 8697, 8725,
    8750, 8766, 8795, 8801, 8802, 8804, 8830, 9001, 9005, 9007,
    9008, 9009, 9020, 9021, 9022, 9064, 9101, 9104, 9107, 9201,
    9202, 9301, 9432, 9433, 9434, 9501, 9502, 9503, 9531, 9532,
    9602, 9613, 9735, 9766, 9983, 9984,
]


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def prev_business_day(d: date) -> date:
    """d の直前の営業日"""
    prev = d - timedelta(days=1)
    while not is_business_day(prev):
        prev -= timedelta(days=1)
    return prev


def get_jpx_stock_list() -> Optional[pd.DataFrame]:
    """JPX公式CSVから東証個別株一覧を取得"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; YTH-Tracker/1.0)"}
        resp = requests.get(JPX_CSV_URL, headers=headers, timeout=30)
        resp.raise_for_status()

        df = pd.read_csv(io.BytesIO(resp.content), encoding="shift_jis")
        logger.info(f"JPX CSV取得: {len(df)} 行")

        # カラム名の動的解決
        code_col = next((c for c in df.columns if "コード" in c), None)
        name_col = next((c for c in df.columns if "銘柄名" in c), None)
        market_col = next((c for c in df.columns if "市場" in c), None)

        if not all([code_col, name_col, market_col]):
            raise ValueError(f"必要カラムが見つかりません: {df.columns.tolist()}")

        df = df.rename(columns={code_col: "code", name_col: "name", market_col: "market"})
        df = df[df["market"].isin(TSE_INDIVIDUAL_MARKETS)].copy()

        exclude_pat = "|".join(EXCLUDE_KEYWORDS)
        df = df[~df["name"].str.contains(exclude_pat, na=False)].copy()

        df["code"] = df["code"].astype(str).str.zfill(4)
        df = df[["code", "name"]].drop_duplicates("code").reset_index(drop=True)

        logger.info(f"個別株フィルタ後: {len(df)} 銘柄")
        return df

    except Exception as e:
        logger.error(f"JPX CSV取得失敗: {e}")
        return None


def get_nikkei225_fallback() -> pd.DataFrame:
    """日経225フォールバックリストを返す"""
    logger.warning("日経225フォールバックを使用")
    records = [{"code": str(c).zfill(4), "name": f"銘柄{c}"} for c in NIKKEI225_CODES]
    return pd.DataFrame(records)


def _download_prices(
    codes: list[str], year_start: date, target_date: date, chunk_size: int = 400
) -> pd.DataFrame:
    """yfinanceで全銘柄の価格データをチャンク単位で一括取得"""
    frames = []
    end_date = (target_date + timedelta(days=1)).isoformat()
    start_date = year_start.isoformat()

    for i in range(0, len(codes), chunk_size):
        chunk = codes[i : i + chunk_size]
        tickers = " ".join(f"{c}.T" for c in chunk)
        logger.info(f"価格取得 {i + 1}〜{min(i + chunk_size, len(codes))}/{len(codes)}")
        try:
            df = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True,
                threads=True,
            )
            if df.empty:
                continue

            # マルチインデックスの場合 Close を抽出
            if isinstance(df.columns, pd.MultiIndex):
                close = df["Close"].copy()
            else:
                # 単一銘柄ダウンロードの場合
                close = df[["Close"]].rename(columns={"Close": f"{chunk[0]}.T"})

            frames.append(close)
        except Exception as e:
            logger.error(f"チャンク取得エラー (i={i}): {e}")
        time.sleep(0.3)

    if not frames:
        return pd.DataFrame()

    # 日付インデックスを揃えて結合
    combined = pd.concat(frames, axis=1)
    combined.index = combined.index.normalize()
    return combined


def _filter_by_market_cap(
    ytd_hit_codes: list[str],
    names: dict[str, str],
    closes: dict[str, float],
) -> list[str]:
    """年初来高値更新銘柄に対して時価総額フィルタを適用"""
    passed = []
    for code in ytd_hit_codes:
        ticker = f"{code}.T"
        try:
            t = yf.Ticker(ticker)
            mc = t.fast_info.market_cap
            if mc is None or mc >= MARKET_CAP_THRESHOLD:
                passed.append(code)
            else:
                logger.debug(f"{code} 時価総額除外: {mc:,.0f}円")
        except Exception as e:
            logger.debug(f"{code} 時価総額取得失敗 → 残す: {e}")
            passed.append(code)  # 取得失敗時は除外しない
        time.sleep(0.1)
    return passed


def fetch_ytd_highs(
    target_date: Optional[date] = None,
    use_fallback: bool = False,
) -> tuple[list[dict], bool]:
    """
    指定日の年初来高値更新銘柄を返す。
    Returns:
        (results, is_market_closed)
        results: [{"code", "name", "close", "date"}, ...]
        is_market_closed: 休場日の場合 True
    """
    if target_date is None:
        target_date = date.today()

    if not is_business_day(target_date):
        logger.info(f"{target_date} は休場日")
        return [], True

    # 銘柄リスト取得
    stock_df = None if use_fallback else get_jpx_stock_list()
    if stock_df is None:
        stock_df = get_nikkei225_fallback()

    codes = stock_df["code"].tolist()
    names = dict(zip(stock_df["code"], stock_df["name"]))

    year_start = date(target_date.year, 1, 1)

    # 価格データ一括取得
    close_df = _download_prices(codes, year_start, target_date)
    if close_df.empty:
        logger.warning("価格データなし（休場の可能性）")
        return [], True

    # 当日データ存在確認
    target_ts = pd.Timestamp(target_date)
    today_row = close_df[close_df.index == target_ts]
    if today_row.empty:
        logger.warning(f"{target_date} のデータなし")
        return [], True

    today_close = today_row.iloc[-1]
    ytd_max = close_df.max()

    # 年初来高値更新銘柄を抽出
    ytd_hit_codes = []
    ytd_closes: dict[str, float] = {}

    for code in codes:
        col = f"{code}.T"
        if col not in close_df.columns:
            continue
        t_close = today_close.get(col)
        t_max = ytd_max.get(col)
        if pd.isna(t_close) or pd.isna(t_max) or t_max == 0:
            continue
        if float(t_close) >= float(t_max) * 0.99999:
            ytd_hit_codes.append(code)
            ytd_closes[code] = round(float(t_close), 2)

    logger.info(f"年初来高値候補: {len(ytd_hit_codes)} 銘柄（時価総額フィルタ前）")

    # 時価総額フィルタ（候補のみ対象）
    if ytd_hit_codes:
        ytd_hit_codes = _filter_by_market_cap(ytd_hit_codes, names, ytd_closes)

    results = [
        {
            "code": code,
            "name": names.get(code, ""),
            "close": ytd_closes[code],
            "date": target_date,
        }
        for code in ytd_hit_codes
    ]

    logger.info(f"確定: {len(results)} 銘柄が年初来高値を更新")
    return results, False
