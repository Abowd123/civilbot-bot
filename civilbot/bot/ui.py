"""Message layouts for the bot (pure strings, no Telegram import): tool cards, wizard steps, review screen."""
from __future__ import annotations
import html
import re

from .. import forms as FM

SEP = "━━━━━━━━━━━━━━━━"
KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
e = lambda x: html.escape(str(x), quote=False)


def _keycap(i):
    return KEYCAPS[i - 1] if i <= len(KEYCAPS) else f"<b>{i}.</b>"


def _unit(f):
    return f" <i>({e(f.unit)})</i>" if f.unit else ""


def _opt_label(f, value):
    for v, lbl in f.options:
        if v == value:
            return lbl
    return value


def _cond(form, f):
    if not f.when:
        return ""
    dep = next((x for x in form.fields if x.key == f.when[0]), None)
    names = " / ".join(_opt_label(dep, v) for v in f.when[1]) if dep else ", ".join(f.when[1])
    return f" <i>· عند {e(names)}</i>"


def example_of(tool, help_html=""):
    form = FM.FORMS.get(tool)
    if form:
        return form.example
    m = re.search(r"<code>(.*?)</code>", help_html or "", re.S)
    return html.unescape(re.sub(r"^/\w+\s*", "", m.group(1))).strip() if m else ""


def tool_card(tool: str, name: str, help_html: str) -> str:
    form = FM.FORMS.get(tool)
    desc = FM.desc(tool)
    out = [f"<b>{e(name)}</b>"] + ([f"<i>{e(desc)}</i>"] if desc else []) + [SEP]
    if not form:
        out.append(help_html.strip())
        ex = example_of(tool, help_html)
        out += [SEP, "🚀 اكتب المدخلات بنفس الصيغة وأرسلها" + ("، أو اضغط <b>«▶️ جرّب المثال»</b>" if ex else "")]
        return "\n".join(out)
    req = [f for f in form.fields if f.req]
    opt = [f for f in form.fields if not f.req]
    out.append("📥 <b>المدخلات المطلوبة</b>")
    for i, f in enumerate(req, 1):
        out.append(f"{_keycap(i)} <b>{e(f.label)}</b> · <code>{e(f.key)}</code>{_unit(f)}{_cond(form, f)}")
    if opt:
        out += ["", "⚙️ <b>اختيارية</b> <i>(لها قيمة افتراضية)</i>"]
        for f in opt:
            if f.kind == "choice":
                ch = " / ".join(f"{e(lbl)}" + (f" <code>{e(v)}</code>" if v else "") for v, lbl in f.options)
                out.append(f"• <b>{e(f.label)}</b> · <code>{e(f.key)}</code>: {ch}{_cond(form, f)}")
            else:
                d = f" · الافتراضي <b>{e(f.default)}</b>" if f.default and f.default != "-" else ""
                out.append(f"• <b>{e(f.label)}</b> · <code>{e(f.key)}</code>{_unit(f)}{d}{_cond(form, f)}")
    out += [SEP, "🚀 <b>طريقتين للإدخال</b>",
            "① اضغط <b>«📝 إدخال خطوة بخطوة»</b> وأسألك عن كل قيمة لحالها",
            "② أو أرسل كل القيم بسطر واحد بهذا الشكل:",
            f"<code>{e(form.example)}</code>"]
    if form.note:
        out.append(f"ℹ️ <i>{e(form.note)}</i>")
    return "\n".join(out)


def progress(i, n, width=10):
    k = round(width * i / n) if n else width
    return "▰" * k + "▱" * (width - k)


def _shown(f, v):
    if f.kind == "choice":
        return e(_opt_label(f, v)) if v != "" else e(_opt_label(f, ""))
    return f"<code>{e(v)}</code>" + (f" {e(f.unit)}" if f.unit else "")


def step_prompt(name: str, form, f, idx: int, total: int, values: dict, error: str | None = None) -> str:
    out = []
    if error:
        out += [f"⚠️ <b>{e(error)}</b>", ""]
    out += [f"📝 <b>{e(name)}</b>", f"الخطوة <b>{idx}</b> من <b>{total}</b>   {progress(idx - 1, total)}", "",
            f"❓ <b>{e(f.label)}</b>   <code>{e(f.key)}</code>"]
    if f.unit:
        out.append(f"📏 الوحدة: <b>{e(f.unit)}</b>")
    if f.kind != "choice" and f.ex:
        out.append(f"💡 قيمة شائعة: <code>{e(f.ex)}</code>")
    if f.req:
        out.append("⭐ <b>مطلوب</b>")
    elif f.kind != "choice":
        d = f.default if f.default and f.default != "-" else "بدون"
        out.append(f"⚙️ اختياري · الافتراضي: <b>{e(d)}</b>")
    if f.hint:
        out.append(f"ℹ️ <i>{e(f.hint)}</i>")
    done = [x for x in form.fields if x.key in values and x.key != f.key]
    if done:
        out += ["", "📋 " + " · ".join(f"{e(x.key)}={e(_opt_label(x, values[x.key]) if x.kind == 'choice' else values[x.key])}" for x in done)]
    out += [SEP, ("👇 اختر من الأزرار" if f.kind == "choice" else
                  "✍️ اكتب الرقم فقط (مثل <code>%s</code>) أو اضغط زر 👇" % e(f.ex or "10") if f.kind == "num" else
                  "✍️ اكتب القيمة (مثل <code>%s</code>) أو اضغط زر 👇" % e(f.ex))]
    return "\n".join(out)


def review(name: str, form, values: dict, note: str | None = None) -> str:
    out = [f"✅ <b>راجع المدخلات</b> · {e(name)}", SEP]
    for f in FM.visible(form, values):
        v = values.get(f.key)
        if v is None:
            if f.kind == "choice":
                out.append(f"▫️ <b>{e(f.label)}</b>: {e(_opt_label(f, FM._choice_default_value(f)))} <i>(افتراضي)</i>")
            elif f.default and f.default != "-" and f.ask:
                num = FM.NUM_RE.match(f.default)
                shown = f"<code>{e(f.default)}</code>{(' ' + e(f.unit)) if f.unit else ''}" if num else e(f.default)
                out.append(f"▫️ <b>{e(f.label)}</b>: {shown} <i>(افتراضي)</i>")
            continue
        out.append(f"▪️ <b>{e(f.label)}</b>: {_shown(f, v)}")
    out += [SEP, "✍️ <b>نفس المدخلات بسطر واحد</b> (انسخها للمرة الجاية):", f"<code>{e(FM.build_text(form, values))}</code>"]
    if note:
        out += ["", f"⚠️ <b>{e(note)}</b>"]
    return "\n".join(out)


def category_text(title: str, tools: list, names: dict) -> str:
    out = [f"<b>{e(title)}</b>", SEP]
    for t in tools:
        d = FM.desc(t)
        out.append(f"{e(names[t])}" + (f"\n   <i>{e(d)}</i>" if d else ""))
    out += [SEP, "👇 اختر الأداة من الأزرار"]
    return "\n".join(out)
