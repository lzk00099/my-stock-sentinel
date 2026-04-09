import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
import pytz
import warnings

# 基础配置
warnings.filterwarnings('ignore')
st.set_page_config(page_title="Sentinel 战略指挥中心", layout="wide")

# --- 时间处理逻辑 ---
def get_market_times():
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    
    # 计算当日或下一个交易日的开盘时间 (9:30 AM)
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    
    if now.weekday() >= 5: # 周末
        days_to_monday = 7 - now.weekday()
        open_time += timedelta(days=days_to_monday)
    elif now >= now.replace(hour=16, minute=0): # 已收盘
        open_time += timedelta(days=1 if now.weekday() < 4 else 3)
    
    countdown = open_time - now
    return now, open_time, countdown

def is_market_open():
    now, _, _ = get_market_times()
    return now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)

# --- 数据获取工具函数 ---
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

def calculate_pivots_full(df, ticker):
    """计算多层 Pivot Points (S1, S2, R1, R2)"""
    try:
        high = safe_get(df, ticker, "High").iloc[-1]
        low = safe_get(df, ticker, "Low").iloc[-1]
        close = safe_get(df, ticker, "Close").iloc[-1]
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        return round(s1, 2), round(s2, 2), round(r1, 2), round(r2, 2)
    except:
        return 0, 0, 0, 0

# --- 核心引擎 1: Sentinel Omega (宏观环境) ---
@st.fragment(run_every=300)
def run_omega():
    st.markdown("### 🌌 Sentinel Omega V3.2 | 全球全资产全景监控")
    assets = {
        "NQ=F": "纳指100期指", "ES=F": "标普500期指", "YM=F": "道琼斯期指",
        "RTY=F": "罗素2000期指", "BTC-USD": "比特币(流动性)", "CL=F": "WTI原油",
        "GC=F": "黄金(避险)", "DX-Y.NYB": "美元指数"
    }
    all_symbols = list(assets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    data_30m = yf.download(all_symbols, period="5d", interval="30m", progress=False, auto_adjust=True)
    data_5m = yf.download(all_symbols, period="1d", interval="5m", progress=False, auto_adjust=True)
    data_daily = yf.download(all_symbols, period="2d", interval="1d", progress=False, auto_adjust=True)

    if not data_30m.empty:
        vix_s = safe_get(data_30m, "^VIX", "Close")
        vvix_s = safe_get(data_30m, "^VVIX", "Close")
        tnx_s = safe_get(data_30m, "^TNX", "Close")
        dx_s = safe_get(data_30m, "DX-Y.NYB", "Close")
        
        v_curr = vix_s.iloc[-1] if not vix_s.empty else 0
        t_curr = tnx_s.iloc[-1] if not tnx_s.empty else 0
        vv_slope = np.polyfit(np.arange(len(vvix_s.tail(10))), vvix_s.tail(10).values, 1)[0] if len(vvix_s) > 10 else 0
        
        risk_status = "🔴 避险模式 (Risk-Off)" if v_curr > 22 or vv_slope > 0.3 else "🟢 积极模式 (Risk-On)"
        
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
            
            s1, _, r1, _ = calculate_pivots_full(data_daily, symbol)
            
            sig = "🚀 强力多头" if score == 3 else "📉 空头占优" if score == 0 else "⚖️ 中性震荡"
            reports.append({
                "标的": symbol, "名称": name, "最新价": round(curr_p, 2), 
                "关键位 (S1|R1)": f"S:{s1} | R:{r1}", 
                "RSI": round(rsi.iloc[-1], 1), "诊断结论": sig
            })
        
        st.table(pd.DataFrame(reports))

        st.markdown("#### 🤖 Sentinel Omega 专家情报")
        notes = []
        if not dx_s.empty and len(dx_s) >= 5:
            if dx_s.iloc[-1] > dx_s.iloc[-5]:
                notes.append("💵 **美元压制**：美元指数日内走强，通常对纳指期指（NQ）构成估值天花板。")
        
        btc_s = [r for r in reports if "BTC-USD" in r['标的']]
        if btc_s and "🚀 强力多头" not in btc_s[0]['诊断结论']:
            notes.append("₿ **流动性预警**：比特币走势偏弱，反映全球投机资金正在退潮。")
            
        if v_curr > 20:
            notes.append("🚨 **高波预警**：VIX 站上 20 分界线，建议收紧止盈。")

        if notes:
            for n in notes: st.info(n)
        else:
            st.success("✅ 各资产走势联动正常，未见明显背离。")

# --- 核心引擎 2: Sentinel V10 Pro (实战决策) ---
@st.fragment(run_every=60)
def run_v10_pro():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V10.1 | 多维动量与期权决策")
    
    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    now, open_time, countdown = get_market_times()

    if not is_market_open():
        st.warning(f"🌙 当前非交易时段。系统进入休眠模式。")
        hours, remainder = divmod(int(countdown.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        st.subheader(f"⏳ 距离美股开盘还有: {hours}小时 {minutes}分")
        
        st.markdown("#### 📊 前一交易日收盘概览")
        last_close_data = yf.download(all_tickers, period="2d", interval="1d", progress=False)
        if not last_close_data.empty:
            summary = []
            for t in targets.keys():
                closes = last_close_data['Close'][t].dropna()
                if len(closes) >= 2:
                    last_p = closes.iloc[-1]
                    prev_p = closes.iloc[-2]
                    chg = (last_p / prev_p) - 1
                    summary.append({"代码": t, "名称": targets[t], "收盘价": round(last_p, 2), "涨跌幅": f"{chg:+.2%}"})
            st.table(pd.DataFrame(summary))
        return

    data_5m = yf.download(all_tickers, period="5d", interval="5m", progress=False, auto_adjust=True)
    data_daily = yf.download(all_tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
    
    v10_reports = []
    vvix_5m = get_col(data_5m, "^VVIX", "Close").tail(10)
    vvix_intra_slope = np.polyfit(np.arange(len(vvix_5m)), vvix_5m.values, 1)[0] if len(vvix_5m) > 1 else 0

    for t in targets.keys():
        c_5 = get_col(data_5m, t, "Close")
        v_5 = get_col(data_5m, t, "Volume")
        if c_5.empty: continue
        
        curr_p = c_5.iloc[-1]
        vwap_series = (c_5 * v_5).cumsum() / v_5.cumsum()
        vwap = vwap_series.iloc[-1]
        macd = ta.macd(c_5)
        bb = ta.bbands(c_5, length=20, std=2)
        
        s1, s2, r1, r2 = calculate_pivots_full(data_daily, t)
        
        score = (1 if curr_p > vwap else 0) + (1 if (not macd.empty and macd.iloc[-1,0] > macd.iloc[-1,2]) else 0)
        is_squeeze = (bb.iloc[-1,2] - bb.iloc[-1,0]) / bb.iloc[-1,1] < 0.0015 if bb is not None else False

        sig = "🎯 CALL (爆发)" if score == 2 and vvix_intra_slope < 0 else "📉 PUT (杀跌)" if score == 0 else "☕ 观望"
        if is_squeeze: sig += " [SQUEEZE]"
        
        v10_reports.append({
            "代码": t, "现价": round(curr_p, 2), 
            "阻力(R1/R2)": f"{r1} | {r2}", "支撑(S1/S2)": f"{s1} | {s2}",
            "VWAP乖离": f"{((curr_p/vwap)-1):+.2%}", "期权建议": sig
        })
    
    st.dataframe(pd.DataFrame(v10_reports), use_container_width=True)

    st.markdown("#### 🤖 Sentinel 战术诊断")
    qqq_rep = next((r for r in v10_reports if r['代码'] == "QQQ"), None)
    if qqq_rep:
        if vvix_intra_slope > 0.3:
            st.warning(f"⚠️ **风控警报**：波动率斜率 ({vvix_intra_slope:.2f}) 快速转正，警惕机构买入对冲。")
        if "SQUEEZE" in qqq_rep['期权建议']:
            st.error(f"⚡ **爆发预警**：QQQ 布林带极度收紧，配合 MACD 放量即是 0DTE 进场点。")
        vwap_diff = abs(float(qqq_rep['VWAP乖离'].strip('%'))/100)
        if vwap_diff > 0.01:
            st.info(f"🎈 **均值回归**：当前价格距离 VWAP 较远，不宜追高。")

# --- 启动运行 ---
run_omega()
run_v10_pro()
