# Google Sheets API セットアップ手順

年初来高値トラッカーを動かすために必要な設定を、ステップごとに説明します。  
所要時間の目安: 約15〜20分

---

## 前提条件

- Google アカウントを持っていること
- GitHub リポジトリが作成済みであること
- Google Sheets で記録先スプレッドシートを1つ作成済みであること

---

## STEP 1: Google Cloud プロジェクトの作成

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. 画面上部のプロジェクト選択メニュー → **「新しいプロジェクト」** をクリック
3. プロジェクト名を入力（例: `yth-tracker`）し **「作成」** をクリック
4. 作成したプロジェクトが選択されていることを確認する

---

## STEP 2: Google Sheets API の有効化

1. Google Cloud Console 左メニュー → **「APIとサービス」** → **「ライブラリ」**
2. 検索ボックスに `Google Sheets API` と入力
3. **「Google Sheets API」** をクリック → **「有効にする」** をクリック
4. 続けて `Google Drive API` も同様に有効化する（gspread の内部動作に必要）

---

## STEP 3: サービスアカウントの作成

1. 左メニュー → **「APIとサービス」** → **「認証情報」**
2. 画面上部 **「認証情報を作成」** → **「サービスアカウント」** を選択
3. 以下を入力して **「完了」** をクリック
   - サービスアカウント名: `yth-tracker-sa`（任意）
   - 説明: `年初来高値トラッカー用サービスアカウント`（任意）
   - ロール: 今回は不要（Sheets はファイル単位で権限を付与するため）

4. 作成されたサービスアカウントをクリック → **「キー」** タブを開く
5. **「鍵を追加」** → **「新しい鍵を作成」** → 種類: **JSON** → **「作成」**
6. JSON ファイルが自動ダウンロードされる（大切に保管すること）

---

## STEP 4: Google Sheets をサービスアカウントと共有

1. 記録先の Google スプレッドシートを開く
2. 右上の **「共有」** ボタンをクリック
3. ダウンロードした JSON ファイル内の `"client_email"` の値をコピーする  
   例: `yth-tracker-sa@your-project.iam.gserviceaccount.com`
4. 共有ダイアログに上記メールアドレスを貼り付け
5. 権限を **「編集者」** に設定して **「送信」** をクリック

### スプレッドシートIDの確認方法

スプレッドシートの URL は以下の形式です：

```
https://docs.google.com/spreadsheets/d/【ここがスプレッドシートID】/edit
```

この `d/` と `/edit` の間の文字列を控えておいてください。

---

## STEP 5: GitHub Secrets への登録

1. GitHub リポジトリページを開く
2. **「Settings」** → **「Secrets and variables」** → **「Actions」**
3. **「New repository secret」** で以下の2つを登録する

---

### Secret 1: `GOOGLE_CREDENTIALS_JSON`

| 項目 | 値 |
|------|-----|
| Name | `GOOGLE_CREDENTIALS_JSON` |
| Secret | ダウンロードした JSON ファイルの**内容全体**をコピー＆ペースト |

JSON ファイルをテキストエディタで開き、`{` から `}` までの全文字列を貼り付けてください。

---

### Secret 2: `SPREADSHEET_ID`

| 項目 | 値 |
|------|-----|
| Name | `SPREADSHEET_ID` |
| Secret | STEP 4 で確認したスプレッドシートID |

---

## STEP 6: 動作確認

1. GitHub リポジトリの **「Actions」** タブを開く
2. **「年初来高値トラッカー」** ワークフローを選択
3. **「Run workflow」** をクリック
4. 以下のオプションを設定して実行
   - `date`: 直近の平日（例: 2024-01-15）
   - `dry_run`: `true`（最初はSheetsへの書き込みなしでテスト）
5. ログにエラーがないことを確認する
6. 問題なければ `dry_run: false` で再実行してスプレッドシートへの書き込みを確認

---

## トラブルシューティング

### `PERMISSION_DENIED` エラー

→ STEP 4 でサービスアカウントのメールアドレスをスプレッドシートに共有したか確認する

### `INVALID_ARGUMENT` または JSON パースエラー

→ `GOOGLE_CREDENTIALS_JSON` の値が正しくコピーされているか確認する（改行や余分なスペースが入っていないか）

### `Spreadsheet not found`

→ `SPREADSHEET_ID` の値が正しいか確認する

### ワークフローがスキップされる

→ 土日祝日は市場が休みのため自動スキップされます。平日の `date` を指定して手動実行してください。
