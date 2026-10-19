"""CivilBot — Telegram entry point (python-telegram-bot v21, async).

Run:  BOT_TOKEN=xxx python -m civilbot.bot.main
Env:  BETA_USERS=123,456 (optional whitelist)  ADMIN_IDS=123  DAILY_LIMIT=50
"""
from __future__ import annotations
import asyncio
import html as _h
import re
import io
import logging
import os
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as KB, Update, InputFile
from telegram import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters)

from .. import services as S
from .. import services2 as S2
from .. import services3 as S3
from .. import services4 as S4
from ..ai import llm
from ..engines import quiz as QZ
from ..core import InputError
from . import storage
from . import launch as L
from . import plans as PL
from . import rk
from . import ui
from .. import forms as FM
from .textutil import split_html, LEGACY_RE
from telegram.ext import PreCheckoutQueryHandler, TypeHandler, ApplicationHandlerStop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("civilbot")
logging.getLogger("fontTools").setLevel(logging.WARNING)
logging.getLogger("weasyprint").setLevel(logging.WARNING)

BETA = {int(x) for x in os.getenv("BETA_USERS", "").split(",") if x.strip()}
ADMINS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

# only brand-new messages: edited messages must not re-run a calculation (double work + double quota),
# and channel posts have no user (effective_user is None).
MSG = filters.UpdateType.MESSAGE
ALLOWED_UPDATES = ["message", "callback_query", "pre_checkout_query"]
TELEGRAM_MAX_DOWNLOAD = 20 * 1024 * 1024
# tools that are waiting for free text: a word like "AI" or "about" here is user input, not an old button
TEXT_INPUT_TOOLS = ("feedback", "newproject", "eqcalc", "quiz")

def _rc(text):
    return S2.enrich_rc(S.run_rc(text), text)


TOOLS = {
    # phase 1
    "beam": ("📈 القص والعزم SFD/BMD", S.BEAM_HELP, S.run_beam),
    "rc": ("🏗 تصميم كمرة خرسانية", S.RC_HELP + "\n• أضف <code>span=6</code> لرسم الواجهة وجدول التفريد", _rc),
    "section": ("📐 خصائص المقاطع", S.SECTION_HELP, S.run_section),
    "formula": ("🧠 القوانين خطوة بخطوة", None, S.run_formula),
    "units": ("🔁 محول الوحدات", S.UNITS_HELP, None),
    # phase 2
    "truss": ("🔺 الجمالونات", S2.TRUSS_HELP, S2.run_truss),
    "frame": ("🏛 الإطارات 2D", S2.FRAME_HELP, S2.run_frame),
    "column": ("🏢 الأعمدة + P-M", S2.COLUMN_HELP, S2.run_column),
    "slab": ("⬜ البلاطات", S2.SLAB_HELP, S2.run_slab),
    "punch": ("🎯 القص الثاقب", S2.SLAB_HELP, S2.run_punch),
    "footing": ("🟫 القواعد", S2.FOOTING_HELP, S2.run_footing),
    "wall": ("🧱 الجدران الساندة", S2.WALL_HELP, S2.run_wall),
    "combo": ("⚖️ تراكيب الأحمال", S2.COMBO_HELP, S2.run_combo),
    "trib": ("🧭 مسار الأحمال", S2.TRIB_HELP, S2.run_trib),
    # phase 3
    "bearing": ("🏔 قدرة التحمل", S3.GEO_HELP, S3.run_bearing),
    "mohr": ("⭕ دائرة مور", S3.GEO_HELP, S3.run_mohr),
    "lateral": ("↔️ الضغط الجانبي", S3.GEO_HELP, S3.run_lateral),
    "consol": ("⬇️ الهبوط", S3.GEO_HELP, S3.run_consol),
    "bulb": ("🫧 بصيلات الإجهاد", S3.GEO_HELP, S3.run_bulb),
    "slope": ("⛰ ثبات المنحدرات", S3.GEO_HELP, S3.run_slope),
    "mix": ("🧪 تصميم الخلطة", S3.MAT_HELP, S3.run_mix),
    "sieve": ("🪣 التحليل المنخلي", S3.MAT_HELP, S3.run_sieve),
    "channel": ("🌊 القنوات المفتوحة", S3.HYD_HELP, S3.run_channel),
    "pipe": ("🚰 الأنابيب", S3.HYD_HELP, S3.run_pipe),
    "traverse": ("📐 المضلعات", S3.SUR_HELP, S3.run_traverse),
    "level": ("📏 الميزانية", S3.SUR_HELP, S3.run_level),
    "hcurve": ("↪️ منحنى أفقي", S3.SUR_HELP, S3.run_hcurve),
    "vcurve": ("⛰ منحنى رأسي", S3.SUR_HELP, S3.run_vcurve),
    "earth": ("🚜 الحفر والردم", S3.SUR_HELP, S3.run_earth),
    "pavement": ("🛣 الرصف AASHTO", S3.SUR_HELP, S3.run_pavement),
    "ssd": ("🚗 مسافة الرؤية", S3.SUR_HELP, S3.run_ssd),
    "sbeam": ("🔩 كمرة معدنية", S3.STEEL_HELP, S3.run_sbeam),
    "scol": ("🏗 عمود معدني", S3.STEEL_HELP, S3.run_scol),
    "stab": ("🔗 وصلة قص", S3.STEEL_HELP, S3.run_stab),
    "bplate": ("🟦 لوح القاعدة", S3.STEEL_HELP, S3.run_bplate),
    "il": ("📉 خطوط التأثير", S3.VIS_HELP, S3.run_il),
    "anim": ("🎬 رسوم متحركة GIF", S3.VIS_HELP, S3.run_anim),
    # phase 4
    "codes": ("📚 مقارنة الأكواد", S4.AI_HELP, S4.run_codes),
    "schedule": ("📋 جدول الأعمدة", S4.SCHED_HELP, S4.run_schedule),
    "boq": ("🧾 حصر الكميات", S4.BOQ_HELP, S4.run_boq),
    "crack": ("🔍 محلل الشروخ (صورة)", S4.AI_HELP, None),
    "equation": ("🧮 قارئ المعادلات (صورة)", S4.AI_HELP, None),
    "layout": ("🏠 توزيع الأعمدة (صورة)", S4.AI_HELP, None),
}
PHOTO_TOOLS = ("crack", "equation", "layout")

CATS = {
    "analysis": ("🧮 التحليل الإنشائي", ["beam", "truss", "frame", "trib", "combo"]),
    "design": ("🏗 التصميم الخرساني", ["rc", "column", "slab", "punch", "footing", "wall"]),
    "geo": ("🌍 ميكانيكا التربة", ["bearing", "mohr", "lateral", "consol", "bulb", "slope"]),
    "steel": ("🔩 المنشآت المعدنية", ["sbeam", "scol", "stab", "bplate"]),
    "civil": ("💧 هيدروليكا ومساحة وطرق", ["channel", "pipe", "traverse", "level", "hcurve", "vcurve", "earth", "pavement", "ssd"]),
    "mat": ("🧪 مواد وخلطات", ["mix", "sieve"]),
    "vis": ("🎬 تصور وحركة", ["il", "anim"]),
    "ai": ("🧠 الذكاء الاصطناعي", ["crack", "equation", "layout", "codes"]),
    "prod": ("📦 الإنتاجية", ["schedule", "boq"]),
    "tools": ("🛠 أدوات ومراجع", ["section", "formula", "units"]),
}


HOME = ("🏠 القائمة", "menu")


def menu():
    keys = list(CATS)
    rows = [[(CATS[c][0], f"cat:{c}") for c in keys[i:i + 2]] for i in range(0, len(keys), 2)]
    rows.append([("🎓 اختبر نفسك (FE)", "quizmenu"), ("📋 جدول التفريد BBS", "bbs")])
    rows.append([("📁 مشاريعي", "projects"), ("🕘 السجل", "history")])
    rows.append([("✏️ المحرر الرسومي", "editor"), ("📑 قوالب Excel", "templates")])
    rows.append(([] if PL.FREE_MODE else [("⭐ الباقات", "plans")]) + [("🎁 ادعُ زملاءك", "invite"), ("💬 ملاحظاتك", "tool:feedback")])
    return rk.kb(rows, placeholder="اختر قسماً أو اكتب مدخلاتك…")


def cat_menu(c):
    keys = CATS[c][1]
    rows = [[(TOOLS[k][0], f"tool:{k}") for k in keys[i:i + 2]] for i in range(0, len(keys), 2)]
    rows.append([("⬅️ رجوع", "menu")])
    return rk.kb(rows)


def home_kb():
    return rk.kb([[HOME]])


def start_kb():
    return rk.kb([[("📈 كمرة بسيطة", "ex:beam"), ("🏗 تصميم كمرة", "ex:rc")],
                  [("🔺 جمالون", "ex:truss"), ("📋 القائمة الكاملة", "menu")]])


def after_kb(web_url: str | None = None):
    rows = [[("📄 مذكرة PDF", "pdf"), ("✏️ عدّل القيم", "wiz:reedit")],
            [("🔁 نفس الأداة", "again"), ("↩️ القسم السابق", "lastcat")], [HOME]]
    if web_url:
        rows.insert(0, [("🧊 عرض 3D", WebAppInfo(url=web_url))])
    return rk.kb(rows)


def photo_kb():
    return rk.kb([[("🔍 تحليل شرخ", "photo:crack"), ("🧮 قراءة معادلة", "photo:equation")],
                  [("🏠 توزيع أعمدة على اسكتش", "photo:layout")], [HOME]])


def allowed(update: Update) -> bool:
    return not BETA or update.effective_user.id in BETA or update.effective_user.id in ADMINS


async def gate(update: Update, tool: str | None = None, feature: str | None = None) -> bool:
    if not allowed(update):
        await update.effective_message.reply_text("🔒 البوت حالياً في مرحلة تجريبية مغلقة. تواصل مع الإدارة للانضمام.")
        return False
    storage.touch_user(update.effective_user.id, update.effective_user.full_name)
    return await L.check(update, tool, feature)


EXAMPLES = {"beam": "L=6 type=ss w=20 P=40@2", "rc": "b=300 h=600 fc=28 fy=420 Mu=250 Vu=180", "truss": "type=pratt span=12 h=3 n=6 P=20"}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        await update.effective_message.reply_text("🔒 البوت حالياً في مرحلة تجريبية مغلقة.")
        return
    uid = update.effective_user.id
    new = storage.used_today(uid) == 0 and not storage.history(uid, None, 1)
    note = await L.handle_start_payload(update, ctx)
    storage.touch_user(uid, update.effective_user.full_name)
    ctx.user_data.clear()
    if note:
        await update.effective_message.reply_text(note)
    if new:
        await update.effective_message.reply_text(
            "أهلاً بك في <b>CivilBot</b> 👷‍♂️\nأكثر من 60 أداة للمهندس المدني: حسابات، رسومات، DXF، مذكرات PDF وذكاء اصطناعي.\n\n"
            "جرّب مثال بضغطة من الأزرار بالأسفل 👇 أو اكتب المدخلات مباشرة مثل:\n<code>/beam L=6 type=ss w=20</code>",
            parse_mode=ParseMode.HTML, reply_markup=start_kb())
        return
    await update.effective_message.reply_text(
        "أهلاً بك في <b>CivilBot</b> 👷‍♂️\nمساعدك في الحسابات الإنشائية والرسم.\n\nاختر الأداة من الأزرار بالأسفل 👇",
        parse_mode=ParseMode.HTML, reply_markup=menu())


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = ("<b>الأوامر</b>\n<b>التحليل:</b> /beam /truss /frame /trib /combo\n"
           "<b>التصميم:</b> /rc /column /slab /punch /footing /wall\n"
           "<b>التربة:</b> /bearing /mohr /lateral /consol /bulb /slope\n"
           "<b>المعدني:</b> /sbeam /scol /stab /bplate\n"
           "<b>هيدروليكا/مساحة/طرق:</b> /channel /pipe /traverse /level /hcurve /vcurve /earth /pavement /ssd\n"
           "<b>مواد:</b> /mix /sieve  ·  <b>تصور:</b> /il /anim\n"
           "<b>ذكاء اصطناعي:</b> أرسل صورة (شرخ/معادلة/اسكتش) · /codes\n"
           "<b>إنتاجية:</b> /schedule /boq /projects /history /export /editor /templates\n"
           "<b>أدوات:</b> /section /formula /convert /bbs /quiz /score /feedback\n"
           + ("<b>عام:</b> /invite /myplan /terms /privacy /deleteme\n\n" if PL.FREE_MODE else
              "<b>الحساب:</b> /plans /myplan /invite /redeem /team /terms /privacy /paysupport\n\n") +
           "تقدر تكتب المدخلات مباشرة بعد الأمر، مثل:\n<code>/beam L=6 type=ss w=20</code>")
    await update.effective_message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=menu())


def tool_help(tool: str) -> str:
    if tool == "formula":
        return S.FORMULA_HELP + "<b>القوانين المتاحة:</b>\n" + S.formulas.list_formulas()
    if tool == "feedback":
        return "💬 اكتب ملاحظتك أو المشكلة اللي واجهتك وأرسلها:"
    return TOOLS[tool][1]


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """أزرار Inline قديمة ما زالت ظاهرة في رسائل سابقة — نفس المسار."""
    q = update.callback_query
    await q.answer()
    await route(update, ctx, q.data)


async def route(update: Update, ctx: ContextTypes.DEFAULT_TYPE, data: str):
    """ينفّذ أكشن زر (من لوحة الأزرار السفلية أو من زر Inline قديم)."""
    msg = update.effective_message
    if not data.startswith("wiz:"):
        ctx.user_data.pop("wiz", None)          # any other button leaves the step-by-step input
    if data.startswith("wiz:"):
        await wiz_action(update, ctx, data[4:])
    elif data == "menu":
        ctx.user_data.pop("tool", None)
        await msg.reply_text(MENU_TEXT, parse_mode=ParseMode.HTML, reply_markup=menu())
    elif data.startswith("cat:") or data == "lastcat":
        c = data.split(":", 1)[1] if data.startswith("cat:") else ctx.user_data.get("cat")
        if c not in CATS:
            await msg.reply_text("اختر الأداة:", reply_markup=menu())
            return
        ctx.user_data["cat"] = c
        await msg.reply_text(ui.category_text(CATS[c][0], CATS[c][1], {k: TOOLS[k][0] for k in CATS[c][1]}),
                             parse_mode=ParseMode.HTML, reply_markup=cat_menu(c))
    elif data == "bbs":
        await send_bbs(update, ctx)
    elif data.startswith("ex:"):
        t = data.split(":")[1]
        ctx.user_data["tool"] = t
        await run_tool(update, ctx, t, EXAMPLES[t])
    elif data == "plans":
        await L.plans_cmd(update, ctx)
    elif data.startswith("buy:"):
        await L.send_invoice(update, ctx, data.split(":")[1])
    elif data == "invite":
        await L.invite_cmd(update, ctx)
    elif data == "projects":
        await projects_cmd(update, ctx)
    elif data == "newproject":
        ctx.user_data["tool"] = "newproject"
        await msg.reply_text("📁 اكتب اسم المشروع الجديد:")
    elif data.startswith("proj:"):
        pid = int(data.split(":")[1])
        name = storage.project_name(update.effective_user.id, pid)
        if name:
            ctx.user_data["project"] = pid
            await msg.reply_text(f"✅ المشروع الحالي: <b>{_h.escape(name)}</b>. كل الحسابات الجاية بتنحفظ فيه.", parse_mode=ParseMode.HTML)
    elif data == "history":
        await history_cmd(update, ctx)
    elif data.startswith("rerun:"):
        row = storage.calc(update.effective_user.id, int(data.split(":")[1]))
        if row:
            ctx.user_data["tool"] = row[0]
            await run_tool(update, ctx, row[0], row[1])
    elif data == "export":
        await export_cmd(update, ctx)
    elif data == "editor":
        await editor_cmd(update, ctx)
    elif data == "templates":
        await templates_cmd(update, ctx)
    elif data.startswith("photo:"):
        await run_photo(update, ctx, data.split(":", 1)[1], ctx.user_data.get("photo_caption", ""))
    elif data == "quizmenu":
        await msg.reply_text("🎓 اختر الموضوع:", reply_markup=quiz_kb())
    elif data.startswith("quiz:"):
        await ask_question(update, ctx, data.split(":", 1)[1])
    elif data == "quiz_next":
        t = ctx.user_data.get("quiz_topic")
        if t in QZ.TOPIC_AR:
            await ask_question(update, ctx, t)
        else:
            await msg.reply_text("🎓 اختر الموضوع:", reply_markup=quiz_kb())
    elif data == "quiz_show":
        qq = ctx.user_data.pop("quiz", None)
        if qq:
            storage.quiz_log(update.effective_user.id, qq["topic_key"], False)
            await msg.reply_text(f"💡 الجواب ≈ <b>{S.fmt(qq['ans'], 4)} {qq['unit']}</b>\n<code>{qq['sol']}</code>", parse_mode=ParseMode.HTML,
                                 reply_markup=quiz_next_kb())
    elif data == "score":
        await score_cmd(update, ctx)
    elif data == "bbs_clear":
        ctx.user_data["bbs"] = []
        await msg.reply_text("🗑 تم تفريغ جدول التفريد.", reply_markup=menu())
    elif data.startswith("tool:"):
        tool = data.split(":", 1)[1]
        ctx.user_data["tool"] = tool
        await send_card(update, ctx, tool)
    elif data == "again":
        tool = ctx.user_data.get("tool")
        if tool:
            await send_card(update, ctx, tool)
    elif data == "pdf":
        res = ctx.user_data.get("last")
        if not res:
            await msg.reply_text("ما في نتيجة محفوظة. شغّل حساب أولاً.")
            return
        if not await gate(update, feature="pdf"):
            return
        await msg.chat.send_action("upload_document")
        uid_ = update.effective_user.id
        pdf = await L.offload("pdf", res, update.effective_user.full_name, storage.logo_for(uid_) if L.plan(uid_) == "office" else None, None)
        await msg.reply_document(InputFile(io.BytesIO(pdf), filename=f"CivilBot_{res.tool}.pdf"),
                                 caption="📄 المذكرة الحسابية")


MENU_TEXT = ("🏠 <b>القائمة الرئيسية</b>\n" + ui.SEP + "\nاختر القسم من الأزرار بالأسفل 👇\n\n"
             "💡 تقدر تكتب المدخلات مباشرة، مثل:\n<code>/beam L=6 type=ss w=20</code>")


# ------------------------------------------------------------------ tool card + step-by-step input
def card_kb(tool):
    if tool in FM.FORMS:
        rows = [[("📝 إدخال خطوة بخطوة", "wiz:start"), ("▶️ جرّب المثال", "wiz:try")],
                [("📖 الشرح الكامل", "wiz:help"), ("↩️ القسم السابق", "lastcat")], [HOME]]
    else:
        rows = [[("▶️ جرّب المثال", "wiz:try"), ("↩️ القسم السابق", "lastcat")], [HOME]]
    return rk.kb(rows)


def review_kb():
    return rk.kb([[("✅ احسب الآن", "wiz:run"), ("✏️ تعديل قيمة", "wiz:edit")],
                  [("🔄 من البداية", "wiz:start"), ("✖️ إلغاء", "wiz:cancel")]])


async def send_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE, tool: str):
    msg = update.effective_message
    if tool in PHOTO_TOOLS or tool in ("feedback", "formula", "units") or tool not in TOOLS:
        await msg.reply_text(tool_help(tool), parse_mode=ParseMode.HTML)
        return
    for part in split_html(ui.tool_card(tool, TOOLS[tool][0], tool_help(tool))):
        await msg.reply_text(part, parse_mode=ParseMode.HTML, reply_markup=card_kb(tool))


def _wiz(ctx):
    return ctx.user_data.get("wiz")


async def wiz_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE, error: str | None = None):
    w = _wiz(ctx)
    form = FM.FORMS[w["tool"]]
    if w.get("edit"):
        f = next(x for x in form.fields if x.key == w["edit"])
        fields = FM.visible(form, w["vals"])
        idx, total = (fields.index(f) + 1 if f in fields else 1), len(fields)
    else:
        fields = FM.wizard_fields(form, w["vals"])
        if w["i"] >= len(fields):
            return await wiz_review(update, ctx)
        f, idx, total = fields[w["i"]], w["i"] + 1, len(fields)
    rows = []
    if f.kind == "choice":
        opts = [(lbl + (" ✓" if FM._choice_default_value(f) == v and f.key not in w["vals"] else ""), f"wiz:set:{v}") for v, lbl in f.options]
        rows += [opts[i:i + 2] for i in range(0, len(opts), 2)]
    else:
        quick = []
        if f.ex:
            quick.append((f"💡 {f.ex}", f"wiz:set:{f.ex}"))
        if not f.req:
            d = f.default if f.default and f.default != "-" else ""
            quick.append((f"⏭ تخطي" + (f" ({d})" if d else ""), "wiz:skip"))
        rows.append(quick)
    rows.append([("↩️ السابق", "wiz:back"), ("✖️ إلغاء", "wiz:cancel")])
    ph = (f"{f.label} ({f.unit})" if f.unit else f.label)[:64]
    await update.effective_message.reply_text(ui.step_prompt(TOOLS[w["tool"]][0], form, f, idx, total, w["vals"], error),
                                              parse_mode=ParseMode.HTML, reply_markup=rk.kb(rows, ctx, placeholder=ph))


async def wiz_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE, note: str | None = None):
    w = _wiz(ctx)
    w["review"] = True
    w.pop("edit", None)
    form = FM.FORMS[w["tool"]]
    await update.effective_message.reply_text(ui.review(TOOLS[w["tool"]][0], form, w["vals"], note),
                                              parse_mode=ParseMode.HTML, reply_markup=review_kb())


def _current_field(ctx):
    w = _wiz(ctx)
    form = FM.FORMS[w["tool"]]
    if w.get("edit"):
        return next(x for x in form.fields if x.key == w["edit"])
    fields = FM.wizard_fields(form, w["vals"])
    return fields[w["i"]] if w["i"] < len(fields) else None


async def _wiz_store(update, ctx, f, value):
    w = _wiz(ctx)
    if value is None:
        w["vals"].pop(f.key, None)
    else:
        w["vals"][f.key] = value
    if w.get("edit") or w.get("review"):
        return await wiz_review(update, ctx)
    w["i"] += 1
    await wiz_ask(update, ctx)


async def wiz_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    w = _wiz(ctx)
    if w.get("review") and not w.get("edit"):
        await update.effective_message.reply_text("👇 اضغط «✅ احسب الآن» أو «✏️ تعديل قيمة»", reply_markup=review_kb())
        return
    f = _current_field(ctx)
    if f is None:
        return await wiz_review(update, ctx)
    value, err = FM.parse_value(f, text)
    if err:
        return await wiz_ask(update, ctx, error=err)
    await _wiz_store(update, ctx, f, value)


async def wiz_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE, act: str):
    msg = update.effective_message
    tool = ctx.user_data.get("tool")
    if act == "start":
        if tool not in FM.FORMS:
            await msg.reply_text("اختر الأداة أولاً:", reply_markup=menu())
            return
        ctx.user_data["wiz"] = {"tool": tool, "vals": {}, "i": 0}
        return await wiz_ask(update, ctx)
    if act == "reedit":
        last = ctx.user_data.get("last_input")
        if not last or last[0] not in FM.FORMS:
            if tool:
                await send_card(update, ctx, tool)
            return
        ctx.user_data["tool"] = last[0]
        ctx.user_data["wiz"] = {"tool": last[0], "vals": FM.parse_text(FM.FORMS[last[0]], last[1]), "i": 0}
        return await wiz_review(update, ctx)
    if act == "try":
        if tool in TOOLS:
            ex = ui.example_of(tool, tool_help(tool))
            if ex:
                await msg.reply_text(f"▶️ أجرّب المثال:\n<code>{_h.escape(ex)}</code>", parse_mode=ParseMode.HTML)
                return await run_tool(update, ctx, tool, ex)
        await msg.reply_text("اختر الأداة أولاً:", reply_markup=menu())
        return
    if act == "help":
        if tool in TOOLS:
            await msg.reply_text(tool_help(tool), parse_mode=ParseMode.HTML, reply_markup=card_kb(tool))
        return
    w = _wiz(ctx)
    if not w:
        await msg.reply_text("انتهى الإدخال خطوة بخطوة. اختر الأداة من جديد 👇", reply_markup=menu())
        return
    form = FM.FORMS[w["tool"]]
    if act == "cancel":
        ctx.user_data.pop("wiz", None)
        await msg.reply_text("✖️ ألغيت الإدخال.", reply_markup=card_kb(w["tool"]))
    elif act == "back":
        if w.get("edit"):
            return await wiz_review(update, ctx)
        if w.get("review"):
            w["review"] = False
            w["i"] = max(0, len(FM.wizard_fields(form, w["vals"])) - 1)
        elif w["i"] == 0:
            ctx.user_data.pop("wiz", None)
            return await send_card(update, ctx, w["tool"])
        else:
            w["i"] -= 1
        await wiz_ask(update, ctx)
    elif act == "skip":
        f = _current_field(ctx)
        if f is not None and not f.req:
            await _wiz_store(update, ctx, f, None)
        else:
            await wiz_ask(update, ctx, error="هذي القيمة مطلوبة")
    elif act.startswith("set:"):
        f = _current_field(ctx)
        if f is None:
            return await wiz_review(update, ctx)
        value, err = FM.parse_value(f, act[4:]) if f.kind != "choice" else (act[4:], None)
        if err:
            return await wiz_ask(update, ctx, error=err)
        await _wiz_store(update, ctx, f, value)
    elif act == "edit":
        fields = FM.visible(form, w["vals"])
        btns = [(f"✏️ {f.label}"[:40], f"wiz:goto:{f.key}") for f in fields]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [[("⬅️ رجوع للمراجعة", "wiz:review")]]
        await msg.reply_text("✏️ <b>أي قيمة تبي تعدّل؟</b>", parse_mode=ParseMode.HTML, reply_markup=rk.kb(rows, ctx))
    elif act.startswith("goto:"):
        w["edit"] = act[5:]
        await wiz_ask(update, ctx)
    elif act == "review":
        await wiz_review(update, ctx)
    elif act == "run":
        miss = FM.missing_any(form, w["vals"])
        if miss:
            names = " أو ".join(next(f.label for f in form.fields if f.key == k) for k in miss[:3])
            w["edit"] = miss[0]
            return await wiz_ask(update, ctx, error=f"لازم تدخل قيمة وحدة على الأقل: {names}")
        text = FM.build_text(form, w["vals"])
        ctx.user_data.pop("wiz", None)
        ctx.user_data["tool"] = w["tool"]
        await msg.reply_text(f"⚡ أحسب…\n<code>{_h.escape(text)}</code>", parse_mode=ParseMode.HTML)
        await run_tool(update, ctx, w["tool"], text)


def quiz_kb():
    ks = list(QZ.TOPIC_AR)
    rows = [[(QZ.TOPIC_AR[k], f"quiz:{k}") for k in ks[i:i + 2]] for i in range(0, len(ks), 2)]
    rows.append([("📊 نتيجتي", "score"), ("⬅️ رجوع", "menu")])
    return rk.kb(rows)


def quiz_ctl_kb():
    return rk.kb([[("💡 الحل", "quiz_show"), ("⏭ سؤال آخر", "quiz_next")], [("🎓 المواضيع", "quizmenu"), HOME]])


def quiz_next_kb():
    return rk.kb([[("➡️ السؤال التالي", "quiz_next"), ("📊 نتيجتي", "score")], [("🎓 المواضيع", "quizmenu"), HOME]])


async def ask_question(update: Update, ctx: ContextTypes.DEFAULT_TYPE, topic: str):
    q = QZ.new_question(topic)
    q["topic_key"] = topic
    ctx.user_data["quiz"] = q
    ctx.user_data["quiz_topic"] = topic
    ctx.user_data["tool"] = "quiz"
    await update.effective_message.reply_text(f"🎓 <b>{q['topic']}</b>\n\n{q['q']}\n\nأرسل الجواب رقم فقط ({q['unit']}). سماحية ±2%",
                                              parse_mode=ParseMode.HTML, reply_markup=quiz_ctl_kb())


async def answer_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    q = ctx.user_data.get("quiz")
    if not q:
        return False
    m = re.search(r"[-+]?\d[\d,]*\.?\d*(?:e[-+]?\d+)?", text.replace("٫", ".").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if not m:
        return False
    val = float(m.group(0).replace(",", ""))
    ok = QZ.grade(q, val)
    storage.quiz_log(update.effective_user.id, q["topic_key"], ok)
    ctx.user_data.pop("quiz", None)
    head = "✅ صح! " if ok else f"❌ مو دقيق. الجواب الصحيح ≈ <b>{S.fmt(q['ans'], 4)} {q['unit']}</b>\n"
    await update.effective_message.reply_text(head + f"\n<b>الحل:</b>\n<code>{q['sol']}</code>", parse_mode=ParseMode.HTML,
                                              reply_markup=quiz_next_kb())
    return True


async def send_bbs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    bars = ctx.user_data.get("bbs") or []
    if not bars:
        await msg.reply_text("جدول التفريد فاضي. صمّم عناصر (كمرة مع span، عمود، قاعدة، بلاطة، جدار) وبتنضاف تلقائياً.")
        return
    if not await gate(update, feature="dxf"):
        return
    files, png = await L.offload("bbs", bars)
    await msg.reply_photo(io.BytesIO(png), caption=f"📋 جدول تفريد الحديد ({len(bars)} بند)")
    for name, data in files.items():
        await msg.reply_document(InputFile(io.BytesIO(data), filename=name))
    await msg.reply_text("تبي تفرغ الجدول وتبدأ مشروع جديد؟", reply_markup=rk.kb([[("🗑 تفريغ الجدول", "bbs_clear")], [HOME]]))


async def run_tool(update: Update, ctx: ContextTypes.DEFAULT_TYPE, tool: str, text: str):
    if not await gate(update, tool=tool):
        return
    msg = update.effective_message
    uid = update.effective_user.id
    t0 = time.perf_counter()
    ok, counts = False, True
    try:
        if tool == "units":
            out = S.run_units(text)
            await msg.reply_text(out, parse_mode=ParseMode.HTML)
            ok = True
            return
        await msg.chat.send_action("upload_photo")
        res = await L.offload("tool", tool, text, cache=True)
        ctx.user_data["last"] = res
        summary = S.summary_html(res)
        imgs, files, locked = L.filter_output(uid, res)
        for name, png in imgs.items():
            await msg.reply_photo(io.BytesIO(png))
        if locked:
            await msg.reply_text(f"🔒 ملفات {', '.join(locked)} (أوتوكاد/Excel) متاحة في باقة المحترف.", reply_markup=L.upsell_kb("pro"))
        for fname, data in files.items():
            if fname.endswith(".gif"):
                await msg.reply_animation(InputFile(io.BytesIO(data), filename=fname))
            else:
                await msg.reply_document(InputFile(io.BytesIO(data), filename=fname),
                                         caption="📐 ملف أوتوكاد DXF" if fname.endswith(".dxf") else None)
        new_bars = res.outputs.get("bbs") if isinstance(res.outputs, dict) else None
        if new_bars:
            import copy
            new_bars = copy.deepcopy(new_bars)   # cached results must not be mutated
            store = ctx.user_data.setdefault("bbs", [])
            idx = len({b.member for b in store}) + 1
            for b in new_bars:
                b.member = f"{b.member[0]}{idx}"
                b.mark = f"{b.member}-{b.mark.split('-')[-1]}"
            store.extend(new_bars)
        # Telegram message limit = 4096 chars
        chunks = split_html(summary)
        for i, ch in enumerate(chunks):
            await msg.reply_text(ch, parse_mode=ParseMode.HTML, reply_markup=after_kb() if i == len(chunks) - 1 else None)
        if new_bars:
            await msg.reply_text(f"➕ انضاف {len(new_bars)} بند لجدول التفريد. اضغط BBS من القائمة أو /bbs لتصديره.")
        raw = getattr(res, "_res", None)
        if raw is not None and tool in ("frame", "truss"):
            model = S4.model3d(raw, tool)
            url = S4.viewer_url(model)
            if url:
                await msg.reply_text("🧊 شوف المنشأ ثلاثي الأبعاد مع التشوه المتحرك: اضغط «🧊 عرض 3D» بالأسفل 👇", reply_markup=after_kb(url))
            else:
                await msg.reply_document(InputFile(io.BytesIO(S4.viewer_html(model)), filename=f"{tool}_3d.html"),
                                         caption="🧊 افتح الملف في المتصفح لعرض 3D تفاعلي")
        ctx.user_data["last_input"] = (tool, text)
        storage.save_calc(uid, ctx.user_data.get("project"), tool, text, res.steps[-1].result if res.steps else "")
        ok = True
    except InputError as e:
        counts = False
        ctx.user_data["last_input"] = (tool, text)
        hint = ("💡 اضغط <b>«📝 إدخال خطوة بخطوة»</b> وأسألك عن كل قيمة لحالها، أو صحّح السطر وأرسله."
                if tool in FM.FORMS else "💡 صحّح السطر وأرسله، أو اضغط <b>«▶️ جرّب المثال»</b>.")
        await msg.reply_text(f"⚠️ <b>في مشكلة بالمدخلات</b>\n{_h.escape(str(e))}\n\n{hint}", parse_mode=ParseMode.HTML,
                             reply_markup=card_kb(tool))
    except L.Busy:
        counts = False
        await msg.reply_text(L.BUSY_TEXT)
    except asyncio.TimeoutError:
        await msg.reply_text("⌛ الحساب أخذ وقت أطول من المسموح. بسّط النموذج أو قلل الدقة وجرب مرة ثانية.")
    except Exception:
        log.exception("tool %s failed for input %r", tool, text)
        await msg.reply_text("صار خطأ غير متوقع 😕 تم تسجيله وبنصلحه. جرّب مدخلات مختلفة أو أرسل /feedback.")
    finally:
        storage.log(uid, tool, ok, int((time.perf_counter() - t0) * 1000), counts=counts)


def _cmd(tool):
    async def h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        ctx.user_data["tool"] = tool
        raw = update.effective_message.text or ""
        args = raw.split(None, 1)[1] if (raw.startswith("/") and len(raw.split(None, 1)) > 1) else (" ".join(ctx.args) if ctx.args else "")
        ctx.user_data.pop("wiz", None)
        if args.strip():
            await run_tool(update, ctx, tool, args)
        else:
            await send_card(update, ctx, tool)
    return h


async def on_legacy_kb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """زر من لوحة المشروع القديم (TikTok/AI/YouTube/...) -> استبدلها بلوحة CivilBot."""
    if ctx.user_data.get("tool") in TEXT_INPUT_TOOLS or ctx.user_data.get("wiz"):   # المستخدم يكتب ملاحظة/اسم مشروع/جواب، مو زر قديم
        return await on_text(update, ctx)
    ctx.user_data.pop("tool", None)
    await update.effective_message.reply_text("🔄 تم استبدال الأزرار القديمة بأزرار CivilBot 👇\nاختر الأداة:", reply_markup=menu())


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tool = ctx.user_data.get("tool")
    text = update.effective_message.text or ""
    act = rk.resolve(ctx, text.strip())
    if act:                                   # ضغطة زر من اللوحة السفلية
        if not allowed(update):
            await update.effective_message.reply_text("🔒 البوت حالياً في مرحلة تجريبية مغلقة.")
            return
        await route(update, ctx, act)
        return
    if ctx.user_data.get("wiz"):
        await wiz_answer(update, ctx, text)
        return
    if tool == "feedback":
        storage.feedback(update.effective_user.id, text)
        ctx.user_data.pop("tool", None)
        await update.effective_message.reply_text("🙏 شكراً! وصلت ملاحظتك.", reply_markup=menu())
        for a in ADMINS:
            try:
                await ctx.bot.send_message(a, f"💬 Feedback from {update.effective_user.full_name} ({update.effective_user.id}):\n{text}")
            except Exception:
                pass
        return
    if tool == "newproject":
        pid = storage.new_project(update.effective_user.id, text.strip() or "مشروع")
        ctx.user_data["project"] = pid
        ctx.user_data.pop("tool", None)
        await update.effective_message.reply_text(f"✅ أنشأت المشروع <b>{_h.escape(text.strip()[:60])}</b> وصار هو الحالي.", parse_mode=ParseMode.HTML)
        return
    if tool == "eqcalc" and ctx.user_data.get("eq"):
        try:
            res = S4.eval_equation(ctx.user_data["eq"], text)
            await update.effective_message.reply_text(S.summary_html(res), parse_mode=ParseMode.HTML)
        except InputError as e:
            await update.effective_message.reply_text(f"⚠️ {e}")
        return
    if tool in PHOTO_TOOLS:
        await update.effective_message.reply_text("📷 أرسل صورة (مع وصف اختياري). " + ("مثال الوصف: element=beam coin=25" if tool == "crack" else "مثال الوصف: L=15 span=6" if tool == "layout" else ""))
        return
    if tool == "quiz":
        if await answer_quiz(update, ctx, text):
            return
        ctx.user_data.pop("tool", None)
        tool = None
    if not tool:
        # smart routing: guess tool from text
        low = " " + text.lower()
        has = lambda k: re.search(r"(?<![a-z0-9_])" + k + r"\s*=", low) is not None
        if has("pu"):
            tool = "column"
        elif has("pd"):
            tool = "footing"
        elif has("phi") and has("h"):
            tool = "wall"
        elif has("mu"):
            tool = "rc"
        elif has("n") and has("m") and has("s"):
            tool = "frame" if (has("w") or has("i") or has("hinge")) else "truss"
        elif has("sx") and has("sy"):
            tool = "mohr"
        elif has("phi") and has("df"):
            tool = "bearing"
        elif has("cc") and has("e0"):
            tool = "consol"
        elif has("sizes") and has("mass"):
            tool = "sieve"
        elif has("az") and has("d"):
            tool = "traverse"
        elif has("rows") and has("rl"):
            tool = "level"
        elif has("g1") and has("g2"):
            tool = "vcurve"
        elif has("w18"):
            tool = "pavement"
        elif has("n") and has("s") and (has("q") or has("y")) and has("shape"):
            tool = "channel"
        elif has("x") and has("y") and has("q"):
            tool = "trib"
        elif has("lx") and has("ly"):
            tool = "slab"
        elif has("d") and (has("l") or has("w")) and not has("p"):
            tool = "combo"
        elif has("l") and (has("p") or has("w") or has("m")):
            tool = "beam"
        elif low.split()[:1] and low.split()[0] in ("rect", "t", "i", "l", "c", "circle", "pipe", "hrect", "poly"):
            tool = "section"
        else:
            await update.effective_message.reply_text("اختر الأداة أولاً:", reply_markup=menu())
            return
        ctx.user_data["tool"] = tool
    await run_tool(update, ctx, tool, text)


async def score_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = storage.quiz_stats(update.effective_user.id)
    if not rows:
        await update.effective_message.reply_text("ما حليت أي سؤال بعد. جرب /quiz")
        return
    lines = ["📊 <b>نتيجتك</b>"]
    tot = cor = 0
    for topic, n, ok in rows:
        ok = ok or 0
        tot += n; cor += ok
        bar = "🟩" * round(10 * ok / n) + "⬜" * (10 - round(10 * ok / n))
        lines.append(f"{QZ.TOPIC_AR.get(topic, topic)}: {ok}/{n} {bar}")
    weak = min(rows, key=lambda t: (t[2] or 0) / t[1])
    lines.append(f"\nالإجمالي: {cor}/{tot} ({round(100 * cor / tot)}%)\n🎯 ركّز على: {QZ.TOPIC_AR.get(weak[0], weak[0])}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=quiz_kb())


async def quiz_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update):
        return
    topic = (ctx.args[0].lower() if ctx.args else "")
    if topic in QZ.TOPIC_AR:
        await ask_question(update, ctx, topic)
    else:
        await update.effective_message.reply_text("🎓 اختر الموضوع:", reply_markup=quiz_kb())


async def projects_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = storage.projects(update.effective_user.id)
    cur = ctx.user_data.get("project")
    kb, seen = [], set()
    for pid, name, created, n in rows[:10]:
        label = ("✅ " if pid == cur else "📁 ") + f"{str(name)[:30]} ({n})"
        if label in seen:
            label += f" #{pid}"
        seen.add(label)
        kb.append([(label, f"proj:{pid}")])
    kb.append([("➕ مشروع جديد", "newproject"), ("📦 تصدير الحالي", "export")])
    kb.append([HOME])
    await update.effective_message.reply_text("📁 <b>مشاريعك</b>" if rows else "ما عندك مشاريع. أنشئ واحد:", parse_mode=ParseMode.HTML, reply_markup=rk.kb(kb, ctx))


async def newproject_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = " ".join(ctx.args) if ctx.args else ""
    if not name:
        ctx.user_data["tool"] = "newproject"
        await update.effective_message.reply_text("📁 اكتب اسم المشروع:")
        return
    ctx.user_data["project"] = storage.new_project(update.effective_user.id, name)
    await update.effective_message.reply_text(f"✅ المشروع الحالي: {name}")


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = storage.history(update.effective_user.id, ctx.user_data.get("project"), 10)
    if not rows:
        await update.effective_message.reply_text("السجل فاضي.")
        return
    lines, btns = ["🕘 <b>آخر الحسابات</b>"], []
    for cid, tool, inp, summ, at in rows:
        lines.append(f"#{cid} <b>{_h.escape(TOOLS.get(tool, (tool,))[0])}</b>\n<code>{_h.escape(inp[:70])}</code>\n➜ {_h.escape(summ[:80])}")
        btns.append((f"🔁 إعادة #{cid}", f"rerun:{cid}"))
    btns = btns[:8]
    kb = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [[HOME]]
    await update.effective_message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=rk.kb(kb, ctx))


async def export_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, feature="export"):
        return
    pid = ctx.user_data.get("project")
    rows = storage.history(update.effective_user.id, pid, 60)
    if not rows:
        await update.effective_message.reply_text("ما في حسابات للتصدير.")
        return
    await update.effective_message.chat.send_action("upload_document")

    uid_ = update.effective_user.id
    data = await L.offload("export", rows, update.effective_user.full_name, storage.logo_for(uid_) if L.plan(uid_) == "office" else None)
    name = storage.project_name(update.effective_user.id, pid) if pid else "history"
    await update.effective_message.reply_document(InputFile(io.BytesIO(data), filename=f"CivilBot_{name}.zip"), caption="📦 كل المذكرات والملفات")


async def editor_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    base = os.getenv("WEBAPP_URL")
    if not base:
        await update.effective_message.reply_text("✏️ المحرر الرسومي يحتاج استضافة ملفات webapp وضبط WEBAPP_URL. راجع README.")
        return
    kb = rk.kb([[("✏️ افتح المحرر", WebAppInfo(url=base.rstrip("/") + "/editor.html"))], [HOME]])
    await update.effective_message.reply_text("ارسم الإطار أو الجمالون ثم اضغط «حلّل في البوت»:", reply_markup=kb)


async def on_webapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        kind, text = S4.webapp_to_text(update.effective_message.web_app_data.data)
    except InputError as e:
        await update.effective_message.reply_text(f"⚠️ {e}")
        return
    ctx.user_data["tool"] = kind
    await update.effective_message.reply_text(f"📥 استلمت النموذج:\n<code>{text}</code>", parse_mode=ParseMode.HTML)
    await run_tool(update, ctx, kind, text)


async def templates_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_document(InputFile(io.BytesIO(S4.templates_xlsx()), filename="CivilBot_templates.xlsx"),
                                                  caption="📑 كل ورقة = أداة، وكل صف = حساب. عدّل وارفع الملف هنا وبرجع لك النتائج.")


async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    doc = update.effective_message.document
    name = (doc.file_name or "").lower()
    is_img = name.endswith((".png", ".jpg", ".jpeg", ".webp"))
    if not is_img and not name.endswith(".xlsx"):
        await update.effective_message.reply_text("أدعم ملفات Excel (.xlsx) والصور حالياً.")
        return
    if (doc.file_size or 0) > TELEGRAM_MAX_DOWNLOAD:
        await update.effective_message.reply_text("📦 الملف أكبر من 20MB (حد تلجرام للبوتات). صغّره وأرسله مرة ثانية.")
        return
    if not is_img and not await gate(update, feature="import"):
        return
    f = await doc.get_file()
    data = bytes(await f.download_as_bytearray())
    if is_img:
        await on_photo_bytes(update, ctx, data, update.effective_message.caption or "")
        return
    try:
        out, summary, specials = await L.offload("import", data)
    except InputError as e:
        await update.effective_message.reply_text(f"⚠️ {e}")
        return
    await update.effective_message.reply_text("📥 <b>نتيجة الاستيراد</b>\n" + "\n".join(summary), parse_mode=ParseMode.HTML)
    if out:
        await update.effective_message.reply_document(InputFile(io.BytesIO(out), filename="CivilBot_results.xlsx"))
    for res in specials:
        for png in res.images.values():
            await update.effective_message.reply_photo(io.BytesIO(png))
        for fname, d in res.files.items():
            await update.effective_message.reply_document(InputFile(io.BytesIO(d), filename=fname))


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("tool") == "logo":
        if not await gate(update, feature="logo"):
            return
        f = await update.effective_message.photo[-1].get_file()
        storage.set_logo(update.effective_user.id, bytes(await f.download_as_bytearray()))
        ctx.user_data.pop("tool", None)
        await update.effective_message.reply_text("✅ حفظت شعار مكتبك، بيظهر على كل المذكرات.")
        return
    if not allowed(update):
        return
    ph = update.effective_message.photo[-1]
    f = await ph.get_file()
    data = bytes(await f.download_as_bytearray())
    await on_photo_bytes(update, ctx, data, update.effective_message.caption or "")


async def on_photo_bytes(update, ctx, data: bytes, caption: str):
    ctx.user_data["photo"] = data
    ctx.user_data["photo_caption"] = caption
    first = caption.strip().split()[0].lower() if caption.strip() else ""
    kind = first if first in PHOTO_TOOLS else (ctx.user_data.get("tool") if ctx.user_data.get("tool") in PHOTO_TOOLS else None)
    if kind:
        await run_photo(update, ctx, kind, caption)
        return
    await update.effective_message.reply_text("📷 وش تبي أسوي بالصورة؟", reply_markup=photo_kb())


async def run_photo(update, ctx, kind: str, caption: str):
    msg = update.effective_message
    if not await gate(update, tool=kind):
        return
    data = ctx.user_data.get("photo")
    if not data:
        await msg.reply_text("أرسل الصورة أول.")
        return
    uid = update.effective_user.id
    t0 = time.perf_counter()
    ok, counts = False, True
    try:
        await msg.chat.send_action("typing")
        eq, res = await L.offload("photo", kind, data, caption)
        if kind == "equation":
            ctx.user_data["eq"] = eq
            ctx.user_data["tool"] = "eqcalc"
        ctx.user_data["last"] = res
        imgs, _, _ = L.filter_output(uid, res)
        for png in imgs.values():
            await msg.reply_photo(io.BytesIO(png))
        tail = "\n\n🧮 أرسل القيم الآن (مثل E=200e6 I=8e-6) وبحسبها لك، أو قيمة الطرف الأيسر مع البقية لحل المجهول." if kind == "equation" else ""
        parts = split_html(S.summary_html(res) + tail)
        for i, ch in enumerate(parts):
            await msg.reply_text(ch, parse_mode=ParseMode.HTML, reply_markup=after_kb() if i == len(parts) - 1 else None)
        ok = True
    except InputError as e:
        counts = False
        await msg.reply_text(f"⚠️ {e}")
    except L.Busy:
        counts = False
        await msg.reply_text(L.BUSY_TEXT)
    except asyncio.TimeoutError:
        await msg.reply_text("⌛ تحليل الصورة أخذ وقت أطول من المسموح. جرّب صورة أصغر أو أوضح.")
    except llm.LLMError as e:
        await msg.reply_text(f"🤖 {e}")
    except Exception:
        log.exception("photo tool %s failed", kind)
        await msg.reply_text("صار خطأ غير متوقع أثناء تحليل الصورة 😕")
    finally:
        storage.log(uid, kind, ok, int((time.perf_counter() - t0) * 1000), counts=counts)


def prereg():
    """يسجّل كل نصوص الأزرار الثابتة مسبقاً، حتى تشتغل لو الشاشة لسا فيها لوحة من قبل إعادة التشغيل."""
    menu(); home_kb(); start_kb(); after_kb(); photo_kb(); quiz_kb(); quiz_ctl_kb(); quiz_next_kb(); card_kb("rc"); card_kb("section")
    review_kb()
    for c in CATS:
        cat_menu(c)
    for lbl, act in (("➕ مشروع جديد", "newproject"), ("📦 تصدير الحالي", "export"), ("🗑 تفريغ الجدول", "bbs_clear")):
        rk.reg(lbl, act)
    for need in ("student", "pro", "office"):
        L.upsell_kb(need)
    L.plans_kb()


def _C(name, fn):
    return CommandHandler(name, fn, filters=MSG)


async def beta_guard(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Closed beta: blocks EVERY command/button/message (not only calculations) for users outside BETA_USERS."""
    if not BETA or not isinstance(update, Update):
        return
    u = update.effective_user
    if u is not None and (u.id in BETA or u.id in ADMINS):
        return
    try:
        if update.callback_query:
            await update.callback_query.answer("🔒 البوت في مرحلة تجريبية مغلقة", show_alert=True)
        elif update.pre_checkout_query:
            await update.pre_checkout_query.answer(ok=False, error_message="البوت في مرحلة تجريبية مغلقة")
        elif update.effective_message and update.effective_chat and update.effective_chat.type == "private":
            await update.effective_message.reply_text("🔒 البوت حالياً في مرحلة تجريبية مغلقة. تواصل مع الإدارة للانضمام.")
    except Exception:
        pass
    raise ApplicationHandlerStop


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Last line of defence: log it and never leave the user without a reply."""
    err = ctx.error
    if isinstance(err, L.Busy):
        text = L.BUSY_TEXT
    elif isinstance(err, asyncio.TimeoutError):
        text = "⌛ العملية أخذت وقت أطول من المسموح. جرّب مرة ثانية بمدخلات أبسط."
    else:
        log.error("unhandled error for update %r", getattr(update, "update_id", None), exc_info=err)
        text = "صار خطأ غير متوقع 😕 تم تسجيله وبنصلحه. جرّب مرة ثانية أو أرسل /feedback."
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(text)
        except Exception:
            pass


def build_app() -> Application:
    token = os.environ["BOT_TOKEN"]
    app = (Application.builder().token(token).concurrent_updates(True)
           .post_init(L.post_init).post_shutdown(L.post_shutdown).build())
    app.add_handler(TypeHandler(Update, beta_guard), group=-2)
    app.add_error_handler(on_error)
    app.add_handler(MessageHandler(MSG & filters.SUCCESSFUL_PAYMENT, L.paid), group=-1)
    app.add_handler(_C("start", start))
    app.add_handler(_C("help", help_cmd))
    app.add_handler(_C("beam", _cmd("beam")))
    app.add_handler(_C("rc", _cmd("rc")))
    app.add_handler(_C("section", _cmd("section")))
    app.add_handler(_C("formula", _cmd("formula")))
    app.add_handler(_C("convert", _cmd("units")))
    for t in ("truss", "frame", "column", "slab", "punch", "footing", "wall", "combo", "trib",
              "bearing", "mohr", "lateral", "consol", "bulb", "slope", "mix", "sieve", "channel", "pipe", "traverse", "level",
              "hcurve", "vcurve", "earth", "pavement", "ssd", "sbeam", "scol", "stab", "bplate", "il", "anim"):
        app.add_handler(_C(t, _cmd(t)))
    app.add_handler(_C("bbs", send_bbs))
    app.add_handler(_C("quiz", quiz_cmd))
    for t in ("codes", "schedule", "boq"):
        app.add_handler(_C(t, _cmd(t)))
    app.add_handler(_C("projects", projects_cmd))
    app.add_handler(_C("newproject", newproject_cmd))
    app.add_handler(_C("history", history_cmd))
    app.add_handler(_C("export", export_cmd))
    app.add_handler(_C("editor", editor_cmd))
    app.add_handler(_C("templates", templates_cmd))
    app.add_handler(MessageHandler(MSG & filters.StatusUpdate.WEB_APP_DATA, on_webapp))
    app.add_handler(MessageHandler(MSG & filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(MSG & filters.Document.ALL, on_document))
    app.add_handler(_C("score", score_cmd))
    app.add_handler(_C("feedback", lambda u, c: on_button_feedback(u, c)))
    app.add_handler(_C("stats", L.stats_cmd))
    for name, fn in (("plans", L.plans_cmd), ("myplan", L.myplan_cmd), ("invite", L.invite_cmd), ("redeem", L.redeem_cmd),
                     ("team", L.team_cmd), ("myid", L.myid_cmd), ("grant", L.grant_cmd), ("revoke", L.revoke_cmd), ("promo", L.promo_cmd),
                     ("refund", L.refund_cmd), ("broadcast", L.broadcast_cmd), ("backup", L.backup_cmd), ("terms", L.terms_cmd),
                     ("privacy", L.privacy_cmd), ("paysupport", L.paysupport_cmd), ("deleteme", L.deleteme_cmd), ("logo", logo_cmd)):
        app.add_handler(_C(name, fn))
    app.add_handler(PreCheckoutQueryHandler(L.precheckout))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(MSG & filters.TEXT & filters.Regex(LEGACY_RE), on_legacy_kb))
    app.add_handler(MessageHandler(MSG & filters.TEXT & ~filters.COMMAND, on_text))
    prereg()
    return app


async def logo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, feature="logo"):
        return
    ctx.user_data["tool"] = "logo"
    await update.effective_message.reply_text("🖼 أرسل صورة شعار مكتبك (PNG بخلفية بيضاء أو شفافة).")


async def on_button_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["tool"] = "feedback"
    await update.effective_message.reply_text(tool_help("feedback"))


def main():
    app = build_app()
    url = os.getenv("WEBHOOK_URL")
    if url:  # production
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "8080")), url_path="tg",
                        webhook_url=f"{url.rstrip('/')}/tg", secret_token=os.getenv("WEBHOOK_SECRET"),
                        allowed_updates=ALLOWED_UPDATES)
    else:    # local dev
        app.run_polling(allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    main()
