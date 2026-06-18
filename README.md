# Discord 投資台帳ボット

Discord のスラッシュコマンドで、入金・出金・買い・売り・履歴・保有・レビューを管理する投資取引台帳Botです。PC上のExcel運用を減らし、スマホDiscordから日々の投資記録を残すことを目的にしています。

## 目的

- Discord で資産、入出金、売買、保有銘柄、投資仮説、レビューを記録する
- 年率20%目標に対して現在資産がどの位置にあるか確認する
- 一度保有を登録した後は、`/買い` `/売り` を中心に台帳運用する
- SQLite によるローカル保存でシンプルに運用する
- Lightsail / Ubuntu で常時稼働できる構成にする

## Bot の主なコマンド

- `/資産`
  - 現在資産、基準資産、入出金、資産内訳を表示します。
- `/資産更新 金額 通貨`
  - 現在資産を手動更新します。
- `/資産設定 金額 YYYY-MM-DD`
  - 基準資産、基準日、現在資産をまとめて設定します。
- `/更新 銘柄 現在価格`
  - 保有と試算の現在価格を更新します。
- `/入金 金額 通貨`
  - 入金を `DEPOSIT` 取引として記録し、現在資産に加算します。
- `/出金 金額 通貨`
  - 出金を `WITHDRAW` 取引として記録し、現在資産から減算します。
- `/買い 銘柄 株数 価格 通貨`
  - 買い取引を `BUY` として記録し、保有株数と平均取得単価を更新します。
- `/売り 銘柄 株数 価格 通貨`
  - 売り取引を `SELL` として記録し、保有株数を減らします。
- `/履歴`
  - 直近の取引履歴を表示します。
- `/一括反映`
  - 複数行テキストを解析し、確認後にまとめてDBへ反映します。
- `/保有 銘柄 株数 取得単価 通貨`
  - 初期登録や修正用に保有銘柄を直接登録します。既存保有がある場合は加算せず上書きします。
- `/試算`
  - 試算ポジションを表示します。
- `/試算登録 銘柄 株数 価格 通貨 メモ`
  - 試算ポジションを登録します。
- `/試算削除 銘柄`
  - 試算ポジションを削除します。
- `/仮説登録 銘柄 保有理由 期待数字 買い増し条件 損切り条件`
  - 投資仮説を記録・更新します。
- `/仮説 銘柄`
  - 登録済みの投資仮説を確認します。
- `/判定 銘柄`
  - 銘柄ごとの保有判定と資産比率を表示します。
- `/比率`
  - 登録済み保有銘柄の資産比率を表示します。
- `/目標`
  - 年率20%の目標額と差分を表示します。
- `/レビュー`
  - 入出金と資産から運用状況をレビューします。
- `/ヘルプ`
  - コマンド一覧を表示します。

## 運用方針

通常運用では、入出金と売買を取引台帳として記録します。

```text
/入金 100000 JPY
/出金 50000 JPY
/買い NET 77 228.51 USD
/売り NET 5 250 USD
/履歴
```

`/保有` は初期登録や修正用です。既存保有がある場合は、株数と取得単価を上書きします。日々の売買は `/買い` `/売り` を使うことで、取引履歴と現在保有をつなげて管理できます。

このBotはOCRを使いません。スマホDiscordにテキストを貼り付け、確認してから登録する運用に寄せています。

基準資産と基準日は以下を初期値にしています。

```text
基準資産: 7,096,249円
基準日: 2026-06-09
```

DBリセット後も、最初にBotが資産情報を参照した時点で、基準資産と現在資産は自動的に `7,096,249円` で初期化されます。必要に応じて `/資産設定 7096249 2026-06-09` で再設定できます。

資産コマンドの役割:

- `/資産` は表示専用です。金額入力は不要です。
- `/資産更新 6811322 JPY` は現在資産を手動更新します。
- `/資産設定 7096249 2026-06-09` は基準資産と基準日を設定します。
- `/一括反映` は現在資産・資産内訳・入出金・保有・試算をまとめて反映します。

入出金と売買の基本動作:

- `/入金` は現在資産に加算します。
- `/出金` は現在資産から減算します。
- `/買い` は既存保有に加算し、平均取得単価を再計算します。
- `/売り` は既存保有から減算し、平均取得単価は原則そのままにします。

## 一括反映

`/一括反映` を実行すると長文入力用のModalが開きます。複数行の取引テキストを貼り付けると、Botが内容を解析し、確認Embedを表示します。`登録する` を押した場合だけDBに反映します。

入力例:

```text
資産 6811322 JPY

資産内訳
国内株式 994000 JPY
米国株式 2995660 JPY
投資信託 2404885 JPY
預り金 381645 JPY
USドル 35132 JPY

入金 500000 JPY
出金 100000 JPY

保有
NET 77 228.51 USD
AMZN 5 238.55 USD
NVDA 2 205.19 USD

試算
SOFI 300 8.5 USD AIテーマ監視
PLTR 50 120 USD 高成長枠
```

明示形式も使えます。

```text
DEPOSIT 500000 JPY
WITHDRAW 100000 JPY
BUY NET 10 220 USD
SELL AMZN 1 250 USD
HOLDING NET 77 228.51 USD
SIM SOFI 300 8.5 USD AIテーマ監視
```

一括反映のルール:

- 空行は無視します。
- `#` で始まる行はコメントとして無視します。
- `資産 amount currency` は現在資産を更新します。
- `資産内訳` セクション内の `name amount currency` は資産内訳として保存します。
- `国内株式`、`米国株式`、`投資信託`、`投信`、`預り金`、`USドル` はセクション外でも資産内訳として扱います。
- `保有` セクション内の `ticker quantity price currency memo` は保有として扱います。
- `保有` セクションは初期登録・修正用です。既存保有がある場合は加算せず、入力した株数と取得単価で上書きします。
- `試算` セクション内の `ticker quantity price currency memo` は試算として扱います。
- 解析できない行があっても、成功候補だけ確認画面に表示されます。
- 登録時は成功候補だけDBへ反映され、エラー行は登録されません。
- 保有の初期登録・修正は、履歴には `BUY` として残り、memo に `初期登録/修正` が入ります。

## 保有と試算の違い

- 保有
  - 実際の保有銘柄です。
  - `/買い` `/売り` または `/保有` で更新します。
  - `/買い` は加算、`/売り` は減算、`/保有` は上書きです。
  - 資産比率や判定の対象です。
  - 一括反映の初期登録は `BUY` として履歴に残ります。
- 試算
  - 買った場合を想定する監視・シミュレーション用です。
  - holdings には入りません。
  - 総資産やレビューには含めません。
  - `/試算` `/試算登録` `/試算削除` で管理します。

## レビューの計算式

`/レビュー` は、基準資産・現在資産・入出金を使って入金除外の運用成果を確認します。試算ポジションは総資産に含めません。

```text
現在資産 = 基準資産 + 純入金額 + 運用成果
純入金額 = 入金合計 - 出金合計
運用成果 = 現在資産 - 基準資産 - 純入金額
入金除外リターン = 運用成果 / 基準資産 * 100
```

例:

```text
基準資産: 7,096,249
入金合計: 500,000
出金合計: 100,000
純入金額: 400,000
現在資産: 7,496,249
運用成果: 0
入金除外リターン: 0.00%
```

## 資産更新と価格更新

`/資産更新 金額 通貨` は現在資産を直接更新します。

```text
/資産更新 7496249 JPY
```

`/更新 銘柄 現在価格` は、同じ銘柄が保有と試算に存在する場合、両方の現在価格を更新します。

```text
/更新 NET 250
```

金額も銘柄も指定しない `/更新` は、現在価格取得の仮実装として、未設定の現在価格に取得単価を入れます。将来的に外部株価APIへ差し替える前提です。試算の評価額も更新対象ですが、`/レビュー` の総資産には含めません。

## ローカル起動手順

1. リポジトリをサーバーまたはローカルに配置します。
2. `setup.sh` を使って必要なパッケージと Python 環境を準備します。
3. `.env` を用意して `DISCORD_TOKEN` を設定します。
4. 仮想環境を有効化します。
5. `bot.py` でボットを起動します。

```bash
source venv/bin/activate
python bot.py
```

Windows では仮想環境の有効化コマンドが異なります。

```powershell
venv\Scripts\activate
python bot.py
```

## requirements.txt の説明

- `discord.py` : Discord API とスラッシュコマンドの実装
- `python-dotenv` : `.env` から環境変数を読み込む

`setup.sh` は `requirements.txt` を使って依存関係をインストールします。

## GitHub / 手動ファイル配置手順

GitHub からクローンする場合:

```bash
git clone <repository-url> stock
cd stock
```

手動で配置する場合:

- `bot.py`
- `database.py`
- `config.py`
- `requirements.txt`
- `setup.sh`
- `systemd/discord-bot.service.example`
- `.env.example`

上記を同じフォルダに置きます。

## setup.sh を使ったインストール

リポジトリルートで以下を実行します。

```bash
bash setup.sh
```

setup.sh の主な動作:

- Ubuntu / Debian 向けの前提パッケージをインストールします。
- `venv` が存在しなければ仮想環境を作成します。
- pip をアップグレードして `requirements.txt` をインストールします。
- `.env` がない場合、`.env.example` をコピーして `.env` を作成します。
- `bot.py` の静的構文チェックを実行します。

## .env の配置方法

ルートに `.env` を置き、`.env.example` を参考に `DISCORD_TOKEN` を設定します。

```text
DISCORD_TOKEN=your_discord_bot_token_here
```

- トークンは必ず Git 管理外にしてください。
- `.gitignore` で `.env` は無視されるようになっています。

## systemd サービスファイル

`systemd/discord-bot.service.example` は例です。必要に応じてコピーし、`User` / `WorkingDirectory` / `ExecStart` を環境に合わせて編集してください。

```ini
[Unit]
Description=Discord Investment Ledger Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/stock
ExecStart=/home/ubuntu/stock/venv/bin/python /home/ubuntu/stock/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## systemd サービスの起動

```bash
sudo cp systemd/discord-bot.service.example /etc/systemd/system/discord-bot.service
sudo systemctl daemon-reload
sudo systemctl enable discord-bot.service
sudo systemctl start discord-bot.service
sudo systemctl status discord-bot.service
```

## ログ確認方法

リアルタイムログ:

```bash
sudo journalctl -u discord-bot.service -f
```

ステータス確認:

```bash
sudo systemctl status discord-bot.service
```

## Bot 停止・再起動方法

停止:

```bash
sudo systemctl stop discord-bot.service
```

再起動:

```bash
sudo systemctl restart discord-bot.service
```

## 実地テスト手順

Discord 上で以下を順に入力します。

```text
/資産
/資産更新 7096249 JPY
/資産設定 7096249 2026-06-09
/入金 100000 JPY
/出金 50000 JPY
/買い NET 77 228.51 USD
/買い NET 10 220 USD
/売り NET 5 250 USD
/履歴
/保有
/試算登録 SOFI 300 8.5 USD AIテーマ監視
/試算
/レビュー
```

一括反映の確認:

```text
資産 6811322 JPY

資産内訳
国内株式 994000 JPY
米国株式 2995660 JPY
投資信託 2404885 JPY
預り金 381645 JPY
USドル 35132 JPY

入金 500000 JPY
出金 100000 JPY

保有
NET 77 228.51 USD
AMZN 5 238.55 USD
NVDA 2 205.19 USD

試算
SOFI 300 8.5 USD AIテーマ監視
PLTR 50 120 USD 高成長枠
```

簡易チェックリスト:

- [ ] Bot が起動する
- [ ] Discord 上で Bot がオンラインになる
- [ ] スラッシュコマンドが表示される
- [ ] `/入金` が `DEPOSIT` として記録される
- [ ] `/出金` が `WITHDRAW` として記録される
- [ ] `/買い` で保有株数と平均取得単価が更新される
- [ ] `/売り` で保有株数が減り、実現損益が表示される
- [ ] `/履歴` で直近取引が表示される
- [ ] `/一括反映` で確認Embedが表示される
- [ ] `/一括反映` の登録後、保有と試算が反映される
- [ ] `/試算` で試算ポジションが表示される
- [ ] `/レビュー` で入金合計、出金合計、純入金額、運用成果が表示される
- [ ] `/レビュー` に試算が含まれない

## SQLite の中身を確認する方法

Bot を停止するか、書き込み中でないことを確認してから SQLite を開きます。

```bash
sqlite3 investment_data.db
```

SQLite のプロンプトで以下を実行します。

```sql
.tables
SELECT * FROM transactions;
SELECT * FROM holdings;
SELECT * FROM user_assets;
SELECT * FROM asset_breakdowns;
```

終了する場合:

```sql
.quit
```

## 開発中のDBリセット方法

開発中にテストデータを消して最初から確認したい場合だけ、Botを停止してからDBファイルを削除します。本番運用中のDBでは実行しないでください。

PowerShell:

```powershell
Remove-Item .\investment_data.db
```

Ubuntu / macOS:

```bash
rm investment_data.db
```

次回Bot起動時に、必要なテーブルは `CREATE TABLE IF NOT EXISTS` で再作成されます。

## Git 管理を開始する手順

初回だけ以下を実行します。

```bash
git init
git status
git add bot.py database.py config.py requirements.txt README.md setup.sh .env.example .gitignore systemd/
git commit -m "Initial Discord investment ledger bot"
```

`.env` には Discord Bot Token が含まれるため、絶対にコミットしないでください。DBファイルもコミットしないでください。

## よくあるエラーと対処

- `DISCORD_TOKEN` が未設定または `.env` が存在しない
  - `.env` を作成し、`DISCORD_TOKEN` を設定してください。
- `requirements.txt` がない
  - `setup.sh` 実行前にファイルが存在するか確認してください。
- `bot.py` がない
  - リポジトリのルートに `bot.py` があるか確認してください。
- `Permission denied`
  - systemd 実行ユーザーとファイルの所有権を確認してください。

## 次の実装予定

- 取引履歴のCSVエクスポート
- 為替レート対応
- 売却損益の累計表示
- Discord通知 / 定期リマインダー機能
