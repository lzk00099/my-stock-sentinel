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

# 强制紧凑排版 CSS
st.markdown("""
    <style>
    .reportview-container .main .block-container{ padding-top: 1rem; }
    .stTable { font-size: 0.9rem !important; }
    </style>
    """, unsafe_allow_html=True)

# 交易时间判断
def is_market_open():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    return now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) <= (16, 0)

# 辅助函数
def safe_get(df, ticker, col):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if col in df.columns.levels[0] and ticker in df.columns.levels[1]:
                s = df[col][ticker].dropna()
                return s if not s.empty else pd.Series()
        return pd.Series()
    except: return pd.Series()

def get_col(df, ticker, col_name):
    try:
        if isinstance(df.columns, pd.MultiIndex): return df[col_name][ticker].dropna()
        return df[col_name].dropna()
    except: return pd.Series()

# --- 1. Sentinel Omega (5分钟刷新) ---
@st.fragment(run_every=300)
def run_omega():
    st.markdown("### 🌌 Sentinel Omega V3.1 | 全球全资产全景监控")
    assets = {"NQ=F": "纳指100期指", "ES=F": "标普500期指", "YM=F": "道琼斯期指", "RTY=F": "罗素2000期指", "BTC-USD": "比特币(流动性)", "CL=F": "WTI原油", "GC=F": "黄金(避险)", "DX-Y.NYB": "美元指数"}
    all_s = list(assets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    data_30m = yf.download(all_s, period="5d", interval="30m", progress=False, auto_adjust=True)
    data_5m = yf.download(all_s, period="1d", interval="5m", progress=False, auto_adjust=True)

    if not data_30m.empty:
        vix_s = safe_get(data_30m, "^VIX", "Close")
        vvix_s = safe_get(data_30m, "^VVIX", "Close")
        tnx_s = safe_get(data_30m, "^TNX", "Close")
        v_curr = vix_s.iloc[-1]; t_curr = tnx_s.iloc[-1]
        vv_slope = np.polyfit(np.arange(len(vvix_s.tail(10))), vvix_s.tail(10).values, 1)[0]
        risk_status = "🔴 避险" if v_curr > 22 or vv_slope > 0.3 else "🟢 积极"
        
        st.markdown(f"""<div style='display: flex; justify-content: space-around; border: 2px solid #334155; padding: 10px; border-radius: 10px; background: #0f172a; color: white; margin-bottom: 10px;'>
            <div style='text-align: center;'>VIX: {v_curr:.2f}</div><div style='text-align: center;'>10Y: {t_curr:.2f}%</div>
            <div style='text-align: center;'>情绪: {'↗️' if vv_slope > 0.1 else '↘️'}</div><div style='text-align: center;'>模式: {risk_status}</div>
        </div>""", unsafe_allow_html=True)

        reports = []
        for symbol, name in assets.items():
            c_30, c_5, v_5 = safe_get(data_30m, symbol, "Close"), safe_get(data_5m, symbol, "Close"), safe_get(data_5m, symbol, "Volume")
            if len(c_30) < 20 or c_5.empty: continue
            cp = c_5.iloc[-1]; vwap = ((c_5 * v_5).cumsum() / v_5.cumsum()).iloc[-1]
            macd = ta.macd(c_30); rsi = ta.rsi(c_30)
            score = (1 if cp > vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0) + (1 if rsi.iloc[-1] > 50 else 0)
            reports.append({"标的": symbol, "名称": name, "最新价": round(cp, 2), "RSI": round(rsi.iloc[-1], 1), "诊断": "🚀强" if score==3 else "📉弱" if score==0 else "⚖️稳"})
        st.table(pd.DataFrame(reports))

# --- 2. Sentinel V10 Pro (1分钟刷新) ---
@st.fragment(run_every=60)
def run_v10():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V10.1 | 多维动量与期权决策")
    if not is_market_open(): st.info("🌙 非交易时段，显示最后收盘数据")
    
    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "NVDA": "英伟达"}
    data_d = yf.download(list(targets.keys()) + ["^VVIX"], period="60d", interval="1d", progress=False, auto_adjust=True)
    data_5m = yf.download(list(targets.keys()) + ["^VVIX"], period="5d", interval="5m", progress=False, auto_adjust=True)

    vvix_5 = get_col(data_5m, "^VVIX", "Close").tail(10)
    slope = np.polyfit(np.arange(len(vvix_5)), vvix_5.values, 1)[0] if not vvix_5.empty else 0
    
    v10_res = []
    for t in targets.keys():
        c_5, v_5 = get_col(data_5m, t, "Close"), get_col(data_5m, t, "Volume")
        cp = c_5.iloc[-1]; vwap = ((c_5 * v_5).cumsum() / v_5.cumsum()).iloc[-1]
        macd = ta.macd(c_5)
        score = (1 if cp > vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0)
        sig = "🎯 CALL" if score == 2 and slope < 0 else "📉 PUT" if score == 0 and slope > 0 else "☕ 观望"
        v10_res.append({"代码": t, "现价": cp, "VWAP乖离": f"{((cp/vwap)-1):+.2%}", "决策": sig})
    st.table(pd.DataFrame(v10_res))

# --- 3. 赛道与前沿科技 (底部静态显示) ---
@st.fragment(run_every=3600)
def run_bottom_scanners():
    st.markdown("---")
    st.markdown("### 🛰️ 全赛道与前沿科技追踪")
    sectors = {"核能":"URA", "太空":"ITA", "AI芯":"SMH", "中概":"KWEB", "石油":"XLE", "黄金":"GLD", "基建":"XLU"}
    frontier = {'AIPO':'AI电力','ARKX':'太空','DRNZ':'无人机','NUKZ':'下代核','QTUM':'量子','URNM':'铀矿'}
    all_s = list(sectors.values()) + list(frontier.keys()) + ['SPY']
    data = yf.download(all_s, period="60d", progress=False, auto_adjust=True)['Close']
    
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("**🏛️ 赛道强度看板**")
        sec_res = []
        for name, tk in sectors.items():
            s = data[tk].dropna()
            sec_res.append({"赛道": name, "今日": f"{(s.iloc[-1]/s.iloc[-2]-1):+.2%}", "当月": f"{(s.iloc[-1]/s.iloc[-21]-1):+.2%}"})
        st.table(pd.DataFrame(sec_res))
    
    with col_r:
        st.write("**🏆 前沿科技潜力 Top 6**")
        f_res = []
        for tk, name in frontier.items():
            s = data[tk].dropna()
            m1 = (s.iloc[-1]/s.iloc[-21]-1)
            vol = s.pct_change().std() * np.sqrt(252)
            f_res.append({"领域": name, "得分": round(m1/vol, 3), "1M": f"{m1:+.2%}"})
        st.table(pd.DataFrame(f_res).sort_values("得分", ascending=False))

# 执行
run_omega()
run_v10()
run_bottom_scanners()

# --- 启动运行 ---
run_omega()
run_v10_pro()
