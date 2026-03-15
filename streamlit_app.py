import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
from datetime import datetime
import os
from streamlit_autorefresh import st_autorefresh

# 1. إعدادات الصفحة
st.set_page_config(page_title="FAHAD.AI", layout="wide", initial_sidebar_state="expanded")

# 2. تعريف الأسهم
STOCK_MAP = {
    "تاسي": "^TASI", "الراجحي": "1120.SR", "أرامكو": "2222.SR", 
    "سابك": "2010.SR", "STC": "7010.SR", "الأهلي": "1180.SR",
    "الإنماء": "1150.SR", "معادن": "1211.SR", "أكوا باور": "2082.SR"
}

# 3. وظيفة جلب البيانات
@st.cache_data(ttl=600)
def get_data(tickers, period="1y"):
    try:
        data = yf.download(tickers, period=period, progress=False, group_by='ticker', threads=False)
        return data
    except:
        return None

def clean_stock_df(df, ticker):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df = df[ticker] if ticker in df.columns.get_level_values(0) else df.iloc[:, :6]
        df.columns = [str(c).capitalize() for c in df.columns]
        return df.dropna(subset=['Close'])
    except:
        return None

def get_gemini_api_key():
    key = None
    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        key = None
    if not key:
        key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    return str(key).strip()

def generate_gemini_text(api_key, prompt):
    try:
        from google import genai
    except Exception as e:
        return None, f"مكتبة google-genai غير مثبتة: {type(e).__name__}"
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        text = getattr(resp, "text", None)
        if text:
            return text, None
        try:
            return resp.candidates[0].content.parts[0].text, None
        except Exception:
            return str(resp), None
    except Exception as e:
        msg = str(e).strip()
        msg_short = (msg[:240] + "…") if len(msg) > 240 else msg
        if any(k in msg for k in ["API key not valid", "invalid api key", "Invalid API key", "PERMISSION_DENIED", "permissionDenied"]):
            hint = "تحقق من صحة المفتاح وأن Gemini API مفعّل في حسابك."
        elif any(k in msg for k in ["429", "RESOURCE_EXHAUSTED", "quota", "Too Many Requests", "rate"]):
            hint = "قد تكون الحصة انتهت أو يوجد ضغط. جرّب بعد دقائق أو أنشئ مفتاح جديد."
        else:
            hint = "تحقق من Secrets ومن صلاحيات المفتاح ثم أعد التشغيل."
        return None, f"{type(e).__name__}: {msg_short}\n{hint}"

# 4. التصميم
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo&display=swap');
    html, body, [class*="st-"] { font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; }
    .metric-card { background: white; padding: 20px; border-radius: 10px; border: 1px solid #eee; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# 5. الصفحات
def page_home():
    st.title("🏠 لوحة التحكم")
    data = get_data(list(STOCK_MAP.values()), period="5d")
    if data is not None:
        results = []
        for name, ticker in STOCK_MAP.items():
            df = clean_stock_df(data, ticker)
            if df is not None and len(df) >= 2:
                last = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                chg = ((last - prev) / prev) * 100
                results.append({"الشركة": name, "السعر": last, "التغير %": chg})
        
        if results:
            df_res = pd.DataFrame(results)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader("📈 الأعلى صعوداً")
                st.dataframe(df_res.nlargest(5, 'التغير %').style.format({'التغير %': '{:+.2f}%', 'السعر': '{:.2f}'}), hide_index=True)
            with c2:
                st.subheader("📉 الأعلى هبوطاً")
                st.dataframe(df_res.nsmallest(5, 'التغير %').style.format({'التغير %': '{:+.2f}%', 'السعر': '{:.2f}'}), hide_index=True)
            with c3:
                tasi = df_res[df_res['الشركة'] == "تاسي"]
                if not tasi.empty:
                    st.subheader("📊 مؤشر تاسي")
                    st.metric("تاسي", f"{tasi.iloc[0]['السعر']:,.2f}", f"{tasi.iloc[0]['التغير %']:+.2f}%")

def page_analysis():
    st.title("📋 تحليل سهم")
    choice = st.selectbox("اختر السهم:", list(STOCK_MAP.keys()))
    ticker = STOCK_MAP[choice]
    data = get_data([ticker], period="1y")
    if data is not None:
        df = clean_stock_df(data, ticker)
        if df is not None and not df.empty:
            df['RSI'] = ta.momentum.rsi(df['Close'], window=14).fillna(50)
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
                fig.update_layout(template="plotly_white", height=500)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.metric("مؤشر RSI", f"{df['RSI'].iloc[-1]:.2f}")
                if st.button("🤖 تحليل AI"):
                    api_key = get_gemini_api_key()
                    if api_key:
                        try:
                            prompt = f"حلل سهم {choice} بالسوق السعودي. السعر {df['Close'].iloc[-1]:.2f}. أعط نصيحة مختصرة."
                            text, err = generate_gemini_text(api_key, prompt)
                            if err:
                                st.error("خطأ في الاتصال بالذكاء الاصطناعي.")
                                st.code(err, language="text")
                            else:
                                st.info(text)
                        except Exception as e:
                            st.error("خطأ في الاتصال بالذكاء الاصطناعي.")
                            st.code(f"{type(e).__name__}: {str(e)[:240]}", language="text")
                    else:
                        st.warning("أضف GEMINI_API_KEY داخل Secrets (مع علامات اقتباس).")

# 6. التشغيل
def main():
    st.sidebar.title("FAHAD.AI 🚀")
    page = st.sidebar.radio("التنقل:", ["الرئيسية", "التحليل الفني"])
    if page == "الرئيسية": page_home()
    else: page_analysis()
    st_autorefresh(interval=300000, key="refresh")

if __name__ == "__main__":
    main()
