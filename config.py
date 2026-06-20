"""設定ファイル"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# .envファイルから環境変数を読み込み
dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path, encoding='utf-8-sig')

# Discord Bot
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', 'your_token_here')
DAILY_REPORT_CHANNEL_ID = os.getenv('DAILY_REPORT_CHANNEL_ID', '')
DAILY_REPORT_USER_ID = os.getenv('DAILY_REPORT_USER_ID', '')

# 投資管理設定
BASE_DATE = datetime(2026, 6, 9)  # 基準日
BASE_ASSET = 7_096_249  # 基準資産（円）
ANNUAL_TARGET = 0.20  # 年率目標 20%

# データベース
DB_PATH = 'investment_data.db'

# ユーザー設定（複数ユーザー対応）
USER_CONFIG = {
    # ユーザーIDをキー、初期設定を値
}
