import os
import re
import time
import hashlib
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import ta
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="FAHAD.AI", layout="wide", initial_sidebar_state="expanded")

DEFAULT_WATCHLIST = [
    ("الراجحي", "1120.SR"),
    ("أرامكو", "2222.SR"),
    ("سابك", "2010.SR"),
    ("STC", "7010.SR"),
    ("الأهلي", "1180.SR"),
]

SAUDI_EXCHANGE_ISSUER_DIRECTORY_URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/trading/participants-directory/issuer-directory"
)

def _rtl_style():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
        html, body, [class*="st-"] { font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; }
        .hint { color: #475569; font-size: 0.9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        key = None
    if not key:
        key = os.environ.get("GEMINI_API_KEY")
    return str(key).strip() if key else None

def _extract_ticker_frame(download_df, ticker):
    if download_df is None or getattr(download_df, "empty", True):
        return None
    df = download_df
    if isinstance(df.columns, pd.MultiIndex):
        lvl0 = [str(x) for x in df.columns.get_level_values(0)]
        lvl1 = [str(x) for x in df.columns.get_level_values(1)]

        # حالة 1: المستوى الأول رموز الأسهم
        if ticker in lvl0:
            df = df[ticker]
        # حالة 2: المستوى الثاني رموز الأسهم (بعض نسخ yfinance)
        elif ticker in lvl1:
            try:
                # استخراج أعمدة السهم من المستوى الثاني ثم تسوية الأسماء
                sub = df.xs(ticker, axis=1, level=1)
                df = sub
            except Exception:
                return None
        else:
            return None
    df = df.copy()
    df.columns = [str(c).capitalize() for c in df.columns]
    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns:
            return None
    df = df.dropna(subset=["Close"])
    return df if not df.empty else None

def _add_indicators(df):
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"] if "Volume" in df.columns else None

    df["SMA20"] = ta.trend.sma_indicator(close, window=20)
    df["SMA50"] = ta.trend.sma_indicator(close, window=50)
    df["EMA20"] = ta.trend.ema_indicator(close, window=20)
    df["EMA50"] = ta.trend.ema_indicator(close, window=50)
    df["EMA200"] = ta.trend.ema_indicator(close, window=200)

    df["RSI"] = ta.momentum.rsi(close, window=14)
    df["ROC"] = ta.momentum.roc(close, window=10)
    df["WILLR"] = ta.momentum.williams_r(high, low, close, lbp=14)
    df["CCI"] = ta.trend.cci(high, low, close, window=20)

    macd = ta.trend.MACD(close)
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_DIFF"] = macd.macd_diff()

    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    df["STOCH_K"] = stoch.stoch()
    df["STOCH_D"] = stoch.stoch_signal()

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["BB_MID"] = bb.bollinger_mavg()
    df["BB_UP"] = bb.bollinger_hband()
    df["BB_LOW"] = bb.bollinger_lband()
    df["BB_WIDTH"] = (df["BB_UP"] - df["BB_LOW"]) / df["BB_MID"]

    df["ATR"] = ta.volatility.average_true_range(high, low, close, window=14)
    adx = ta.trend.ADXIndicator(high, low, close, window=14)
    df["ADX"] = adx.adx()
    df["DI_POS"] = adx.adx_pos()
    df["DI_NEG"] = adx.adx_neg()

    psar = ta.trend.PSARIndicator(high, low, close)
    df["PSAR"] = psar.psar()

    ichi = ta.trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
    df["ICHIMOKU_A"] = ichi.ichimoku_a()
    df["ICHIMOKU_B"] = ichi.ichimoku_b()
    df["ICHIMOKU_BASE"] = ichi.ichimoku_base_line()
    df["ICHIMOKU_CONV"] = ichi.ichimoku_conversion_line()

    if volume is not None:
        df["OBV"] = ta.volume.on_balance_volume(close, volume)
        df["MFI"] = ta.volume.money_flow_index(high, low, close, volume, window=14)
        vwap = ta.volume.volume_weighted_average_price(high, low, close, volume, window=14)
        df["VWAP"] = vwap

    return df

def _score_opportunity(df):
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    reasons = []
    score = 0

    ema20 = float(last.get("EMA20", float("nan")))
    ema50 = float(last.get("EMA50", float("nan")))
    close = float(last["Close"])
    rsi = float(last.get("RSI", 50.0))
    atr = float(last.get("ATR", 0.0) or 0.0)

    trend_up = pd.notna(ema20) and pd.notna(ema50) and ema20 > ema50 and close > ema20
    if trend_up:
        score += 2
        reasons.append("اتجاه صاعد (EMA20 فوق EMA50 والسعر فوق EMA20)")

    macd_diff = last.get("MACD_DIFF")
    if pd.notna(macd_diff) and float(macd_diff) > 0:
        score += 1
        reasons.append("زخم إيجابي (MACD_DIFF > 0)")

    pullback = trend_up and abs(close - ema20) / close < 0.01 and 40 <= rsi <= 60
    if pullback:
        score += 2
        reasons.append("ارتداد للمتوسط (Pullback قرب EMA20 مع RSI متوازن)")

    bb_low = last.get("BB_LOW")
    if pd.notna(bb_low) and close < float(bb_low) and rsi < 30:
        score += 2
        reasons.append("تشبع بيعي (السعر تحت Bollinger Low و RSI < 30)")

    vol_ok = False
    if "Volume" in df.columns:
        vol = float(last.get("Volume", 0.0) or 0.0)
        vol_avg = float(df["Volume"].tail(20).mean()) if df["Volume"].tail(20).notna().any() else 0.0
        vol_ok = vol_avg > 0 and vol >= vol_avg * 1.5
        if vol_ok:
            score += 1
            reasons.append("زيادة سيولة (الحجم أعلى من متوسط 20 يوم)")

    breakout = False
    if len(df) >= 21:
        hh20 = float(df["High"].tail(21).max())
        breakout = close >= hh20 * 0.999
        if breakout and vol_ok:
            score += 2
            reasons.append("اختراق قريب (قمة 20 يوم مع سيولة)")

    adx = last.get("ADX")
    if pd.notna(adx) and float(adx) >= 20:
        score += 1
        reasons.append("قوة اتجاه (ADX >= 20)")

    if score >= 6:
        label = "🔥 فرصة مضاربية قوية"
    elif score >= 4:
        label = "✅ فرصة مضاربية"
    elif score >= 2:
        label = "⚠️ مراقبة"
    else:
        label = "⌛ لا إشارة واضحة"

    if atr and atr > 0:
        entry = close
        stop = close - atr * 1.5
        target1 = close + atr * 2.0
        target2 = close + atr * 3.0
    else:
        entry = close
        stop = close * 0.97
        target1 = close * 1.04
        target2 = close * 1.06

    return {
        "label": label,
        "score": int(score),
        "reasons": reasons,
        "entry": float(entry),
        "stop": float(stop),
        "target1": float(target1),
        "target2": float(target2),
    }

@st.cache_data(ttl=900)
def _download_tickers(tickers_tuple, period="5d", interval="1d"):
    tickers = list(tickers_tuple)
    return yf.download(
        tickers,
        period=period,
        interval=interval,
        progress=False,
        group_by="ticker",
        threads=False,
    )

def _safe_download(tickers, period="5d", interval="1d"):
    tickers_tuple = tuple(tickers)
    try:
        df = _download_tickers(tickers_tuple, period=period, interval=interval)
        if df is not None and not df.empty:
            st.session_state["last_good_download"] = df
        return df
    except Exception:
        return st.session_state.get("last_good_download")

def _mini_market_index(rows):
    if not rows:
        return None
    changes = [r["التغير %"] for r in rows if r.get("التغير %") is not None]
    if not changes:
        return None
    return sum(changes) / len(changes)

def _gemini_generate(prompt):
    now = time.time()
    block_until = float(st.session_state.get("ai_block_until", 0.0) or 0.0)
    if now < block_until:
        wait_s = int(max(1, block_until - now))
        return None, f"Rate Limit/Quota: تم إيقاف طلبات الذكاء الاصطناعي مؤقتاً بسبب الحصة. جرّب بعد {wait_s} ثانية."

    last_call = float(st.session_state.get("ai_last_call", 0.0) or 0.0)
    if now - last_call < 12:
        wait_s = int(max(1, 12 - (now - last_call)))
        return None, f"Rate Limit: انتظر {wait_s} ثواني ثم أعد المحاولة (لتقليل استهلاك الحصة)."

    api_key = _get_api_key()
    if not api_key:
        return None, 'أضف GEMINI_API_KEY داخل Secrets بهذا الشكل: GEMINI_API_KEY = "AIza..."'

    prompt_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    cache = st.session_state.get("ai_cache")
    if not isinstance(cache, dict):
        cache = {}
        st.session_state["ai_cache"] = cache
    cached = cache.get(prompt_key)
    if isinstance(cached, dict):
        ts = float(cached.get("ts", 0.0) or 0.0)
        txt = cached.get("text")
        if txt and (now - ts) < 3600:
            return txt, None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model_candidates = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        last_err = None
        for model in model_candidates:
            try:
                st.session_state["ai_last_call"] = now
                resp = client.models.generate_content(model=model, contents=prompt)
                text = getattr(resp, "text", None)
                if text:
                    cache[prompt_key] = {"ts": now, "text": text}
                    return text, None
                out = str(resp)
                cache[prompt_key] = {"ts": now, "text": out}
                return out, None
            except Exception as e:
                msg = str(e)
                last_err = e
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "exceeded your current quota" in msg or "quota" in msg:
                    st.session_state["ai_block_until"] = now + 90
                    return None, (
                        "تم تجاوز الحصة (Quota) أو الحد (Rate Limit) في Gemini.\n"
                        "الحل: فعّل Billing/الخطة في Google AI Studio أو انتظر حتى تتجدد الحصة.\n"
                        "ولتقليل الاستهلاك: لا تضغط زر الذكاء عدة مرات بسرعة، والتزم بانتظار 10–15 ثانية."
                    )
                if "404" in msg or "NOT_FOUND" in msg or "is not found" in msg or "ListModels" in msg:
                    continue
                raise

        msg = str(last_err).strip() if last_err else "Unknown error"
        msg = (msg[:240] + "…") if len(msg) > 240 else msg
        return None, f"ClientError: {msg}"
    except Exception as e:
        msg = str(e).strip()
        msg = (msg[:240] + "…") if len(msg) > 240 else msg
        return None, f"{type(e).__name__}: {msg}"

def _openrouter_generate(prompt):
    try:
        key = st.secrets.get("OPENROUTER_API_KEY")
    except Exception:
        key = None
    if not key:
        key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None, "OPENROUTER_API_KEY غير موجود في Secrets."

    try:
        model = st.secrets.get("OPENROUTER_MODEL", "qwen/qwen3-4b:free")
    except Exception:
        model = "qwen/qwen3-4b:free"

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "أنت مستشار فني عربي للسوق السعودي، مختصر ودقيق."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=25,
        )
        if resp.status_code >= 400:
            msg = f"HTTP {resp.status_code}: {resp.text[:220]}"
            if resp.status_code in (402, 429):
                return None, "تم تجاوز حد/رصيد OpenRouter. سيتم التحليل المحلي."
            return None, msg
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text, None
    except Exception as e:
        msg = str(e).strip()
        msg = (msg[:240] + "…") if len(msg) > 240 else msg
        return None, f"{type(e).__name__}: {msg}"

def _ai_generate(prompt, local_fallback_text):
    provider = st.session_state.get("ai_provider", "محلي مجاني")
    if provider == "محلي مجاني":
        return local_fallback_text, None
    if provider == "OpenRouter مجاني":
        text, err = _openrouter_generate(prompt)
        if err:
            return local_fallback_text, err
        return text, None
    text, err = _gemini_generate(prompt)
    if err:
        return local_fallback_text, err
    return text, None

def _is_quota_error(err_text):
    if not err_text:
        return False
    e = str(err_text)
    return any(k in e for k in ["RESOURCE_EXHAUSTED", "429", "quota", "Rate Limit", "الحصة"])

def _local_advisor_reply(name, ticker, price, rsi, opp, adx=0.0, atr=0.0, user_text=""):
    direction = "محايد"
    if opp["score"] >= 6:
        direction = "زخم مضاربي قوي"
    elif opp["score"] >= 4:
        direction = "فرصة مضاربية جيدة"
    elif opp["score"] >= 2:
        direction = "مراقبة قبل الدخول"
    text = (
        f"📌 تحليل محلي احتياطي للسهم {name} ({ticker})\n"
        f"- الاتجاه الحالي: {direction}\n"
        f"- درجة الفرصة: {opp['score']}/8 ({opp['label']})\n"
        f"- السعر: {price:.2f} | RSI: {rsi:.2f} | ADX: {adx:.2f} | ATR: {atr:.2f}\n"
        f"- دخول مقترح: {opp['entry']:.2f}\n"
        f"- وقف خسارة: {opp['stop']:.2f}\n"
        f"- الهدف 1: {opp['target1']:.2f}\n"
        f"- الهدف 2: {opp['target2']:.2f}\n"
    )
    if opp["reasons"]:
        text += "- أسباب الإشارة:\n"
        for r in opp["reasons"][:4]:
            text += f"  • {r}\n"
    if user_text:
        if "وقف" in user_text or "مخاطر" in user_text:
            text += "🛡️ إدارة المخاطر: لا تخاطر بأكثر من 1-2% من رأس المال في الصفقة.\n"
        if "دخول" in user_text:
            text += "🎯 الأفضل انتظار شمعة تأكيد فوق منطقة الدخول قبل التنفيذ.\n"
    text += "ℹ️ ملاحظة: هذا تحليل فني آلي وليس توصية استثمارية ملزمة."
    return text

@st.cache_data(ttl=86400)
def _get_full_market_tickers_from_saudi_exchange():
    try:
        raw = requests.get(
            SAUDI_EXCHANGE_ISSUER_DIRECTORY_URL,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,*/*",
            },
        ).text
    except Exception:
        return []

    tokens = re.findall(r"\b[A-Z0-9]{2,6}\b", raw)
    deny = {
        "HTML",
        "BODY",
        "DIV",
        "SPAN",
        "STYLE",
        "SCRIPT",
        "HTTP",
        "HTTPS",
        "WPS",
        "PORTAL",
        "SAUDI",
        "EXCHANGE",
        "ISSUER",
        "DIRECTORY",
        "MARKET",
        "DATA",
        "SAR",
        "USD",
        "ETF",
        "EOD",
    }

    symbols = []
    seen = set()
    for t in tokens:
        if t in deny:
            continue
        if t.startswith("WPS"):
            continue
        if t.endswith("SA"):
            continue
        if t not in seen:
            seen.add(t)
            symbols.append(t)

    tickers = []
    for s in symbols:
        if s == "TASI":
            continue
        tickers.append(f"{s}.SR")

    return tickers

def _get_full_market_tickers():
    try:
        raw = st.secrets.get("SAUDI_MARKET_TICKERS")
    except Exception:
        raw = None
    if raw:
        tickers = []
        for line in str(raw).replace(",", "\n").splitlines():
            t = line.strip()
            if not t:
                continue
            tickers.append(t)
        return tickers
    return _get_full_market_tickers_from_saudi_exchange()

@st.cache_data(ttl=3600)
def _download_many_tickers(tickers_tuple, period="90d", interval="1d"):
    tickers = list(tickers_tuple)
    return yf.download(
        tickers,
        period=period,
        interval=interval,
        progress=False,
        group_by="ticker",
        threads=False,
    )

def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]

def _render_dev_panel():
    if not st.session_state.get("dev_mode", False):
        return
    now = time.time()
    block_until = float(st.session_state.get("ai_block_until", 0.0) or 0.0)
    wait_ai = int(max(0, block_until - now))
    ai_cache = st.session_state.get("ai_cache")
    ai_cache_size = len(ai_cache) if isinstance(ai_cache, dict) else 0
    radar_cache = st.session_state.get("full_market_radar_cache")
    radar_rows = int(len(radar_cache)) if isinstance(radar_cache, pd.DataFrame) else 0
    radar_stats = st.session_state.get("radar_last_stats", {})

    with st.sidebar.expander("🛠️ Dev Mode", expanded=True):
        st.write(f"AI Provider: {st.session_state.get('ai_provider', 'محلي مجاني')}")
        st.write(f"AI Cache: {ai_cache_size}")
        st.write(f"AI Cooldown: {wait_ai}s")
        st.write(f"Radar Cache Rows: {radar_rows}")
        st.write(f"Tickers: {radar_stats.get('tickers', 0)}")
        st.write(f"Batches: {radar_stats.get('batches_with_data', 0)}/{radar_stats.get('batches_total', 0)}")
        st.write(f"Analyzed: {radar_stats.get('analyzed', 0)}")
        st.write(f"Qualified: {radar_stats.get('qualified', 0)}")
        if radar_stats.get("used_rescue"):
            st.warning("Rescue Mode Active")
        if radar_stats.get("used_cached"):
            st.info("Cached Radar Used")
        if st.button("مسح كاش الذكاء"):
            st.session_state["ai_cache"] = {}
            st.success("تم مسح كاش الذكاء")
        if st.button("مسح كاش الرادار"):
            st.session_state.pop("full_market_radar_cache", None)
            st.success("تم مسح كاش الرادار")

def page_dashboard():
    st.title("🏠 لوحة التحكم")
    st.markdown('<div class="hint">التحديث كل 15 دقيقة لتقليل الحظر من المصدر.</div>', unsafe_allow_html=True)

    watch = st.session_state.get("watchlist")
    if not watch:
        watch = DEFAULT_WATCHLIST
        st.session_state["watchlist"] = watch

    tickers = [t for _, t in watch]
    data = _safe_download(tickers, period="5d")

    if data is None or getattr(data, "empty", True):
        st.error("تعذر جلب البيانات حالياً (قد يكون Rate Limit). جرّب بعد دقائق.")
        return

    rows = []
    for name, ticker in watch:
        df = _extract_ticker_frame(data, ticker)
        if df is None or len(df) < 2:
            continue
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        chg = ((last - prev) / prev) * 100 if prev else None
        rows.append({"الشركة": name, "الرمز": ticker, "السعر": last, "التغير %": chg})

    if not rows:
        st.warning("لا توجد بيانات كافية حالياً لعرض السوق.")
        return

    df_res = pd.DataFrame(rows)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("📈 الأعلى صعوداً")
        st.dataframe(
            df_res.sort_values("التغير %", ascending=False).head(5).style.format({"السعر": "{:.2f}", "التغير %": "{:+.2f}%"}),
            hide_index=True,
            width="stretch",
        )
    with c2:
        st.subheader("📉 الأعلى هبوطاً")
        st.dataframe(
            df_res.sort_values("التغير %", ascending=True).head(5).style.format({"السعر": "{:.2f}", "التغير %": "{:+.2f}%"}),
            hide_index=True,
            width="stretch",
        )
    with c3:
        st.subheader("📊 مؤشر مصغّر")
        mini = _mini_market_index(rows)
        if mini is None:
            st.metric("حركة السوق", "—")
        else:
            st.metric("حركة السوق", "متوسط الأسهم", f"{mini:+.2f}%")

def page_analysis():
    st.title("📋 التحليل الفني")
    watch = st.session_state.get("watchlist") or DEFAULT_WATCHLIST
    name = st.selectbox("اختر السهم:", [n for n, _ in watch])
    ticker = dict(watch)[name]

    data = _safe_download([ticker], period="1y")
    df = _extract_ticker_frame(data, ticker) if data is not None else None
    if df is None or df.empty:
        st.error("لا توجد بيانات كافية لهذا السهم حالياً.")
        return

    df = df.copy()
    dfi = _add_indicators(df).dropna()
    if dfi is None or dfi.empty:
        st.error("تعذر حساب المؤشرات لهذا السهم حالياً.")
        return

    overlay = st.multiselect(
        "إظهار على الرسم:",
        options=["SMA20", "SMA50", "EMA20", "EMA50", "EMA200", "BB_UP", "BB_MID", "BB_LOW", "VWAP", "PSAR"],
        default=["EMA20", "EMA50", "BB_UP", "BB_MID", "BB_LOW"],
    )

    tab_price, tab_ind, tab_opps = st.tabs(["📈 الرسم", "📊 المؤشرات", "🎯 فرص مضاربية"])

    with tab_price:
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.60, 0.20, 0.20],
        )
        fig.add_trace(
            go.Candlestick(
                x=dfi.index,
                open=dfi["Open"],
                high=dfi["High"],
                low=dfi["Low"],
                close=dfi["Close"],
                name="السعر",
            ),
            row=1,
            col=1,
        )

        color_map = {
            "SMA20": "#0ea5e9",
            "SMA50": "#0284c7",
            "EMA20": "#22c55e",
            "EMA50": "#16a34a",
            "EMA200": "#6b7280",
            "BB_UP": "#7c3aed",
            "BB_MID": "#a855f7",
            "BB_LOW": "#7c3aed",
            "VWAP": "#f59e0b",
            "PSAR": "#ef4444",
        }

        for ind in overlay:
            if ind in dfi.columns and dfi[ind].notna().any():
                mode = "markers" if ind == "PSAR" else "lines"
                fig.add_trace(
                    go.Scatter(x=dfi.index, y=dfi[ind], mode=mode, name=ind, line=dict(color=color_map.get(ind))),
                    row=1,
                    col=1,
                )

        fig.add_trace(go.Scatter(x=dfi.index, y=dfi["RSI"], mode="lines", name="RSI", line=dict(color="#0f172a")), row=2, col=1)
        fig.add_hline(y=70, line_width=1, line_dash="dot", line_color="#ef4444", row=2, col=1)
        fig.add_hline(y=30, line_width=1, line_dash="dot", line_color="#22c55e", row=2, col=1)

        fig.add_trace(go.Bar(x=dfi.index, y=dfi["MACD_DIFF"], name="MACD_H", marker_color="#64748b"), row=3, col=1)
        fig.add_trace(go.Scatter(x=dfi.index, y=dfi["MACD"], mode="lines", name="MACD", line=dict(color="#2563eb")), row=3, col=1)
        fig.add_trace(go.Scatter(x=dfi.index, y=dfi["MACD_SIGNAL"], mode="lines", name="MACD_S", line=dict(color="#f97316")), row=3, col=1)

        fig.update_layout(template="plotly_white", height=780, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, width="stretch")

    with tab_ind:
        last = dfi.iloc[-1]
        cols = st.columns(4)
        cols[0].metric("RSI", f"{float(last['RSI']):.2f}")
        cols[1].metric("MACD_DIFF", f"{float(last['MACD_DIFF']):.3f}")
        cols[2].metric("ADX", f"{float(last['ADX']):.2f}")
        cols[3].metric("ATR", f"{float(last['ATR']):.2f}")

        show_cols = [
            "SMA20", "SMA50", "EMA20", "EMA50", "EMA200",
            "BB_UP", "BB_MID", "BB_LOW", "BB_WIDTH",
            "STOCH_K", "STOCH_D",
            "CCI", "MFI", "WILLR", "ROC",
            "DI_POS", "DI_NEG",
            "VWAP", "OBV", "PSAR",
            "ICHIMOKU_A", "ICHIMOKU_B", "ICHIMOKU_BASE", "ICHIMOKU_CONV",
        ]
        present = [c for c in show_cols if c in dfi.columns]
        ind_df = dfi[present].tail(60).copy()
        st.dataframe(ind_df, width="stretch")

    with tab_opps:
        opp = _score_opportunity(dfi)
        st.subheader(opp["label"])
        st.metric("درجة الفرصة", str(opp["score"]))
        st.write(f"سعر الدخول المقترح: {opp['entry']:.2f}")
        st.write(f"وقف الخسارة: {opp['stop']:.2f}")
        st.write(f"الهدف 1: {opp['target1']:.2f}")
        st.write(f"الهدف 2: {opp['target2']:.2f}")
        if opp["reasons"]:
            st.subheader("أسباب الإشارة")
            for r in opp["reasons"]:
                st.write(f"- {r}")

        if st.button("🤖 رأي AI"):
            price = float(dfi["Close"].iloc[-1])
            rsi = float(dfi["RSI"].iloc[-1])
            adx = float(dfi["ADX"].iloc[-1]) if "ADX" in dfi.columns else 0.0
            atr = float(dfi["ATR"].iloc[-1]) if "ATR" in dfi.columns else 0.0
            prompt = (
                f"حلل سهم {name} ({ticker}) في السوق السعودي. "
                f"السعر {price:.2f}، RSI {rsi:.2f}، "
                f"التوصية الآلية: {opp['label']} بدرجة {opp['score']}/8. "
                f"اقترح إدارة مخاطر ودخول/خروج مختصر."
            )
            local_text = _local_advisor_reply(name, ticker, price, rsi, opp, adx=adx, atr=atr)
            text, err = _ai_generate(prompt, local_text)
            if err:
                st.warning(err)
            st.info(text)

def page_radar():
    st.title("📡 الرادار")

    mode = st.radio("نطاق المسح:", ["قائمة المراقبة", "كامل السوق"], horizontal=True)
    min_score = st.slider("الحد الأدنى للدرجة:", min_value=0, max_value=8, value=2, step=1)
    max_results = st.slider("أقصى عدد نتائج للعرض:", min_value=20, max_value=200, value=60, step=10)
    use_cached = st.checkbox("استخدام آخر نتيجة محفوظة (أسرع وأقل استهلاكاً)", value=True)

    if mode == "قائمة المراقبة":
        watch = st.session_state.get("watchlist") or DEFAULT_WATCHLIST
        tickers = [t for _, t in watch]
        name_map = {t: n for n, t in watch}
    else:
        tickers = _get_full_market_tickers()
        name_map = {}

        if not tickers:
            st.error("تعذر تحميل قائمة كامل السوق. ضع SAUDI_MARKET_TICKERS في Secrets أو جرّب لاحقاً.")
            st.info("صيغة Secrets:\nSAUDI_MARKET_TICKERS = \"1120.SR\\n2222.SR\\n...\"")
            return

        st.caption(f"عدد الرموز المكتشفة: {len(tickers)}")
        st.info("تم تفعيل وضع كامل السوق مع حماية ضد Rate Limit عبر الدفعات + التخزين المؤقت.")

    if st.button("ابدأ المسح"):
        if mode == "كامل السوق" and use_cached:
            cached = st.session_state.get("full_market_radar_cache")
            if isinstance(cached, pd.DataFrame) and not cached.empty:
                st.success("تم عرض آخر نتيجة محفوظة لتقليل الاستهلاك.")
                st.session_state["radar_last_stats"] = {
                    "tickers": len(tickers),
                    "batches_with_data": 0,
                    "batches_total": 0,
                    "analyzed": 0,
                    "qualified": int(len(cached)),
                    "used_rescue": False,
                    "used_cached": True,
                }
                show_df = cached.sort_values(["الدرجة", "RSI"], ascending=[False, True]).head(max_results)
                st.dataframe(
                    show_df.style.format(
                        {
                            "السعر": "{:.2f}",
                            "RSI": "{:.2f}",
                            "دخول": "{:.2f}",
                            "وقف": "{:.2f}",
                            "هدف1": "{:.2f}",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                )
                return

        rows = []
        rows_all = []
        total_analyzed = 0
        batches_with_data = 0
        used_rescue = False
        progress = st.progress(0.0)

        batches = list(_chunk(tickers, 40))
        for bi, batch in enumerate(batches, start=1):
            data = None
            try:
                data = _download_many_tickers(tuple(batch), period="120d")
            except Exception:
                data = None

            if data is None or getattr(data, "empty", True):
                progress.progress(min(1.0, bi / max(1, len(batches))))
                continue
            batches_with_data += 1

            for t in batch:
                df = _extract_ticker_frame(data, t)
                if df is None or len(df) < 40:
                    continue
                total_analyzed += 1
                dfi = _add_indicators(df).dropna()
                if dfi is None or dfi.empty:
                    continue
                opp = _score_opportunity(dfi)
                last = float(dfi["Close"].iloc[-1])
                rsi = float(dfi["RSI"].iloc[-1]) if "RSI" in dfi.columns and dfi["RSI"].notna().any() else 50.0
                row = {
                    "السهم": name_map.get(t, t.replace(".SR", "")),
                    "الرمز": t,
                    "السعر": last,
                    "RSI": rsi,
                    "الفرصة": opp["label"],
                    "الدرجة": opp["score"],
                    "دخول": opp["entry"],
                    "وقف": opp["stop"],
                    "هدف1": opp["target1"],
                }
                rows_all.append(row)
                if opp["score"] >= min_score:
                    rows.append(row)

            progress.progress(min(1.0, bi / max(1, len(batches))))

        st.caption(f"تم فحص: {len(tickers)} رمز | دفعات ناجحة: {batches_with_data}/{len(batches)} | أسهم محللة: {total_analyzed}")

        if not rows_all and mode == "كامل السوق":
            st.warning("المصدر لم يعط بيانات كافية لكامل السوق. سيتم تشغيل وضع إنقاذ على الأسهم القيادية الآن.")
            used_rescue = True
            rescue_universe = [
                "2222.SR", "1120.SR", "1180.SR", "1150.SR", "7010.SR", "7020.SR",
                "2010.SR", "1211.SR", "2082.SR", "2020.SR", "1060.SR", "1140.SR",
                "1020.SR", "1080.SR", "2350.SR", "2290.SR", "4250.SR", "4300.SR",
                "7203.SR", "7202.SR", "4031.SR", "4002.SR", "4004.SR", "4164.SR",
            ]
            rescue_data = _safe_download(rescue_universe, period="120d")
            if rescue_data is not None and not getattr(rescue_data, "empty", True):
                for t in rescue_universe:
                    df = _extract_ticker_frame(rescue_data, t)
                    if df is None or len(df) < 40:
                        continue
                    dfi = _add_indicators(df).dropna()
                    if dfi is None or dfi.empty:
                        continue
                    opp = _score_opportunity(dfi)
                    last = float(dfi["Close"].iloc[-1])
                    rsi = float(dfi["RSI"].iloc[-1]) if "RSI" in dfi.columns and dfi["RSI"].notna().any() else 50.0
                    row = {
                        "السهم": t.replace(".SR", ""),
                        "الرمز": t,
                        "السعر": last,
                        "RSI": rsi,
                        "الفرصة": opp["label"],
                        "الدرجة": opp["score"],
                        "دخول": opp["entry"],
                        "وقف": opp["stop"],
                        "هدف1": opp["target1"],
                    }
                    rows_all.append(row)
                    if opp["score"] >= min_score:
                        rows.append(row)

        if not rows and rows_all:
            st.warning("لا توجد نتائج مطابقة للحد الأدنى الحالي. تم عرض أفضل الفرص المتاحة تلقائياً.")
            rows_all_sorted = sorted(rows_all, key=lambda x: (x["الدرجة"], -x["RSI"]), reverse=True)
            rows = rows_all_sorted[:max_results]
        elif not rows and not rows_all:
            st.warning("لا توجد بيانات كافية حالياً للمسح. جرّب تخفيف الشروط أو الانتظار قليلاً.")
            return

        radar_df = pd.DataFrame(rows)
        radar_df = radar_df.sort_values(["الدرجة", "RSI"], ascending=[False, True]).head(max_results)
        if mode == "كامل السوق":
            st.session_state["full_market_radar_cache"] = radar_df.copy()
        st.session_state["radar_last_stats"] = {
            "tickers": len(tickers),
            "batches_with_data": batches_with_data,
            "batches_total": len(batches),
            "analyzed": total_analyzed,
            "qualified": int(len(radar_df)),
            "used_rescue": used_rescue,
            "used_cached": False,
        }
        st.dataframe(
            radar_df.style.format(
                {
                    "السعر": "{:.2f}",
                    "RSI": "{:.2f}",
                    "دخول": "{:.2f}",
                    "وقف": "{:.2f}",
                    "هدف1": "{:.2f}",
                }
            ),
            hide_index=True,
            width="stretch",
        )

def page_settings():
    st.title("⚙️ الإعدادات")
    st.caption("هذه الصفحة لضبط قائمة المراقبة ومزود الذكاء الاصطناعي.")
    watch = st.session_state.get("watchlist") or DEFAULT_WATCHLIST
    names = [n for n, _ in watch]
    current = st.multiselect("قائمة المراقبة:", options=names, default=names)
    if st.button("حفظ"):
        st.session_state["watchlist"] = [item for item in watch if item[0] in current]
        st.success("تم الحفظ")

    st.markdown("---")
    provider = st.radio(
        "مزود المستشار:",
        options=["محلي مجاني", "Gemini", "OpenRouter مجاني"],
        index=["محلي مجاني", "Gemini", "OpenRouter مجاني"].index(st.session_state.get("ai_provider", "محلي مجاني")),
        horizontal=True,
    )
    st.session_state["ai_provider"] = provider
    if provider == "Gemini":
        st.info('أضف المفتاح في Secrets: GEMINI_API_KEY = "..."')
    elif provider == "OpenRouter مجاني":
        st.info('أضف المفتاح في Secrets: OPENROUTER_API_KEY = "..." ويمكن تحديد OPENROUTER_MODEL')
    else:
        st.success("الوضع المحلي المجاني مفعل: لا يحتاج أي رصيد أو API.")

def page_advisor():
    st.title("🤖 المستشار الذكي")

    watch = st.session_state.get("watchlist") or DEFAULT_WATCHLIST
    names = [n for n, _ in watch]
    name = st.selectbox("السهم (من قائمة المراقبة):", options=names)
    ticker = dict(watch)[name]

    data = _safe_download([ticker], period="1y")
    df = _extract_ticker_frame(data, ticker) if data is not None else None
    if df is None or df.empty:
        st.warning("لا توجد بيانات كافية لهذا السهم حالياً.")
        return

    dfi = _add_indicators(df).dropna()
    if dfi is None or dfi.empty:
        st.warning("تعذر حساب المؤشرات لهذا السهم حالياً.")
        return

    opp = _score_opportunity(dfi)
    last = dfi.iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("السعر", f"{float(last['Close']):.2f}")
    c2.metric("RSI", f"{float(last.get('RSI', 0.0)):.2f}")
    c3.metric("الدرجة", str(opp["score"]))
    c4.metric("الفرصة", opp["label"])

    st.caption(f"دخول: {opp['entry']:.2f} | وقف: {opp['stop']:.2f} | هدف1: {opp['target1']:.2f} | هدف2: {opp['target2']:.2f}")

    if "advisor_messages" not in st.session_state:
        st.session_state["advisor_messages"] = [
            {
                "role": "assistant",
                "content": "اكتب سؤالك عن السهم (نقاط دخول/خروج، مخاطرة، قراءة المؤشرات). سأجيب اعتماداً على البيانات الحالية والمؤشرات. هذا ليس توصية مالية.",
            }
        ]

    for m in st.session_state["advisor_messages"]:
        with st.chat_message(m["role"]):
            st.write(m["content"])

    user_text = st.chat_input("اسأل المستشار...")
    if user_text:
        st.session_state["advisor_messages"].append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.write(user_text)

        price = float(last["Close"])
        rsi = float(last.get("RSI", 0.0))
        adx = float(last.get("ADX", 0.0)) if pd.notna(last.get("ADX")) else 0.0
        atr = float(last.get("ATR", 0.0)) if pd.notna(last.get("ATR")) else 0.0
        macd = float(last.get("MACD", 0.0)) if pd.notna(last.get("MACD")) else 0.0
        macd_diff = float(last.get("MACD_DIFF", 0.0)) if pd.notna(last.get("MACD_DIFF")) else 0.0

        history = st.session_state["advisor_messages"][-8:]
        history_txt = "\n".join([f"{x['role']}: {x['content']}" for x in history])

        prompt = (
            "أنت مستشار فني للسوق السعودي. أجب بالعربية باختصار ووضوح.\n"
            "لا تقدم توصية مالية قطعية. ركّز على السيناريوهات وإدارة المخاطر.\n\n"
            f"السهم: {name} ({ticker})\n"
            f"السعر: {price:.2f}\nRSI: {rsi:.2f}\nADX: {adx:.2f}\nATR: {atr:.2f}\n"
            f"MACD: {macd:.3f}\nMACD_DIFF: {macd_diff:.3f}\n"
            f"إشارة النظام: {opp['label']} | الدرجة: {opp['score']}/8\n"
            f"دخول: {opp['entry']:.2f} | وقف: {opp['stop']:.2f} | هدف1: {opp['target1']:.2f} | هدف2: {opp['target2']:.2f}\n\n"
            f"المحادثة:\n{history_txt}\n\n"
            "أجب على آخر رسالة للمستخدم فقط مع نقاط مختصرة."
        )

        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                local_text = _local_advisor_reply(
                    name=name,
                    ticker=ticker,
                    price=price,
                    rsi=rsi,
                    opp=opp,
                    adx=adx,
                    atr=atr,
                    user_text=user_text,
                )
                text, err = _ai_generate(prompt, local_text)
                if err:
                    st.warning(err)
                st.write(text)
                reply = text

        st.session_state["advisor_messages"].append({"role": "assistant", "content": reply})

def main():
    _rtl_style()
    st.sidebar.title("FAHAD.AI 🚀")
    st.sidebar.toggle("Dev Mode", key="dev_mode")
    page = st.sidebar.radio("التنقل:", ["🏠 الرئيسية", "📋 التحليل", "📡 الرادار", "🤖 المستشار", "⚙️ الإعدادات"])
    st.sidebar.markdown("---")
    st.sidebar.write("آخر تحديث: " + datetime.now().strftime("%H:%M:%S"))
    _render_dev_panel()

    if page == "🏠 الرئيسية":
        page_dashboard()
        st_autorefresh(interval=900000, key="refresh")  # 15 دقيقة
    elif page == "📋 التحليل":
        page_analysis()
    elif page == "📡 الرادار":
        page_radar()
    elif page == "🤖 المستشار":
        page_advisor()
    else:
        page_settings()

if __name__ == "__main__":
    main()
