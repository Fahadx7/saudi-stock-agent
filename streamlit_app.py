import streamlit as st
import yfinance as yf
import pandas as pd
import ta
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz
import requests

# إعدادات الصفحة
st.set_page_config(page_title="FAHAD.AI - رادار الأسهم السعودية", layout="wide", page_icon="🚀")

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

# نمط CSS مخصص مع إضافة الشريط المتحرك
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
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

# قائمة موسعة للأسهم السعودية (تاسي)
SAUDI_STOCKS = {
    "الراجحي (1120)": "1120.SR",
    "أرامكو (2222)": "2222.SR",
    "سابك (2010)": "2010.SR",
    "إس تي سي (7010)": "7010.SR",
    "الأهلي (1180)": "1180.SR",
    "معادن (1211)": "1211.SR",
    "الإنماء (1150)": "1150.SR",
    "سابك للمغذيات (2020)": "2020.SR",
    "أكوا باور (2082)": "2082.SR",
    "سليمان الحبيب (4013)": "4013.SR",
    "البنك الأول (1060)": "1060.SR",
    "بنك البلاد (1140)": "1140.SR",
    "جرير (4190)": "4190.SR",
    "البحري (4030)": "4030.SR",
    "كيان (2350)": "2350.SR",
    "كهرباء السعودية (5110)": "5110.SR",
    "المواساة (4002)": "4002.SR",
    "علم (7203)": "7203.SR",
    "تاسي (مؤشر السوق)": "^TASI"
}

# قائمة مخصصة للرادار (أهم الأسهم السيولة والمضاربة)
RADAR_LIST = {
    "الراجحي": "1120.SR", "أرامكو": "2222.SR", "سابك": "2010.SR", "STC": "7010.SR",
    "الأهلي": "1180.SR", "معادن": "1211.SR", "الإنماء": "1150.SR", "أكوا باور": "2082.SR",
    "سليمان الحبيب": "4013.SR", "سابك للمغذيات": "2020.SR", "البنك الأول": "1060.SR",
    "بنك البلاد": "1140.SR", "جرير": "4190.SR", "البحري": "4030.SR", "كيان": "2350.SR",
    "كهرباء السعودية": "5110.SR", "المواساة": "4002.SR", "علم": "7203.SR", "بوان": "1302.SR",
    "ثمار": "4160.SR", "الباحة": "4130.SR", "أنابيب": "2320.SR", "تطوير": "4031.SR"
}

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
    """حساب نقاط مضاربية سريعة لترتيب الأسهم في الرادار"""
    if df is None or len(df) < 30: return 0
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    # 1. زخم السعر (1-5 نقاط)
    change_pct = ((latest['Close'] - prev['Close']) / prev['Close']) * 100
    if change_pct > 0: score += min(3, change_pct)
    
    # 2. حجم التداول (1-5 نقاط)
    vol_ratio = latest['Volume'] / latest['VOL_SMA'] if latest['VOL_SMA'] > 0 else 1
    if vol_ratio > 1.2: score += 2
    if vol_ratio > 2: score += 3
    
    # 3. مؤشر القوة النسبية (RSI)
    rsi = latest['RSI']
    if 40 < rsi < 65: score += 2 # منطقة انطلاق
    if rsi < 30: score += 3 # ارتداد
    
    # 4. الماكدي (MACD)
    if latest['MACD'] > latest['MACD_SIGNAL']: score += 2
        
    return score

# جلب بيانات الشريط المتحرك (Ticker)
@st.cache_data(ttl=300) # تخزين مؤقت لمدة 5 دقائق لسرعة التحميل
def get_ticker_data():
    ticker_items = []
    # تقليل عدد الأسهم في الشريط لسرعة الاستجابة الأولية
    sample_stocks = list(RADAR_LIST.items())[:10] 
    for name, ticker in sample_stocks:
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

# واجهة المستخدم
st.title("🚀 FAHAD.AI - رادار الأسهم السعودية")

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

st.sidebar.header("🔍 ابحث عن سهم")

# عرض أسعار مواد البناء في القائمة الجانبية
b_prices = get_building_prices()
if b_prices:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🏗️ أسعار مواد البناء")
    
    col_b1, col_b2 = st.sidebar.columns(2)
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
    st.sidebar.markdown("---")

# إنشاء تبويبات
tab1, tab2 = st.tabs(["📋 التحليل التفصيلي", "📡 رادار الفرص المضاربية"])

with tab1:
    # خيارين للبحث: قائمة جاهزة أو إدخال يدوي
    search_method = st.sidebar.radio("طريقة الاختيار:", ["القائمة الجاهزة", "إدخال رمز السهم (4 أرقام)"])

    if search_method == "القائمة الجاهزة":
        selected_stock_display = st.sidebar.selectbox("اختر السهم:", list(SAUDI_STOCKS.keys()))
        ticker = SAUDI_STOCKS[selected_stock_display]
        selected_stock_name = selected_stock_display.split(" (")[0]
    else:
        custom_ticker = st.sidebar.text_input("أدخل رمز السهم (مثلاً: 1120):", placeholder="1120")
        if custom_ticker:
            if len(custom_ticker) == 4 and custom_ticker.isdigit():
                ticker = f"{custom_ticker}.SR"
                selected_stock_name = f"السهم ذو الرمز {custom_ticker}"
            else:
                st.sidebar.warning("الرجاء إدخال رمز صحيح مكون من 4 أرقام")
                ticker = None
        else:
            ticker = None

    period = st.sidebar.selectbox("الفترة الزمنية للتحليل الفني:", ["3mo", "6mo", "1y", "2y", "5y"], index=2)

    if st.sidebar.button("ابدأ التحليل العميق") and ticker:
        with st.spinner(f"جاري تحليل سهم {selected_stock_name}..."):
            df, info = get_stock_data(ticker, period)
            
            if df is not None and len(df) > 30:
                df = add_indicators(df)
                rec, style_class, reasons = generate_recommendation(df)
                
                # عرض التوصية الكبرى
                st.markdown(f"""
                    <div class="recommendation-box {style_class}">
                        توصية المحلل الذكي: {rec}
                    </div>
                """, unsafe_allow_html=True)

                # قسم التحليل المالي (Fundamentals)
                st.subheader("📊 التحليل المالي الأساسي")
                f_col1, f_col2, f_col3, f_col4 = st.columns(4)
                
                mkt_cap = info.get('marketCap', 0) / 1e9 # بليون ريال
                pe_ratio = info.get('trailingPE', 'N/A')
                eps = info.get('trailingEps', 'N/A')
                div_yield = info.get('dividendYield', 0) * 100 # نسبة مئوية
                
                f_col1.metric("القيمة السوقية", f"{mkt_cap:.1f}B")
                f_col2.metric("مكرر الربحية (P/E)", f"{pe_ratio}")
                f_col3.metric("ربحية السهم (EPS)", f"{eps}")
                f_col4.metric("عائد التوزيعات", f"{div_yield:.2f}%")

                # المقاييس الفنية الرئيسية
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

                # الرسم البياني التفاعلي
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df.index,
                                open=df['Open'], high=df['High'],
                                low=df['Low'], close=df['Close'], name='السعر'))
                
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20', line=dict(color='orange', width=1)))
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50', line=dict(color='blue', width=1)))
                
                fig.update_layout(title=f'الرسم البياني الفني لـ {selected_stock_name}',
                                yaxis_title='السعر (ريال)',
                                xaxis_title='التاريخ',
                                template='plotly_white',
                                height=600)
                st.plotly_chart(fig, use_container_width=True)

                # أسباب التوصية ومستويات الدعم والمقاومة
                st.markdown("---")
                res_col1, res_col2 = st.columns(2)
                
                with res_col1:
                    st.subheader("📝 مبررات التوصية")
                    for reason in reasons:
                        st.write(f"- {reason}")
                
                with res_col2:
                    st.subheader("🎯 مستويات الدعم والمقاومة")
                    st.write(f"🚩 مقاومة 2 (R2): **{df['R2'].iloc[-1]:.2f}**")
                    st.write(f"🚩 مقاومة 1 (R1): **{df['R1'].iloc[-1]:.2f}**")
                    st.write(f"🔵 نقطة الارتكاز (Pivot): **{df['Pivot'].iloc[-1]:.2f}**")
                    st.write(f"🟢 دعم 1 (S1): **{df['S1'].iloc[-1]:.2f}**")
                    st.write(f"🟢 دعم 2 (S2): **{df['S2'].iloc[-1]:.2f}**")
                    
                    st.markdown("---")
                    st.subheader("🛡️ إدارة المخاطر والمدى الزمني")
                    atr_val = df['ATR'].iloc[-1]
                    adx_val = df['ADX'].iloc[-1]
                    
                    # معامل السرعة بناءً على قوة الاتجاه (ADX)
                    # إذا كان ADX > 25 الاتجاه قوي والوصول أسرع
                    speed_factor = 1.2 if adx_val > 25 else 0.8
                    
                    stop_loss = latest_price - (atr_val * 1.5)
                    target_1 = latest_price + (atr_val * 2)
                    target_2 = latest_price + (atr_val * 4)
                    
                    # حساب الأيام المتوقعة (بناءً على متوسط الحركة اليومية ATR)
                    days_t1 = max(1, round((target_1 - latest_price) / (atr_val * speed_factor)))
                    days_t2 = max(3, round((target_2 - latest_price) / (atr_val * speed_factor)))
                    
                    st.error(f"🚫 وقف الخسارة: **{stop_loss:.2f}**")
                    
                    st.success(f"🎯 الهدف 1: **{target_1:.2f}**")
                    st.info(f"⏳ الوقت المتوقع (T1): **{days_t1}-{days_t1+2} أيام تداول**")
                    
                    st.success(f"🎯 الهدف 2: **{target_2:.2f}**")
                    st.info(f"⏳ الوقت المتوقع (T2): **{days_t2}-{days_t2+3} أيام تداول**")
                    
                    st.warning("⚠️ ملاحظة: الوقت تقديري بناءً على تذبذب السهم الأخير وقوة الزخم.")

                # جدول البيانات الأخير
                with st.expander("عرض البيانات التاريخية الأخيرة"):
                    st.dataframe(df.tail(10))

            else:
                st.error("لم نتمكن من العثور على بيانات كافية لهذا السهم. يرجى التأكد من الرمز أو اختيار فترة زمنية أطول.")
    else:
        st.info("الرجاء اختيار سهم من القائمة الجانبية والضغط على 'ابدأ التحليل العميق'")

with tab2:
    st.subheader("📡 رادار الفرص اللحظية (تحديث تلقائي كل 5 دقائق)")
    
    # تفعيل التحديث التلقائي (كل 5 دقائق = 300,000 مللي ثانية)
    st_autorefresh(interval=300000, key="radar_refresh")

    # خيار التحديث اليدوي
    if st.button("تحديث الرادار يدوياً"):
        st.rerun()

    radar_results = []
    with st.spinner("جاري مسح السوق واصطياد الفرص..."):
        # نقوم بمسح عينة من الأسهم القيادية والمضاربية
        for name, ticker in RADAR_LIST.items():
            df_radar, _ = get_stock_data(ticker, period="3mo")
            if df_radar is not None and len(df_radar) > 20:
                df_radar = add_indicators(df_radar)
                score = calculate_spec_score(df_radar)
                
                latest_p = df_radar['Close'].iloc[-1]
                prev_p = df_radar['Close'].iloc[-2]
                chg = ((latest_p - prev_p) / prev_p) * 100
                atr = df_radar['ATR'].iloc[-1]
                
                # حساب الأهداف اللحظية للرادار
                t1 = latest_p + (atr * 1.5)
                sl = latest_p - (atr * 1.2)
                
                radar_results.append({
                    "السهم": name,
                    "السعر": round(latest_p, 2),
                    "التغير %": round(chg, 2),
                    "قوة الفرصة": score,
                    "دخول آمن": round(latest_p, 2),
                    "الهدف اللحظي": round(t1, 2),
                    "وقف الخسارة": round(sl, 2),
                    "RSI": round(df_radar['RSI'].iloc[-1], 1)
                })
    
    if radar_results:
        # ترتيب النتائج حسب قوة الفرصة
        radar_df = pd.DataFrame(radar_results).sort_values(by="قوة الفرصة", ascending=False)
        
        # عرض النتائج في جدول
        st.dataframe(radar_df, use_container_width=True)
        
        st.info("💡 الأسهم ذات النقاط الأعلى في 'قوة الفرصة' هي الأقرب للانطلاق مضاربياً.")
    else:
        st.warning("فشل جلب بيانات الرادار، يرجى المحاولة مرة أخرى.")

# تذييل الصفحة
st.markdown("---")
st.markdown("""
    <div style="text-align: center; color: gray; font-size: 12px;">
        إخلاء مسؤولية: هذه التوصيات مبنية على خوارزميات تحليل فني فقط ولا تعتبر نصيحة مالية مباشرة. 
        الاستثمار في الأسهم ينطوي على مخاطر عالية.
    </div>
""", unsafe_allow_html=True)
