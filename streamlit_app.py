import streamlit as st
import yfinance as yf
import pandas as pd
from google import genai

# إعداد الصفحة الأساسي
st.set_page_config(page_title="FAHAD.AI", layout="wide")

st.title("🚀 FAHAD.AI - النسخة المستقرة")

# وظيفة جلب البيانات بنظام الحماية
def fetch_safe_data(ticker):
    try:
        # محاولة جلب بيانات يومين فقط للتأكد من الاتصال
        data = yf.download(ticker, period="5d", interval="1d", progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except:
        return None

# القائمة الجانبية
page = st.sidebar.radio("التنقل", ["الرئيسية", "التحليل"])

if page == "الرئيسية":
    st.subheader("📊 ملخص السوق السريع")
    tasi_data = fetch_safe_data("^TASI")
    
    if tasi_data is not None and not tasi_data.empty:
        last_price = tasi_data['Close'].iloc[-1]
        st.metric("مؤشر تاسي", f"{last_price:.2f}")
        st.line_chart(tasi_data['Close'])
    else:
        st.error("⚠️ عذراً، ياهو فاينانس يرفض الاتصال حالياً. حاول إعادة تشغيل التطبيق بعد دقيقتين.")

elif page == "التحليل":
    st.subheader("📋 تحليل سهم محدد")
    symbol = st.text_input("أدخل رمز السهم (مثال: 1120):", "1120")
    if st.button("تحليل"):
        data = fetch_safe_data(f"{symbol}.SR")
        if data is not None and not data.empty:
            st.write(f"آخر سعر لإغلاق {symbol} هو: {data['Close'].iloc[-1]:.2f}")
            st.dataframe(data.tail())
        else:
            st.warning("لم يتم العثور على بيانات.")

st.sidebar.markdown("---")
st.sidebar.info("إذا ظهرت شاشة سوداء، يرجى الضغط على 'Reboot App' من لوحة تحكم Streamlit.")
