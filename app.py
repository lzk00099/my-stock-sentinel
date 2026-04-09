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

# --- 数据获取工具函数 (安全性增强版) ---
def safe_get(df, ticker, col):
    """通用安全获取函数"""
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if col in df.columns.levels[0] and ticker in df.columns.levels[1]:
                s = df[col][ticker].dropna()
                return s
        else:
            if col in df.columns:
                return df[col].dropna()
        return pd.Series(dtype='float64')
    except:
        return pd.Series(dtype='float64')

def get_col(df, ticker, col_name):
    """修正 KeyError 的核心逻辑"""
    try:
        if isinstance(df.columns, pd.MultiIndex):
            # 必须同时检查 第一层(列名) 和 第二层(代码)
            if col_name in df.columns.get_level_values(0) and ticker in df.columns.get_level_values(1):
                return df[col_name][ticker].dropna()
        else:
            if col_name in df.columns:
                return df[col_name].dropna()
    except Exception:
        pass
    return pd.Series(dtype='float64')

def calculate_pivots_full(df, ticker):
    """计算多层 Pivot Points (S1, S2, R1, R2)"""
    try:
        high_s = safe_get(df, ticker, "High")
        low_s = safe_get(df, ticker, "Low")
        close_s = safe_get(df, ticker, "Close")
        
        if high_s.empty or low_s.empty or close_s.empty:
            return 0, 0, 0, 0
            
        high = high_s.iloc[-1]
        low = low_s.iloc[-1]
        close = close_s.iloc[-1]
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        return round(s1, 2), round(s2, 2), round(r1, 2), round(r2, 2)
    except:
        return 0, 0, 0, 0

# --- 市场结构 analysis 工具 ---
def get_market_structure(ticker_str, df_5m):
    poc = 0
    try:
        bins = 20
        temp_df_close = get_col(df_5m, ticker_str, "Close")
        temp_df_vol = get_col(df_5m, ticker_str, "Volume")
        
        if not temp_df_close.empty and not temp_df_vol.empty:
            combined = pd.DataFrame({'Close': temp_df_close, 'Volume': temp_df_vol}).dropna()
            combined['bin'] = pd.cut(combined['Close'], bins=bins)
            poc_bin = combined.groupby('bin', observed=True)['Volume'].sum().idxmax()
            poc = round(poc_bin.mid, 2)
    except: poc = 0

    call_wall, put_wall = 0, 0
    try:
        t_obj = yf.Ticker(ticker_str)
        exp = t_obj.options[0]
        opt = t_obj.option_chain(exp)
        call_wall = opt.calls.loc[opt.calls['openInterest'].idxmax(), 'strike']
        put_wall = opt.puts.loc[opt.puts['openInterest'].idxmax(), 'strike']
    except: pass
    
    return poc, call_wall, put_wall

# --- 核心引擎 1: Sentinel Omega ---
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
        
        vvix_clean = vvix_s.tail(10).dropna()
        vv_slope = np.polyfit(np.arange(len(vvix_clean)), vvix_clean.values, 1)[0] if len(vvix_clean) > 1 else 0
        
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
            # 计算时确保没有 NaN
            valid_v5 = v_5.replace(0, np.nan).fillna(1)
            curr_vwap = (c_5 * v_5).cumsum() / v_5.cumsum()
            curr_vwap_val = curr_vwap.iloc[-1] if not curr_vwap.empty else c_5.mean()
            
            macd = ta.macd(c_30)
            rsi = ta.rsi(c_30)
            
            if macd is None or rsi is None or rsi.empty: continue
            
            score = (1 if curr_p > curr_vwap_val else 0) + (1 if macd.iloc[-1,0] > macd.iloc[-1,2] else 0) + (1 if rsi.iloc[-1] > 50 else 0)
            
            s1, _, r1, _ = calculate_pivots_full(data_daily, symbol)
            sig = "🚀 强力多头" if score == 3 else "📉 空头占优" if score == 0 else "⚖️ 中性震荡"
            
            reports.append({
                "标的": symbol, "名称": name, "最新价": round(curr_p, 2), 
                "关键位 (S1|R1)": f"S:{s1} | R:{r1}", 
                "RSI": round(rsi.iloc[-1], 1), "诊断结论": sig
            })
        
        if reports:
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

# --- 核心引擎 2: Sentinel V12.4 Pro ---
@st.fragment(run_every=60)
def run_v10_pro():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V12.4 Pro | 全维度结构与期权决策终端")
    
    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "DIA": "道琼斯", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]
    
    now, open_time, countdown = get_market_times()

    if not is_market_open():
        st.warning(f"🌙 当前非交易时段。系统进入休眠模式。")
        hours, remainder = divmod(int(countdown.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        st.subheader(f"⏳ 距离美股开盘还有: {hours}小时 {minutes}分")
        
        last_close_data = yf.download(all_tickers, period="2d", interval="1d", progress=False)
        if not last_close_data.empty:
            summary = []
            for t in targets.keys():
                closes = get_col(last_close_data, t, "Close")
                if len(closes) >= 2:
                    last_p = closes.iloc[-1]
                    prev_p = closes.iloc[-2]
                    chg = (last_p / prev_p) - 1
                    summary.append({"代码": t, "名称": targets[t], "收盘价": round(last_p, 2), "涨跌幅": f"{chg:+.2%}"})
            if summary:
                st.table(pd.DataFrame(summary))
        return

    # 交易时段逻辑
    data_5m = yf.download(all_tickers, period="5d", interval="5m", progress=False, auto_adjust=True)
    data_daily = yf.download(all_tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
    
    # 宏观斜率计算 (增加安全检查)
    tnx_5m = get_col(data_5m, "^TNX", "Close").tail(10).dropna()
    tnx_slope = np.polyfit(np.arange(len(tnx_5m)), tnx_5m.values, 1)[0] if len(tnx_5m) > 1 else 0
    
    vvix_5m = get_col(data_5m, "^VVIX", "Close").tail(10).dropna()
    vvix_intra_slope = np.polyfit(np.arange(len(vvix_5m)), vvix_5m.values, 1)[0] if len(vvix_5m) > 1 else 0
    
    # VIX 标量获取 (防止 ValueError)
    vix_df = yf.download("^VIX", period="1d", progress=False)
    vix_val = float(vix_df["Close"].iloc[-1]) if not vix_df.empty else 20.0

    v12_reports = []
    audit_data = []

    for t in targets.keys():
        c_5 = get_col(data_5m, t, "Close")
        v_5 = get_col(data_5m, t, "Volume")
        if c_5.empty: continue
        
        curr_p = c_5.iloc[-1]
        vwap_series = (c_5 * v_5).cumsum() / v_5.cumsum()
        c_vwap = vwap_series.iloc[-1]
        
        bias = (curr_p / c_vwap) - 1
        
        prev_close_series = get_col(data_daily, t, "Close")
        prev_c = prev_close_series.iloc[-2] if len(prev_close_series) >= 2 else curr_p
        
        if curr_p > prev_c and curr_p > c_vwap:
            structure = "🚀 强势突破"
        elif curr_p > c_vwap:
            structure = "🩹 超跌反弹"
        else:
            structure = "📉 弱势运行"
            
        # 量价背离分析
        tail_data = c_5.tail(5).dropna()
        vol_tail = v_5.tail(5).dropna()
        if len(tail_data) >= 2 and len(vol_tail) >= 2:
            p_slope = np.polyfit(np.arange(len(tail_data)), tail_data.values, 1)[0]
            vol_slope = np.polyfit(np.arange(len(vol_tail)), vol_tail.values, 1)[0]
            is_div = p_slope > 0 and vol_slope < 0
        else:
            is_div = False
        
        poc, call_wall, put_wall = get_market_structure(t, data_5m)
        s1, s2, r1, r2 = calculate_pivots_full(data_daily, t)
        
        # Squeeze 变盘判定
        is_sqz = False
        try:
            bb = ta.bbands(c_5, length=20, std=2)
            high_col = get_col(data_5m, t, "High")
            low_col = get_col(data_5m, t, "Low")
            kc = ta.kc(high_col, low_col, c_5, length=20)
            if bb is not None and kc is not None:
                is_sqz = (bb.iloc[-1, 2] - bb.iloc[-1, 0]) < (kc.iloc[-1, 2] - kc.iloc[-1, 0])
        except: pass

        # 综合决策评分
        score = (1 if curr_p > c_vwap else 0) + (1 if curr_p > poc and poc != 0 else 0) + (1 if vvix_intra_slope < 0 else 0)
        
        if is_div and curr_p > c_vwap:
            decision = "🚫 <b style='color:#ef4444;'>诱多 (背离)</b>"
        elif score >= 3:
            decision = "🎯 <b style='color:#10b981;'>CALL (爆发)</b>"
        elif is_sqz:
            decision = "⚡ <b style='color:#a855f7;'>SQUEEZE</b>"
        else:
            decision = "☕ 观望"

        v12_reports.append({
            "代码": t, "现价": round(curr_p, 2), "结构": structure, "VWAP乖离": f"{bias:+.2%}",
            "量价": "⚠️背离" if is_div else "✅同步", "POC(引力)": poc,
            "期权墙(C|P)": f"{call_wall} | {put_wall}" if call_wall != 0 else "N/A",
            "支撑 S1/S2": f"{s1} / {s2}", "阻力 R1/R2": f"{r1} / {r2}", "决策": decision
        })
        
        audit_data.append({
            "code": t, "curr_p": curr_p, "poc": poc, "cw": call_wall, "pw": put_wall, 
            "is_sqz": is_sqz, "prev_c": prev_c, "r1": r1, "s1": s1, "decision": decision, "structure": structure
        })

    st.write(pd.DataFrame(v12_reports).to_html(escape=False, index=False), unsafe_allow_html=True)

    st.markdown("#### 🤖 Sentinel 战术全维度审计 (Hybrid Pro)")
    for a in audit_data:
        with st.expander(f"查看 {a['code']} 深度审计报告", expanded=True):
            if "诱多" in a['decision']:
                st.error(f"🚫 **性质警告**：典型诱多结构。价格上涨但量能枯竭，且 POC **{a['poc']}** 存在强烈向下引力。")
            if "反弹" in a['structure']:
                st.info(f"🩹 **位阶提示**：目前价格 ({a['curr_p']}) 未收复昨收线 ({a['prev_c']})，仅按反弹对待。")
            if a['is_sqz']:
                st.warning(f"⚡ **爆发预警**：布林带收口至极限。若放量站上 R1 (**{a['r1']}**) 则是日内强拉开端。")
            if a['cw'] != 0 and abs(a['curr_p'] - a['cw']) / a['cw'] < 0.005:
                st.error(f"🧱 **压力警告**：现价极度逼近期权 Call 墙 (**{a['cw']}**)，预计此处有机构级抛压。")
            if a['poc'] != 0 and abs(a['curr_p'] - a['poc']) / a['poc'] < 0.0015:
                st.info(f"⚓ **磁吸效应**：价格锁定在筹码 POC **{a['poc']}**。多空均衡，需等待放量打破。")
            if a['curr_p'] < a['s1'] and a['s1'] != 0:
                st.error(f"⚠️ **趋势转弱**：跌破 S1 支撑位，警惕向下方期权 Put 墙 (**{a['pw']}**) 回撤的风险。")
            
            # 使用 float(vix_val) 确保比较安全
            if vix_val > 30 and "CALL" in a['decision']:
                st.warning(f"🎭 **策略对冲**：当前 VIX ({vix_val:.2f}) 极高，建议使用 Spread (价差) 代替单腿买入。")

# --- 启动运行 ---
run_omega()
run_v10_pro()
