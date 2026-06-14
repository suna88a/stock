# Discord 投資管理ボット

このリポジトリは、Discord のスラッシュコマンドと OCR スクリーンショット登録を使った投資管理ボットの記録です。Excel 運用を置き換えるための自動化とログを目的としています。

## 目的

- Discord で資産・入金・保有銘柄・目標・レビューを記録・確認できるボット
- スクリーンショットから OCR で保有銘柄を自動登録する機能
- SQLite によるローカル保存でシンプルに運用
- Lightsail / Ubuntu へのデプロイを想定したセットアップ

## Bot の主なコマンド

- `/資産 金額`
  - 現在の総資産を登録・更新し、目標進捗を表示します。
- `/入金 金額`
  - 入金履歴を記録し、累計入金を表示します。
- `/保有 銘柄 株数 取得単価 通貨`
  - 保有銘柄を登録します。
- `/仮説登録 銘柄 保有理由 期待数字 買い増し条件 損切り条件`
  - 投資仮説を記録・更新します。
- `/判定 銘柄`
  - 銘柄ごとの保有判定と資産比率を表示します。
- `/比率`
  - 登録済み保有銘柄の資産比率を表示します。
- `/目標`
  - 年率 20% の目標額と進捗を表示します。
- `/レビュー`
  - 3 か月単位の投資レビューを表示します。

## OCR 機能

- `bot.py` にはスクリーンショット添付から OCR を実行し、保有銘柄を登録する処理があります。
- pytesseract と Tesseract OCR が必要です。
- OCR で読み取ったテキストから銘柄・株数・取得単価・通貨を抽出します。
- OCR 結果は即登録せず、Discord 上の確認ボタンで承認してから登録します。

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

## requirements.txt の説明

- `discord.py` : Discord API とスラッシュコマンドの実装
- `python-dotenv` : `.env` から環境変数を読み込む
- `Pillow` : 画像処理用ライブラリ
- `pytesseract` : OCR の Python バインディング

`setup.sh` は `requirements.txt` を使って依存関係をインストールします。

## Tesseract 導入手順

Ubuntu / Debian では、`setup.sh` の実行で以下をインストールします。

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git tesseract-ocr libtesseract-dev tesseract-ocr-jpn tesseract-ocr-eng
```

- 日本語と英語の OCR モデルを追加しています。
- Windows 環境で使う場合は別途 Tesseract の公式インストールが必要です。

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

### setup.sh の安全設計

- `set -e` を使用しています。
- 既存 `venv` は上書きしません。
- 既存 `.env` は上書きしません。
- `requirements.txt` がない場合はエラーで停止します。
- `bot.py` がない場合はエラーで停止します。
- `DISCORD_TOKEN` はスクリプト内に直接書き込んでいません。

## .env の配置方法

ルートに `.env` を置き、`.env.example` を参考に `DISCORD_TOKEN` を設定します。

```text
DISCORD_TOKEN=your_discord_bot_token_here
```

- トークンは必ず Git 管理外にしてください。
- `.gitignore` で `.env` は無視されるようになっています。

## systemd サービスファイル

`systemd/discord-bot.service.example` は例です。必要に応じてコピーし、`User` / `WorkingDirectory` / `ExecStart` を環境に合わせて編集してください。

例:

```ini
[Unit]
Description=Discord Investment Management Bot
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

- `Restart=always` は Bot が落ちたときに自動再起動するための設定です。

## systemd の .env 取り扱い

`config.py` は起動時に `.env` を自動読み込みします。したがって、原則として systemd サービスで `EnvironmentFile` を指定する必要はありません。

どうしても systemd に `.env` を読み込ませる場合は、systemd 用のフォーマットに従って明示的に指定してください。

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

## 起動後の Discord 動作確認

- `/資産 10000000` などを入力して応答を確認します。
- `/入金 1000000` で入金記録が追加されるか確認します。
- `/保有 AAPL 10 150 USD` のように保有を登録します。
- スクリーンショットをボットに送信し、OCR 候補が表示されるか確認します。
- `/レビュー` でレビュー情報が返るか確認します。

## 実地テスト手順

ローカル環境または Lightsail Ubuntu 上で Bot を起動し、Discord 上から最低限の動作確認を行います。

### 事前準備

1. `.env` に `DISCORD_TOKEN` を設定します。
2. 依存関係をインストールします。
3. Tesseract OCR をインストールします。
4. Bot を起動します。

```bash
python bot.py
```

systemd で起動している場合は、以下でログを確認します。

```bash
sudo journalctl -u discord-bot.service -f
```

### テスト用サンプル入力

Discord 上で以下を入力します。

```text
/資産 7096249
/入金 100000
/保有 NET 77 203.5 USD
```

OCR テストでは、証券アプリや注文画面などのスクリーンショットを Discord に送信します。

### 簡易テストチェックリスト

- [ ] Bot が起動する
- [ ] Discord 上で Bot がオンラインになる
- [ ] スラッシュコマンドが表示される
- [ ] `/資産` が動作する
- [ ] `/入金` が動作する
- [ ] `/保有` が動作する
- [ ] `/目標` が動作する
- [ ] `/レビュー` が動作する
- [ ] 画像送信で OCR 候補が表示される
- [ ] OCR 候補に「登録する」「キャンセル」ボタンが表示される
- [ ] 「登録する」を押すと DB に登録される
- [ ] 「キャンセル」を押すと DB に登録されない
- [ ] 他人がボタンを押すと拒否される
- [ ] 登録ボタン連打で二重登録されない
- [ ] 5分放置で期限切れになる

### SQLite の中身を確認する方法

Bot を停止するか、書き込み中でないことを確認してから SQLite を開きます。

```bash
sqlite3 investment_bot.db
```

SQLite のプロンプトで以下を実行します。

```sql
.tables
SELECT * FROM holdings;
SELECT * FROM assets;
SELECT * FROM deposits;
SELECT * FROM reviews;
```

終了する場合:

```sql
.quit
```

### Git 管理を開始する手順

初回だけ以下を実行します。

```bash
git init
git status
git add bot.py database.py config.py requirements.txt README.md setup.sh .env.example .gitignore systemd/
git commit -m "Initial Discord investment bot"
```

`.env` には Discord Bot Token が含まれるため、絶対にコミットしないでください。

コミット前に必ず確認します。

```bash
git status
```

`.env` が `git status` に表示される場合は、`.gitignore` に `.env` が含まれているか確認してください。

## よくあるエラーと対処

- `DISCORD_TOKEN` が未設定または `.env` が存在しない
  - `.env` を作成し、`DISCORD_TOKEN` を設定してください。
- `requirements.txt` がない
  - `setup.sh` 実行前にファイルが存在するか確認してください。
- `bot.py` がない
  - リポジトリのルートに `bot.py` があるか確認してください。
- `pytesseract` / `tesseract-ocr` がない
  - `setup.sh` を実行するか、手動で Tesseract をインストールしてください。
- `Permission denied`
  - systemd 実行ユーザーとファイルの所有権を確認してください。

## Ubuntu 上での確認

Windows 環境では `bash -n setup.sh` が実行できないため、Ubuntu で以下を確認してください。

```bash
bash -n setup.sh
bash setup.sh
source venv/bin/activate
python -m py_compile bot.py
python bot.py
```

## 次の実装予定

- OCR 解析精度の向上
- スクリーンショット登録の適応範囲拡大
- デプロイ自動化と systemd テンプレートの強化
- Discord 通知 / 定期リマインダー機能
