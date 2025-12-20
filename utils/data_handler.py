import json
import os
from datetime import datetime
import shutil
from utils.price_fetcher import get_currency_for_ticker
import math

DATA_PATH = 'data/portfolio.json'
BACKUP_PATH = 'data/backup'
EPS = 1e-6  # 부동소수점 허용오차 (업비트 대응)

def load_portfolio():
    if not os.path.exists(DATA_PATH):
        return create_initial_portfolio()
    
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 마이그레이션
    if 'realized_pnl_events' not in data:
        data['realized_pnl_events'] = []
    
    # 로드 후 모든 포지션 정합성 검증
    normalize_all_positions(data)
    save_portfolio(data)
    
    return data

def save_portfolio(data):
    """포트폴리오 데이터 저장"""
    data['portfolio_metadata']['last_updated'] = datetime.now().isoformat()
    
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def create_backup():
    """백업 생성"""
    if not os.path.exists(BACKUP_PATH):
        os.makedirs(BACKUP_PATH)
    
    backup_name = f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_file = os.path.join(BACKUP_PATH, backup_name)
    
    if os.path.exists(DATA_PATH):
        shutil.copy(DATA_PATH, backup_file)
        return backup_file
    return None

def create_initial_portfolio():
    """초기 포트폴리오 구조 생성"""
    initial_data = {
        "portfolio_metadata": {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "base_currency": "USD",
            "initial_capital": 10000,
            "default_fee_pct": 0.2,
            "exchange_rate": 1300.0
        },
        "strategies": {
            "value_longterm": {
                "name": "가치투자 기반 장투",
                "description": "매크로 위주, 대형주",
                "base_currency": "USD",
                "allocated_capital": 0,
                "positions": {}
            },
            "momentum": {
                "name": "스크리너 기반 모멘텀",
                "description": "중소형주",
                "base_currency": "USD",
                "allocated_capital": 0,
                "positions": {}
            }
        },
        "closed_positions": [],
        "realized_pnl_events": []
    }
    
    if not os.path.exists('data'):
        os.makedirs('data')
    
    save_portfolio(initial_data)
    return initial_data

def recompute_shares_from_transactions(position: dict) -> float:
    """거래 내역 기반 보유수량 재계산 (진실의 원천)"""
    buy_qty = sum(float(t.get("quantity", 0.0)) for t in position.get("transactions", []) if t.get("type") == "buy")
    sell_qty = sum(float(t.get("quantity", 0.0)) for t in position.get("transactions", []) if t.get("type") == "sell")
    return float(buy_qty - sell_qty)

def normalize_all_positions(portfolio: dict):
    """
    모든 포지션의 current_shares를 transactions 기반으로 재계산
    
    ★ 수정: 0주 포지션도 유지 (거래 내역 보존)
    """
    for strategy_id, strategy in portfolio.get("strategies", {}).items():
        positions = strategy.get("positions", {})
        to_delete = []
        
        for ticker, pos in list(positions.items()):
            # 거래 내역이 없으면 삭제
            if not pos.get('transactions'):
                to_delete.append(ticker)
                continue
            
            # 포지션 완전 재구성 (shares + avg_price)
            rebuild_position_from_transactions(pos)
            
            # ★★★ 수정: 0주 포지션은 유지 (삭제하지 않음) ★★★
            # 음수면 0으로 스냅만 수행
            if pos["current_shares"] < 0:
                pos["current_shares"] = 0.0
        
        # 거래 내역이 없는 포지션만 삭제
        for ticker in to_delete:
            del positions[ticker]


def calculate_total_realized_pnl(transactions: list) -> float:
    """전체 거래 내역 기반 누적 실현손익 계산 (FIFO 방식)"""
    buys = [t for t in transactions if t['type'] == 'buy']
    sells = [t for t in transactions if t['type'] == 'sell']
    
    if not sells:
        return 0.0
    
    # 가중평균 매수가 계산
    total_buy_qty = sum(t['quantity'] for t in buys)
    total_buy_cost = sum(t['price'] * t['quantity'] + t['fee_amount'] for t in buys)
    avg_buy_price = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0
    
    # 매도 기준 실현손익 (매도수량 * (매도가 - 평단가) - 매도수수료)
    total_sell_qty = sum(t['quantity'] for t in sells)
    total_sell_revenue = sum(t['price'] * t['quantity'] for t in sells)
    total_sell_fees = sum(t['fee_amount'] for t in sells)
    
    realized_pnl = total_sell_revenue - (avg_buy_price * total_sell_qty) - total_sell_fees
    
    return float(realized_pnl)

def add_transaction(portfolio, strategy_id, ticker, trans_type, price, quantity, date=None, fee_pct=None, currency=None):
    """매수/매도 거래 추가 (클린 버전)"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    if fee_pct is None:
        fee_pct = portfolio['portfolio_metadata'].get('default_fee_pct', 0.2)
    
    if currency is None:
        currency = get_currency_for_ticker(ticker)
    
    # 수수료 계산
    transaction_amount = price * quantity
    fee_amount = transaction_amount * (fee_pct / 100)
    
    # 포지션 생성 (없으면)
    if ticker not in portfolio['strategies'][strategy_id]['positions']:
        portfolio['strategies'][strategy_id]['positions'][ticker] = {
            "ticker": ticker,
            "currency": currency,
            "current_shares": 0,
            "avg_price": 0,
            "transactions": []
        }
    
    position = portfolio['strategies'][strategy_id]['positions'][ticker]
    
    # 거래 기록 추가
    transaction = {
        "date": date,
        "type": trans_type,
        "price": float(price),
        "quantity": float(quantity),
        "fee_pct": float(fee_pct),
        "fee_amount": float(fee_amount),
        "currency": currency
    }
    position['transactions'].append(transaction)
    
    # ========== 매수 처리 ==========
    if trans_type == "buy":
        total_cost = position['avg_price'] * position['current_shares']
        total_cost += price * quantity + fee_amount
        position['current_shares'] += quantity
        position['avg_price'] = total_cost / position['current_shares']
    
    # ========== 매도 처리 ==========
    elif trans_type == "sell":
        have = float(position['current_shares'])
        sell = float(quantity)
        
        # 과매도 체크 (허용오차 포함)
        if (sell > have) and not math.isclose(sell, have, rel_tol=1e-9, abs_tol=EPS):
            raise ValueError(f"Sell quantity exceeds current shares: have={have:.8f}, sell={sell:.8f}")
        
        # 거의 같으면 전량매도로 스냅
        if math.isclose(sell, have, rel_tol=1e-9, abs_tol=EPS):
            sell = have
            quantity = have
            transaction_amount = price * quantity
            fee_amount = transaction_amount * (fee_pct / 100)
            transaction['quantity'] = float(quantity)
            transaction['fee_amount'] = float(fee_amount)
        
        # 매도 1건 실현손익 (평단가 기준)
        realized_pnl_tx = (price - position['avg_price']) * quantity - fee_amount
        
        # 이벤트 기록 (매도마다 무조건)
        portfolio.setdefault('realized_pnl_events', []).append({
            "date": date,
            "strategy": strategy_id,
            "ticker": ticker,
            "currency": currency,
            "type": "sell",
            "quantity": float(quantity),
            "price": float(price),
            "fee_amount": float(fee_amount),
            "realized_pnl": float(realized_pnl_tx)
        })
        
        # 보유수량 감소
        position['current_shares'] = float(position['current_shares'] - quantity)
        
        # 전량청산 판정 (0에 수렴)
        if math.isclose(position['current_shares'], 0.0, abs_tol=EPS):
            position['current_shares'] = 0.0
            
            # 전체 실현손익 재계산 (transactions 기반)
            total_realized_pnl = calculate_total_realized_pnl(position['transactions'])
            
            # 매도 평균가 계산
            sell_txs = [t for t in position['transactions'] if t['type'] == 'sell']
            total_sell_qty = sum(t['quantity'] for t in sell_txs)
            total_sell_amount = sum(t['price'] * t['quantity'] for t in sell_txs)
            avg_sell_price = (total_sell_amount / total_sell_qty) if total_sell_qty > 0 else 0.0
            
            # 매수 평균가 계산
            buy_txs = [t for t in position['transactions'] if t['type'] == 'buy']
            total_buy_qty = sum(t['quantity'] for t in buy_txs)
            total_buy_cost = sum(t['price'] * t['quantity'] + t['fee_amount'] for t in buy_txs)
            avg_buy_price = (total_buy_cost / total_buy_qty) if total_buy_qty > 0 else 0.0
            
            # 수익률 계산
            return_pct = ((avg_sell_price - avg_buy_price) / avg_buy_price * 100) if avg_buy_price > 0 else 0.0
            
            # closed_positions 요약 (선택적, 히스토리용)
            closed_position = {
                "ticker": ticker,
                "currency": currency,
                "strategy": strategy_id,
                "buy_date": position['transactions'][0]['date'],
                "sell_date": date,
                "quantity": total_buy_qty,
                "avg_buy_price": avg_buy_price,
                "avg_sell_price": avg_sell_price,
                "realized_pnl": total_realized_pnl,
                "return_pct": return_pct
            }
            portfolio['closed_positions'].append(closed_position)
            
            # ★★★ 중요: 포지션을 삭제하지 않고 유지! ★★★
            # del portfolio['strategies'][strategy_id]['positions'][ticker]  # 이 줄 삭제 또는 주석처리

    save_portfolio(portfolio)


# 나머지 함수들은 기존과 동일
def add_strategy(portfolio, strategy_id, name, description, base_currency="USD", allocated_capital=0):
    portfolio['strategies'][strategy_id] = {
        "name": name,
        "description": description,
        "base_currency": base_currency,
        "allocated_capital": allocated_capital,
        "positions": {}
    }
    save_portfolio(portfolio)

def delete_strategy(portfolio, strategy_id):
    if strategy_id in portfolio['strategies']:
        if len(portfolio['strategies'][strategy_id]['positions']) == 0:
            del portfolio['strategies'][strategy_id]
            save_portfolio(portfolio)
            return True
    return False

def update_strategy_capital(portfolio, strategy_id, allocated_capital):
    if strategy_id in portfolio['strategies']:
        portfolio['strategies'][strategy_id]['allocated_capital'] = allocated_capital
        save_portfolio(portfolio)
        return True
    return False

def update_strategy_info(portfolio, strategy_id, name=None, description=None, base_currency=None):
    if strategy_id in portfolio['strategies']:
        if name:
            portfolio['strategies'][strategy_id]['name'] = name
        if description:
            portfolio['strategies'][strategy_id]['description'] = description
        if base_currency:
            portfolio['strategies'][strategy_id]['base_currency'] = base_currency
        save_portfolio(portfolio)
        return True
    return False

def rebuild_position_from_transactions(position: dict):
    """
    거래 내역(transactions)만을 기반으로 포지션을 완전히 재구성
    current_shares, avg_price를 처음부터 다시 계산
    
    ★ 핵심: 매수는 가중평균, 매도는 수량만 차감
    """
    current_shares = 0.0
    total_cost = 0.0  # 수수료 포함 총 매수 비용
    
    # Step 1: 모든 거래를 순회하며 재계산
    for tx in position['transactions']:
        if tx['type'] == 'buy':
            # 매수: 비용 추가, 수량 추가
            total_cost += tx['price'] * tx['quantity'] + tx['fee_amount']
            current_shares += tx['quantity']
        
        elif tx['type'] == 'sell':
            # 매도: 수량만 차감 (평단가는 불변)
            # 단, 총 비용도 비례해서 차감 (남은 주식의 비용만 유지)
            if current_shares > 0:
                sell_ratio = tx['quantity'] / current_shares
                total_cost = total_cost * (1.0 - sell_ratio)
            current_shares -= tx['quantity']
    
    # Step 2: 결과 반영
    position['current_shares'] = float(current_shares)
    
    # Step 3: 평단가 계산
    if current_shares > EPS:
        position['avg_price'] = float(total_cost / current_shares)
    else:
        position['avg_price'] = 0.0
        # ★ 주의: 여기서 current_shares를 0으로 강제하지 않음!
        # 부동소수점 오차로 -0.0000001 같은 값이 나올 수 있지만
        # 이건 나중에 normalize에서 처리

def rebuild_realized_pnl_events(portfolio):
    """
    모든 포지션의 transactions를 순회하며 realized_pnl_events를 완전히 재구성
    
    ★ 핵심: 매도 시점의 평단가를 정확히 계산
    """
    portfolio['realized_pnl_events'] = []
    
    for strategy_id, strategy in portfolio['strategies'].items():
        for ticker, position in strategy['positions'].items():
            # 매도 시점의 평단가를 추적하기 위한 임시 변수
            running_shares = 0.0
            running_cost = 0.0
            
            for tx in position['transactions']:
                if tx['type'] == 'buy':
                    # 매수 시 비용/수량 누적
                    running_cost += tx['price'] * tx['quantity'] + tx['fee_amount']
                    running_shares += tx['quantity']
                
                elif tx['type'] == 'sell':
                    # 매도 시점의 평단가 계산
                    avg_price_at_sell = running_cost / running_shares if running_shares > 0 else 0
                    
                    # 실현손익 = (매도가 - 평단가) * 수량 - 매도수수료
                    realized_pnl = (tx['price'] - avg_price_at_sell) * tx['quantity'] - tx['fee_amount']
                    
                    # 이벤트 추가
                    portfolio['realized_pnl_events'].append({
                        "date": tx['date'],
                        "strategy": strategy_id,
                        "ticker": ticker,
                        "currency": tx.get('currency', 'USD'),
                        "type": "sell",
                        "quantity": float(tx['quantity']),
                        "price": float(tx['price']),
                        "fee_amount": float(tx['fee_amount']),
                        "realized_pnl": float(realized_pnl)
                    })
                    
                    # 매도 후 비용/수량 조정
                    if running_shares > 0:
                        sell_ratio = tx['quantity'] / running_shares
                        running_cost = running_cost * (1.0 - sell_ratio)
                    running_shares -= tx['quantity']


def delete_transaction(portfolio, strategy_id, ticker, transaction_index):
    """
    특정 거래를 삭제하고 포지션/이벤트를 재계산
    
    ★ 핵심: transactions만 삭제하고, 나머지는 rebuild로 자동 복구
    """
    # 삭제 전 백업
    create_backup()
    
    if strategy_id not in portfolio['strategies']:
        return False
    
    if ticker not in portfolio['strategies'][strategy_id]['positions']:
        return False
    
    position = portfolio['strategies'][strategy_id]['positions'][ticker]
    
    if transaction_index < 0 or transaction_index >= len(position['transactions']):
        return False
    
    # Step 1: 거래 삭제
    deleted_tx = position['transactions'].pop(transaction_index)
    
    # Step 2: 거래가 모두 사라지면 포지션 삭제
    if len(position['transactions']) == 0:
        del portfolio['strategies'][strategy_id]['positions'][ticker]
    else:
        # Step 3: 포지션 재계산 (transactions 기반 완전 재구성)
        rebuild_position_from_transactions(position)
        
        # ★★★ 수정: 0주가 되어도 포지션은 유지 (거래 내역 보존) ★★★
        # 포지션 삭제 로직 제거
    
    # Step 4: realized_pnl_events 완전 재구성 (전체 동기화)
    rebuild_realized_pnl_events(portfolio)
    
    # Step 5: 저장
    save_portfolio(portfolio)
    
    return True


def get_all_transactions_with_metadata(portfolio):
    """
    모든 거래 내역을 메타데이터와 함께 반환 (삭제용 UI)
    
    Returns:
        list: [{
            'strategy_id': str,
            'strategy_name': str,
            'ticker': str,
            'transaction_index': int,
            'date': str,
            'type': str,
            'price': float,
            'quantity': float,
            'fee_amount': float,
            'currency': str
        }]
    """
    all_transactions = []
    
    for strategy_id, strategy in portfolio['strategies'].items():
        strategy_name = strategy['name']
        
        for ticker, position in strategy['positions'].items():
            for idx, tx in enumerate(position['transactions']):
                all_transactions.append({
                    'strategy_id': strategy_id,
                    'strategy_name': strategy_name,
                    'ticker': ticker,
                    'transaction_index': idx,
                    'date': tx['date'],
                    'type': tx['type'],
                    'price': tx['price'],
                    'quantity': tx['quantity'],
                    'fee_amount': tx['fee_amount'],
                    'currency': tx.get('currency', 'USD')
                })
    
    # 날짜 최신순 정렬
    all_transactions.sort(key=lambda x: x['date'], reverse=True)
    
    return all_transactions

def restore_from_backup(backup_file):
    """
    백업 파일로부터 포트폴리오 복원
    
    Args:
        backup_file: 백업 파일 경로
    
    Returns:
        bool: 성공 여부
    """
    try:
        # 현재 파일을 임시 백업
        if os.path.exists(DATA_PATH):
            temp_backup = DATA_PATH + '.temp_backup'
            shutil.copy(DATA_PATH, temp_backup)
        
        # 백업에서 복원
        shutil.copy(backup_file, DATA_PATH)
        
        # 임시 백업 삭제
        if os.path.exists(temp_backup):
            os.remove(temp_backup)
        
        return True
    except Exception as e:
        print(f"Restore failed: {e}")
        # 복원 실패 시 임시 백업을 다시 되돌림
        if os.path.exists(temp_backup):
            shutil.copy(temp_backup, DATA_PATH)
            os.remove(temp_backup)
        return False

def get_backup_files():
    """
    모든 백업 파일 목록 반환 (최신순)
    
    Returns:
        list: [(파일명, 전체 경로, 생성 시간)]
    """
    if not os.path.exists(BACKUP_PATH):
        return []
    
    backups = []
    for filename in os.listdir(BACKUP_PATH):
        if filename.endswith('.json'):
            filepath = os.path.join(BACKUP_PATH, filename)
            mtime = os.path.getmtime(filepath)
            backups.append((filename, filepath, datetime.fromtimestamp(mtime)))
    
    # 최신순 정렬
    backups.sort(key=lambda x: x[2], reverse=True)
    
    return backups
