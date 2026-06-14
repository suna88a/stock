#!/usr/bin/env bash
set -e
set -o pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

echo "[INFO] Starting setup for Discord Investment Management Bot"

if [ -f /etc/os-release ]; then
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ] && [ "${ID_LIKE:-}" != "debian" ]; then
    echo "[WARN] This script assumes Ubuntu/Debian. Detected: ${ID:-unknown}. Continue at your own risk."
  fi
fi

echo "[INFO] Updating APT repositories..."
sudo apt update

echo "[INFO] Installing system packages..."
sudo apt install -y python3 python3-pip python3-venv git tesseract-ocr libtesseract-dev tesseract-ocr-jpn tesseract-ocr-eng

if [ ! -d "venv" ]; then
  echo "[INFO] Creating Python virtual environment..."
  python3 -m venv venv
else
  echo "[INFO] Existing virtual environment found, skipping creation."
fi

source venv/bin/activate

echo "[INFO] Upgrading pip..."
python -m pip install --upgrade pip

echo "[INFO] Checking required files..."
if [ ! -f "requirements.txt" ]; then
  echo "[ERROR] requirements.txt が見つかりません。リポジトリルートに配置してください。"
  exit 1
fi
if [ ! -f "bot.py" ]; then
  echo "[ERROR] bot.py が見つかりません。リポジトリルートに配置してください。"
  exit 1
fi

echo "[INFO] Installing Python requirements..."
python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "[INFO] Creating .env from .env.example (token must be added manually)."
    cp .env.example .env
    echo "# Please edit .env and set DISCORD_TOKEN before running the bot." >> .env
  else
    echo "[ERROR] .env.example not found. Create .env manually."
    exit 1
  fi
else
  echo "[INFO] Existing .env file found, skipping creation."
fi

echo "[INFO] Running static syntax check..."
python -m py_compile bot.py

echo "[INFO] Setup completed successfully."
echo "[INFO] Please edit .env and set DISCORD_TOKEN, then run 'source venv/bin/activate && python bot.py' or enable the service manually."
