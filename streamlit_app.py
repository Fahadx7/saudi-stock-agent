import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from google import genai
from streamlit_autorefresh import st_autorefresh

# 1. الإعدادات الأساسية
st.set_page_config(page_title="FAHAD.AI", layout="wide")

# 2. تعريف الأسهم (تأكد من صحة الرموز)
STOCKS = {
    "تاسي": "^TASI", "الراجحي": "1120.SR", "أرامكو": "2222.SR", 
    "سابك": "2010.SR", "STC": "7010.SR", "الأهلي": "1180.SR",
    "الإنماء": "1150.SR", "معادن": "1211.SR", "أكوا باور": "2082.SR"
}

# 3. وظيفة جلب البيانات (مقاومة للحظر والأخطاء)
@st.cache_data(ttl=300)
def get_data(ticker):
    try:
        # محاولة جلب البيانات الأساسية
        df = yf.download(ticker, period="1mo", interval="1d", progress=False)
        if df.empty: return None
        # تنظيف الأعمدة إذا كانت MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return None

# 4. حقن التصميم (RTL ودعم العربية)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo&display=swap');
    html, body, [class*="st-"] { font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; }
    .metric-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #eee; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# 5. القائمة الجانبية
st.sidebar.title("FAHAD.AI 🚀")
page = st.sidebar.radio("القائمة", ["🏠 الرئيسية", "📋 التحليل الفني", "📡 الرادار"])

if page == "🏠 الرئيسية":
    st.title("لوحة تحكم السوق السعودي")
    
    # شريط تاسي
    data = get_data("^TASI")
    if data is not None:
        last = data['Close'].iloc[-1]
        prev = data['Close'].iloc[-2]
        chg = ((last - prev) / prev) * 100
        color = "green" if chg >= 0 else "red"
        st.markdown(f"""
            <div class="metric-card">
                <h3>مؤشر تاسي الرئيسي</h3>
                <h1 style="color:{color}">{last:,.2f} ({chg:+.2f}%)</h1>
            </div>
        """, unsafe_allow_html=True)
        st.line_chart(data['Close'])
    else:
        st.warning("⚠️ بيانات السوق غير متوفرة حالياً من المصدر. يرجى المحاولة لاحقاً.")

elif page == "📋 التحليل الفني":
    st.title("التحليل التفصيلي للأسهم")
    choice = st.selectbox("اختر السهم:", list(STOCKS.keys()))
    ticker = STOCKS[choice]
    
    df = get_data(ticker)
    if df is not None:
        # إضافة مؤشر RSI ببساطة
        df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(title=f"رسم بياني لـ {choice}", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("المؤشرات")
            last_rsi = df['RSI'].iloc[-1]
            st.metric("مؤشر القوة النسبية (RSI)", f"{last_rsi:.2f}")
            if last_rsi < 30: st.success("تشبع بيعي (فرصة شراء)")
            elif last_rsi > 70: st.error("تشبع شرائي (منطقة خطر)")
            else: st.info("منطقة محايدة")

elif page == "📡 الرادار":
    st.title("رادار اقتناص الفرص")
    if st.button("بدء المسح"):
        results = []
        for name, ticker in STOCKS.items():
            d = get_data(ticker)
            if d is not None:
                last = d['Close'].iloc[-1]
                results.append({"السهم": name, "السعر": f"{last:.2f}"})
        st.table(results)

# التحديث التلقائي
st_autorefresh(interval=300000, key="frefresh")
