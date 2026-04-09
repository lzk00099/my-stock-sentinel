import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime
import pytz
import warnings

# --- 基础配置 ---
warnings.filterwarnings('ignore')
st.set_page_config(page_title="Sentinel 战略指挥中心", layout="wide")

# 强制紧凑样式的 CSS
st.markdown("""
    <style>
    .reportview-container .main .block-container{ padding-top: 1rem; padding-bottom: 1rem; }
    h1, h2, h3 { margin-top: -10px; padding-top: 10px; font-size: 1.2rem !important; }
    p, span { font-size: 0.9rem !important; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1rem !important; font-weight: bold; }
    .stDataFrame { font-size: 0.8rem !important; }
    </style>
    """, unsafe_allow_html=True)

# 交易时间判断
def is_market_open():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    return now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) <= (16, 0)

# 辅助函数
def get_col(df, ticker, col_name):
    try:
        if isinstance(df.columns, pd.MultiIndex): return df[col_name][ticker].dropna()
        return df[col_name].dropna()
    except: return pd.Series()

# --- 模块 1: Sentinel Omega & V10 Pro (合并引擎) ---
@st.fragment(run_every=60)
def run_main_terminal():
    col_a, col_b = st.columns([1, 1.2])
    
    # 获取数据
    omega_assets = {"NQ=F":"纳指期","ES=F":"标普期","BTC-USD":"BTC","DX-Y.NYB":"美元"}
    v10_targets = {"QQQ":"纳指100","SPY":"标普500","NVDA":"英伟达"}
    all_main = list(omega_assets.keys()) + list(v10_targets.keys()) + ["^VIX","^VVIX","^TNX"]
    
    data = yf.download(all_main, period="5d", interval="5m", progress=False, auto_adjust=True)
    
    with col_a:
        st.subheader("🌌 Omega 宏观 & 情绪")
        v_curr = get_col(data, "^VIX", "Close").iloc[-1]
        t_curr = get_col(data, "^TNX", "Close").iloc[-1]
        vvix_s = get_col(data, "^VVIX", "Close").tail(10)
        vv_slope = np.polyfit(np.arange(len(vvix_s)), vvix_s.values, 1)[0] if len(vvix_s)>1 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("VIX", f"{v_curr:.2f}")
        c2.metric("10Y", f"{t_curr:.2f}%")
        c3.metric("VVIX斜率", "↗️升" if vv_slope > 0.1 else "↘️降")
        
        res = []
        for s, n in omega_assets.items():
            cp = get_col(data, s, "Close").iloc[-1]
            res.append({"标的": n, "现价": round(cp, 2)})
        st.dataframe(pd.DataFrame(res), hide_index=True, use_container_width=True)

    with col_b:
        st.subheader("🏛️ V10 Pro 期权决策")
        if is_market_open():
            v10_res = []
            for t, n in v10_targets.items():
                cp = get_col(data, t, "Close").iloc[-1]
                v = get_col(data, t, "Volume")
                vwap = ((get_col(data, t, "Close") * v).cumsum() / v.cumsum()).iloc[-1]
                sig = "🎯 CALL" if cp > vwap and vv_slope < 0 else "📉 PUT" if cp < vwap and vv_slope > 0 else "☕ 观望"
                v10_res.append({"代码": t, "建议": sig, "VWAP": f"{((cp/vwap)-1):+.2%}"})
            st.dataframe(pd.DataFrame(v10_res), hide_index=True, use_container_width=True)
        else:
            st.info("🌙 休眠模式：显示最后收盘价")

# --- 模块 2: 赛道全维强度 (V7.2) & 前沿科技前十 ---
@st.fragment(run_every=3600) # 赛道分析属于慢频率，每小时更新即可
def run_sector_scanners():
    st.markdown("---")
    col_l, col_r = st.columns(2)
    
    sectors = {"核能":"URA","太空":"ITA","AI芯":"SMH","中概":"KWEB","银行":"KRE","石油":"XLE","黄金":"GLD","电力":"XLU"}
    frontier = {'AIPO':'AI电力','NUKZ':'下代核','DRNZ':'无人机','SMH':'AI芯','QTUM':'量子','ARKX':'太空','URNM':'铀矿'}
    
    lev_filter = ['SOXL', 'SOXS', 'TQQQ', 'SQQQ']
    all_s = list(sectors.values()) + list(frontier.keys()) + ['SPY']
    
    data_s = yf.download(all_s, period="60d", interval="1d", progress=False, auto_adjust=True)
    close = data_s['Close']

    with col_l:
        st.subheader("🏛️ V7.2 赛道全维强度")
        sec_res = []
        for name, tk in sectors.items():
            if tk in lev_filter: continue
            s = close[tk].dropna()
            d_ret = (s.iloc[-1]/s.iloc[-2])-1
            m_ret = (s.iloc[-1]/s.iloc[-21])-1
            sec_res.append({"赛道": name, "今日": f"{d_ret:+.1%}", "当月": f"{m_ret:+.1%}"})
        st.dataframe(pd.DataFrame(sec_res), hide_index=True, use_container_width=True)

    with col_r:
        st.subheader("🏆 前沿科技潜力 Top 10")
        f_res = []
        for tk, name in frontier.items():
            s = close[tk].dropna()
            m1 = (s.iloc[-1]/s.iloc[-21])-1
            vol = s.pct_change().std() * np.sqrt(252)
            score = (m1 * 0.7) / vol
            f_res.append({"标的": name, "得分": round(score, 3), "1M": f"{m1:+.1%}"})
        df_f = pd.DataFrame(f_res).sort_values("得分", ascending=False).head(10)
        st.dataframe(df_f, hide_index=True, use_container_width=True)

# 启动执行
run_main_terminal()
run_sector_scanners()
