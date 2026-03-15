import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz
import requests
import google.generativeai as genai

# إعدادات الصفحة
st.set_page_config(page_title="FAHAD.AI - رادار الأسهم السعودية", layout="wide", page_icon="🚀")

# وظائف الذكاء الاصطناعي (AI Analysis)
def get_ai_analysis(stock_name, indicators_summary):
    """تحليل السهم باستخدام Gemini مع معالجة أخطاء متقدمة"""
    prompt = f"""
    أنت كبير المحللين الماليين في FAHAD.AI. قم بتحليل السهم التالي في السوق السعودي:
    السهم: {stock_name}
    المؤشرات: {indicators_summary}
    المطلوب: تحليل فني مختصر، نقاط القوة، المخاطر، ونصيحة للمتداول.
    اجعل الإجابة احترافية وباللغة العربية.
    """
    
    if "GEMINI_API_KEY" in st.secrets:
        key = st.secrets["GEMINI_API_KEY"].strip()
        if not key.startswith("AIza"):
            return "❌ خطأ في تنسيق مفتاح Gemini: يجب أن يبدأ بـ AIza"
            
        try:
            genai.configure(api_key=key)
            
            # محاولة اكتشاف الموديلات المتاحة لهذا المفتاح تحديداً
            available_models = []
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            except:
                pass
            
            # ترتيب الموديلات المفضلة
            preferred = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro', 'gemini-1.5-flash', 'gemini-1.5-pro']
            
            # دمج المكتشف مع المفضل
            models_to_try = []
            for p in preferred:
                if p not in models_to_try: models_to_try.append(p)
            for m in available_models:
                if m not in models_to_try: models_to_try.append(m)
            
            last_error = ""
            for model_name in models_to_try:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    return response.text
                except Exception as e:
                    last_error = str(e)
                    continue
            
            return f"❌ فشلت جميع المحاولات. تأكد من تفعيل Gemini API في Google Cloud لهذا المفتاح. الخطأ: {last_error}"
            
        except Exception as e:
            if "API_KEY_INVALID" in str(e):
                return "❌ خطأ في مفتاح Gemini: المفتاح غير صالح."
            return f"❌ خطأ غير متوقع في Gemini: {e}"
            
    return "لا يوجد مفتاح API لموديل Gemini في إعدادات Secrets."

# جلب أسعار مواد البناء من Firebase
def get_building_prices():
    try:
        url = "https://bekam-a9279-default-rtdb.firebaseio.com/market_prices.json"
        response = requests.get(url, timeout=5) # إضافة timeout لتجنب التعليق
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.sidebar.error(f"فشل جلب أسعار البناء: {e}")
    return None

# نمط CSS مخصص مع تحسين التنسيق لليمين (RTL) ونقل القائمة الجانبية
st.markdown("""
    <style>
    /* جعل التطبيق بالكامل من اليمين إلى اليسار */
    .main, .stApp {
        direction: RTL;
        text-align: right;
    }
    
    /* نقل القائمة الجانبية إلى اليمين */
    section[data-testid="stSidebar"] {
        position: fixed;
        right: 0;
        left: auto !important;
        direction: RTL;
    }
    
    /* تعديل محتوى الصفحة ليفسح مجالاً للقائمة على اليمين */
    section[data-testid="stSidebar"] + section {
        margin-right: 0px;
        margin-left: 0px;
    }
    
    /* تحسين شكل القائمة الجانبية */
    [data-testid="stSidebarNav"] {
        direction: RTL;
    }
    
    .building-price-box {
        background: white;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e0e6ed;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    .building-price-box h4 {
        margin: 0;
        color: #4a5568;
        font-size: 0.9em;
    }
    
    .building-price-box .price {
        font-size: 1.5em;
        font-weight: 800;
        color: #1e3d59;
        margin: 5px 0;
    }
    
    /* شريط الأسهم المتحرك (Ticker) */
    .ticker-wrapper {
        width: 100%;
        overflow: hidden;
        background-color: #1e3d59;
        color: white;
        padding: 10px 0;
        position: sticky;
        top: 0;
        z-index: 999;
        border-bottom: 2px solid #E94560;
    }
    
    .ticker-content {
        display: inline-block;
        white-space: nowrap;
        padding-right: 100%;
        animation: ticker 60s linear infinite;
    }
    
    @keyframes ticker {
        0% { transform: translate3d(100%, 0, 0); }
        100% { transform: translate3d(-100%, 0, 0); }
    }
    
    .ticker-item {
        display: inline-block;
        padding: 0 20px;
        font-weight: bold;
    }
    
    .price-up { color: #00ff00; }
    .price-down { color: #ff4b4b; }

    .stMetric {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        border: 1px solid #e0e6ed;
        text-align: center;
    }
    /* تحسين وضوح الأرقام والعناوين داخل المربعات */
    [data-testid="stMetricValue"] {
        font-size: 32px !important;
        font-weight: 800 !important;
        color: #1e3d59 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 18px !important;
        font-weight: 600 !important;
        color: #4a5568 !important;
        margin-bottom: 10px !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 16px !important;
    }
    h1, h2, h3 {
        color: #1e3d59;
        text-align: right;
    }
    .recommendation-box {
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
        text-align: center;
        font-weight: bold;
        font-size: 24px;
    }
    .buy { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .sell { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .hold { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    </style>
""", unsafe_allow_html=True)

# قائمة موسعة للأسهم السعودية (تاسي) مقسمة حسب القطاعات
SECTORS = {
    "القياديات": ["1120.SR", "2222.SR", "2010.SR", "7010.SR", "1180.SR", "2082.SR"],
    "البنوك": ["1120.SR", "1180.SR", "1150.SR", "1060.SR", "1140.SR", "1020.SR", "1080.SR"],
    "البتروكيماويات": ["2010.SR", "2020.SR", "2350.SR", "2290.SR", "2002.SR", "2250.SR"],
    "الاتصالات وتقنية المعلومات": ["7010.SR", "7020.SR", "7030.SR", "7203.SR", "7202.SR", "7201.SR"],
    "التطوير العقاري": ["4031.SR", "4150.SR", "4250.SR", "4300.SR", "4310.SR"],
    "المضاربة والسيولة": ["4160.SR", "4130.SR", "2320.SR", "4031.SR", "1302.SR", "4070.SR", "2140.SR", "8210.SR", "4190.SR"]
}

# قاموس لأسماء الشركات (للعرض في الجدول)
STOCK_NAMES = {
    "1120.SR": "الراجحي", "2222.SR": "أرامكو", "2010.SR": "سابك", "7010.SR": "STC",
    "1180.SR": "الأهلي", "2082.SR": "أكوا باور", "1150.SR": "الإنماء", "1060.SR": "البنك الأول",
    "1140.SR": "بنك البلاد", "1020.SR": "بنك الجزيرة", "1080.SR": "البنك العربي", "2020.SR": "سابك للمغذيات",
    "2350.SR": "كيان", "2290.SR": "ينساب", "2002.SR": "المجموعة السعودية", "2250.SR": "المجموعة الصناعية",
    "7020.SR": "موبايلي", "7030.SR": "زين", "7203.SR": "علم", "7202.SR": "حلول", "7201.SR": "بحر العرب",
    "4031.SR": "تطوير", "4150.SR": "أرناج", "4250.SR": "جبل عمر", "4300.SR": "دار الأركان", "4310.SR": "مدينة المعرفة",
    "4160.SR": "ثمار", "4130.SR": "الباحة", "2320.SR": "أنابيب", "1302.SR": "بوان", "4070.SR": "تهامة",
    "2140.SR": "أيان", "8210.SR": "بوبا", "4190.SR": "جرير", "^TASI": "تاسي"
}

# إنشاء قائمة مسطحة لسهولة البحث في الواجهة
FLAT_STOCKS = {}
for sector, stocks in SECTORS.items():
    for stock in stocks:
        name = STOCK_NAMES.get(stock, f"سهم {stock.split('.')[0]}")
        FLAT_STOCKS[f"{name} ({stock.split('.')[0]})"] = stock
FLAT_STOCKS["تاسي (مؤشر السوق)"] = "^TASI"

def get_stock_data(ticker, period="1y"):
    try:
        # جلب بيانات السعر مع timeout
        data = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, timeout=10)
        
        if data is None or data.empty:
            return None, None

        # جلب معلومات السهم الأساسية مع معالجة الأخطاء
        try:
            stock_info = yf.Ticker(ticker).info
        except:
            stock_info = {} # إرجاع قاموس فارغ إذا فشل جلب المعلومات الأساسية
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        return data, stock_info
    except Exception as e:
        st.error(f"خطأ في الاتصال بالسوق: {e}")
        return None, None

def add_indicators(df):
    # استخدام مكتبة ta المستقرة بدلاً من pandas-ta
    close_series = df['Close']
    high_series = df['High']
    low_series = df['Low']
    volume_series = df['Volume']
    
    # RSI
    df['RSI'] = ta.momentum.rsi(close_series, window=14)
    
    # MACD
    macd_obj = ta.trend.MACD(close_series)
    df['MACD'] = macd_obj.macd()
    df['MACD_SIGNAL'] = macd_obj.macd_signal()
    
    # EMAs
    df['EMA20'] = ta.trend.ema_indicator(close_series, window=20)
    df['EMA50'] = ta.trend.ema_indicator(close_series, window=50)
    df['EMA200'] = ta.trend.ema_indicator(close_series, window=200)
    
    # ADX (Trend Strength)
    adx_obj = ta.trend.ADXIndicator(high_series, low_series, close_series, window=14)
    df['ADX'] = adx_obj.adx()
        
    # Stochastic Oscillator
    stoch_obj = ta.momentum.StochasticOscillator(high_series, low_series, close_series, window=14, smooth_window=3)
    df['STOCHk'] = stoch_obj.stoch()
    df['STOCHd'] = stoch_obj.stoch_signal()
        
    # ATR (Average True Range) for Stop Loss
    df['ATR'] = ta.volatility.average_true_range(high_series, low_series, close_series, window=14)
    
    # Volume SMA for Breakout detection
    df['VOL_SMA'] = volume_series.rolling(window=20).mean()
    
    # Bollinger Bands
    bb_obj = ta.volatility.BollingerBands(close_series, window=20, window_dev=2)
    df['BB_HIGH'] = bb_obj.bollinger_hband()
    df['BB_LOW'] = bb_obj.bollinger_lband()
    
    # حساب السيولة التقريبية (Money Flow Proxy)
    df['MONEY_FLOW'] = (df['Close'] - df['Close'].shift(1)) * df['Volume']
    
    # حساب مستويات الدعم والمقاومة (Pivot Points - Standard)
    high_p = df['High'].iloc[-2]
    low_p = df['Low'].iloc[-2]
    close_p = df['Close'].iloc[-2]
    
    pivot = (high_p + low_p + close_p) / 3
    df['Pivot'] = pivot
    df['R1'] = (2 * pivot) - low_p
    df['S1'] = (2 * pivot) - high_p
    df['R2'] = pivot + (high_p - low_p)
    df['S2'] = pivot - (high_p - low_p)
    
    return df

def generate_recommendation(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest['RSI']
    close = latest['Close']
    ema20 = latest['EMA20']
    ema50 = latest['EMA50']
    volume = latest['Volume']
    vol_sma = latest['VOL_SMA']
    adx_val = latest['ADX']
    stoch_k = latest['STOCHk']
    stoch_d = latest['STOCHd']
    macd = latest['MACD']
    signal = latest['MACD_SIGNAL']
    prev_macd = prev['MACD']
    prev_signal = prev['MACD_SIGNAL']

    score = 0
    reasons = []

    # 1. تحليل قوة الاتجاه (ADX)
    if adx_val > 25:
        reasons.append(f"قوة الاتجاه الحالية قوية (ADX: {adx_val:.1f})")
        if close > ema20: score += 1
    else:
        reasons.append(f"الاتجاه الحالي ضعيف أو عرضي (ADX: {adx_val:.1f})")

    # 2. تحليل الزخم (RSI & Stochastic)
    if rsi < 35:
        score += 2
        reasons.append("مؤشر RSI في منطقة تجميع (فرصة ارتداد)")
    elif rsi > 65:
        score -= 2
        reasons.append("مؤشر RSI في منطقة تصريف (خطر جني أرباح)")

    if stoch_k < 20 and stoch_k > stoch_d:
        score += 1.5
        reasons.append("تقاطع إيجابي لمؤشر ستوكاستيك في منطقة تشبع بيعي")

    # 3. تحليل السيولة (Volume Breakout)
    if volume > (vol_sma * 1.5):
        score += 2
        reasons.append("🚀 اختراق سعري مدعوم بأحجام تداول عالية (دخول سيولة)")

    # 4. منطق المتوسطات و MACD
    if close > ema20 > ema50:
        score += 1
        reasons.append("السعر في مسار صاعد فوق المتوسطات")
    
    if macd > signal and prev_macd <= prev_signal:
        score += 1.5
        reasons.append("إشارة دخول مبكرة من مؤشر MACD")

    # تحديد التوصية النهائية للمضارب
    if score >= 4:
        return "فرصة مضاربية ذهبية (شراء قوي)", "buy", reasons
    elif score >= 1.5:
        return "إشارة شراء مضاربية", "buy", reasons
    elif score <= -3:
        return "خروج مضاربي (بيع قوي)", "sell", reasons
    elif score <= -1:
        return "إشارة تخفيف / بيع", "sell", reasons
    else:
        return "انتظار (تراقب واقتناص)", "hold", ["السوق في منطقة حيرة، انتظر تأكيد الاختراق"]

def calculate_spec_score(df):
    """حساب نقاط مضاربية متقدمة لاكتشاف الانفجارات السعرية"""
    if df is None or len(df) < 50: return 0, "عادي"
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    signals = []

    # 1. سيولة غير طبيعية (Volume Spike)
    vol_ratio = latest['Volume'] / latest['VOL_SMA'] if latest['VOL_SMA'] > 0 else 1
    if vol_ratio > 2.5: 
        score += 5
        signals.append("🔥 سيولة ضخمة")
    elif vol_ratio > 1.5:
        score += 3
        signals.append("📈 دخول سيولة")

    # 2. اختراق المتوسطات (EMA Breakout)
    if prev['Close'] < prev['EMA20'] and latest['Close'] > latest['EMA20']:
        score += 4
        signals.append("🚀 اختراق EMA20")
    
    # 3. زخم القوة النسبية (RSI Momentum)
    rsi = latest['RSI']
    if 45 < rsi < 55 and rsi > prev['RSI']:
        score += 3
        signals.append("⚡ انطلاق زخم")
    elif rsi < 30:
        score += 4
        signals.append("💎 قاع فني")

    # 4. التقاطع الإيجابي (MACD Golden Cross)
    if prev['MACD'] < prev['MACD_SIGNAL'] and latest['MACD'] > latest['MACD_SIGNAL']:
        score += 4
        signals.append("⚔️ تقاطع ذهبي")

    # 5. ضيق البولنجر (Bollinger Squeeze) - انفجار وشيك
    bb_width = (latest['BB_HIGH'] - latest['BB_LOW']) / latest['EMA20']
    if bb_width < 0.05: # ضيق جداً
        score += 3
        signals.append("📦 ضغط سعري")

    status = " / ".join(signals) if signals else "هدوء"
    return score, status

# جلب بيانات الشريط المتحرك (Ticker)
@st.cache_data(ttl=300) # تخزين مؤقت لمدة 5 دقائق لسرعة التحميل
def get_ticker_data():
    ticker_items = []
    # اختيار 12 سهماً من القياديات والمضاربة للشريط
    top_stocks = SECTORS["القياديات"] + SECTORS["المضاربة والسيولة"][:6]
    for ticker in top_stocks:
        try:
            data = yf.download(ticker, period="2d", interval="1d", progress=False, timeout=5)
            if data is not None and not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                latest_p = float(data['Close'].iloc[-1])
                prev_p = float(data['Close'].iloc[-2])
                chg = ((latest_p - prev_p) / prev_p) * 100
                color_class = "price-up" if chg >= 0 else "price-down"
                arrow = "▲" if chg >= 0 else "▼"
                name = ticker.split(".")[0]
                ticker_items.append(f'<span class="ticker-item">{name}: {latest_p:.2f} <span class="{color_class}">{arrow} {abs(chg):.2f}%</span></span>')
        except Exception:
            continue
    
    if not ticker_items:
        return '<span class="ticker-item">جاري جلب بيانات السوق...</span>'
    return "".join(ticker_items)

# عرض الشريط المتحرك
ticker_html = get_ticker_data()
st.markdown(f"""
    <div class="ticker-wrapper">
        <div class="ticker-content">
            {ticker_html}
        </div>
    </div>
""", unsafe_allow_html=True)

# عرض نبض السوق (Market Breadth)
def get_market_breadth(summary_data):
    if not summary_data: return 0, 0, 0
    df = summary_data['all_data']
    advancers = len(df[df['chg_pct'] > 0])
    decliners = len(df[df['chg_pct'] < 0])
    unchanged = len(df[df['chg_pct'] == 0])
    return advancers, decliners, unchanged

@st.cache_data(ttl=900) # تحديث كل 15 دقيقة
def get_market_summary():
    """جلب ملخص السوق لأهم الشركات أداءً وسيولةً باستخدام Batch Download لسرعة فائقة"""
    all_results = []
    # مسح جميع الأسهم المعرفة في القطاعات
    all_tickers = list(set([stock for sublist in SECTORS.values() for stock in sublist]))
    
    try:
        # جلب البيانات لجميع الأسهم دفعة واحدة (Batch Download)
        # نستخدم 5 أيام للتأكد من وجود بيانات كافية لحساب التغير
        data_all = yf.download(all_tickers, period="5d", interval="1d", progress=False, group_by='ticker', timeout=15)
        
        for ticker in all_tickers:
            if ticker == "^TASI": continue
            try:
                # استخراج بيانات السهم الواحد من الدفعة
                if ticker in data_all.columns.levels[0]:
                    s_data = data_all[ticker].dropna()
                    if len(s_data) >= 2:
                        latest_p = float(s_data['Close'].iloc[-1])
                        prev_p = float(s_data['Close'].iloc[-2])
                        chg_pct = ((latest_p - prev_p) / prev_p) * 100
                        volume = int(s_data['Volume'].iloc[-1])
                        money_flow = (latest_p - prev_p) * volume
                        
                        all_results.append({
                            "ticker": ticker,
                            "name": STOCK_NAMES.get(ticker, ticker.split(".")[0]),
                            "price": latest_p,
                            "chg_pct": chg_pct,
                            "volume": volume,
                            "money_flow": money_flow
                        })
            except: continue
    except Exception as e:
        st.error(f"خطأ في جلب ملخص السوق: {e}")
        return None
    
    if not all_results: return None
    
    df_summary = pd.DataFrame(all_results)
    
    summary = {
        "most_active": df_summary.nlargest(5, 'volume'),
        "top_gainers": df_summary.nlargest(5, 'chg_pct'),
        "top_losers": df_summary.nsmallest(5, 'chg_pct'),
        "top_inflow": df_summary.nlargest(5, 'money_flow'),
        "top_outflow": df_summary.nsmallest(5, 'money_flow'),
        "all_data": df_summary # للبحث والتنبيهات
    }
    return summary

# واجهة المستخدم
st.title("🚀 FAHAD.AI - المحطة المتكاملة للمتداول")

# شريط جانبي محسن
st.sidebar.header("🛠️ أدوات التحكم")

# تفعيل التحديث التلقائي الشامل (كل 15 دقيقة = 900,000 مللي ثانية) لملخص السوق
st_autorefresh(interval=900000, key="market_summary_refresh")

# تهيئة حالة الجلسة (Session State) عند بدء التشغيل
if "ai_results" not in st.session_state:
    st.session_state.ai_results = {}
if "active_page" not in st.session_state:
    st.session_state.active_page = "📊 ملخص السوق"

# شريط جانبي محسن للتنقل
st.sidebar.title("🎮 قائمة التحكم")
menu_choice = st.sidebar.radio("انتقل إلى:", ["📊 ملخص السوق", "📋 التحليل التفصيلي", "📡 رادار الاقتناص", "🏗️ مواد البناء"])

# حاسبة إدارة المخاطر (Pro Feature)
with st.sidebar.expander("🧮 حاسبة إدارة المخاطر"):
    capital = st.number_input("رأس المال (ريال):", value=100000)
    risk_pct = st.slider("نسبة المخاطرة للمركز (%):", 1, 5, 2)
    entry_p = st.number_input("سعر الدخول:", value=100.0)
    stop_p = st.number_input("سعر وقف الخسارة:", value=95.0)
    if entry_p > stop_p:
        risk_amount = capital * (risk_pct / 100)
        shares = int(risk_amount / (entry_p - stop_p))
        total_cost = shares * entry_p
        st.success(f"الكمية المقترحة: {shares} سهم")
        st.info(f"التكلفة الإجمالية: {total_cost:,.0f} ريال")

# وضع التشخيص لمفاتيح API
with st.sidebar.expander("🛠️ وضع تشخيص المفاتيح"):
    st.write("تحقق من إعدادات Secrets:")
    if "GEMINI_API_KEY" in st.secrets:
        key = st.secrets["GEMINI_API_KEY"]
        if key.startswith("AIza"):
            st.success("✅ مفتاح Gemini جاهز")
            if st.button("فحص الموديلات المتاحة"):
                try:
                    genai.configure(api_key=key)
                    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    st.write("الموديلات المدعومة لمفتاحك:")
                    for m in models:
                        st.code(m)
                except Exception as e:
                    st.error(f"فشل جلب الموديلات: {e}")
        else:
            st.error("❌ خطأ في تنسيق مفتاح Gemini")
    else:
        st.warning("⚠️ مفتاح Gemini غير مضاف")

# عرض التاريخ والوقت بتوقيت السعودية
saudi_tz = pytz.timezone('Asia/Riyadh')
now = datetime.now(saudi_tz)
formatted_date = now.strftime("%Y-%m-%d")
formatted_time = now.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

st.markdown(f"""
    <div style="text-align: left; padding: 0 20px; color: #1e3d59; font-weight: bold; font-size: 1.1em; margin-top: -20px; margin-bottom: 20px;">
        📅 {formatted_date} | 🕒 {formatted_time} (بتوقيت الرياض)
    </div>
""", unsafe_allow_html=True)

# نظام تنبيهات البرق (Flash Alerts)
summary_data = get_market_summary()

# عرض نبض السوق
adv, dec, unc = get_market_breadth(summary_data)
total_sample = adv + dec + unc
if total_sample > 0:
    st.markdown(f"""
        <div style="display: flex; justify-content: space-around; background: #1e3d59; padding: 15px; border-radius: 10px; margin-bottom: 20px; color: white;">
            <div style="text-align: center;">🟢 صاعد: {adv}</div>
            <div style="text-align: center;">🔴 هابط: {dec}</div>
            <div style="text-align: center;">⚪ عرضي: {unc}</div>
            <div style="text-align: center;">📊 نبض السوق: {"إيجابي" if adv > dec else "سلبي"}</div>
        </div>
    """, unsafe_allow_html=True)

if summary_data:
    st.markdown("### ⚡ تنبيهات البرق اللحظية")
    alerts = []
    # تنبيه للانفجارات السعرية (> 3%)
    top_mover = summary_data['top_gainers'].iloc[0]
    if top_mover['chg_pct'] > 3:
        alerts.append(f"🚀 **{top_mover['name']}** يحلق بارتفاع {top_mover['chg_pct']:.2f}%")
    
    # تنبيه للسيولة الضخمة
    top_inflow = summary_data['top_inflow'].iloc[0]
    if top_inflow['money_flow'] > 0:
        alerts.append(f"🔥 سيولة قوية تدخل سهم **{top_inflow['name']}** الآن")
        
    if alerts:
        for alert in alerts:
            st.toast(alert, icon="⚡") # تنبيه منبثق
            st.success(alert) # تنبيه ثابت في الواجهة

st.sidebar.header("🔍 ابحث عن سهم")

# عرض أسعار مواد البناء
def display_building_prices():
    b_prices = get_building_prices()
    if b_prices:
        st.subheader("🏗️ أسعار مواد البناء")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.markdown(f"""
                <div class="building-price-box">
                    <h4>طن الحديد</h4>
                    <div class="price">{b_prices.get('iron', '0')}</div>
                    <small>ريال</small>
                </div>
            """, unsafe_allow_html=True)
        with col_b2:
            st.markdown(f"""
                <div class="building-price-box">
                    <h4>كيس أسمنت</h4>
                    <div class="price">{b_prices.get('cement', '0')}</div>
                    <small>ريال</small>
                </div>
            """, unsafe_allow_html=True)

# منطق عرض الصفحات بناءً على القائمة الجانبية
if menu_choice == "📊 ملخص السوق":
    st.subheader("🏁 ملخص السوق اليومي (تحديث كل 15 دقيقة)")
    with st.spinner("جاري تحليل ملخص السوق..."):
        summary = get_market_summary()
        if summary:
            # دالة لتصميم بطاقات القوائم
            def display_mini_table(df, title, color, is_pct=True):
                st.markdown(f"""
                    <div style="background: white; padding: 15px; border-radius: 12px; border-top: 5px solid {color}; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <h4 style="text-align: center; color: #1e3d59; margin-bottom: 10px;">{title}</h4>
                    </div>
                """, unsafe_allow_html=True)
                display_df = df[['name', 'price', 'chg_pct' if is_pct else 'volume']].copy()
                if is_pct: display_df.columns = ['الشركة', 'السعر', 'التغير %']
                else: display_df.columns = ['الشركة', 'السعر', 'الحجم']
                st.dataframe(display_df, hide_index=True, use_container_width=True)

            col_a, col_b, col_c = st.columns(3)
            with col_a: display_mini_table(summary['top_gainers'], "📈 الأكثر ارتفاعاً", "#00ff00")
            with col_b: display_mini_table(summary['top_losers'], "📉 الأكثر انخفاضاً", "#ff4b4b")
            with col_c: display_mini_table(summary['most_active'], "🔥 الأكثر نشاطاً", "#1e3d59", is_pct=False)
            
            st.markdown("---")
            col_d, col_e = st.columns(2)
            with col_d:
                st.markdown("<div style='background: #d4edda; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; color: #155724; margin-bottom: 10px;'>💰 الأكثر دخولاً للسيولة (تقديري)</div>", unsafe_allow_html=True)
                inflow_df = summary['top_inflow'][['name', 'price', 'money_flow']]
                inflow_df.columns = ['الشركة', 'السعر', 'تدفق السيولة']
                st.dataframe(inflow_df, hide_index=True, use_container_width=True)
            with col_e:
                st.markdown("<div style='background: #f8d7da; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; color: #721c24; margin-bottom: 10px;'>💸 الأكثر خروجاً للسيولة (تقديري)</div>", unsafe_allow_html=True)
                outflow_df = summary['top_outflow'][['name', 'price', 'money_flow']]
                outflow_df.columns = ['الشركة', 'السعر', 'تدفق السيولة']
                st.dataframe(outflow_df, hide_index=True, use_container_width=True)
        else:
            st.warning("جاري جلب بيانات ملخص السوق...")

elif menu_choice == "📋 التحليل التفصيلي":
    st.sidebar.markdown("---")
    search_method = st.sidebar.radio("طريقة الاختيار:", ["القائمة الجاهزة", "إدخال يدوي"])
    if search_method == "القائمة الجاهزة":
        selected_stock_display = st.sidebar.selectbox("اختر السهم:", list(FLAT_STOCKS.keys()))
        ticker = FLAT_STOCKS[selected_stock_display]
        selected_stock_name = selected_stock_display
    else:
        custom_ticker = st.sidebar.text_input("أدخل رمز السهم (مثلاً: 1120):", placeholder="1120")
        if custom_ticker and len(custom_ticker) == 4:
            ticker = f"{custom_ticker}.SR"
            selected_stock_name = f"سهم {custom_ticker}"
        else: ticker = None

    period = st.sidebar.selectbox("الفترة الزمنية:", ["3mo", "6mo", "1y", "2y", "5y"], index=2)

    if ticker:
        with st.spinner(f"جاري تحليل {selected_stock_name}..."):
            df, info = get_stock_data(ticker, period)
            if df is not None and len(df) > 30:
                df = add_indicators(df)
                rec, style_class, reasons = generate_recommendation(df)
                st.markdown(f"<div class='recommendation-box {style_class}'>توصية المحلل الذكي: {rec}</div>", unsafe_allow_html=True)
                
                # التحليل المالي
                st.subheader("📊 التحليل المالي الأساسي")
                f_col1, f_col2, f_col3, f_col4 = st.columns(4)
                mkt_cap = info.get('marketCap', 0) / 1e9
                f_col1.metric("القيمة السوقية", f"{mkt_cap:.1f}B")
                f_col2.metric("مكرر الربحية (P/E)", f"{info.get('trailingPE', 'N/A')}")
                f_col3.metric("ربحية السهم (EPS)", f"{info.get('trailingEps', 'N/A')}")
                f_col4.metric("عائد التوزيعات", f"{info.get('dividendYield', 0)*100:.2f}%")

                # المؤشرات الفنية
                st.subheader("📈 المؤشرات الفنية اللحظية")
                col1, col2, col3, col4 = st.columns(4)
                latest_price = float(df['Close'].iloc[-1])
                prev_price = float(df['Close'].iloc[-2])
                change = latest_price - prev_price
                pct_change = (change / prev_price) * 100
                col1.metric("السعر الحالي", f"{latest_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
                col2.metric("مؤشر RSI", f"{df['RSI'].iloc[-1]:.2f}")
                col3.metric("EMA 20", f"{df['EMA20'].iloc[-1]:.2f}")
                col4.metric("حجم التداول", f"{df['Volume'].iloc[-1]:,.0f}")

                # الرسم البياني
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'))
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20', line=dict(color='orange', width=1)))
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50', line=dict(color='blue', width=1)))
                fig.update_layout(title=f'الرسم البياني لـ {selected_stock_name}', yaxis_title='السعر', template='plotly_white', height=500)
                st.plotly_chart(fig, use_container_width=True)

                # أهداف الشراء والبيع
                res_col1, res_col2 = st.columns(2)
                with res_col1:
                    st.subheader("📝 مبررات التوصية")
                    for reason in reasons: st.write(f"- {reason}")
                with res_col2:
                    st.subheader("🛡️ إدارة المخاطر")
                    atr_val = df['ATR'].iloc[-1]
                    st.error(f"🚫 وقف الخسارة: **{latest_price - (atr_val * 1.5):.2f}**")
                    st.success(f"🎯 الهدف 1: **{latest_price + (atr_val * 2):.2f}**")
                    st.success(f"🎯 الهدف 2: **{latest_price + (atr_val * 4):.2f}**")

                # المحلل الذكي
                st.markdown("---")
                st.subheader("🤖 المحلل الذكي (FAHAD AI Analyst)")
                if "GEMINI_API_KEY" in st.secrets:
                    if st.button("استشارة المحلل الذكي حول هذا السهم", key=f"ai_btn_{ticker}"):
                        with st.spinner("جاري تحليل البيانات باستخدام Gemini..."):
                            summary_text = f"السعر: {latest_price}, RSI: {df['RSI'].iloc[-1]:.2f}, MACD: {df['MACD'].iloc[-1]:.2f}"
                            ai_commentary = get_ai_analysis(selected_stock_name, summary_text)
                            st.session_state.ai_results[ticker] = ai_commentary
                    
                    if ticker in st.session_state.ai_results:
                        st.info(st.session_state.ai_results[ticker])
                else:
                    st.warning("⚠️ ميزة الذكاء الاصطناعي تتطلب تفعيل مفتاح API في Secrets.")

elif menu_choice == "📡 رادار الاقتناص":
    st.subheader("📡 رادار الفرص اللحظية")
    target_sector = st.selectbox("اختر القطاع للمسح:", list(SECTORS.keys()))
    if st.button("تحديث الرادار يدوياً"): st.rerun()
    
    radar_results = []
    with st.spinner(f"جاري مسح قطاع {target_sector}..."):
        for ticker in SECTORS[target_sector]:
            df_radar, _ = get_stock_data(ticker, period="3mo")
            if df_radar is not None and len(df_radar) > 50:
                df_radar = add_indicators(df_radar)
                score, status = calculate_spec_score(df_radar)
                latest_p = df_radar['Close'].iloc[-1]
                radar_results.append({
                    "الشركة": STOCK_NAMES.get(ticker, ticker.split(".")[0]),
                    "الرمز": ticker.split(".")[0],
                    "السعر": round(latest_p, 2),
                    "قوة الفرصة": score,
                    "الإشارة": status,
                    "RSI": round(df_radar['RSI'].iloc[-1], 1)
                })
    if radar_results:
        radar_df = pd.DataFrame(radar_results).sort_values(by="قوة الفرصة", ascending=False)
        st.dataframe(radar_df, use_container_width=True)

elif menu_choice == "🏗️ مواد البناء":
    display_building_prices()

# تذييل الصفحة
st.markdown("---")
st.markdown("""
    <div style="text-align: center; color: gray; font-size: 12px;">
        إخلاء مسؤولية: هذه التوصيات مبنية على خوارزميات تحليل فني فقط ولا تعتبر نصيحة مالية مباشرة. 
        الاستثمار في الأسهم ينطوي على مخاطر عالية.
    </div>
""", unsafe_allow_html=True)
