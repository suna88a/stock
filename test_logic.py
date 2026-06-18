"""Database logic smoke tests for the investment ledger bot."""
import os
import sqlite3
import tempfile

from config import BASE_ASSET, BASE_DATE
from database import InvestmentDatabase


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def assert_close(actual, expected, label, tolerance=1e-6):
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def main():
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.remove(db_path)

    try:
        db = InvestmentDatabase(db_path)
        user_id = 12345

        initial_asset = db.get_asset(user_id)
        assert_equal(initial_asset['initial_asset'], BASE_ASSET, 'initial_asset default')
        assert_equal(initial_asset['total_asset'], BASE_ASSET, 'current_asset default')
        assert_equal(initial_asset['base_date'], BASE_DATE.date().isoformat(), 'base_date default')

        db.add_deposit(user_id, 500000, 'JPY')
        db.add_withdraw(user_id, 100000, 'JPY')

        cash_flow = db.get_cash_flow_summary(user_id)
        asset = db.get_asset(user_id)
        performance = asset['total_asset'] - asset['initial_asset'] - cash_flow['net_deposit']
        return_rate = performance / asset['initial_asset'] if asset['initial_asset'] else 0
        assert_equal(cash_flow['deposit_total'], 500000, 'deposit_total')
        assert_equal(cash_flow['withdraw_total'], 100000, 'withdraw_total')
        assert_equal(cash_flow['net_deposit'], 400000, 'net_deposit')
        assert_equal(asset['total_asset'], BASE_ASSET + 400000, 'asset after deposit/withdraw')
        assert_equal(performance, 0, 'performance after deposit/withdraw')
        assert_close(return_rate, 0, 'return rate after deposit/withdraw')

        db.add_holding(user_id, 'NET', 77, 228.51, 'USD')
        db.add_holding(user_id, 'NET', 10, 220, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 10, 'holding overwrite quantity')
        assert_close(holding['purchase_price'], 220, 'holding overwrite price')

        db.add_buy(user_id, 'NET', 10, 240, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 20, 'buy adds quantity')
        assert_close(holding['purchase_price'], 230, 'buy recalculates average')

        sell_result = db.add_sell(user_id, 'NET', 5, 250, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 15, 'sell subtracts quantity')
        assert_close(sell_result['realized_profit'], 100, 'sell realized profit')

        before_asset = db.get_asset(user_id)['total_asset']
        db.add_simulation(user_id, 'SOFI', 300, 8.5, 'USD', 'AIテーマ監視')
        after_asset = db.get_asset(user_id)['total_asset']
        assert_equal(after_asset, before_asset, 'simulation does not affect total asset')

        legacy_user_id = 67890
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_assets (user_id, total_asset, deposits)
            VALUES (?, ?, ?)
        ''', (legacy_user_id, 400000, 500000))
        conn.commit()
        conn.close()

        migrated_asset = db.get_asset(legacy_user_id)
        assert_equal(migrated_asset['initial_asset'], BASE_ASSET, 'legacy initial asset migration')
        assert_equal(migrated_asset['total_asset'], BASE_ASSET + 400000, 'legacy current asset migration')

        print('OK')
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == '__main__':
    main()
