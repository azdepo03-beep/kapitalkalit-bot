import logging
import asyncio
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)
from groq import Groq

# =============================================
# SOZLAMALAR
# =============================================
TELEGRAM_TOKEN = "8911906004:AAHdMeSz56WbIkBj11HWLEb-ipDEbFZ8FPU"
GROQ_API_KEY = "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"
DB_FILE = "baza.json"
SAHIFA_HAJMI = 3

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
client = Groq(api_key=GROQ_API_KEY)

# =============================================
# CONVERSATION STATES
# =============================================
(
    ELON_TUR, ELON_NOM, ELON_NARX, ELON_MANZIL,
    ELON_TAVSIF, ELON_RASM, ELON_TEL
) = range(7)

# =============================================
# BAZA
# =============================================
def baza_yukla():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"elonlar": [], "keyingi_id": 1}

def baza_saqlа(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def elon_qosh(data):
    baza = baza_yukla()
    data["id"] = baza["keyingi_id"]
    data["faol"] = True
    data["korishlar"] = 0
    baza["elonlar"].append(data)
    baza["keyingi_id"] += 1
    baza_saqlа(baza)
    return data["id"]

def elon_ochir(elon_id, user_id):
    baza = baza_yukla()
    for e in baza["elonlar"]:
        if e["id"] == elon_id and e["user_id"] == user_id:
            e["faol"] = False
            baza_saqlа(baza)
            return True
    return False

def ai_qidir(sorov, tur_filter=None):
    """AI yordamida matnni tahlil qilib mos elonlarni topadi"""
    baza = baza_yukla()
    faol = [e for e in baza["elonlar"] if e.get("faol")]
    
    if tur_filter:
        faol = [e for e in faol if e.get("tur","").lower() == tur_filter.lower()]
    
    if not faol:
        return []

    # Narx qidirish
    import re
    raqamlar = re.findall(r'\d+', sorov.replace(",","").replace(".",""))
    max_narx = None
    for r in raqamlar:
        n = int(r)
        if 1000 <= n <= 9999999:
            max_narx = n
            break

    # Kalit so'zlar
    sorov_lower = sorov.lower()
    
    # Tuman/joy qidirish
    tumanlar = ["chilanzar", "yunusobod", "mirzo", "sergeli", "shayxontohur", 
                "olmazar", "bektemir", "yashnobod", "uchtepa", "yakkasaroy",
                "toshkent", "samarqand", "buxoro", "namangan", "andijon"]
    joy_filter = None
    for t in tumanlar:
        if t in sorov_lower:
            joy_filter = t
            break

    # Xona soni
    xona_filter = None
    for i in range(1, 10):
        if f"{i} xona" in sorov_lower or f"{i}xona" in sorov_lower or f"{i}-xona" in sorov_lower:
            xona_filter = i
            break

    # Marka (avto uchun)
    markalar = ["cobalt", "nexia", "spark", "malibu", "damas", "lacetti",
                "camry", "toyota", "hyundai", "kia", "chevrolet", "bmw", "mercedes", "lexus"]
    marka_filter = None
    for m in markalar:
        if m in sorov_lower:
            marka_filter = m
            break

    # Holat
    holat_filter = None
    if "yangi" in sorov_lower or "sifatli" in sorov_lower:
        holat_filter = "yangi"
    elif "arzon" in sorov_lower:
        holat_filter = "arzon"

    # Filtrlash va ball berish
    natijalar = []
    for e in faol:
        ball = 0
        matn = (str(e.get("nom","")) + " " + str(e.get("tavsif","")) + " " + str(e.get("manzil",""))).lower()
        
        # Narx filtri
        if max_narx:
            try:
                elon_narx_str = str(e.get("narx","0")).replace("$","").replace(",","").replace(" ","")
                elon_narx_str = elon_narx_str.split("-")[0].split("s")[0]
                elon_narx = int(''.join(filter(str.isdigit, elon_narx_str)) or "0")
                if elon_narx > max_narx * 1.1:
                    continue
                if elon_narx <= max_narx:
                    ball += 30
            except:
                pass

        # Joy filtri
        if joy_filter and joy_filter in matn:
            ball += 25

        # Xona filtri
        if xona_filter:
            if f"{xona_filter} xona" in matn or f"{xona_filter}xona" in matn:
                ball += 20

        # Marka filtri
        if marka_filter and marka_filter in matn:
            ball += 25

        # Holat filtri
        if holat_filter == "yangi" and ("yangi" in matn or "evro" in matn or "tamirli" in matn):
            ball += 10
        if holat_filter == "arzon":
            ball += 5

        # Umumiy moslik
        sorov_sozlar = sorov_lower.split()
        for soz in sorov_sozlar:
            if len(soz) > 3 and soz in matn:
                ball += 5

        if ball > 0 or not max_narx:
            natijalar.append((ball, e))

    natijalar.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in natijalar]

# =============================================
# FOYDALANUVCHI HOLATI
# =============================================
user_data = {}
user_state = {}

# =============================================
# ELON KARTOCHKASI
# =============================================
def elon_matn(e, index=None, jami=None):
    username = e.get("username","")
    tel = e.get("telefon","")
    kontakt = f"@{username}" if username else tel
    
    sarlavha = ""
    if index is not None and jami is not None:
        sarlavha = f"📊 {index}/{jami} ta e'lon\n"
    
    return (
        f"{sarlavha}"
        f"{'━'*28}\n"
        f"🏷 *{e.get('nom','')}*\n"
        f"{'━'*28}\n"
        f"💰 *Narx:* {e.get('narx','')}\n"
        f"📍 *Manzil:* {e.get('manzil','')}\n"
        f"📝 *Tavsif:* {e.get('tavsif','')}\n"
        f"{'━'*28}\n"
        f"📞 *Bog'lanish:* {kontakt}\n"
        f"🆔 E'lon #{e.get('id','')}"
    )

def navigatsiya_tugmalar(index, jami, prefix):
    tugmalar = []
    row = []
    if index > 0:
        row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"{prefix}_{index-1}"))
    if index < jami - 1:
        row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"{prefix}_{index+1}"))
    if row:
        tugmalar.append(row)
    tugmalar.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")])
    return InlineKeyboardMarkup(tugmalar)

# =============================================
# BOSH MENYU
# =============================================
def bosh_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Uy/Kvartira", callback_data="cat_uy"),
         InlineKeyboardButton("🚗 Avtomobil", callback_data="cat_avto")],
        [InlineKeyboardButton("🔍 Qidirish", callback_data="qidir_start"),
         InlineKeyboardButton("📋 Barcha e'lonlar", callback_data="barchasi_0")],
        [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start"),
         InlineKeyboardButton("📁 Mening e'lonlarim", callback_data="mening_0")],
        [InlineKeyboardButton("🤖 AI maslahat", callback_data="ai_start"),
         InlineKeyboardButton("📞 Aloqa", callback_data="aloqa")],
    ])

def qayta_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]])

def bekor_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="bosh_menu")]])

async def bosh_menyu_yuborish(update, context, yangi=False):
    matn = (
        "🏡 *KAPITALKALIT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "O'zbekistondagi eng qulay\n"
        "mulk va avto platformasi\n\n"
        "📌 *Nima qilmoqchisiz?*"
    )
    if yangi and update.message:
        await update.message.reply_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")
        except:
            await update.callback_query.message.reply_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")
    else:
        await update.message.reply_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")

# =============================================
# START
# =============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None)
    user_data.pop(uid, None)
    await bosh_menyu_yuborish(update, context, yangi=True)

# =============================================
# KATEGORIYA KO'RISH
# =============================================
async def kategoriya_kors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "cat_uy":
        tur_filter = "uy"
        sarlavha = "🏠 *Uy/Kvartiralar*"
    else:
        tur_filter = "avto"
        sarlavha = "🚗 *Avtomobillar*"

    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("faol") and e.get("tur") == tur_filter]
    
    if not elonlar:
        await query.edit_message_text(
            f"{sarlavha}\n\n😔 Hozircha e'lonlar yo'q.\n\nBirinchi e'lonni siz joylashtiring!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ]),
            parse_mode="Markdown"
        )
        return

    user_state[query.from_user.id] = {"tur": tur_filter, "elonlar": elonlar}
    prefix = f"cat_{tur_filter}"
    await kors_elon(query, elonlar, 0, prefix, context)

async def kors_elon(query, elonlar, index, prefix, context):
    e = elonlar[index]
    e["korishlar"] = e.get("korishlar", 0) + 1
    matn = elon_matn(e, index+1, len(elonlar))
    keyboard = navigatsiya_tugmalar(index, len(elonlar), prefix)
    
    rasmlar = e.get("rasmlar", [])
    chat_id = query.message.chat_id
    
    try:
        if rasmlar:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=rasmlar[0],
                caption=matn,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(matn, reply_markup=keyboard, parse_mode="Markdown")
    except:
        try:
            await context.bot.send_message(chat_id=chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")
        except:
            pass

# =============================================
# KATEGORIYA NAVIGATSIYA
# =============================================
async def cat_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    parts = query.data.split("_")
    
    if parts[1] == "uy":
        tur = "uy"
        prefix = "cat_uy"
    else:
        tur = "avto"
        prefix = "cat_avto"
    
    index = int(parts[2])
    
    state = user_state.get(uid, {})
    elonlar = state.get("elonlar", [])
    
    if not elonlar:
        baza = baza_yukla()
        elonlar = [e for e in baza["elonlar"] if e.get("faol") and e.get("tur") == tur]
        user_state[uid] = {"tur": tur, "elonlar": elonlar}
    
    if not elonlar:
        await query.edit_message_text("E'lonlar topilmadi.", reply_markup=qayta_keyboard())
        return
    
    index = max(0, min(index, len(elonlar)-1))
    await kors_elon(query, elonlar, index, prefix, context)

# =============================================
# BARCHA E'LONLAR
# =============================================
async def barchasi_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    
    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("faol")]
    user_state[uid] = {"elonlar": elonlar}
    
    if not elonlar:
        await query.edit_message_text(
            "😔 Hozircha e'lonlar yo'q.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ])
        )
        return
    
    index = max(0, min(index, len(elonlar)-1))
    await kors_elon(query, elonlar, index, "barchasi", context)

# =============================================
# QIDIRISH — AI bilan
# =============================================
async def qidir_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_state[uid] = {"holat": "qidiryapti"}
    
    await query.edit_message_text(
        "🔍 *Qidiruv*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Oddiy so'zlarda yozing — AI tushunadi!\n\n"
        "💡 *Misollar:*\n"
        "• _Chilanzarda 2 xonali 40 ming dollar_\n"
        "• _Arzon Cobalt 2022_\n"
        "• _Yunusobodda 3 xonali yangi tamirli_\n"
        "• _10000 dollar gacha mashina_\n"
        "• _Hovli uy Sergeli_",
        reply_markup=bekor_keyboard(),
        parse_mode="Markdown"
    )

async def qidir_natija_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sorov = update.message.text
    
    state = user_state.get(uid, {})
    if state.get("holat") != "qidiryapti":
        return False
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    natijalar = ai_qidir(sorov)
    
    if not natijalar:
        await update.message.reply_text(
            "😔 *Hech narsa topilmadi*\n\n"
            "Boshqa so'zlar bilan qidiring:\n"
            "• Narxni o'zgartiring\n"
            "• Boshqa tuman yozing\n"
            "• Umumiyroq qidiring",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Qayta qidirish", callback_data="qidir_start")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ]),
            parse_mode="Markdown"
        )
        user_state[uid] = {}
        return True
    
    user_state[uid] = {"holat": "natija", "elonlar": natijalar, "sorov": sorov}
    
    await update.message.reply_text(
        f"✅ *{len(natijalar)} ta mos e'lon topildi!*\n"
        f"🔍 Sorov: _{sorov}_",
        parse_mode="Markdown"
    )
    
    e = natijalar[0]
    matn = elon_matn(e, 1, len(natijalar))
    keyboard = navigatsiya_tugmalar(0, len(natijalar), "qnatija")
    
    rasmlar = e.get("rasmlar", [])
    if rasmlar:
        await update.message.reply_photo(photo=rasmlar[0], caption=matn, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(matn, reply_markup=keyboard, parse_mode="Markdown")
    
    return True

async def qnatija_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    
    state = user_state.get(uid, {})
    elonlar = state.get("elonlar", [])
    
    if not elonlar:
        await query.edit_message_text("Qidiruv muddati tugadi. Qayta qidiring.", reply_markup=qayta_keyboard())
        return
    
    index = max(0, min(index, len(elonlar)-1))
    await kors_elon(query, elonlar, index, "qnatija", context)

# =============================================
# E'LON JOYLASH
# =============================================
async def elon_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_data[uid] = {}
    user_state[uid] = {"holat": "elon_jarayon"}
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Kvartira", callback_data="etur_uy"),
         InlineKeyboardButton("🏡 Uy/Hovli", callback_data="etur_hovli")],
        [InlineKeyboardButton("🚗 Avtomobil", callback_data="etur_avto"),
         InlineKeyboardButton("🏢 Tijorat", callback_data="etur_tijorat")],
        [InlineKeyboardButton("🏞 Yer", callback_data="etur_yer"),
         InlineKeyboardButton("❌ Bekor", callback_data="bosh_menu")],
    ])
    await query.edit_message_text(
        "➕ *E'lon joylash*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Nimani sotmoqchisiz?*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return ELON_TUR

async def etur_tanlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    tur_map = {
        "etur_uy": ("uy", "Kvartira"),
        "etur_hovli": ("uy", "Uy/Hovli"),
        "etur_avto": ("avto", "Avtomobil"),
        "etur_tijorat": ("uy", "Tijorat"),
        "etur_yer": ("uy", "Yer"),
    }
    tur_key, tur_nomi = tur_map[query.data]
    user_data[uid]["tur"] = tur_key
    user_data[uid]["tur_nomi"] = tur_nomi
    user_state[uid]["bosqich"] = "nom"
    
    if tur_key == "avto":
        misol = "_Misol: Chevrolet Cobalt 2022 to'liq jihozli_"
        savol = "🚗 *Avtomobil nomi*\n\nMarka, model va yilni kiriting:"
    else:
        misol = "_Misol: Chilanzarda 2 xonali kvartira_"
        savol = "🏠 *E'lon sarlavhasi*\n\nQisqa va aniq yozing:"
    
    await query.edit_message_text(
        f"{savol}\n\n{misol}",
        reply_markup=bekor_keyboard(),
        parse_mode="Markdown"
    )
    return ELON_NOM

async def elon_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["nom"] = update.message.text
    user_state[uid]["bosqich"] = "narx"
    
    await update.message.reply_text(
        "💰 *Narx*\n\nNarxni kiriting:\n\n"
        "_Misol: $45,000_\n"
        "_Misol: $12,500 savdolashiladi_\n"
        "_Misol: $300/oy ijara_",
        reply_markup=bekor_keyboard(),
        parse_mode="Markdown"
    )
    return ELON_NARX

async def elon_narx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["narx"] = update.message.text
    user_state[uid]["bosqich"] = "manzil"
    
    tur = user_data[uid].get("tur")
    if tur == "avto":
        savol = "📍 *Joylashuv*\n\nQaysi shaharda?\n\n_Misol: Toshkent, Chilanzar_"
    else:
        savol = "📍 *Manzil*\n\nTuman va ko'chani kiriting:\n\n_Misol: Yunusobod, 19-mavze_"
    
    await update.message.reply_text(savol, reply_markup=bekor_keyboard(), parse_mode="Markdown")
    return ELON_MANZIL

async def elon_manzil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["manzil"] = update.message.text
    user_state[uid]["bosqich"] = "tavsif"
    tur = user_data[uid].get("tur")
    
    if tur == "avto":
        savol = (
            "📝 *Batafsil ma'lumot*\n\n"
            "Quyidagilarni yozing:\n"
            "• Probeg (km)\n"
            "• Rang\n"
            "• Holat (a'lo/yaxshi/o'rtacha)\n"
            "• Qo'shimcha jihozlar\n\n"
            "_Misol: 45,000 km, oq, a'lo holat, konditsioner, muftomobil yo'q_"
        )
    else:
        savol = (
            "📝 *Batafsil ma'lumot*\n\n"
            "Quyidagilarni yozing:\n"
            "• Maydon (m²)\n"
            "• Qavat\n"
            "• Ta'mirlash holati\n"
            "• Qo'shimcha (lift, parkovka, gaz...)\n\n"
            "_Misol: 52m², 5/9 qavat, evro ta'mir, lift bor, issiq suv doim_"
        )
    
    await update.message.reply_text(savol, reply_markup=bekor_keyboard(), parse_mode="Markdown")
    return ELON_TAVSIF

async def elon_tavsif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["tavsif"] = update.message.text
    user_data[uid]["rasmlar"] = []
    user_state[uid]["bosqich"] = "rasm"
    
    await update.message.reply_text(
        "📸 *Rasmlar*\n\n"
        "Rasmlarni yuboring (1-10 ta)\n"
        "Ko'p rasm = ko'p xaridor!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Rasmlar tayyor bo'lgach tugmani bosing 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Rasmlar tayyor, davom etish", callback_data="rasmlar_ok")]
        ]),
        parse_mode="Markdown"
    )
    return ELON_RASM

async def elon_rasm_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        if "rasmlar" not in user_data[uid]:
            user_data[uid]["rasmlar"] = []
        user_data[uid]["rasmlar"].append(file_id)
        n = len(user_data[uid]["rasmlar"])
        await update.message.reply_text(
            f"✅ {n} ta rasm qabul qilindi!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Tayyor, davom etish", callback_data="rasmlar_ok")]
            ])
        )
    return ELON_RASM

async def rasmlar_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_state[uid]["bosqich"] = "tel"
    
    await query.edit_message_text(
        "📞 *Telefon raqam*\n\n"
        "Xaridorlar siz bilan bog'lanadi:\n\n"
        "_Misol: +998 90 123 45 67_",
        reply_markup=bekor_keyboard(),
        parse_mode="Markdown"
    )
    return ELON_TEL

async def elon_tel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["telefon"] = update.message.text
    user_data[uid]["user_id"] = uid
    user_data[uid]["username"] = update.effective_user.username or ""
    
    elon_id = elon_qosh(user_data[uid])
    
    d = user_data[uid]
    rasmlar_soni = len(d.get("rasmlar", []))
    
    await update.message.reply_text(
        f"🎉 *E'lon joylandi!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Raqam: *#{elon_id}*\n"
        f"📋 *{d.get('nom')}*\n"
        f"💰 {d.get('narx')}\n"
        f"📍 {d.get('manzil')}\n"
        f"📸 {rasmlar_soni} ta rasm\n\n"
        f"✅ E'loningiz xaridorlarga ko'rinmoqda!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Mening e'lonlarim", callback_data="mening_0")],
            [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
        ]),
        parse_mode="Markdown"
    )
    user_data.pop(uid, None)
    user_state.pop(uid, None)
    return ConversationHandler.END

# =============================================
# MENING E'LONLARIM
# =============================================
async def mening_elonlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    
    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("user_id") == uid and e.get("faol")]
    
    if not elonlar:
        await query.edit_message_text(
            "📭 *Sizda e'lonlar yo'q*\n\nYangi e'lon joylashtiring!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    index = max(0, min(index, len(elonlar)-1))
    e = elonlar[index]
    
    matn = (
        f"📁 *Mening e'lonlarim* ({index+1}/{len(elonlar)})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷 *{e.get('nom')}*\n"
        f"💰 {e.get('narx')}\n"
        f"📍 {e.get('manzil')}\n"
        f"👁 {e.get('korishlar', 0)} marta ko'rilgan\n"
        f"🆔 #{e.get('id')}"
    )
    
    tugmalar = []
    row = []
    if index > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"mening_{index-1}"))
    if index < len(elonlar)-1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"mening_{index+1}"))
    if row:
        tugmalar.append(row)
    tugmalar.append([InlineKeyboardButton(f"🗑 E'lonni o'chirish", callback_data=f"ochir_{e['id']}")])
    tugmalar.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")])
    
    try:
        await query.edit_message_text(matn, reply_markup=InlineKeyboardMarkup(tugmalar), parse_mode="Markdown")
    except:
        await query.message.reply_text(matn, reply_markup=InlineKeyboardMarkup(tugmalar), parse_mode="Markdown")

async def elon_ochirish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    elon_id = int(query.data.split("_")[1])
    
    if elon_ochir(elon_id, uid):
        await query.edit_message_text(
            f"✅ #{elon_id} raqamli e'lon o'chirildi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📁 Mening e'lonlarim", callback_data="mening_0")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ])
        )
    else:
        await query.edit_message_text("❌ Xatolik.", reply_markup=qayta_keyboard())

# =============================================
# AI MASLAHAT
# =============================================
AI_PROMPT = """Sen Kapitalkalit platformasining mulk va avto maslahatchisin.
O'zbek tilida qisqa, aniq, foydali javob ber. Emoji ishlat. 150 so'zdan oshirma.

Bilimlar:
- Toshkent kv narxlari: Yunusobod $900-1200/m², Chilanzar $650-800/m², Sergeli $400-550/m², Mirzo Ulugbek $700-900/m²
- Mashhur avto narxlar: Cobalt $10-13k, Nexia3 $9-11k, Spark $7-9k, Malibu $15-20k, Camry $20-28k, Tucson $18-23k
- Ipoteka foizi: 18-24% yillik
- Hujjatlar: kadastr, notarius, DXB
- Investitsiya: Toshkent kv yiliga 15-20% o'sadi
"""

ai_suhbatlar = {}

async def ai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    ai_suhbatlar[uid] = []
    user_state[uid] = {"holat": "ai"}
    
    await query.edit_message_text(
        "🤖 *AI Maslahatchi*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Mulk yoki avto haqida har qanday savol bering!\n\n"
        "💡 *Misol savollar:*\n"
        "• _Chilanzarda kvartira narxi qancha?_\n"
        "• _Cobalt yoki Nexia qaysi yaxshi?_\n"
        "• _Investitsiya uchun qaysi rayon?_\n"
        "• _Ipoteka olish qanday?_",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]),
        parse_mode="Markdown"
    )

async def ai_javob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    matn = update.message.text
    ai_suhbatlar[uid].append({"role": "user", "content": matn})
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": AI_PROMPT}] + ai_suhbatlar[uid][-10:],
            max_tokens=600,
            temperature=0.7,
        )
        javob = resp.choices[0].message.content
        ai_suhbatlar[uid].append({"role": "assistant", "content": javob})
        await update.message.reply_text(
            javob,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]])
        )
    except Exception as e:
        await update.message.reply_text("Xatolik yuz berdi, qayta urinib ko'ring.")

# =============================================
# UMUMIY XABAR HANDLER
# =============================================
async def xabar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_state.get(uid, {})
    holat = state.get("holat", "")
    
    if holat == "qidiryapti":
        await qidir_natija_msg(update, context)
    elif holat == "ai":
        await ai_javob(update, context)
    else:
        await update.message.reply_text(
            "👇 Bosh menyudan tanlang:",
            reply_markup=bosh_keyboard()
        )

# =============================================
# CALLBACK HANDLER
# =============================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "bosh_menu":
        uid = query.from_user.id
        user_state.pop(uid, None)
        await bosh_menyu_yuborish(update, context)
    elif data in ["cat_uy", "cat_avto"]:
        await kategoriya_kors(update, context)
    elif data.startswith("cat_uy_") or data.startswith("cat_avto_"):
        await cat_nav(update, context)
    elif data.startswith("barchasi_"):
        await barchasi_nav(update, context)
    elif data == "qidir_start":
        await qidir_start(update, context)
    elif data.startswith("qnatija_"):
        await qnatija_nav(update, context)
    elif data.startswith("mening_"):
        await mening_elonlar(update, context)
    elif data.startswith("ochir_"):
        await elon_ochirish_cb(update, context)
    elif data == "ai_start":
        await ai_start(update, context)
    elif data == "aloqa":
        await query.answer()
        await query.edit_message_text(
            "📞 *Bog'lanish*\n\n"
            "📱 Telegram: @kapitalkalit_support\n"
            "⏰ Ish vaqti: 9:00 — 21:00\n\n"
            "Savollar uchun murojaat qiling!",
            reply_markup=qayta_keyboard(),
            parse_mode="Markdown"
        )

# =============================================
# ISHGA TUSHIRISH
# =============================================
async def run_bot():
    print("🚀 Kapitalkalit Bot ishga tushmoqda...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    elon_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(elon_start, pattern="^elon_start$")],
        states={
            ELON_TUR: [CallbackQueryHandler(etur_tanlash, pattern="^etur_")],
            ELON_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_nom)],
            ELON_NARX: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_narx)],
            ELON_MANZIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_manzil)],
            ELON_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_tavsif)],
            ELON_RASM: [
                MessageHandler(filters.PHOTO, elon_rasm_qabul),
                CallbackQueryHandler(rasmlar_ok, pattern="^rasmlar_ok$"),
            ],
            ELON_TEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_tel)],
        },
        fallbacks=[CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^bosh_menu$")],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(elon_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, xabar_handler))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("✅ Bot ishlayapti!")
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(run_bot())
