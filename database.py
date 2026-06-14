"""SQLiteデータベース管理"""
import sqlite3
from datetime import datetime
from config import DB_PATH


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
        
        conn.commit()
        conn.close()
    
    def set_asset(self, user_id, total_asset):
        """資産を設定・更新"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO user_assets (user_id, total_asset) 
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            total_asset = ?, last_updated = CURRENT_TIMESTAMP
        ''', (user_id, total_asset, total_asset))
        
        conn.commit()
        conn.close()
    
    def get_asset(self, user_id):
        """資産情報を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT total_asset, deposits, last_updated 
            FROM user_assets WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'total_asset': result[0],
                'deposits': result[1],
                'last_updated': result[2]
            }
        return None
    
    def add_deposit(self, user_id, amount, notes=''):
        """入金を記録"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        
        # 入金履歴を記録
        cursor.execute('''
            INSERT INTO deposits (user_id, amount, deposit_date, notes)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, today, notes))
        
        # ユーザー資産の累計入金を更新
        cursor.execute('''
            SELECT deposits FROM user_assets WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        
        if result:
            current_deposits = result[0]
            cursor.execute('''
                UPDATE user_assets 
                SET deposits = ?, total_asset = total_asset + ? 
                WHERE user_id = ?
            ''', (current_deposits + amount, amount, user_id))
        else:
            cursor.execute('''
                INSERT INTO user_assets (user_id, total_asset, deposits)
                VALUES (?, ?, ?)
            ''', (user_id, amount, amount))
        
        conn.commit()
        conn.close()
    
    def get_deposits(self, user_id):
        """入金履歴を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT SUM(amount) FROM deposits WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0

    def add_holding(self, user_id, symbol, quantity, purchase_price, currency='JPY'):
        """保有銘柄を記録"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        symbol = symbol.upper()
        currency = currency.upper()
        
        cursor.execute('''
            INSERT INTO holdings (user_id, symbol, quantity, purchase_price, currency, purchase_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, symbol, quantity, purchase_price, currency, today))
        
        conn.commit()
        conn.close()

    def get_holdings(self, user_id):
        """ユーザーの保有銘柄を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT symbol, quantity, purchase_price, currency, purchase_date
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
                'purchase_date': row[4]
            }
            for row in results
        ]

    def get_holding_by_symbol(self, user_id, symbol):
        """特定銘柄の保有情報を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        symbol = symbol.upper()
        
        cursor.execute('''
            SELECT symbol, quantity, purchase_price, currency, purchase_date
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
                'purchase_date': result[4]
            }
        return None

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
