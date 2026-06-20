"""SQLiteデータベース管理"""
import sqlite3
from datetime import datetime
from config import DB_PATH, BASE_ASSET, BASE_DATE


class InvestmentDatabase:
    """投資管理用データベース"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """データベーステーブルの初期化"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # ユーザー資産情報テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                total_asset INTEGER NOT NULL,
                deposits INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 入金履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                deposit_date DATE NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 保有銘柄テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                purchase_price REAL NOT NULL,
                currency TEXT DEFAULT 'JPY',
                purchase_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 投資仮説テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                reason TEXT,
                expected_return TEXT,
                add_condition TEXT,
                cut_condition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 取引履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                ticker TEXT,
                quantity REAL,
                price REAL,
                amount REAL,
                currency TEXT,
                memo TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 試算・監視用ポジションテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                currency TEXT DEFAULT 'USD',
                memo TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 資産内訳テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_breakdowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'JPY',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
        ''')

        # 総資産履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                asset_value REAL NOT NULL,
                currency TEXT DEFAULT 'JPY',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 投資判断シナリオテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS investment_scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                market_type TEXT,
                position_type TEXT,
                investment_amount REAL,
                portfolio_weight REAL,
                buy_reason TEXT,
                business_thesis TEXT,
                market_mispricing TEXT,
                growth_thesis TEXT,
                capital_flow_reason TEXT,
                next_earnings_watch TEXT,
                hold_condition TEXT,
                reduce_condition TEXT,
                exit_condition TEXT,
                max_loss_amount REAL,
                earnings_date TEXT,
                review_date TEXT,
                memo TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 将来の履歴表示・差分比較に備えて更新前スナップショットを保存
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scenario_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                market_type TEXT,
                position_type TEXT,
                investment_amount REAL,
                portfolio_weight REAL,
                buy_reason TEXT,
                business_thesis TEXT,
                market_mispricing TEXT,
                growth_thesis TEXT,
                capital_flow_reason TEXT,
                next_earnings_watch TEXT,
                hold_condition TEXT,
                reduce_condition TEXT,
                exit_condition TEXT,
                max_loss_amount REAL,
                earnings_date TEXT,
                review_date TEXT,
                memo TEXT,
                active INTEGER,
                created_at TEXT,
                updated_at TEXT,
                archived_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 売却判断記録テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sell_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                sell_date TEXT,
                sell_quantity REAL,
                sell_amount REAL,
                reason_category TEXT NOT NULL,
                reason_detail TEXT,
                scenario_status_at_sell TEXT,
                emotion_at_sell TEXT,
                reflection TEXT,
                memo TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self._ensure_column(cursor, 'holdings', 'current_price', 'REAL')
        self._ensure_position_columns(cursor, 'holdings')
        self._ensure_position_columns(cursor, 'simulations')
        self._ensure_column(cursor, 'user_assets', 'initial_asset', 'INTEGER')
        self._ensure_column(cursor, 'user_assets', 'base_date', 'TEXT')
        self._ensure_column(cursor, 'investment_scenarios', 'user_id', 'INTEGER')
        self._ensure_column(cursor, 'sell_records', 'user_id', 'INTEGER')
        
        conn.commit()
        conn.close()

    def _ensure_column(self, cursor, table_name, column_name, column_type):
        cursor.execute(f'PRAGMA table_info({table_name})')
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}')

    def _ensure_position_columns(self, cursor, table_name):
        columns = {
            'current_currency': 'TEXT',
            'current_value': 'REAL',
            'current_value_jpy': 'REAL',
            'unrealized_pnl': 'REAL',
            'unrealized_pnl_jpy': 'REAL',
            'unrealized_pnl_rate': 'REAL',
            'previous_close': 'REAL',
            'day_change': 'REAL',
            'day_change_rate': 'REAL',
            'price_updated_at': 'TEXT',
        }
        for column_name, column_type in columns.items():
            self._ensure_column(cursor, table_name, column_name, column_type)

    def _ensure_user_asset(self, cursor, user_id):
        cursor.execute('''
            SELECT id, total_asset, initial_asset, base_date FROM user_assets WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        default_base_date = BASE_DATE.date().isoformat()
        if result:
            total_asset = result[1] if result[1] is not None else 0
            initial_asset = result[2]
            base_date = result[3]
            if initial_asset is None and total_asset < BASE_ASSET:
                cursor.execute('''
                    UPDATE user_assets
                    SET total_asset = total_asset + ?
                    WHERE user_id = ?
                ''', (BASE_ASSET, user_id))
            if initial_asset is None or base_date is None:
                cursor.execute('''
                    UPDATE user_assets
                    SET initial_asset = COALESCE(initial_asset, ?),
                        base_date = COALESCE(base_date, ?)
                    WHERE user_id = ?
                ''', (BASE_ASSET, default_base_date, user_id))
            return

        cursor.execute('''
            INSERT INTO user_assets (user_id, total_asset, deposits, initial_asset, base_date)
            VALUES (?, ?, 0, ?, ?)
        ''', (user_id, BASE_ASSET, BASE_ASSET, default_base_date))
    
    def set_asset(self, user_id, total_asset):
        """資産を設定・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self._ensure_user_asset(cursor, user_id)
        cursor.execute('SELECT total_asset FROM user_assets WHERE user_id = ?', (user_id,))
        current = cursor.fetchone()
        previous_asset = current[0] if current else None
        cursor.execute('''
            SELECT asset_value FROM asset_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
        ''', (user_id,))
        latest_history = cursor.fetchone()
        latest_history_value = latest_history[0] if latest_history else None
        if previous_asset is not None and latest_history_value != previous_asset:
            self._record_asset_history(cursor, user_id, previous_asset, 'JPY')
        cursor.execute('''
            UPDATE user_assets
            SET total_asset = ?, last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (total_asset, user_id))
        self._record_asset_history(cursor, user_id, total_asset, 'JPY')
        
        conn.commit()
        conn.close()

    def _record_asset_history(self, cursor, user_id, asset_value, currency='JPY'):
        cursor.execute('''
            INSERT INTO asset_history (user_id, asset_value, currency)
            VALUES (?, ?, ?)
        ''', (user_id, asset_value, currency.upper()))

    def get_asset_previous_change(self, user_id):
        """直近の総資産履歴から前回比を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asset_value, currency, created_at
            FROM asset_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 2
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {
                'current': None,
                'previous': None,
                'change': None,
                'change_rate': None,
                'currency': 'JPY',
                'updated_at': None,
            }
        current = rows[0][0]
        previous = rows[1][0] if len(rows) >= 2 else None
        change = current - previous if previous not in (None, 0) else None
        change_rate = change / previous if change is not None and previous else None
        return {
            'current': current,
            'previous': previous,
            'change': change,
            'change_rate': change_rate,
            'currency': rows[0][1] or 'JPY',
            'updated_at': rows[0][2],
        }

    def _scenario_from_row(self, row):
        if not row:
            return None
        keys = [
            'id', 'user_id', 'ticker', 'company_name', 'market_type', 'position_type',
            'investment_amount', 'portfolio_weight', 'buy_reason', 'business_thesis',
            'market_mispricing', 'growth_thesis', 'capital_flow_reason',
            'next_earnings_watch', 'hold_condition', 'reduce_condition',
            'exit_condition', 'max_loss_amount', 'earnings_date', 'review_date',
            'memo', 'active', 'created_at', 'updated_at'
        ]
        return dict(zip(keys, row))

    def _insert_scenario_history(self, cursor, row):
        scenario = self._scenario_from_row(row)
        if not scenario:
            return
        cursor.execute('''
            INSERT INTO scenario_history (
                scenario_id, user_id, ticker, company_name, market_type, position_type,
                investment_amount, portfolio_weight, buy_reason, business_thesis,
                market_mispricing, growth_thesis, capital_flow_reason,
                next_earnings_watch, hold_condition, reduce_condition,
                exit_condition, max_loss_amount, earnings_date, review_date,
                memo, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            scenario['id'], scenario['user_id'], scenario['ticker'], scenario['company_name'],
            scenario['market_type'], scenario['position_type'], scenario['investment_amount'],
            scenario['portfolio_weight'], scenario['buy_reason'], scenario['business_thesis'],
            scenario['market_mispricing'], scenario['growth_thesis'], scenario['capital_flow_reason'],
            scenario['next_earnings_watch'], scenario['hold_condition'], scenario['reduce_condition'],
            scenario['exit_condition'], scenario['max_loss_amount'], scenario['earnings_date'],
            scenario['review_date'], scenario['memo'], scenario['active'], scenario['created_at'],
            scenario['updated_at'],
        ))

    def add_or_update_scenario(self, user_id, data, save_history=True):
        """投資シナリオを登録・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        ticker = data['ticker'].upper()
        cursor.execute('''
            SELECT
                id, user_id, ticker, company_name, market_type, position_type,
                investment_amount, portfolio_weight, buy_reason, business_thesis,
                market_mispricing, growth_thesis, capital_flow_reason,
                next_earnings_watch, hold_condition, reduce_condition,
                exit_condition, max_loss_amount, earnings_date, review_date,
                memo, active, created_at, updated_at
            FROM investment_scenarios
            WHERE user_id = ? AND ticker = ?
            ORDER BY active DESC, updated_at DESC, id DESC
            LIMIT 1
        ''', (user_id, ticker))
        existing = cursor.fetchone()

        values = (
            data.get('company_name'), data.get('market_type'), data.get('position_type'),
            data.get('investment_amount'), data.get('portfolio_weight'), data.get('buy_reason'),
            data.get('business_thesis'), data.get('market_mispricing'), data.get('growth_thesis'),
            data.get('capital_flow_reason'), data.get('next_earnings_watch'),
            data.get('hold_condition'), data.get('reduce_condition'), data.get('exit_condition'),
            data.get('max_loss_amount'), data.get('earnings_date'), data.get('review_date'),
            data.get('memo'), 1 if data.get('active', True) else 0,
        )

        if existing:
            if save_history:
                self._insert_scenario_history(cursor, existing)
            cursor.execute('''
                UPDATE investment_scenarios
                SET company_name = ?, market_type = ?, position_type = ?,
                    investment_amount = ?, portfolio_weight = ?, buy_reason = ?,
                    business_thesis = ?, market_mispricing = ?, growth_thesis = ?,
                    capital_flow_reason = ?, next_earnings_watch = ?,
                    hold_condition = ?, reduce_condition = ?, exit_condition = ?,
                    max_loss_amount = ?, earnings_date = ?, review_date = ?,
                    memo = ?, active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', values + (existing[0],))
            scenario_id = existing[0]
        else:
            cursor.execute('''
                INSERT INTO investment_scenarios (
                    user_id, ticker, company_name, market_type, position_type,
                    investment_amount, portfolio_weight, buy_reason, business_thesis,
                    market_mispricing, growth_thesis, capital_flow_reason,
                    next_earnings_watch, hold_condition, reduce_condition,
                    exit_condition, max_loss_amount, earnings_date, review_date,
                    memo, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, ticker) + values)
            scenario_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return self.get_scenario_by_ticker(user_id, ticker, active_only=False) or {'id': scenario_id}

    def get_scenario_by_ticker(self, user_id, ticker, active_only=True):
        """銘柄コードから投資シナリオを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query = '''
            SELECT
                id, user_id, ticker, company_name, market_type, position_type,
                investment_amount, portfolio_weight, buy_reason, business_thesis,
                market_mispricing, growth_thesis, capital_flow_reason,
                next_earnings_watch, hold_condition, reduce_condition,
                exit_condition, max_loss_amount, earnings_date, review_date,
                memo, active, created_at, updated_at
            FROM investment_scenarios
            WHERE user_id = ? AND ticker = ?
        '''
        params = [user_id, ticker.upper()]
        if active_only:
            query += ' AND active = 1'
        query += ' ORDER BY active DESC, updated_at DESC, id DESC LIMIT 1'
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        return self._scenario_from_row(row)

    def get_active_scenarios(self, user_id):
        """有効な投資シナリオ一覧を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                id, user_id, ticker, company_name, market_type, position_type,
                investment_amount, portfolio_weight, buy_reason, business_thesis,
                market_mispricing, growth_thesis, capital_flow_reason,
                next_earnings_watch, hold_condition, reduce_condition,
                exit_condition, max_loss_amount, earnings_date, review_date,
                memo, active, created_at, updated_at
            FROM investment_scenarios
            WHERE user_id = ? AND active = 1
            ORDER BY
                CASE position_type
                    WHEN '超主力' THEN 1
                    WHEN '主力' THEN 2
                    WHEN '準主力' THEN 3
                    WHEN '観察枠' THEN 4
                    ELSE 99
                END,
                ticker
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._scenario_from_row(row) for row in rows]

    def add_sell_record(self, user_id, data):
        """売却判断を記録"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sell_records (
                user_id, ticker, company_name, sell_date, sell_quantity, sell_amount,
                reason_category, reason_detail, scenario_status_at_sell,
                emotion_at_sell, reflection, memo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data['ticker'].upper(),
            data.get('company_name'),
            data.get('sell_date'),
            data.get('sell_quantity'),
            data.get('sell_amount'),
            data['reason_category'],
            data.get('reason_detail'),
            data.get('scenario_status_at_sell'),
            data.get('emotion_at_sell'),
            data.get('reflection'),
            data.get('memo'),
        ))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return record_id

    def get_latest_user_id(self):
        """日次レポート用に直近更新ユーザーを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id
            FROM user_assets
            ORDER BY last_updated DESC, id DESC
            LIMIT 1
        ''')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def set_base_asset(self, user_id, initial_asset, base_date):
        """基準資産・基準日・現在資産を設定"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self._ensure_user_asset(cursor, user_id)
        base_date_text = base_date.isoformat() if hasattr(base_date, 'isoformat') else str(base_date)
        cursor.execute('''
            UPDATE user_assets
            SET initial_asset = ?,
                total_asset = ?,
                base_date = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (initial_asset, initial_asset, base_date_text, user_id))
        conn.commit()
        conn.close()

    def set_asset_breakdown(self, user_id, name, amount, currency='JPY'):
        """資産内訳を登録・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        name = str(name).strip()
        currency = currency.upper()
        cursor.execute('''
            INSERT INTO asset_breakdowns (user_id, name, amount, currency)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                amount = ?,
                currency = ?,
                updated_at = CURRENT_TIMESTAMP
        ''', (user_id, name, amount, currency, amount, currency))
        conn.commit()
        conn.close()

    def get_asset_breakdowns(self, user_id):
        """資産内訳を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, amount, currency, updated_at
            FROM asset_breakdowns
            WHERE user_id = ?
            ORDER BY CASE name
                WHEN '国内株式' THEN 1
                WHEN '米国株式' THEN 2
                WHEN '投資信託' THEN 3
                WHEN '投信' THEN 3
                WHEN '預り金' THEN 4
                WHEN 'USドル' THEN 5
                ELSE 99
            END, name
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'name': row[0],
                'amount': row[1],
                'currency': row[2],
                'updated_at': row[3],
            }
            for row in rows
        ]
    
    def get_asset(self, user_id):
        """資産情報を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self._ensure_user_asset(cursor, user_id)
        conn.commit()
        
        cursor.execute('''
            SELECT total_asset, deposits, last_updated, initial_asset, base_date
            FROM user_assets WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'total_asset': result[0],
                'deposits': result[1],
                'last_updated': result[2],
                'initial_asset': result[3] if result[3] is not None else BASE_ASSET,
                'base_date': result[4] if result[4] else BASE_DATE.date().isoformat(),
            }
        return None
    
    def add_transaction(self, user_id, transaction_type, ticker=None, quantity=None, price=None, amount=None, currency='JPY', memo=''):
        """取引を記録"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        ticker = ticker.upper() if ticker else None
        currency = currency.upper() if currency else 'JPY'

        cursor.execute('''
            INSERT INTO transactions (user_id, date, type, ticker, quantity, price, amount, currency, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, today, transaction_type, ticker, quantity, price, amount, currency, memo))

        conn.commit()
        conn.close()

    def add_deposit(self, user_id, amount, currency='JPY', memo=''):
        """入金を記録"""
        self.add_transaction(user_id, 'DEPOSIT', amount=amount, currency=currency, memo=memo)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().date()
        self._ensure_user_asset(cursor, user_id)

        cursor.execute('''
            INSERT INTO deposits (user_id, amount, deposit_date, notes)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, today, memo))

        cursor.execute('''
            UPDATE user_assets
            SET deposits = COALESCE(deposits, 0) + ?,
                total_asset = total_asset + ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (amount, amount, user_id))

        conn.commit()
        conn.close()

    def add_withdraw(self, user_id, amount, currency='JPY', memo=''):
        """出金を記録"""
        self.add_transaction(user_id, 'WITHDRAW', amount=amount, currency=currency, memo=memo)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self._ensure_user_asset(cursor, user_id)
        cursor.execute('''
            UPDATE user_assets
            SET total_asset = total_asset - ?, last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (amount, user_id))
        conn.commit()
        conn.close()

    def _replace_holding(self, cursor, user_id, symbol, quantity, purchase_price, currency, current_price=None):
        """銘柄の現在保有を1行に集約して保存"""
        today = datetime.now().date()
        symbol = symbol.upper()
        currency = currency.upper()
        cursor.execute('DELETE FROM holdings WHERE user_id = ? AND symbol = ?', (user_id, symbol))
        if quantity > 0:
            cursor.execute('''
                INSERT INTO holdings (user_id, symbol, quantity, purchase_price, currency, purchase_date, current_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, symbol, quantity, purchase_price, currency, today, current_price))

    def add_buy(self, user_id, symbol, quantity, price, currency='USD', memo=''):
        """買い取引を記録し、平均取得単価を更新"""
        symbol = symbol.upper()
        currency = currency.upper()
        amount = quantity * price
        self.add_transaction(user_id, 'BUY', symbol, quantity, price, amount, currency, memo)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        holding = self.get_holding_by_symbol(user_id, symbol)
        if holding:
            old_quantity = holding['quantity']
            old_price = holding['purchase_price']
            new_quantity = old_quantity + quantity
            new_price = ((old_quantity * old_price) + (quantity * price)) / new_quantity
        else:
            new_quantity = quantity
            new_price = price
        current_price = holding.get('current_price') if holding else None
        self._replace_holding(cursor, user_id, symbol, new_quantity, new_price, currency, current_price)
        conn.commit()
        conn.close()
        return {'symbol': symbol, 'quantity': new_quantity, 'purchase_price': new_price, 'currency': currency}

    def add_sell(self, user_id, symbol, quantity, price, currency='USD', memo=''):
        """売り取引を記録し、保有数量を減らす"""
        symbol = symbol.upper()
        currency = currency.upper()
        holding = self.get_holding_by_symbol(user_id, symbol)
        if not holding:
            raise ValueError(f'{symbol} の保有情報がありません。')
        if quantity > holding['quantity']:
            raise ValueError(f'売却株数が保有株数を超えています。保有: {holding["quantity"]}')

        amount = quantity * price
        realized_profit = (price - holding['purchase_price']) * quantity
        self.add_transaction(user_id, 'SELL', symbol, quantity, price, amount, currency, memo)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        new_quantity = holding['quantity'] - quantity
        self._replace_holding(cursor, user_id, symbol, new_quantity, holding['purchase_price'], holding['currency'], holding.get('current_price'))
        conn.commit()
        conn.close()
        return {
            'symbol': symbol,
            'quantity': new_quantity,
            'purchase_price': holding['purchase_price'],
            'currency': holding['currency'],
            'realized_profit': realized_profit
        }
    
    def get_deposits(self, user_id):
        """入金合計を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*), SUM(amount) FROM transactions WHERE user_id = ? AND type = 'DEPOSIT'
        ''', (user_id,))
        
        result = cursor.fetchone()
        if result and result[0] > 0:
            conn.close()
            return result[1] if result[1] else 0

        cursor.execute('''
            SELECT SUM(amount) FROM deposits WHERE user_id = ?
        ''', (user_id,))

        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0

    def get_transactions(self, user_id, limit=10):
        """直近の取引履歴を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, type, ticker, quantity, price, amount, currency, memo, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'date': row[0],
                'type': row[1],
                'ticker': row[2],
                'quantity': row[3],
                'price': row[4],
                'amount': row[5],
                'currency': row[6],
                'memo': row[7],
                'created_at': row[8],
            }
            for row in rows
        ]

    def get_net_deposit(self, user_id):
        """純入金額を取得"""
        summary = self.get_cash_flow_summary(user_id)
        return summary['deposit_total'] - summary['withdraw_total']

    def get_cash_flow_summary(self, user_id):
        """入出金サマリーを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM transactions WHERE user_id = ?
        ''', (user_id,))
        tx_count = cursor.fetchone()[0]

        cursor.execute('''
            SELECT
                SUM(CASE WHEN type = 'DEPOSIT' THEN amount ELSE 0 END),
                SUM(CASE WHEN type = 'WITHDRAW' THEN amount ELSE 0 END)
            FROM transactions
            WHERE user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        deposit_total = row[0] if row and row[0] else 0
        withdraw_total = row[1] if row and row[1] else 0
        if tx_count == 0:
            deposit_total = self.get_deposits(user_id)
        return {
            'deposit_total': deposit_total,
            'withdraw_total': withdraw_total,
            'net_deposit': deposit_total - withdraw_total,
        }

    def get_trade_summary(self, user_id):
        """売買サマリーを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                SUM(CASE WHEN type = 'BUY' THEN amount ELSE 0 END),
                SUM(CASE WHEN type = 'SELL' THEN amount ELSE 0 END)
            FROM transactions
            WHERE user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        buy_total = row[0] if row and row[0] else 0
        sell_total = row[1] if row and row[1] else 0
        return {
            'buy_total': buy_total,
            'sell_total': sell_total,
        }

    def add_holding(self, user_id, symbol, quantity, purchase_price, currency='JPY', memo=''):
        """保有銘柄を初期登録・修正し、BUYとして履歴に残す"""
        history_memo = '初期登録/修正'
        if memo:
            history_memo = f'{history_memo} {memo}'
        self.add_transaction(
            user_id,
            'BUY',
            ticker=symbol,
            quantity=quantity,
            price=purchase_price,
            amount=quantity * purchase_price,
            currency=currency,
            memo=history_memo
        )
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self._replace_holding(cursor, user_id, symbol, quantity, purchase_price, currency)
        conn.commit()
        conn.close()

    def get_holdings(self, user_id):
        """ユーザーの保有銘柄を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT
                symbol, quantity, purchase_price, currency, purchase_date, current_price,
                current_currency, current_value, current_value_jpy,
                unrealized_pnl, unrealized_pnl_jpy, unrealized_pnl_rate,
                previous_close, day_change, day_change_rate,
                price_updated_at
            FROM holdings WHERE user_id = ?
            ORDER BY symbol
        ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'symbol': row[0],
                'quantity': row[1],
                'purchase_price': row[2],
                'currency': row[3],
                'purchase_date': row[4],
                'current_price': row[5],
                'current_currency': row[6],
                'current_value': row[7],
                'current_value_jpy': row[8],
                'unrealized_pnl': row[9],
                'unrealized_pnl_jpy': row[10],
                'unrealized_pnl_rate': row[11],
                'previous_close': row[12],
                'day_change': row[13],
                'day_change_rate': row[14],
                'price_updated_at': row[15],
            }
            for row in results
        ]

    def get_holding_by_symbol(self, user_id, symbol):
        """特定銘柄の保有情報を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        symbol = symbol.upper()
        
        cursor.execute('''
            SELECT
                symbol, quantity, purchase_price, currency, purchase_date, current_price,
                current_currency, current_value, current_value_jpy,
                unrealized_pnl, unrealized_pnl_jpy, unrealized_pnl_rate,
                previous_close, day_change, day_change_rate,
                price_updated_at
            FROM holdings WHERE user_id = ? AND symbol = ?
            ORDER BY purchase_date DESC
            LIMIT 1
        ''', (user_id, symbol))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'symbol': result[0],
                'quantity': result[1],
                'purchase_price': result[2],
                'currency': result[3],
                'purchase_date': result[4],
                'current_price': result[5],
                'current_currency': result[6],
                'current_value': result[7],
                'current_value_jpy': result[8],
                'unrealized_pnl': result[9],
                'unrealized_pnl_jpy': result[10],
                'unrealized_pnl_rate': result[11],
                'previous_close': result[12],
                'day_change': result[13],
                'day_change_rate': result[14],
                'price_updated_at': result[15],
            }
        return None

    def calculate_position_values(self, quantity, entry_price, current_price, currency='USD', usdjpy=None):
        """評価額・損益・円換算を計算"""
        currency = (currency or 'USD').upper()
        quantity = quantity or 0
        entry_price = entry_price or 0
        current_price = current_price if current_price is not None else entry_price
        current_value = quantity * current_price
        cost = quantity * entry_price
        unrealized_pnl = current_value - cost
        unrealized_pnl_rate = (unrealized_pnl / cost * 100) if cost else 0

        fx_rate = 1 if currency == 'JPY' else usdjpy
        if fx_rate:
            current_value_jpy = current_value * fx_rate
            unrealized_pnl_jpy = unrealized_pnl * fx_rate
        else:
            current_value_jpy = None
            unrealized_pnl_jpy = None

        return {
            'current_value': current_value,
            'current_value_jpy': current_value_jpy,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_jpy': unrealized_pnl_jpy,
            'unrealized_pnl_rate': unrealized_pnl_rate,
        }

    def update_holding_valuation(
        self,
        user_id,
        symbol,
        current_price,
        current_currency='USD',
        usdjpy=None,
        previous_close=None,
        day_change=None,
        day_change_rate=None,
    ):
        """保有銘柄の現在価格・評価額・損益を更新"""
        holding = self.get_holding_by_symbol(user_id, symbol)
        if not holding:
            return False
        current_currency = (current_currency or holding['currency'] or 'USD').upper()
        if previous_close not in (None, 0) and day_change is None:
            day_change = current_price - previous_close
        if previous_close not in (None, 0) and day_change_rate is None and day_change is not None:
            day_change_rate = day_change / previous_close
        values = self.calculate_position_values(
            holding['quantity'],
            holding['purchase_price'],
            current_price,
            current_currency,
            usdjpy,
        )
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE holdings
            SET current_price = ?,
                current_currency = ?,
                current_value = ?,
                current_value_jpy = ?,
                unrealized_pnl = ?,
                unrealized_pnl_jpy = ?,
                unrealized_pnl_rate = ?,
                previous_close = ?,
                day_change = ?,
                day_change_rate = ?,
                price_updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND symbol = ?
        ''', (
            current_price,
            current_currency,
            values['current_value'],
            values['current_value_jpy'],
            values['unrealized_pnl'],
            values['unrealized_pnl_jpy'],
            values['unrealized_pnl_rate'],
            previous_close,
            day_change,
            day_change_rate,
            user_id,
            symbol.upper(),
        ))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed > 0

    def update_holding_price(self, user_id, symbol, current_price):
        """保有銘柄の現在価格を更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        symbol = symbol.upper()
        cursor.execute('''
            UPDATE holdings
            SET current_price = ?
            WHERE user_id = ? AND symbol = ?
        ''', (current_price, user_id, symbol))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed

    def refresh_current_prices_fallback(self, user_id):
        """外部価格API未実装時の現在価格更新。未設定なら取得単価を使う。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE holdings
            SET current_price = purchase_price
            WHERE user_id = ? AND current_price IS NULL
        ''', (user_id,))
        holdings_changed = cursor.rowcount
        cursor.execute('''
            UPDATE simulations
            SET current_price = entry_price, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND current_price IS NULL
        ''', (user_id,))
        simulations_changed = cursor.rowcount
        conn.commit()
        conn.close()
        return {
            'holdings_changed': holdings_changed,
            'simulations_changed': simulations_changed,
        }

    def get_holdings_market_value(self, user_id):
        """保有の評価額を取得。現在価格がなければ取得単価を使う。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(quantity * COALESCE(current_price, purchase_price))
            FROM holdings
            WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0

    def get_simulations_market_value(self, user_id):
        """試算の評価額を取得。総資産には含めない。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(quantity * COALESCE(current_price, entry_price))
            FROM simulations
            WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0

    def add_simulation(self, user_id, ticker, quantity, entry_price, currency='USD', memo=''):
        """試算ポジションを登録・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        ticker = ticker.upper()
        currency = currency.upper()
        cursor.execute('''
            SELECT id FROM simulations WHERE user_id = ? AND ticker = ?
        ''', (user_id, ticker))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
                UPDATE simulations
                SET quantity = ?, entry_price = ?, current_price = ?, currency = ?, memo = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND ticker = ?
            ''', (quantity, entry_price, entry_price, currency, memo, user_id, ticker))
        else:
            cursor.execute('''
                INSERT INTO simulations (user_id, ticker, quantity, entry_price, current_price, currency, memo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, ticker, quantity, entry_price, entry_price, currency, memo))
        conn.commit()
        conn.close()

    def delete_simulation(self, user_id, ticker):
        """試算ポジションを削除"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM simulations WHERE user_id = ? AND ticker = ?', (user_id, ticker.upper()))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed

    def get_simulations(self, user_id):
        """試算ポジション一覧を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                ticker, quantity, entry_price, current_price, currency, memo, created_at, updated_at,
                current_currency, current_value, current_value_jpy,
                unrealized_pnl, unrealized_pnl_jpy, unrealized_pnl_rate,
                previous_close, day_change, day_change_rate,
                price_updated_at
            FROM simulations
            WHERE user_id = ?
            ORDER BY ticker
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'ticker': row[0],
                'quantity': row[1],
                'entry_price': row[2],
                'current_price': row[3],
                'currency': row[4],
                'memo': row[5],
                'created_at': row[6],
                'updated_at': row[7],
                'current_currency': row[8],
                'current_value': row[9],
                'current_value_jpy': row[10],
                'unrealized_pnl': row[11],
                'unrealized_pnl_jpy': row[12],
                'unrealized_pnl_rate': row[13],
                'previous_close': row[14],
                'day_change': row[15],
                'day_change_rate': row[16],
                'price_updated_at': row[17],
            }
            for row in rows
        ]

    def update_simulation_valuation(
        self,
        user_id,
        ticker,
        current_price,
        current_currency='USD',
        usdjpy=None,
        previous_close=None,
        day_change=None,
        day_change_rate=None,
    ):
        """試算ポジションの現在価格・評価額・損益を更新"""
        simulations = [item for item in self.get_simulations(user_id) if item['ticker'] == ticker.upper()]
        if not simulations:
            return False
        simulation = simulations[0]
        current_currency = (current_currency or simulation['currency'] or 'USD').upper()
        if previous_close not in (None, 0) and day_change is None:
            day_change = current_price - previous_close
        if previous_close not in (None, 0) and day_change_rate is None and day_change is not None:
            day_change_rate = day_change / previous_close
        values = self.calculate_position_values(
            simulation['quantity'],
            simulation['entry_price'],
            current_price,
            current_currency,
            usdjpy,
        )
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE simulations
            SET current_price = ?,
                current_currency = ?,
                current_value = ?,
                current_value_jpy = ?,
                unrealized_pnl = ?,
                unrealized_pnl_jpy = ?,
                unrealized_pnl_rate = ?,
                previous_close = ?,
                day_change = ?,
                day_change_rate = ?,
                price_updated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND ticker = ?
        ''', (
            current_price,
            current_currency,
            values['current_value'],
            values['current_value_jpy'],
            values['unrealized_pnl'],
            values['unrealized_pnl_jpy'],
            values['unrealized_pnl_rate'],
            previous_close,
            day_change,
            day_change_rate,
            user_id,
            ticker.upper(),
        ))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed > 0

    def update_simulation_price(self, user_id, ticker, current_price):
        """試算ポジションの現在価格を更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE simulations
            SET current_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND ticker = ?
        ''', (current_price, user_id, ticker.upper()))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed

    def get_holdings_total_cost(self, user_id):
        """保有銘柄の総コストを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT SUM(quantity * purchase_price) FROM holdings WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0

    def add_or_update_hypothesis(self, user_id, symbol, reason, expected_return, add_condition, cut_condition):
        """投資仮説を登録・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        symbol = symbol.upper()
        
        cursor.execute('''
            SELECT id FROM hypotheses WHERE user_id = ? AND symbol = ?
        ''', (user_id, symbol))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE hypotheses
                SET reason = ?, expected_return = ?, add_condition = ?, cut_condition = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND symbol = ?
            ''', (reason, expected_return, add_condition, cut_condition, user_id, symbol))
        else:
            cursor.execute('''
                INSERT INTO hypotheses (user_id, symbol, reason, expected_return, add_condition, cut_condition)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, symbol, reason, expected_return, add_condition, cut_condition))

        conn.commit()
        conn.close()

    def get_hypothesis(self, user_id, symbol):
        """投資仮説を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        symbol = symbol.upper()
        
        cursor.execute('''
            SELECT symbol, reason, expected_return, add_condition, cut_condition, created_at, updated_at
            FROM hypotheses WHERE user_id = ? AND symbol = ?
            ORDER BY updated_at DESC
            LIMIT 1
        ''', (user_id, symbol))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'symbol': result[0],
                'reason': result[1],
                'expected_return': result[2],
                'add_condition': result[3],
                'cut_condition': result[4],
                'created_at': result[5],
                'updated_at': result[6]
            }
        return None
