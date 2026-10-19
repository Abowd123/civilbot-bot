"""New input forms, step-by-step wizard layouts and result display (2026-10-19)."""
import re
from civilbot import forms as F, runner, services as S, catalog as C
from civilbot.bot import ui


def _valid_html(t):
    stack = []
    for m in re.finditer(r"<(/?)([a-z]+)[^>]*>", t):
        if m.group(1):
            assert stack and stack.pop() == m.group(2), t[:300]
        else:
            stack.append(m.group(2))
    return not stack and len(t) <= 4096


def test_every_form_example_runs():
    for tool, form in F.FORMS.items():
        assert runner.run_tool(tool, form.example) is not None, tool
        assert F.parse_text(form, form.example), tool


def test_wizard_minimal_answers_run_for_every_tool():
    """User answers only the required questions (with the suggested values) and skips the rest."""
    for tool, form in F.FORMS.items():
        vals = {f.key: f.ex for f in F.wizard_fields(form, {}) if f.req and f.ex}
        miss = F.missing_any(form, vals)
        if miss:
            vals[miss[0]] = next(f.ex for f in form.fields if f.key == miss[0])
        runner.run_tool(tool, F.build_text(form, vals))


def test_every_choice_branch_runs():
    for tool, form in F.FORMS.items():
        for cf in [f for f in form.fields if f.kind == "choice"]:
            for v, _ in cf.options:
                vals = {cf.key: v}
                for f in F.wizard_fields(form, vals):
                    if f.key not in vals and f.kind != "choice" and f.ex:
                        vals[f.key] = f.ex
                runner.run_tool(tool, F.build_text(form, vals))


def test_parse_value_is_forgiving_but_strict():
    b = F.FORMS["rc"].fields[0]
    assert F.parse_value(b, "٣٠٠") == ("300", None)
    assert F.parse_value(b, "300 mm") == ("300", None)
    assert F.parse_value(b, "0,5")[0] == "0.5"
    assert F.parse_value(b, "abc")[1] and F.parse_value(b, "-5")[1]
    t = F.FORMS["beam"].fields[1]
    assert F.parse_value(t, "كابولي") == ("cant", None) and F.parse_value(t, "xyz")[1]


def test_conditional_fields():
    slab = F.FORMS["slab"]
    assert "Lx" in [f.key for f in F.wizard_fields(slab, {})]
    one = [f.key for f in F.wizard_fields(slab, {"type": "one"})]
    assert "L" in one and "Lx" not in one and "support" in one


def test_layouts_are_valid_telegram_html():
    for tool, (name, help_html) in C.META.items():
        assert _valid_html(ui.tool_card(tool, name, help_html or "")), tool
    for tool, form in F.FORMS.items():
        vals = F.parse_text(form, form.example)
        fields = F.wizard_fields(form, vals)
        for i, f in enumerate(fields, 1):
            assert _valid_html(ui.step_prompt(tool, form, f, i, len(fields), vals, "خطأ <تجريبي>")), (tool, f.key)
        assert _valid_html(ui.review(tool, form, vals, "ملاحظة & تنبيه"))


def test_result_summary_layout():
    r = runner.run_tool("punch", "c1=400 c2=400 d=200 fc=28 Vu=550 pos=interior")
    s = S.summary_html(r)
    assert "📥 <b>المدخلات</b>" in s and "🧮 <b>خطوات الحل</b>" in s and "✅" in s
    assert "&#x27;" not in s and _valid_html(s[:4000] if len(s) > 4096 else s)


def test_catalog_exposes_forms_for_the_app():
    from civilbot import api
    c = api.catalog()
    assert c["tools"]["rc"]["form"]["fields"][0]["key"] == "b"
    assert c["tools"]["section"]["form"] is None and c["tools"]["section"]["desc"]
