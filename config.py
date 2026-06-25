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
DAILY_REPORT_CHANNEL_ID = os.getenv('DAILY_REPORT_CHANNEL_ID', '').strip()
DAILY_REPORT_USER_ID = os.getenv('DAILY_REPORT_USER_ID', '').strip()


def _env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    if minimum <= value <= maximum:
        return value
    return default


DAILY_REPORT_HOUR = _env_int('DAILY_REPORT_HOUR', 7, 0, 23)
DAILY_REPORT_MINUTE = _env_int('DAILY_REPORT_MINUTE', 0, 0, 59)

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
