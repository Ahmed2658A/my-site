import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# =========================================================
# MONEY CASH EGY 🇪🇬💰
# نسخة كاملة جاهزة للتشغيل
#
# قبل التشغيل: ضع Bot Token مكان النص الموجود تحت فقط.
# لا ترسل التوكن لأي شخص.
# =========================================================

BOT_TOKEN = "8690388621:AAH-gqdWyVeb73yK1KFsXxxCRs2u8z_ukRY"

CHANNEL_LINK = "https://t.me/+K2aqGn-bEpY2Y2E0"
SUPPORT_USERNAME = "@X2cash1"

DB_FILE = "money_cash_egy.db"

# القيم الافتراضية
DEFAULT_REFERRAL_REQUIRED = 3
DEFAULT_REFERRAL_REWARD = 1
DEFAULT_DAILY_GIFT = 2
DEFAULT_MIN_WITHDRAWAL = 10

WALLETS = [
    "Vodafone Cash",
    "Orange Cash",
    "Etisalat Cash",
    "WE Pay"
]


# =========================================================
# قاعدة البيانات
# =========================================================

def connect():
    return sqlite3.connect(DB_FILE, timeout=30)


def init_db():
    con = connect()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            total_earnings REAL DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referral_earnings REAL DEFAULT 0,
            gift_earnings REAL DEFAULT 0,
            total_withdrawals REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            invited_id INTEGER UNIQUE NOT NULL,
            reward_added REAL DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_gifts (
            user_id INTEGER PRIMARY KEY,
            last_claim TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            wallet_type TEXT NOT NULL,
            wallet_number TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            request_date TEXT,
            request_time TEXT,
            processed_date TEXT,
            processed_time TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    settings = {
        "referral_required": DEFAULT_REFERRAL_REQUIRED,
        "referral_reward": DEFAULT_REFERRAL_REWARD,
        "daily_gift": DEFAULT_DAILY_GIFT,
        "min_withdrawal": DEFAULT_MIN_WITHDRAWAL,
    }

    for key, value in settings.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, str(value))
        )

    # يحتفظ البوت برقم القناة بعد أن تصله channel_post
    cur.execute(
        "INSERT OR IGNORE INTO bot_config(key,value) VALUES('channel_id','')"
    )

    # الأدمن يتم تعيينه بأول استخدام لـ /claimadmin
    cur.execute(
        "INSERT OR IGNORE INTO bot_config(key,value) VALUES('admin_id','0')"
    )

    con.commit()
    con.close()


def setting(key, default):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else str(default)


def set_setting(key, value):
    con = connect()
    con.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (key, str(value))
    )
    con.commit()
    con.close()


def config(key, default=""):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT value FROM bot_config WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else default


def set_config(key, value):
    con = connect()
    con.execute(
        "INSERT OR REPLACE INTO bot_config(key,value) VALUES(?,?)",
        (key, str(value))
    )
    con.commit()
    con.close()


def admin_id():
    try:
        return int(config("admin_id", "0"))
    except Exception:
        return 0


def is_admin(user_id):
    return user_id == admin_id() and user_id != 0


def money(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def get_user(user_id):
    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT id,username,first_name,balance,total_earnings,
               referral_count,referral_earnings,gift_earnings,
               total_withdrawals,is_banned,created_at
        FROM users WHERE id=?
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    return row


def save_user(tg_user):
    con = connect()
    cur = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("SELECT id FROM users WHERE id=?", (tg_user.id,))
    if cur.fetchone() is None:
        cur.execute("""
            INSERT INTO users
            (id,username,first_name,created_at)
            VALUES(?,?,?,?)
        """, (
            tg_user.id,
            tg_user.username or "",
            tg_user.first_name or "",
            now
        ))
    else:
        cur.execute("""
            UPDATE users
            SET username=?, first_name=?
            WHERE id=?
        """, (
            tg_user.username or "",
            tg_user.first_name or "",
            tg_user.id
        ))

    con.commit()
    con.close()


# =========================================================
# القناة والاشتراك
# =========================================================

async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حفظ الـ ID الحقيقي للقناة تلقائيًا من أي منشور يصل للبوت.
    post = update.channel_post
    if post and post.chat:
        set_config("channel_id", str(post.chat.id))
        set_config("channel_title", post.chat.title or "")


async def is_member(context, user_id):
    channel_id = config("channel_id", "")

    # لا تسمح بالدخول إذا لم يتعرف البوت على القناة بعد.
    if not channel_id:
        return False

    # إعادة المحاولة لتجنب أخطاء Telegram المؤقتة بعد الاشتراك مباشرة.
    for _ in range(2):
        try:
            member = await context.bot.get_chat_member(
                chat_id=int(channel_id),
                user_id=user_id
            )

            status = member.status

            # عضو عادي / أدمن / مالك القناة.
            if status in ("member", "administrator", "creator"):
                return True

            # Telegram قد يرجع restricted للمشترك الذي ما زال عضوًا.
            if status == "restricted" and getattr(member, "is_member", False):
                return True

            # left / kicked / أي حالة أخرى = غير مشترك.
            return False

        except Exception as e:
            print("SUBSCRIPTION CHECK ERROR:", repr(e))
            # محاولة ثانية فقط للأخطاء المؤقتة.
            await asyncio.sleep(0.8)

    return False


def subscribe_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=CHANNEL_LINK)],
        [InlineKeyboardButton(
            "✅ تحققت من الاشتراك",
            callback_data="check_subscription"
        )]
    ])


async def require_subscription(update, context):
    text = (
        "🇪🇬 MONEY CASH EGY 💰\n\n"
        "⚠️ لازم تشترك في القناة أولًا.\n\n"
        "بعد الاشتراك اضغط «تحققت من الاشتراك»."
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text, reply_markup=subscribe_keyboard()
        )
    else:
        await update.message.reply_text(
            text, reply_markup=subscribe_keyboard()
        )


# =========================================================
# القوائم
# =========================================================

def home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 دعوة الأصدقاء", callback_data="referrals"),
            InlineKeyboardButton("💰 رصيدي", callback_data="balance")
        ],
        [
            InlineKeyboardButton("📊 إحصائياتي", callback_data="stats"),
            InlineKeyboardButton("💸 سحب الأرباح", callback_data="withdraw")
        ],
        [
            InlineKeyboardButton("🎁 الهدية اليومية", callback_data="gift")
        ],
        [
            InlineKeyboardButton("📜 الشروط", callback_data="terms"),
            InlineKeyboardButton("🆘 خدمة العملاء",
                                 url="https://t.me/X2cash1")
        ]
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data="home")]
    ])


async def show_home(update, context):
    user = update.effective_user
    save_user(user)
    row = get_user(user.id)

    text = (
        "🇪🇬 MONEY CASH EGY 💰\n\n"
        f"👋 أهلاً بيك يا {user.first_name}\n\n"
        f"💰 رصيدك: {money(row[3])} جنيه\n"
        f"👥 دعواتك الناجحة: {row[5]}\n"
        "⭐ مستواك: 1\n\n"
        "🎁 ادعُ أصحابك واكسب مكافآت مالية\n"
        "🚀 كل ما تزود دعواتك، تزود أرباحك\n\n"
        "👇 اختار من القائمة:"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text, reply_markup=home_keyboard()
        )
    else:
        await update.message.reply_text(
            text, reply_markup=home_keyboard()
        )


# =========================================================
# الإحالات
# =========================================================

def referral_exists(invited_id):
    con = connect()
    cur = con.cursor()
    cur.execute(
        "SELECT id FROM referrals WHERE invited_id=?",
        (invited_id,)
    )
    result = cur.fetchone()
    con.close()
    return result is not None


def add_referral(inviter_id, invited_id):
    if inviter_id == invited_id:
        return False, False

    if get_user(inviter_id) is None:
        return False, False

    if referral_exists(invited_id):
        return False, False

    con = connect()
    cur = con.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO referrals(inviter_id,invited_id,reward_added,created_at)
        VALUES(?,?,0,?)
    """, (inviter_id, invited_id, now))

    cur.execute("""
        UPDATE users
        SET referral_count=referral_count+1
        WHERE id=?
    """, (inviter_id,))

    cur.execute(
        "SELECT referral_count FROM users WHERE id=?",
        (inviter_id,)
    )
    count = cur.fetchone()[0]

    required = int(float(setting(
        "referral_required", DEFAULT_REFERRAL_REQUIRED
    )))
    reward = float(setting(
        "referral_reward", DEFAULT_REFERRAL_REWARD
    ))

    paid = False

    if required > 0 and count % required == 0:
        cur.execute("""
            UPDATE users
            SET balance=balance+?,
                total_earnings=total_earnings+?,
                referral_earnings=referral_earnings+?
            WHERE id=?
        """, (reward, reward, reward, inviter_id))

        cur.execute("""
            UPDATE referrals
            SET reward_added=?
            WHERE invited_id=?
        """, (reward, invited_id))
        paid = True

    con.commit()
    con.close()
    return True, paid


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    row = get_user(user.id)
    if row and row[9] == 1:
        await update.message.reply_text("🚫 حسابك موقوف.")
        return

    if not await is_member(context, user.id):
        await require_subscription(update, context)
        return

    # رابط الإحالة
    if context.args:
        try:
            inviter_id = int(context.args[0])
            added, paid = add_referral(inviter_id, user.id)

            if added:
                inviter = get_user(inviter_id)
                if inviter:
                    try:
                        if paid:
                            await context.bot.send_message(
                                inviter_id,
                                "🎉 مبروك!\n\n"
                                f"اكتملت {setting('referral_required', 3)} دعوات "
                                f"وحصلت على {money(setting('referral_reward', 1))} جنيه 💰"
                            )
                        else:
                            required = int(float(setting(
                                "referral_required", 3
                            )))
                            remaining = required - (
                                inviter[5] + 1
                            ) % required
                            if remaining == required:
                                remaining = 0
                            await context.bot.send_message(
                                inviter_id,
                                f"👥 تم احتساب دعوة جديدة!\n"
                                f"🎯 الدعوات: {inviter[5] + 1}\n"
                                f"💰 كل {required} دعوات = "
                                f"{money(setting('referral_reward', 1))} جنيه"
                            )
                    except Exception:
                        pass

        except (ValueError, TypeError):
            pass

    await show_home(update, context)


# =========================================================
# الرصيد والإحصائيات
# =========================================================

async def show_balance(update, context):
    q = update.callback_query
    row = get_user(q.from_user.id)

    text = (
        "💰 رصيدك\n\n"
        f"💵 الرصيد الحالي: {money(row[3])} جنيه\n"
        f"📈 إجمالي الأرباح: {money(row[4])} جنيه\n"
        f"💸 إجمالي المسحوبات: {money(row[8])} جنيه"
    )
    await q.message.edit_text(text, reply_markup=back_keyboard())


async def show_stats(update, context):
    q = update.callback_query
    row = get_user(q.from_user.id)

    text = (
        "📊 إحصائياتك\n\n"
        f"👥 الدعوات الناجحة: {row[5]}\n"
        f"💰 أرباح الدعوات: {money(row[6])} جنيه\n"
        f"🎁 أرباح الهدايا: {money(row[7])} جنيه\n"
        f"💵 إجمالي الأرباح: {money(row[4])} جنيه\n"
        f"💸 إجمالي المسحوبات: {money(row[8])} جنيه\n"
        f"💰 الرصيد الحالي: {money(row[3])} جنيه"
    )
    await q.message.edit_text(text, reply_markup=back_keyboard())


# =========================================================
# رابط الدعوة
# =========================================================

async def show_referrals(update, context):
    q = update.callback_query
    row = get_user(q.from_user.id)

    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={q.from_user.id}"

    required = setting("referral_required", DEFAULT_REFERRAL_REQUIRED)
    reward = setting("referral_reward", DEFAULT_REFERRAL_REWARD)

    share = (
        "https://t.me/share/url?url="
        + link
        + "&text="
        + "🎁 انضم إلى MONEY CASH EGY واربح من دعوة أصدقائك!"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 مشاركة الرابط", url=share)],
        [InlineKeyboardButton("🔙 رجوع", callback_data="home")]
    ])

    text = (
        "👥 دعوة الأصدقاء\n\n"
        "💰 اكسب فلوس من دعوة أصحابك!\n\n"
        f"🎯 كل {required} دعوات ناجحة = {reward} جنيه\n\n"
        "🔗 رابط دعوتك الخاص:\n"
        f"{link}\n\n"
        f"👥 دعواتك الناجحة: {row[5]}\n"
        f"💰 أرباحك من الدعوات: {money(row[6])} جنيه\n\n"
        "📢 ابعت رابطك لأصحابك وابدأ اكسب!"
    )

    await q.message.edit_text(text, reply_markup=keyboard)


# =========================================================
# الهدية اليومية
# =========================================================

async def daily_gift(update, context):
    q = update.callback_query
    user_id = q.from_user.id

    con = connect()
    cur = con.cursor()
    cur.execute(
        "SELECT last_claim FROM daily_gifts WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()

    now = datetime.now()

    if row:
        try:
            last = datetime.strptime(
                row[0], "%Y-%m-%d %H:%M:%S"
            )
            next_claim = last + timedelta(hours=24)

            if now < next_claim:
                remaining = next_claim - now
                total_minutes = int(remaining.total_seconds() // 60)
                hours = total_minutes // 60
                minutes = total_minutes % 60

                con.close()
                await q.answer(
                    f"⏳ الهدية متاحة بعد {hours} ساعة و{minutes} دقيقة",
                    show_alert=True
                )
                return
        except Exception:
            pass

    gift = float(setting("daily_gift", DEFAULT_DAILY_GIFT))

    cur.execute("""
        INSERT OR REPLACE INTO daily_gifts(user_id,last_claim)
        VALUES(?,?)
    """, (user_id, now.strftime("%Y-%m-%d %H:%M:%S")))

    cur.execute("""
        UPDATE users
        SET balance=balance+?,
            total_earnings=total_earnings+?,
            gift_earnings=gift_earnings+?
        WHERE id=?
    """, (gift, gift, gift, user_id))

    con.commit()
    con.close()

    await q.answer(
        f"🎁 مبروك! حصلت على {money(gift)} جنيه",
        show_alert=True
    )
    await show_home(update, context)


# =========================================================
# الشروط
# =========================================================

async def show_terms(update, context):
    q = update.callback_query

    text = (
        "📜 شروط MONEY CASH EGY\n\n"
        "1️⃣ كل مستخدم يتم احتسابه مرة واحدة فقط.\n"
        "2️⃣ ممنوع دعوة نفسك.\n"
        "3️⃣ كل 3 دعوات ناجحة = 1 جنيه.\n"
        "4️⃣ الهدية اليومية 2 جنيه كل 24 ساعة.\n"
        "5️⃣ الحد الأدنى للسحب 10 جنيه.\n"
        "6️⃣ طلبات السحب تتم مراجعتها يدويًا.\n"
        "7️⃣ يمنع التحايل أو إنشاء حسابات وهمية.\n"
        "8️⃣ أي مخالفة للشروط قد تؤدي إلى إيقاف الحساب."
    )
    await q.message.edit_text(text, reply_markup=back_keyboard())


# =========================================================
# السحب
# =========================================================

async def start_withdraw(update, context):
    q = update.callback_query
    row = get_user(q.from_user.id)

    minimum = float(setting(
        "min_withdrawal", DEFAULT_MIN_WITHDRAWAL
    ))

    if row[3] < minimum:
        await q.answer(
            f"❌ الحد الأدنى للسحب {money(minimum)} جنيه",
            show_alert=True
        )
        return

    keyboard = [
        [InlineKeyboardButton(w, callback_data=f"wallet|{w}")]
        for w in WALLETS
    ]
    keyboard.append(
        [InlineKeyboardButton("🔙 رجوع", callback_data="home")]
    )

    context.user_data.clear()
    context.user_data["withdraw_step"] = "wallet"

    await q.message.edit_text(
        f"💸 سحب الأرباح\n\n"
        f"💰 رصيدك: {money(row[3])} جنيه\n"
        f"📌 الحد الأدنى: {money(minimum)} جنيه\n\n"
        "اختار نوع المحفظة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def process_text(update, context):
    user = update.effective_user
    save_user(user)

    row = get_user(user.id)
    if row[9] == 1:
        await update.message.reply_text("🚫 حسابك موقوف.")
        return

    step = context.user_data.get("withdraw_step")

    if step == "amount":
        try:
            amount = float(update.message.text.strip().replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ اكتب مبلغ صحيح.")
            return

        minimum = float(setting(
            "min_withdrawal", DEFAULT_MIN_WITHDRAWAL
        ))

        if amount < minimum:
            await update.message.reply_text(
                f"❌ الحد الأدنى للسحب {money(minimum)} جنيه."
            )
            return

        if amount > row[3]:
            await update.message.reply_text("❌ رصيدك غير كافي.")
            return

        context.user_data["amount"] = amount
        context.user_data["withdraw_step"] = "number"

        await update.message.reply_text(
            "📱 اكتب رقم المحفظة الآن:"
        )
        return

    if step == "number":
        number = update.message.text.strip()

        if not number.isdigit() or len(number) < 10 or len(number) > 15:
            await update.message.reply_text(
                "❌ رقم المحفظة غير صحيح."
            )
            return

        amount = float(context.user_data["amount"])
        wallet = context.user_data["wallet"]

        con = connect()
        cur = con.cursor()
        now = datetime.now()

        # خصم الرصيد فقط لحظة إنشاء الطلب
        cur.execute("""
            UPDATE users
            SET balance=balance-?
            WHERE id=? AND balance>=?
        """, (amount, user.id, amount))

        if cur.rowcount != 1:
            con.close()
            context.user_data.clear()
            await update.message.reply_text("❌ الرصيد غير كافي.")
            return

        cur.execute("""
            INSERT INTO withdrawals
            (user_id,amount,wallet_type,wallet_number,status,
             request_date,request_time)
            VALUES(?,?,?,?,?,?,?)
        """, (
            user.id,
            amount,
            wallet,
            number,
            "pending",
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S")
        ))

        request_id = cur.lastrowid
        con.commit()
        con.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم إرسال طلب السحب بنجاح.\n\n"
            f"🆔 رقم الطلب: #{request_id}\n"
            f"💰 المبلغ: {money(amount)} جنيه\n"
            f"💳 المحفظة: {wallet}\n"
            f"📱 الرقم: {number}\n"
            f"📅 التاريخ: {now.strftime('%d/%m/%Y')}\n"
            f"⏰ الوقت: {now.strftime('%H:%M:%S')}\n\n"
            "⏳ طلبك قيد المراجعة."
        )

        aid = admin_id()
        if aid:
            try:
                await context.bot.send_message(
                    aid,
                    "💸 طلب سحب جديد\n\n"
                    f"🆔 الطلب: #{request_id}\n"
                    f"👤 المستخدم: @{user.username or 'بدون username'}\n"
                    f"🆔 ID: {user.id}\n"
                    f"💰 المبلغ: {money(amount)} جنيه\n"
                    f"💳 المحفظة: {wallet}\n"
                    f"📱 الرقم: {number}\n"
                    f"📅 التاريخ: {now.strftime('%d/%m/%Y')}\n"
                    f"⏰ الوقت: {now.strftime('%H:%M:%S')}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "✅ قبول الطلب",
                            callback_data=f"admin_accept|{request_id}"
                        ),
                        InlineKeyboardButton(
                            "❌ رفض الطلب",
                            callback_data=f"admin_reject|{request_id}"
                        )
                    ]])
                )
            except Exception:
                pass
        return

    await update.message.reply_text(
        "استخدم أزرار البوت لاختيار الخدمة المطلوبة."
    )


# =========================================================
# الأدمن
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"),
            InlineKeyboardButton("💸 طلبات السحب", callback_data="admin_withdrawals")
        ],
        [
            InlineKeyboardButton("👥 إدارة مستخدم", callback_data="admin_user"),
            InlineKeyboardButton("🎁 إعدادات المكافآت", callback_data="admin_rewards")
        ]
    ])


async def claim_admin(update, context):
    user = update.effective_user
    current = admin_id()

    if current != 0:
        if current == user.id:
            await update.message.reply_text(
                "👑 أنت الأدمن بالفعل.\n\n"
                "استخدم /admin لفتح لوحة التحكم."
            )
        else:
            await update.message.reply_text("❌ الأدمن تم تعيينه بالفعل.")
        return

    set_config("admin_id", str(user.id))

    await update.message.reply_text(
        "👑 تم تعيين حسابك كأدمن بنجاح.\n\n"
        "⚠️ لا ترسل الأمر /claimadmin لأي شخص.\n\n"
        "استخدم /admin لفتح لوحة التحكم."
    )


async def admin_command(update, context):
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    await update.message.reply_text(
        "👑 لوحة تحكم MONEY CASH EGY",
        reply_markup=admin_keyboard()
    )


async def admin_stats(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ غير مصرح لك.", show_alert=True)
        return

    con = connect()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM referrals")
    referrals = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(total_earnings),0) FROM users")
    earnings = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(total_withdrawals),0) FROM users"
    )
    withdrawals = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM withdrawals WHERE status='pending'"
    )
    pending = cur.fetchone()[0]

    con.close()

    text = (
        "📊 إحصائيات البوت\n\n"
        f"👥 إجمالي المستخدمين: {users}\n"
        f"👥 إجمالي الدعوات: {referrals}\n"
        f"💰 إجمالي المكافآت: {money(earnings)} جنيه\n"
        f"💸 إجمالي المسحوبات المقبولة: {money(withdrawals)} جنيه\n"
        f"⏳ طلبات قيد المراجعة: {pending}"
    )

    await q.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 لوحة الأدمن", callback_data="admin_home")
        ]])
    )


async def admin_withdrawals(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ غير مصرح لك.", show_alert=True)
        return

    con = connect()
    cur = con.cursor()
    cur.execute("""
        SELECT id,user_id,amount,wallet_type,wallet_number,
               request_date,request_time
        FROM withdrawals
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    con.close()

    if not rows:
        await q.message.edit_text(
            "💸 لا توجد طلبات سحب قيد المراجعة.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔙 لوحة الأدمن", callback_data="admin_home"
                )
            ]])
        )
        return

    for row in rows:
        rid, uid, amount, wallet, number, date, tm = row

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ قبول",
                callback_data=f"admin_accept|{rid}"
            ),
            InlineKeyboardButton(
                "❌ رفض",
                callback_data=f"admin_reject|{rid}"
            )
        ]])

        await context.bot.send_message(
            q.from_user.id,
            "💸 طلب سحب\n\n"
            f"🆔 الطلب: #{rid}\n"
            f"🆔 المستخدم: {uid}\n"
            f"💰 المبلغ: {money(amount)} جنيه\n"
            f"💳 المحفظة: {wallet}\n"
            f"📱 الرقم: {number}\n"
            f"📅 التاريخ: {date}\n"
            f"⏰ الوقت: {tm}",
            reply_markup=keyboard
        )

    await q.message.edit_text(
        "💸 تم عرض طلبات السحب الجديدة.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔙 لوحة الأدمن", callback_data="admin_home"
            )
        ]])
    )


async def admin_rewards(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ غير مصرح لك.", show_alert=True)
        return

    text = (
        "🎁 إعدادات المكافآت الحالية\n\n"
        f"👥 عدد الدعوات المطلوبة: {setting('referral_required', 3)}\n"
        f"💰 مكافأة الدعوات: {setting('referral_reward', 1)} جنيه\n"
        f"🎁 الهدية اليومية: {setting('daily_gift', 2)} جنيه\n"
        f"💸 الحد الأدنى للسحب: {setting('min_withdrawal', 10)} جنيه\n\n"
        "لتعديلها استخدم الأوامر:\n"
        "/setreferrals 3\n"
        "/setreferralreward 1\n"
        "/setgift 2\n"
        "/setminwithdraw 10"
    )

    await q.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔙 لوحة الأدمن", callback_data="admin_home"
            )
        ]])
    )


async def admin_user(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ غير مصرح لك.", show_alert=True)
        return

    await q.message.edit_text(
        "👥 إدارة مستخدم\n\n"
        "استخدم:\n"
        "/user ID\n"
        "/addbalance ID AMOUNT\n"
        "/ban ID\n"
        "/unban ID",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔙 لوحة الأدمن", callback_data="admin_home"
            )
        ]])
    )


async def process_admin_withdraw(update, context, request_id, accepted):
    q = update.callback_query

    if not is_admin(q.from_user.id):
        await q.answer("❌ غير مصرح لك.", show_alert=True)
        return

    con = connect()
    cur = con.cursor()

    cur.execute("""
        SELECT user_id,amount,status
        FROM withdrawals
        WHERE id=?
    """, (request_id,))
    row = cur.fetchone()

    if not row:
        con.close()
        await q.answer("❌ الطلب غير موجود.", show_alert=True)
        return

    user_id, amount, status = row

    if status != "pending":
        con.close()
        await q.answer("⚠️ تم التعامل مع الطلب من قبل.", show_alert=True)
        return

    now = datetime.now()
    new_status = "accepted" if accepted else "rejected"

    cur.execute("""
        UPDATE withdrawals
        SET status=?,processed_date=?,processed_time=?
        WHERE id=?
    """, (
        new_status,
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        request_id
    ))

    if accepted:
        cur.execute("""
            UPDATE users
            SET total_withdrawals=total_withdrawals+?
            WHERE id=?
        """, (amount, user_id))
    else:
        # عند الرفض يرجع المبلغ للرصيد
        cur.execute("""
            UPDATE users
            SET balance=balance+?
            WHERE id=?
        """, (amount, user_id))

    con.commit()
    con.close()

    if accepted:
        user_text = (
            "✅ تم قبول طلب السحب الخاص بك بنجاح.\n\n"
            f"💰 المبلغ: {money(amount)} جنيه\n\n"
            "💳 سيتم تحويل المبلغ إلى محفظتك خلال\n"
            "⏰ 10 إلى 30 دقيقة.\n\n"
            "📩 شكرًا لاستخدامك MONEY CASH EGY 🇪🇬💰"
        )
        admin_text = (
            f"🟢 تم قبول الطلب #{request_id}\n\n"
            f"💰 المبلغ: {money(amount)} جنيه\n"
            f"⏰ وقت المعالجة: {now.strftime('%d/%m/%Y %H:%M:%S')}"
        )
    else:
        user_text = (
            "❌ تم رفض طلب السحب.\n\n"
            f"💰 المبلغ: {money(amount)} جنيه\n\n"
            "💰 تم إعادة المبلغ إلى رصيدك.\n\n"
            "📩 للتواصل مع خدمة العملاء:\n"
            f"{SUPPORT_USERNAME}"
        )
        admin_text = (
            f"🔴 تم رفض الطلب #{request_id}\n\n"
            f"💰 المبلغ: {money(amount)} جنيه\n"
            f"⏰ وقت المعالجة: {now.strftime('%d/%m/%Y %H:%M:%S')}"
        )

    try:
        await context.bot.send_message(user_id, user_text)
    except Exception:
        pass

    await q.edit_message_text(admin_text)


# =========================================================
# أوامر الأدمن لتعديل الإعدادات
# =========================================================

async def set_number_setting(update, context, key, label):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    if not context.args:
        await update.message.reply_text(
            f"الاستخدام الصحيح: /{update.message.text.split()[0][1:]} رقم"
        )
        return

    try:
        value = float(context.args[0])
        if value < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ اكتب رقم صحيح.")
        return

    if key == "referral_required":
        if value < 1 or value != int(value):
            await update.message.reply_text(
                "❌ عدد الدعوات يجب أن يكون رقمًا صحيحًا أكبر من صفر."
            )
            return
        value = int(value)

    set_setting(key, value)

    await update.message.reply_text(
        f"✅ تم تعديل {label} إلى {money(value)}"
    )


async def cmd_setreferrals(update, context):
    await set_number_setting(
        update, context, "referral_required", "عدد الدعوات المطلوبة"
    )


async def cmd_setreferralreward(update, context):
    await set_number_setting(
        update, context, "referral_reward", "مكافأة الدعوات"
    )


async def cmd_setgift(update, context):
    await set_number_setting(
        update, context, "daily_gift", "الهدية اليومية"
    )


async def cmd_setminwithdraw(update, context):
    await set_number_setting(
        update, context, "min_withdrawal", "الحد الأدنى للسحب"
    )


async def cmd_addbalance(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "الاستخدام:\n/addbalance USER_ID AMOUNT"
        )
        return

    try:
        uid = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ بيانات غير صحيحة.")
        return

    if amount <= 0:
        await update.message.reply_text("❌ المبلغ يجب أن يكون أكبر من صفر.")
        return

    con = connect()
    cur = con.cursor()

    cur.execute("""
        UPDATE users
        SET balance=balance+?, total_earnings=total_earnings+?
        WHERE id=?
    """, (amount, amount, uid))

    changed = cur.rowcount
    con.commit()
    con.close()

    if changed:
        await update.message.reply_text(
            f"✅ تم إضافة {money(amount)} جنيه للمستخدم {uid}."
        )
    else:
        await update.message.reply_text("❌ المستخدم غير موجود.")


async def cmd_ban(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("الاستخدام: /ban USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح.")
        return

    con = connect()
    cur = con.cursor()
    cur.execute(
        "UPDATE users SET is_banned=1 WHERE id=?",
        (uid,)
    )
    changed = cur.rowcount
    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ تم حظر المستخدم." if changed else "❌ المستخدم غير موجود."
    )


async def cmd_unban(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("الاستخدام: /unban USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح.")
        return

    con = connect()
    cur = con.cursor()
    cur.execute(
        "UPDATE users SET is_banned=0 WHERE id=?",
        (uid,)
    )
    changed = cur.rowcount
    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ تم إلغاء حظر المستخدم." if changed else "❌ المستخدم غير موجود."
    )


async def cmd_user(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("الاستخدام: /user USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح.")
        return

    row = get_user(uid)

    if not row:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return

    await update.message.reply_text(
        "👤 بيانات المستخدم\n\n"
        f"🆔 ID: {row[0]}\n"
        f"👤 الاسم: {row[2]}\n"
        f"🔗 username: @{row[1] or 'بدون'}\n"
        f"💰 الرصيد: {money(row[3])} جنيه\n"
        f"👥 الدعوات: {row[5]}\n"
        f"📈 إجمالي الأرباح: {money(row[4])} جنيه\n"
        f"🎁 أرباح الهدايا: {money(row[7])} جنيه\n"
        f"💸 المسحوبات: {money(row[8])} جنيه\n"
        f"🚫 موقوف: {'نعم' if row[9] else 'لا'}"
    )


# =========================================================
# Callback handler
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    # لا نضع answer في بداية كل callback حتى نتمكن من استخدام alert
    if data == "check_subscription":
        if await is_member(context, q.from_user.id):
            await q.answer("✅ تم التحقق من الاشتراك.")
            await show_home(update, context)
        else:
            await q.answer(
                "❌ لم يتم تأكيد الاشتراك. تأكد أنك اشتركت ثم اضغط الزر مرة أخرى.",
                show_alert=True
            )
        return

    if data == "home":
        await q.answer()
        await show_home(update, context)
        return

    if data == "balance":
        await q.answer()
        await show_balance(update, context)
        return

    if data == "stats":
        await q.answer()
        await show_stats(update, context)
        return

    if data == "referrals":
        await q.answer()
        await show_referrals(update, context)
        return

    if data == "gift":
        await daily_gift(update, context)
        return

    if data == "terms":
        await q.answer()
        await show_terms(update, context)
        return

    if data == "withdraw":
        await q.answer()
        await start_withdraw(update, context)
        return

    if data.startswith("wallet|"):
        await q.answer()
        wallet = data.split("|", 1)[1]
        context.user_data["wallet"] = wallet
        context.user_data["withdraw_step"] = "amount"

        await q.message.edit_text(
            f"💳 المحفظة: {wallet}\n\n"
            "💰 اكتب مبلغ السحب:"
        )
        return

    if data == "admin_home":
        await q.answer()
        if not is_admin(q.from_user.id):
            await q.answer("❌ غير مصرح لك.", show_alert=True)
            return
        await q.message.edit_text(
            "👑 لوحة تحكم MONEY CASH EGY",
            reply_markup=admin_keyboard()
        )
        return

    if data == "admin_stats":
        await q.answer()
        await admin_stats(update, context)
        return

    if data == "admin_withdrawals":
        await q.answer()
        await admin_withdrawals(update, context)
        return

    if data == "admin_user":
        await q.answer()
        await admin_user(update, context)
        return

    if data == "admin_rewards":
        await q.answer()
        await admin_rewards(update, context)
        return

    if data.startswith("admin_accept|"):
        await q.answer()
        await process_admin_withdraw(
            update, context,
            data.split("|", 1)[1],
            True
        )
        return

    if data.startswith("admin_reject|"):
        await q.answer()
        await process_admin_withdraw(
            update, context,
            data.split("|", 1)[1],
            False
        )
        return

    await q.answer()


# =========================================================
# التشغيل
# =========================================================

async def error_handler(update, context):
    print("ERROR:", context.error)


def main():
    init_db()

    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("ERROR: Bot Token غير موجود داخل BOT_TOKEN")
        return

    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        print("ERROR: فشل إنشاء البوت:", repr(e))
        raise

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("claimadmin", claim_admin))
    application.add_handler(CommandHandler("admin", admin_command))

    application.add_handler(CommandHandler(
        "setreferrals", cmd_setreferrals
    ))
    application.add_handler(CommandHandler(
        "setreferralreward", cmd_setreferralreward
    ))
    application.add_handler(CommandHandler("setgift", cmd_setgift))
    application.add_handler(CommandHandler(
        "setminwithdraw", cmd_setminwithdraw
    ))

    application.add_handler(CommandHandler(
        "addbalance", cmd_addbalance
    ))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("unban", cmd_unban))
    application.add_handler(CommandHandler("user", cmd_user))

    application.add_handler(
        CallbackQueryHandler(callbacks)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            process_text
        )
    )

    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            channel_post
        )
    )

    application.add_error_handler(error_handler)

    print("========================================")
    print("MONEY CASH EGY 🇪🇬💰")
    print("BOT IS RUNNING...")
    print("========================================")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
