import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pyupbit
import numpy as np

def get_exchange_rate():
    """USD/KRW 환율 조회"""
    try:
        ticker = yf.Ticker("KRW=X")
        data = ticker.history(period='5d') # 기간 늘림
        if not data.empty and not data['Close'].dropna().empty:
            return float(data['Close'].dropna().iloc[-1]) # NaN 제외 후 마지막 값
        return 1300.0
    except Exception as e:
        print(f"환율 조회 실패: {e}")
        return 1300.0

def detect_ticker_type(ticker):
    """티커 유형 감지"""
    ticker_upper = ticker.upper()
    if ticker_upper.startswith('KRW-'): return 'upbit'
    if ticker_upper.endswith('.KS') or ticker_upper.endswith('.KQ'): return 'korean_stock'
    return 'us_stock'

def get_current_price(ticker):
    """현재가 조회 (자동 감지)"""
    ticker_type = detect_ticker_type(ticker)
    if ticker_type == 'upbit':
        return get_upbit_price(ticker)
    else:
        return get_stock_price(ticker)

def get_stock_price(ticker):
    """주식 현재가 조회 (단일)"""
    try:
        stock = yf.Ticker(ticker)
        # 1일 대신 5일치 데이터를 가져와 안전장치 확보
        data = stock.history(period='5d')
        
        # 데이터가 있고, Close 컬럼의 유효한 값이 하나라도 있다면
        if not data.empty and not data['Close'].dropna().empty:
            return float(data['Close'].dropna().iloc[-1])
            
        return None
    except Exception as e:
        print(f"Error fetching stock price for {ticker}: {e}")
        return None

def get_upbit_price(ticker):
    """업비트 현재가"""
    try:
        price = pyupbit.get_current_price(ticker)
        if price:
            return float(price)
        return None
    except Exception as e:
        print(f"Error fetching Upbit price for {ticker}: {e}")
        return None

def get_multiple_prices(tickers):
    """여러 종목 현재가 한번에 조회 (NaN 방지 로직 적용)"""
    prices = {}
    if not tickers:
        return {}
    
    # 분류
    us_stocks = []
    korean_stocks = []
    upbit_tickers = []
    
    for ticker in tickers:
        ticker_type = detect_ticker_type(ticker)
        if ticker_type == 'upbit':
            upbit_tickers.append(ticker)
        elif ticker_type == 'korean_stock':
            korean_stocks.append(ticker)
        else:
            us_stocks.append(ticker)
    
    # === 미국 주식 일괄 조회 ===
    if us_stocks:
        try:
            tickers_str = ' '.join(us_stocks)
            # 5일치 데이터 요청 (주말/휴일/시차로 인한 NaN 방지)
            data = yf.download(tickers_str, period='5d', progress=False, auto_adjust=False)
            
            if not data.empty:
                closes = data['Close']
                
                if len(us_stocks) == 1:
                    # 단일 종목 (Series)
                    if not closes.dropna().empty:
                        prices[us_stocks[0]] = float(closes.dropna().iloc[-1])
                else:
                    # 다중 종목 (DataFrame)
                    # 각 컬럼(종목)별로 순회하며 마지막 유효값(valid value) 추출
                    for ticker in us_stocks:
                        if ticker in closes.columns:
                            series = closes[ticker].dropna()
                            if not series.empty:
                                prices[ticker] = float(series.iloc[-1])
                            else:
                                print(f"Warning: No valid price data for {ticker}")
        except Exception as e:
            print(f"미국 주식 가격 조회 실패: {e}")
            # 실패 시 개별 조회 시도 (Fallback)
            for ticker in us_stocks:
                p = get_stock_price(ticker)
                if p: prices[ticker] = p
    
    # === 한국 주식 일괄 조회 ===
    if korean_stocks:
        try:
            tickers_str = ' '.join(korean_stocks)
            data = yf.download(tickers_str, period='5d', progress=False, auto_adjust=False)
            
            if not data.empty:
                closes = data['Close']
                
                if len(korean_stocks) == 1:
                    if not closes.dropna().empty:
                        prices[korean_stocks[0]] = float(closes.dropna().iloc[-1])
                else:
                    for ticker in korean_stocks:
                        if ticker in closes.columns:
                            series = closes[ticker].dropna()
                            if not series.empty:
                                prices[ticker] = float(series.iloc[-1])
        except Exception as e:
            print(f"한국 주식 가격 조회 실패: {e}")
            for ticker in korean_stocks:
                p = get_stock_price(ticker)
                if p: prices[ticker] = p
    
    # === 업비트 조회 ===
    if upbit_tickers:
        try:
            upbit_prices = pyupbit.get_current_price(upbit_tickers)
            if upbit_prices:
                if isinstance(upbit_prices, dict):
                    for ticker, price in upbit_prices.items():
                        if price:
                            prices[ticker] = float(price)
                else:
                    prices[upbit_tickers[0]] = float(upbit_prices)
        except Exception as e:
            print(f"업비트 가격 조회 실패: {e}")

    return prices

# ... 기존 historical 함수들은 유지 ...
# (이전 단계에서 수정한 timezone safe 버전 사용)
def get_historical_prices(ticker, start_date, end_date=None):
    ticker_type = detect_ticker_type(ticker)
    if ticker_type == 'upbit':
        return get_upbit_historical(ticker, start_date, end_date)
    else:
        return get_stock_historical(ticker, start_date, end_date)

def get_stock_historical(ticker, start_date, end_date=None):
    try:
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        stock = yf.Ticker(ticker)
        data = stock.history(start=start_date, end=end_date, auto_adjust=False)
        if not data.empty and data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        return data
    except Exception as e:
        print(f"Error: {e}")
        return pd.DataFrame()

def get_upbit_historical(ticker, start_date, end_date=None):
    try:
        df = pyupbit.get_ohlcv(ticker, interval="day", count=200)
        if df is not None and not df.empty:
            df.columns = [col.capitalize() for col in df.columns]
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]
            return df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def get_benchmark_data(benchmark='SPY', period='1y'):
    try:
        stock = yf.Ticker(benchmark)
        data = stock.history(period=period, auto_adjust=False)
        if not data.empty and data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        return data
    except Exception as e:
        return pd.DataFrame()

def get_currency_for_ticker(ticker):
    ticker_type = detect_ticker_type(ticker)
    if ticker_type == 'upbit' or ticker_type == 'korean_stock':
        return 'KRW'
    else:
        return 'USD'
