import logging
import asyncio
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
from groq import Groq

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8911906004:AAHdMeSz56WbIkBj11HWLEb-ipDEbFZ8FPU")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
DB_FILE = "baza.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
client = Groq(api_key=GROQ_API_KEY)

ELON_TUR, ELON_NOM, ELON_NARX, ELON_MANZIL, ELON_TAVSIF, ELON_RASM, ELON_TEL = range(7)

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
    import re
    baza = baza_yukla()
    faol = [e for e in baza["elonlar"] if e.get("faol")]
    if tur_filter:
        faol = [e for e in faol if e.get("tur","") == tur_filter]
    if not faol:
        return []
    raqamlar = re.findall(r'\d+', sorov.replace(",",""))
    max_narx = None
    for r in raqamlar:
        n = int(r)
        if 1000 <= n <= 9999999:
            max_narx = n
            break
    sorov_lower = sorov.lower()
    tumanlar = ["chilanzar","yunusobod","mirzo","sergeli","shayxontohur","olmazar","bektemir","yashnobod","uchtepa","yakkasaroy","toshkent","samarqand","buxoro","namangan","andijon"]
    joy_filter = next((t for t in tumanlar if t in sorov_lower), None)
    xona_filter = next((i for i in range(1,10) if f"{i} xona" in sorov_lower or f"{i}xona" in sorov_lower), None)
    markalar = ["cobalt","nexia","spark","malibu","damas","lacetti","camry","toyota","hyundai","kia","chevrolet","bmw","mercedes","lexus"]
    marka_filter = next((m for m in markalar if m in sorov_lower), None)
    natijalar = []
    for e in faol:
        ball = 0
        matn = (str(e.get("nom",""))+" "+str(e.get("tavsif",""))+" "+str(e.get("manzil",""))).lower()
        if max_narx:
            try:
                narx_str = str(e.get("narx","0")).replace("$","").replace(",","").replace(" ","")
                narx_str = ''.join(filter(str.isdigit, narx_str.split("-")[0]))
                if narx_str and int(narx_str) <= max_narx:
                    ball += 30
                elif narx_str and int(narx_str) > max_narx * 1.1:
                    continue
            except:
                pass
        if joy_filter and joy_filter in matn:
            ball += 25
        if xona_filter and (f"{xona_filter} xona" in matn or f"{xona_filter}xona" in matn):
            ball += 20
        if marka_filter and marka_filter in matn:
            ball += 25
        for soz in sorov_lower.split():
            if len(soz) > 3 and soz in matn:
                ball += 5
        if ball > 0 or not max_narx:
            natijalar.append((ball, e))
    natijalar.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in natijalar]

user_data = {}
user_state = {}
ai_suhbatlar = {}

def bosh_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Uy/Kvartira", callback_data="cat_uy"),
         InlineKeyboardButton("🚗 Avtomobil", callback_data="cat_avto")],
        [InlineKeyboardButton("🔍 Qidirish", callback_data="qidir_start"),
         InlineKeyboardButton("📋 Barcha e'lonlar", callback_data="bar_0")],
        [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start"),
         InlineKeyboardButton("📁 Mening e'lonlarim", callback_data="men_0")],
        [InlineKeyboardButton("🤖 AI maslahat", callback_data="ai_start"),
         InlineKeyboardButton("📞 Aloqa", callback_data="aloqa")],
    ])

def qayta_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]])

def bekor_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="bosh_menu")]])

def nav_kb(index, jami, prefix):
    row = []
    if index > 0:
        row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"{prefix}_{index-1}"))
    if index < jami-1:
        row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"{prefix}_{index+1}"))
    kb = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")])
    return InlineKeyboardMarkup(kb)

def elon_matn(e, index=None, jami=None):
    username = e.get("username","")
    tel = e.get("telefon","")
    kontakt = f"@{username}" if username else tel
    sarlavha = f"📊 {index}/{jami}\n" if index and jami else ""
    return (
        f"{sarlavha}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 *{e.get('nom','')}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Narx:* {e.get('narx','')}\n"
        f"📍 *Manzil:* {e.get('manzil','')}\n"
        f"📝 {e.get('tavsif','')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📞 {kontakt} | 🆔 #{e.get('id','')}"
    )

async def send_elon(bot, chat_id, e, keyboard, index=None, jami=None):
    matn = elon_matn(e, index, jami)
    rasmlar = e.get("rasmlar", [])
    try:
        if rasmlar:
            await bot.send_photo(chat_id=chat_id, photo=rasmlar[0], caption=matn, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id=chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")
    except:
        await bot.send_message(chat_id=chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None)
    ai_suhbatlar.pop(uid, None)
    matn = (
        f"Assalomu alaykum, *{update.effective_user.first_name}*! 👋\n\n"
        "🏡 *KAPITALKALIT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Uy va avto oldi-sotti platformasi\n\n"
        "✅ Tekshirilgan e'lonlar\n"
        "🔍 AI qidiruv tizimi\n"
        "📸 Rasmlar bilan\n"
        "🆓 Bepul e'lon joylash\n\n"
        "*Nima qilmoqchisiz?*"
    )
    if update.message:
        await update.message.reply_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")
    else:
        try:
            await update.callback_query.edit_message_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")
        except:
            await update.callback_query.message.reply_text(matn, reply_markup=bosh_keyboard(), parse_mode="Markdown")

async def kategoriya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    tur = "uy" if query.data == "cat_uy" else "avto"
    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("faol") and e.get("tur") == tur]
    if not elonlar:
        nom = "Uy/Kvartiralar" if tur == "uy" else "Avtomobillar"
        await query.edit_message_text(
            f"{'🏠' if tur=='uy' else '🚗'} *{nom}*\n\n😔 Hozircha e'lonlar yo'q.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]
            ]),
            parse_mode="Markdown"
        )
        return
    user_state[uid] = {"elonlar": elonlar, "tur": tur}
    prefix = f"cuy" if tur == "uy" else "cavto"
    await query.message.delete()
    await send_elon(context.bot, query.message.chat_id, elonlar[0], nav_kb(0, len(elonlar), prefix), 1, len(elonlar))

async def cat_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    parts = query.data.split("_")
    prefix = parts[0]
    index = int(parts[1])
    tur = "uy" if prefix == "cuy" else "avto"
    state = user_state.get(uid, {})
    elonlar = state.get("elonlar", [])
    if not elonlar:
        baza = baza_yukla()
        elonlar = [e for e in baza["elonlar"] if e.get("faol") and e.get("tur") == tur]
        user_state[uid] = {"elonlar": elonlar, "tur": tur}
    if not elonlar:
        await query.edit_message_text("E'lonlar topilmadi.", reply_markup=qayta_kb())
        return
    index = max(0, min(index, len(elonlar)-1))
    e = elonlar[index]
    matn = elon_matn(e, index+1, len(elonlar))
    keyboard = nav_kb(index, len(elonlar), prefix)
    rasmlar = e.get("rasmlar", [])
    try:
        await query.message.delete()
        if rasmlar:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=rasmlar[0], caption=matn, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")
    except:
        pass

async def barchasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("faol")]
    user_state[uid] = {"elonlar": elonlar}
    if not elonlar:
        await query.edit_message_text("😔 Hozircha e'lonlar yo'q.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]))
        return
    index = max(0, min(index, len(elonlar)-1))
    e = elonlar[index]
    matn = elon_matn(e, index+1, len(elonlar))
    keyboard = nav_kb(index, len(elonlar), "bar")
    rasmlar = e.get("rasmlar", [])
    try:
        await query.message.delete()
        if rasmlar:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=rasmlar[0], caption=matn, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")
    except:
        pass

async def qidir_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_state[query.from_user.id] = {"holat": "qidiryapti"}
    await query.edit_message_text(
        "🔍 *Qidiruv*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Oddiy so'zlarda yozing:\n\n"
        "💡 *Misollar:*\n"
        "• _Chilanzarda 2 xonali 40 ming_\n"
        "• _Arzon Cobalt 2022_\n"
        "• _Yunusobodda yangi tamirli_\n"
        "• _10000 gacha mashina_",
        reply_markup=bekor_kb(),
        parse_mode="Markdown"
    )

async def elon_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_data[uid] = {"rasmlar": []}
    user_state[uid] = {"holat": "elon_jarayon"}
    await query.edit_message_text(
        "➕ *E'lon joylash*\n━━━━━━━━━━━━━━━━━━━━\n\n*Nimani sotmoqchisiz?*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Kvartira", callback_data="etur_kvartira"),
             InlineKeyboardButton("🏡 Uy/Hovli", callback_data="etur_hovli")],
            [InlineKeyboardButton("🚗 Avtomobil", callback_data="etur_avto"),
             InlineKeyboardButton("🏢 Tijorat", callback_data="etur_tijorat")],
            [InlineKeyboardButton("🏞 Yer", callback_data="etur_yer"),
             InlineKeyboardButton("❌ Bekor", callback_data="bosh_menu")],
        ]),
        parse_mode="Markdown"
    )
    return ELON_TUR

async def etur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    tur_map = {"etur_kvartira":("uy","Kvartira"),"etur_hovli":("uy","Uy/Hovli"),"etur_avto":("avto","Avtomobil"),"etur_tijorat":("uy","Tijorat"),"etur_yer":("uy","Yer")}
    tur_key, tur_nomi = tur_map[query.data]
    user_data[uid]["tur"] = tur_key
    user_data[uid]["tur_nomi"] = tur_nomi
    if tur_key == "avto":
        savol = "🚗 *Avtomobil nomi*\n\nMarka, model, yilni kiriting:\n_Misol: Chevrolet Cobalt 2022_"
    else:
        savol = "🏠 *Sarlavha*\n\nQisqa va aniq yozing:\n_Misol: Chilanzarda 2 xonali kvartira_"
    await query.edit_message_text(savol, reply_markup=bekor_kb(), parse_mode="Markdown")
    return ELON_NOM

async def elon_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["nom"] = update.message.text
    await update.message.reply_text("💰 *Narx*\n\n_Misol: $45,000 yoki $300/oy_", reply_markup=bekor_kb(), parse_mode="Markdown")
    return ELON_NARX

async def elon_narx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["narx"] = update.message.text
    tur = user_data[uid].get("tur")
    savol = "📍 *Joylashuv*\n\n_Misol: Toshkent, Chilanzar_" if tur=="avto" else "📍 *Manzil*\n\n_Misol: Yunusobod, 19-mavze_"
    await update.message.reply_text(savol, reply_markup=bekor_kb(), parse_mode="Markdown")
    return ELON_MANZIL

async def elon_manzil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["manzil"] = update.message.text
    tur = user_data[uid].get("tur")
    if tur == "avto":
        savol = "📝 *Tavsif*\n\nProbeg, rang, holat, jihozlar:\n_Misol: 45,000 km, oq, a'lo holat_"
    else:
        savol = "📝 *Tavsif*\n\nMaydon, qavat, ta'mirlash:\n_Misol: 52m², 5/9 qavat, evro ta'mir_"
    await update.message.reply_text(savol, reply_markup=bekor_kb(), parse_mode="Markdown")
    return ELON_TAVSIF

async def elon_tavsif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["tavsif"] = update.message.text
    await update.message.reply_text(
        "📸 *Rasmlar*\n\nRasmlarni yuboring (1-10 ta)\n\nTugagach bosing 👇",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Rasmlar tayyor", callback_data="rasmlar_ok")]]),
        parse_mode="Markdown"
    )
    return ELON_RASM

async def elon_rasm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.photo:
        user_data[uid]["rasmlar"].append(update.message.photo[-1].file_id)
        n = len(user_data[uid]["rasmlar"])
        await update.message.reply_text(
            f"✅ {n} ta rasm!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Tayyor, davom etish", callback_data="rasmlar_ok")]])
        )
    return ELON_RASM

async def rasmlar_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📞 *Telefon raqam*\n\n_Misol: +998 90 123 45 67_", reply_markup=bekor_kb(), parse_mode="Markdown")
    return ELON_TEL

async def elon_tel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["telefon"] = update.message.text
    user_data[uid]["user_id"] = uid
    user_data[uid]["username"] = update.effective_user.username or ""
    elon_id = elon_qosh(user_data[uid])
    d = user_data[uid]
    await update.message.reply_text(
        f"🎉 *E'lon joylandi!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 #{elon_id}\n📋 *{d.get('nom')}*\n💰 {d.get('narx')}\n📍 {d.get('manzil')}\n📸 {len(d.get('rasmlar',[]))} ta rasm\n\n✅ E'loningiz ko'rinmoqda!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📁 Mening e'lonlarim", callback_data="men_0")],[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]),
        parse_mode="Markdown"
    )
    user_data.pop(uid, None)
    user_state.pop(uid, None)
    return ConversationHandler.END

async def mening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    baza = baza_yukla()
    elonlar = [e for e in baza["elonlar"] if e.get("user_id")==uid and e.get("faol")]
    if not elonlar:
        await query.edit_message_text("📭 *E'lonlar yo'q*\n\nYangi e'lon joylashtiring!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ E'lon joylash", callback_data="elon_start")],[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]), parse_mode="Markdown")
        return
    index = max(0, min(index, len(elonlar)-1))
    e = elonlar[index]
    row = []
    if index > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"men_{index-1}"))
    if index < len(elonlar)-1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"men_{index+1}"))
    kb = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"ochir_{e['id']}")])
    kb.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")])
    matn = f"📁 *Mening e'lonlarim* ({index+1}/{len(elonlar)})\n━━━━━━━━━━━━━━━━━━━━\n\n🏷 *{e.get('nom')}*\n💰 {e.get('narx')}\n📍 {e.get('manzil')}\n👁 {e.get('korishlar',0)} marta ko'rilgan\n🆔 #{e.get('id')}"
    try:
        await query.edit_message_text(matn, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except:
        await query.message.reply_text(matn, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def ochirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    elon_id = int(query.data.split("_")[1])
    if elon_ochir(elon_id, uid):
        await query.edit_message_text(f"✅ #{elon_id} o'chirildi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📁 E'lonlarim", callback_data="men_0")],[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]))
    else:
        await query.edit_message_text("❌ Xatolik.", reply_markup=qayta_kb())

AI_PROMPT = """Sen Kapitalkalit platformasining mulk va avto maslahatchisin. O'zbek tilida qisqa, aniq javob ber. Emoji ishlat. 150 so'zdan oshirma.
Bilimlar: Yunusobod $900-1200/m², Chilanzar $650-800/m², Sergeli $400-550/m². Cobalt $10-13k, Nexia3 $9-11k, Spark $7-9k, Camry $20-28k."""

async def ai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    ai_suhbatlar[uid] = []
    user_state[uid] = {"holat": "ai"}
    await query.edit_message_text(
        "🤖 *AI Maslahatchi*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Har qanday savol bering!\n\n"
        "💡 _Narx tahlili, investitsiya, hujjatlar..._",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]),
        parse_mode="Markdown"
    )

async def xabar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    holat = user_state.get(uid, {}).get("holat", "")
    matn = update.message.text

    if holat == "qidiryapti":
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        natijalar = ai_qidir(matn)
        if not natijalar:
            await update.message.reply_text("😔 Hech narsa topilmadi.\n\nBoshqa so'zlar bilan qidiring:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Qayta qidirish", callback_data="qidir_start")],[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]))
        else:
            user_state[uid] = {"holat": "natija", "elonlar": natijalar}
            await update.message.reply_text(f"✅ *{len(natijalar)} ta mos e'lon topildi!*", parse_mode="Markdown")
            e = natijalar[0]
            await send_elon(context.bot, update.effective_chat.id, e, nav_kb(0, len(natijalar), "qnat"), 1, len(natijalar))

    elif holat == "ai":
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        if uid not in ai_suhbatlar:
            ai_suhbatlar[uid] = []
        ai_suhbatlar[uid].append({"role":"user","content":matn})
        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role":"system","content":AI_PROMPT}]+ai_suhbatlar[uid][-10:],
                max_tokens=500,
                temperature=0.7,
            )
            javob = resp.choices[0].message.content
            ai_suhbatlar[uid].append({"role":"assistant","content":javob})
            await update.message.reply_text(javob, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="bosh_menu")]]))
        except:
            await update.message.reply_text("Xatolik, qayta urinib ko'ring.")
    else:
        await update.message.reply_text("👇 Menyudan tanlang:", reply_markup=bosh_keyboard())

async def qnat_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    index = int(query.data.split("_")[1])
    elonlar = user_state.get(uid, {}).get("elonlar", [])
    if not elonlar:
        await query.edit_message_text("Qidiruv tugadi.", reply_markup=qayta_kb())
        return
    index = max(0, min(index, len(elonlar)-1))
    e = elonlar[index]
    matn = elon_matn(e, index+1, len(elonlar))
    keyboard = nav_kb(index, len(elonlar), "qnat")
    rasmlar = e.get("rasmlar", [])
    try:
        await query.message.delete()
        if rasmlar:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=rasmlar[0], caption=matn, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=matn, reply_markup=keyboard, parse_mode="Markdown")
    except:
        pass

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "bosh_menu":
        uid = query.from_user.id
        user_state.pop(uid, None)
        await start(update, context)
    elif data in ["cat_uy","cat_avto"]:
        await kategoriya(update, context)
    elif data.startswith("cuy_") or data.startswith("cavto_"):
        await cat_nav(update, context)
    elif data.startswith("bar_"):
        await barchasi(update, context)
    elif data == "qidir_start":
        await qidir_start(update, context)
    elif data.startswith("qnat_"):
        await qnat_nav(update, context)
    elif data.startswith("men_"):
        await mening(update, context)
    elif data.startswith("ochir_"):
        await ochirish(update, context)
    elif data == "ai_start":
        await ai_start(update, context)
    elif data == "aloqa":
        await query.answer()
        await query.edit_message_text("📞 *Bog'lanish*\n\n📱 @kapitalkalit_support\n⏰ 9:00 — 21:00", reply_markup=qayta_kb(), parse_mode="Markdown")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    elon_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(elon_start, pattern="^elon_start$")],
        states={
            ELON_TUR: [CallbackQueryHandler(etur, pattern="^etur_")],
            ELON_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_nom)],
            ELON_NARX: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_narx)],
            ELON_MANZIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_manzil)],
            ELON_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_tavsif)],
            ELON_RASM: [MessageHandler(filters.PHOTO, elon_rasm), CallbackQueryHandler(rasmlar_ok, pattern="^rasmlar_ok$")],
            ELON_TEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, elon_tel)],
        },
        fallbacks=[CallbackQueryHandler(lambda u,c: ConversationHandler.END, pattern="^bosh_menu$")],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(elon_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, xabar_handler))
    print("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
