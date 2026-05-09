# 年初来高値トラッカー（日本株）

東証上場の個別株を対象に、毎日「年初来高値を更新した銘柄」を自動取得・Google Sheetsに記録するツールです。

## 機能

- 毎日15:35 JSTに自動実行（GitHub Actions）
- 東証全銘柄（プライム・スタンダード・グロース）から時価総額1000億円以上を対象
- 年初来高値更新銘柄を自動検出・Google Sheetsに記録
- 累計更新回数・連続更新日数を自動集計
- ウォッチリスト機能（銘柄コード入力で自動追跡）
- 過去日指定による遡り取得対応

## Google Sheets の構成

| シート | 内容 |
|--------|------|
| 今日の更新銘柄 | 当日の年初来高値更新銘柄一覧（毎日上書き） |
| ランキング | 直近10営業日以内に更新したアクティブ銘柄（累計回数順） |
| ウォッチリスト | ユーザーが監視したい銘柄を登録（手動入力） |
| 履歴 | 全更新履歴（削除しない） |

## セットアップ

1. このリポジトリをフォーク
2. [docs/setup_gcp.md](docs/setup_gcp.md) に従って Google Cloud と GitHub Secrets を設定
3. Actions タブからテスト実行

## ローカル実行

```bash
pip install -r requirements.txt

# 環境変数を設定
export GOOGLE_CREDENTIALS_JSON='{"type": "service_account", ...}'
export SPREADSHEET_ID='your_spreadsheet_id'

# 今日のデータを取得
python src/main.py

# 特定日を指定
python src/main.py --date 2024-01-15

# 書き込みなしでテスト
python src/main.py --dry-run

# 日経225のみで高速テスト
python src/main.py --fallback --dry-run
```

## 技術スタック

- Python 3.11
- yfinance（株価データ取得）
- gspread（Google Sheets API）
- jpholiday（日本の祝日判定）
- GitHub Actions（定期実行）
