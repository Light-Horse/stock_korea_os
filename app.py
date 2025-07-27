import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import requests
import os

# --- 1. 앱 기본 설정 및 폰트 설정 ---
st.set_page_config(layout="wide")

# [수정] 프로젝트에 포함된 폰트 파일을 직접 사용하는 방식으로 변경
@st.cache_resource
def get_font_prop():
    font_path = os.path.join('fonts', 'NanumGothic.ttf')
    if os.path.exists(font_path):
        return fm.FontProperties(fname=font_path)
    # 폰트 파일이 없을 경우, Streamlit 기본 폰트를 사용하도록 시도
    # (이 경우 한글이 깨질 수 있음)
    return None

font_prop = get_font_prop()
if font_prop:
    plt.rcParams['font.family'] = font_prop.get_name()
else:
    st.warning("'fonts/NanumGothic.ttf' 폰트 파일을 찾을 수 없습니다. 한글이 깨질 수 있습니다.")
plt.rcParams['axes.unicode_minus'] = False


# API 서버 주소
API_BASE_URL = "https://lighthorse.duckdns.org"


# --- 2. API 통신 및 데이터 처리 함수 ---

@st.cache_data(ttl=3600) 
def fetch_stock_list_from_api():
    """API 서버로부터 분석 가능한 전체 주식 목록을 가져옵니다."""
    api_url = f"{API_BASE_URL}/os/stocks"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"전체 종목 목록 API 호출 실패: {e}")
        return []

@st.cache_data(ttl=600) 
def fetch_data_from_api(stock_code):
    """API 서버로부터 특정 종목의 상세 시계열 데이터를 가져옵니다."""
    api_url = f"{API_BASE_URL}/os/stock/{stock_code}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df['날짜'] = pd.to_datetime(df['날짜'])
        df.set_index('날짜', inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        st.error(f"종목 데이터 API 호출 실패 ({stock_code}): {e}")
        return None

def calculate_stats(data, osc_col_name):
    """지정된 오실레이터 컬럼으로 통계치를 계산합니다."""
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

# [수정] 그래프 함수에 font_prop 인자 추가하여 폰트 적용
def create_macd_graph(data, stats, stock_code, stock_name, osc_col_name, title_prefix, font_prop):
    """지정된 오실레이터 컬럼으로 그래프(figure 객체)를 생성합니다."""
    fig, ax1 = plt.subplots(figsize=(12, 8)) # 모바일 가독성을 위해 크기 약간 조정
    
    ax1.plot(data.index, data['시가총액'], label='시가총액', color='black')
    ax1.set_ylabel('시가총액', fontproperties=font_prop)
    ax1.tick_params(axis='y', labelcolor='black')
    for date in data.index:
        ax1.axvline(date, color='gray', linestyle=':', linewidth=0.5)

    ax2 = ax1.twinx()
    ax2.plot(data.index, data[osc_col_name], label=osc_col_name, color='red')
    ax2.set_ylabel('MACD 오실레이터', fontproperties=font_prop)
    ax2.tick_params(axis='y', labelcolor='black')
    
    ax2.axhline(0, color='gray', linestyle='--', linewidth=0.7)
    
    if stats:
        for key, value in stats.items():
            if key == '현재 값': continue
            linestyle = '-' if key == '평균' else '--'
            color = 'purple' if key == '평균' else ('green' if '10%' in key else 'blue')
            linewidth = 1.5 if key == '평균' else 1
            ax2.axhline(value, color=color, linestyle=linestyle, linewidth=linewidth, label=key)

    plt.title(f"[{title_prefix}] {stock_name}({stock_code})", fontproperties=font_prop, fontsize=16)
    fig.legend(loc='upper left', prop=font_prop)
    plt.tight_layout()
    
    return fig


# --- 3. Streamlit 앱 화면 구성 ---

st.title("📈 MACD 계산 방식 비교 분석기")

stock_list = fetch_stock_list_from_api()

if stock_list:
    # [수정] 검색 UI를 텍스트 입력 대신 Selectbox로 변경
    stock_names = [s['name'] for s in stock_list]
    selected_name = st.selectbox(
        '종목을 검색하거나 선택하세요:',
        options=stock_names,
        index=None, # 기본적으로 아무것도 선택되지 않도록 설정
        placeholder="종목명을 입력하여 검색..."
    )

    # 종목이 선택되었을 경우 결과 표시
    if selected_name:
        # 선택된 이름으로 종목 코드 찾기
        target_code = next((s['code'] for s in stock_list if s['name'] == selected_name), None)
        
        if target_code:
            data = fetch_data_from_api(target_code)

            if data is not None and not data.empty:
                
                # [수정] 결과를 탭으로 분리하여 모바일 최적화
                tab1, tab2 = st.tabs(["✅ 정확한 계산 (1년 데이터)", "⚠️ 부정확한 계산 (77일 데이터)"])

                with tab1:
                    if 'MACD_Oscillator_Accurate' in data.columns:
                        stats_acc = calculate_stats(data, 'MACD_Oscillator_Accurate')
                        stats_df_acc = pd.DataFrame(list(stats_acc.items()), columns=['항목', '값'])
                        stats_df_acc['값'] = stats_df_acc['값'].apply(lambda x: f"{x:,.5f}")
                        st.table(stats_df_acc)
                        
                        fig_acc = create_macd_graph(data, stats_acc, target_code, selected_name, 'MACD_Oscillator_Accurate', '정확한 계산', font_prop)
                        st.pyplot(fig_acc)

                with tab2:
                    if 'MACD_Oscillator_Inaccurate' in data.columns:
                        stats_inacc = calculate_stats(data, 'MACD_Oscillator_Inaccurate')
                        stats_df_inacc = pd.DataFrame(list(stats_inacc.items()), columns=['항목', '값'])
                        stats_df_inacc['값'] = stats_df_inacc['값'].apply(lambda x: f"{x:,.5f}")
                        st.table(stats_df_inacc)

                        fig_inacc = create_macd_graph(data, stats_inacc, target_code, selected_name, 'MACD_Oscillator_Inaccurate', '부정확한 계산', font_prop)
                        st.pyplot(fig_inacc)
else:
    st.error("API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하고 페이지를 새로고침 하세요.")
