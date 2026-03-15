import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from datetime import datetime
import pytz
import requests
from google import genai
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from streamlit_autorefresh import st_autorefresh

# ==========================================
# ⚙️ الإعدادات والثوابت (Constants & Settings)
# ==========================================

st.set_page_config(page_title="FAHAD.AI - رادار التداول", layout="wide", initial_sidebar_state="expanded")

# قائمة الأسهم السعودية المحدثة (بدون الرموز الملغية)
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
    "2350.SR": "كيان", "2290.SR": "ينساب", "2250.SR": "المجموعة الصناعية",
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
        retry = Retry(connect=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
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
            if ticker in df.columns.get_level_values(0):
                df = df[ticker]
            else:
                df.columns = df.columns.get_level_values(0)
        
        df.columns = [c.capitalize() for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        
        required = ['Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required):
            return None
            
        return df.dropna(subset=['Close'])

    @classmethod
    def fetch_data(cls, ticker, period="1y", interval="1d"):
        session = cls.get_session()
        try:
            stock = yf.Ticker(ticker, session=session)
            data = stock.history(period=period, interval=interval, auto_adjust=True)
            
            if data.empty:
                data = yf.download(ticker, period=period, interval=interval, progress=False, session=session, threads=False)
            
            data = cls.clean_df(data, ticker)
            return data, stock.info if data is not None else (None, None)
        except:
            return None, None

    @classmethod
    def get_ai_analysis(cls, stock_name, metrics):
        if "GEMINI_API_KEY" not in st.secrets: return "⚠️ مفتاح API غير متوفر في الإعدادات"
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            prompt = f"أنت محلل مالي خبير في السوق السعودي. حلل سهم {stock_name} بناءً على: {metrics}. قدم نصيحة مختصرة واحترافية بالعربية."
            response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
            return response.text
        except Exception as e:
            return f"❌ تعذر الاتصال بمحلل الذكاء الاصطناعي: {str(e)}"

class AnalysisEngine:
    @staticmethod
    def add_indicators(df):
        if df is None: return None
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
        if df is None or len(df) < 30: return "بيانات غير كافية", "#94a3b8"
        last, prev = df.iloc[-1], df.iloc[-2]
        vol_avg = df['Volume'].tail(20).mean() if 'Volume' in df.columns else 1
        
        if last['Low'] < df['Low'].tail(20).min() and last['Close'] > prev['Low']:
            return "💎 تجميع (Spring)", "#10b981"
        if last['High'] > df['High'].tail(20).max() and (last['High']-last['Low']) > (df['High']-df['Low']).tail(20).mean() * 1.5:
            return "🚨 تصريف (Climax)", "#ef4444"
        return "🔄 حياد", "#94a3b8"

    @staticmethod
    def get_recommendation(df):
        if df is None: return "⌛ انتظار", "hold", []
        last = df.iloc[-1]
        score = 0
        reasons = []
        if last['RSI'] < 30: score += 2; reasons.append("تشبع بيعي (RSI)")
        elif last['RSI'] > 70: score -= 2; reasons.append("تشبع شرائي (RSI)")
        if last['Close'] > last['EMA20']: score += 1; reasons.append("فوق EMA20")
        if last['MACD'] > last['MACD_S']: score += 1; reasons.append("MACD إيجابي")
        
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
        .stApp { background-color: #f8fafc; }
        .modern-card { background: white; padding: 1.5rem; border-radius: 1rem; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 1rem; }
        .recommendation-box { padding: 1rem; border-radius: 0.5rem; text-align: center; font-weight: bold; font-size: 1.2rem; margin-bottom: 1rem; }
        .buy { background-color: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .sell { background-color: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .hold { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        .ticker-wrapper { background: #1e293b; color: white; padding: 0.75rem; overflow: hidden; white-space: nowrap; margin-bottom: 1.5rem; border-radius: 0.5rem; }
        .ticker-content { display: inline-block; animation: scroll 40s linear infinite; }
        @keyframes scroll { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
        .ticker-item { margin-right: 2rem; font-weight: bold; }
        .metric-label { color: #64748b; font-size: 0.875rem; margin-bottom: 0.25rem; }
        .metric-value { color: #1e293b; font-size: 1.5rem; font-weight: 700; }
        </style>
    """, unsafe_allow_html=True)

def display_ticker():
    items = []
    tickers = SECTORS["القياديات"]
    try:
        data = yf.download(tickers, period="2d", session=DataEngine.get_session(), progress=False, group_by='ticker', threads=False)
        for t in tickers:
            df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            if not df.empty and len(df) >= 2:
                last, chg = df['Close'].iloc[-1], ((df['Close'].iloc[-1] - df['Close'].iloc[-2])/df['Close'].iloc[-2])*100
                color = "#4ade80" if chg >= 0 else "#f87171"
                items.append(f'<span class="ticker-item">{STOCK_NAMES.get(t, t)}: {last:.2f} <span style="color:{color}">{chg:+.2f}%</span></span>')
    except: pass
    content = " ".join(items) if items else "جاري تحديث بيانات السوق..."
    st.markdown(f'<div class="ticker-wrapper"><div class="ticker-content">{content}</div></div>', unsafe_allow_html=True)

# ==========================================
# 🚀 الصفحات الرئيسية (Main Pages)
# ==========================================

def page_home():
    st.title("🏠 لوحة تحكم FAHAD.AI")
    display_ticker()
    
    if st.session_state.get('watchlist'):
        st.subheader("⭐ أسهمي الخاصة")
        w_cols = st.columns(len(st.session_state.watchlist))
        try:
            w_data = yf.download(st.session_state.watchlist, period="2d", session=DataEngine.get_session(), progress=False, group_by='ticker', threads=False)
            for i, t in enumerate(st.session_state.watchlist):
                df = w_data[t].dropna() if isinstance(w_data.columns, pd.MultiIndex) else w_data.dropna()
                if not df.empty:
                    last, prev = df['Close'].iloc[-1], df['Close'].iloc[-2]
                    pct = ((last - prev) / prev) * 100
                    color = "#10b981" if pct >= 0 else "#ef4444"
                    with w_cols[i]:
                        st.markdown(f"""
                            <div class="modern-card" style="text-align: center; border-top: 4px solid {color};">
                                <div class="metric-label">{STOCK_NAMES.get(t, t)}</div>
                                <div class="metric-value">{last:.2f}</div>
                                <div style="color: {color}; font-weight: 700;">{pct:+.2f}%</div>
                            </div>
                        """, unsafe_allow_html=True)
        except: st.info("أضف أسهمك المفضلة من القائمة الجانبية")
    
    st.markdown("---")
    
    all_tickers = [s for sub in SECTORS.values() for s in sub]
    with st.spinner("جاري جلب بيانات السوق..."):
        try:
            data = yf.download(all_tickers, period="2d", session=DataEngine.get_session(), progress=False, group_by='ticker', threads=False)
            results = []
            for t in all_tickers:
                df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
                if not df.empty and len(df) >= 2:
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
                    st.dataframe(df_res.nlargest(5, 'التغير %').style.format({'السعر': '{:.2f}', 'التغير %': '{:+.2f}%'}), hide_index=True, width='stretch')
                with c2:
                    st.subheader("📉 الأعلى هبوطاً")
                    st.dataframe(df_res.nsmallest(5, 'التغير %').style.format({'السعر': '{:.2f}', 'التغير %': '{:+.2f}%'}), hide_index=True, width='stretch')
                with c3:
                    st.subheader("🔥 الأكثر نشاطاً")
                    st.dataframe(df_res.nlargest(5, 'الحجم').style.format({'السعر': '{:.2f}', 'الحجم': '{:,.0f}'}), hide_index=True, width='stretch')
            else: st.warning("السوق مغلق حالياً أو تعذر جلب البيانات")
        except: st.warning("تعذر تحديث ملخص السوق")

def page_analysis():
    st.title("📋 التحليل الفني المفصل")
    ticker_display = st.selectbox("اختر السهم للتحليل:", list(FLAT_STOCKS.keys()))
    ticker = FLAT_STOCKS[ticker_display]
    
    with st.spinner("جاري تحليل البيانات..."):
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
                
                atr = df['ATR'].iloc[-1]
                price = df['Close'].iloc[-1]
                st.subheader("🛡️ إدارة المخاطر")
                st.error(f"وقف الخسارة: {price - (atr * 1.5):.2f}")
                st.success(f"الهدف 1: {price + (atr * 2):.2f}")

                st.markdown("---")
                if st.button("🤖 استشارة المحلل الذكي"):
                    with st.spinner("جاري التحليل بالذكاء الاصطناعي..."):
                        metrics = f"السعر: {price:.2f}, RSI: {df['RSI'].iloc[-1]:.2f}, وايكوف: {wyck_msg}"
                        ai_comment = DataEngine.get_ai_analysis(ticker_display, metrics)
                        st.info(ai_comment)
        else: st.error("تعذر جلب بيانات هذا السهم")

def page_radar():
    st.title("📡 رادار الفرص الذكي")
    sector = st.selectbox("اختر القطاع للمسح:", list(SECTORS.keys()))
    
    if st.button("بدء المسح اللحظي"):
        tickers = SECTORS[sector]
        results = []
        progress = st.progress(0)
        try:
            data = yf.download(tickers, period="60d", session=DataEngine.get_session(), progress=False, group_by='ticker', threads=False)
            for i, t in enumerate(tickers):
                df = data[t].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
                if not df.empty and len(df) > 20:
                    df = AnalysisEngine.add_indicators(df)
                    rec, _, _ = AnalysisEngine.get_recommendation(df)
                    wyck, _ = AnalysisEngine.get_wyckoff(df)
                    results.append({
                        "الشركة": STOCK_NAMES.get(t, t), "السعر": df['Close'].iloc[-1],
                        "الإشارة": rec, "وايكوف": wyck, "RSI": df['RSI'].iloc[-1]
                    })
                progress.progress((i + 1) / len(tickers))
            
            if results:
                radar_df = pd.DataFrame(results)
                st.dataframe(radar_df, hide_index=True, width='stretch')
            else: st.warning("لا توجد بيانات كافية حالياً")
        except: st.error("فشل المسح، حاول مرة أخرى")

def page_building():
    st.title("🏗️ مواد البناء")
    st.info("الأسعار تقديرية للسوق المحلي")
    c1, c2, c3 = st.columns(3)
    c1.metric("طن الحديد", "3,150 ريال", "+10")
    c2.metric("كيس الأسمنت", "18.50 ريال", "-0.5")
    c3.metric("الخرسانة (م3)", "240 ريال")

# ==========================================
# 🛠️ إدارة التطبيق (Application Core)
# ==========================================

def main():
    inject_css()
    if 'watchlist' not in st.session_state: st.session_state.watchlist = ["1120.SR", "2222.SR", "7010.SR"]
    
    st.sidebar.title("FAHAD.AI 🚀")
    page = st.sidebar.radio("التنقل:", ["🏠 الرئيسية", "📋 التحليل", "📡 الرادار", "🏗️ مواد البناء"])
    
    with st.sidebar.expander("⭐ قائمة المراقبة"):
        selected = st.multiselect("اختر الأسهم:", options=list(FLAT_STOCKS.keys()), default=[f"{STOCK_NAMES[s]} ({s.split('.')[0]})" for s in st.session_state.watchlist if s in STOCK_NAMES])
        if st.button("حفظ القائمة"):
            st.session_state.watchlist = [FLAT_STOCKS[n] for n in selected[:5]]
            st.rerun()
            
    if page == "🏠 الرئيسية": page_home()
    elif page == "📋 التحليل": page_analysis()
    elif page == "📡 الرادار": page_radar()
    elif page == "🏗️ مواد البناء": page_building()
    
    st.markdown("---")
    st.markdown('<div style="text-align:center; color:#64748b; font-size:0.8rem;">تطوير فهد AI © 2024 | جميع البيانات من Yahoo Finance</div>', unsafe_allow_html=True)
    
    if page == "🏠 الرئيسية": st_autorefresh(interval=60000, key="home_refresh")

if __name__ == "__main__":
    main()
