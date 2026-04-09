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

# --- 核心引擎 1: Sentinel Omega (宏观环境) - 保持原样 ---
@st.fragment(run_every=300) 
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
            v_sum = v_5.cumsum()
            curr_vwap = (c_5 * v_5).cumsum() / v_sum if not v_sum.empty else c_5.mean()
            curr_vwap = curr_vwap.iloc[-1]
            macd = ta.macd(c_30); rsi = ta.rsi(c_30)
            score = (1 if curr_p > curr_vwap else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0) + (1 if rsi.iloc[-1] > 50 else 0)
            
            sig = "🚀 强力多头" if score == 3 else "📉 空头占优" if score == 0 else "⚖️ 中性震荡"
            reports.append({"标的": symbol, "名称": name, "最新价": round(curr_p, 2), "RSI": round(rsi.iloc[-1], 1), "诊断结论": sig})
        
        st.table(pd.DataFrame(reports))

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
            st.success("✅ 各资产走势联动正常，未见明显背离。")

# --- 核心引擎 2: 多维动量与期权决策 (由 V11 Pro 逻辑升级替换) ---
@st.fragment(run_every=60)
def run_dynamic_decision():
    st.markdown("---")
    st.markdown("### 🏛️ 多维动量与期权决策 | Sentinel V11 Pro Core")
    
    if not is_market_open():
        st.warning("🌙 当前非交易时段，系统处于休眠模式。点位基于最近收盘数据。")

    targets = {"DIA": "道琼斯", "SPY": "标普500", "QQQ": "纳指100", "IWM": "罗素2000", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    data_daily = yf.download(all_tickers, period="60d", interval="1d", progress=False, auto_adjust=True)
    data_5m = yf.download(all_tickers, period="5d", interval="5m", progress=False, auto_adjust=True)

    if data_daily.empty or data_5m.empty: return

    # --- 宏观分级指标显示 ---
    vix_s = get_col(data_5m, "^VIX", "Close")
    vix_curr = vix_s.iloc[-1]
    vvix_s = get_col(data_5m, "^VVIX", "Close")
    vvix_curr = vvix_s.iloc[-1]
    
    # 斜率描述逻辑
    vvix_tail = vvix_s.tail(10)
    v_slope = np.polyfit(np.arange(len(vvix_tail)), vvix_tail.values, 1)[0] if len(vvix_tail) > 1 else 0
    v_slope_desc = "🚨 飙升" if v_slope > 0.4 else "⚠️ 升温" if v_slope > 0.1 else "✅ 降温" if v_slope < -0.1 else "🧱 平稳"
    
    # 渲染宏观分级面板
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    vix_color = "green" if vix_curr < 15 else "orange" if vix_curr < 23 else "red"
    mcol1.markdown(f"**VIX 状态** \n:{vix_color}[{vix_curr:.2f} ({'低波' if vix_curr < 15 else '中波' if vix_curr < 23 else '高波'})]")
    mcol2.markdown(f"**VVIX 情绪** \n{vvix_curr:.1f} ({v_slope_desc})")
    
    tnx = get_col(data_daily, "^TNX", "Close").iloc[-1]
    tnx_delta = tnx - get_col(data_daily, "^TNX", "Close").iloc[-2]
    mcol3.markdown(f"**10Y 美债** \n{tnx:.2f}% ({tnx_delta:+.3f})")
    mcol4.markdown(f"**刷新时间** \n{datetime.now().strftime('%H:%M:%S')}")

    v11_reports = []
    audit_notes = []

    for t in targets.keys():
        c_5 = get_col(data_5m, t, "Close")
        v_5 = get_col(data_5m, t, "Volume")
        if c_5.empty: continue
        
        curr_p = c_5.iloc[-1]
        vwap_series = (c_5 * v_5).cumsum() / v_5.cumsum()
        c_vwap = vwap_series.iloc[-1]

        # 量价背离检测
        p_slope = np.polyfit(np.arange(5), c_5.tail(5).values, 1)[0]
        vol_slope = np.polyfit(np.arange(5), v_5.tail(5).values, 1)[0]
        is_divergence = p_slope > 0 and vol_slope < 0

        # Squeeze 逻辑
        bb = ta.bbands(c_5, length=20, std=2)
        kc = ta.kc(get_col(data_5m, t, "High"), get_col(data_5m, t, "Low"), c_5, length=20, scalar=1.5)
        is_squeezing = (bb.iloc[-1, 2] - bb.iloc[-1, 0]) < (kc.iloc[-1, 2] - kc.iloc[-1, 0])

        # 支撑阻力
        prev_h, prev_l, prev_c = get_col(data_daily, t, "High").iloc[-2], get_col(data_daily, t, "Low").iloc[-2], get_col(data_daily, t, "Close").iloc[-2]
        pivot = (prev_h + prev_l + prev_c) / 3
        r1, s1 = (2 * pivot) - prev_l, (2 * pivot) - prev_h
        r2, s2 = pivot + (prev_h - prev_l), pivot - (prev_h - prev_l)

        # 结构判定
        if curr_p > prev_c and curr_p > c_vwap: structure = "🚀 强势突破"
        elif curr_p > c_vwap and curr_p <= prev_c: structure = "🩹 超跌反弹"
        else: structure = "📉 弱势运行"

        # 决策
        score = (1 if curr_p > c_vwap else 0) + (1 if curr_p > prev_c else 0) + (1 if v_slope < 0 else 0) + (1 if not is_divergence else 0)
        if score >= 4: sig = "🎯 CALL (爆发)"
        elif is_divergence and curr_p > c_vwap: sig = "🚫 诱多 (背离)"
        elif is_squeezing: sig = "⚡ SQUEEZE"
        else: sig = "☕ 观望"

        v11_reports.append({
            "代码": t, "现价": round(curr_p, 2),
            "支撑 S1/S2": f"{s1:.2f} / {s2:.2f}",
            "阻力 R1/R2": f"{r1:.2f} / {r2:.2f}",
            "昨收": round(prev_c, 2),
            "结构": structure, "决策": sig
        })
        
        # 审计收集
        if "诱多" in sig: audit_notes.append(f"🚫 **{t}**：量价背离，警惕机构诱多。")
        if "超跌反弹" in structure: audit_notes.append(f"🩹 **{t}**：反弹受限于昨收线 {prev_c:.2f}，非趋势反转。")
        if is_squeezing: audit_notes.append(f"⚡ **{t}**：Squeeze 状态，紧盯阻力位 {r1:.2f}。")

    st.table(pd.DataFrame(v11_reports))

    # --- 战术审计解读 ---
    st.markdown("#### 🤖 Sentinel 核心战术审计")
    if audit_notes:
        for note in audit_notes: st.info(note)
    else:
        st.success("✅ 结构稳定，暂无显著背离。")

# --- 启动 ---
run_omega()
run_dynamic_decision()
