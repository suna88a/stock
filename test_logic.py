"""Database logic smoke tests for the investment ledger bot."""
import os
import sqlite3
import tempfile

from config import BASE_ASSET, BASE_DATE
from database import InvestmentDatabase
from price_fetcher import normalize_ticker
from time_utils import format_datetime_jst


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

        db.set_asset(user_id, 6811322)
        asset_change = db.get_asset_previous_change(user_id)
        assert_equal(asset_change['current'], 6811322, 'asset history current')
        assert_equal(asset_change['previous'], BASE_ASSET + 400000, 'asset history previous')
        assert_equal(asset_change['change'], 6811322 - (BASE_ASSET + 400000), 'asset history change')
        db.set_asset(user_id, 6800000)
        db.set_asset(user_id, 6811322)
        asset_change = db.get_asset_previous_change(user_id)
        assert_equal(asset_change['current'], 6811322, 'asset history second current')
        assert_equal(asset_change['previous'], 6800000, 'asset history second previous')
        assert_equal(asset_change['change'], 11322, 'asset history second change')
        db.set_asset_breakdown(user_id, '国内株式', 994000, 'JPY')
        db.set_asset_breakdown(user_id, '米国株式', 2995660, 'JPY')
        db.set_asset_breakdown(user_id, '投資信託', 2404885, 'JPY')
        db.set_asset_breakdown(user_id, '預り金', 381645, 'JPY')
        db.set_asset_breakdown(user_id, 'USドル', 35132, 'JPY')
        asset = db.get_asset(user_id)
        breakdowns = {item['name']: item for item in db.get_asset_breakdowns(user_id)}
        assert_equal(asset['total_asset'], 6811322, 'bulk asset line updates current asset')
        assert_equal(breakdowns['国内株式']['amount'], 994000, 'asset breakdown domestic stocks')
        assert_equal(breakdowns['米国株式']['amount'], 2995660, 'asset breakdown us stocks')
        assert_equal(breakdowns['投資信託']['amount'], 2404885, 'asset breakdown fund')
        assert_equal(breakdowns['預り金']['amount'], 381645, 'asset breakdown cash')
        assert_equal(breakdowns['USドル']['amount'], 35132, 'asset breakdown usd')

        db.add_holding(user_id, 'NET', 77, 228.51, 'USD')
        db.add_holding(user_id, 'NET', 10, 220, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 10, 'holding overwrite quantity')
        assert_close(holding['purchase_price'], 220, 'holding overwrite price')

        db.add_buy(user_id, 'NET', 10, 240, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 20, 'buy adds quantity')
        assert_close(holding['purchase_price'], 230, 'buy recalculates average')

        assert_equal(normalize_ticker('4633'), '4633.T', 'japanese ticker normalization')
        assert_equal(normalize_ticker('AMZN'), 'AMZN', 'us ticker normalization')

        before_price_update_asset = db.get_asset(user_id)['total_asset']
        db.update_holding_valuation(user_id, 'NET', 250, 'USD', usdjpy=157.2, previous_close=240)
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_close(holding['current_value'], 5000, 'usd holding value')
        assert_close(holding['unrealized_pnl'], 400, 'usd holding pnl')
        assert_close(holding['current_value_jpy'], 786000, 'usd holding value jpy')
        assert_close(holding['unrealized_pnl_jpy'], 62880, 'usd holding pnl jpy')
        assert_close(holding['day_change'], 10, 'usd day change')
        assert_close(holding['day_change_rate'], 10 / 240, 'usd day change rate')
        assert_equal(db.get_asset(user_id)['total_asset'], before_price_update_asset, 'price update does not change current asset')

        db.add_holding(user_id, '4633', 100, 1800, 'JPY')
        db.update_holding_valuation(user_id, '4633', 2438, 'JPY', usdjpy=157.2, previous_close=2500)
        jpy_holding = db.get_holding_by_symbol(user_id, '4633')
        assert_close(jpy_holding['current_value'], 243800, 'jpy holding value')
        assert_close(jpy_holding['unrealized_pnl'], 63800, 'jpy holding pnl')
        assert_close(jpy_holding['current_value_jpy'], 243800, 'jpy holding value jpy')
        assert_close(jpy_holding['day_change'], -62, 'jpy day change')
        assert_close(jpy_holding['day_change_rate'], -62 / 2500, 'jpy day change rate')

        sell_result = db.add_sell(user_id, 'NET', 5, 250, 'USD')
        holding = db.get_holding_by_symbol(user_id, 'NET')
        assert_equal(holding['quantity'], 15, 'sell subtracts quantity')
        assert_close(sell_result['realized_profit'], 100, 'sell realized profit')

        before_asset = db.get_asset(user_id)['total_asset']
        db.add_simulation(user_id, 'SOFI', 300, 8.5, 'USD', 'AIテーマ監視')
        db.update_simulation_valuation(user_id, 'SOFI', 10, 'USD', usdjpy=157.2, previous_close=9.5)
        after_asset = db.get_asset(user_id)['total_asset']
        assert_equal(after_asset, before_asset, 'simulation does not affect total asset')
        simulation = db.get_simulations(user_id)[0]
        assert_close(simulation['current_value'], 3000, 'simulation value')
        assert_close(simulation['current_value_jpy'], 471600, 'simulation jpy value')
        assert_close(simulation['day_change'], 0.5, 'simulation day change')
        assert_close(simulation['day_change_rate'], 0.5 / 9.5, 'simulation day change rate')

        assert_equal(format_datetime_jst('2026-06-18 15:22:19'), '2026-06-19 00:22:19', 'jst formatting')

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
