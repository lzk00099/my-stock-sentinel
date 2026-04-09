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
        dx_s = safe_get(data_30m, "DX-Y.NYB", "Close")
        
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
            
            # Pivot Points (R1/S1)
            prev_day_data = c_30.tail(48)
            pivot = (prev_day_data.max() + prev_day_data.min() + prev_day_data.iloc[0]) / 3
            r1, s1 = (2 * pivot) - prev_day_data.min(), (2 * pivot) - prev_day_data.max()
            
            curr_p = c_5.iloc[-1]
            curr_vwap = (c_5 * v_5).cumsum() / v_5.cumsum()
            curr_vwap = curr_vwap.iloc[-1] if not curr_vwap.empty else c_5.mean()
            macd = ta.macd(c_30); rsi = ta.rsi(c_30)
            score = (1 if curr_p > curr_vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0) + (1 if rsi.iloc[-1] > 50 else 0)
            
            sig = "🚀 强力多头" if score == 3 else "📉 空头占优" if score == 0 else "⚖️ 中性震荡"
            
            reports.append({
                "标的": symbol, 
                "名称": name, 
                "最新价": round(curr_p, 2), 
                "S1 | R1 (参考)": f"{s1:.2f} | {r1:.2f}",
                "RSI": round(rsi.iloc[-1], 1), 
                "诊断结论": sig
            })
        
        st.table(pd.DataFrame(reports))

        # --- 跨资产专家情报 ---
        st.markdown("#### 🤖 Sentinel Omega 专家情报")
        notes = []
        if not dx_s.empty and len(dx_s) >= 5:
            if dx_s.iloc[-1] > dx_s.iloc[-5]:
                notes.append("💵 **美元压制**：美元指数日内走强，通常对纳指期指（NQ）构成估值天花板。")
        
        btc_s = [r for r in reports if "BTC-USD" in r['标的']]
        if btc_s and "🚀 强力多头" not in btc_s[0]['诊断结论']:
            notes.append("₿ **流动性预警**：比特币走势偏弱，反映全球投机资金正在退潮，现货开盘需谨慎追高。")
            
        if v_curr > 20:
            notes.append("🚨 **高波预警**：VIX 站上 20 分界线，任何单边行情都容易出现剧烈反转，建议收紧止盈。")

        if notes:
            for n in notes: st.info(n)
        else:
            st.success("✅ 各资产走势联动正常，未见明显背离，建议按关键位交易。")

# --- 核心引擎 2: Sentinel V10 Pro (实战决策) ---
@st.fragment(run_every=60)
def run_v10_pro():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V10.1 | 多维动量与期权决策")
    
    # 判断是否为实时更新模式
    market_active = is_market_open()
    if not market_active:
        st.caption("🌙 当前非交易时段，展示最近收盘状态。")

    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    # 如果处于休眠期，拉取最近1天的数据以获取最后收盘价
    data_5m = yf.download(all_tickers, period="1d" if market_active else "2d", interval="5m", progress=False, auto_adjust=True)

    if data_5m.empty:
        st.error("无法获取决策层数据。")
        return

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
        
        score = (1 if curr_p > vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0)
        
        is_squeeze = False
        if bb is not None:
            bandwidth = (bb.iloc[-1,2] - bb.iloc[-1,0]) / bb.iloc[-1,1]
            if bandwidth < 0.0015: is_squeeze = True

        sig = "🎯 CALL (爆发)" if score == 2 and vvix_intra_slope < 0 else "📉 PUT (杀跌)" if score == 0 else "☕ 观望"
        if is_squeeze: sig += " [SQUEEZE]"
        
        v10_reports.append({
            "代码": t, "现价": round(curr_p, 2), 
            "VWAP乖离": f"{((curr_p/vwap)-1):+.2%}", "期权建议": sig
        })
    
    st.dataframe(pd.DataFrame(v10_reports), use_container_width=True)

    # --- Sentinel 战术诊断解读 ---
    st.markdown("#### 🤖 Sentinel 战术诊断")
    qqq_rep = next((r for r in v10_reports if r['代码'] == "QQQ"), None)
    
    if qqq_rep:
        if vvix_intra_slope > 0.3:
            st.warning(f"⚠️ **风控警报**：日内波动率斜率 ({vvix_intra_slope:.2f}) 快速转正，警惕机构正在反手做空或买入对冲。")
        if "SQUEEZE" in qqq_rep['期权建议']:
            st.error(f"⚡ **爆发预警**：QQQ 目前布林带极度收紧，一旦价格突破位点并配合 MACD 放量，即是 0DTE 期权进场点。")
        vwap_diff = abs(float(qqq_rep['VWAP乖离'].strip('%'))/100)
        if vwap_diff > 0.01:
            st.info(f"🎈 **均值回归**：当前价格距离 VWAP 较远 ({qqq_rep['VWAP乖离']})，不宜在阻力位附近盲目追高。")

# --- 启动运行 ---
run_omega()
run_v10_pro()
