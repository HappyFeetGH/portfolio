import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def calculate_unrealized_pnl(avg_price, current_price, shares):
    """미실현 손익 계산"""
    if shares == 0:
        return 0.0, 0.0
    
    cost_basis = avg_price * shares
    current_value = current_price * shares
    pnl = current_value - cost_basis
    pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0.0
    
    return float(pnl), float(pnl_pct)

def calculate_portfolio_value(portfolio, current_prices, exchange_rate=1300.0):
    """전체 포트폴리오 가치 계산 (통화별 분리)"""
    total_value_usd = 0.0
    total_cost_usd = 0.0
    total_value_krw = 0.0
    total_cost_krw = 0.0
    
    strategy_values = {}
    
    for strategy_id, strategy_data in portfolio['strategies'].items():
        strategy_value_usd = 0.0
        strategy_cost_usd = 0.0
        strategy_value_krw = 0.0
        strategy_cost_krw = 0.0
        
        for ticker, position in strategy_data['positions'].items():
            if position['current_shares'] > 0:
                current_price = current_prices.get(ticker, 0.0)
                cost = position['avg_price'] * position['current_shares']
                value = current_price * position['current_shares']
                
                currency = position.get('currency', 'USD')
                
                if currency == 'KRW':
                    strategy_value_krw += value
                    strategy_cost_krw += cost
                    total_value_krw += value
                    total_cost_krw += cost
                else:  # USD
                    strategy_value_usd += value
                    strategy_cost_usd += cost
                    total_value_usd += value
                    total_cost_usd += cost
        
        # 전략별 USD 환산 값 계산
        strategy_value_usd_total = strategy_value_usd + (strategy_value_krw / exchange_rate)
        strategy_cost_usd_total = strategy_cost_usd + (strategy_cost_krw / exchange_rate)
        
        strategy_values[strategy_id] = {
            'value_usd': float(strategy_value_usd),
            'cost_usd': float(strategy_cost_usd),
            'value_krw': float(strategy_value_krw),
            'cost_krw': float(strategy_cost_krw),
            'value': float(strategy_value_usd_total),
            'cost': float(strategy_cost_usd_total),
            'pnl': float(strategy_value_usd_total - strategy_cost_usd_total),
            'pnl_pct': float((strategy_value_usd_total - strategy_cost_usd_total) / strategy_cost_usd_total * 100) if strategy_cost_usd_total > 0 else 0.0
        }
    
    # 전체 USD 환산
    total_value_usd_converted = total_value_usd + (total_value_krw / exchange_rate)
    total_cost_usd_converted = total_cost_usd + (total_cost_krw / exchange_rate)
    
    return {
        'total_value': float(total_value_usd_converted),
        'total_cost': float(total_cost_usd_converted),
        'total_pnl': float(total_value_usd_converted - total_cost_usd_converted),
        'total_pnl_pct': float((total_value_usd_converted - total_cost_usd_converted) / total_cost_usd_converted * 100) if total_cost_usd_converted > 0 else 0.0,
        'total_value_usd': float(total_value_usd),
        'total_cost_usd': float(total_cost_usd),
        'total_value_krw': float(total_value_krw),
        'total_cost_krw': float(total_cost_krw),
        'strategy_values': strategy_values
    }

def calculate_portfolio_history(portfolio, current_prices, exchange_rate=1300.0, days=30):
    """포트폴리오 가치 히스토리 계산 (현재 보유 포지션만)"""
    from utils.price_fetcher import get_historical_prices
    
    # 현재 보유 중인 모든 티커 수집
    all_positions = {}
    for strategy_id, strategy_data in portfolio['strategies'].items():
        for ticker, position in strategy_data['positions'].items():
            if position['current_shares'] > 0:
                all_positions[ticker] = {
                    'shares': position['current_shares'],
                    'avg_price': position['avg_price'],
                    'currency': position.get('currency', 'USD')
                }
    
    if not all_positions:
        return pd.DataFrame()
    
    # 과거 데이터 조회
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    historical_data = {}
    for ticker in all_positions.keys():
        try:
            hist = get_historical_prices(ticker, start_date.strftime('%Y-%m-%d'))
            if not hist.empty and 'Close' in hist.columns:
                historical_data[ticker] = hist['Close']
        except Exception as e:
            print(f"Error loading history for {ticker}: {e}")
            continue
    
    if not historical_data:
        return pd.DataFrame()
    
    # 데이터프레임 생성
    df = pd.DataFrame(historical_data)
    df = df.fillna(method='ffill').fillna(method='bfill')
    
    # 날짜별 포트폴리오 가치 계산
    portfolio_values = []
    portfolio_costs = []
    
    for date, prices in df.iterrows():
        total_value_usd = 0.0
        total_cost_usd = 0.0
        
        for ticker, position in all_positions.items():
            if ticker in prices and pd.notna(prices[ticker]):
                price = prices[ticker]
                value = price * position['shares']
                cost = position['avg_price'] * position['shares']
                
                currency = position['currency']
                if currency == 'KRW':
                    total_value_usd += value / exchange_rate
                    total_cost_usd += cost / exchange_rate
                else:
                    total_value_usd += value
                    total_cost_usd += cost
        
        portfolio_values.append(total_value_usd)
        portfolio_costs.append(total_cost_usd)
    
    # 결과 데이터프레임
    result = pd.DataFrame({
        'date': df.index,
        'portfolio_value': portfolio_values,
        'portfolio_cost': portfolio_costs,
        'pnl': [v - c for v, c in zip(portfolio_values, portfolio_costs)],
        'return_pct': [(v - c) / c * 100 if c > 0 else 0 for v, c in zip(portfolio_values, portfolio_costs)]
    })
    
    return result

def calculate_portfolio_history_by_currency(portfolio, current_prices, exchange_rate=1300.0, days=30):
    """통화별 포트폴리오 가치 히스토리 계산"""
    from utils.price_fetcher import get_historical_prices
    
    # 통화별로 포지션 분리
    usd_positions = {}
    krw_positions = {}
    
    for strategy_id, strategy_data in portfolio['strategies'].items():
        for ticker, position in strategy_data['positions'].items():
            if position['current_shares'] > 0:
                pos_data = {
                    'shares': position['current_shares'],
                    'avg_price': position['avg_price'],
                    'currency': position.get('currency', 'USD')
                }
                
                if pos_data['currency'] == 'KRW':
                    krw_positions[ticker] = pos_data
                else:
                    usd_positions[ticker] = pos_data
    
    # USD 히스토리
    usd_df = pd.DataFrame()
    if usd_positions:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        usd_historical = {}
        for ticker in usd_positions.keys():
            try:
                hist = get_historical_prices(ticker, start_date.strftime('%Y-%m-%d'))
                if not hist.empty and 'Close' in hist.columns:
                    usd_historical[ticker] = hist['Close']
            except Exception as e:
                print(f"Error loading USD history for {ticker}: {e}")
                continue
        
        if usd_historical:
            df = pd.DataFrame(usd_historical).fillna(method='ffill').fillna(method='bfill')
            
            usd_values = []
            usd_costs = []
            
            for date, prices in df.iterrows():
                total_value = 0.0
                total_cost = 0.0
                
                for ticker, position in usd_positions.items():
                    if ticker in prices and pd.notna(prices[ticker]):
                        total_value += prices[ticker] * position['shares']
                        total_cost += position['avg_price'] * position['shares']
                
                usd_values.append(total_value)
                usd_costs.append(total_cost)
            
            usd_df = pd.DataFrame({
                'date': df.index,
                'value': usd_values,
                'cost': usd_costs,
                'pnl': [v - c for v, c in zip(usd_values, usd_costs)],
                'return_pct': [(v - c) / c * 100 if c > 0 else 0 for v, c in zip(usd_values, usd_costs)]
            })
    
    # KRW 히스토리
    krw_df = pd.DataFrame()
    if krw_positions:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        krw_historical = {}
        for ticker in krw_positions.keys():
            try:
                hist = get_historical_prices(ticker, start_date.strftime('%Y-%m-%d'))
                if not hist.empty and 'Close' in hist.columns:
                    krw_historical[ticker] = hist['Close']
            except Exception as e:
                print(f"Error loading KRW history for {ticker}: {e}")
                continue
        
        if krw_historical:
            df = pd.DataFrame(krw_historical).fillna(method='ffill').fillna(method='bfill')
            
            krw_values = []
            krw_costs = []
            
            for date, prices in df.iterrows():
                total_value = 0.0
                total_cost = 0.0
                
                for ticker, position in krw_positions.items():
                    if ticker in prices and pd.notna(prices[ticker]):
                        total_value += prices[ticker] * position['shares']
                        total_cost += position['avg_price'] * position['shares']
                
                krw_values.append(total_value)
                krw_costs.append(total_cost)
            
            krw_df = pd.DataFrame({
                'date': df.index,
                'value': krw_values,
                'cost': krw_costs,
                'pnl': [v - c for v, c in zip(krw_values, krw_costs)],
                'return_pct': [(v - c) / c * 100 if c > 0 else 0 for v, c in zip(krw_values, krw_costs)]
            })
    
    return usd_df, krw_df

def calculate_daily_realized_pnl(portfolio):
    """일별 실현 손익 계산 (통화별 분리) - realized_pnl_events 우선"""
    events = portfolio.get('realized_pnl_events', [])
    
    rows = []
    if events:
        for e in events:
            if e.get("type") == "sell":
                rows.append({
                    "date": e.get("date"),
                    "currency": e.get("currency", "USD"),
                    "realized_pnl": e.get("realized_pnl", 0.0)
                })
    else:
        # 구버전 호환: closed_positions만 있는 경우
        for cp in portfolio.get('closed_positions', []):
            rows.append({
                "date": cp.get("sell_date"),
                "currency": cp.get("currency", "USD"),
                "realized_pnl": cp.get("realized_pnl", 0.0)
            })
    
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
    
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    
    usd = df[df["currency"] == "USD"].groupby("date", as_index=False)["realized_pnl"].sum()
    krw = df[df["currency"] == "KRW"].groupby("date", as_index=False)["realized_pnl"].sum()
    
    if not usd.empty:
        usd["cumulative_pnl"] = usd["realized_pnl"].cumsum()
    if not krw.empty:
        krw["cumulative_pnl"] = krw["realized_pnl"].cumsum()
    
    return usd, krw

def calculate_total_realized_pnl_from_events(portfolio, exchange_rate=1300.0):
    """realized_pnl_events 기반 총 실현손익 계산 (USD 환산)"""
    events = portfolio.get('realized_pnl_events', [])
    
    if events:
        total_usd = 0.0
        for e in events:
            if e.get("type") != "sell":
                continue
            cur = e.get("currency", "USD")
            pnl = float(e.get("realized_pnl", 0.0))
            total_usd += pnl if cur == "USD" else pnl / exchange_rate
        return float(total_usd)
    else:
        # fallback: closed_positions
        return sum([
            cp.get('realized_pnl', 0.0) if cp.get('currency', 'USD') == 'USD'
            else cp.get('realized_pnl', 0.0) / exchange_rate
            for cp in portfolio.get('closed_positions', [])
        ])

def calculate_strategy_metrics(portfolio, strategy_id, current_prices, exchange_rate=1300.0):
    """전략별 성과 지표 계산 (events 우선)"""
    strategy = portfolio['strategies'].get(strategy_id)
    if not strategy:
        return None
    
    positions = strategy['positions']
    
    total_value_usd = 0.0
    total_cost_usd = 0.0
    total_value_krw = 0.0
    total_cost_krw = 0.0
    position_count = 0
    
    for ticker, pos in positions.items():
        if pos['current_shares'] > 0:
            current_price = current_prices.get(ticker, 0.0)
            value = current_price * pos['current_shares']
            cost = pos['avg_price'] * pos['current_shares']
            
            currency = pos.get('currency', 'USD')
            if currency == 'KRW':
                total_value_krw += value
                total_cost_krw += cost
            else:
                total_value_usd += value
                total_cost_usd += cost
            
            position_count += 1
    
    # USD 환산
    total_value = total_value_usd + (total_value_krw / exchange_rate)
    total_cost = total_cost_usd + (total_cost_krw / exchange_rate)
    
    # 실현손익: events 우선
    events = portfolio.get('realized_pnl_events', [])
    if events:
        closed_pnl = sum([
            e.get('realized_pnl', 0.0) if e.get('currency', 'USD') == 'USD' else e.get('realized_pnl', 0.0) / exchange_rate
            for e in events
            if e.get('strategy') == strategy_id and e.get('type') == 'sell'
        ])
    else:
        closed_pnl = sum([
            cp['realized_pnl'] if cp.get('currency', 'USD') == 'USD' else cp['realized_pnl'] / exchange_rate
            for cp in portfolio.get('closed_positions', [])
            if cp.get('strategy') == strategy_id
        ])
    
    unrealized_pnl = total_value - total_cost
    total_pnl = closed_pnl + unrealized_pnl
    
    return {
        'position_count': position_count,
        'total_value': float(total_value),
        'total_cost': float(total_cost),
        'unrealized_pnl': float(unrealized_pnl),
        'unrealized_pnl_pct': float(unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0,
        'realized_pnl': float(closed_pnl),
        'total_pnl': float(total_pnl),
        'total_return_pct': float(total_pnl / (total_cost + abs(closed_pnl)) * 100) if (total_cost + abs(closed_pnl)) > 0 else 0.0
    }

def calculate_sharpe_ratio(returns, risk_free_rate=0.02):
    """샤프 비율 계산"""
    if len(returns) < 2:
        return 0.0
    
    excess_returns = returns - (risk_free_rate / 252)
    
    if excess_returns.std() == 0:
        return 0.0
    
    sharpe = np.sqrt(252) * (excess_returns.mean() / excess_returns.std())
    return float(sharpe)

def calculate_max_drawdown(prices):
    """최대 낙폭(MDD) 계산"""
    if len(prices) < 2:
        return 0.0
    
    cumulative = (1 + prices).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    
    return float(drawdown.min() * 100)

def export_to_csv(portfolio, current_prices, exchange_rate=1300.0, filename='portfolio_export.csv'):
    """포트폴리오 데이터를 CSV로 내보내기"""
    rows = []
    
    for strategy_id, strategy_data in portfolio['strategies'].items():
        for ticker, position in strategy_data['positions'].items():
            if position['current_shares'] > 0:
                current_price = current_prices.get(ticker, 0.0)
                pnl, pnl_pct = calculate_unrealized_pnl(
                    position['avg_price'],
                    current_price,
                    position['current_shares']
                )
                
                currency = position.get('currency', 'USD')
                
                rows.append({
                    '전략': strategy_data['name'],
                    '티커': ticker,
                    '통화': currency,
                    '보유수량': position['current_shares'],
                    '평균단가': position['avg_price'],
                    '현재가': current_price,
                    '평가금액': current_price * position['current_shares'],
                    '투자금액': position['avg_price'] * position['current_shares'],
                    '평가손익': pnl,
                    '수익률(%)': pnl_pct
                })
    
    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    return filename
