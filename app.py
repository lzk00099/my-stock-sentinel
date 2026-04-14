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
    """计算固定的日内 Pivot Points (基于前一交易日数据)"""
    try:
        # 确保 df 包含足够的数据行
        high_s = safe_get(df, ticker, "High")
        low_s = safe_get(df, ticker, "Low")
        close_s = safe_get(df, ticker, "Close")
        
        # 关键修改：必须取 iloc[-2] (昨日)，因为 iloc[-1] 在交易时段是变动的今日数据
        if len(close_s) >= 2:
            prev_h = high_s.iloc[-2]
            prev_l = low_s.iloc[-2]
            prev_c = close_s.iloc[-2]
        else:
            # 如果数据量不足，才退而求其次
            return 0, 0, 0, 0
            
        pivot = (prev_h + prev_l + prev_c) / 3
        r1 = (2 * pivot) - prev_l
        s1 = (2 * pivot) - prev_h
        r2 = pivot + (prev_h - prev_l)
        s2 = pivot - (prev_h - prev_l)
        
        return round(s1, 2), round(s2, 2), round(r1, 2), round(r2, 2)
    except Exception as e:
        return 0, 0, 0, 0

# --- 市场结构 analysis 工具 (增强版：修复期权墙 N/A) ---
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
        # 使用 yfinance Ticker 对象获取期权链
        t_obj = yf.Ticker(ticker_str)
        # 获取所有可用的到期日
        options_dates = t_obj.options
        if options_dates:
            # 自动选择最近的一个到期日（通常是 0DTE 或当周到期）
            target_exp = options_dates[0]
            opt = t_obj.option_chain(target_exp)
            
            # 提取最大未平仓合约 (Open Interest) 所在的行
            if not opt.calls.empty and 'openInterest' in opt.calls.columns:
                valid_calls = opt.calls.dropna(subset=['openInterest'])
                if not valid_calls.empty:
                    call_wall = valid_calls.loc[valid_calls['openInterest'].idxmax(), 'strike']
            
            if not opt.puts.empty and 'openInterest' in opt.puts.columns:
                valid_puts = opt.puts.dropna(subset=['openInterest'])
                if not valid_puts.empty:
                    put_wall = valid_puts.loc[valid_puts['openInterest'].idxmax(), 'strike']
    except Exception:
        pass
    
    return poc, call_wall, put_wall

# --- 核心引擎 1: Sentinel Omega (视觉增强版) ---
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
        vv_curr = vvix_s.iloc[-1] if not vvix_s.empty else 0
        t_curr = tnx_s.iloc[-1] if not tnx_s.empty else 0
        
        # 计算 VVIX 斜率
        vvix_clean = vvix_s.tail(10).dropna()
        vv_slope = np.polyfit(np.arange(len(vvix_clean)), vvix_clean.values, 1)[0] if len(vvix_clean) > 1 else 0
        slope_desc = "↗️ 升温" if vv_slope > 0.1 else "↘️ 降温" if vv_slope < -0.1 else "➡️ 平稳"
        
        # VIX 颜色与评级逻辑
# 在计算 vix_color 前，强制确保 v_curr 是浮点数
        v_curr = float(vix_s.iloc[-1]) if not vix_s.empty else 0.0

# 逻辑检查：确保你的判断区间没有死角
        if v_curr < 15.0:
            vix_color, vix_rank = "#10b981", "【安全 · 忽略尾部风险】"
        elif 15.0 <= v_curr < 20.0:
            vix_color, vix_rank = "#facc15", "【防守 · 波动率回归中】"
        elif 20.0 <= v_curr < 28.0:
            vix_color, vix_rank = "#fb923c", "【警惕 · 市场对冲升温】"
        else:
            vix_color, vix_rank = "#ef4444", "【恐慌 · 极端情绪爆发】"
        
        risk_status = "🔴 避险模式 (Risk-Off)" if v_curr > 22 or vv_slope > 0.3 else "🟢 积极模式 (Risk-On)"
        
        # 渲染顶层指标
# --- 修复后的渲染部分 ---
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 使用 container 保证样式隔离
            st.markdown(f"**VIX 指数**")
            # 这里的 color 样式一定要确保 v_curr 变化时重新生成
            st.markdown(
                f"""<div style="background-color: {vix_color}22; padding: 5px; border-radius: 5px;">
                    <h2 style='color:{vix_color}; margin:0;'>{v_curr:.2f}</h2>
                </div>""", 
                unsafe_allow_html=True
            )
            st.caption(f"{vix_rank}")
            
        with col2:
            st.metric("10Y 美债收益率", f"{t_curr:.2f}%")
            
        with col3:
            st.markdown("**VVIX 指数**")
            # 1. 增加异常值处理：如果获取到的是 NaN 或 0，给出提示
            if vv_curr > 0:
                # 2. 尝试使用 st.metric 作为 fallback，如果 markdown 依然失效
                # 先用 HTML 渲染大字
                st.markdown(f"<h2 style='margin:0; color:#ffffff;'>{vv_curr:.2f}</h2>", unsafe_allow_html=True)
            else:
                # 如果数据源没拿到数，显示 N/A
                st.markdown("<h2 style='margin:0; color:gray;'>N/A</h2>", unsafe_allow_html=True)
            
            st.caption(f"趋势: {slope_desc}")
            
        with col4:
            # 风险偏好建议使用带有颜色的 markdown 而非简单的 metric
            pref_color = "#ef4444" if "🔴" in risk_status else "#10b981"
            st.markdown(f"**风险偏好总评**")
            st.markdown(f"<span style='color:{pref_color}; font-weight:bold;'>{risk_status}</span>", unsafe_allow_html=True)

        # --- 资产诊断报告 (保持原有逻辑) ---
        reports = []
        for symbol, name in assets.items():
            c_30, c_5, v_5 = safe_get(data_30m, symbol, "Close"), safe_get(data_5m, symbol, "Close"), safe_get(data_5m, symbol, "Volume")
            if len(c_30) < 20 or c_5.empty: continue
            
            curr_p = c_5.iloc[-1]
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

        # --- 专家情报 ---
        st.markdown("#### 🤖 Sentinel Omega 专家情报")
        notes = []
        if not dx_s.empty and len(dx_s) >= 5:
            if dx_s.iloc[-1] > dx_s.iloc[-5]:
                notes.append("💵 **美元压制**：美元指数日内走强，对风险资产构成估值压力。")
        
        btc_s = [r for r in reports if "BTC-USD" in r['标的']]
        if btc_s and "🚀 强力多头" not in btc_s[0]['诊断结论']:
            notes.append("₿ **流动性预警**：比特币动能不足，暗示场内投机资金相对谨慎。")
            
        if v_curr > 20:
            notes.append(f"🚨 **中高波环境**：VIX 处于 {v_curr:.2f}，此时操作应严格执行止损计划。")

        if notes:
            for n in notes: st.info(n)
        else:
            st.success("✅ 全球宏观走势平稳，多空博弈处于平衡区间。")

# --- 核心引擎 2: Sentinel V12.4 Pro ---
SECTOR_ETFS = {
    "XLK": "科技", "XLV": "医疗", "XLF": "金融", "XLY": "消费", 
    "XLI": "工业", "XLP": "必选", "XLE": "能源", "XLB": "材料"
}
INDEX_TICKERS = ["QQQ", "SPY", "IWM", "DIA"]
@st.fragment(run_every=60)
def run_v10_pro():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V12.4 Pro | 全维度结构与期权决策终端")
    targets = {"QQQ": "纳指100", "SPY": "标普500", "IWM": "罗素2000", "DIA": "道琼斯", "NVDA": "英伟达"}
    all_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"]

@st.fragment(run_every=60)
def run_v10_pro():
    # ... 前置代码 (get_market_times 等) ...
    
    # 统一获取看板所需数据 (增加 20 日均线所需长度)
    all_monitor_tickers = list(targets.keys()) + ["^VIX", "^VVIX", "^TNX"] + list(SECTOR_ETFS.keys())
    data_monitor = yf.download(all_monitor_tickers, period="30d", interval="1d", progress=False)
    
    # --- 看板计算逻辑 ---
    # 1. VIX & VVIX 处理
    vix_s = data_monitor["Close"]["^VIX"].dropna()
    vvix_s = data_monitor["Close"]["^VVIX"].dropna()
    v_curr = vix_s.iloc[-1] if not vix_s.empty else 0
    
    # VVIX 斜率 (取最近 5 日)
    vv_slope = np.polyfit(np.arange(5), vvix_s.tail(5).values, 1)[0] if len(vvix_s) >= 5 else 0
    vv_desc = "↗️ 升温" if vv_slope > 0.1 else "↘️ 降温" if vv_slope < -0.1 else "➡️ 平稳"
    
    vix_color = "#10b981" if v_curr < 18 else "#facc15" if v_curr < 25 else "#ef4444"
    
    # 2. 市场宽度 (8大行业站上 20MA 比例)
    breadth_count = 0
    for etf in SECTOR_ETFS.keys():
        prices = data_monitor["Close"][etf].dropna()
        if len(prices) >= 20:
            ma20 = prices.rolling(20).mean().iloc[-1]
            if prices.iloc[-1] > ma20:
                breadth_count += 1
    breadth_pct = breadth_count / len(SECTOR_ETFS)
    
    # 3. 指数共振 (QQQ, SPY, IWM, DIA 日内/短线方向)
    up_indices = 0
    for idx in INDEX_TICKERS:
        p = data_monitor["Close"][idx].dropna()
        if len(p) >= 2 and p.iloc[-1] > p.iloc[-2]: # 简单昨日共振逻辑
            up_indices += 1
    resonance_desc = "🔥 全线共振" if up_indices == 4 else "横盘分化" if up_indices >= 2 else "❄️ 普跌压制"

    # --- UI 渲染部分 (非交易时段也显示) ---
    st.markdown("### 📊 Sentinel 全球宏观仪表盘")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    
    with m_col1:
        st.markdown(f"**VIX 恐慌指数**")
        st.markdown(f"<h2 style='color:{vix_color}; margin:0;'>{v_curr:.2f}</h2>", unsafe_allow_html=True)
        st.caption("波动率环境评分")
        
    with m_col2:
        st.markdown(f"**VVIX 速率**")
        st.markdown(f"<h2 style='margin:0;'>{vvix_s.iloc[-1]:.2f}</h2>", unsafe_allow_html=True)
        st.caption(f"趋势: {vv_desc}")
        
    with m_col3:
        # 市场宽度进度条
        st.markdown("**市场宽度 (Sector > 20MA)**")
        st.progress(breadth_pct)
        st.caption(f"行业多头占比: {breadth_pct:.0%}")
        
    with m_col4:
        st.markdown("**四大指数共振**")
        res_color = "#10b981" if up_indices >= 3 else "#ef4444" if up_indices <= 1 else "#facc15"
        st.markdown(f"<h3 style='color:{res_color}; margin:0;'>{resonance_desc}</h3>", unsafe_allow_html=True)
        st.caption(f"上涨指数数量: {up_indices}/4")

    # --- 原始非交易/交易逻辑 ---
    if not is_market_open():
        st.info("🌙 市场已关闭 - 仪表盘保持实时静态分析")
        # ... 保持你原有的倒计时和 summary table ...
        return

    # ... 进入交易时段逻辑 (run_v12_pro 剩余部分) ...
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
    data_daily = yf.download(all_tickers, period="5d", interval="1d", progress=False, auto_adjust=True)
    # 宏观斜率计算 (增加安全检查)
    tnx_5m = get_col(data_5m, "^TNX", "Close").tail(10).dropna()
    tnx_slope = np.polyfit(np.arange(len(tnx_5m)), tnx_5m.values, 1)[0] if len(tnx_5m) > 1 else 0
    vvix_5m = get_col(data_5m, "^VVIX", "Close").tail(10).dropna()
    vvix_intra_slope = np.polyfit(np.arange(len(vvix_5m)), vvix_5m.values, 1)[0] if len(vvix_5m) > 1 else 0
    # VIX 标量获取 (防止 ValueError)
    # --- 极致稳健的 VIX 获取逻辑 ---
    vix_df = yf.download("^VIX", period="1d", progress=False)
    vix_val = 20.0 # 默认值
    if not vix_df.empty:
        try:
            # 无论 yfinance 返回的是单层还是多层索引，使用 .values.flatten() 都能拿到纯数值阵列
            vix_raw = vix_df["Close"].values.flatten()
            # 过滤掉 nan 并取最后一个有效值
            vix_valid = vix_raw[~np.isnan(vix_raw)]
            if len(vix_valid) > 0:
                vix_val = float(vix_valid[-1])
        except Exception:
            vix_val = 20.0
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

# --- 核心引擎 3: Sentinel V7.2 全维强度看板 ---
@st.fragment(run_every=600)
def run_v7_sector():
    st.markdown("---")
    st.markdown("### 🏛️ Sentinel V7.2 全维强度看板")
    
    sector_clusters = {
        "核能能源": "URA", "太空航天": "ITA", "AI半导体": "SMH",
        "半导体设备": "SOXX", "加密金融": "BITO", "电力基建": "XLU",
        "软件SaaS": "IGV", "生物医药": "IBB", "传统银行": "KBE",
        "石油能源": "XLE", "黄金避险": "GLD", "中概互联": "KWEB",
        "网络安全": "CIBR", "机器人自动化": "BOTZ", "工业制造": "XLI",
        "基础材料": "XLB", "零售消费": "XRT", "区域银行": "KRE",
        "房地产": "XLRE", "铜矿资源": "COPX", "白银实物": "SLV",
        "稀土战略": "REMX", "必需消费": "XLP", "电信媒体": "XLC",
        "旅游博彩": "PEJ", "清洁能源": "ICLN", "清洁能源科技": "QCLN",
        "医疗保健": "XLV"
    }
    
    leveraged_keywords = ['SOXL', 'SOXS', 'TQQQ', 'SQQQ', 'LABU', 'LABD', 'FAS', 'FAZ', 'AGQ', 'ZSL']
    all_tickers = list(sector_clusters.values())
    
    data_daily = yf.download(all_tickers, period="60d", interval="1d", progress=False, auto_adjust=True)
    if data_daily.empty:
        st.error("❌ 引擎 3 信号中断")
        return

    close_df = data_daily['Close']
    sector_results = []
    
    for name, ticker in sector_clusters.items():
        if ticker in leveraged_keywords: continue
        try:
            series = close_df[ticker].dropna()
            if len(series) < 22: continue
            
            day_ret = (series.iloc[-1] / series.iloc[-2]) - 1
            month_ret = (series.iloc[-1] / series.iloc[-21]) - 1
            
            sector_results.append({
                "赛道": f"{name} ({ticker})",
                "今日涨跌": day_ret,
                "当月涨跌": month_ret
            })
        except: continue

    df_all = pd.DataFrame(sector_results)
    
    def format_v7_table(df, col):
        # 转换百分比并添加颜色
        styled_df = df[['赛道', col]].copy()
        styled_df[col] = styled_df[col].apply(lambda x: f"<span style='color:{'#2ecc71' if x>0 else '#e74c3c'}; font-weight:bold;'>{x:+.2%}</span>")
        return styled_df.to_html(escape=False, index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🔥 今日领涨 Top 5**")
        st.write(format_v7_table(df_all.nlargest(5, '今日涨跌'), '今日涨跌'), unsafe_allow_html=True)
        st.markdown("**🏆 月度最强 Top 5**")
        st.write(format_v7_table(df_all.nlargest(5, '当月涨跌'), '当月涨跌'), unsafe_allow_html=True)
        
    with col2:
        st.markdown("**❄️ 今日领跌 Top 5**")
        st.write(format_v7_table(df_all.nsmallest(5, '今日涨跌'), '今日涨跌'), unsafe_allow_html=True)
        st.markdown("**📉 月度最弱 Top 5**")
        st.write(format_v7_table(df_all.nsmallest(5, '当月涨跌'), '当月涨跌'), unsafe_allow_html=True)

# --- 核心引擎 4: Sentinel 前沿科技雷达 ---
@st.fragment(run_every=900)
def run_frontier_radar():
    st.markdown("---")
    st.markdown(f"### 🏆 前沿科技潜力雷达 | {datetime.now().strftime('%Y-%m-%d')}")
    
    frontier_pool = {
        'AIPO': 'AI电力需求','ARKQ': '自动驾驶/机器人','ARKX': '太空探索','DRNZ': '无人机/国防',
        'DTCR': '数据中心REITs','GRID': '智能电网','NLR': '全球核电','NUKZ': '下一代核能',
        'PPA': '国防航空','QTUM': '量子计算','ROBO': '具身智能','SMH': 'AI芯片',
        'SOXX': '半导体全链','TCAI': 'AI基础设施', 'URNM': '铀矿与核燃料',
        'XAR': '航空制造','TAN': '太阳能','PBW': '绿色能源'
    }

    tickers = list(frontier_pool.keys()) + ['SPY', 'QQQ']
    raw_data = yf.download(tickers, period='7mo', auto_adjust=True, progress=False)
    if raw_data.empty: return
    
    close_data = raw_data['Close']
    today_return = close_data.pct_change().iloc[-1]
    m1_return = close_data.pct_change(21).iloc[-1]
    m3_return = close_data.pct_change(63).iloc[-1]
    volatility = close_data.pct_change().std() * np.sqrt(252)

    results = []
    for ticker, name in frontier_pool.items():
        # 潜力得分 = ((1月涨幅*0.7) + (3月涨幅*0.3)) / 年化波动
        score = ((m1_return[ticker] * 0.7) + (m3_return[ticker] * 0.3)) / volatility[ticker]
        results.append({
            '代码': ticker, '行业领域': name, '今日涨幅': today_return[ticker],
            '最近1月涨幅': m1_return[ticker], '相对SPY': m1_return[ticker] - m1_return['SPY'],
            '年化波动': volatility[ticker], '潜力得分': score
        })

    df = pd.DataFrame(results).sort_values(by='潜力得分', ascending=False).head(10)

    # 样式处理
    def color_val(v):
        color = "#2ecc71" if v > 0 else "#e74c3c"
        return f"color: {color}; font-weight: bold;"

    st.dataframe(
        df.style.format({
            '今日涨幅': '{:.2%}', '最近1月涨幅': '{:.2%}', '相对SPY': '{:+.2%}',
            '年化波动': '{:.2%}', '潜力得分': '{:.4f}'
        }).map(color_val, subset=['今日涨幅', '最近1月涨幅', '相对SPY'])
          .background_gradient(subset=['潜力得分'], cmap='Blues'),
        use_container_width=True,
        hide_index=True
    )

# 5. 快速诊断结论 
    top_1 = df.iloc[0]['代码']
    st.success(f"✅ **扫描结果**：当前核心标的为 【{top_1}】。绿色代表多头动能，红色代表近期回调。")

# --- 启动运行 ---
yf.download.cache_clear()
run_omega()  
run_v10_pro()
run_v7_sector()
run_frontier_radar()
