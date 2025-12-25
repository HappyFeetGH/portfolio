# utils/price_fetcher.py
import pandas as pd
from datetime import datetime
import pyupbit
import FinanceDataReader as fdr  # pip install finance-datareader [web:259]

DEFAULT_FX = 1300.0

def detect_ticker_type(ticker: str) -> str:
    t = ticker.upper()
    if t.startswith("KRW-"):
        return "upbit"
    if t.endswith(".KS") or t.endswith(".KQ"):
        return "korean_stock"
    return "us_stock"

def get_currency_for_ticker(ticker: str) -> str:
    tt = detect_ticker_type(ticker)
    return "KRW" if tt in ("upbit", "korean_stock") else "USD"

def _kr_symbol(ticker: str) -> str:
    # "000660.KS" -> "000660"
    t = ticker.upper()
    if t.endswith(".KS") or t.endswith(".KQ"):
        return t.split(".")[0]
    return t

def get_exchange_rate() -> float:
    """
    USD/KRW 환율 (FDR)
    """
    try:
        df = fdr.DataReader("USD/KRW")
        if df is not None and not df.empty and "Close" in df.columns:
            return float(df["Close"].dropna().iloc[-1])
    except Exception as e:
        print(f"환율 조회 실패(FDR): {e}")
    return DEFAULT_FX

def get_upbit_price(ticker: str):
    try:
        price = pyupbit.get_current_price(ticker)
        return float(price) if price else None
    except Exception as e:
        print(f"Error fetching Upbit price for {ticker}: {e}")
        return None

def get_stock_price(ticker: str):
    """
    주식 현재가 (FDR)
    - KR: 000660.KS / 308080.KQ 같은 입력을 받아도 동작하도록 심볼 정규화
    - US: AAPL, MSFT 그대로
    """
    try:
        tt = detect_ticker_type(ticker)
        sym = _kr_symbol(ticker) if tt == "korean_stock" else ticker

        df = fdr.DataReader(sym)
        if df is None or df.empty or "Close" not in df.columns:
            return None
        s = df["Close"].dropna()
        return float(s.iloc[-1]) if not s.empty else None
    except Exception as e:
        print(f"Error fetching stock price (FDR) for {ticker}: {e}")
        return None

def get_current_price(ticker: str):
    tt = detect_ticker_type(ticker)
    if tt == "upbit":
        return get_upbit_price(ticker)
    return get_stock_price(ticker)

def get_multiple_prices(tickers):
    """
    여러 종목 현재가 조회:
    - Upbit은 bulk
    - 주식은 FDR 개별 호출 (US 20 + KR 3 => 23회, 버튼 기반이면 충분히 감당 가능)
    """
    prices = {}
    if not tickers:
        return prices

    tickers = list(set(tickers))

    # 분류
    upbit_tickers = [t for t in tickers if detect_ticker_type(t) == "upbit"]
    stock_tickers = [t for t in tickers if detect_ticker_type(t) != "upbit"]

    # 업비트 bulk
    if upbit_tickers:
        try:
            upbit_prices = pyupbit.get_current_price(upbit_tickers)
            if isinstance(upbit_prices, dict):
                for t, p in upbit_prices.items():
                    if p:
                        prices[t] = float(p)
            elif upbit_prices:
                prices[upbit_tickers[0]] = float(upbit_prices)
        except Exception as e:
            print(f"업비트 가격 조회 실패: {e}")

    # 주식 개별
    for t in stock_tickers:
        p = get_stock_price(t)
        if p is not None:
            prices[t] = float(p)

    return prices

def get_historical_prices(ticker, start_date, end_date=None):
    tt = detect_ticker_type(ticker)
    if tt == "upbit":
        return get_upbit_historical(ticker, start_date, end_date)
    return get_stock_historical(ticker, start_date, end_date)

def get_stock_historical(ticker, start_date, end_date=None):
    """
    주식 과거 가격 (FDR)
    """
    try:
        tt = detect_ticker_type(ticker)
        sym = _kr_symbol(ticker) if tt == "korean_stock" else ticker
        df = fdr.DataReader(sym, start_date, end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        # 기존 calculator.py가 'Close' 컬럼을 쓰는 구조이므로 그대로 반환
        return df
    except Exception as e:
        print(f"Error fetching historical (FDR) for {ticker}: {e}")
        return pd.DataFrame()

def get_upbit_historical(ticker, start_date, end_date=None):
    try:
        df = pyupbit.get_ohlcv(ticker, interval="day", count=200)
        if df is not None and not df.empty:
            df.columns = [col.capitalize() for col in df.columns]
            df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def get_benchmark_data(benchmark="SPY", period="1y"):
    """
    벤치마크도 FDR로 (SPY 등)
    period를 start_date로 변환해서 사용
    """
    try:
        days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
        days = days_map.get(period, 365)
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        df = fdr.DataReader(benchmark, start_date)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
