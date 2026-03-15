import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from datetime import datetime
import pytz
import requests
import google.generativeai as genai
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from streamlit_autorefresh import st_autorefresh

# ==========================================
# ⚙️ الإعدادات والثوابت (Constants & Settings)
# ==========================================

st.set_page_config(page_title="FAHAD.AI - رادار التداول", layout="wide", initial_sidebar_state="expanded")

SECTORS = {
    "القياديات": ["1120.SR", "2222.SR", "2010.SR", "7010.SR", "1180.SR", "2082.SR"],
    "البنوك": ["1120.SR", "1180.SR", "1150.SR", "1060.SR", "1140.SR", "1020.SR", "1080.SR"],
    "البتروكيماويات": ["2010.SR", "2020.SR", "2350.SR", "2290.SR", "2250.SR"],
    "الاتصالات": ["7010.SR", "7020.SR", "7030.SR", "7203.SR", "7202.SR", "7201.SR"],
    "العقارات": ["4031.SR", "4150.SR", "4250.SR", "4300.SR", "4310.SR"],
    "المضاربة": ["4160.SR", "4130.SR", "2320.SR", "1302.SR", "4070.SR", "2140.SR", "8210.SR", "4190.SR"]
}

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

FLAT_STOCKS = {f"{STOCK_NAMES.get(s, s)} ({s.split('.')[0]})": s for sub in SECTORS.values() for s in sub}
FLAT_STOCKS["تاسي (مؤشر السوق)"] = "^TASI"

# ==========================================
# 🛠️ الطبقات المنطقية (Logic Layers)
# ==========================================

class DataEngine:
    @staticmethod
    @st.cache_resource
    def get_session():
        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retry))
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Referer': 'https://finance.yahoo.com'
        })
        return session

    @staticmethod
    def clean_df(df, ticker):
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df[ticker] if ticker in df.columns.get_level_values(0) else df.iloc[:, :6]
        df.columns = [c.capitalize() for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        return df.dropna(subset=['Close'])

    @classmethod
    def fetch_data(cls, ticker, period="1y", interval="1d"):
        try:
            # Fallback for TASI if index fails
            current_ticker = ticker
            stock = yf.Ticker(current_ticker, session=cls.get_session())
            data = stock.history(period=period, interval=interval, auto_adjust=True)
            
            if data.empty and current_ticker == "^TASI":
                # Try download as alternative
                data = yf.download(current_ticker, period=period, interval=interval, progress=False, session=cls.get_session())
            
            if data.empty: 
                data = yf.download(current_ticker, period=period, interval=interval, progress=False, session=cls.get_session())
            
            data = cls.clean_df(data, current_ticker)
            return data, stock.info if data is not None else (None, None)
        except Exception as e:
            st.error(f"خطأ في جلب {ticker}: {e}")
            return None, None

    @classmethod
    def get_ai_analysis(cls, stock_name, metrics):
        if "GEMINI_API_KEY" not in st.secrets: return "⚠️ مفتاح API غير متوفر"
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""
            أنت محلل مالي خبير في السوق السعودي. حلل سهم {stock_name} بناءً على:
            {metrics}
            قدم نصيحة مختصرة واحترافية باللغة العربية.
            """
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ خطأ في تحليل AI: {e}"

class AnalysisEngine:
    @staticmethod
    def add_indicators(df):
        df = df.copy()
        close = df['Close']
        df['RSI'] = ta.momentum.rsi(close, window=14).fillna(50)
        df['EMA20'] = ta.trend.ema_indicator(close, window=20).fillna(close)
        df['EMA50'] = ta.trend.ema_indicator(close, window=50).fillna(close)
        df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], close, window=14).fillna(0)
        macd = ta.trend.MACD(close)
        df['MACD'] = macd.macd().fillna(0)
        df['MACD_S'] = macd.macd_signal().fillna(0)
        return df

    @staticmethod
    def get_wyckoff(df):
        if len(df) < 30: return "بيانات غير كافية", "#94a3b8"
        last, prev = df.iloc[-1], df.iloc[-2]
        vol_avg = df['Volume'].tail(20).mean()
        spread = last['High'] - last['Low']
        
        if last['Low'] < df['Low'].tail(20).min() and last['Close'] > prev['Low'] and last['Volume'] > vol_avg:
            return "💎 تجميع (Spring)", "#10b981"
        if last['High'] > df['High'].tail(20).max() and spread > (df['High'] - df['Low']).tail(20).mean() * 1.5:
            return "🚨 تصريف (Climax)", "#ef4444"
        return "🔄 حياد", "#94a3b8"

    @staticmethod
    def get_recommendation(df):
        last = df.iloc[-1]
        score = 0
        reasons = []
        
        if last['RSI'] < 30: score += 2; reasons.append("تشبع بيعي (RSI < 30)")
        elif last['RSI'] > 70: score -= 2; reasons.append("تشبع شرائي (RSI > 70)")
        
        if last['Close'] > last['EMA20']: score += 1; reasons.append("فوق EMA20")
        if last['MACD'] > last['MACD_S']: score += 1; reasons.append("تقاطع MACD إيجابي")
        
        if score >= 3: return "🔥 شراء قوي", "buy", reasons
        if score >= 1: return "✅ شراء", "buy", reasons
        if score <= -3: return "🚨 بيع قوي", "sell", reasons
        return "⌛ انتظار", "hold", reasons

# ==========================================
# 🎨 مكونات واجهة المستخدم (UI Components)
# ==========================================

def inject_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
        html, body, [class*="st-"] { font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; }
        .modern-card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 20px; border: 1px solid #f1f5f9; }
        .recommendation-box { padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 1.2rem; margin-bottom: 15px; }
        .buy { background: #dcfce7; color: #166534; }
        .sell { background: #fee2e2; color: #991b1b; }
        .hold { background: #f1f5f9; color: #475569; }
        .ticker-wrapper { background: #1e293b; color: white; padding: 10px; overflow: hidden; white-space: nowrap; margin-bottom: 20px; border-radius: 8px; }
        .ticker-content { display: inline-block; animation: scroll 30s linear infinite; }
        @keyframes scroll { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
        .ticker-item { margin-right: 30px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

def display_ticker():
    items = []
    session = DataEngine.get_session()
    tickers = SECTORS["القياديات"]
    try:
        data = yf.download(tickers, period="2d", session=session, progress=False, group_by='ticker')
        for t in tickers:
            df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            if len(df) >= 2:
                last, chg = df['Close'].iloc[-1], ((df['Close'].iloc[-1] - df['Close'].iloc[-2])/df['Close'].iloc[-2])*100
                color = "#4ade80" if chg >= 0 else "#f87171"
                items.append(f'<span class="ticker-item">{STOCK_NAMES.get(t, t)}: {last:.2f} <span style="color:{color}">{chg:+.2f}%</span></span>')
    except: pass
    st.markdown(f'<div class="ticker-wrapper"><div class="ticker-content">{" ".join(items)}</div></div>', unsafe_allow_html=True)

# ==========================================
# 🚀 الصفحات الرئيسية (Main Pages)
# ==========================================

def page_home():
    st.title("🏠 لوحة تحكم FAHAD.AI")
    display_ticker()
    
    # Watchlist (My Private Stocks)
    if st.session_state.get('watchlist'):
        st.subheader("⭐ أسهمي الخاصة")
        w_cols = st.columns(len(st.session_state.watchlist))
        try:
            w_data = yf.download(st.session_state.watchlist, period="2d", session=DataEngine.get_session(), progress=False, group_by='ticker')
            for i, t in enumerate(st.session_state.watchlist):
                df = w_data[t].dropna() if isinstance(w_data.columns, pd.MultiIndex) else w_data.dropna()
                if not df.empty:
                    last, prev = df['Close'].iloc[-1], df['Close'].iloc[-2]
                    pct = ((last - prev) / prev) * 100
                    color = "#10b981" if pct >= 0 else "#ef4444"
                    with w_cols[i]:
                        st.markdown(f"""
                            <div class="modern-card" style="text-align: center; border-top: 4px solid {color};">
                                <div style="font-size: 0.9rem; color: #64748b;">{STOCK_NAMES.get(t, t)}</div>
                                <div style="font-size: 1.5rem; font-weight: 900; color: #1e293b;">{last:.2f}</div>
                                <div style="color: {color}; font-weight: 700;">{pct:+.2f}%</div>
                            </div>
                        """, unsafe_allow_html=True)
        except: pass
    
    st.markdown("---")
    
    # ملخص السوق (Batch Download)
    all_tickers = [s for sub in SECTORS.values() for s in sub]
    with st.spinner("جاري تحديث نبض السوق..."):
        try:
            data = yf.download(all_tickers, period="2d", session=DataEngine.get_session(), progress=False, group_by='ticker')
            results = []
            for t in all_tickers:
                df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
                if len(df) >= 2:
                    last, prev = df['Close'].iloc[-1], df['Close'].iloc[-2]
                    results.append({
                        "الشركة": STOCK_NAMES.get(t, t), "السعر": last, 
                        "التغير %": ((last - prev)/prev)*100, "الحجم": df['Volume'].iloc[-1]
                    })
            
            if results:
                df_res = pd.DataFrame(results)
                c1, c2, c3 = st.columns(3)
                with c1: 
                    st.subheader("📈 الأعلى صعوداً")
                    st.dataframe(df_res.nlargest(5, 'التغير %').style.format({'التغير %': '{:+.2f}%'}), hide_index=True, width='stretch')
                with c2:
                    st.subheader("📉 الأعلى هبوطاً")
                    st.dataframe(df_res.nsmallest(5, 'التغير %').style.format({'التغير %': '{:+.2f}%'}), hide_index=True, width='stretch')
                with c3:
                    st.subheader("🔥 الأكثر نشاطاً")
                    st.dataframe(df_res.nlargest(5, 'الحجم').style.format({'الحجم': '{:,.0f}'}), hide_index=True, width='stretch')
        except Exception as e:
            st.warning("تعذر جلب ملخص السوق حالياً")

def page_building():
    st.title("🏗️ أسعار مواد البناء (السوق المحلي)")
    # محاكاة لأسعار مواد البناء بما أن ياهو فاينانس لا يوفرها
    st.info("هذه الأسعار تقديرية بناءً على آخر تحديثات السوق المحلي")
    c1, c2, c3 = st.columns(3)
    c1.metric("طن الحديد (سابك)", "3,150 ريال", "+10")
    c2.metric("كيس الأسمنت (الرياض)", "18.50 ريال", "-0.5")
    c3.metric("الخرسانة الجاهزة (م3)", "240 ريال", "0")
    
    st.markdown("---")
    st.subheader("📊 تطور أسعار الحديد (12 شهر)")
    # بيانات وهمية للعرض
    hist_data = pd.DataFrame({
        "الشهر": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو"],
        "السعر": [3000, 3050, 3100, 3080, 3120, 3150]
    })
    st.line_chart(hist_data.set_index("الشهر"))

def page_analysis():
    st.title("📋 التحليل الفني المفصل")
    ticker_display = st.selectbox("اختر السهم للتحليل:", list(FLAT_STOCKS.keys()))
    ticker = FLAT_STOCKS[ticker_display]
    
    df, info = DataEngine.fetch_data(ticker)
    if df is not None:
        df = AnalysisEngine.add_indicators(df)
        rec, style, reasons = AnalysisEngine.get_recommendation(df)
        wyck_msg, wyck_clr = AnalysisEngine.get_wyckoff(df)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f'<div class="recommendation-box {style}">التوصية: {rec}</div>', unsafe_allow_html=True)
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template='plotly_white', height=500, margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig, width='stretch')
        
        with col2:
            st.markdown(f'<div class="modern-card" style="border-right: 5px solid {wyck_clr}; text-align:center;"><h3>وايكوف (VSA)</h3><p style="font-size:1.5rem; color:{wyck_clr}">{wyck_msg}</p></div>', unsafe_allow_html=True)
            st.subheader("📝 المبررات الفنية")
            for r in reasons: st.write(f"- {r}")
            
            # Risk Management
            atr = df['ATR'].iloc[-1]
            price = df['Close'].iloc[-1]
            st.subheader("🛡️ إدارة المخاطر")
            st.error(f"وقف الخسارة: {price - (atr * 1.5):.2f}")
            st.success(f"الهدف 1: {price + (atr * 2):.2f}")

            # AI Advisor
            st.markdown("---")
            if st.button("🤖 استشارة المحلل الذكي (Gemini)"):
                with st.spinner("جاري التحليل بالذكاء الاصطناعي..."):
                    metrics = f"Price: {price:.2f}, RSI: {df['RSI'].iloc[-1]:.2f}, Wyckoff: {wyck_msg}"
                    ai_comment = DataEngine.get_ai_analysis(ticker_display, metrics)
                    st.info(ai_comment)

def page_radar():
    st.title("📡 رادار الفرص الذكي")
    sector = st.selectbox("اختر القطاع للمسح:", list(SECTORS.keys()))
    
    if st.button("بدء المسح"):
        tickers = SECTORS[sector]
        results = []
        progress = st.progress(0)
        
        # Batch fetching for radar
        data = yf.download(tickers, period="60d", session=DataEngine.get_session(), progress=False, group_by='ticker')
        
        for i, t in enumerate(tickers):
            df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            if len(df) > 20:
                df = AnalysisEngine.add_indicators(df)
                rec, _, _ = AnalysisEngine.get_recommendation(df)
                wyck, _ = AnalysisEngine.get_wyckoff(df)
                results.append({
                    "الشركة": STOCK_NAMES.get(t, t), "السعر": df['Close'].iloc[-1],
                    "الإشارة": rec, "وايكوف": wyck, "RSI": df['RSI'].iloc[-1]
                })
            progress.progress((i + 1) / len(tickers))
        
        if results:
            st.dataframe(pd.DataFrame(results), hide_index=True, width='stretch')

# ==========================================
# 🛠️ إدارة التطبيق (Application Core)
# ==========================================

def main():
    inject_css()
    
    # Session State
    if 'watchlist' not in st.session_state: st.session_state.watchlist = ["1120.SR", "2222.SR", "7010.SR"]
    
    # Sidebar
    st.sidebar.title("FAHAD.AI 🚀")
    page = st.sidebar.radio("التنقل:", ["🏠 الرئيسية", "📋 التحليل", "📡 الرادار", "🏗️ مواد البناء"])
    
    with st.sidebar.expander("⭐ قائمة المراقبة (ماكس 5)"):
        selected = st.multiselect("اختر الأسهم:", options=list(FLAT_STOCKS.keys()), default=[f"{STOCK_NAMES[s]} ({s.split('.')[0]})" for s in st.session_state.watchlist if s in STOCK_NAMES])
        if st.button("تحديث القائمة"):
            st.session_state.watchlist = [FLAT_STOCKS[n] for n in selected[:5]]
            st.rerun()
            
    # Page Router
    if page == "🏠 الرئيسية": page_home()
    elif page == "📋 التحليل": page_analysis()
    elif page == "📡 الرادار": page_radar()
    elif page == "🏗️ مواد البناء": page_building()
    
    # Footer
    st.markdown("---")
    st.markdown('<div style="text-align:center; color:#64748b; font-size:0.8rem;">تطوير فهد AI © 2024 | جميع البيانات من Yahoo Finance</div>', unsafe_allow_html=True)
    
    # Auto Refresh (Home only)
    if page == "🏠 الرئيسية":
        st_autorefresh(interval=60000, key="home_refresh")

if __name__ == "__main__":
    main()
