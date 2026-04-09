import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime
import pytz
import warnings

# 基础配置
warnings.filterwarnings('ignore')
st.set_page_config(page_title="Sentinel 战略指挥中心", layout="wide")

# 美股交易时间判断逻辑
def is_market_open():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    # 周一到周五，9:30 - 16:00
    market_open = now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) <= (16, 0)
    return market_open

# --- 数据获取工具函数 (保留原版 safe_get/get_col 逻辑) ---
def safe_get(df, ticker, col):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if col in df.columns.levels[0] and ticker in df.columns.levels[1]:
                s = df[col][ticker].dropna()
                return s if not s.empty else pd.Series()
        return pd.Series()
    except: return pd.Series()

def get_col(df, ticker, col_name):
    if isinstance(df.columns, pd.MultiIndex):
        return df[col_name][ticker].dropna()
    return df[col_name].dropna()

# --- 核心引擎 1: Sentinel Omega (宏观环境) ---
@st.fragment(run_every=300) # 每5分钟自动刷新
def run_omega():
    st.markdown("### 🌌 Sentinel Omega V3.1 | 全球全资产全景监控")
    assets = {
        "NQ=F": "纳指100期指", "ES=F": "标普500期指", "YM=F": "道琼斯期指",
        "RTY=F": "罗素2000期指", "BTC-USD": "比特币(流动性)", "CL=F": "WTI原油",
        "GC=F": "黄金(避险)", "DX-Y.NYB": "美元指数"
    }
    all_symbols = list(assets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    data_30m = yf.download(all_symbols, period="5d", interval="30m", progress=False, auto_adjust=True)
    data_5m = yf.download(all_symbols, period="1d", interval="5m", progress=False, auto_adjust=True)

    if not data_30m.empty:
        vix_s = safe_get(data_30m, "^VIX", "Close")
        vvix_s = safe_get(data_30m, "^VVIX", "Close")
        tnx_s = safe_get(data_30m, "^TNX", "Close")
        v_curr = vix_s.iloc[-1] if not vix_s.empty else 0
        t_curr = tnx_s.iloc[-1] if not tnx_s.empty else 0
        vv_slope = np.polyfit(np.arange(len(vvix_s.tail(10))), vvix_s.tail(10).values, 1)[0] if len(vvix_s) > 10 else 0
        
        risk_status = "🔴 避险模式 (Risk-Off)" if v_curr > 22 or vv_slope > 0.3 else "🟢 积极模式 (Risk-On)"
        
        # 渲染顶部卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("VIX 指数", f"{v_curr:.2f}")
        col2.metric("10Y 美债", f"{t_curr:.2f}%")
        col3.metric("情绪斜率", "↗️ 升温" if vv_slope > 0.1 else "↘️ 降温")
        col4.metric("当前总评", risk_status)

        reports = []
        for symbol, name in assets.items():
            c_30, c_5, v_5 = safe_get(data_30m, symbol, "Close"), safe_get(data_5m, symbol, "Close"), safe_get(data_5m, symbol, "Volume")
            if len(c_30) < 20 or c_5.empty: continue
            curr_p = c_5.iloc[-1]
            curr_vwap = (c_5 * v_5).cumsum() / v_5.cumsum()
            curr_vwap = curr_vwap.iloc[-1] if not curr_vwap.empty else c_5.mean()
            macd = ta.macd(c_30); rsi = ta.rsi(c_30)
            score = (1 if curr_p > curr_vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0) + (1 if rsi.iloc[-1] > 50 else 0)
            
            sig = "🚀 强力多头" if score == 3 else "📉 空头占优" if score == 0 else "⚖️ 中性震荡"
            reports.append({"标的": symbol, "名称": name, "最新价": round(curr_p, 2), "RSI": round(rsi.iloc[-1], 1), "诊断": sig})
        
        st.table(pd.DataFrame(reports))

# --- 核心引擎 2: Sentinel V10 Pro (实战决策) ---
@st.fragment(run_every=60) # 交易时段每1分钟自动刷新
def run_v10_pro():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V10.1 | 多维动量与期权决策")
    
    if not is_market_open():
        st.warning("🌙 当前非交易时段，系统处于休眠模式。")
        return

    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    data_daily = yf.download(all_tickers, period="60d", interval="1d", progress=False, auto_adjust=True)
    data_5m = yf.download(all_tickers, period="5d", interval="5m", progress=False, auto_adjust=True)

    v10_reports = []
    vvix_5m = get_col(data_5m, "^VVIX", "Close").tail(10)
    vvix_slope = np.polyfit(np.arange(len(vvix_5m)), vvix_5m.values, 1)[0]

    for t in targets.keys():
        c_5 = get_col(data_5m, t, "Close")
        v_5 = get_col(data_5m, t, "Volume")
        curr_p = c_5.iloc[-1]
        vwap = ((c_5 * v_5).cumsum() / v_5.cumsum()).iloc[-1]
        macd = ta.macd(c_5)
        
        score = (1 if curr_p > vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0)
        sig = "🎯 CALL (爆发)" if score == 2 and vvix_slope < 0 else "📉 PUT (杀跌)" if score == 0 else "☕ 观望"
        
        v10_reports.append({"代码": t, "现价": curr_p, "VWAP乖离": f"{((curr_p/vwap)-1):+.2%}", "期权建议": sig})
    
    st.dataframe(pd.DataFrame(v10_reports), use_container_width=True)

# --- 启动运行 ---
run_omega()
run_v10_pro()
run_bottom_scanners()
