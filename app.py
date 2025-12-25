import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os
import time

# utils 모듈 import
from utils.data_handler import (
    load_portfolio,
    save_portfolio,
    add_transaction,
    add_strategy,
    delete_strategy,
    update_strategy_capital,
    update_strategy_info,
    create_backup,
    delete_transaction,  # 추가
    get_all_transactions_with_metadata,  # 추가
    restore_from_backup,  # 추가
    get_backup_files  # 추가
)

from utils.price_fetcher import (
    get_current_price, get_multiple_prices, get_benchmark_data,
    get_exchange_rate, detect_ticker_type, get_currency_for_ticker
)
from utils.calculator import (
    calculate_unrealized_pnl, calculate_portfolio_value, calculate_daily_realized_pnl,
    calculate_strategy_metrics, export_to_csv, calculate_portfolio_history, calculate_portfolio_history_by_currency, calculate_total_realized_pnl_from_events
)

# 페이지 설정
st.set_page_config(
    page_title="포트폴리오 관리자",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()
if 'current_prices' not in st.session_state:
    st.session_state.current_prices = {}
if 'exchange_rate' not in st.session_state:
    st.session_state.exchange_rate = st.session_state.portfolio['portfolio_metadata'].get('exchange_rate', 1300.0)

# 타이틀
st.title("📊 멀티 전략 포트폴리오 관리자")
st.markdown("---")

# 사이드바 - 메뉴
# 사이드바 메뉴 (기존 메뉴 아래 추가)
menu = st.sidebar.radio(
    "메뉴",
    [
        "📈 대시보드",
        "➕ 거래 입력",
        "📝 거래 관리",  # 👈 이 줄 추가
        "⚙️ 전략 관리",
        "💹 가격 업데이트",
        "📊 성과 분석"
    ],
    key="main_menu"
)


# 환율 업데이트 버튼
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("💱 환율 업데이트", use_container_width=True):
        with st.spinner("환율 조회 중..."):
            st.session_state.exchange_rate = get_exchange_rate()
            st.session_state.portfolio['portfolio_metadata']['exchange_rate'] = st.session_state.exchange_rate
            save_portfolio(st.session_state.portfolio)
            st.sidebar.success(f"✅ {st.session_state.exchange_rate:.2f} KRW/USD")

with col2:
    if st.button("🔄 가격 업데이트", use_container_width=True):
        with st.spinner("가격 데이터 업데이트 중..."):
            all_tickers = []
            for strategy in st.session_state.portfolio['strategies'].values():
                all_tickers.extend(strategy['positions'].keys())

            if all_tickers:
                st.session_state.current_prices = get_multiple_prices(list(set(all_tickers)))
                st.sidebar.success("✅ 가격 업데이트 완료")
            else:
                st.sidebar.info("보유 종목이 없습니다")

# 환율 표시
st.sidebar.metric("USD/KRW 환율", f"₩{st.session_state.exchange_rate:,.2f}")

# 백업 버튼
if st.sidebar.button("💾 백업 생성", use_container_width=True):
    backup_file = create_backup()
    if backup_file:
        st.sidebar.success(f"✅ 백업 완료: {os.path.basename(backup_file)}")

st.sidebar.markdown("---")
st.sidebar.caption(f"마지막 업데이트: {st.session_state.portfolio['portfolio_metadata']['last_updated']}")

# === 메뉴별 페이지 ===

if menu == "📈 대시보드":
    st.header("포트폴리오 대시보드")
    
    # 가격 데이터 확인
    if not st.session_state.current_prices:
        st.warning("⚠️ '가격 업데이트' 버튼을 눌러 최신 가격을 불러오세요")
    else:
        # 전체 포트폴리오 가치 계산
        portfolio_summary = calculate_portfolio_value(
            st.session_state.portfolio,
            st.session_state.current_prices,
            st.session_state.exchange_rate
        )
        
        # 통화별 총 할당 자본 계산
        total_allocated_usd = sum([
            s.get('allocated_capital', 0) 
            for s in st.session_state.portfolio['strategies'].values()
            if s.get('base_currency', 'USD') == 'USD'
        ])
        
        total_allocated_krw = sum([
            s.get('allocated_capital', 0) 
            for s in st.session_state.portfolio['strategies'].values()
            if s.get('base_currency', 'USD') == 'KRW'
        ])
        
        # 현금 계산 (통화별)
        cash_balance_usd = total_allocated_usd - portfolio_summary['total_cost_usd']
        cash_balance_krw = total_allocated_krw - portfolio_summary['total_cost_krw']
        cash_balance_total = cash_balance_usd + (cash_balance_krw / st.session_state.exchange_rate)
        
        # 상단 KPI
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_portfolio_value = portfolio_summary['total_value'] + cash_balance_total
            st.metric(
                "총 자산 (USD)",
                f"${total_portfolio_value:,.2f}",
                f"{portfolio_summary['total_pnl_pct']:.2f}%" if portfolio_summary['total_cost'] > 0 else "0.00%"
            )
            st.caption(f"≈ ₩{total_portfolio_value * st.session_state.exchange_rate:,.0f}")
        
        with col2:
            st.metric(
                "투자금액 (USD)",
                f"${portfolio_summary['total_cost']:,.2f}",
                f"현금: ${cash_balance_total:,.2f}"
            )
            st.caption(f"USD: ${portfolio_summary['total_cost_usd']:,.2f} | KRW: ₩{portfolio_summary['total_cost_krw']:,.0f}")
        
        with col3:
            pnl_color = "normal" if portfolio_summary['total_pnl'] >= 0 else "inverse"
            st.metric(
                "평가손익 (USD)",
                f"${portfolio_summary['total_pnl']:,.2f}",
                delta_color=pnl_color
            )
            st.caption(f"≈ ₩{portfolio_summary['total_pnl'] * st.session_state.exchange_rate:,.0f}")
        
        with col4:
            # realized_pnl_events 기반 총 실현손익 (부분매도 포함)
            realized_pnl_usd = calculate_total_realized_pnl_from_events(
                st.session_state.portfolio,
                st.session_state.exchange_rate
            )
            
            st.metric(
                "실현손익 (USD)",
                f"${realized_pnl_usd:,.2f}"
            )
            st.caption(f"≈ ₩{realized_pnl_usd * st.session_state.exchange_rate:,.0f}")

        
        st.markdown("---")
        
        # 📊 포트폴리오 수익률 추이
        st.subheader("📊 포트폴리오 수익률 추이")
        
        # 기간 선택
        col1, col2 = st.columns([1, 3])
        
        with col1:
            period_days = st.selectbox(
                "조회 기간",
                [7, 14, 30, 60, 90, 180, 365],
                index=2,
                format_func=lambda x: f"{x}일",
                key="period_select"
            )
        
        with col2:
            chart_mode = st.radio(
                "차트 모드",
                ["통합 (USD 환산)", "통화별 분리"],
                horizontal=True,
                key="chart_mode_select"
            )
        
        # 수익률 히스토리 계산
        if chart_mode == "통합 (USD 환산)":
            with st.spinner("수익률 데이터 로딩 중..."):
                history_df = calculate_portfolio_history(
                    st.session_state.portfolio,
                    st.session_state.current_prices,
                    st.session_state.exchange_rate,
                    days=period_days
                )
            
            if not history_df.empty:
                # 수익률 꺾은선 그래프
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=history_df['date'],
                    y=history_df['return_pct'],
                    mode='lines',
                    name='수익률 (%)',
                    line=dict(color='#1f77b4', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(31, 119, 180, 0.1)'
                ))
                
                # 0% 기준선
                fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                
                fig.update_layout(
                    title=f"포트폴리오 수익률 추이 (최근 {period_days}일)",
                    xaxis_title="날짜",
                    yaxis_title="수익률 (%)",
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 통계 요약
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("현재 수익률", f"{history_df['return_pct'].iloc[-1]:.2f}%")
                with col2:
                    st.metric("평균 수익률", f"{history_df['return_pct'].mean():.2f}%")
                with col3:
                    st.metric("최고 수익률", f"{history_df['return_pct'].max():.2f}%")
                with col4:
                    st.metric("최저 수익률", f"{history_df['return_pct'].min():.2f}%")
            else:
                st.info("히스토리 데이터가 없습니다. 포지션을 보유하고 있어야 합니다.")
        
        else:  # 통화별 분리
            with st.spinner("수익률 데이터 로딩 중..."):
                usd_history, krw_history = calculate_portfolio_history_by_currency(
                    st.session_state.portfolio,
                    st.session_state.current_prices,
                    st.session_state.exchange_rate,
                    days=period_days
                )
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 🇺🇸 USD 포트폴리오")
                if not usd_history.empty:
                    fig_usd = go.Figure()
                    
                    fig_usd.add_trace(go.Scatter(
                        x=usd_history['date'],
                        y=usd_history['return_pct'],
                        mode='lines',
                        name='USD 수익률 (%)',
                        line=dict(color='#2ca02c', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(44, 160, 44, 0.1)'
                    ))
                    
                    fig_usd.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                    
                    fig_usd.update_layout(
                        xaxis_title="날짜",
                        yaxis_title="수익률 (%)",
                        hovermode='x unified',
                        height=300
                    )
                    
                    st.plotly_chart(fig_usd, use_container_width=True)
                    
                    st.metric("현재 USD 수익률", f"{usd_history['return_pct'].iloc[-1]:.2f}%")
                else:
                    st.info("USD 포지션이 없습니다")
            
            with col2:
                st.markdown("#### 🇰🇷 KRW 포트폴리오")
                if not krw_history.empty:
                    fig_krw = go.Figure()
                    
                    fig_krw.add_trace(go.Scatter(
                        x=krw_history['date'],
                        y=krw_history['return_pct'],
                        mode='lines',
                        name='KRW 수익률 (%)',
                        line=dict(color='#ff7f0e', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(255, 127, 14, 0.1)'
                    ))
                    
                    fig_krw.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                    
                    fig_krw.update_layout(
                        xaxis_title="날짜",
                        yaxis_title="수익률 (%)",
                        hovermode='x unified',
                        height=300
                    )
                    
                    st.plotly_chart(fig_krw, use_container_width=True)
                    
                    st.metric("현재 KRW 수익률", f"{krw_history['return_pct'].iloc[-1]:.2f}%")
                else:
                    st.info("KRW 포지션이 없습니다")
        
        st.markdown("---")
        
        # 💰 일일 실현 손익
        st.subheader("💰 일일 실현 손익")
        
        usd_realized_df, krw_realized_df = calculate_daily_realized_pnl(st.session_state.portfolio)

        # 탭은 항상 2개 표시 (데이터 유무와 무관)
        tab1, tab2 = st.tabs(["🇺🇸 USD 실현 손익", "🇰🇷 KRW 실현 손익"])

        # ===== USD 탭 =====
        with tab1:
            if not usd_realized_df.empty:
                # USD 실현손익 차트
                fig_usd_pnl = go.Figure()
                
                # 일별 손익 바 차트
                colors = ['green' if x >= 0 else 'red' for x in usd_realized_df['realized_pnl']]
                fig_usd_pnl.add_trace(go.Bar(
                    x=usd_realized_df['date'],
                    y=usd_realized_df['realized_pnl'],
                    name='일별 실현손익',
                    marker_color=colors
                ))
                
                # 누적 손익 라인
                fig_usd_pnl.add_trace(go.Scatter(
                    x=usd_realized_df['date'],
                    y=usd_realized_df['cumulative_pnl'],
                    name='누적 실현손익',
                    yaxis='y2',
                    line=dict(color='blue', width=2)
                ))
                
                fig_usd_pnl.update_layout(
                    title="USD 실현 손익 추이",
                    xaxis_title="날짜",
                    yaxis_title="일별 실현손익 ($)",
                    yaxis2=dict(
                        title="누적 실현손익 ($)",
                        overlaying='y',
                        side='right'
                    ),
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig_usd_pnl, use_container_width=True)
                
                # 통계
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("총 실현손익", f"${usd_realized_df['cumulative_pnl'].iloc[-1]:,.2f}")
                with col2:
                    st.metric("평균 일일 손익", f"${usd_realized_df['realized_pnl'].mean():,.2f}")
                with col3:
                    winning_days = len(usd_realized_df[usd_realized_df['realized_pnl'] > 0])
                    total_days = len(usd_realized_df)
                    st.metric("승률", f"{winning_days / total_days * 100:.1f}%")
                
                # 상세 테이블
                with st.expander("📋 USD 실현 손익 상세"):
                    display_df = usd_realized_df.copy()
                    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
                    display_df['realized_pnl'] = display_df['realized_pnl'].apply(lambda x: f"${x:,.2f}")
                    display_df['cumulative_pnl'] = display_df['cumulative_pnl'].apply(lambda x: f"${x:,.2f}")
                    display_df.columns = ['날짜', '일별 실현손익', '누적 실현손익']
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("💡 USD 실현 손익 내역이 없습니다. 매도 거래를 추가하면 여기에 표시됩니다.")
                
                # KRW 데이터가 있으면 안내 메시지
                if not krw_realized_df.empty:
                    st.success("✅ KRW 실현 손익은 **'KRW 실현 손익' 탭**에서 확인하세요!")

        # ===== KRW 탭 =====
        with tab2:
            if not krw_realized_df.empty:
                # KRW 실현손익 차트
                fig_krw_pnl = go.Figure()
                
                # 일별 손익 바 차트
                colors = ['green' if x >= 0 else 'red' for x in krw_realized_df['realized_pnl']]
                fig_krw_pnl.add_trace(go.Bar(
                    x=krw_realized_df['date'],
                    y=krw_realized_df['realized_pnl'],
                    name='일별 실현손익',
                    marker_color=colors
                ))
                
                # 누적 손익 라인
                fig_krw_pnl.add_trace(go.Scatter(
                    x=krw_realized_df['date'],
                    y=krw_realized_df['cumulative_pnl'],
                    name='누적 실현손익',
                    yaxis='y2',
                    line=dict(color='blue', width=2)
                ))
                
                fig_krw_pnl.update_layout(
                    title="KRW 실현 손익 추이",
                    xaxis_title="날짜",
                    yaxis_title="일별 실현손익 (₩)",
                    yaxis2=dict(
                        title="누적 실현손익 (₩)",
                        overlaying='y',
                        side='right'
                    ),
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig_krw_pnl, use_container_width=True)
                
                # 통계
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("총 실현손익", f"₩{krw_realized_df['cumulative_pnl'].iloc[-1]:,.0f}")
                with col2:
                    st.metric("평균 일일 손익", f"₩{krw_realized_df['realized_pnl'].mean():,.0f}")
                with col3:
                    winning_days = len(krw_realized_df[krw_realized_df['realized_pnl'] > 0])
                    total_days = len(krw_realized_df)
                    st.metric("승률", f"{winning_days / total_days * 100:.1f}%")
                
                # 상세 테이블
                with st.expander("📋 KRW 실현 손익 상세"):
                    display_df = krw_realized_df.copy()
                    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
                    display_df['realized_pnl'] = display_df['realized_pnl'].apply(lambda x: f"₩{x:,.0f}")
                    display_df['cumulative_pnl'] = display_df['cumulative_pnl'].apply(lambda x: f"₩{x:,.0f}")
                    display_df.columns = ['날짜', '일별 실현손익', '누적 실현손익']
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("💡 KRW 실현 손익 내역이 없습니다. 한국 주식/업비트 매도 거래를 추가하면 여기에 표시됩니다.")
                
                # USD 데이터가 있으면 안내 메시지
                if not usd_realized_df.empty:
                    st.success("✅ USD 실현 손익은 **'USD 실현 손익' 탭**에서 확인하세요!")

        # 데이터가 아예 없으면 전체 안내
        if usd_realized_df.empty and krw_realized_df.empty:
            st.warning("⚠️ 아직 청산된 포지션이 없습니다. 매도 거래를 입력하면 실현 손익이 여기에 표시됩니다.")
        
        st.markdown("---")
        
        # 통화별 자산 분포
        st.subheader("💵 통화별 자산 분포")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "USD 투자금액",
                f"${portfolio_summary['total_value_usd']:,.2f}",
                f"현금: ${cash_balance_usd:,.2f}"
            )
        
        with col2:
            st.metric(
                "KRW 투자금액",
                f"₩{portfolio_summary['total_value_krw']:,.0f}",
                f"현금: ₩{cash_balance_krw:,.0f}"
            )
        
        with col3:
            usd_ratio = (portfolio_summary['total_value_usd'] / portfolio_summary['total_value'] * 100) if portfolio_summary['total_value'] > 0 else 0
            krw_ratio = 100 - usd_ratio
            st.metric(
                "USD 비중",
                f"{usd_ratio:.1f}%",
                f"KRW: {krw_ratio:.1f}%"
            )
        
        with col4:
            total_allocated_usd_converted = total_allocated_usd + (total_allocated_krw / st.session_state.exchange_rate)
            st.metric(
                "총 할당 자본",
                f"${total_allocated_usd_converted:,.2f}",
                f"USD ${total_allocated_usd:,.0f} | KRW ₩{total_allocated_krw:,.0f}"
            )
        
        st.markdown("---")
        
        # 전략별 자본 할당 현황 (통화별 그룹화)
        st.subheader("💰 전략별 자본 할당 현황")
        
        # USD 전략
        usd_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'USD'}
        
        if usd_strategies:
            st.markdown("#### 🇺🇸 USD 기반 전략")
            capital_data_usd = []
            
            for strategy_id, strategy in usd_strategies.items():
                allocated = strategy.get('allocated_capital', 0)
                used_capital = portfolio_summary['strategy_values'][strategy_id]['cost_usd']
                available = allocated - used_capital
                usage_pct = (used_capital / allocated * 100) if allocated > 0 else 0
                
                capital_data_usd.append({
                    '전략': strategy['name'],
                    '할당금액': f"${allocated:,.2f}",
                    '투자금액': f"${used_capital:,.2f}",
                    '현금': f"${available:,.2f}",
                    '투자비율(%)': f"{usage_pct:.1f}%"
                })
            
            df_capital_usd = pd.DataFrame(capital_data_usd)
            st.dataframe(df_capital_usd, use_container_width=True, hide_index=True)
        
        # KRW 전략
        krw_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'KRW'}
        
        if krw_strategies:
            st.markdown("#### 🇰🇷 KRW 기반 전략")
            capital_data_krw = []
            
            for strategy_id, strategy in krw_strategies.items():
                allocated = strategy.get('allocated_capital', 0)
                used_capital = portfolio_summary['strategy_values'][strategy_id]['cost_krw']
                available = allocated - used_capital
                usage_pct = (used_capital / allocated * 100) if allocated > 0 else 0
                
                capital_data_krw.append({
                    '전략': strategy['name'],
                    '할당금액': f"₩{allocated:,.0f}",
                    '투자금액': f"₩{used_capital:,.0f}",
                    '현금': f"₩{available:,.0f}",
                    '투자비율(%)': f"{usage_pct:.1f}%"
                })
            
            df_capital_krw = pd.DataFrame(capital_data_krw)
            st.dataframe(df_capital_krw, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # 전략별 성과
        st.subheader("📊 전략별 성과")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 전략별 수익률 바 차트
            strategy_data = []
            for strategy_id, strategy_info in portfolio_summary['strategy_values'].items():
                if strategy_info['cost'] > 0:
                    strategy_name = st.session_state.portfolio['strategies'][strategy_id]['name']
                    base_currency = st.session_state.portfolio['strategies'][strategy_id].get('base_currency', 'USD')
                    
                    strategy_data.append({
                        '전략': f"{strategy_name} ({base_currency})",
                        '수익률(%)': strategy_info['pnl_pct'],
                        '평가손익': strategy_info['pnl']
                    })
            
            if strategy_data:
                df_strategy = pd.DataFrame(strategy_data)
                fig = px.bar(
                    df_strategy,
                    x='전략',
                    y='수익률(%)',
                    color='수익률(%)',
                    color_continuous_scale=['red', 'yellow', 'green'],
                    title="전략별 수익률"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("투자된 전략이 없습니다")
        
        with col2:
            # 자산 배분 파이 차트 (현금 포함)
            pie_data = []
            
            # 각 전략의 평가금액 추가
            for strategy_id, strategy_info in portfolio_summary['strategy_values'].items():
                if strategy_info['value'] > 0:
                    strategy_name = st.session_state.portfolio['strategies'][strategy_id]['name']
                    pie_data.append({
                        '항목': strategy_name,
                        '금액': strategy_info['value']
                    })
            
            # USD 현금 추가
            if cash_balance_usd > 0:
                pie_data.append({
                    '항목': '💵 USD 현금',
                    '금액': cash_balance_usd
                })
            
            # KRW 현금 추가 (USD로 환산)
            if cash_balance_krw > 0:
                pie_data.append({
                    '항목': '💵 KRW 현금',
                    '금액': cash_balance_krw / st.session_state.exchange_rate
                })
            
            if pie_data:
                df_pie = pd.DataFrame(pie_data)
                fig = px.pie(
                    df_pie,
                    values='금액',
                    names='항목',
                    title="자산 배분 (USD 기준)"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("자산이 없습니다")
        
        # 보유 종목 리스트        
        st.subheader("📋 전체 보유 종목")

        holdings_data = []
        for strategy_id, strategy_data in st.session_state.portfolio['strategies'].items():
            strategy_name = strategy_data['name']
            base_currency = strategy_data.get('base_currency', 'USD')
            
            for ticker, position in strategy_data['positions'].items():
                # ★ 중요: current_shares > 0인 것만 표시
                if position['current_shares'] > 0:
                    current_price = st.session_state.current_prices.get(ticker, 0.0)
                    pnl, pnl_pct = calculate_unrealized_pnl(
                        position['avg_price'],
                        current_price,
                        position['current_shares']
                    )
                    
                    currency = position.get('currency', 'USD')
                    ticker_type = detect_ticker_type(ticker)
                    
                    # ... (나머지 코드 동일)

                    
                    # 티커 유형 아이콘
                    if ticker_type == 'upbit':
                        ticker_display = f"🪙 {ticker}"
                    elif ticker_type == 'korean_stock':
                        ticker_display = f"🇰🇷 {ticker}"
                    else:
                        ticker_display = f"🇺🇸 {ticker}"
                    
                    if currency == 'KRW':
                        holdings_data.append({
                            '전략': f"{strategy_name} (KRW)",
                            '티커': ticker_display,
                            '보유수량': position['current_shares'],
                            '평균단가': f"₩{position['avg_price']:,.0f}",
                            '현재가': f"₩{current_price:,.0f}",
                            '평가금액': f"₩{current_price * position['current_shares']:,.0f}",
                            '평가손익': f"₩{pnl:,.0f}",
                            '수익률(%)': f"{pnl_pct:.2f}%"
                        })
                    else:
                        holdings_data.append({
                            '전략': f"{strategy_name} (USD)",
                            '티커': ticker_display,
                            '보유수량': position['current_shares'],
                            '평균단가': f"${position['avg_price']:,.2f}",
                            '현재가': f"${current_price:,.2f}",
                            '평가금액': f"${current_price * position['current_shares']:,.2f}",
                            '평가손익': f"${pnl:,.2f}",
                            '수익률(%)': f"{pnl_pct:.2f}%"
                        })
        
        if holdings_data:
            df_holdings = pd.DataFrame(holdings_data)
            st.dataframe(df_holdings, use_container_width=True, hide_index=True)
        else:
            st.info("보유 종목이 없습니다")

elif menu == "➕ 거래 입력":
    st.header("거래 입력")
    
    # 전략 선택
    strategy_options = {
        f"{st.session_state.portfolio['strategies'][sid]['name']} ({st.session_state.portfolio['strategies'][sid].get('base_currency', 'USD')})": sid
        for sid in st.session_state.portfolio['strategies'].keys()
    }
    
    selected_strategy_name = st.selectbox("전략 선택", list(strategy_options.keys()), key="input_strategy_select")
    selected_strategy_id = strategy_options[selected_strategy_name]
    selected_strategy = st.session_state.portfolio['strategies'][selected_strategy_id]
    strategy_currency = selected_strategy.get('base_currency', 'USD')
    
    # 전략의 base_currency 표시
    st.info(f"ℹ️ 선택된 전략의 기준 통화: **{strategy_currency}**")
    
    # 거래 유형
    trans_type = st.radio("거래 유형", ["매수", "매도"], horizontal=True, key="input_trans_type")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 종목 정보")
        ticker_input = st.text_input(
            "티커", 
            placeholder="US: AAPL | KR: 005930.KS | 업비트: KRW-BTC",
            help="미국주식: AAPL, TSLA / 한국주식: 005930.KS, 035720.KQ / 업비트: KRW-BTC, KRW-ETH",
            key="input_ticker"
        ).upper()
        
        # 티커 유형 자동 감지 및 통화 표시
        if ticker_input:
            ticker_type = detect_ticker_type(ticker_input)
            auto_currency = get_currency_for_ticker(ticker_input)
            
            if ticker_type == 'upbit':
                st.success(f"🪙 업비트 암호화폐 감지 - 통화: {auto_currency}")
            elif ticker_type == 'korean_stock':
                st.success(f"🇰🇷 한국 주식 감지 - 통화: {auto_currency}")
            else:
                st.success(f"🇺🇸 미국 주식 감지 - 통화: {auto_currency}")
            
            # 전략 통화와 불일치 경고
            if auto_currency != strategy_currency:
                st.warning(f"⚠️ 주의: 선택한 전략의 기준 통화({strategy_currency})와 종목의 통화({auto_currency})가 다릅니다!")
        
        quantity = st.number_input("수량", min_value=0.00000001, value=1.0, format="%.8f", key="input_quantity")
        price = st.number_input(
            f"가격 ({auto_currency if ticker_input else 'USD'})", 
            min_value=0.0, 
            value=0.0, 
            format="%.2f",
            key="input_price"
        )
    
    with col2:
        st.markdown("#### 거래 상세")
        date = st.date_input("거래 날짜", value=datetime.now(), key="input_date")
        fee_pct = st.number_input(
            "수수료 (%)", 
            min_value=0.0, 
            max_value=100.0,
            value=st.session_state.portfolio['portfolio_metadata'].get('default_fee_pct', 0.2),
            format="%.3f",
            help="거래 금액 대비 수수료 비율 (예: 0.2%)",
            key="input_fee"
        )
        
        # 예상 수수료 금액 표시
        if price > 0 and quantity > 0:
            transaction_amount = price * quantity
            estimated_fee = transaction_amount * (fee_pct / 100)
            st.metric(
                "예상 수수료",
                f"{'$' if (ticker_input and get_currency_for_ticker(ticker_input) == 'USD') or not ticker_input else '₩'}{estimated_fee:,.2f}"
            )
            st.metric(
                "총 거래금액",
                f"{'$' if (ticker_input and get_currency_for_ticker(ticker_input) == 'USD') or not ticker_input else '₩'}{transaction_amount:,.2f}"
            )
    
    st.markdown("---")
    
    # 거래 요약
    if ticker_input and price > 0 and quantity > 0:
        st.subheader("📋 거래 요약")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**전략**: {selected_strategy['name']}")
            st.write(f"**티커**: {ticker_input}")
            st.write(f"**날짜**: {date}")
        
        with col2:
            st.write(f"**유형**: {'🔴 매도' if trans_type == '매도' else '🔵 매수'}")
            st.write(f"**수량**: {quantity:,.8f}")
            st.write(f"**가격**: {auto_currency if ticker_input else 'USD'} {price:,.2f}")
        
        with col3:
            transaction_amount = price * quantity
            estimated_fee = transaction_amount * (fee_pct / 100)
            total = transaction_amount + estimated_fee if trans_type == '매수' else transaction_amount - estimated_fee
            
            st.write(f"**거래금액**: {auto_currency if ticker_input else 'USD'} {transaction_amount:,.2f}")
            st.write(f"**수수료**: {auto_currency if ticker_input else 'USD'} {estimated_fee:,.2f}")
            st.write(f"**{'총 비용' if trans_type == '매수' else '총 수령액'}**: {auto_currency if ticker_input else 'USD'} {total:,.2f}")
    
    # 거래 추가 버튼
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col2:
        if st.button("💾 거래 추가", type="primary", use_container_width=True, key="add_transaction_btn"):
            # 입력 검증
            if not ticker_input:
                st.error("❌ 티커를 입력해주세요!")
            elif price <= 0:
                st.error("❌ 가격은 0보다 커야 합니다!")
            elif quantity <= 0:
                st.error("❌ 수량은 0보다 커야 합니다!")
            else:
                try:
                    # 거래 추가
                    add_transaction(
                        st.session_state.portfolio,
                        selected_strategy_id,
                        ticker_input,
                        "buy" if trans_type == "매수" else "sell",
                        price,
                        quantity,
                        date=date.strftime('%Y-%m-%d'),
                        fee_pct=fee_pct
                    )
                    
                    # 포트폴리오 리로드
                    st.session_state.portfolio = load_portfolio()
                    
                    # 성공 메시지
                    st.success(f"""
                    ✅ **거래가 성공적으로 추가되었습니다!**
                    
                    - 전략: {selected_strategy['name']}
                    - 종목: {ticker_input}
                    - 유형: {'매도' if trans_type == '매도' else '매수'}
                    - 수량: {quantity:,.8f}
                    - 가격: {auto_currency if ticker_input else 'USD'} {price:,.2f}
                    - 날짜: {date.strftime('%Y-%m-%d')}
                    """)
                    
                    # 추가 정보
                    st.info("""
                    💡 **다음 단계**:
                    - 📈 **대시보드**에서 포트폴리오 현황을 확인하세요
                    - 💹 **가격 업데이트**로 최신 시세를 반영하세요
                    - 📝 **거래 관리**에서 방금 추가한 거래를 확인하세요
                    """)
                    
                    # 자동 백업
                    backup_file = create_backup()
                    if backup_file:
                        st.caption(f"💾 백업 생성: {backup_file}")
                    
                    # 폼 초기화를 위한 rerun (3초 후)
                    
                    time.sleep(2)
                    st.rerun()
                    
                except ValueError as e:
                    st.error(f"❌ **거래 추가 실패**: {str(e)}")
                    
                    # 에러 원인 상세 설명
                    if "exceeds current shares" in str(e):
                        st.warning("""
                        ⚠️ **보유 수량 부족**
                        
                        매도하려는 수량이 현재 보유 수량보다 많습니다.
                        
                        **해결 방법**:
                        1. 📈 대시보드에서 현재 보유 수량을 확인하세요
                        2. 매도 수량을 줄이거나, 보유 수량이 맞는지 확인하세요
                        3. 거래 내역이 잘못 입력되었다면 📝 거래 관리에서 수정하세요
                        """)
                
                except Exception as e:
                    st.error(f"❌ **예상치 못한 오류 발생**: {str(e)}")
                    st.warning("문제가 계속되면 ♻️ 백업 복원을 시도해보세요.")
    
    # 현재 보유 포지션 미리보기 (참고용)
    if selected_strategy_id:
        st.markdown("---")
        st.subheader(f"📊 {selected_strategy['name']} - 현재 보유 종목")
        
        positions = selected_strategy.get('positions', {})
        active_positions = {k: v for k, v in positions.items() if v['current_shares'] > 0}
        
        if active_positions:
            preview_data = []
            for ticker, pos in active_positions.items():
                preview_data.append({
                    '티커': ticker,
                    '보유수량': f"{pos['current_shares']:,.8f}",
                    '평균단가': f"{pos.get('currency', 'USD')} {pos['avg_price']:,.2f}",
                    '통화': pos.get('currency', 'USD')
                })
            
            preview_df = pd.DataFrame(preview_data)
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ 현재 이 전략에는 보유 중인 종목이 없습니다.")

elif menu == "📋 거래 내역":
    st.header("거래 내역")
    
    tab1, tab2 = st.tabs(["현재 포지션", "청산 포지션"])
    
    with tab1:
        st.subheader("현재 보유 포지션")
        
        for strategy_id, strategy_data in st.session_state.portfolio['strategies'].items():
            if strategy_data['positions']:
                base_currency = strategy_data.get('base_currency', 'USD')
                st.markdown(f"### {strategy_data['name']} ({base_currency})")
                
                for ticker, position in strategy_data['positions'].items():
                    if position['current_shares'] > 0:
                        currency = position.get('currency', 'USD')
                        ticker_type = detect_ticker_type(ticker)
                        
                        # 티커 표시
                        if ticker_type == 'upbit':
                            ticker_display = f"🪙 {ticker}"
                        elif ticker_type == 'korean_stock':
                            ticker_display = f"🇰🇷 {ticker}"
                        else:
                            ticker_display = f"🇺🇸 {ticker}"
                        
                        with st.expander(f"📌 {ticker_display} - {position['current_shares']} 보유"):
                            if currency == 'KRW':
                                st.write(f"**평균 매수가:** ₩{position['avg_price']:,.0f}")
                            else:
                                st.write(f"**평균 매수가:** ${position['avg_price']:,.2f}")
                            
                            # 거래 내역 테이블
                            trans_df = pd.DataFrame(position['transactions'])
                            trans_df['거래금액'] = trans_df['price'] * trans_df['quantity']
                            trans_df['수수료(%)'] = trans_df['fee_pct']
                            
                            if currency == 'KRW':
                                trans_df['수수료'] = trans_df['fee_amount'].apply(lambda x: f"₩{x:,.0f}")
                                trans_df['price'] = trans_df['price'].apply(lambda x: f"₩{x:,.0f}")
                                trans_df['거래금액'] = trans_df['거래금액'].apply(lambda x: f"₩{x:,.0f}")
                            else:
                                trans_df['수수료'] = trans_df['fee_amount'].apply(lambda x: f"${x:.2f}")
                                trans_df['price'] = trans_df['price'].apply(lambda x: f"${x:.2f}")
                                trans_df['거래금액'] = trans_df['거래금액'].apply(lambda x: f"${x:.2f}")
                            
                            display_df = trans_df[['date', 'type', 'quantity', 'price', '거래금액', '수수료(%)', '수수료']]
                            st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("청산된 포지션")
        
        if st.session_state.portfolio['closed_positions']:
            closed_data = []
            for cp in st.session_state.portfolio['closed_positions']:
                currency = cp.get('currency', 'USD')
                
                if currency == 'KRW':
                    closed_data.append({
                        '티커': cp['ticker'],
                        '전략': cp['strategy'],
                        '통화': currency,
                        '매수일': cp['buy_date'],
                        '매도일': cp['sell_date'],
                        '수량': cp['quantity'],
                        '평균매수가': f"₩{cp['avg_buy_price']:,.0f}",
                        '평균매도가': f"₩{cp['avg_sell_price']:,.0f}",
                        '실현손익': f"₩{cp['realized_pnl']:,.0f}",
                        '수익률(%)': f"{cp['return_pct']:.2f}%"
                    })
                else:
                    closed_data.append({
                        '티커': cp['ticker'],
                        '전략': cp['strategy'],
                        '통화': currency,
                        '매수일': cp['buy_date'],
                        '매도일': cp['sell_date'],
                        '수량': cp['quantity'],
                        '평균매수가': f"${cp['avg_buy_price']:.2f}",
                        '평균매도가': f"${cp['avg_sell_price']:.2f}",
                        '실현손익': f"${cp['realized_pnl']:.2f}",
                        '수익률(%)': f"{cp['return_pct']:.2f}%"
                    })
            
            closed_df = pd.DataFrame(closed_data)
            st.dataframe(closed_df, use_container_width=True, hide_index=True)
        else:
            st.info("청산된 포지션이 없습니다")

# ========== 거래 관리 메뉴 ==========
elif menu == "📝 거래 관리":
    st.header("📝 거래 관리")
    
    tab1, tab2 = st.tabs(["📋 거래 내역 조회/삭제", "♻️ 백업 복원"])
    
    # ===== 탭1: 거래 내역 조회/삭제 =====
    with tab1:
        st.subheader("전체 거래 내역")
        
        all_txs = get_all_transactions_with_metadata(st.session_state.portfolio)
        
        if not all_txs:
            st.info("거래 내역이 없습니다.")
        else:
            st.write(f"**총 {len(all_txs)}건의 거래**")
            
            # 필터링 옵션
            col1, col2, col3 = st.columns(3)
            
            with col1:
                filter_strategy = st.selectbox(
                    "전략 필터",
                    ["전체"] + list(set([tx['strategy_name'] for tx in all_txs])),
                    key="filter_strategy"
                )
            
            with col2:
                filter_type = st.selectbox(
                    "거래 유형 필터",
                    ["전체", "매수", "매도"],
                    key="filter_type"
                )
            
            with col3:
                filter_currency = st.selectbox(
                    "통화 필터",
                    ["전체", "USD", "KRW"],
                    key="filter_currency"
                )
            
            # 필터링 적용
            filtered_txs = all_txs.copy()
            
            if filter_strategy != "전체":
                filtered_txs = [tx for tx in filtered_txs if tx['strategy_name'] == filter_strategy]
            
            if filter_type != "전체":
                type_map = {"매수": "buy", "매도": "sell"}
                filtered_txs = [tx for tx in filtered_txs if tx['type'] == type_map[filter_type]]
            
            if filter_currency != "전체":
                filtered_txs = [tx for tx in filtered_txs if tx['currency'] == filter_currency]
            
            st.write(f"**필터링 결과: {len(filtered_txs)}건**")
            
            # 거래 내역 테이블
            for idx, tx in enumerate(filtered_txs):
                with st.expander(
                    f"[{tx['date']}] {tx['strategy_name']} | {tx['ticker']} | "
                    f"{'🔴 매도' if tx['type'] == 'sell' else '🔵 매수'} | "
                    f"{tx['quantity']} 주 @ "
                    f"{'$' if tx['currency'] == 'USD' else '₩'}{tx['price']:,.2f}"
                ):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**전략**: {tx['strategy_name']}")
                        st.write(f"**티커**: {tx['ticker']}")
                        st.write(f"**날짜**: {tx['date']}")
                        st.write(f"**유형**: {'매도' if tx['type'] == 'sell' else '매수'}")
                        st.write(f"**수량**: {tx['quantity']}")
                        st.write(f"**가격**: {tx['currency']} {tx['price']:,.2f}")
                        st.write(f"**수수료**: {tx['currency']} {tx['fee_amount']:,.2f}")
                        st.write(f"**통화**: {tx['currency']}")
                    
                    with col2:
                        if st.button(
                            "🗑️ 삭제",
                            key=f"delete_tx_{tx['strategy_id']}_{tx['ticker']}_{tx['transaction_index']}_{idx}",
                            type="secondary"
                        ):
                            # 삭제 확인
                            st.session_state[f'confirm_delete_{idx}'] = True
                        
                        # 삭제 확인 상태면 재확인 버튼 표시
                        if st.session_state.get(f'confirm_delete_{idx}', False):
                            st.warning("⚠️ 정말 삭제하시겠습니까?")
                            
                            col_a, col_b = st.columns(2)
                            
                            with col_a:
                                if st.button("✅ 예", key=f"confirm_yes_{idx}"):
                                    success = delete_transaction(
                                        st.session_state.portfolio,
                                        tx['strategy_id'],
                                        tx['ticker'],
                                        tx['transaction_index']
                                    )
                                    
                                    if success:
                                        st.session_state.portfolio = load_portfolio()
                                        st.success("✅ 거래가 삭제되었습니다!")
                                        st.session_state[f'confirm_delete_{idx}'] = False
                                        st.rerun()
                                    else:
                                        st.error("❌ 삭제 실패")
                            
                            with col_b:
                                if st.button("❌ 아니오", key=f"confirm_no_{idx}"):
                                    st.session_state[f'confirm_delete_{idx}'] = False
                                    st.rerun()
    
    # ===== 탭2: 백업 복원 =====
    with tab2:
        st.subheader("♻️ 백업에서 복원")
        
        st.info("💡 거래 삭제 시 자동으로 백업이 생성됩니다. 잘못 삭제한 경우 여기서 복원할 수 있습니다.")
        
        backups = get_backup_files()
        
        if not backups:
            st.warning("백업 파일이 없습니다.")
        else:
            st.write(f"**총 {len(backups)}개의 백업**")
            
            for filename, filepath, mtime in backups[:20]:  # 최근 20개만 표시
                with st.expander(f"📦 {filename} (생성: {mtime.strftime('%Y-%m-%d %H:%M:%S')})"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**파일명**: {filename}")
                        st.write(f"**경로**: {filepath}")
                        st.write(f"**생성 시간**: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    with col2:
                        if st.button("♻️ 복원", key=f"restore_{filename}"):
                            st.session_state[f'confirm_restore_{filename}'] = True
                        
                        if st.session_state.get(f'confirm_restore_{filename}', False):
                            st.warning("⚠️ 현재 데이터가 덮어쓰여집니다!")
                            
                            col_a, col_b = st.columns(2)
                            
                            with col_a:
                                if st.button("✅ 복원 실행", key=f"restore_yes_{filename}"):
                                    if restore_from_backup(filepath):
                                        st.session_state.portfolio = load_portfolio()
                                        st.success("✅ 복원 완료!")
                                        st.session_state[f'confirm_restore_{filename}'] = False
                                        st.rerun()
                                    else:
                                        st.error("❌ 복원 실패")
                            
                            with col_b:
                                if st.button("❌ 취소", key=f"restore_no_{filename}"):
                                    st.session_state[f'confirm_restore_{filename}'] = False
                                    st.rerun()
        
        # 수동 백업 생성
        st.markdown("---")
        st.subheader("💾 수동 백업 생성")
        
        if st.button("💾 지금 백업 생성", type="primary"):
            backup_file = create_backup()
            if backup_file:
                st.success(f"✅ 백업 생성 완료: {backup_file}")
            else:
                st.error("❌ 백업 생성 실패")


elif menu == "⚙️ 전략 관리":
    st.header("전략 관리")
    
    tab1, tab2, tab3 = st.tabs(["전략 목록", "자본 할당", "전략 추가/삭제"])
    
    with tab1:
        st.subheader("📁 전체 전략 목록")
        
        # USD 전략과 KRW 전략 분리 표시
        usd_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'USD'}
        
        krw_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'KRW'}
        
        if usd_strategies:
            st.markdown("### 🇺🇸 USD 기반 전략")
            for strategy_id, strategy_data in usd_strategies.items():
                with st.expander(f"📁 {strategy_data['name']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**전략 ID:** {strategy_id}")
                        st.write(f"**설명:** {strategy_data['description']}")
                        st.write(f"**기준 통화:** USD 🇺🇸")
                    
                    with col2:
                        st.write(f"**할당 자본:** ${strategy_data.get('allocated_capital', 0):,.2f}")
                        st.write(f"**보유 종목 수:** {len(strategy_data['positions'])}")
                        
                        # 현재 투자금액 계산
                        if st.session_state.current_prices:
                            portfolio_summary = calculate_portfolio_value(
                                st.session_state.portfolio,
                                st.session_state.current_prices,
                                st.session_state.exchange_rate
                            )
                            used_capital = portfolio_summary['strategy_values'][strategy_id]['cost_usd']
                            st.write(f"**투자 중인 금액:** ${used_capital:,.2f}")
        
        if krw_strategies:
            st.markdown("### 🇰🇷 KRW 기반 전략")
            for strategy_id, strategy_data in krw_strategies.items():
                with st.expander(f"📁 {strategy_data['name']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**전략 ID:** {strategy_id}")
                        st.write(f"**설명:** {strategy_data['description']}")
                        st.write(f"**기준 통화:** KRW 🇰🇷")
                    
                    with col2:
                        st.write(f"**할당 자본:** ₩{strategy_data.get('allocated_capital', 0):,.0f}")
                        st.write(f"**보유 종목 수:** {len(strategy_data['positions'])}")
                        
                        # 현재 투자금액 계산
                        if st.session_state.current_prices:
                            portfolio_summary = calculate_portfolio_value(
                                st.session_state.portfolio,
                                st.session_state.current_prices,
                                st.session_state.exchange_rate
                            )
                            used_capital = portfolio_summary['strategy_values'][strategy_id]['cost_krw']
                            st.write(f"**투자 중인 금액:** ₩{used_capital:,.0f}")
    
    with tab2:
        st.subheader("💰 전략별 자본 할당")
        st.caption("각 전략에 할당할 초기 자본을 해당 전략의 기준 통화로 설정하세요")
        
        # USD 전략
        usd_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'USD'}
        
        if usd_strategies:
            st.markdown("### 🇺🇸 USD 기반 전략")
            
            for strategy_id, strategy_data in usd_strategies.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**{strategy_data['name']}**")
                    st.caption(strategy_data['description'])
                
                with col2:
                    current_capital = strategy_data.get('allocated_capital', 0)
                    new_capital = st.number_input(
                        "할당 금액 (USD)",
                        min_value=0.0,
                        value=float(current_capital),
                        step=100.0,
                        key=f"capital_usd_{strategy_id}",
                        label_visibility="collapsed"
                    )
                    st.caption(f"≈ ₩{new_capital * st.session_state.exchange_rate:,.0f}")
                
                with col3:
                    if new_capital != current_capital:
                        if st.button(f"💾", key=f"save_usd_{strategy_id}", use_container_width=True, help="저장"):
                            update_strategy_capital(st.session_state.portfolio, strategy_id, new_capital)
                            st.session_state.portfolio = load_portfolio()
                            st.success(f"✅ 업데이트됨")
                            st.rerun()
                
                st.markdown("---")
        
        # KRW 전략
        krw_strategies = {k: v for k, v in st.session_state.portfolio['strategies'].items() 
                          if v.get('base_currency', 'USD') == 'KRW'}
        
        if krw_strategies:
            st.markdown("### 🇰🇷 KRW 기반 전략")
            
            for strategy_id, strategy_data in krw_strategies.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**{strategy_data['name']}**")
                    st.caption(strategy_data['description'])
                
                with col2:
                    current_capital = strategy_data.get('allocated_capital', 0)
                    new_capital = st.number_input(
                        "할당 금액 (KRW)",
                        min_value=0.0,
                        value=float(current_capital),
                        step=10000.0,
                        key=f"capital_krw_{strategy_id}",
                        label_visibility="collapsed",
                        format="%.0f"
                    )
                    st.caption(f"≈ ${new_capital / st.session_state.exchange_rate:,.2f}")
                
                with col3:
                    if new_capital != current_capital:
                        if st.button(f"💾", key=f"save_krw_{strategy_id}", use_container_width=True, help="저장"):
                            update_strategy_capital(st.session_state.portfolio, strategy_id, new_capital)
                            st.session_state.portfolio = load_portfolio()
                            st.success(f"✅ 업데이트됨")
                            st.rerun()
                
                st.markdown("---")
        
        # 총 할당 금액 표시
        total_allocated_usd = sum([s.get('allocated_capital', 0) for s in usd_strategies.values()])
        total_allocated_krw = sum([s.get('allocated_capital', 0) for s in krw_strategies.values()])
        total_allocated_usd_converted = total_allocated_usd + (total_allocated_krw / st.session_state.exchange_rate)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("총 USD 할당", f"${total_allocated_usd:,.2f}")
        with col2:
            st.metric("총 KRW 할당", f"₩{total_allocated_krw:,.0f}")
        with col3:
            st.metric("총 할당 (USD 환산)", f"${total_allocated_usd_converted:,.2f}")
    
    with tab3:
        st.subheader("➕ 새 전략 추가")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_strategy_id = st.text_input(
                "전략 ID (영문)", 
                placeholder="예: crypto_swing",
                help="공백 없이 영문과 언더스코어(_)만 사용"
            )
            new_strategy_name = st.text_input(
                "전략 이름", 
                placeholder="예: 암호화폐 스윙"
            )
            new_strategy_desc = st.text_area(
                "설명", 
                placeholder="전략 설명 입력"
            )
        
        with col2:
            # 기준 통화 선택
            base_currency = st.radio(
                "기준 통화 선택",
                ["USD 🇺🇸", "KRW 🇰🇷"],
                horizontal=True,
                help="이 전략에서 거래할 주요 통화를 선택하세요"
            )
            
            selected_currency = "USD" if "USD" in base_currency else "KRW"
            
            # 통화에 따라 입력 필드 변경
            if selected_currency == "USD":
                new_allocated_capital = st.number_input(
                    "초기 할당 자본 (USD)", 
                    min_value=0.0, 
                    value=0.0, 
                    step=100.0,
                    format="%.2f"
                )
                st.caption(f"≈ ₩{new_allocated_capital * st.session_state.exchange_rate:,.0f}")
            else:
                new_allocated_capital = st.number_input(
                    "초기 할당 자본 (KRW)", 
                    min_value=0.0, 
                    value=0.0, 
                    step=10000.0,
                    format="%.0f"
                )
                st.caption(f"≈ ${new_allocated_capital / st.session_state.exchange_rate:,.2f}")
            
            st.info(f"ℹ️ 이 전략은 **{selected_currency}** 기반으로 생성됩니다")
        
        if st.button("✅ 전략 추가", type="primary", use_container_width=True):
            if new_strategy_id and new_strategy_name:
                # 전략 ID 중복 체크
                if new_strategy_id in st.session_state.portfolio['strategies']:
                    st.error("❌ 이미 존재하는 전략 ID입니다")
                else:
                    add_strategy(
                        st.session_state.portfolio, 
                        new_strategy_id, 
                        new_strategy_name, 
                        new_strategy_desc,
                        selected_currency,
                        new_allocated_capital
                    )
                    st.session_state.portfolio = load_portfolio()
                    st.success(f"✅ '{new_strategy_name}' 전략이 추가되었습니다 ({selected_currency} 기반)")
                    st.rerun()
            else:
                st.error("전략 ID와 이름을 모두 입력하세요")
        
        st.markdown("---")
        
        st.subheader("✏️ 전략 수정")
        
        # 수정할 전략 선택
        edit_strategy_options = {
            f"{st.session_state.portfolio['strategies'][sid]['name']} ({st.session_state.portfolio['strategies'][sid].get('base_currency', 'USD')})": sid
            for sid in st.session_state.portfolio['strategies'].keys()
        }
        
        edit_strategy_name = st.selectbox("수정할 전략", list(edit_strategy_options.keys()), key="edit_select")
        edit_strategy_id = edit_strategy_options[edit_strategy_name]
        edit_strategy = st.session_state.portfolio['strategies'][edit_strategy_id]
        
        col1, col2 = st.columns(2)
        
        with col1:
            edit_name = st.text_input("새 이름", value=edit_strategy['name'], key="edit_name")
            edit_desc = st.text_area("새 설명", value=edit_strategy['description'], key="edit_desc")
        
        with col2:
            current_currency = edit_strategy.get('base_currency', 'USD')
            st.info(f"현재 기준 통화: **{current_currency}**")
            
            # 통화 변경 (포지션이 없을 때만 가능)
            if len(edit_strategy['positions']) == 0:
                new_currency_option = st.radio(
                    "기준 통화 변경",
                    ["USD 🇺🇸", "KRW 🇰🇷"],
                    index=0 if current_currency == "USD" else 1,
                    horizontal=True,
                    key="edit_currency"
                )
                new_currency = "USD" if "USD" in new_currency_option else "KRW"
            else:
                st.warning("⚠️ 보유 종목이 있어 통화를 변경할 수 없습니다")
                new_currency = current_currency
        
        if st.button("💾 전략 정보 저장", key="save_edit"):
            update_strategy_info(
                st.session_state.portfolio,
                edit_strategy_id,
                edit_name,
                edit_desc,
                new_currency
            )
            st.session_state.portfolio = load_portfolio()
            st.success(f"✅ '{edit_name}' 전략 정보가 업데이트되었습니다")
            st.rerun()
        
        st.markdown("---")
        
        st.subheader("🗑️ 전략 삭제")
        
        delete_strategy_options = {
            f"{st.session_state.portfolio['strategies'][sid]['name']} ({st.session_state.portfolio['strategies'][sid].get('base_currency', 'USD')})": sid
            for sid in st.session_state.portfolio['strategies'].keys()
        }
        
        delete_strategy_name = st.selectbox("삭제할 전략", list(delete_strategy_options.keys()), key="delete_select")
        delete_strategy_id = delete_strategy_options[delete_strategy_name]
        
        # 삭제 전 확인 정보
        delete_strategy = st.session_state.portfolio['strategies'][delete_strategy_id]
        st.warning(f"⚠️ **{delete_strategy['name']}** 전략을 삭제하시겠습니까?")
        st.write(f"- 보유 종목 수: {len(delete_strategy['positions'])}")
        
        if st.button("⚠️ 전략 삭제", type="secondary"):
            if delete_strategy(st.session_state.portfolio, delete_strategy_id):
                st.session_state.portfolio = load_portfolio()
                st.success(f"✅ '{delete_strategy_name}' 전략이 삭제되었습니다")
                st.rerun()
            else:
                st.error("❌ 보유 종목이 있는 전략은 삭제할 수 없습니다")

elif menu == "💾 데이터 관리":
    st.header("데이터 관리")
    
    tab1, tab2 = st.tabs(["데이터 내보내기", "백업 관리"])
    
    with tab1:
        st.subheader("📥 CSV 내보내기")
        
        if st.button("📊 현재 포트폴리오 내보내기", use_container_width=True):
            if st.session_state.current_prices:
                filename = export_to_csv(
                    st.session_state.portfolio,
                    st.session_state.current_prices,
                    st.session_state.exchange_rate,
                    f"portfolio_{datetime.now().strftime('%Y%m%d')}.csv"
                )
                st.success(f"✅ 파일 생성 완료: {filename}")
                
                with open(filename, 'rb') as f:
                    st.download_button(
                        label="💾 CSV 다운로드",
                        data=f,
                        file_name=filename,
                        mime='text/csv',
                        use_container_width=True
                    )
            else:
                st.warning("먼저 '가격 업데이트' 버튼을 눌러주세요")
        
        st.markdown("---")
        
        # JSON 원본 다운로드
        st.subheader("📄 JSON 원본 다운로드")
        
        json_str = json.dumps(st.session_state.portfolio, indent=2, ensure_ascii=False)
        st.download_button(
            label="💾 JSON 다운로드",
            data=json_str,
            file_name=f"portfolio_{datetime.now().strftime('%Y%m%d')}.json",
            mime='application/json',
            use_container_width=True
        )
    
    with tab2:
        st.subheader("🗄️ 백업 파일 목록")
        
        if os.path.exists('data/backup'):
            backup_files = [f for f in os.listdir('data/backup') if f.endswith('.json')]
            backup_files.sort(reverse=True)
            
            if backup_files:
                st.caption(f"총 {len(backup_files)}개의 백업 파일")
                
                # 최근 10개만 표시
                for i, backup_file in enumerate(backup_files[:10]):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        file_time = backup_file.replace('portfolio_', '').replace('.json', '')
                        st.text(f"📄 {file_time}")
                    
                    with col2:
                        # 백업 파일 크기 표시
                        file_path = os.path.join('data/backup', backup_file)
                        file_size = os.path.getsize(file_path) / 1024  # KB
                        st.caption(f"{file_size:.1f} KB")
                
                if len(backup_files) > 10:
                    st.caption(f"... 외 {len(backup_files) - 10}개")
            else:
                st.info("백업 파일이 없습니다")
        else:
            st.info("백업 폴더가 없습니다")
