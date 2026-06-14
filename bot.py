"""投資管理Discord Bot - メイン"""
import io
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import discord
from discord import app_commands
from datetime import datetime, timedelta
from PIL import Image

# .envファイルから環境変数を読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path, encoding='utf-8-sig')

try:
    import pytesseract
except ImportError:
    pytesseract = None

from config import DISCORD_TOKEN, BASE_ASSET, ANNUAL_TARGET, BASE_DATE
from database import InvestmentDatabase

# Discord Botの初期化
intents = discord.Intents.default()
intents.message_content = False  # Message Content Intent を無効化
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# データベース初期化
db = InvestmentDatabase()


@bot.event
async def on_ready():
    """Bot起動完了"""
    print(f'{bot.user} としてログインしました')
    await tree.sync()
    print('コマンドを同期しました')


def clean_number(value: str):
    if not value:
        return None
    text = value.replace('¥', '').replace('$', '').replace(',', '').strip()
    text = re.sub(r'[^\x00-\x7f]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    try:
        return float(text)
    except ValueError:
        return None


def extract_order_info(text: str):
    text = text.replace('\r', '\n')
    result = {}

    symbol_match = re.search(r'(?:銘柄|シンボル|Ticker)[:：\s]*([A-Za-z0-9]+)', text, re.IGNORECASE)
    if symbol_match:
        result['symbol'] = symbol_match.group(1).upper()

    qty_match = re.search(r'(?:株数|数量|Qty|数量)[:：\s]*([\d,\.]+)', text, re.IGNORECASE)
    if qty_match:
        result['quantity'] = clean_number(qty_match.group(1))

    price_match = re.search(r'(?:取得単価|平均取得単価|価格|price)[:：\s]*([¥$]?[\d,\.]+)', text, re.IGNORECASE)
    if price_match:
        result['purchase_price'] = clean_number(price_match.group(1))

    currency_match = re.search(r'(?:通貨)[:：\s]*([A-Z]{3})', text)
    if currency_match:
        result['currency'] = currency_match.group(1).upper()

    if 'currency' not in result:
        if result.get('symbol', '').isalpha() and result['symbol'] != 'JPY':
            result['currency'] = 'USD'
        else:
            result['currency'] = 'JPY'

    return result


class ConfirmOCRView(discord.ui.View):
    def __init__(self, author_id: int, order_info: dict, raw_text: str):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.order_info = order_info
        self.raw_text = raw_text
        self.completed = False
        self.message = None

    def disable_all_buttons(self):
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                'この確認は送信者のみ操作できます。',
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.completed:
            return

        self.completed = True
        self.disable_all_buttons()
        if self.message is None:
            return

        embed = self.message.embeds[0] if self.message.embeds else discord.Embed()
        embed.title = '⌛ OCR確認期限切れ'
        embed.description = '確認期限が切れたため、このOCR結果は登録されませんでした。'
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label='登録する', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.completed:
            await interaction.response.send_message(
                'この確認はすでに処理済みです。',
                ephemeral=True
            )
            return

        db.add_holding(
            self.author_id,
            self.order_info['symbol'],
            self.order_info['quantity'],
            self.order_info['purchase_price'],
            self.order_info.get('currency') or 'JPY'
        )
        self.completed = True
        self.disable_all_buttons()
        self.stop()

        embed = discord.Embed(
            title='✅ OCR結果を登録しました',
            color=discord.Color.green()
        )
        embed.add_field(name='銘柄', value=self.order_info['symbol'], inline=False)
        embed.add_field(name='株数', value=f"{self.order_info['quantity']:,}", inline=False)
        embed.add_field(name='取得単価', value=f"{self.order_info['purchase_price']:,}", inline=False)
        embed.add_field(name='通貨', value=self.order_info.get('currency', 'JPY'), inline=False)
        embed.add_field(name='OCR抜粋', value=self.raw_text.strip()[:200] + ('...' if len(self.raw_text.strip()) > 200 else ''), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='キャンセル', style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.completed:
            await interaction.response.send_message(
                'この確認はすでに処理済みです。',
                ephemeral=True
            )
            return

        self.completed = True
        self.disable_all_buttons()
        self.stop()

        embed = discord.Embed(
            title='❌ OCR結果の登録をキャンセルしました',
            color=discord.Color.red()
        )
        embed.add_field(name='OCR抽出候補', value=self.raw_text.strip()[:200] + ('...' if len(self.raw_text.strip()) > 200 else ''), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


async def process_screenshot_attachment(message: discord.Message, attachment: discord.Attachment):
    if pytesseract is None:
        await message.channel.send(
            'OCR機能を使用するには、`pytesseract` と Tesseract OCR をインストールしてください。'
        )
        return

    if not attachment.content_type or 'image' not in attachment.content_type:
        return

    data = await attachment.read()
    image = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(image, lang='jpn+eng')
    order_info = extract_order_info(text)

    if not order_info.get('symbol') or order_info.get('quantity') is None or order_info.get('purchase_price') is None:
        embed = discord.Embed(
            title='OCR読み取りに失敗しました',
            description='画像から必要な保有情報を抽出できませんでした。OCR結果を確認してください。',
            color=discord.Color.red()
        )
        if order_info.get('symbol'):
            embed.add_field(name='推定銘柄', value=order_info['symbol'], inline=False)
        if order_info.get('quantity') is not None:
            embed.add_field(name='推定株数', value=str(order_info['quantity']), inline=False)
        if order_info.get('purchase_price') is not None:
            embed.add_field(name='推定取得単価', value=str(order_info['purchase_price']), inline=False)
        if order_info.get('currency'):
            embed.add_field(name='推定通貨', value=order_info['currency'], inline=False)
        embed.add_field(name='OCR生テキスト', value=text.strip()[:300] + ('...' if len(text.strip()) > 300 else ''), inline=False)
        await message.channel.send(embed=embed)
        return

    embed = discord.Embed(
        title='OCR読み取り結果を確認してください',
        description='以下の内容で保有銘柄を登録します。誤りがなければ「登録する」を押してください。',
        color=discord.Color.blue()
    )
    embed.add_field(name='銘柄', value=order_info['symbol'], inline=False)
    embed.add_field(name='株数', value=f"{order_info['quantity']:,}", inline=False)
    embed.add_field(name='取得単価', value=f"{order_info['purchase_price']:,}", inline=False)
    embed.add_field(name='通貨', value=order_info.get('currency', 'JPY'), inline=False)
    embed.add_field(name='OCR生テキスト', value=text.strip()[:300] + ('...' if len(text.strip()) > 300 else ''), inline=False)

    view = ConfirmOCRView(message.author.id, order_info, text)
    sent_message = await message.channel.send(embed=embed, view=view)
    view.message = sent_message


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                await process_screenshot_attachment(message, attachment)
                return
    await bot.process_app_commands(message)


@tree.command(
    name="資産",
    description="現在の総資産を記録・確認します"
)
async def set_asset(
    interaction: discord.Interaction,
    金額: int
):
    """資産コマンド: /資産 金額"""
    user_id = interaction.user.id
    
    # データベースに保存
    db.set_asset(user_id, 金額)
    total_deposits = db.get_deposits(user_id)
    
    # 基準資産からの増減を計算
    increase = 金額 - BASE_ASSET
    increase_rate = (increase / BASE_ASSET) * 100
    return_excluding_deposits = increase - total_deposits
    return_excluding_deposits_rate = (return_excluding_deposits / BASE_ASSET) * 100
    
    # 年率目標に対する進捗を計算
    target_amount = BASE_ASSET * (1 + ANNUAL_TARGET)
    target_increase = target_amount - BASE_ASSET
    progress = (increase / target_increase) * 100 if target_increase > 0 else 0
    
    embed = discord.Embed(
        title="📊 資産情報",
        color=discord.Color.blue()
    )
    embed.add_field(name="現在の資産", value=f"¥{金額:,}", inline=False)
    embed.add_field(name="基準資産", value=f"¥{BASE_ASSET:,}", inline=False)
    embed.add_field(name="入金累計", value=f"¥{total_deposits:,}", inline=False)
    embed.add_field(name="総リターン", value=f"¥{increase:,} ({increase_rate:+.2f}%)", inline=False)
    embed.add_field(name="入金除外リターン", value=f"¥{return_excluding_deposits:,} ({return_excluding_deposits_rate:+.2f}%)", inline=False)
    embed.add_field(name="年率20%目標額", value=f"¥{target_amount:,}", inline=False)
    embed.add_field(name="目標進捗", value=f"{progress:.1f}%", inline=False)
    embed.set_footer(text=f"基準日: {BASE_DATE.strftime('%Y年%m月%d日')}")
    
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="入金",
    description="入金を記録します"
)
async def add_deposit(
    interaction: discord.Interaction,
    金額: int
):
    """入金コマンド: /入金 金額"""
    user_id = interaction.user.id
    
    # データベースに記録
    db.add_deposit(user_id, 金額)
    
    # 累計入金を取得
    total_deposits = db.get_deposits(user_id)
    
    embed = discord.Embed(
        title="💰 入金を記録しました",
        color=discord.Color.green()
    )
    embed.add_field(name="入金額", value=f"¥{金額:,}", inline=False)
    embed.add_field(name="累計入金", value=f"¥{total_deposits:,}", inline=False)
    embed.set_footer(text=f"記録日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="保有",
    description="保有銘柄を登録します"
)
async def add_holding(
    interaction: discord.Interaction,
    銘柄: str,
    株数: float,
    取得単価: float,
    通貨: str = 'JPY'
):
    """保有コマンド: /保有 銘柄 株数 取得単価 通貨"""
    user_id = interaction.user.id
    db.add_holding(user_id, 銘柄, 株数, 取得単価, 通貨)

    embed = discord.Embed(
        title="📈 保有銘柄を登録しました",
        color=discord.Color.brand_green()
    )
    embed.add_field(name="銘柄", value=銘柄.upper(), inline=False)
    embed.add_field(name="株数", value=f"{株数:,}", inline=False)
    embed.add_field(name="取得単価", value=f"{取得単価:,} {通貨.upper()}", inline=False)
    embed.add_field(name="通貨", value=通貨.upper(), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="仮説登録",
    description="銘柄の投資仮説を登録・更新します"
)
async def register_hypothesis(
    interaction: discord.Interaction,
    銘柄: str,
    保有理由: str,
    期待数字: str,
    買い増し条件: str,
    損切り条件: str
):
    """仮説登録コマンド: /仮説登録 銘柄 保有理由 期待数字 買い増し条件 損切り条件"""
    user_id = interaction.user.id
    db.add_or_update_hypothesis(user_id, 銘柄, 保有理由, 期待数字, 買い増し条件, 損切り条件)

    embed = discord.Embed(
        title="🧠 投資仮説を登録しました",
        color=discord.Color.blurple()
    )
    embed.add_field(name="銘柄", value=銘柄.upper(), inline=False)
    embed.add_field(name="保有理由", value=保有理由, inline=False)
    embed.add_field(name="期待数字", value=期待数字, inline=False)
    embed.add_field(name="買い増し条件", value=買い増し条件, inline=False)
    embed.add_field(name="損切り条件", value=損切り条件, inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="仮説",
    description="登録済みの銘柄仮説を確認します"
)
async def show_hypothesis(
    interaction: discord.Interaction,
    銘柄: str
):
    """仮説コマンド: /仮説 銘柄"""
    user_id = interaction.user.id
    hypothesis = db.get_hypothesis(user_id, 銘柄)

    if not hypothesis:
        await interaction.response.send_message(
            f"❌ {銘柄.upper()} の投資仮説が登録されていません。`/仮説登録` で登録してください。"
        )
        return

    embed = discord.Embed(
        title=f"🧠 {hypothesis['symbol']} の投資仮説",
        color=discord.Color.blurple()
    )
    embed.add_field(name="保有理由", value=hypothesis['reason'], inline=False)
    embed.add_field(name="期待数字", value=hypothesis['expected_return'], inline=False)
    embed.add_field(name="買い増し条件", value=hypothesis['add_condition'], inline=False)
    embed.add_field(name="損切り条件", value=hypothesis['cut_condition'], inline=False)
    embed.add_field(name="最終更新", value=hypothesis['updated_at'] or hypothesis['created_at'], inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="判定",
    description="銘柄判定の情報を表示します"
)
async def evaluate_holding(
    interaction: discord.Interaction,
    銘柄: str
):
    """判定コマンド: /判定 銘柄"""
    user_id = interaction.user.id
    asset_info = db.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    holding = db.get_holding_by_symbol(user_id, 銘柄)
    hypothesis = db.get_hypothesis(user_id, 銘柄)

    if not holding:
        await interaction.response.send_message(
            f"❌ {銘柄.upper()} の保有情報が登録されていません。`/保有` で登録してください。"
        )
        return

    total_cost = holding['quantity'] * holding['purchase_price']
    ratio = (total_cost / current_asset * 100) if current_asset else 0
    status = "✅ 問題なし"
    if ratio >= 40:
        status = "⚠️ 40% を超えています。分散を検討しましょう。"

    embed = discord.Embed(
        title=f"🧾 {holding['symbol']} の判定",
        color=discord.Color.gold()
    )
    embed.add_field(name="保有数量", value=f"{holding['quantity']:,}", inline=False)
    embed.add_field(name="取得単価", value=f"{holding['purchase_price']:,} {holding['currency']}", inline=False)
    embed.add_field(name="保有コスト", value=f"¥{int(total_cost):,}", inline=False)
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


@tree.command(
    name="比率",
    description="保有銘柄の資産比率を表示します"
)
async def show_ratios(interaction: discord.Interaction):
    """比率コマンド: /比率"""
    user_id = interaction.user.id
    asset_info = db.get_asset(user_id)
    current_asset = asset_info['total_asset'] if asset_info else 0
    holdings = db.get_holdings(user_id)

    if not holdings or current_asset == 0:
        await interaction.response.send_message(
            "❌ 保有銘柄または資産情報が登録されていません。`/保有` と `/資産` を使ってください。"
        )
        return

    embed = discord.Embed(
        title="📊 保有銘柄の比率",
        color=discord.Color.blue()
    )
    warnings = []
    for holding in holdings:
        cost = holding['quantity'] * holding['purchase_price']
        ratio = (cost / current_asset) * 100 if current_asset else 0
        embed.add_field(
            name=f"{holding['symbol']} ({holding['currency']})",
            value=(
                f"{holding['quantity']:,} 株 @ {holding['purchase_price']:,}\n"
                f"コスト: ¥{int(cost):,}\n"
                f"比率: {ratio:.2f}%"
            ),
            inline=False
        )
        if ratio >= 40:
            warnings.append(f"{holding['symbol']} が {ratio:.2f}% で40%超です。")

    if warnings:
        embed.add_field(name="⚠️ 警告", value="\n".join(warnings), inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="レビュー",
    description="3か月ごとのレビューを表示します"
)
async def show_review(interaction: discord.Interaction):
    """レビューコマンド: /レビュー"""
    user_id = interaction.user.id
    
    # 現在の資産を取得
    asset_info = db.get_asset(user_id)
    
    if not asset_info:
        await interaction.response.send_message(
            "❌ 資産情報が登録されていません。\n`/資産 金額` で資産を登録してください。"
        )
        return
    
    current_asset = asset_info['total_asset']
    total_deposits = db.get_deposits(user_id)
    
    # 基準日から経過日数を計算
    today = datetime.now().date()
    base_date = BASE_DATE.date()
    days_elapsed = (today - base_date).days
    
    # 3か月単位のレビュー
    quarters_passed = days_elapsed // 90
    
    # リターン計算
    total_return = current_asset - BASE_ASSET
    return_excluding_deposits = current_asset - BASE_ASSET - total_deposits
    
    # 入金を除外したリターン率
    if return_excluding_deposits != 0:
        return_excluding_deposits_rate = (return_excluding_deposits / BASE_ASSET) * 100
    else:
        return_excluding_deposits_rate = 0
    
    embed = discord.Embed(
        title="📋 投資レビュー",
        color=discord.Color.purple()
    )
    embed.add_field(name="レビュー期間", value=f"基準日から {quarters_passed}四半期 ({days_elapsed}日)", inline=False)
    embed.add_field(name="基準資産", value=f"¥{BASE_ASSET:,}", inline=False)
    embed.add_field(name="現在の資産", value=f"¥{current_asset:,}", inline=False)
    embed.add_field(name="入金総額", value=f"¥{total_deposits:,}", inline=False)
    embed.add_field(name="総リターン", value=f"¥{total_return:,}", inline=False)
    embed.add_field(
        name="入金除外リターン",
        value=f"¥{return_excluding_deposits:,} ({return_excluding_deposits_rate:+.2f}%)",
        inline=False
    )
    
    # 推移
    if quarters_passed > 0:
        avg_quarterly_return = total_return / quarters_passed
        embed.add_field(
            name="平均四半期リターン",
            value=f"¥{int(avg_quarterly_return):,}",
            inline=False
        )
    
    embed.set_footer(text=f"レビュー日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    
    await interaction.response.send_message(embed=embed)


@tree.command(
    name="ヘルプ",
    description="使用可能なコマンド一覧"
)
async def help_command(interaction: discord.Interaction):
    """ヘルプコマンド"""
    embed = discord.Embed(
        title="💡 投資管理Bot - ヘルプ",
        color=discord.Color.lighter_gray()
    )
    
    commands_info = [
        ("/資産 金額", "現在の総資産を記録・確認します"),
        ("/入金 金額", "入金を記録します"),
        ("/保有 銘柄 株数 取得単価 通貨", "保有銘柄を登録します"),
        ("/仮説 銘柄", "保存済みの投資仮説を確認します"),
        ("/仮説登録 銘柄 保有理由 期待数字 買い増し条件 損切り条件", "投資仮説を登録・更新します"),
        ("/判定 銘柄", "銘柄の判定と資産比率を表示します"),
        ("/比率", "保有銘柄の資産比率を表示します"),
        ("/目標", "年率20%達成に必要な資産額を表示します"),
        ("/レビュー", "投資状況のレビューを表示します"),
        ("/ヘルプ", "このメッセージを表示します"),
    ]
    
    for cmd, desc in commands_info:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.set_footer(text="基準日: 2026年06月09日 | 基準資産: ¥7,096,249")
    
    await interaction.response.send_message(embed=embed)


def main():
    """メイン関数"""
    token = os.getenv('DISCORD_TOKEN') or DISCORD_TOKEN
    if token == 'your_token_here':
        print("❌ エラー: DISCORD_TOKENが設定されていません")
        print("📝 .env ファイルを作成し、DISCORD_TOKEN=<your_token> を追加してください")
        return
    
    print("🤖 投資管理Botを起動しています...")
    bot.run(token)


if __name__ == '__main__':
    main()
