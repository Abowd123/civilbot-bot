"""لوحات الأزرار السفلية (Reply Keyboard) بدل أزرار Inline.

كل زر = نص يرسله تلجرام عند الضغط. نربط كل نص بـ «أكشن» (نفس callback_data القديمة)
ونحوّله في on_text إلى route(...). الأزرار الثابتة تُسجَّل عالمياً (تشتغل حتى بعد إعادة تشغيل
البوت)، والأزرار المتغيرة (أسماء المشاريع، السجل) تُحفظ لكل مستخدم في ctx.user_data.
"""
from __future__ import annotations
from telegram import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

ACT: dict[str, str] = {}   # label -> action (ثابتة)


def reg(label: str, action: str) -> str:
    old = ACT.get(label)
    assert old in (None, action), f"label collision: {label!r} -> {old!r} vs {action!r}"
    ACT[label] = action
    return label


def kb(rows, ctx=None, placeholder: str | None = None) -> ReplyKeyboardMarkup:
    """rows = [[(label, action) | (label, WebAppInfo(...)), ...], ...]
    ctx=None  -> أزرار ثابتة تُسجَّل عالمياً.   ctx=<context> -> أزرار متغيرة تُحفظ للمستخدم."""
    out, dyn = [], {}
    for row in rows:
        r = []
        for label, a in row:
            if isinstance(a, WebAppInfo):
                r.append(KeyboardButton(label, web_app=a))
                continue
            if ctx is None:
                reg(label, a)
            else:
                dyn[label] = a
            r.append(KeyboardButton(label))
        if r:
            out.append(r)
    if ctx is not None:
        ctx.user_data["rk_dyn"] = dyn
    return ReplyKeyboardMarkup(out, resize_keyboard=True, input_field_placeholder=placeholder)


def resolve(ctx, text: str) -> str | None:
    return (ctx.user_data.get("rk_dyn") or {}).get(text) or ACT.get(text)
