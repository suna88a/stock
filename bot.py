"""投資取引台帳Discord Bot - メイン"""
import asyncio
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import tasks

from config import (
    DISCORD_TOKEN,
    DAILY_REPORT_CHANNEL_ID,
    DAILY_REPORT_USER_ID,
    DAILY_REPORT_HOUR,
    DAILY_REPORT_MINUTE,
    BASE_ASSET,
    ANNUAL_TARGET,
    BASE_DATE,
)
from database import InvestmentDatabase
from price_fetcher import fetch_quote, fetch_usdjpy
from time_utils import JST, format_datetime_jst, now_jst


env_path = Path(__file__).parent / '.env'
load_dotenv(env_path, encoding='utf-8-sig')

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
db = InvestmentDatabase()
daily_report_last_sent_key = None
DEFAULT_TICKER_NAMES = {
    '4633': 'サカタインクス',
    '4755': '楽天グループ',
    'AMZN': 'Amazon',
    'NET': 'Cloudflare',
    'NVDA': 'NVIDIA',
}


@bot.event
async def on_ready():
    """Bot起動完了"""
    print(f'{bot.user} としてログインしました')
    await tree.sync()
    print('コマンドを同期しました')
    print(f"[daily_report] DAILY_REPORT_CHANNEL_ID set={bool(DAILY_REPORT_CHANNEL_ID)}")
    print(f"[daily_report] 通知時刻 JST {DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d}")
    if DAILY_REPORT_CHANNEL_ID:
        if not daily_report_loop.is_running():
            daily_report_loop.start()
            print("[daily_report] 日次レポートスケジューラー開始")
            print(f"[daily_report] 投稿先チャンネルID {DAILY_REPORT_CHANNEL_ID}")
            print(f"[daily_report] 次回実行予定時刻 {get_next_daily_report_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            print("[daily_report] scheduler already running")
    else:
        print("[daily_report] DAILY_REPORT_CHANNEL_ID is not set; 日次レポート無効")


@tasks.loop(minutes=1)
async def daily_report_loop():
    global daily_report_last_sent_key
    current = now_jst()
    scheduled = current.replace(
        hour=DAILY_REPORT_HOUR,
        minute=DAILY_REPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    if current < scheduled or current >= scheduled + timedelta(minutes=2):
        return
    scheduled_key = scheduled.strftime('%Y-%m-%d %H:%M')
    if daily_report_last_sent_key == scheduled_key:
        return

    print("[daily_report] 日次レポート開始")
    channel_id = int(DAILY_REPORT_CHANNEL_ID) if DAILY_REPORT_CHANNEL_ID.isdigit() else None
    if not channel_id:
        print("[daily_report] DAILY_REPORT_CHANNEL_ID is invalid or empty; 日次レポート無効")
        return
    print(f"[daily_report] 投稿先チャンネルID {channel_id}")
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        await send_daily_report(channel)
        daily_report_last_sent_key = scheduled_key
        print("[daily_report] 投稿成功")
    except Exception as exc:
        print(f"[daily_report] 投稿失敗 key={scheduled_key}: {exc}")


@daily_report_loop.before_loop
async def before_daily_report_loop():
    await bot.wait_until_ready()


def get_next_daily_report_time():
    current = now_jst()
    next_run = current.replace(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, second=0, microsecond=0)
    if current >= next_run:
        next_run = next_run + timedelta(days=1)
    return next_run


def format_money(amount, currency='JPY'):
    if amount is None:
        amount = 0
    if currency == 'JPY':
        return f"¥{int(amount):,}"
    return f"{amount:,.2f} {currency}"


def format_signed_money(amount, currency='JPY'):
    if amount is None:
        return '-'
    sign = '+' if amount >= 0 else ''
    if currency == 'JPY':
        return f"{sign}¥{int(amount):,}"
    return f"{sign}{amount:,.2f} {currency}"


def format_price(amount, currency='JPY'):
    if amount is None:
        return '-'
    if currency == 'JPY':
        return f"{amount:,.0f} JPY"
    return f"{amount:,.4g} {currency}"


def format_rate(rate, stored_as_percent=False):
    if rate is None:
        return '-'
    value = rate if stored_as_percent else rate * 100
    return f"{value:+.2f}%"


def format_day_change(item):
    change = item.get('day_change')
    rate = item.get('day_change_rate')
    currency = position_currency(item)
    if change is None or rate is None:
        return '前日比取得不可'
    if currency == 'JPY':
        change_text = f"{change:+,.0f} JPY"
    else:
        change_text = f"{change:+,.2f} {currency}"
    return f"{change_text} ({format_rate(rate)})"


def format_asset_change(change_info):
    change = change_info.get('change')
    rate = change_info.get('change_rate')
    currency = change_info.get('currency') or 'JPY'
    if change is None or rate is None:
        return '-'
    return f"{format_signed_money(change, currency)} ({format_rate(rate)})"


def format_percent(value, signed=False):
    if value is None:
        return '-'
    sign = '+' if signed and value >= 0 else ''
    return f"{sign}{value * 100:.1f}%"


def daily_value_icon(value, risk=False):
    if value is None or value == 0:
        return ''
    if risk:
        return '🟡 '
    return '🔴 ' if value > 0 else '🟢 '


def format_daily_signed_money(amount, currency='JPY', risk=False):
    if amount is None:
        return '-'
    return f"{daily_value_icon(amount, risk=risk)}{format_signed_money(amount, currency)}"


def format_daily_asset_change(change_info):
    change = change_info.get('change')
    rate = change_info.get('change_rate')
    currency = change_info.get('currency') or 'JPY'
    if change is None or rate is None:
        return '-'
    return f"{format_daily_signed_money(change, currency)} ({format_rate(rate)})"


def position_currency(item):
    return (item.get('current_currency') or item.get('currency') or 'USD').upper()


def format_position_value(item, entry_label='平均取得単価', quantity_label='株数'):
    currency = position_currency(item)
    entry_price = item.get('purchase_price', item.get('entry_price'))
    current_price = item.get('current_price') if item.get('current_price') is not None else entry_price
    current_value = item.get('current_value')
    if current_value is None and current_price is not None:
        current_value = item['quantity'] * current_price
    pnl = item.get('unrealized_pnl')
    pnl_rate = item.get('unrealized_pnl_rate')
    current_value_jpy = item.get('current_value_jpy')
    pnl_jpy = item.get('unrealized_pnl_jpy')
    updated_at = item.get('price_updated_at') or '-'

    lines = [
        f"{quantity_label}: {item['quantity']:,}",
        f"{entry_label}: {entry_price:,} {item.get('currency', currency)}",
        f"現在価格: {format_price(current_price, currency)}",
        f"前日比: {format_day_change(item)}",
        f"評価額: {format_money(current_value, currency)}",
    ]
    if pnl is not None:
        rate_text = f" ({pnl_rate:+.2f}%)" if pnl_rate is not None else ''
        lines.append(f"評価損益: {format_signed_money(pnl, currency)}{rate_text}")
    if current_value_jpy is not None:
        lines.append(f"円換算評価額: {format_money(current_value_jpy, 'JPY')}")
    if pnl_jpy is not None:
        lines.append(f"円換算損益: {format_signed_money(pnl_jpy, 'JPY')}")
    lines.append(f"更新日時: {format_datetime_jst(updated_at)}")
    if item.get('memo'):
        lines.append(f"memo: {item['memo']}")
    return '\n'.join(lines)


def holding_display_name(item):
    symbol = item.get('symbol') or item.get('ticker') or ''
    name = item.get('name') or item.get('company_name') or item.get('memo') or DEFAULT_TICKER_NAMES.get(symbol.upper())
    return f"{symbol} / {name}" if name else symbol


def format_report_price(amount, currency):
    if amount is None:
        return '-'
    if currency == 'JPY':
        return f"{amount:,.0f} JPY"
    return f"{amount:,.4f}".rstrip('0').rstrip('.') + f" {currency}"


def format_daily_position_row(label, value, rate=None):
    if rate is None:
        return f"{label}   {value}"
    return f"{label}   {value} / {rate}"


def daily_day_change_jpy(item, usdjpy=None):
    day_change = item.get('day_change')
    quantity = item.get('quantity') or 0
    currency = position_currency(item)
    if day_change is None:
        return None
    if currency == 'JPY':
        return day_change * quantity
    if currency == 'USD' and usdjpy:
        return day_change * quantity * usdjpy
    return None


def format_daily_holding_value(item, usdjpy=None):
    currency = position_currency(item)
    entry_price = item.get('purchase_price')
    current_price = item.get('current_price') if item.get('current_price') is not None else entry_price
    day_change_jpy = daily_day_change_jpy(item, usdjpy=usdjpy)
    day_rate = format_rate(item.get('day_change_rate'))
    pnl_jpy = item.get('unrealized_pnl_jpy')
    pnl_rate = item.get('unrealized_pnl_rate')
    if pnl_jpy is None and item.get('unrealized_pnl') is not None:
        if currency == 'JPY':
            pnl_jpy = item['unrealized_pnl']
        elif currency == 'USD' and usdjpy:
            pnl_jpy = item['unrealized_pnl'] * usdjpy

    lines = [
        holding_display_name(item),
        format_daily_position_row('株数', f"{item.get('quantity', 0):,.1f}"),
        format_daily_position_row('取得', format_report_price(entry_price, item.get('currency', currency))),
        format_daily_position_row('現在', format_report_price(current_price, currency)),
        format_daily_position_row('前日', format_daily_signed_money(day_change_jpy) if day_change_jpy is not None else '-', day_rate),
        format_daily_position_row('損益', format_daily_signed_money(pnl_jpy) if pnl_jpy is not None else '-', f"{pnl_rate:+.2f}%" if pnl_rate is not None else '-'),
    ]
    return "```text\n" + "\n".join(lines) + "\n```"


def clean_number(value):
    return float(str(value).replace(',', ''))


def default_currency_for_ticker(ticker, cash=False):
    if cash:
        return 'JPY'
    if re.fullmatch(r'\d{4}', ticker):
        return 'JPY'
    return 'USD'


def parse_date_text(value):
    return datetime.strptime(value, '%Y-%m-%d')


def asset_base_values(asset_info):
    initial_asset = asset_info.get('initial_asset') or BASE_ASSET
    base_date_text = asset_info.get('base_date') or BASE_DATE.date().isoformat()
    try:
        base_date = parse_date_text(base_date_text)
    except ValueError:
        base_date = BASE_DATE
    return initial_asset, base_date


def split_line(line):
    return re.sub(r'[\u3000\s]+', ' ', line.strip()).split(' ')


def parse_trade_like(parts, default_type, line_number, original):
    if len(parts) < 3:
        return None, f"{line_number}: {original}"
    ticker = parts[0].upper()
    try:
        quantity = clean_number(parts[1])
        price = clean_number(parts[2])
    except ValueError:
        return None, f"{line_number}: {original}"
    currency = parts[3].upper() if len(parts) >= 4 and re.fullmatch(r'[A-Za-z]{3}', parts[3]) else default_currency_for_ticker(ticker)
    memo_start = 4 if len(parts) >= 4 and re.fullmatch(r'[A-Za-z]{3}', parts[3]) else 3
    return {
        'type': default_type,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'currency': currency,
        'memo': ' '.join(parts[memo_start:]),
        'line': line_number,
        'raw': original,
    }, None


def parse_cash(parts, tx_type, line_number, original):
    if len(parts) < 2:
        return None, f"{line_number}: {original}"
    try:
        amount = clean_number(parts[1])
    except ValueError:
        return None, f"{line_number}: {original}"
    currency = parts[2].upper() if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 'JPY'
    memo_start = 3 if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 2
    return {
        'type': tx_type,
        'amount': amount,
        'currency': currency,
        'memo': ' '.join(parts[memo_start:]),
        'line': line_number,
        'raw': original,
    }, None


def parse_asset_line(parts, line_number, original):
    if len(parts) < 2:
        return None, f"{line_number}: {original}"
    try:
        amount = clean_number(parts[1])
    except ValueError:
        return None, f"{line_number}: {original}"
    currency = parts[2].upper() if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 'JPY'
    memo_start = 3 if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 2
    return {
        'type': 'ASSET',
        'amount': amount,
        'currency': currency,
        'memo': ' '.join(parts[memo_start:]),
        'line': line_number,
        'raw': original,
    }, None


def parse_asset_breakdown(parts, line_number, original):
    if len(parts) < 2:
        return None, f"{line_number}: {original}"
    try:
        amount = clean_number(parts[1])
    except ValueError:
        return None, f"{line_number}: {original}"
    currency = parts[2].upper() if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 'JPY'
    memo_start = 3 if len(parts) >= 3 and re.fullmatch(r'[A-Za-z]{3}', parts[2]) else 2
    return {
        'type': 'ASSET_BREAKDOWN',
        'name': parts[0],
        'amount': amount,
        'currency': currency,
        'memo': ' '.join(parts[memo_start:]),
        'line': line_number,
        'raw': original,
    }, None


def parse_bulk_text(text):
    actions = {
        'ASSET': [],
        'ASSET_BREAKDOWN': [],
        'DEPOSIT': [],
        'WITHDRAW': [],
        'BUY': [],
        'SELL': [],
        'HOLDING': [],
        'SIM': [],
    }
    errors = []
    section = None
    section_map = {
        '入出金': 'cash',
        '資産': 'asset',
        '資産内訳': 'asset',
        '保有': 'holding',
        '試算': 'sim',
    }
    asset_breakdown_names = {
        '国内株式',
        '米国株式',
        '投資信託',
        '投信',
        '預り金',
        'USドル',
        'USD',
        '現金',
        '日本円',
    }
    command_map = {
        '資産': 'ASSET',
        'ASSET': 'ASSET',
        '入金': 'DEPOSIT',
        'DEPOSIT': 'DEPOSIT',
        '出金': 'WITHDRAW',
        'WITHDRAW': 'WITHDRAW',
        '買い': 'BUY',
        'BUY': 'BUY',
        '売り': 'SELL',
        'SELL': 'SELL',
        '保有': 'HOLDING',
        'HOLDING': 'HOLDING',
        '試算': 'SIM',
        'SIM': 'SIM',
    }

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        original = raw_line.strip()
        if not original or original.startswith('#'):
            continue
        if original in section_map:
            section = section_map[original]
            continue

        parts = split_line(original)
        keyword = parts[0].upper()
        japanese_keyword = parts[0]
        tx_type = command_map.get(japanese_keyword) or command_map.get(keyword)

        if tx_type == 'ASSET':
            action, error = parse_asset_line(parts, line_number, original)
        elif tx_type in ('DEPOSIT', 'WITHDRAW'):
            action, error = parse_cash(parts, tx_type, line_number, original)
        elif tx_type in ('BUY', 'SELL', 'HOLDING', 'SIM'):
            action, error = parse_trade_like(parts[1:], tx_type, line_number, original)
        elif japanese_keyword in asset_breakdown_names or section == 'asset':
            action, error = parse_asset_breakdown(parts, line_number, original)
        elif section == 'holding':
            action, error = parse_trade_like(parts, 'HOLDING', line_number, original)
        elif section == 'sim':
            action, error = parse_trade_like(parts, 'SIM', line_number, original)
        elif section == 'cash':
            action, error = None, f"{line_number}: {original}"
        else:
            action, error = None, f"{line_number}: {original}"

        if error:
            errors.append(error)
        elif action:
            actions[action['type']].append(action)
    return actions, errors


def summarize_action(action):
    if action['type'] == 'ASSET':
        return f"- 現在資産 {action['amount']:,.0f} {action['currency']} {action.get('memo', '')}".strip()
    if action['type'] == 'ASSET_BREAKDOWN':
        return f"- {action['name']} {action['amount']:,.0f} {action['currency']} {action.get('memo', '')}".strip()
    if action['type'] in ('DEPOSIT', 'WITHDRAW'):
        return f"- {action['amount']:,.0f} {action['currency']} {action.get('memo', '')}".strip()
    return (
        f"- {action['ticker']} {action['quantity']:g}株 "
        f"{action['price']:g} {action['currency']} {action.get('memo', '')}"
    ).strip()


def add_list_field(embed, name, items):
    if not items:
        return
    text = '\n'.join(summarize_action(item) for item in items)
    embed.add_field(name=name, value=text[:1000], inline=False)


SCENARIO_AXIS = "成長加速 × 市場誤認 × 資金流入"
MARKET_TYPES = {"米国株", "日本株", "その他"}
POSITION_TYPES = {"超主力", "主力", "準主力", "観察枠"}
SELL_REASON_CATEGORIES = [
    "仮説崩れ",
    "資金流入反転",
    "バリュエーション過熱",
    "他銘柄への入替",
    "最大損失許容額超過",
    "メンタル不安",
    "ルール外売却",
    "その他",
]


def compact_value(value, default='-'):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def embed_value(value, limit=1000):
    text = compact_value(value)
    if len(text) <= limit:
        return text
    return text[:limit - 1] + '…'


def format_optional_money(amount):
    if amount in (None, ''):
        return '-'
    return format_money(amount, 'JPY')


def format_optional_percent(value):
    if value in (None, ''):
        return '-'
    return f"{value:.2f}%"


def parse_key_value_text(*texts):
    data = {}
    for text in texts:
        for raw_line in str(text or '').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            normalized = line.replace('：', ':')
            if ':' not in normalized:
                continue
            key, value = normalized.split(':', 1)
            data[key.strip()] = value.strip()
    return data


def first_value(data, *keys, default=''):
    for key in keys:
        if key in data and data[key] != '':
            return data[key]
    return default


def parse_optional_float(value):
    text = str(value or '').strip()
    if not text:
        return None
    text = (
        text.replace(',', '')
        .replace('円', '')
        .replace('¥', '')
        .replace('%', '')
        .strip()
    )
    if not text:
        return None
    return float(text)


def parse_active_flag(value):
    text = str(value or '').strip().lower()
    if text in ('', 'true', '1', 'yes', 'y', 'on', 'active', '有効', 'はい'):
        return True
    if text in ('false', '0', 'no', 'n', 'off', 'inactive', '無効', 'いいえ'):
        return False
    return True


def normalize_scenario_data(ticker, raw_data):
    market_type = first_value(raw_data, '市場区分', '市場')
    position_type = first_value(raw_data, '投資区分', '区分')
    if market_type and market_type not in MARKET_TYPES:
        raise ValueError("市場区分は 米国株 / 日本株 / その他 のいずれかで入力してください。")
    if position_type and position_type not in POSITION_TYPES:
        raise ValueError("投資区分は 超主力 / 主力 / 準主力 / 観察枠 のいずれかで入力してください。")
    return {
        'ticker': ticker.upper(),
        'company_name': first_value(raw_data, '銘柄名', '会社名'),
        'market_type': market_type or 'その他',
        'position_type': position_type or '観察枠',
        'investment_amount': parse_optional_float(first_value(raw_data, '投資額')),
        'portfolio_weight': parse_optional_float(first_value(raw_data, '現在の保有比率', '保有比率')),
        'buy_reason': first_value(raw_data, '購入理由'),
        'business_thesis': first_value(raw_data, '事業仮説'),
        'market_mispricing': first_value(raw_data, '市場誤認'),
        'growth_thesis': first_value(raw_data, '成長仮説'),
        'capital_flow_reason': first_value(raw_data, '資金流入の根拠', '資金流入'),
        'next_earnings_watch': first_value(raw_data, '次の決算で見る数字', '次回決算で見る数字'),
        'hold_condition': first_value(raw_data, '継続条件'),
        'reduce_condition': first_value(raw_data, '一部縮小条件'),
        'exit_condition': first_value(raw_data, '全撤退条件'),
        'max_loss_amount': parse_optional_float(first_value(raw_data, '最大損失許容額')),
        'earnings_date': first_value(raw_data, '決算予定日'),
        'review_date': first_value(raw_data, '3か月レビュー予定日', '3ヶ月レビュー予定日'),
        'memo': first_value(raw_data, 'メモ', 'memo'),
        'active': parse_active_flag(first_value(raw_data, 'active', 'activeフラグ', default='有効')),
    }


def scenario_template(scenario=None):
    scenario = scenario or {}
    def get(key, default=''):
        return compact_value(scenario.get(key), default='')

    basic = (
        f"銘柄名: {get('company_name')}\n"
        f"市場区分: {get('market_type', '米国株') or '米国株'}\n"
        f"投資区分: {get('position_type', '観察枠') or '観察枠'}\n"
        f"投資額: {get('investment_amount')}\n"
        f"現在の保有比率: {get('portfolio_weight')}\n"
        f"active: {'有効' if scenario.get('active', 1) else '無効'}"
    )
    thesis = (
        f"購入理由: {get('buy_reason')}\n"
        f"事業仮説: {get('business_thesis')}\n"
        f"市場誤認: {get('market_mispricing')}\n"
        f"成長仮説: {get('growth_thesis')}\n"
        f"資金流入の根拠: {get('capital_flow_reason')}"
    )
    earnings = (
        f"次の決算で見る数字: {get('next_earnings_watch')}\n"
        f"継続条件: {get('hold_condition')}"
    )
    rules = (
        f"一部縮小条件: {get('reduce_condition')}\n"
        f"全撤退条件: {get('exit_condition')}\n"
        f"最大損失許容額: {get('max_loss_amount')}"
    )
    schedule = (
        f"決算予定日: {get('earnings_date')}\n"
        f"3か月レビュー予定日: {get('review_date')}\n"
        f"メモ: {get('memo')}"
    )
    return basic, thesis, earnings, rules, schedule


def create_scenario_embed(scenario, title="【投資シナリオ】"):
    embed = discord.Embed(title=title, color=discord.Color.blurple())
    embed.add_field(
        name="銘柄",
        value=f"{scenario['ticker']} / {compact_value(scenario.get('company_name'))}",
        inline=False,
    )
    embed.add_field(name="市場区分", value=compact_value(scenario.get('market_type')), inline=True)
    embed.add_field(name="投資区分", value=compact_value(scenario.get('position_type')), inline=True)
    embed.add_field(name="投資額", value=format_optional_money(scenario.get('investment_amount')), inline=True)
    embed.add_field(name="保有比率", value=format_optional_percent(scenario.get('portfolio_weight')), inline=True)
    embed.add_field(name="投資軸", value=SCENARIO_AXIS, inline=False)
    sections = [
        ("購入理由", 'buy_reason'),
        ("事業仮説", 'business_thesis'),
        ("市場誤認", 'market_mispricing'),
        ("成長仮説", 'growth_thesis'),
        ("資金流入の根拠", 'capital_flow_reason'),
        ("次回決算で見る数字", 'next_earnings_watch'),
        ("継続条件", 'hold_condition'),
        ("一部縮小条件", 'reduce_condition'),
        ("全撤退条件", 'exit_condition'),
        ("最大損失許容額", 'max_loss_amount'),
        ("決算予定日", 'earnings_date'),
        ("3か月レビュー予定日", 'review_date'),
        ("メモ", 'memo'),
    ]
    for label, key in sections:
        value = scenario.get(key)
        if key == 'max_loss_amount':
            value = format_optional_money(value)
        embed.add_field(name=label, value=embed_value(value), inline=False)
    if scenario.get('created_at'):
        embed.add_field(name="登録日", value=format_datetime_jst(scenario.get('created_at')), inline=True)
    if scenario.get('updated_at'):
        embed.add_field(name="更新日", value=format_datetime_jst(scenario.get('updated_at')), inline=True)
    embed.set_footer(text=f"active: {'有効' if scenario.get('active') else '無効'}")
    return embed


class ScenarioModal(discord.ui.Modal):
    def __init__(self, ticker, existing=None, mode='register'):
        title = 'シナリオ更新' if mode == 'update' else 'シナリオ登録'
        super().__init__(title=title)
        self.ticker = ticker.upper()
        self.mode = mode
        basic, thesis, earnings, rules, schedule = scenario_template(existing)
        inputs = [
            ('basic', '基本情報', basic),
            ('thesis', '投資仮説', thesis),
            ('earnings', '決算確認', earnings),
            ('rules', '売買ルール', rules),
            ('schedule', '予定とメモ', schedule),
        ]
        for custom_id, label, default in inputs:
            self.add_item(discord.ui.TextInput(
                label=label,
                custom_id=custom_id,
                style=discord.TextStyle.paragraph,
                default=default[:4000],
                required=False,
                max_length=4000,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            raw = parse_key_value_text(*(item.value for item in self.children))
            scenario_data = normalize_scenario_data(self.ticker, raw)
            scenario = db.add_or_update_scenario(
                interaction.user.id,
                scenario_data,
                save_history=(self.mode == 'update'),
            )
            title = "【投資シナリオ更新】" if self.mode == 'update' else "【投資シナリオ登録】"
            await interaction.followup.send(embed=create_scenario_embed(scenario, title=title))
        except ValueError as exc:
            await interaction.followup.send(f"入力内容を確認してください: {exc}", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"シナリオ保存中にエラーが発生しました: {exc}", ephemeral=True)


class SellRecordModal(discord.ui.Modal):
    def __init__(self, ticker, company_name, reason_category):
        super().__init__(title='売却記録')
        self.ticker = ticker.upper()
        self.company_name = company_name
        self.reason_category = reason_category
        defaults = [
            ('basic', '売却内容', "売却日: \n売却数量: \n売却金額: "),
            ('reason', '売却理由詳細', "売却理由詳細: "),
            ('scenario', '売却時のシナリオ状態', "売却時のシナリオ状態: "),
            ('emotion', '売却時の感情状態', "売却時の感情状態: "),
            ('reflection', '反省とメモ', "売却後の反省: \nメモ: "),
        ]
        for custom_id, label, default in defaults:
            self.add_item(discord.ui.TextInput(
                label=label,
                custom_id=custom_id,
                style=discord.TextStyle.paragraph,
                default=default,
                required=False,
                max_length=4000,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            raw = parse_key_value_text(*(item.value for item in self.children))
            sell_data = {
                'ticker': self.ticker,
                'company_name': self.company_name,
                'sell_date': first_value(raw, '売却日'),
                'sell_quantity': parse_optional_float(first_value(raw, '売却数量')),
                'sell_amount': parse_optional_float(first_value(raw, '売却金額')),
                'reason_category': self.reason_category,
                'reason_detail': first_value(raw, '売却理由詳細', '売却理由'),
                'scenario_status_at_sell': first_value(raw, '売却時のシナリオ状態'),
                'emotion_at_sell': first_value(raw, '売却時の感情状態'),
                'reflection': first_value(raw, '売却後の反省', '反省'),
                'memo': first_value(raw, 'メモ', 'memo'),
            }
            db.add_sell_record(interaction.user.id, sell_data)
            embed = discord.Embed(title="【売却記録】", color=discord.Color.orange())
            embed.add_field(name="銘柄", value=f"{self.ticker} / {compact_value(self.company_name)}", inline=False)
            embed.add_field(name="売却日", value=compact_value(sell_data['sell_date']), inline=True)
            embed.add_field(name="売却数量", value=compact_value(sell_data['sell_quantity']), inline=True)
            embed.add_field(name="売却金額", value=format_optional_money(sell_data['sell_amount']), inline=True)
            embed.add_field(name="理由カテゴリ", value=self.reason_category, inline=False)
            embed.add_field(name="売却理由", value=embed_value(sell_data['reason_detail']), inline=False)
            embed.add_field(name="売却時のシナリオ状態", value=embed_value(sell_data['scenario_status_at_sell']), inline=False)
            embed.add_field(name="売却時の感情状態", value=embed_value(sell_data['emotion_at_sell']), inline=False)
            embed.add_field(name="反省", value=embed_value(sell_data['reflection']), inline=False)
            if sell_data['memo']:
                embed.add_field(name="メモ", value=embed_value(sell_data['memo']), inline=False)
            await interaction.followup.send(embed=embed)
        except ValueError as exc:
            await interaction.followup.send(f"数値項目を確認してください: {exc}", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"売却記録の保存中にエラーが発生しました: {exc}", ephemeral=True)


def build_bulk_confirm_embed(actions, errors):
    embed = discord.Embed(title="一括反映の確認", color=discord.Color.blurple())
    embed.description = "保有セクションは初期登録/修正として既存保有を上書きします。/買い は既存保有に加算します。"
    add_list_field(embed, "資産", actions['ASSET'])
    add_list_field(embed, "資産内訳", actions['ASSET_BREAKDOWN'])
    add_list_field(embed, "入金", actions['DEPOSIT'])
    add_list_field(embed, "出金", actions['WITHDRAW'])
    add_list_field(embed, "買い", actions['BUY'])
    add_list_field(embed, "売り", actions['SELL'])
    add_list_field(embed, "保有", actions['HOLDING'])
    add_list_field(embed, "試算", actions['SIM'])
    if errors:
        embed.add_field(name="エラー", value='\n'.join(f"- {err}" for err in errors)[:1000], inline=False)
    success_count = sum(len(items) for items in actions.values())
    embed.set_footer(text=f"成功候補: {success_count}件 / エラー: {len(errors)}件")
    return embed


class BulkApplyView(discord.ui.View):
    def __init__(self, author_id, actions, errors):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.actions = actions
        self.errors = errors
        self.completed = False
        self.message = None

    def disable_all_buttons(self):
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message('この確認は入力者のみ操作できます。', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.completed = True
        self.disable_all_buttons()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='登録する', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.completed:
            await interaction.response.send_message('この確認はすでに処理済みです。', ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id
        success = 0
        failures = []
        try:
            for action in self.actions['ASSET']:
                db.set_asset(user_id, action['amount'])
                success += 1
            for action in self.actions['ASSET_BREAKDOWN']:
                db.set_asset_breakdown(user_id, action['name'], action['amount'], action['currency'])
                success += 1
            for action in self.actions['DEPOSIT']:
                db.add_deposit(user_id, action['amount'], action['currency'], action['memo'])
                success += 1
            for action in self.actions['WITHDRAW']:
                db.add_withdraw(user_id, action['amount'], action['currency'], action['memo'])
                success += 1
            for action in self.actions['BUY']:
                db.add_buy(user_id, action['ticker'], action['quantity'], action['price'], action['currency'], action['memo'])
                success += 1
            for action in self.actions['SELL']:
                try:
                    db.add_sell(user_id, action['ticker'], action['quantity'], action['price'], action['currency'], action['memo'])
                    success += 1
                except ValueError as exc:
                    failures.append(f"{action['line']}: {exc}")
            for action in self.actions['HOLDING']:
                db.add_holding(user_id, action['ticker'], action['quantity'], action['price'], action['currency'], action['memo'])
                success += 1
            for action in self.actions['SIM']:
                db.add_simulation(user_id, action['ticker'], action['quantity'], action['price'], action['currency'], action['memo'])
                success += 1
        except Exception as exc:
            await interaction.followup.send(f"一括反映中にエラーが発生しました: {exc}")
            return

        self.completed = True
        self.disable_all_buttons()
        embed = discord.Embed(title="一括反映を完了しました", color=discord.Color.green())
        embed.add_field(name="成功件数", value=str(success), inline=False)
        embed.add_field(name="失敗件数", value=str(len(self.errors) + len(failures)), inline=False)
        if self.errors or failures:
            embed.add_field(name="未反映", value='\n'.join(self.errors + failures)[:1000], inline=False)
        if self.message is not None:
            await self.message.edit(embed=embed, view=self)
        await interaction.followup.send("一括反映を完了しました。", ephemeral=True)

    @discord.ui.button(label='キャンセル', style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.completed:
            await interaction.response.send_message('この確認はすでに処理済みです。', ephemeral=True)
            return
        self.completed = True
        self.disable_all_buttons()
        embed = discord.Embed(title="一括反映をキャンセルしました", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=self)


class BulkApplyModal(discord.ui.Modal, title='一括反映'):
    text = discord.ui.TextInput(
        label='複数行テキスト',
        style=discord.TextStyle.paragraph,
        placeholder='入金 500000 JPY\n買い NET 10 220 USD',
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        actions, errors = parse_bulk_text(str(self.text.value))
        view = BulkApplyView(interaction.user.id, actions, errors)
        await interaction.response.send_message(embed=build_bulk_confirm_embed(actions, errors), view=view)
        view.message = await interaction.original_response()


def create_asset_embed(user_id, total_asset=None):
    cash_flow = db.get_cash_flow_summary(user_id)
    net_deposit = cash_flow['net_deposit']
    asset_info = db.get_asset(user_id)
    if total_asset is None:
        total_asset = asset_info['total_asset']
    initial_asset, base_date = asset_base_values(asset_info)
    breakdowns = db.get_asset_breakdowns(user_id)
    asset_change = db.get_asset_previous_change(user_id)

    increase = total_asset - initial_asset
    operation_result = increase - net_deposit
    target_amount = initial_asset * (1 + ANNUAL_TARGET)
    target_increase = target_amount - initial_asset
    progress = (increase / target_increase) * 100 if target_increase > 0 else 0

    embed = discord.Embed(title="📊 資産情報", color=discord.Color.blue())
    embed.add_field(name="現在の資産", value=format_money(total_asset), inline=False)
    embed.add_field(name="前回比", value=format_asset_change(asset_change), inline=False)
    embed.add_field(name="基準資産", value=format_money(initial_asset), inline=False)
    embed.add_field(name="入金合計", value=format_money(cash_flow['deposit_total']), inline=False)
    embed.add_field(name="出金合計", value=format_money(cash_flow['withdraw_total']), inline=False)
    embed.add_field(name="純入金額", value=format_money(net_deposit), inline=False)
    embed.add_field(name="運用成果", value=format_money(operation_result), inline=False)
    embed.add_field(name="年率20%目標額", value=format_money(target_amount), inline=False)
    embed.add_field(name="目標進捗", value=f"{progress:.1f}%", inline=False)
    if breakdowns:
        breakdown_text = '\n'.join(
            f"{item['name']}: {format_money(item['amount'], item['currency'])}"
            for item in breakdowns
        )
        embed.add_field(name="資産内訳", value=breakdown_text[:1000], inline=False)
    if asset_info.get('last_updated'):
        embed.add_field(name="更新日時", value=format_datetime_jst(asset_info['last_updated']), inline=False)
    embed.set_footer(text=f"基準日: {base_date.strftime('%Y年%m月%d日')}")
    return embed


def estimate_holding_value_jpy(holding, usdjpy=None):
    value_jpy = holding.get('current_value_jpy')
    if value_jpy is not None:
        return value_jpy, False

    quantity = holding.get('quantity') or 0
    price = holding.get('current_price')
    if price is None:
        price = holding.get('purchase_price')
    currency = (holding.get('current_currency') or holding.get('currency') or 'JPY').upper()
    if price is None:
        return None, True
    if currency == 'JPY':
        return quantity * price, True
    if currency == 'USD' and usdjpy:
        return quantity * price * usdjpy, True
    return None, True


def build_portfolio_risk_data(user_id, database=None, usdjpy=None):
    database = database or db
    asset_info = database.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    holdings = database.get_holdings(user_id)
    breakdowns = database.get_asset_breakdowns(user_id)

    holding_ratios = []
    approximate = False
    for holding in holdings:
        value_jpy, is_approx = estimate_holding_value_jpy(holding, usdjpy=usdjpy)
        if value_jpy is None:
            approximate = True
            continue
        approximate = approximate or is_approx
        ratio = value_jpy / current_asset if current_asset else 0
        holding_ratios.append({
            'symbol': holding['symbol'],
            'value_jpy': value_jpy,
            'ratio': ratio,
            'approximate': is_approx,
        })
    holding_ratios.sort(key=lambda item: item['value_jpy'], reverse=True)

    breakdown_ratios = []
    for item in breakdowns:
        amount = item.get('amount') or 0
        ratio = amount / current_asset if current_asset else 0
        breakdown_ratios.append({
            'name': item['name'],
            'amount': amount,
            'currency': item.get('currency') or 'JPY',
            'ratio': ratio,
        })
    breakdown_ratios.sort(key=lambda item: item['amount'], reverse=True)

    breakdown_amounts = {item['name']: item.get('amount') or 0 for item in breakdowns}
    cash_amount = sum(
        amount for name, amount in breakdown_amounts.items()
        if name in {'預り金', 'USドル'}
    )
    cash_ratio = cash_amount / current_asset if current_asset else 0

    jpy_names = {'国内株式', '投資信託', '投信', '預り金'}
    usd_names = {'米国株式', 'USドル'}
    jpy_amount = sum(amount for name, amount in breakdown_amounts.items() if name in jpy_names)
    usd_amount = sum(amount for name, amount in breakdown_amounts.items() if name in usd_names)
    other_amount = max(0, sum(breakdown_amounts.values()) - jpy_amount - usd_amount)

    decline_rates = [0.2, 0.4, 0.6]
    decline_scenarios = []
    for item in holding_ratios[:3]:
        scenarios = []
        for decline_rate in decline_rates:
            loss = item['value_jpy'] * decline_rate
            impact_rate = loss / current_asset if current_asset else 0
            scenarios.append({
                'decline_rate': decline_rate,
                'loss': loss,
                'impact_rate': impact_rate,
            })
        decline_scenarios.append({
            'symbol': item['symbol'],
            'value_jpy': item['value_jpy'],
            'scenarios': scenarios,
        })

    return {
        'current_asset': current_asset,
        'holding_ratios': holding_ratios,
        'breakdown_ratios': breakdown_ratios,
        'cash_amount': cash_amount,
        'cash_ratio': cash_ratio,
        'currency_amounts': {
            'JPY': jpy_amount,
            'USD': usd_amount,
            'その他': other_amount,
        },
        'decline_scenarios': decline_scenarios,
        'approximate': approximate,
    }


def create_risk_embed(user_id, update_result=None):
    update_result = update_result or {}
    risk = build_portfolio_risk_data(user_id, usdjpy=update_result.get('usdjpy'))
    current_asset = risk['current_asset']
    embed = discord.Embed(title="ポートフォリオ・リスク管理", color=discord.Color.orange())
    embed.add_field(name="現在資産", value=format_money(current_asset), inline=False)

    if risk['holding_ratios']:
        lines = []
        for item in risk['holding_ratios'][:10]:
            approx = "（概算）" if item.get('approximate') else ""
            lines.append(
                f"{item['symbol']}: {format_money(item['value_jpy'])} / {format_percent(item['ratio'])}{approx}"
            )
        embed.add_field(name="銘柄別保有比率", value='\n'.join(lines)[:1000], inline=False)
    else:
        embed.add_field(name="銘柄別保有比率", value="保有銘柄の円換算評価額がありません。`/更新` 後に再確認してください。", inline=False)

    if risk['breakdown_ratios']:
        lines = [
            f"{item['name']}: {format_money(item['amount'], item['currency'])} / {format_percent(item['ratio'])}"
            for item in risk['breakdown_ratios']
        ]
        embed.add_field(name="資産内訳比率", value='\n'.join(lines)[:1000], inline=False)
    else:
        embed.add_field(name="資産内訳比率", value="資産内訳が登録されていません。", inline=False)

    embed.add_field(
        name="現金比率",
        value=f"{format_money(risk['cash_amount'])} / {format_percent(risk['cash_ratio'])}",
        inline=False,
    )

    currency_lines = []
    for currency, amount in risk['currency_amounts'].items():
        if amount <= 0:
            continue
        ratio = amount / current_asset if current_asset else 0
        currency_lines.append(f"{currency}: {format_money(amount)} / {format_percent(ratio)}")
    embed.add_field(name="通貨別比率", value='\n'.join(currency_lines) if currency_lines else "-", inline=False)

    if risk['decline_scenarios']:
        lines = []
        for item in risk['decline_scenarios']:
            for scenario in item['scenarios']:
                lines.append(
                    f"{item['symbol']} -{scenario['decline_rate'] * 100:.0f}% → "
                    f"資産 -{scenario['impact_rate'] * 100:.1f}% / {format_signed_money(-scenario['loss'])}"
                )
        embed.add_field(name="主力銘柄の下落シミュレーション", value='\n'.join(lines)[:1000], inline=False)
    else:
        embed.add_field(name="主力銘柄の下落シミュレーション", value="対象銘柄がありません。", inline=False)

    footer = "売買推奨ではなく、集中度と下落耐性の可視化です。"
    if risk['approximate']:
        footer += " current_value_jpy がない銘柄は取得単価ベースの概算または除外です。"
    if update_result.get('failed'):
        footer += f" 価格取得失敗: {', '.join(update_result['failed'][:5])}"
    embed.set_footer(text=footer)
    return embed


def format_daily_risk_summary(risk):
    current_asset = risk.get('current_asset') or 0
    lines = []
    top_holding = risk.get('holding_ratios', [None])[0]
    if top_holding:
        approx = "（概算）" if top_holding.get('approximate') else ""
        lines.append(f"最大 {top_holding['symbol']} {format_percent(top_holding['ratio'])}{approx}")
    else:
        lines.append("最大 -")

    lines.append(f"現金 {format_percent(risk.get('cash_ratio'))}")

    currency_amounts = risk.get('currency_amounts') or {}
    jpy_amount = currency_amounts.get('JPY') or 0
    usd_amount = currency_amounts.get('USD') or 0
    jpy_ratio = jpy_amount / current_asset if current_asset else 0
    usd_ratio = usd_amount / current_asset if current_asset else 0
    lines.append(f"JPY {format_percent(jpy_ratio)} / USD {format_percent(usd_ratio)}")

    top_scenario = risk.get('decline_scenarios', [None])[0]
    if top_scenario:
        lines.append("")
        lines.append(f"{top_scenario['symbol']} 下落影響")
        for scenario in top_scenario['scenarios']:
            lines.append(
                f"-{scenario['decline_rate'] * 100:.0f}% {format_daily_signed_money(-scenario['loss'], risk=True)} "
                f"/ {format_percent(-scenario['impact_rate'], signed=True)}"
            )
    else:
        lines.append("下落 -")
    return '\n'.join(lines)


async def update_market_prices(user_id):
    """保有・試算の価格を取得してDBに反映する。current_assetsは更新しない。"""
    holdings = db.get_holdings(user_id)
    simulations = db.get_simulations(user_id)
    usdjpy = await asyncio.to_thread(fetch_usdjpy)
    failed = []
    holding_lines = []
    simulation_lines = []
    holding_success = 0
    simulation_success = 0

    async def resolve_price(item, ticker_key, entry_price):
        fetched = await asyncio.to_thread(fetch_quote, ticker_key, item.get('currency'))
        if fetched and fetched.get('price') is not None:
            return fetched
        failed.append(ticker_key)
        fallback_price = item.get('current_price') if item.get('current_price') is not None else entry_price
        return {
            'price': fallback_price,
            'currency': item.get('current_currency') or item.get('currency') or 'USD',
            'previous_close': None,
            'change': None,
            'change_rate': None,
            'fallback': True,
        }

    for holding in holdings:
        result = await resolve_price(holding, holding['symbol'], holding['purchase_price'])
        if db.update_holding_valuation(
            user_id,
            holding['symbol'],
            result['price'],
            result['currency'],
            usdjpy,
            result.get('previous_close'),
            result.get('change'),
            result.get('change_rate'),
        ):
            holding_success += 1
            updated = db.get_holding_by_symbol(user_id, holding['symbol'])
            holding_lines.append(
                f"- {updated['symbol']}: {format_price(updated['current_price'], position_currency(updated))} / "
                f"前日比 {format_day_change(updated)} / "
                f"評価額 {format_money(updated['current_value'], position_currency(updated))} / "
                f"損益 {format_signed_money(updated['unrealized_pnl'], position_currency(updated))}"
            )

    for simulation in simulations:
        result = await resolve_price(simulation, simulation['ticker'], simulation['entry_price'])
        if db.update_simulation_valuation(
            user_id,
            simulation['ticker'],
            result['price'],
            result['currency'],
            usdjpy,
            result.get('previous_close'),
            result.get('change'),
            result.get('change_rate'),
        ):
            simulation_success += 1
            updated = [item for item in db.get_simulations(user_id) if item['ticker'] == simulation['ticker']][0]
            simulation_lines.append(
                f"- {updated['ticker']}: {format_price(updated['current_price'], position_currency(updated))} / "
                f"前日比 {format_day_change(updated)} / "
                f"評価額 {format_money(updated['current_value'], position_currency(updated))} / "
                f"損益 {format_signed_money(updated['unrealized_pnl'], position_currency(updated))}"
            )

    return {
        'usdjpy': usdjpy,
        'failed': sorted(set(failed)),
        'holding_lines': holding_lines,
        'simulation_lines': simulation_lines,
        'holding_success': holding_success,
        'simulation_success': simulation_success,
    }


def build_update_result_embed(update_result):
    embed = discord.Embed(title="/更新 実行結果", color=discord.Color.blue())
    usdjpy = update_result['usdjpy']
    failed = update_result['failed']
    embed.add_field(name="為替", value=f"USDJPY {usdjpy:.2f}" if usdjpy else "USDJPY 取得失敗", inline=False)
    embed.add_field(name="保有更新", value='\n'.join(update_result['holding_lines'])[:1000] if update_result['holding_lines'] else "なし", inline=False)
    embed.add_field(name="試算更新", value='\n'.join(update_result['simulation_lines'])[:1000] if update_result['simulation_lines'] else "なし", inline=False)
    embed.add_field(name="成功件数", value=f"保有 {update_result['holding_success']}件 / 試算 {update_result['simulation_success']}件", inline=False)
    embed.add_field(name="取得失敗", value='\n'.join(f"- {item}" for item in failed) if failed else "なし", inline=False)
    embed.set_footer(text="現在資産は更新していません。総資産更新は /一括反映 または /資産更新 を使ってください。")
    return embed


def _truncate_lines(lines, limit=1000):
    text = '\n'.join(lines)
    if len(text) <= limit:
        return text or "なし"
    trimmed = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > limit - 20:
            break
        trimmed.append(line)
        total += len(line) + 1
    trimmed.append("...")
    return '\n'.join(trimmed)


def pad_daily_section(text):
    return f"\n{text}\n"


def format_daily_asset_summary(report_data):
    return (
        f"現在 {format_money(report_data['current_asset'])}\n"
        f"前回 {format_daily_asset_change(report_data['asset_change'])}\n"
        f"成果 {format_daily_signed_money(report_data['operation_result'])}\n"
        f"差分 {format_daily_signed_money(report_data['target_diff'])}"
    )


def _build_position_embeds(title, items, name_key, entry_label='平均取得単価', quantity_label='株数', color=discord.Color.green()):
    if not items:
        embed = discord.Embed(title=title, description="なし", color=color)
        return [embed]

    embeds = []
    for index in range(0, len(items), 25):
        chunk = items[index:index + 25]
        suffix = f" {index // 25 + 1}" if index else ""
        embed = discord.Embed(title=f"{title}{suffix}", color=color)
        embed.description = "\u200b"
        for item in chunk:
            embed.add_field(
                name=item[name_key],
                value=format_position_value(item, entry_label=entry_label, quantity_label=quantity_label)[:1024],
                inline=False,
            )
        embeds.append(embed)
    return embeds


def _build_daily_holding_embeds(items, usdjpy=None):
    if not items:
        embed = discord.Embed(title="保有銘柄", description="なし", color=discord.Color.green())
        return [embed]

    embeds = []
    for index in range(0, len(items), 25):
        chunk = items[index:index + 25]
        suffix = f" {index // 25 + 1}" if index else ""
        embed = discord.Embed(title=f"保有銘柄{suffix}", color=discord.Color.green())
        embed.description = "\u200b"
        for item in chunk:
            embed.add_field(
                name=holding_display_name(item),
                value=format_daily_holding_value(item, usdjpy=usdjpy)[:1024],
                inline=False,
            )
        embeds.append(embed)
    return embeds


def enrich_holding_display_names(user_id, holdings):
    enriched = []
    for holding in holdings:
        item = dict(holding)
        scenario = db.get_scenario_by_ticker(user_id, item['symbol'], active_only=False)
        if scenario and scenario.get('company_name'):
            item['company_name'] = scenario['company_name']
        enriched.append(item)
    return enriched


def build_daily_report_data(user_id, update_result=None):
    asset_info = db.get_asset(user_id)
    initial_asset, base_date = asset_base_values(asset_info)
    current_asset = asset_info['total_asset']
    cash_flow = db.get_cash_flow_summary(user_id)
    asset_change = db.get_asset_previous_change(user_id)
    net_deposit = cash_flow['net_deposit']
    operation_result = current_asset - initial_asset - net_deposit
    return_rate = (operation_result / initial_asset) * 100 if initial_asset else 0
    target_amount = initial_asset * (1 + ANNUAL_TARGET)
    target_diff = current_asset - target_amount

    return {
        'user_id': user_id,
        'asset_info': asset_info,
        'base_date': base_date,
        'current_asset': current_asset,
        'initial_asset': initial_asset,
        'cash_flow': cash_flow,
        'asset_change': asset_change,
        'operation_result': operation_result,
        'return_rate': return_rate,
        'target_amount': target_amount,
        'target_diff': target_diff,
        'breakdowns': db.get_asset_breakdowns(user_id),
        'holdings': enrich_holding_display_names(user_id, db.get_holdings(user_id)),
        'simulations': db.get_simulations(user_id),
        'risk_data': build_portfolio_risk_data(user_id, usdjpy=(update_result or {}).get('usdjpy')),
        'update_result': update_result or {},
        'generated_at': now_jst(),
    }


def build_daily_report_embeds(report_data):
    embeds = []
    update_result = report_data.get('update_result') or {}
    usdjpy = update_result.get('usdjpy')
    failed = update_result.get('failed') or []

    risk_data = report_data.get('risk_data')

    summary_parts = [
        "資産サマリー",
        format_daily_asset_summary(report_data),
    ]
    if risk_data:
        summary_parts.extend(["", "リスク概要", format_daily_risk_summary(risk_data)])
    summary = discord.Embed(
        title="📊 日次資産レポート",
        description="\n".join(summary_parts)[:4096],
        color=discord.Color.blue(),
    )
    embeds.append(summary)

    breakdown_lines = [
        f"{item['name']}: {format_money(item['amount'], item['currency'])}"
        for item in report_data['breakdowns']
    ]
    info_text = "\n".join([
        "資産内訳",
        _truncate_lines(breakdown_lines),
        "",
        "更新情報",
        (f"USDJPY: {usdjpy:.2f}" if usdjpy else "USDJPY: 取得失敗"),
        f"更新日時: {report_data['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}",
        f"価格取得失敗: {', '.join(failed) if failed else 'なし'}",
    ])
    embeds.append(discord.Embed(
        title="資産内訳・更新情報",
        description=info_text[:4096],
        color=discord.Color.blue(),
    ))

    embeds.extend(_build_daily_holding_embeds(report_data['holdings'], usdjpy=usdjpy))

    embeds.extend(_build_position_embeds(
        "試算",
        report_data['simulations'],
        'ticker',
        entry_label='想定取得単価',
        quantity_label='想定株数',
        color=discord.Color.teal(),
    ))

    return embeds


async def send_daily_report(channel, user_id=None):
    if user_id is None:
        user_id = get_daily_report_user_id()
    if user_id is None:
        print("[daily_report] user_id not found")
        await channel.send("日次レポート対象のユーザー資産が見つかりません。")
        return

    print("[daily_report] 日次レポート開始")
    update_result = await update_market_prices(user_id)
    print(
        f"[daily_report] 価格更新成功件数 holdings={update_result['holding_success']} "
        f"simulations={update_result['simulation_success']}"
    )
    print(f"[daily_report] 価格更新失敗件数 {len(update_result['failed'])}")
    report_data = build_daily_report_data(user_id, update_result)
    embeds = build_daily_report_embeds(report_data)
    for embed in embeds:
        await channel.send(embed=embed)
    print("[daily_report] 投稿成功")


def get_daily_report_user_id():
    if DAILY_REPORT_USER_ID:
        try:
            return int(DAILY_REPORT_USER_ID)
        except ValueError:
            print(f"[daily_report] invalid DAILY_REPORT_USER_ID={DAILY_REPORT_USER_ID}")
    return db.get_latest_user_id()


@tree.command(name="資産", description="現在の資産状況を表示します")
async def show_asset(interaction: discord.Interaction):
    """資産コマンド: /資産"""
    await interaction.response.defer(thinking=True)
    try:
        user_id = interaction.user.id
        await interaction.followup.send(embed=create_asset_embed(user_id))
    except Exception as exc:
        await interaction.followup.send(f"資産表示中にエラーが発生しました: {exc}")


@tree.command(name="資産更新", description="現在資産を手動更新します")
async def update_total_asset(interaction: discord.Interaction, 金額: int, 通貨: str = 'JPY'):
    """資産更新コマンド: /資産更新 金額 通貨"""
    user_id = interaction.user.id
    db.set_asset(user_id, 金額)
    embed = create_asset_embed(user_id, 金額)
    embed.title = "📊 現在資産を更新しました"
    embed.add_field(name="更新額", value=format_money(金額, 通貨.upper()), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="資産設定", description="基準資産・基準日・現在資産を設定します")
async def set_base_asset(interaction: discord.Interaction, 金額: int, 基準日: str = '2026-06-09'):
    """資産設定コマンド: /資産設定 金額 YYYY-MM-DD"""
    user_id = interaction.user.id
    try:
        base_date = parse_date_text(基準日)
    except ValueError:
        await interaction.response.send_message("基準日は `YYYY-MM-DD` 形式で入力してください。例: `/資産設定 7096249 2026-06-09`")
        return

    db.set_base_asset(user_id, 金額, base_date.date())
    embed = discord.Embed(title="基準資産を設定しました", color=discord.Color.blue())
    embed.add_field(name="基準資産", value=format_money(金額), inline=False)
    embed.add_field(name="現在資産", value=format_money(金額), inline=False)
    embed.add_field(name="基準日", value=base_date.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="更新", description="保有と試算の現在価格を更新します")
async def update_prices(interaction: discord.Interaction):
    """更新コマンド: /更新"""
    await interaction.response.defer(thinking=True)
    user_id = interaction.user.id
    try:
        update_result = await update_market_prices(user_id)
        await interaction.followup.send(embed=build_update_result_embed(update_result))
    except Exception as exc:
        await interaction.followup.send(f"更新中にエラーが発生しました: {exc}")


@tree.command(name="入金", description="入金を記録します")
async def add_deposit(interaction: discord.Interaction, 金額: int, 通貨: str = 'JPY', メモ: str = ''):
    """入金コマンド: /入金 金額 通貨"""
    user_id = interaction.user.id
    currency = 通貨.upper()
    db.add_deposit(user_id, 金額, currency, メモ)
    cash_flow = db.get_cash_flow_summary(user_id)
    breakdowns = db.get_asset_breakdowns(user_id)
    asset_change = db.get_asset_previous_change(user_id)

    embed = discord.Embed(title="💰 入金を記録しました", color=discord.Color.green())
    embed.add_field(name="入金額", value=format_money(金額, currency), inline=False)
    embed.add_field(name="入金合計", value=format_money(cash_flow['deposit_total']), inline=False)
    embed.add_field(name="純入金額", value=format_money(cash_flow['net_deposit']), inline=False)
    embed.set_footer(text=f"記録日時: {now_jst().strftime('%Y年%m月%d日 %H:%M')}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="出金", description="出金を記録します")
async def add_withdraw(interaction: discord.Interaction, 金額: int, 通貨: str = 'JPY', メモ: str = ''):
    """出金コマンド: /出金 金額 通貨"""
    user_id = interaction.user.id
    currency = 通貨.upper()
    db.add_withdraw(user_id, 金額, currency, メモ)
    cash_flow = db.get_cash_flow_summary(user_id)

    embed = discord.Embed(title="💸 出金を記録しました", color=discord.Color.orange())
    embed.add_field(name="出金額", value=format_money(金額, currency), inline=False)
    embed.add_field(name="出金合計", value=format_money(cash_flow['withdraw_total']), inline=False)
    embed.add_field(name="純入金額", value=format_money(cash_flow['net_deposit']), inline=False)
    embed.set_footer(text=f"記録日時: {now_jst().strftime('%Y年%m月%d日 %H:%M')}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="買い", description="買い取引を記録します")
async def add_buy(interaction: discord.Interaction, 銘柄: str, 株数: float, 価格: float, 通貨: str = 'USD', メモ: str = ''):
    """買いコマンド: /買い 銘柄 株数 価格 通貨"""
    user_id = interaction.user.id
    currency = 通貨.upper()
    holding = db.add_buy(user_id, 銘柄, 株数, 価格, currency, メモ)

    embed = discord.Embed(title="🟢 買い取引を記録しました", color=discord.Color.green())
    embed.add_field(name="銘柄", value=holding['symbol'], inline=False)
    embed.add_field(name="買付株数", value=f"{株数:,}", inline=False)
    embed.add_field(name="買付価格", value=format_money(価格, currency), inline=False)
    embed.add_field(name="買付金額", value=format_money(株数 * 価格, currency), inline=False)
    embed.add_field(name="現在株数", value=f"{holding['quantity']:,}", inline=False)
    embed.add_field(name="平均取得単価", value=format_money(holding['purchase_price'], currency), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="売り", description="売り取引を記録します")
async def add_sell(interaction: discord.Interaction, 銘柄: str, 株数: float, 価格: float, 通貨: str = 'USD', メモ: str = ''):
    """売りコマンド: /売り 銘柄 株数 価格 通貨"""
    user_id = interaction.user.id
    currency = 通貨.upper()
    try:
        result = db.add_sell(user_id, 銘柄, 株数, 価格, currency, メモ)
    except ValueError as exc:
        await interaction.response.send_message(f"❌ {exc}")
        return

    embed = discord.Embed(title="🔴 売り取引を記録しました", color=discord.Color.red())
    embed.add_field(name="銘柄", value=result['symbol'], inline=False)
    embed.add_field(name="売却株数", value=f"{株数:,}", inline=False)
    embed.add_field(name="売却価格", value=format_money(価格, currency), inline=False)
    embed.add_field(name="売却金額", value=format_money(株数 * 価格, currency), inline=False)
    embed.add_field(name="残り株数", value=f"{result['quantity']:,}", inline=False)
    embed.add_field(name="実現損益", value=format_money(result['realized_profit'], currency), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="履歴", description="直近の取引履歴を表示します")
async def show_transactions(interaction: discord.Interaction, 件数: int = 10):
    """履歴コマンド: /履歴"""
    user_id = interaction.user.id
    limit = max(1, min(件数, 20))
    transactions = db.get_transactions(user_id, limit)
    if not transactions:
        await interaction.response.send_message("取引履歴がありません。")
        return

    embed = discord.Embed(title=f"🧾 直近{limit}件の取引履歴", color=discord.Color.blurple())
    for tx in transactions:
        value = (
            f"type: {tx['type']}\n"
            f"ticker: {tx['ticker'] or '-'}\n"
            f"quantity: {tx['quantity'] if tx['quantity'] is not None else '-'}\n"
            f"price: {tx['price'] if tx['price'] is not None else '-'}\n"
            f"amount: {tx['amount'] if tx['amount'] is not None else '-'} {tx['currency'] or ''}\n"
            f"memo: {tx['memo'] or '-'}\n"
            f"created_at: {format_datetime_jst(tx['created_at'])}"
        )
        embed.add_field(name=tx['date'], value=value, inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="一括反映", description="複数行テキストを解析して確認後に一括登録します")
async def bulk_apply(interaction: discord.Interaction):
    await interaction.response.send_modal(BulkApplyModal())


@tree.command(name="日次レポート", description="日次資産レポートを手動投稿します")
async def manual_daily_report(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        await send_daily_report(interaction.channel, interaction.user.id)
        await interaction.followup.send("日次資産レポートを投稿しました。", ephemeral=True)
    except Exception as exc:
        print(f"[daily_report] manual report failed: {exc}")
        await interaction.followup.send(f"日次レポート作成中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="試算", description="試算ポジションを表示します")
async def show_simulations(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        user_id = interaction.user.id
        simulations = db.get_simulations(user_id)
        if not simulations:
            await interaction.followup.send("試算ポジションはありません。")
            return

        embed = discord.Embed(title="🧪 試算ポジション", color=discord.Color.teal())
        for sim in simulations:
            embed.add_field(
                name=sim['ticker'],
                value=format_position_value(sim, entry_label='想定取得単価', quantity_label='想定株数'),
                inline=False
            )
        await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"試算表示中にエラーが発生しました: {exc}")


@tree.command(name="試算登録", description="試算ポジションを登録します")
async def add_simulation(interaction: discord.Interaction, 銘柄: str, 株数: float, 価格: float, 通貨: str = 'USD', メモ: str = ''):
    user_id = interaction.user.id
    db.add_simulation(user_id, 銘柄, 株数, 価格, 通貨, メモ)
    embed = discord.Embed(title="試算ポジションを登録しました", color=discord.Color.teal())
    embed.add_field(name="銘柄", value=銘柄.upper(), inline=False)
    embed.add_field(name="想定株数", value=f"{株数:,}", inline=False)
    embed.add_field(name="想定取得単価", value=f"{価格:,} {通貨.upper()}", inline=False)
    embed.add_field(name="memo", value=メモ or '-', inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="試算削除", description="試算ポジションを削除します")
async def delete_simulation(interaction: discord.Interaction, 銘柄: str):
    user_id = interaction.user.id
    changed = db.delete_simulation(user_id, 銘柄)
    if changed:
        await interaction.response.send_message(f"{銘柄.upper()} の試算を削除しました。")
    else:
        await interaction.response.send_message(f"{銘柄.upper()} の試算は見つかりませんでした。")


@tree.command(name="保有", description="保有一覧の表示、または保有銘柄を初期登録・修正します")
async def add_holding(
    interaction: discord.Interaction,
    銘柄: str = '',
    株数: float = 0.0,
    取得単価: float = 0.0,
    通貨: str = 'JPY'
):
    """保有コマンド: /保有 銘柄 株数 取得単価 通貨"""
    await interaction.response.defer(thinking=True)
    try:
        user_id = interaction.user.id
        if not 銘柄:
            holdings = db.get_holdings(user_id)
            if not holdings:
                await interaction.followup.send("保有銘柄はありません。")
                return
            embed = discord.Embed(title="📈 保有銘柄一覧", color=discord.Color.brand_green())
            for holding in holdings:
                embed.add_field(name=holding['symbol'], value=format_position_value(holding), inline=False)
            await interaction.followup.send(embed=embed)
            return

        if 株数 <= 0 or 取得単価 <= 0:
            await interaction.followup.send("登録する場合は `/保有 銘柄 株数 取得単価 通貨` を入力してください。")
            return

        db.add_holding(user_id, 銘柄, 株数, 取得単価, 通貨)

        embed = discord.Embed(title="📈 保有銘柄を登録しました", color=discord.Color.brand_green())
        embed.description = "通常運用では `/買い` `/売り` を使い、初期登録や修正時だけ `/保有` を使います。"
        embed.add_field(name="銘柄", value=銘柄.upper(), inline=False)
        embed.add_field(name="株数", value=f"{株数:,}", inline=False)
        embed.add_field(name="取得単価", value=f"{取得単価:,} {通貨.upper()}", inline=False)
        embed.add_field(name="通貨", value=通貨.upper(), inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"保有処理中にエラーが発生しました: {exc}")


@tree.command(name="仮説登録", description="銘柄の投資仮説を登録・更新します")
async def register_hypothesis(interaction: discord.Interaction, 銘柄: str, 保有理由: str, 期待数字: str, 買い増し条件: str, 損切り条件: str):
    user_id = interaction.user.id
    db.add_or_update_hypothesis(user_id, 銘柄, 保有理由, 期待数字, 買い増し条件, 損切り条件)

    embed = discord.Embed(title="🧠 投資仮説を登録しました", color=discord.Color.blurple())
    embed.add_field(name="銘柄", value=銘柄.upper(), inline=False)
    embed.add_field(name="保有理由", value=保有理由, inline=False)
    embed.add_field(name="期待数字", value=期待数字, inline=False)
    embed.add_field(name="買い増し条件", value=買い増し条件, inline=False)
    embed.add_field(name="損切り条件", value=損切り条件, inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="仮説", description="登録済みの銘柄仮説を確認します")
async def show_hypothesis(interaction: discord.Interaction, 銘柄: str):
    user_id = interaction.user.id
    hypothesis = db.get_hypothesis(user_id, 銘柄)
    if not hypothesis:
        await interaction.response.send_message(
            f"❌ {銘柄.upper()} の投資仮説が登録されていません。`/仮説登録` で登録してください。"
        )
        return

    embed = discord.Embed(title=f"🧠 {hypothesis['symbol']} の投資仮説", color=discord.Color.blurple())
    embed.add_field(name="保有理由", value=hypothesis['reason'], inline=False)
    embed.add_field(name="期待数字", value=hypothesis['expected_return'], inline=False)
    embed.add_field(name="買い増し条件", value=hypothesis['add_condition'], inline=False)
    embed.add_field(name="損切り条件", value=hypothesis['cut_condition'], inline=False)
    embed.add_field(name="最終更新", value=format_datetime_jst(hypothesis['updated_at'] or hypothesis['created_at']), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="判定", description="銘柄判定の情報を表示します")
async def evaluate_holding(interaction: discord.Interaction, 銘柄: str):
    user_id = interaction.user.id
    asset_info = db.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    holding = db.get_holding_by_symbol(user_id, 銘柄)
    hypothesis = db.get_hypothesis(user_id, 銘柄)
    if not holding:
        await interaction.response.send_message(
            f"❌ {銘柄.upper()} の保有情報が登録されていません。`/買い` または `/保有` で登録してください。"
        )
        return

    total_cost = holding['quantity'] * holding['purchase_price']
    ratio = (total_cost / current_asset * 100) if current_asset else 0
    status = "✅ 問題なし" if ratio < 40 else "⚠️ 40% を超えています。分散を検討しましょう。"

    embed = discord.Embed(title=f"🧾 {holding['symbol']} の判定", color=discord.Color.gold())
    embed.add_field(name="保有数量", value=f"{holding['quantity']:,}", inline=False)
    embed.add_field(name="平均取得単価", value=f"{holding['purchase_price']:,} {holding['currency']}", inline=False)
    embed.add_field(name="保有コスト", value=format_money(total_cost, holding['currency']), inline=False)
    embed.add_field(name="資産比率", value=f"{ratio:.2f}%", inline=False)
    embed.add_field(name="判定", value=status, inline=False)
    if hypothesis:
        embed.add_field(name="保有理由", value=hypothesis['reason'], inline=False)
        embed.add_field(name="期待数字", value=hypothesis['expected_return'], inline=False)
        embed.add_field(name="買い増し条件", value=hypothesis['add_condition'], inline=False)
        embed.add_field(name="損切り条件", value=hypothesis['cut_condition'], inline=False)
    else:
        embed.add_field(name="仮説", value="登録されていません。`/仮説登録` で追加してください。", inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="比率", description="保有銘柄の資産比率を表示します")
async def show_ratios(interaction: discord.Interaction):
    user_id = interaction.user.id
    asset_info = db.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    holdings = db.get_holdings(user_id)
    if not holdings or current_asset == 0:
        await interaction.response.send_message(
            "❌ 保有銘柄または資産情報が登録されていません。`/買い` または `/保有` と `/資産` を使ってください。"
        )
        return

    embed = discord.Embed(title="📊 保有銘柄の比率", color=discord.Color.blue())
    warnings = []
    for holding in holdings:
        cost = holding['quantity'] * holding['purchase_price']
        ratio = (cost / current_asset) * 100 if current_asset else 0
        embed.add_field(
            name=f"{holding['symbol']} ({holding['currency']})",
            value=(
                f"{holding['quantity']:,} 株 @ {holding['purchase_price']:,}\n"
                f"コスト: {format_money(cost, holding['currency'])}\n"
                f"比率: {ratio:.2f}%"
            ),
            inline=False
        )
        if ratio >= 40:
            warnings.append(f"{holding['symbol']} が {ratio:.2f}% で40%超です。")
    if warnings:
        embed.add_field(name="⚠️ 警告", value="\n".join(warnings), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="目標", description="年率20%達成に必要な資産額を表示します")
async def show_goal(interaction: discord.Interaction):
    user_id = interaction.user.id
    asset_info = db.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    initial_asset, _ = asset_base_values(asset_info)
    target_amount = initial_asset * (1 + ANNUAL_TARGET)
    difference = current_asset - target_amount if current_asset else -target_amount

    embed = discord.Embed(title="🎯 年率20%目標", color=discord.Color.green())
    embed.add_field(name="基準資産", value=format_money(initial_asset), inline=False)
    embed.add_field(name="目標額", value=format_money(target_amount), inline=False)
    embed.add_field(name="現在資産", value=format_money(current_asset), inline=False)
    embed.add_field(name="目標との差分", value=format_money(difference), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="リスク", description="ポートフォリオの集中度・現金比率・通貨比率を表示します")
async def show_risk(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        user_id = interaction.user.id
        update_result = await update_market_prices(user_id)
        await interaction.followup.send(embed=create_risk_embed(user_id, update_result=update_result))
    except Exception as exc:
        await interaction.followup.send(f"リスク表示中にエラーが発生しました: {exc}")


@tree.command(name="レビュー", description="取引台帳ベースのレビューを表示します")
async def show_review(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        user_id = interaction.user.id
        asset_info = db.get_asset(user_id)
        if not asset_info:
            await interaction.followup.send(
                "❌ 資産情報が登録されていません。\n`/資産更新 金額` または `/一括反映` で資産を登録してください。"
            )
            return

        current_asset = asset_info['total_asset']
        initial_asset, base_date = asset_base_values(asset_info)
        cash_flow = db.get_cash_flow_summary(user_id)
        breakdowns = db.get_asset_breakdowns(user_id)
        asset_change = db.get_asset_previous_change(user_id)
        net_deposit = cash_flow['net_deposit']
        operation_result = current_asset - initial_asset - net_deposit
        return_excluding_deposits_rate = (operation_result / initial_asset) * 100 if initial_asset else 0
        target_amount = initial_asset * (1 + ANNUAL_TARGET)
        target_diff = current_asset - target_amount
        today = now_jst().date()
        days_elapsed = (today - base_date.date()).days
        quarters_passed = days_elapsed // 90

        embed = discord.Embed(title="📋 投資レビュー", color=discord.Color.purple())
        embed.add_field(name="レビュー期間", value=f"基準日から {quarters_passed}四半期 ({days_elapsed}日)", inline=False)
        embed.add_field(name="基準資産", value=format_money(initial_asset), inline=False)
        embed.add_field(name="現在資産", value=format_money(current_asset), inline=False)
        embed.add_field(name="前回比", value=format_asset_change(asset_change), inline=False)
        embed.add_field(name="入金合計", value=format_money(cash_flow['deposit_total']), inline=False)
        embed.add_field(name="出金合計", value=format_money(cash_flow['withdraw_total']), inline=False)
        embed.add_field(name="純入金額", value=format_money(net_deposit), inline=False)
        embed.add_field(name="運用成果", value=format_money(operation_result), inline=False)
        embed.add_field(name="入金除外リターン", value=f"{return_excluding_deposits_rate:+.2f}%", inline=False)
        embed.add_field(name="年20%目標額", value=format_money(target_amount), inline=False)
        embed.add_field(name="目標との差分", value=format_money(target_diff), inline=False)
        if breakdowns:
            breakdown_text = '\n'.join(
                f"{item['name']}: {format_money(item['amount'], item['currency'])}"
                for item in breakdowns
            )
            embed.add_field(name="資産内訳", value=breakdown_text[:1000], inline=False)
        embed.add_field(name="試算の扱い", value="試算ポジションはこのレビューの総資産に含めません。", inline=False)
        embed.set_footer(text=f"レビュー日時: {now_jst().strftime('%Y年%m月%d日 %H:%M')}")
        await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"レビュー表示中にエラーが発生しました: {exc}")


@tree.command(name="シナリオ登録", description="銘柄ごとの投資シナリオを登録します")
async def register_scenario(interaction: discord.Interaction, 銘柄コード: str):
    try:
        await interaction.response.send_modal(ScenarioModal(銘柄コード, mode='register'))
    except Exception as exc:
        await interaction.response.send_message(f"シナリオ登録画面の表示中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="シナリオ確認", description="登録済みの投資シナリオを確認します")
async def show_scenario(interaction: discord.Interaction, 銘柄コード: str):
    try:
        scenario = db.get_scenario_by_ticker(interaction.user.id, 銘柄コード, active_only=True)
        if not scenario:
            await interaction.response.send_message(
                f"{銘柄コード.upper()} の有効な投資シナリオは登録されていません。`/シナリオ登録` で登録してください。",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(embed=create_scenario_embed(scenario, title="【投資シナリオ確認】"))
    except Exception as exc:
        await interaction.response.send_message(f"シナリオ確認中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="シナリオ一覧", description="activeな投資シナリオを一覧表示します")
async def list_scenarios(interaction: discord.Interaction):
    try:
        scenarios = db.get_active_scenarios(interaction.user.id)
        if not scenarios:
            await interaction.response.send_message("有効な投資シナリオはまだ登録されていません。")
            return

        embed = discord.Embed(title="【投資シナリオ一覧】", color=discord.Color.green())
        embed.description = SCENARIO_AXIS
        for scenario in scenarios[:25]:
            value = (
                f"銘柄名: {compact_value(scenario.get('company_name'))}\n"
                f"区分: {compact_value(scenario.get('position_type'))}\n"
                f"投資額: {format_optional_money(scenario.get('investment_amount'))}\n"
                f"保有比率: {format_optional_percent(scenario.get('portfolio_weight'))}\n"
                f"決算予定日: {compact_value(scenario.get('earnings_date'))}\n"
                f"3か月レビュー: {compact_value(scenario.get('review_date'))}"
            )
            embed.add_field(name=scenario['ticker'], value=value, inline=False)
        if len(scenarios) > 25:
            embed.set_footer(text=f"表示: 25件 / 登録: {len(scenarios)}件")
        await interaction.response.send_message(embed=embed)
    except Exception as exc:
        await interaction.response.send_message(f"シナリオ一覧の表示中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="シナリオ更新", description="登録済みの投資シナリオを更新します")
async def update_scenario(interaction: discord.Interaction, 銘柄コード: str):
    try:
        scenario = db.get_scenario_by_ticker(interaction.user.id, 銘柄コード, active_only=False)
        if not scenario:
            await interaction.response.send_message(
                f"{銘柄コード.upper()} の投資シナリオは登録されていません。先に `/シナリオ登録` を使ってください。",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ScenarioModal(銘柄コード, existing=scenario, mode='update'))
    except Exception as exc:
        if interaction.response.is_done():
            await interaction.followup.send(f"シナリオ更新画面の表示中にエラーが発生しました: {exc}", ephemeral=True)
        else:
            await interaction.response.send_message(f"シナリオ更新画面の表示中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="売却記録", description="売却理由と売却時の心理状態を記録します")
@app_commands.choices(理由カテゴリ=[
    app_commands.Choice(name=category, value=category)
    for category in SELL_REASON_CATEGORIES
])
async def record_sell_reason(
    interaction: discord.Interaction,
    銘柄コード: str,
    銘柄名: str,
    理由カテゴリ: app_commands.Choice[str],
):
    try:
        await interaction.response.send_modal(SellRecordModal(銘柄コード, 銘柄名, 理由カテゴリ.value))
    except Exception as exc:
        await interaction.response.send_message(f"売却記録画面の表示中にエラーが発生しました: {exc}", ephemeral=True)


@tree.command(name="ヘルプ", description="使用可能なコマンド一覧")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="💡 投資台帳Bot - ヘルプ", color=discord.Color.lighter_gray())
    commands_info = [
        ("/一括反映", "資産・資産内訳・入出金・保有・試算をまとめて確認後に登録します"),
        ("/日次レポート", "朝7時の自動通知と同じ日次資産レポートを手動投稿します"),
        ("/資産", "現在資産・前回比・基準資産・入出金・資産内訳を表示します"),
        ("/資産更新 金額 通貨", "証券口座サマリーの現在資産を手動更新します"),
        ("/資産設定 金額 YYYY-MM-DD", "基準資産・基準日・現在資産を設定します"),
        ("/入金 金額 通貨", "入金を台帳に記録します"),
        ("/出金 金額 通貨", "出金を台帳に記録します"),
        ("/買い 銘柄 株数 価格 通貨", "買い取引を記録し、平均取得単価を更新します"),
        ("/売り 銘柄 株数 価格 通貨", "売り取引を記録し、保有数量を減らします"),
        ("/履歴", "直近の取引履歴を表示します"),
        ("/保有", "保有一覧を表示します。引数ありなら初期登録や修正をします"),
        ("/試算", "試算ポジションを表示します"),
        ("/試算登録 銘柄 株数 価格 通貨", "試算ポジションを登録します"),
        ("/試算削除 銘柄", "試算ポジションを削除します"),
        ("/更新", "保有・試算の現在価格と前日比を自動取得して評価損益を更新します"),
        ("/レビュー", "年20%目標に対する運用成果を確認します"),
        ("/リスク", "銘柄集中度・資産内訳・現金比率・通貨比率・下落影響を確認します"),
        ("/シナリオ登録 銘柄コード", "投資シナリオ登録用のModalを開きます"),
        ("/シナリオ確認 銘柄コード", "有効な投資シナリオを確認します"),
        ("/シナリオ一覧", "activeな投資シナリオを一覧表示します"),
        ("/シナリオ更新 銘柄コード", "登録済み投資シナリオをModalで更新します"),
        ("/売却記録 銘柄コード 銘柄名 理由カテゴリ", "売却理由、シナリオ状態、感情、反省を記録します"),
        ("/目標", "年率20%目標との差分を表示します"),
        ("/仮説 銘柄", "保存済みの投資仮説を確認します"),
        ("/仮説登録 銘柄 保有理由 期待数字 買い増し条件 損切り条件", "投資仮説を登録・更新します"),
        ("/判定 銘柄", "銘柄の判定と資産比率を表示します"),
        ("/比率", "保有銘柄の資産比率を表示します"),
    ]
    for cmd, desc in commands_info:
        embed.add_field(name=cmd, value=desc, inline=False)
    embed.set_footer(text=f"基準日: {BASE_DATE.strftime('%Y年%m月%d日')} | 基準資産: ¥{BASE_ASSET:,}")
    await interaction.response.send_message(embed=embed)


def main():
    """メイン関数"""
    token = os.getenv('DISCORD_TOKEN') or DISCORD_TOKEN
    if token == 'your_token_here':
        print("❌ エラー: DISCORD_TOKENが設定されていません")
        print("📝 .env ファイルを作成し、DISCORD_TOKEN=<your_token> を追加してください")
        return

    print("🤖 投資台帳Botを起動しています...")
    bot.run(token)


if __name__ == '__main__':
    main()
