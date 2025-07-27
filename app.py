import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests

# --- 1. 앱 기본 설정 및 한글 폰트 설정 ---
st.set_page_config(layout="wide") 
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# <<< [수정] API 서버 주소 변경
API_BASE_URL = "https://lighthorse.duckdns.org"


# --- 2. API 통신 및 데이터 처리 함수 ---

@st.cache_data(ttl=3600) 
def fetch_stock_list_from_api():
    """API 서버로부터 분석 가능한 전체 주식 목록을 가져옵니다."""
    api_url = f"{API_BASE_URL}/os/stocks"
    try:
        response = requests.get(api_url, timeout=10) # 외부 접속이므로 timeout 증가
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"전체 종목 목록 API 호출 실패: {e}")
        return None

def search_stock_code(keyword, stock_list):
    """API에서 받아온 주식 목록 안에서 종목을 검색합니다."""
    if not stock_list: return None, None
    for stock in stock_list:
        if stock['name'] == keyword: return [stock['code']], None
    similar_stocks = {stock['code']: stock['name'] for stock in stock_list if keyword in stock['name']}
    return None, similar_stocks if similar_stocks else None

@st.cache_data(ttl=600) 
def fetch_data_from_api(stock_code):
    """API 서버로부터 특정 종목의 상세 시계열 데이터를 가져옵니다."""
    api_url = f"{API_BASE_URL}/os/stock/{stock_code}"
    try:
        response = requests.get(api_url, timeout=10) # 외부 접속이므로 timeout 증가
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df['날짜'] = pd.to_datetime(df['날짜'])
        df.set_index('날짜', inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        st.error(f"종목 데이터 API 호출 실패 ({stock_code}): {e}")
        return None

def calculate_stats(data, osc_col_name):
    """지정된 오실레이터 컬럼으로 통계치를 계산하고 '현재 값'을 추가합니다."""
    if data.empty or osc_col_name not in data.columns: return {}
    stats = {
        '현재 값': data[osc_col_name].iloc[-1],
        '상위 10%': data[osc_col_name].quantile(0.9),
        '상위 25%': data[osc_col_name].quantile(0.75),
        '평균': data[osc_col_name].mean(),
        '하위 25%': data[osc_col_name].quantile(0.25),
        '하위 10%': data[osc_col_name].quantile(0.1),
    }
    return stats

def create_macd_graph(data, stats, stock_code, stock_name, osc_col_name, title_prefix):
    """지정된 오실레이터 컬럼으로 그래프(figure 객체)를 생성합니다."""
    fig, ax1 = plt.subplots(figsize=(14, 10))
    
    ax1.plot(data.index, data['시가총액'], label='시가총액', color='black')
    ax1.set_ylabel('시가총액', color='black')
    ax1.tick_params(axis='y', labelcolor='black')
    for date in data.index:
        ax1.axvline(date, color='gray', linestyle=':', linewidth=0.5)

    ax2 = ax1.twinx()
    ax2.plot(data.index, data[osc_col_name], label=osc_col_name, color='red')
    ax2.set_ylabel('MACD 오실레이터', color='black')
    ax2.tick_params(axis='y', labelcolor='black')
    
    ax2.axhline(0, color='gray', linestyle='--', linewidth=0.7)
    
    if stats:
        for key, value in stats.items():
            if key == '현재 값': continue
            linestyle = '-' if key == '평균' else '--'
            color = 'purple' if key == '평균' else ('green' if '10%' in key else 'blue')
            linewidth = 1.5 if key == '평균' else 1
            ax2.axhline(value, color=color, linestyle=linestyle, linewidth=linewidth, label=key)

    plt.title(f"[{title_prefix}] {stock_name}({stock_code}) - 시가총액과 MACD 오실레이터", fontsize=16)
    fig.legend(loc='upper left')
    plt.tight_layout()
    
    return fig


# --- 3. Streamlit 앱 화면 구성 ---

st.title("📈 MACD 계산 방식 비교 분석기")

stock_list_from_api = fetch_stock_list_from_api()

if stock_list_from_api:
    with st.form(key='stock_search_form'):
        stock_name_input = st.text_input("종목명을 입력하세요 (예: 삼성전자)")
        submit_button = st.form_submit_button(label='조회')

    if submit_button and stock_name_input:
        exact_match, similar = search_stock_code(stock_name_input, stock_list_from_api)
        if exact_match:
            st.session_state.target_code = exact_match[0]
            st.session_state.similar_stocks = None
        elif similar:
            st.session_state.target_code = None
            st.session_state.similar_stocks = similar
        else:
            st.error(f"'{stock_name_input}'에 해당하는 종목을 찾을 수 없습니다.")
            st.session_state.target_code = None
            st.session_state.similar_stocks = None

    if 'similar_stocks' in st.session_state and st.session_state.similar_stocks:
        st.warning("정확한 종목명이 없습니다. 아래에서 선택하세요:")
        for code, name in st.session_state.similar_stocks.items():
            if st.button(f"{name} ({code})"):
                st.session_state.target_code = code
                st.session_state.similar_stocks = None
                st.rerun() 

    if 'target_code' in st.session_state and st.session_state.target_code:
        target_code = st.session_state.target_code
        data = fetch_data_from_api(target_code)

        if data is not None and not data.empty:
            stock_name = next((s['name'] for s in stock_list_from_api if s['code'] == target_code), target_code)
            
            col1, col2 = st.columns(2)

            with col1:
                st.header("✅ 정확한 계산 (1년 데이터 기반)")
                if 'MACD_Oscillator_Accurate' in data.columns:
                    stats_acc = calculate_stats(data, 'MACD_Oscillator_Accurate')
                    stats_df_acc = pd.DataFrame(list(stats_acc.items()), columns=['항목', '값'])
                    stats_df_acc['값'] = stats_df_acc['값'].apply(lambda x: f"{x:,.5f}")
                    st.table(stats_df_acc)
                    
                    fig_acc = create_macd_graph(data, stats_acc, target_code, stock_name, 'MACD_Oscillator_Accurate', '정확한 계산')
                    st.pyplot(fig_acc)

            with col2:
                st.header("⚠️ 부정확한 계산 (77일 데이터 기반)")
                if 'MACD_Oscillator_Inaccurate' in data.columns:
                    stats_inacc = calculate_stats(data, 'MACD_Oscillator_Inaccurate')
                    stats_df_inacc = pd.DataFrame(list(stats_inacc.items()), columns=['항목', '값'])
                    stats_df_inacc['값'] = stats_df_inacc['값'].apply(lambda x: f"{x:,.5f}")
                    st.table(stats_df_inacc)

                    fig_inacc = create_macd_graph(data, stats_inacc, target_code, stock_name, 'MACD_Oscillator_Inaccurate', '부정확한 계산')
                    st.pyplot(fig_inacc)
else:
    st.error("API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
