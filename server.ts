import express, { Request, Response, NextFunction } from "express";
import { createServer as createViteServer } from "vite";
import path from "path";
import yahooFinance from "yahoo-finance2";
import fetch from "node-fetch";
import { SAUDI_STOCKS } from "./src/symbols";

// ═══════════════════════════════════════════════════════════════════
// Firebase Admin — للمصادقة من جهة الـ Server
// ═══════════════════════════════════════════════════════════════════
import admin from "firebase-admin";

let adminDb: admin.firestore.Firestore | null = null;
let adminInitialized = false;

function initFirebaseAdmin() {
    if (adminInitialized) return;
    try {
        if (admin.apps.length === 0) {
            // يستخدم Application Default Credentials عند النشر على Google Cloud
            // أو GOOGLE_APPLICATION_CREDENTIALS env var محلياً
            admin.initializeApp({
                credential: admin.credential.applicationDefault(),
                projectId: process.env.FIREBASE_PROJECT_ID || "gen-lang-client-0929071098",
            });
        }
        adminDb = admin.firestore();
        adminDb.settings({ databaseId: process.env.FIREBASE_DATABASE_ID || "ai-studio-34bf63a9-aefc-4316-ab7b-dedb83ef4837" });
        adminInitialized = true;
        console.log("✅ Firebase Admin تم تهيئته بنجاح");
    } catch (e: any) {
        console.warn("⚠️ Firebase Admin لم يُهيَّأ — بعض الميزات ستعمل بدون Persistence:", e.message);
        adminInitialized = true; // لا تحاول مرة أخرى
    }
}

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════
interface StockData {
    symbol: string;
    companyName: string;
    price: number;
    change: number;
    volume: number;
    volumeRatio: number;
    rsi: number;
    wave: string;
    macd: { macd: number; signal: number; histogram: number };
    bb: { middle: number; upper: number; lower: number };
}

interface ActiveTrade {
    symbol: string;
    companyName: string;
    entryPrice: number;
    entryTime: string;
    rsi: number;
    sma50: number;
    wave: string;
}

interface CustomAlert {
    id: string;
    symbol: string;
    targetPrice?: number;
    targetRsi?: number;
    triggered: boolean;
    createdAt: string;
    userId?: string;
}

interface BotStatus {
    isValid: boolean;
    name: string | null;
    username: string | null;
    lastError: string | null;
    lastChecked: string | null;
    isFormatValid: boolean;
}

// ═══════════════════════════════════════════════════════════════════
// إعدادات التليجرام
// ═══════════════════════════════════════════════════════════════════
const cleanToken = (t: string) =>
    t ? t.replace(/\s/g, "").replace(/^TOKEN=/i, "").replace(/^"|"$/g, "").trim() : "";

const TOKEN = cleanToken(process.env.TELEGRAM_TOKEN || "");
const CHAT_ID = (process.env.TELEGRAM_CHAT_ID || "")
    .replace(/\s/g, "")
    .replace(/^ID=/i, "")
    .replace(/^"|"$/g, "")
    .trim();

const isTokenFormatValid = (t: string) => /^\d+:[A-Za-z0-9_-]{35,}$/.test(t);

let botStatus: BotStatus = {
    isValid: false,
    name: null,
    username: null,
    lastError: null,
    lastChecked: null,
    isFormatValid: false,
};

// ═══════════════════════════════════════════════════════════════════
// الحالة في الذاكرة (مع Firestore Persistence للبيانات المهمة)
// ═══════════════════════════════════════════════════════════════════
let activeTrades: Record<string, ActiveTrade> = {};
let customAlerts: CustomAlert[] = [];

let scanStatus = {
    lastScan: null as string | null,
    isScanning: false,
    processedCount: 0,
    totalCount: 0,
    alerts: [] as any[],
    topGainers: [] as StockData[],
    topLosers: [] as StockData[],
    liquidityEntry: [] as StockData[],
    liquidityExit: [] as StockData[],
    waveStocks: [] as StockData[],
    tickerData: new Map<string, StockData>(),
    marketIndex: null as any,
    telegramBotName: null as string | null,
};

// ═══════════════════════════════════════════════════════════════════
// Firestore Persistence Helpers
// ═══════════════════════════════════════════════════════════════════

/** تحميل الصفقات المفتوحة من Firestore عند التشغيل */
async function loadActiveTradesFromFirestore() {
    if (!adminDb) return;
    try {
        const snap = await adminDb.collection("active_trades").get();
        snap.forEach((doc) => {
            activeTrades[doc.id] = doc.data() as ActiveTrade;
        });
        console.log(`📂 تم تحميل ${snap.size} صفقة مفتوحة من Firestore`);
    } catch (e: any) {
        console.warn("⚠️ فشل تحميل الصفقات من Firestore:", e.message);
    }
}

/** حفظ صفقة في Firestore */
async function saveTradeToFirestore(symbol: string, trade: ActiveTrade) {
    if (!adminDb) return;
    try {
        await adminDb.collection("active_trades").doc(symbol).set(trade);
    } catch (e: any) {
        console.warn(`⚠️ فشل حفظ الصفقة ${symbol}:`, e.message);
    }
}

/** حذف صفقة من Firestore عند الإغلاق */
async function deleteTradeFromFirestore(symbol: string) {
    if (!adminDb) return;
    try {
        await adminDb.collection("active_trades").doc(symbol).delete();
    } catch (e: any) {
        console.warn(`⚠️ فشل حذف الصفقة ${symbol}:`, e.message);
    }
}

/** تحميل التنبيهات من Firestore */
async function loadAlertsFromFirestore() {
    if (!adminDb) return;
    try {
        const snap = await adminDb
            .collection("custom_alerts")
            .where("triggered", "==", false)
            .get();
        snap.forEach((doc) => {
            customAlerts.push({ id: doc.id, ...doc.data() } as CustomAlert);
        });
        console.log(`📂 تم تحميل ${snap.size} تنبيه من Firestore`);
    } catch (e: any) {
        console.warn("⚠️ فشل تحميل التنبيهات من Firestore:", e.message);
    }
}

/** حفظ تنبيه في Firestore */
async function saveAlertToFirestore(alert: CustomAlert): Promise<string> {
    if (!adminDb) return alert.id;
    try {
        const docRef = await adminDb.collection("custom_alerts").add(alert);
        return docRef.id;
    } catch (e: any) {
        console.warn("⚠️ فشل حفظ التنبيه:", e.message);
        return alert.id;
    }
}

/** حفظ feedback في Firestore */
async function saveFeedbackToFirestore(data: {
    name?: string;
    email?: string;
    type: string;
    message: string;
    userId?: string;
}) {
    if (!adminDb) return;
    try {
        await adminDb.collection("feedback").add({
            ...data,
            createdAt: admin.firestore.FieldValue.serverTimestamp(),
        });
    } catch (e: any) {
        console.warn("⚠️ فشل حفظ feedback في Firestore:", e.message);
    }
}

// ═══════════════════════════════════════════════════════════════════
// Auth Middleware
// ═══════════════════════════════════════════════════════════════════

/** التحقق من Firebase JWT token */
async function verifyFirebaseToken(
    req: Request,
    res: Response,
    next: NextFunction
) {
    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith("Bearer ")) {
        return res.status(401).json({ error: "غير مصرح — مطلوب Bearer token" });
    }
    const idToken = authHeader.split("Bearer ")[1];
    try {
        if (!adminInitialized || !admin.apps.length) {
            // في بيئة التطوير بدون Admin SDK — السماح بالمرور مع تحذير
            console.warn("⚠️ Firebase Admin غير مهيأ — تخطي التحقق من الـ Token (بيئة تطوير فقط)");
            (req as any).user = { uid: "dev-user", role: "admin" };
            return next();
        }
        const decoded = await admin.auth().verifyIdToken(idToken);
        (req as any).user = decoded;
        next();
    } catch (e: any) {
        return res.status(401).json({ error: "Token غير صالح أو منتهي الصلاحية" });
    }
}

/** التحقق من أن المستخدم admin */
async function requireAdmin(req: Request, res: Response, next: NextFunction) {
    await verifyFirebaseToken(req, res, async () => {
        const uid = (req as any).user?.uid;
        if (!uid || !adminDb) {
            return res.status(403).json({ error: "غير مصرح — مطلوب صلاحيات المدير" });
        }
        try {
            const userDoc = await adminDb.collection("users").doc(uid).get();
            if (userDoc.exists && userDoc.data()?.role === "admin") {
                return next();
            }
            return res.status(403).json({ error: "غير مصرح — ليس مديراً" });
        } catch (e) {
            return res.status(500).json({ error: "خطأ في التحقق من الصلاحيات" });
        }
    });
}

// ═══════════════════════════════════════════════════════════════════
// التحقق من البوت
// ═══════════════════════════════════════════════════════════════════
async function checkBot() {
    botStatus.lastChecked = new Date().toISOString();
    botStatus.isFormatValid = isTokenFormatValid(TOKEN);

    if (!TOKEN || TOKEN.includes("YOUR_TOKEN")) {
        botStatus.isValid = false;
        botStatus.lastError = "التوكن غير مضبوط";
        return;
    }
    if (!botStatus.isFormatValid) {
        botStatus.isValid = false;
        botStatus.lastError = "تنسيق التوكن غير صحيح";
        return;
    }
    try {
        const res = await fetch(`https://api.telegram.org/bot${TOKEN}/getMe`);
        const data: any = await res.json();
        if (data.ok) {
            botStatus.isValid = true;
            botStatus.name = data.result.first_name;
            botStatus.username = data.result.username;
            botStatus.lastError = null;
            scanStatus.telegramBotName = data.result.username;
            console.log(`✅ البوت متصل: @${data.result.username}`);
        } else {
            botStatus.isValid = false;
            botStatus.lastError = `${data.error_code}: ${data.description}`;
        }
    } catch (e: any) {
        botStatus.isValid = false;
        botStatus.lastError = `خطأ في الاتصال: ${e.message}`;
    }
}

async function sendTelegramMsg(message: string): Promise<{ success: boolean; error?: string }> {
    if (!TOKEN || !botStatus.isValid || !CHAT_ID) {
        return { success: false, error: "Telegram غير مهيأ" };
    }
    try {
        const response = await fetch(
            `https://api.telegram.org/bot${TOKEN}/sendMessage`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    chat_id: CHAT_ID,
                    text: message,
                    parse_mode: "Markdown",
                }),
            }
        );
        const data: any = await response.json().catch(() => ({}));
        if (!response.ok) {
            const err = data.description || `HTTP ${response.status}`;
            console.error(`❌ فشل إرسال Telegram: ${err}`);
            return { success: false, error: err };
        }
        return { success: true };
    } catch (e: any) {
        console.error(`❌ خطأ في Telegram:`, e.message);
        return { success: false, error: e.message };
    }
}

// ═══════════════════════════════════════════════════════════════════
// المؤشرات التقنية — محسّنة
// ═══════════════════════════════════════════════════════════════════

function calculateRSI(closes: number[], period = 14): number {
    if (closes.length <= period) return 50;
    let avgGain = 0;
    let avgLoss = 0;

    for (let i = 1; i <= period; i++) {
        const diff = closes[i] - closes[i - 1];
        if (diff > 0) avgGain += diff;
        else avgLoss += -diff;
    }
    avgGain /= period;
    avgLoss /= period;

    // Wilder's Smoothing
    for (let i = period + 1; i < closes.length; i++) {
        const diff = closes[i] - closes[i - 1];
        const gain = diff > 0 ? diff : 0;
        const loss = diff < 0 ? -diff : 0;
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
    }

    if (avgLoss === 0) return 100;
    return 100 - 100 / (1 + avgGain / avgLoss);
}

/**
 * حساب EMA بشكل تدريجي — O(n) بدلاً من O(n²)
 * يُرجع مصفوفة بطول (closes.length - period + 1)
 * العنصر [0] يقابل closes[period-1]
 */
function calculateEMAArray(data: number[], period: number): number[] {
    if (data.length < period) return [];
    const k = 2 / (period + 1);
    const result: number[] = [];

    // أول قيمة = SMA
    let ema = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
    result.push(ema);

    for (let i = period; i < data.length; i++) {
        ema = data[i] * k + ema * (1 - k);
        result.push(ema);
    }
    return result;
}

/** حساب EMA لآخر قيمة فقط — O(n) */
function calculateEMA(data: number[], period: number): number {
    const arr = calculateEMAArray(data, period);
    return arr.length > 0 ? arr[arr.length - 1] : 0;
}

/**
 * MACD محسّن — O(n) بدلاً من O(n²)
 * الكود القديم كان يُعيد حساب EMA من الصفر في كل iteration
 */
function calculateMACD(closes: number[]): {
    macd: number;
    signal: number;
    histogram: number;
} {
    if (closes.length < 26) return { macd: 0, signal: 0, histogram: 0 };

    // حساب EMA 12 و 26 مرة واحدة فقط — O(n)
    const ema12Array = calculateEMAArray(closes, 12); // index 0 = closes[11]
    const ema26Array = calculateEMAArray(closes, 26); // index 0 = closes[25]

    // بناء خط MACD: المحاذاة — EMA26 يبدأ من closes[25]، EMA12 يبدأ من closes[11]
    // الفرق في البداية = 25 - 11 = 14، أي ema12Array[14] يقابل ema26Array[0]
    const offset = 26 - 12; // = 14
    const macdLine: number[] = [];

    for (let i = 0; i < ema26Array.length; i++) {
        const ema12Val = ema12Array[i + offset];
        if (ema12Val !== undefined) {
            macdLine.push(ema12Val - ema26Array[i]);
        }
    }

    if (macdLine.length === 0) return { macd: 0, signal: 0, histogram: 0 };

    // Signal line = EMA 9 على خط MACD
    const signalArray = calculateEMAArray(macdLine, 9);
    const lastMACD = macdLine[macdLine.length - 1];
    const lastSignal = signalArray.length > 0 ? signalArray[signalArray.length - 1] : lastMACD;

    return {
        macd: Number(lastMACD.toFixed(4)),
        signal: Number(lastSignal.toFixed(4)),
        histogram: Number((lastMACD - lastSignal).toFixed(4)),
    };
}

function calculateBollingerBands(
    closes: number[],
    period = 20,
    multiplier = 2
): { middle: number; upper: number; lower: number } {
    if (closes.length < period) return { middle: 0, upper: 0, lower: 0 };

    const lastPeriod = closes.slice(-period);
    const middle = lastPeriod.reduce((a, b) => a + b, 0) / period;
    const variance =
        lastPeriod.reduce((a, b) => a + Math.pow(b - middle, 2), 0) / period;
    const stdDev = Math.sqrt(variance);

    return {
        middle: Number(middle.toFixed(2)),
        upper: Number((middle + multiplier * stdDev).toFixed(2)),
        lower: Number((middle - multiplier * stdDev).toFixed(2)),
    };
}

// ═══════════════════════════════════════════════════════════════════
// تحليل السهم
// ═══════════════════════════════════════════════════════════════════
async function analyzeStock(symbol: string): Promise<void> {
    try {
        const period1 = Math.floor(Date.now() / 1000) - 7 * 24 * 60 * 60;
        const result = await yahooFinance.chart(symbol, {
            interval: "5m",
            period1,
        }) as any;

        if (!result?.quotes || result.quotes.length < 50) {
            // Fallback: بيانات أساسية فقط
            try {
                const quote = await yahooFinance.quote(symbol) as any;
                if (quote?.regularMarketPrice) {
                    const existing = scanStatus.tickerData.get(symbol);
                    scanStatus.tickerData.set(symbol, {
                        symbol,
                        companyName: SAUDI_STOCKS[symbol.split(".")[0]] || symbol,
                        price: quote.regularMarketPrice,
                        change: quote.regularMarketChangePercent || 0,
                        volume: quote.regularMarketVolume || 0,
                        volumeRatio: existing?.volumeRatio ?? 1,
                        rsi: existing?.rsi ?? 50,
                        wave: existing?.wave ?? "غير محدد",
                        macd: existing?.macd ?? { macd: 0, signal: 0, histogram: 0 },
                        bb: existing?.bb ?? { middle: 0, upper: 0, lower: 0 },
                    });
                }
            } catch (fallbackErr: any) {
                console.warn(`[skip fallback] ${symbol}: ${fallbackErr.message}`);
            }
            return;
        }

        const quotes = (result.quotes as any[]).filter(
            (q) => q.close !== null && q.volume !== null
        );
        if (quotes.length < 50) return;

        const closes = quotes.map((q) => q.close as number);
        const volumes = quotes.map((q) => q.volume as number);

        const lastClose = closes[closes.length - 1];
        const lastVolume = volumes[volumes.length - 1];

        // ✅ FIX: نسبة التغيير اليومية الصحيحة (الإغلاق السابق وليس أول نقطة في 7 أيام)
        const prevClose = closes[closes.length - 2];
        const changePercent = prevClose > 0
            ? ((lastClose - prevClose) / prevClose) * 100
            : 0;

        const sma50 = closes.slice(-50).reduce((a, b) => a + b, 0) / 50;
        const rsi = calculateRSI(closes, 14);
        const macdData = calculateMACD(closes); // ✅ الآن O(n) وليس O(n²)
        const bbData = calculateBollingerBands(closes);
        const avgVolume = volumes.slice(-10).reduce((a, b) => a + b, 0) / 10;
        const volumeRatio = avgVolume > 0 ? lastVolume / avgVolume : 1;
        const companyName = SAUDI_STOCKS[symbol.split(".")[0]] || symbol;

        // ─── موجات إليوت المبسطة ───────────────────────────────────
        let elliottWave = "غير محدد";
        const windowSize = 10;
        const recentCloses = closes.slice(-40);
        const pivots: { type: "high" | "low"; price: number; index: number }[] = [];

        for (let i = windowSize; i < recentCloses.length - windowSize; i++) {
            const current = recentCloses[i];
            const left = recentCloses.slice(i - windowSize, i);
            const right = recentCloses.slice(i + 1, i + windowSize + 1);
            if (current > Math.max(...left) && current > Math.max(...right)) {
                pivots.push({ type: "high", price: current, index: i });
            } else if (current < Math.min(...left) && current < Math.min(...right)) {
                pivots.push({ type: "low", price: current, index: i });
            }
        }

        if (pivots.length >= 3) {
            const last3 = pivots.slice(-3);
            if (
                last3[0].type === "low" &&
                last3[1].type === "high" &&
                last3[2].type === "low"
            ) {
                if (last3[2].price > last3[0].price && lastClose > last3[1].price) {
                    elliottWave = "بداية الموجة 3 (انفجارية) 🚀";
                } else if (
                    last3[2].price > last3[0].price &&
                    lastClose < last3[1].price
                ) {
                    elliottWave = "نهاية الموجة 2 (تصحيح منتهي) ⏳";
                }
            } else if (
                last3[0].type === "high" &&
                last3[1].type === "low" &&
                last3[2].type === "high"
            ) {
                if (last3[2].price < last3[0].price && lastClose < last3[1].price) {
                    elliottWave = "بداية موجة هابطة 📉";
                }
            }
        } else if (pivots.length >= 2) {
            const last2 = pivots.slice(-2);
            if (
                last2[0].type === "low" &&
                last2[1].type === "high" &&
                lastClose > last2[1].price
            ) {
                elliottWave = "اختراق قمة سابقة ⚡";
            }
        }

        const stockData: StockData = {
            symbol,
            companyName,
            price: lastClose,
            change: changePercent,
            volume: lastVolume,
            volumeRatio,
            rsi,
            wave: elliottWave,
            macd: macdData,
            bb: bbData,
        };

        scanStatus.tickerData.set(symbol, stockData);

        if (changePercent > 0) scanStatus.topGainers.push(stockData);
        else if (changePercent < 0) scanStatus.topLosers.push(stockData);
        if (volumeRatio > 2 && changePercent > 0) scanStatus.liquidityEntry.push(stockData);
        else if (volumeRatio > 2 && changePercent < 0) scanStatus.liquidityExit.push(stockData);
        if (elliottWave !== "غير محدد") scanStatus.waveStocks.push(stockData);

        // ─── التنبيهات المخصصة ────────────────────────────────────
        for (const alert of customAlerts) {
            if (alert.symbol !== symbol || alert.triggered) continue;
            let triggered = false;
            let reason = "";

            if (alert.targetPrice !== undefined && lastClose >= alert.targetPrice) {
                triggered = true;
                reason = `وصل السعر إلى الهدف: ${alert.targetPrice}`;
            }
            if (alert.targetRsi !== undefined && rsi >= alert.targetRsi) {
                triggered = true;
                reason = `وصل RSI إلى الهدف: ${alert.targetRsi}`;
            }

            if (triggered) {
                alert.triggered = true;
                // تحديث Firestore
                if (adminDb && alert.id) {
                    adminDb
                        .collection("custom_alerts")
                        .doc(alert.id)
                        .update({ triggered: true })
                        .catch((e: any) => console.warn("فشل تحديث التنبيه:", e.message));
                }
                const alertMsg =
                    `🔔 *تنبيه مخصص!*\n` +
                    `━━━━━━━━━━━━━━━\n` +
                    `🏢 الشركة: *${companyName}*\n` +
                    `📦 الرمز: \`${symbol}\`\n` +
                    `💰 السعر الحالي: \`${lastClose.toFixed(2)}\`\n` +
                    `📈 RSI: \`${rsi.toFixed(1)}\`\n` +
                    `📝 السبب: *${reason}*\n` +
                    `━━━━━━━━━━━━━━━\n` +
                    `⚡️ *رادار صائد الفرص الذكي*`;
                await sendTelegramMsg(alertMsg);
                scanStatus.alerts.unshift({
                    type: "entry",
                    symbol,
                    companyName,
                    price: lastClose,
                    time: new Date().toISOString(),
                    wave: `تنبيه مخصص: ${reason}`,
                });
            }
        }

        if (activeTrades[symbol]) {
            activeTrades[symbol].wave = elliottWave;
        }

        // ─── شروط الدخول ─────────────────────────────────────────
        const isBullishWave =
            elliottWave.includes("الموجة 3") || elliottWave.includes("اختراق");
        const isVolumeBreakout = volumeRatio > 1.8;
        const isRsiBullish = rsi > 50 && rsi < 75;
        const isPriceAboveSma = lastClose > sma50;

        if (
            ((isPriceAboveSma && isRsiBullish && isVolumeBreakout) || isBullishWave) &&
            !activeTrades[symbol]
        ) {
            const waveInfo =
                elliottWave !== "غير محدد" ? `\n🌊 الموجة: *${elliottWave}*` : "";
            const msg =
                `🚀 *فرصة ذهبية مكتشفة!*\n` +
                `━━━━━━━━━━━━━━━\n` +
                `🏢 الشركة: *${companyName}*\n` +
                `📦 الرمز: \`${symbol}\`\n` +
                `💰 السعر: \`${lastClose.toFixed(2)}\`\n` +
                `📈 RSI: \`${rsi.toFixed(1)}\`\n` +
                `📊 حجم التداول: \`${(lastVolume / 1000).toFixed(1)}K\`\n` +
                `${waveInfo}\n` +
                `━━━━━━━━━━━━━━━\n` +
                `🎯 الهدف الأول: \`${(lastClose * 1.03).toFixed(2)}\`\n` +
                `🎯 الهدف الثاني: \`${(lastClose * 1.05).toFixed(2)}\`\n` +
                `🛑 وقف الخسارة: \`${(lastClose * 0.97).toFixed(2)}\`\n` +
                `━━━━━━━━━━━━━━━\n` +
                `⚡️ *رادار صائد الفرص الذكي*`;

            await sendTelegramMsg(msg);

            const newTrade: ActiveTrade = {
                symbol,
                companyName,
                entryPrice: lastClose,
                entryTime: new Date().toISOString(),
                rsi,
                sma50,
                wave: elliottWave,
            };
            activeTrades[symbol] = newTrade;
            await saveTradeToFirestore(symbol, newTrade); // ✅ حفظ في Firestore

            scanStatus.alerts.unshift({
                type: "entry",
                symbol,
                companyName,
                price: lastClose,
                wave: elliottWave,
                time: new Date().toISOString(),
            });
        }

        // ─── شروط الخروج ─────────────────────────────────────────
        const isRsiOverbought = rsi > 82;
        const isPriceBelowSma = lastClose < sma50;
        const isRsiWeakening = rsi < 38;

        if (
            (isPriceBelowSma || isRsiOverbought || isRsiWeakening) &&
            activeTrades[symbol]
        ) {
            const entryPrice = activeTrades[symbol].entryPrice;
            const profit = ((lastClose - entryPrice) / entryPrice) * 100;
            const profitEmoji = profit >= 0 ? "💰" : "📉";
            const exitReason = isPriceBelowSma
                ? "كسر متوسط 50 لأسفل"
                : isRsiOverbought
                ? "تشبع شرائي (RSI > 82)"
                : "ضعف الزخم (RSI < 38)";

            await sendTelegramMsg(
                `⚠️ *تنبيه جني أرباح / خروج!*\n\n` +
                    `🏢 الشركة: *${companyName}*\n` +
                    `📦 الرمز: \`${symbol}\`\n` +
                    `💵 سعر الخروج: \`${lastClose.toFixed(2)}\`\n` +
                    `${profitEmoji} النتيجة: \`${profit.toFixed(2)}%\`\n` +
                    `🛑 السبب: ${exitReason}.`
            );

            delete activeTrades[symbol];
            await deleteTradeFromFirestore(symbol); // ✅ حذف من Firestore

            scanStatus.alerts.unshift({
                type: "exit",
                symbol,
                companyName,
                price: lastClose,
                profit,
                time: new Date().toISOString(),
            });
        }
    } catch (e: any) {
        if (
            e.message?.includes("No data found") ||
            e.message?.includes("delisted")
        ) {
            return; // سهم محذوف أو غير مدرج — تجاهل بصمت
        }
        // ✅ FIX: لا تبتلع الأخطاء — سجّلها
        console.warn(`[analyzeStock] ${symbol}: ${e.message}`);
    }
}

// ═══════════════════════════════════════════════════════════════════
// المسح الشامل
// ═══════════════════════════════════════════════════════════════════
async function startFullScan() {
    if (scanStatus.isScanning) return;

    scanStatus.isScanning = true;
    scanStatus.processedCount = 0;
    // ✅ تصفير المصفوفات في كل دورة مسح جديدة
    scanStatus.topGainers = [];
    scanStatus.topLosers = [];
    scanStatus.liquidityEntry = [];
    scanStatus.liquidityExit = [];
    scanStatus.waveStocks = [];

    console.log(`🚀 بدأ مسح السوق... ${new Date().toLocaleTimeString()}`);

    // جلب مؤشر TASI
    try {
        const tasiResult = await yahooFinance.quote("^TASI") as any;
        if (tasiResult) {
            scanStatus.marketIndex = {
                price: tasiResult.regularMarketPrice,
                change: tasiResult.regularMarketChange,
                changePercent: tasiResult.regularMarketChangePercent,
                high: tasiResult.regularMarketDayHigh,
                low: tasiResult.regularMarketDayLow,
                volume: tasiResult.regularMarketVolume,
                time: new Date().toISOString(),
            };
        }
    } catch (e: any) {
        console.warn("خطأ في جلب TASI:", e.message);
    }

    const symbols = Object.keys(SAUDI_STOCKS).map((s) => `${s}.SR`);
    scanStatus.totalCount = symbols.length;

    // المرحلة 1: أسعار لحظية سريعة بحزم
    const quoteChunkSize = 20;
    for (let i = 0; i < symbols.length; i += quoteChunkSize) {
        const chunk = symbols.slice(i, i + quoteChunkSize);
        try {
            const quotes = await yahooFinance.quote(chunk) as any;
            if (!Array.isArray(quotes)) continue;

            for (const q of quotes) {
                if (!q?.symbol) continue;
                scanStatus.tickerData.set(q.symbol, {
                    symbol: q.symbol,
                    companyName: SAUDI_STOCKS[q.symbol.split(".")[0]] || q.symbol,
                    price: q.regularMarketPrice || 0,
                    change: q.regularMarketChangePercent || 0,
                    volume: q.regularMarketVolume || 0,
                    volumeRatio: 1,
                    rsi: 50,
                    wave: "جاري التحليل...",
                    macd: { macd: 0, signal: 0, histogram: 0 },
                    bb: { middle: 0, upper: 0, lower: 0 },
                });
            }
        } catch (e: any) {
            console.warn(`فشل حزمة الأسعار [${i}]:`, e.message);
            // Fallback فردي
            for (const s of chunk) {
                try {
                    const q = await yahooFinance.quote(s) as any;
                    if (q?.symbol) {
                        scanStatus.tickerData.set(q.symbol, {
                            symbol: q.symbol,
                            companyName: SAUDI_STOCKS[q.symbol.split(".")[0]] || q.symbol,
                            price: q.regularMarketPrice || 0,
                            change: q.regularMarketChangePercent || 0,
                            volume: q.regularMarketVolume || 0,
                            volumeRatio: 1,
                            rsi: 50,
                            wave: "جاري التحليل...",
                            macd: { macd: 0, signal: 0, histogram: 0 },
                            bb: { middle: 0, upper: 0, lower: 0 },
                        });
                    }
                } catch (innerE: any) {
                    console.warn(`[skip] ${s}: ${innerE.message}`);
                }
            }
        }
        await new Promise((r) => setTimeout(r, 300));
    }

    // المرحلة 2: تحليل عميق (RSI + موجات إليوت + MACD)
    const chunkSize = 5;
    for (let i = 0; i < symbols.length; i += chunkSize) {
        const chunk = symbols.slice(i, i + chunkSize);
        await Promise.all(
            chunk.map(async (s) => {
                let retries = 2;
                while (retries > 0) {
                    try {
                        await analyzeStock(s);
                        break;
                    } catch (e: any) {
                        retries--;
                        if (retries > 0)
                            await new Promise((r) => setTimeout(r, 1000));
                        else console.warn(`[analyzeStock exhausted] ${s}: ${e.message}`);
                    }
                }
            })
        );
        scanStatus.processedCount += chunk.length;
        await new Promise((r) => setTimeout(r, 1000));
    }

    scanStatus.isScanning = false;
    scanStatus.lastScan = new Date().toISOString();

    // ترتيب وتحديد الأعلى
    scanStatus.topGainers.sort((a, b) => b.change - a.change);
    scanStatus.topLosers.sort((a, b) => a.change - b.change);
    scanStatus.liquidityEntry.sort((a, b) => b.volumeRatio - a.volumeRatio);
    scanStatus.liquidityExit.sort((a, b) => b.volumeRatio - a.volumeRatio);
    scanStatus.topGainers = scanStatus.topGainers.slice(0, 10);
    scanStatus.topLosers = scanStatus.topLosers.slice(0, 10);
    scanStatus.liquidityEntry = scanStatus.liquidityEntry.slice(0, 10);
    scanStatus.liquidityExit = scanStatus.liquidityExit.slice(0, 10);

    console.log("✅ اكتمل المسح.");
}

// ═══════════════════════════════════════════════════════════════════
// Input Validation Helpers
// ═══════════════════════════════════════════════════════════════════
const VALID_SYMBOL_RE = /^[0-9]{4}(\.SR)?$/;
const MAX_ALERTS_PER_REQUEST = 50;

function validateSymbol(symbol: unknown): string | null {
    if (typeof symbol !== "string") return null;
    const s = symbol.trim().toUpperCase();
    if (!VALID_SYMBOL_RE.test(s)) return null;
    return s.includes(".SR") ? s : `${s}.SR`;
}

function validatePrice(val: unknown): number | null {
    const n = parseFloat(String(val));
    if (!isFinite(n) || n <= 0 || n > 1_000_000) return null;
    return n;
}

function validateRsi(val: unknown): number | null {
    const n = parseFloat(String(val));
    if (!isFinite(n) || n < 0 || n > 100) return null;
    return n;
}

// ═══════════════════════════════════════════════════════════════════
// Simple In-Memory Rate Limiter
// ═══════════════════════════════════════════════════════════════════
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function rateLimit(
    windowMs: number,
    maxRequests: number
): (req: Request, res: Response, next: NextFunction) => void {
    return (req, res, next) => {
        const key = req.ip || "unknown";
        const now = Date.now();
        const entry = rateLimitMap.get(key);

        if (!entry || now > entry.resetAt) {
            rateLimitMap.set(key, { count: 1, resetAt: now + windowMs });
            return next();
        }
        entry.count++;
        if (entry.count > maxRequests) {
            return res
                .status(429)
                .json({ error: "طلبات كثيرة جداً — حاول لاحقاً" });
        }
        next();
    };
}

// ═══════════════════════════════════════════════════════════════════
// Server
// ═══════════════════════════════════════════════════════════════════
async function startServer() {
    initFirebaseAdmin();
    await checkBot();
    await loadActiveTradesFromFirestore();
    await loadAlertsFromFirestore();

    const app = express();
    const PORT = 3000;

    app.use(express.json({ limit: "1mb" }));

    // ─── Security Headers ─────────────────────────────────────────
    app.use((_req, res, next) => {
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("X-Frame-Options", "DENY");
        res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
        next();
    });

    // ─── GET /api/status ─────────────────────────────────────────
    app.get(
        "/api/status",
        rateLimit(60_000, 60), // 60 طلب/دقيقة
        (req, res) => {
            const tickerArray = Array.from(scanStatus.tickerData.values());
            res.json({
                ...scanStatus,
                tickerData: tickerArray,
                activeTradesCount: Object.keys(activeTrades).length,
                activeTrades: Object.values(activeTrades),
                customAlerts: customAlerts.filter((a) => !a.triggered),
                // ✅ لا نُرجع TOKEN الكامل أبداً
                telegramConfigured: botStatus.isValid,
                telegramBotName: botStatus.username,
                botStatus: {
                    isValid: botStatus.isValid,
                    name: botStatus.name,
                    username: botStatus.username,
                    lastError: botStatus.lastError,
                },
            });
        }
    );

    // ─── POST /api/feedback ──────────────────────────────────────
    app.post(
        "/api/feedback",
        rateLimit(60_000, 10), // 10 طلبات/دقيقة
        async (req, res) => {
            const { name, email, message, type } = req.body;

            // ✅ Input validation
            if (!message || typeof message !== "string" || message.trim().length < 3) {
                return res.status(400).json({ error: "الرسالة مطلوبة (3 أحرف على الأقل)" });
            }
            const validTypes = ["تحسين", "خطأ", "ميزة", "أخرى"];
            if (!type || !validTypes.includes(type)) {
                return res.status(400).json({ error: "نوع الملاحظة غير صالح" });
            }
            if (message.length > 5000) {
                return res.status(400).json({ error: "الرسالة طويلة جداً (الحد 5000 حرف)" });
            }

            const feedbackData = {
                name: typeof name === "string" ? name.slice(0, 100) : undefined,
                email: typeof email === "string" ? email.slice(0, 200) : undefined,
                type,
                message: message.trim().slice(0, 5000),
            };

            // ✅ FIX: حفظ في Firestore أولاً (لا تضيع الملاحظات)
            await saveFeedbackToFirestore(feedbackData);

            // ثم إرسال لـ Telegram (اختياري — لا يوقف الـ response إن فشل)
            if (botStatus.isValid && CHAT_ID) {
                sendTelegramMsg(
                    `📝 *ملاحظة جديدة*\n\n` +
                        `👤 ${feedbackData.name || "مجهول"}\n` +
                        `📧 ${feedbackData.email || "—"}\n` +
                        `🏷️ ${type}\n\n` +
                        `💬 ${message}`
                ).catch((e) => console.warn("Telegram feedback:", e));
            }

            res.json({ success: true, message: "تم استلام ملاحظتك، شكراً!" });
        }
    );

    // ─── POST /api/alerts ────────────────────────────────────────
    app.post(
        "/api/alerts",
        rateLimit(60_000, 20),
        async (req, res) => {
            const { symbol, targetPrice, targetRsi } = req.body;

            // ✅ Input validation
            const validSymbol = validateSymbol(symbol);
            if (!validSymbol) {
                return res.status(400).json({
                    error: "رمز السهم غير صالح (مثال: 1120 أو 1120.SR)",
                });
            }

            // يجب أن يكون هناك هدف واحد على الأقل
            const validPrice =
                targetPrice !== undefined ? validatePrice(targetPrice) : undefined;
            const validRsi =
                targetRsi !== undefined ? validateRsi(targetRsi) : undefined;

            if (validPrice === null && targetPrice !== undefined) {
                return res.status(400).json({ error: "السعر المستهدف غير صالح" });
            }
            if (validRsi === null && targetRsi !== undefined) {
                return res.status(400).json({ error: "قيمة RSI غير صالحة (0-100)" });
            }
            if (validPrice === undefined && validRsi === undefined) {
                return res.status(400).json({
                    error: "يجب تحديد سعر مستهدف أو قيمة RSI مستهدفة",
                });
            }

            // حد أقصى للتنبيهات النشطة
            const activeCount = customAlerts.filter((a) => !a.triggered).length;
            if (activeCount >= MAX_ALERTS_PER_REQUEST) {
                return res.status(400).json({
                    error: `الحد الأقصى للتنبيهات النشطة هو ${MAX_ALERTS_PER_REQUEST}`,
                });
            }

            const newAlert: CustomAlert = {
                id: `alert_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
                symbol: validSymbol,
                targetPrice: validPrice,
                targetRsi: validRsi,
                triggered: false,
                createdAt: new Date().toISOString(),
            };

            // ✅ حفظ في Firestore
            newAlert.id = await saveAlertToFirestore(newAlert);
            customAlerts.push(newAlert);

            res.json({ success: true, alert: newAlert });
        }
    );

    // ─── POST /api/test-telegram ────────────────────────────────
    app.post(
        "/api/test-telegram",
        rateLimit(60_000, 5),
        async (req, res) => {
            try {
                await checkBot();
                if (!botStatus.isValid) {
                    throw new Error(botStatus.lastError || "فشل التحقق من البوت");
                }
                const result = await sendTelegramMsg(
                    `🔔 *رسالة تجريبية*\n\n` +
                        `✅ كل شيء يعمل بشكل مثالي!\n` +
                        `🤖 البوت: ${botStatus.name} (@${botStatus.username})\n` +
                        `⏰ ${new Date().toLocaleTimeString()}`
                );
                if (!result.success) throw new Error(result.error);
                res.json({
                    success: true,
                    message: `تم الإرسال عبر @${botStatus.username}`,
                });
            } catch (e: any) {
                res.status(500).json({ success: false, error: e.message });
            }
        }
    );

    // ─── POST /api/scan — محمي بـ Admin Auth ─────────────────────
    app.post(
        "/api/scan",
        rateLimit(600_000, 3), // 3 مرات كل 10 دقائق
        requireAdmin,
        async (_req, res) => {
            if (scanStatus.isScanning) {
                return res.status(400).json({ message: "جاري المسح بالفعل" });
            }
            startFullScan().catch((e) =>
                console.error("خطأ في المسح اليدوي:", e.message)
            );
            res.json({ success: true, message: "بدأ المسح اليدوي" });
        }
    );

    // ─── GET /api/history/:symbol ────────────────────────────────
    app.get(
        "/api/history/:symbol",
        rateLimit(60_000, 30),
        async (req, res) => {
            const rawSymbol = req.params.symbol;
            const symbol = validateSymbol(rawSymbol);
            if (!symbol) {
                return res.status(400).json({ error: "رمز السهم غير صالح" });
            }

            try {
                const period1 =
                    Math.floor(Date.now() / 1000) - 30 * 24 * 60 * 60;
                const result = await yahooFinance.chart(symbol, {
                    interval: "1h",
                    period1,
                }) as any;

                if (!result?.quotes?.length) {
                    return res.json({ success: false, error: "بيانات غير متوفرة" });
                }

                const quotes = (result.quotes as any[]).filter(
                    (q) => q.close !== null
                );
                const displayCount = 50;
                const startIndex = Math.max(0, quotes.length - displayCount);

                // ✅ حساب مؤشرات المخطط مرة واحدة بكفاءة
                const allCloses = quotes.map((q: any) => q.close as number);

                const history = quotes.slice(startIndex).map((q: any, i: number) => {
                    const actualIndex = startIndex + i;
                    const subCloses = allCloses.slice(0, actualIndex + 1);
                    const macd = calculateMACD(subCloses); // O(n) الآن
                    const bb = calculateBollingerBands(subCloses);

                    return {
                        time: new Date(q.date).toLocaleTimeString("ar-SA", {
                            hour: "2-digit",
                            minute: "2-digit",
                        }),
                        fullDate: q.date,
                        price: Number(q.close.toFixed(2)),
                        macd: macd.macd,
                        signal: macd.signal,
                        histogram: macd.histogram,
                        bbUpper: bb.upper,
                        bbMiddle: bb.middle,
                        bbLower: bb.lower,
                    };
                });

                res.json({ success: true, history });
            } catch (e: any) {
                console.error(`خطأ في تاريخ ${symbol}:`, e.message);
                res.status(500).json({ success: false, error: e.message });
            }
        }
    );

    // ─── GET /api/health ─────────────────────────────────────────
    app.get("/api/health", (_req, res) => {
        res.json({
            status: "ok",
            uptime: process.uptime(),
            adminConnected: adminInitialized && !!adminDb,
            telegramConnected: botStatus.isValid,
            lastScan: scanStatus.lastScan,
        });
    });

    // ─── Vite Middleware ──────────────────────────────────────────
    if (process.env.NODE_ENV !== "production") {
        const vite = await createViteServer({
            server: { middlewareMode: true },
            appType: "spa",
        });
        app.use(vite.middlewares);
    } else {
        const distPath = path.join(process.cwd(), "dist");
        app.use(express.static(distPath));
        app.get("*", (_req, res) => {
            res.sendFile(path.join(distPath, "index.html"));
        });
    }

    app.listen(PORT, "0.0.0.0", async () => {
        console.log(`\n🚀 Server: http://localhost:${PORT}\n`);

        // اختبار الاتصال بـ Yahoo Finance
        try {
            const testQuote = await yahooFinance.quote("1120.SR") as any;
            if (testQuote) {
                console.log(`✅ Yahoo Finance: الراجحي @ ${testQuote.regularMarketPrice}`);
            }
        } catch (e: any) {
            console.error("❌ Yahoo Finance test failed:", e.message);
        }

        // أول مسح بعد تأخير قصير
        setTimeout(() => {
            console.log("⚙️ بدء المسح الأول...");
            sendTelegramMsg("⚙️ *تم تشغيل الرادار!*\nجاري مسح السوق السعودي...");
            startFullScan().catch((e) =>
                console.error("خطأ في المسح الأول:", e.message)
            );
        }, 3000);

        // مسح دوري كل 10 دقائق
        setInterval(() => {
            startFullScan().catch((e) =>
                console.error("خطأ في المسح الدوري:", e.message)
            );
        }, 600_000);
    });
}

startServer();
