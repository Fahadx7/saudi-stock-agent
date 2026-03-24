# CLAUDE.md — دليل Claude Code لمنصة تريندسا

## نظرة عامة على المشروع

**الاسم:** تريندسا (Trandsa) — منصة التداول الذكي للسوق السعودي (تاسي)
**النوع:** Full-stack React + Express + Firebase
**اللغة الأساسية:** العربية (RTL)
**الهدف:** رادار أسهم ذكي يرصد فرص الدخول والخروج بناءً على مؤشرات تقنية + موجات إليوت + AI

---

## البنية التقنية

```
/
├── server.ts          ← Express backend (بيانات Yahoo Finance + Telegram + Firebase Admin)
├── vite.config.ts     ← Vite config (لا تُمرّر GEMINI_API_KEY للـ client)
├── firestore.rules    ← قواعد أمان Firestore
├── index.html         ← entry HTML (lang="ar" dir="rtl")
├── package.json       ← dependencies (firebase-admin مطلوب)
├── .env.example       ← نموذج متغيرات البيئة
└── src/
    ├── main.tsx       ← React entry point
    ├── symbols.ts     ← قاموس رموز الأسهم السعودية (SAUDI_STOCKS)
    ├── components/    ← مكونات React
    └── ...
```

---

## الـ API Endpoints

| Method | Path | Auth | الوصف |
|--------|------|------|-------|
| GET | `/api/status` | Public | حالة المسح + بيانات الأسهم |
| GET | `/api/health` | Public | فحص صحة الـ server |
| GET | `/api/history/:symbol` | Public | تاريخ سهم (30 يوم) |
| POST | `/api/feedback` | Public + Rate Limit | إرسال ملاحظة |
| POST | `/api/alerts` | Public + Rate Limit | إنشاء تنبيه مخصص |
| POST | `/api/test-telegram` | Rate Limit | اختبار اتصال Telegram |
| POST | `/api/scan` | **Admin Auth مطلوب** | تشغيل مسح يدوي |

---

## Firestore Collections

| Collection | الوصف | من يكتب |
|------------|-------|---------|
| `/users/{uid}` | ملف المستخدم (role, email) | Client |
| `/watchlists/{id}` | قائمة المتابعة | Client |
| `/feedback/{id}` | ملاحظات المستخدمين | Server (Admin SDK) |
| `/active_trades/{symbol}` | الصفقات المفتوحة | Server (Admin SDK) فقط |
| `/custom_alerts/{id}` | التنبيهات المخصصة | Server (Admin SDK) |
| `/margin_accounts/{uid}` | حساب الهامش | Client |
| `/margin_positions/{id}` | مراكز الهامش | Client |

---

## قواعد مهمة عند التطوير

### ❌ لا تفعل أبداً
- لا تُمرّر `GEMINI_API_KEY` لـ `vite.config.ts` define — المفتاح للـ backend فقط
- لا تضع بريد إلكتروني شخصي في `firestore.rules`
- لا تستخدم `as any` — استخدم الأنواع الصحيحة
- لا تترك `catch(e) {}` فارغة — سجّل الخطأ دائماً
- لا تكتب مباشرة في collection `active_trades` من الـ client

### ✅ افعل دائماً
- استخدم `validateSymbol()` قبل أي طلب يحتوي رمز سهم
- استخدم `rateLimit()` middleware على كل endpoint
- حفظ البيانات المهمة (صفقات، تنبيهات) في Firestore قبل إرسال Telegram
- اتبع نمط `lang="ar" dir="rtl"` في أي HTML جديد

---

## المؤشرات التقنية

### calculateMACD (O(n) — محسّن)
```typescript
// استخدم calculateEMAArray() للحصول على كل القيم دفعة واحدة
// لا تستدعي calculateEMA() داخل loop — هذا O(n²)
const ema12Array = calculateEMAArray(closes, 12);
const ema26Array = calculateEMAArray(closes, 26);
```

### نسبة التغيير الصحيحة
```typescript
// ✅ صح — التغيير اليومي
const changePercent = ((lastClose - prevClose) / prevClose) * 100;

// ❌ خطأ — تغيير 7 أيام
const changePercent = ((lastClose - closes[0]) / closes[0]) * 100;
```

---

## الـ Firebase Admin

```typescript
// تهيئة تلقائية عبر ADC
admin.initializeApp({ credential: admin.credential.applicationDefault() });

// الكتابة من Server تتجاوز firestore.rules تلقائياً
await adminDb.collection("active_trades").doc(symbol).set(trade);
```

لتعيين مدير جديد (بدلاً من hardcoded email):
```typescript
// من Cloud Functions أو Admin script:
await adminDb.collection("users").doc(uid).update({ role: "admin" });
```

---

## المتغيرات البيئية المطلوبة

```bash
GEMINI_API_KEY=           # للـ backend فقط
FIREBASE_PROJECT_ID=      # ID المشروع
FIREBASE_DATABASE_ID=     # ID قاعدة Firestore
GOOGLE_APPLICATION_CREDENTIALS=  # مسار ملف Service Account
TELEGRAM_TOKEN=           # توكن البوت
TELEGRAM_CHAT_ID=         # ID المحادثة
```

---

## أولويات العمل القادمة

1. **[عاجل]** إضافة Firebase Auth في Frontend لتمرير JWT token مع طلب `/api/scan`
2. **[عاجل]** إنشاء ملف `firebase-service-account.json` من Firebase Console
3. **[مهم]** إضافة `src/api/client.ts` — wrapper موحّد لكل API calls مع error handling
4. **[مهم]** نشر على Cloud Run أو Railway مع الـ environment variables
5. **[تحسين]** إضافة WebSocket لتحديث البيانات في الوقت الفعلي بدلاً من polling
6. **[تحسين]** إضافة Redis لـ caching بيانات الأسهم (تقليل طلبات Yahoo Finance)

---

## تشغيل المشروع محلياً

```bash
# 1. نسخ متغيرات البيئة
cp .env.example .env.local

# 2. تعبئة المتغيرات في .env.local

# 3. تثبيت الـ packages
npm install

# 4. تشغيل السيرفر
npm run dev
```

---

*آخر تحديث: 2026-03 | تريندسا v1.0*
