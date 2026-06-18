"""Price fetching helpers for holdings and simulations."""
import re

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - depends on local environment
    yf = None


def is_japanese_stock(ticker):
    return bool(re.fullmatch(r'\d{4}', str(ticker).strip()))


def is_us_stock(ticker):
    return bool(re.fullmatch(r'[A-Za-z]{1,5}', str(ticker).strip()))


def normalize_ticker(ticker, currency=None):
    symbol = str(ticker).strip().upper()
    if symbol == 'USDJPY':
        return 'JPY=X'
    if is_japanese_stock(symbol):
        return f'{symbol}.T'
    return symbol


def infer_currency(ticker, currency=None):
    if currency:
        return str(currency).upper()
    if is_japanese_stock(ticker):
        return 'JPY'
    return 'USD'


def _get_info_value(ticker_obj, keys):
    try:
        fast_info = getattr(ticker_obj, 'fast_info', None)
        if fast_info:
            for key in keys:
                try:
                    value = fast_info.get(key)
                except AttributeError:
                    value = getattr(fast_info, key, None)
                if value is not None:
                    return float(value)
    except Exception:
        pass

    try:
        info = getattr(ticker_obj, 'info', None)
        if info:
            for key in keys:
                value = info.get(key)
                if value is not None:
                    return float(value)
    except Exception:
        pass
    return None


def _extract_history_closes(ticker_obj):
    try:
        history = ticker_obj.history(period='5d')
        closes = history['Close'].dropna()
        if closes.empty:
            return None, None
        current = float(closes.iloc[-1])
        previous = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return current, previous
    except Exception:
        return None, None


def _extract_price(ticker_obj):
    try:
        fast_info = getattr(ticker_obj, 'fast_info', None)
        if fast_info:
            for key in ('last_price', 'lastPrice', 'regular_market_price'):
                try:
                    value = fast_info.get(key)
                except AttributeError:
                    value = getattr(fast_info, key, None)
                if value:
                    return float(value)
    except Exception:
        pass

    try:
        history = ticker_obj.history(period='1d')
        if not history.empty:
            return float(history['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return None


def fetch_quote(ticker, currency=None):
    if yf is None:
        return None
    symbol = normalize_ticker(ticker, currency)
    try:
        ticker_obj = yf.Ticker(symbol)
        price = _get_info_value(ticker_obj, ('last_price', 'lastPrice', 'regular_market_price', 'regularMarketPrice'))
        previous_close = _get_info_value(ticker_obj, (
            'previous_close',
            'previousClose',
            'regular_market_previous_close',
            'regularMarketPreviousClose',
        ))
        history_price, history_previous = _extract_history_closes(ticker_obj)
        if price is None:
            price = history_price
        if previous_close is None:
            previous_close = history_previous
    except Exception:
        return None
    if price is None:
        return None

    change = None
    change_rate = None
    if previous_close:
        change = price - previous_close
        change_rate = change / previous_close

    return {
        'ticker': str(ticker).strip().upper(),
        'yf_ticker': symbol,
        'yf_symbol': symbol,
        'price': price,
        'previous_close': previous_close,
        'change': change,
        'change_rate': change_rate,
        'currency': infer_currency(ticker, currency),
    }


def fetch_price(ticker, currency=None):
    quote = fetch_quote(ticker, currency)
    if quote is None:
        return None
    return quote


def fetch_prices(tickers):
    results = {}
    for item in tickers:
        if isinstance(item, dict):
            ticker = item.get('ticker') or item.get('symbol')
            currency = item.get('currency')
        else:
            ticker = item
            currency = None
        if not ticker:
            continue
        results[str(ticker).upper()] = fetch_price(ticker, currency)
    return results


def fetch_usdjpy():
    if yf is None:
        return None
    try:
        ticker_obj = yf.Ticker('JPY=X')
        price = _extract_price(ticker_obj)
    except Exception:
        return None
    return price
