import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# =========================
# إعدادات Telegram
# =========================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8023582461")

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN غير موجود في إعدادات Render")


def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if response.ok:
            print("📨 تم إرسال الرسالة")
        else:
            print("❌ Telegram:", response.text)

    except Exception as e:
        print("❌ Telegram Error:", e)


# =========================
# إعدادات المراقب
# =========================

SYMBOL = "GC=F"

CHECK_SECONDS = 60

MIN_SCORE = 80

COOLDOWN_SECONDS = 30 * 60

last_signal = None
last_signal_time = 0


# =========================
# جلب البيانات
# =========================

def get_data():

    try:

        data = yf.download(
            SYMBOL,
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=False
        )

        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data.dropna()

    except Exception as e:

        print("❌ Data Error:", e)
        return None


# =========================
# المؤشرات
# =========================

def calculate_indicators(df):

    df = df.copy()

    # المتوسطات
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

    # RSI
    delta = df["Close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["RSI"] = 100 - (100 / (1 + rs))

    # ATR
    tr1 = df["High"] - df["Low"]
    tr2 = abs(df["High"] - df["Close"].shift())
    tr3 = abs(df["Low"] - df["Close"].shift())

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()

    # الحجم
    df["VolumeMA"] = df["Volume"].rolling(20).mean()

    df["VolumeRatio"] = (
        df["Volume"] /
        df["VolumeMA"].replace(0, np.nan)
    )

    return df.dropna()


# =========================
# تحليل الاتجاه
# =========================

def analyze(df):

    last = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(last["Close"])

    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])

    rsi = float(last["RSI"])

    volume_ratio = float(last["VolumeRatio"])

    buy_score = 0
    sell_score = 0

    buy_reasons = []
    sell_reasons = []

    # الاتجاه الرئيسي
    if ema20 > ema50:
        buy_score += 25
        buy_reasons.append("الاتجاه صاعد")

    elif ema20 < ema50:
        sell_score += 25
        sell_reasons.append("الاتجاه هابط")

    # السعر مقابل EMA20
    if price > ema20:
        buy_score += 15
        buy_reasons.append("السعر فوق EMA20")

    elif price < ema20:
        sell_score += 15
        sell_reasons.append("السعر تحت EMA20")

    # RSI
    if 52 <= rsi <= 68:
        buy_score += 20
        buy_reasons.append("الزخم صاعد")

    elif 32 <= rsi <= 48:
        sell_score += 20
        sell_reasons.append("الزخم هابط")

    # الحجم
    if volume_ratio >= 1.30:

        if price > float(previous["Close"]):
            buy_score += 20
            buy_reasons.append("حجم مرتفع مع صعود")

        elif price < float(previous["Close"]):
            sell_score += 20
            sell_reasons.append("حجم مرتفع مع هبوط")

    # التسارع
    change = (
        (price - float(previous["Close"]))
        / float(previous["Close"])
    ) * 100

    if change > 0.05:
        buy_score += 10
        buy_reasons.append("تسارع إيجابي")

    elif change < -0.05:
        sell_score += 10
        sell_reasons.append("تسارع سلبي")

    # القرار النهائي
    if buy_score >= MIN_SCORE and buy_score > sell_score:

        return "BUY", buy_score, price, rsi, volume_ratio, buy_reasons

    if sell_score >= MIN_SCORE and sell_score > buy_score:

        return "SELL", sell_score, price, rsi, volume_ratio, sell_reasons

    return "WAIT", max(buy_score, sell_score), price, rsi, volume_ratio, []


# =========================
# المراقب الرئيسي
# =========================

def main():

    global last_signal
    global last_signal_time

    print("😈 Devil Gold Monitor بدأ العمل")

    send_telegram(
        "😈🔥 Devil Gold Monitor بدأ العمل\n\n"
        "📊 مراقبة الذهب مفعلة\n"
        "🎯 الحد الأدنى للإشارة: 80/100\n"
        "⏳ فاصل الإشارات: 30 دقيقة\n\n"
        "⚠️ تنبيهات تحليلية فقط."
    )

    while True:

        try:

            df = get_data()

            if df is None:

                print("⚠️ لا توجد بيانات، إعادة المحاولة...")
                time.sleep(CHECK_SECONDS)
                continue

            df = calculate_indicators(df)

            signal, score, price, rsi, volume, reasons = analyze(df)

            print(
                f"💰 {price:.2f} | "
                f"{signal} | "
                f"Score: {score}/100 | "
                f"RSI: {rsi:.1f} | "
                f"Volume: {volume:.2f}x"
            )

            now = time.time()

            cooldown_ok = (
                now - last_signal_time >= COOLDOWN_SECONDS
            )

            if (
                signal in ("BUY", "SELL")
                and score >= MIN_SCORE
                and signal != last_signal
                and cooldown_ok
            ):

                emoji = "🟢" if signal == "BUY" else "🔴"

                reason_text = "\n".join(
                    "• " + reason
                    for reason in reasons
                )

                message = (
                    f"😈🔥 DEVIL GOLD SIGNAL\n\n"
                    f"{emoji} {signal}\n"
                    f"💰 الذهب: {price:.2f}\n"
                    f"📊 القوة: {score}/100\n"
                    f"📈 RSI: {rsi:.1f}\n"
                    f"💧 الحجم: {volume:.2f}x\n\n"
                    f"الأسباب:\n"
                    f"{reason_text}\n\n"
                    f"⚠️ إشارة تحليلية وليست ضمانًا."
                )

                send_telegram(message)

                last_signal = signal
                last_signal_time = now

            time.sleep(CHECK_SECONDS)

        except Exception as e:

            print("❌ خطأ:", e)
            time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
