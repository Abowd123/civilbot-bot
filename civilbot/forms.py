"""Structured input forms for every tool (Telegram-free).

One schema drives three things:
  1. the tool card in the bot (clear list of inputs with units, defaults and an example line),
  2. the step-by-step input wizard in the bot (one question per field, buttons for choices/defaults),
  3. the labelled input form in the web/APK app (served through /api/tools).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict


@dataclass
class F:
    key: str                     # parameter name exactly as typed (b, Mu, fc …)
    label: str                   # Arabic label
    unit: str = ""
    req: bool = False            # required
    default: str | None = None   # shown to the user; skipping = engine default
    ex: str = ""                 # typical value (quick-fill button + placeholder)
    kind: str = "num"            # num | text | choice
    options: list = field(default_factory=list)   # [(value, label)]; value "" = do not send the key
    ask: bool = True             # asked in the wizard (False = advanced, one-line only)
    when: tuple | None = None    # (other_key, (values…)) show only when that field has one of the values
    multi: bool = False          # text: several values separated by spaces -> repeated key (P=40@2 P=30@4)
    hint: str = ""               # short extra explanation
    pos: bool = False            # must be > 0

    def to_dict(self):
        d = asdict(self)
        d["options"] = [list(o) for o in self.options]
        d["when"] = list(self.when[:1]) + [list(self.when[1])] if self.when else None
        return d


@dataclass
class Form:
    desc: str
    fields: list
    example: str
    note: str = ""
    any_of: tuple = ()           # at least one of these keys must be given by the user


def _n(key, label, unit="", ex="", default=None, req=None, **k):
    return F(key, label, unit, req=(default is None) if req is None else req, default=default, ex=ex, **k)


def _c(key, label, options, default=None, **k):
    return F(key, label, "", req=False, default=default, kind="choice", options=options, ex="", **k)


def _t(key, label, unit="", ex="", default=None, req=None, **k):
    return F(key, label, unit, req=(default is None) if req is None else req, default=default, ex=ex, kind="text", **k)


FC = lambda d="28": _n("fc", "مقاومة الخرسانة f'c", "MPa", d, d)
FY = lambda d="420": _n("fy", "إجهاد خضوع الحديد fy", "MPa", d, d)

FORMS: dict[str, Form] = {
    "beam": Form("رسم القص والعزم والترخيم لأي كمرة", [
        _n("L", "طول الكمرة", "m", "6", pos=True),
        _c("type", "نوع الركائز", [("ss", "بسيطة"), ("cant", "كابولي"), ("ff", "مثبتة الطرفين"), ("prop", "مثبتة + بسيطة")], "ss"),
        _n("w", "حمل موزع على كامل الطول", "kN/m", "20", "0", hint="لأسفل موجب"),
        _t("P", "أحمال مركزة (القيمة@المسافة)", "kN@m", "40@2", "بدون", multi=True, hint="أكثر من حمل: 40@2 30@4"),
        _n("EI", "الجساءة EI للترخيم", "kN·m²", "50000", "-", ask=False),
    ], "L=6 type=ss w=20 P=40@2", "ركائز مخصصة وأحمال جزئية من «الشرح الكامل»", any_of=("w", "P")),
    "rc": Form("تصميم كمرة خرسانية ACI 318-19 (مفرد/مزدوج + قص)", [
        _n("b", "عرض الكمرة", "mm", "300", pos=True), _n("h", "الارتفاع الكلي", "mm", "600", pos=True),
        FC(), FY(), _n("Mu", "العزم التصميمي", "kN·m", "250", pos=True),
        _n("Vu", "قوة القص التصميمية", "kN", "180", "0"),
        _n("span", "البحر (لرسم الواجهة والتفريد)", "m", "6", "-"),
        _n("cover", "الغطاء الخرساني", "mm", "40", "40", ask=False), _n("stirrup", "قطر الكانة", "mm", "10", "10", ask=False),
    ], "b=300 h=600 fc=28 fy=420 Mu=250 Vu=180 span=6"),
    "truss": Form("تحليل جمالون جاهز (Pratt/Howe/Warren)", [
        _c("type", "نوع الجمالون", [("pratt", "Pratt"), ("howe", "Howe"), ("warren", "Warren")], "pratt"),
        _n("span", "البحر", "m", "12", pos=True), _n("h", "الارتفاع", "m", "3", pos=True),
        _n("n", "عدد الألواح", "", "6", "4"), _n("P", "حمل كل عقدة سفلية", "kN", "20", "10"),
    ], "type=pratt span=12 h=3 n=6 P=20", "جمالون مخصص بالعقد والأعضاء من «الشرح الكامل»"),
    "frame": Form("تحليل إطار 2D جاهز (Portal/Gable)", [
        _c("type", "نوع الإطار", [("portal", "Portal"), ("gable", "Gable جملوني")], "portal"),
        _n("L", "البحر", "m", "6", pos=True), _n("H", "ارتفاع العمود", "m", "4", pos=True),
        _n("w", "حمل موزع على الكمرة", "kN/m", "15", "0"), _n("P", "حمل أفقي أعلى العمود الأيسر", "kN", "20", "0"),
        _c("base", "نوع القاعدة", [("fixed", "مثبتة Fixed"), ("pin", "مفصلية Pin")], "fixed"),
        _n("rise", "ارتفاع الجملون", "m", "1.5", "1.5", when=("type", ("gable",))),
    ], "type=portal L=6 H=4 w=15 P=20 base=fixed", "إطار مخصص بالعقد والمفصلات من «الشرح الكامل»"),
    "column": Form("تصميم عمود خرساني + منحنى التفاعل P-M والنحافة", [
        _n("b", "عرض العمود", "mm", "400", pos=True), _n("h", "عمق العمود", "mm", "500", pos=True), FC(), FY(),
        _n("Pu", "الحمل المحوري التصميمي", "kN", "1800", pos=True), _n("Mu", "العزم التصميمي", "kN·m", "220", "0"),
        _n("lu", "الطول الحر (للنحافة)", "m", "3.5", "-"),
        _n("k", "معامل الطول الفعال", "", "1", "1", ask=False), _n("n", "عدد الأسياخ (تثبيت)", "", "8", "تلقائي", ask=False),
        _n("db", "قطر السيخ (تثبيت)", "mm", "20", "تلقائي", ask=False), _n("cover", "الغطاء", "mm", "40", "40", ask=False),
    ], "b=400 h=500 fc=28 fy=420 Pu=1800 Mu=220 lu=3.5"),
    "slab": Form("تصميم بلاطة باتجاه واحد أو اتجاهين", [
        _c("type", "نوع البلاطة", [("", "اتجاهين"), ("one", "اتجاه واحد")], "اتجاهين"),
        _n("Lx", "البحر القصير", "m", "4", when=("type", ("",)), req=True),
        _n("Ly", "البحر الطويل", "m", "5", when=("type", ("",)), req=True),
        _c("edges", "حالة الحواف (يسار،يمين،أسفل،أعلى)", [("SSSS", "كلها بسيطة SSSS"), ("FFFF", "كلها مستمرة FFFF"),
                                                         ("FSFS", "FSFS"), ("FFSS", "FFSS"), ("FFFS", "FFFS")], "SSSS",
           when=("type", ("",)), hint="F مستمر/مثبت ، S بسيط"),
        _n("L", "البحر", "m", "4", when=("type", ("one",)), req=True),
        _c("support", "الاستمرارية", [("ss", "بسيطة"), ("one", "مستمرة من طرف"), ("both", "مستمرة من الطرفين"), ("cant", "كابولي")], "ss",
           when=("type", ("one",))),
        _n("wD", "الحمل الميت الإضافي", "kN/m²", "2", "1.5"), _n("wL", "الحمل الحي", "kN/m²", "3", "2"),
        FC(), FY(), _n("h", "السماكة", "mm", "150", "تلقائي", ask=False),
    ], "Lx=4 Ly=5 edges=FSFS wD=2 wL=3 fc=28 fy=420"),
    "punch": Form("فحص القص الثاقب ACI 22.6", [
        _n("c1", "بعد العمود c1", "mm", "400", pos=True), _n("c2", "بعد العمود c2", "mm", "400", "= c1"),
        _n("d", "العمق الفعال للبلاطة", "mm", "200", pos=True), FC(), _n("Vu", "قوة القص التصميمية", "kN", "550", pos=True),
        _c("pos", "موقع العمود", [("interior", "داخلي"), ("edge", "طرفي"), ("corner", "ركني")], "interior"),
    ], "c1=400 c2=400 d=200 fc=28 Vu=550 pos=interior"),
    "footing": Form("تصميم قاعدة منفصلة (ثاقب + قص + حديد + DXF)", [
        _n("PD", "الحمل الميت", "kN", "800", pos=True), _n("PL", "الحمل الحي", "kN", "500", "0"),
        _n("qa", "قدرة تحمل التربة المسموحة", "kPa", "200", pos=True),
        _n("c1", "بعد العمود c1", "mm", "400", pos=True), _n("c2", "بعد العمود c2", "mm", "400", "= c1"),
        FC("25"), FY(), _n("M", "عزم تشغيلي", "kN·m", "60", "0"),
        _n("Df", "عمق التأسيس", "m", "1.5", "1.5", ask=False), _n("ratio", "نسبة L/B", "", "1.2", "1", ask=False),
    ], "PD=800 PL=500 qa=200 c1=400 c2=400 fc=25 fy=420 M=60"),
    "wall": Form("تصميم جدار ساند كابولي (انقلاب، انزلاق، ضغط، حديد)", [
        _n("H", "ارتفاع الجدار", "m", "5", pos=True), _n("phi", "زاوية الاحتكاك φ", "°", "30", pos=True),
        _n("gamma", "وزن التربة النوعي", "kN/m³", "18", "18"), _n("q", "حمل إضافي سطحي", "kPa", "10", "0"),
        _n("qa", "قدرة التحمل المسموحة", "kPa", "200", "200"), FC(), FY(),
        _n("B", "عرض القاعدة", "m", "3.5", "تلقائي", ask=False), _n("mu", "معامل الاحتكاك", "", "0.5", "تلقائي", ask=False),
    ], "H=5 phi=30 gamma=18 q=10 qa=200"),
    "combo": Form("كل تراكيب الأحمال والحالة الحاكمة", [
        _n("D", "الحمل الميت", "kN", "120", "0"), _n("L", "الحمل الحي", "kN", "80", "0"),
        _n("Lr", "حمل السطح الحي", "kN", "10", "0", ask=False), _n("S", "حمل الثلج", "kN", "0", "0", ask=False),
        _n("W", "حمل الرياح", "kN", "40", "0"), _n("E", "حمل الزلازل", "kN", "30", "0"),
        _c("code", "الكود", [("aci", "ACI/ASCE LRFD"), ("asd", "ASD"), ("bs", "BS 8110")], "aci"),
    ], "D=120 L=80 W=40 code=aci", any_of=("D", "L", "Lr", "S", "W", "E")),
    "trib": Form("المساحات التخديمية وأحمال الكمرات والأعمدة", [
        _t("X", "بحور اتجاه x (مفصولة بفاصلة)", "m", "5,6"), _t("Y", "بحور اتجاه y", "m", "4,4.5"),
        _n("q", "حمل البلاطة", "kN/m²", "12", pos=True),
    ], "X=5,6 Y=4,4.5 q=12"),
    "bearing": Form("قدرة تحمل التربة للأساسات الضحلة", [
        _n("B", "عرض الأساس", "m", "2", pos=True), _n("L", "طول الأساس (0 = شريطي)", "m", "2", "0"),
        _n("Df", "عمق التأسيس", "m", "1.5"), _n("c", "التماسك c", "kPa", "0", "0"), _n("phi", "زاوية الاحتكاك φ", "°", "30"),
        _n("gamma", "وزن التربة", "kN/m³", "18", "18"),
        _c("method", "الطريقة", [("terzaghi", "Terzaghi"), ("meyerhof", "Meyerhof"), ("hansen", "Hansen"), ("vesic", "Vesic")], "meyerhof"),
        _n("FS", "معامل الأمان", "", "3", "3"), _n("gw", "عمق المياه الجوفية", "m", "2", "-", ask=False),
    ], "B=2 L=2 Df=1.5 c=0 phi=30 gamma=18 method=meyerhof FS=3"),
    "mohr": Form("دائرة مور والإجهادات الرئيسية", [
        _n("sx", "الإجهاد σx", "kPa", "80"), _n("sy", "الإجهاد σy", "kPa", "-40"), _n("txy", "إجهاد القص τxy", "kPa", "25", "0"),
        _n("theta", "زاوية مستوى مطلوب", "°", "30", "-"),
    ], "sx=80 sy=-40 txy=25 theta=30"),
    "lateral": Form("ضغط التربة الجانبي (Rankine/Coulomb)", [
        _n("H", "ارتفاع الجدار", "m", "6", pos=True), _n("phi", "زاوية الاحتكاك φ", "°", "30"),
        _n("gamma", "وزن التربة", "kN/m³", "18", "18"), _n("c", "التماسك", "kPa", "0", "0"), _n("q", "حمل سطحي", "kPa", "10", "0"),
        _c("method", "الطريقة", [("rankine", "Rankine"), ("coulomb", "Coulomb")], "rankine"),
        _n("delta", "احتكاك الجدار δ", "°", "20", "0", when=("method", ("coulomb",))),
        _n("beta", "ميل سطح الردم β", "°", "0", "0", when=("method", ("coulomb",))),
    ], "H=6 phi=30 gamma=18 c=0 q=10 method=rankine"),
    "consol": Form("هبوط التصلب الأولي ومنحنى الزمن", [
        _n("H", "سماكة طبقة الطين", "m", "4", pos=True), _n("e0", "نسبة الفراغات الابتدائية", "", "1.1", pos=True),
        _n("Cc", "معامل الانضغاط Cc", "", "0.36", pos=True), _n("s0", "الإجهاد الفعال الأولي", "kPa", "80", pos=True),
        _n("ds", "زيادة الإجهاد", "kPa", "60", pos=True), _n("cv", "معامل التصلب cv", "m²/yr", "1.5", "-"),
        _n("t", "الزمن", "yr", "1", "-"), _n("Cs", "معامل الانتفاخ Cs", "", "0.05", "-", ask=False),
        _n("sp", "إجهاد ما قبل التحميل", "kPa", "120", "-", ask=False),
    ], "H=4 e0=1.1 Cc=0.36 s0=80 ds=60 cv=1.5 t=1"),
    "bulb": Form("بصيلات الإجهاد تحت الأساس (Boussinesq)", [
        _n("q", "الضغط على الأساس", "kPa", "150", pos=True), _n("B", "عرض الأساس", "m", "2", pos=True),
        _n("L", "طول الأساس", "m", "3", "-"),
    ], "q=150 B=2 L=3"),
    "slope": Form("ثبات المنحدرات بطريقة Bishop", [
        _n("H", "ارتفاع المنحدر", "m", "10", pos=True), _n("beta", "زاوية الميل", "°", "30", pos=True),
        _n("c", "التماسك", "kPa", "10", "0"), _n("phi", "زاوية الاحتكاك φ", "°", "30"),
        _n("gamma", "وزن التربة", "kN/m³", "18", "18"), _n("ru", "نسبة ضغط المسام ru", "", "0", "0"),
    ], "H=10 beta=30 c=10 phi=30 gamma=18 ru=0"),
    "mix": Form("تصميم خلطة خرسانية ACI 211.1", [
        _n("fc", "المقاومة المطلوبة f'c", "MPa", "28", pos=True), _n("slump", "الهبوط", "mm", "75", "75"),
        _n("nmsa", "أكبر مقاس للركام", "mm", "19", "19"), _n("fm", "معامل نعومة الرمل", "", "2.8", "2.7"),
        _n("rodded", "وحدة وزن الركام الخشن المدموك", "kg/m³", "1600", "1600"),
        _c("air", "هواء محبوس", [("", "بدون"), ("1", "مع هواء محبوس")], "بدون"),
        _c("exposure", "درجة التعرض", [("mild", "خفيف"), ("moderate", "متوسط"), ("severe", "شديد")], "moderate", when=("air", ("1",))),
    ], "fc=28 slump=75 nmsa=19 fm=2.8 rodded=1600"),
    "sieve": Form("التحليل المنخلي، FM و Cu و Cc وحدود ASTM", [
        _t("sizes", "فتحات المناخل (مفصولة بفاصلة)", "mm", "4.75,2.36,1.18,0.6,0.3,0.15,0.075"),
        _t("mass", "الكتلة المحجوزة على كل منخل", "g", "20,80,120,150,90,30,10"),
        _c("spec", "المواصفة", [("fine", "رمل ASTM C33"), ("57", "ركام #57"), ("67", "ركام #67"), ("none", "بدون")], "fine"),
    ], "sizes=4.75,2.36,1.18,0.6,0.3,0.15,0.075 mass=20,80,120,150,90,30,10 spec=fine"),
    "channel": Form("قناة مفتوحة بمعادلة Manning", [
        _c("shape", "شكل القناة", [("rect", "مستطيل"), ("trap", "شبه منحرف"), ("tri", "مثلث"), ("circle", "دائري")], "rect"),
        _n("b", "عرض القاع", "m", "3", when=("shape", ("rect", "trap")), req=True),
        _n("z", "ميل الجوانب (أفقي:رأسي)", "", "2", when=("shape", ("trap", "tri")), req=True),
        _n("D", "القطر", "m", "1.2", when=("shape", ("circle",)), req=True),
        _n("n", "معامل Manning", "", "0.015", pos=True), _n("S", "ميل القاع", "m/m", "0.001", pos=True),
        _n("Q", "التصريف (لإيجاد العمق)", "m³/s", "10", "-", hint="أعط Q أو y"),
        _n("y", "العمق (لإيجاد التصريف)", "m", "1.5", "-"),
    ], "shape=trap b=3 z=2 n=0.015 S=0.001 Q=10", any_of=("Q", "y")),
    "pipe": Form("فواقد الأنابيب وقدرة المضخة", [
        _n("Q", "التصريف", "m³/s", "0.05", pos=True), _n("D", "قطر الأنبوب", "m", "0.2", pos=True),
        _n("L", "طول الأنبوب", "m", "500", pos=True),
        _c("method", "الطريقة", [("darcy", "Darcy-Colebrook"), ("hw", "Hazen-Williams")], "darcy"),
        _n("eps", "خشونة الجدار", "mm", "0.045", "0.045", when=("method", ("darcy",))),
        _n("C", "معامل Hazen-Williams", "", "130", "130", when=("method", ("hw",))),
        _n("K", "مجموع معاملات الفواقد الثانوية", "", "5", "0"), _n("dz", "فرق المنسوب", "m", "10", "0"),
    ], "Q=0.05 D=0.2 L=500 eps=0.045 K=5 dz=10"),
    "traverse": Form("ضبط مضلع مغلق بطريقة Bowditch", [
        _t("az", "الانحرافات (درجة-دقيقة-ثانية)", "", "45-30-00,135-12-00,225,315-06"),
        _t("d", "الأطوال", "m", "100,100,100.05,99.98"),
        _n("E0", "إحداثي الشرق للبداية", "m", "1000", "1000"), _n("N0", "إحداثي الشمال للبداية", "m", "1000", "1000"),
    ], "az=45-30-00,135-12-00,225,315-06 d=100,100,100.05,99.98 E0=1000 N0=1000"),
    "hcurve": Form("عناصر وتوقيع منحنى أفقي", [
        _n("R", "نصف القطر", "m", "300", pos=True), _t("delta", "زاوية الانحراف (درجة أو د-د-ث)", "°", "40"),
        _n("PI", "محطة نقطة التقاطع", "m", "1000"), _n("chord", "طول الوتر", "m", "20", "20"),
    ], "R=300 delta=40 PI=1000 chord=20"),
    "vcurve": Form("منحنى رأسي ومناسيبه", [
        _n("g1", "الميل الداخل", "%", "3"), _n("g2", "الميل الخارج", "%", "-2"), _n("L", "طول المنحنى", "m", "200", pos=True),
        _n("PVI", "محطة نقطة التقاطع", "m", "1500"), _n("el", "منسوب نقطة التقاطع", "m", "100"),
        _n("step", "مسافة الحساب", "m", "20", "20", ask=False),
    ], "g1=3 g2=-2 L=200 PVI=1500 el=100"),
    "earth": Form("كميات الحفر والردم ومنحنى ماس هول", [
        _t("st", "المحطات", "m", "0,20,40,60"), _t("A", "مساحات المقاطع (+حفر / -ردم)", "m²", "10,5,-4,-8"),
    ], "st=0,20,40,60 A=10,5,-4,-8"),
    "pavement": Form("تصميم رصف مرن AASHTO 93", [
        _n("W18", "عدد المحاور المكافئة ESAL", "", "5e6", pos=True), _n("R", "الاعتمادية", "%", "95", "95"),
        _n("S0", "الانحراف المعياري", "", "0.45", "0.45"), _n("MR", "معامل المرونة للتربة", "MPa", "50", pos=True),
    ], "W18=5e6 R=95 S0=0.45 MR=50"),
    "ssd": Form("مسافة الرؤية للتوقف", [
        _n("V", "السرعة التصميمية", "km/h", "100", pos=True), _n("t", "زمن رد الفعل", "s", "2.5", "2.5"),
        _n("G", "الميل الطولي", "%", "0", "0"),
    ], "V=100 t=2.5 G=0"),
    "sbeam": Form("اختيار وتصميم كمرة معدنية AISC 360-16", [
        _n("Mu", "العزم التصميمي", "kN·m", "150", pos=True), _n("Vu", "القص التصميمي", "kN", "120", "0"),
        _n("Lb", "الطول غير المدعوم جانبياً", "m", "3"), _n("Fy", "إجهاد الخضوع", "MPa", "355", "355"),
        _c("family", "عائلة المقاطع", [("IPE", "IPE"), ("HEA", "HEA"), ("HEB", "HEB")], "IPE"),
        _n("L", "البحر (للترخيم)", "m", "6", "-", ask=False), _n("w", "الحمل التشغيلي (للترخيم)", "kN/m", "15", "-", ask=False),
    ], "Mu=150 Vu=120 Lb=3 Fy=355"),
    "scol": Form("تصميم عمود معدني AISC 360-16", [
        _n("Pu", "الحمل المحوري", "kN", "1500", pos=True), _n("KL", "الطول الفعال", "m", "4", pos=True),
        _n("Fy", "إجهاد الخضوع", "MPa", "355", "355"), _n("Mux", "عزم مصاحب", "kN·m", "60", "0"),
        _c("family", "عائلة المقاطع", [("HEB", "HEB"), ("HEA", "HEA"), ("IPE", "IPE")], "HEB"),
    ], "Pu=1500 KL=4 Fy=355"),
    "stab": Form("تصميم وصلة قص بمسامير", [
        _n("Vu", "قوة القص", "kN", "250", pos=True), _n("d", "قطر المسمار", "mm", "20", "20"),
        _c("grade", "رتبة المسامير", [("A325N", "A325N"), ("A325X", "A325X"), ("A490N", "A490N")], "A325N"),
        _n("tp", "سماكة اللوح", "mm", "10", "10"), _n("tw", "سماكة جذع الكمرة", "mm", "7.1", "7.1"),
    ], "Vu=250 d=20 grade=A325N tp=10 tw=7.1"),
    "bplate": Form("تصميم لوح قاعدة عمود معدني", [
        _n("Pu", "الحمل المحوري", "kN", "1500", pos=True), _n("d", "عمق مقطع العمود", "mm", "300", pos=True),
        _n("bf", "عرض شفة العمود", "mm", "300", pos=True), _n("fc", "مقاومة الخرسانة", "MPa", "25", "25"),
        _n("Fy", "إجهاد خضوع اللوح", "MPa", "250", "250"),
    ], "Pu=1500 d=300 bf=300 fc=25 Fy=250"),
}

# one-line descriptions for tools without a form (shown in the category list and the tool card)
DESC = {
    "section": "خصائص أي مقطع: المساحة، المركز، العزوم، المحاور الرئيسية",
    "formula": "حل أي قانون هندسي خطوة بخطوة وإيجاد المجهول",
    "units": "تحويل فوري بين وحدات القوى والإجهادات والأحمال",
    "level": "حساب المناسيب من دفتر الميزانية مع التحقق",
    "il": "خطوط التأثير وأقصى تأثير لشاحنة أو حمل موزع",
    "anim": "رسوم متحركة GIF للانبعاج والترخيم والاهتزاز",
    "codes": "مقارنة بنود الأكواد بالذكاء الاصطناعي",
    "schedule": "جدول تصميم أعمدة كامل دفعة واحدة",
    "boq": "حصر كميات الخرسانة والحديد والطوب مع التكلفة",
    "crack": "تحليل صورة شرخ: النوع، السبب المحتمل، العرض",
    "equation": "قراءة معادلة من صورة وحسابها",
    "layout": "اقتراح توزيع أعمدة على اسكتش معماري",
}


def desc(tool: str) -> str:
    f = FORMS.get(tool)
    return f.desc if f else DESC.get(tool, "")


def visible(form: Form, values: dict) -> list:
    """Fields that apply given the values chosen so far (choice-dependent fields)."""
    out = []
    for f in form.fields:
        if f.when:
            k, allowed = f.when
            dep = next((x for x in form.fields if x.key == k), None)
            cur = values.get(k, _choice_default_value(dep) if dep else None)
            if cur not in allowed:
                continue
        out.append(f)
    return out


def _choice_default_value(f: F):
    if f.kind != "choice":
        return f.default
    for v, lbl in f.options:
        if f.default in (v, lbl):
            return v
    return f.options[0][0] if f.options else ""


def wizard_fields(form: Form, values: dict) -> list:
    return [f for f in visible(form, values) if f.ask or f.req]


_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
NUM_RE = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$", re.I)


def clean(text: str) -> str:
    """Arabic/Persian digits -> ASCII, Arabic comma -> comma, trim."""
    return text.translate(_AR).replace("،", ",").replace("−", "-").strip()


def parse_value(f: F, text: str) -> tuple[str | None, str | None]:
    """Returns (value, error_message_ar)."""
    t = clean(text)
    if f.kind == "choice":
        for v, lbl in f.options:
            if t.lower() in (v.lower(), lbl.lower()) and t != "":
                return v, None
        return None, "اختر من الأزرار بالأسفل 👇"
    if not t:
        return None, "القيمة فاضية"
    if f.kind == "num":
        t = t.replace(",", ".") if t.count(",") == 1 and "." not in t else t.replace(",", "")
        t = re.sub(r"\s*[a-zA-Z/²³·°%]+.*$", "", t) if re.match(r"^[-+]?[\d.]", t) else t   # "300 mm" -> 300
        if not NUM_RE.match(t):
            return None, f"لازم رقم. مثال: {f.ex or '10'}"
        if f.pos and float(t) <= 0:
            return None, "لازم القيمة تكون أكبر من صفر"
        return t, None
    t = re.sub(r"\s+", " ", t)
    if " " in t and not f.multi:
        t = t.replace(" ", "")
    return t, None


def build_text(form: Form, values: dict) -> str:
    parts = []
    for f in visible(form, values):
        v = values.get(f.key)
        if v is None and f.kind == "choice":
            v = _choice_default_value(f)      # a choice always sends its value (e.g. frame needs type=portal)
        elif v is None and f.kind == "num" and f.ask and f.default and NUM_RE.match(f.default):
            v = f.default                     # numeric defaults are sent explicitly: the user sees exactly what was used
        if v in (None, ""):
            continue
        if f.multi:
            parts += [f"{f.key}={x}" for x in re.split(r"[\s,]+", v) if x]
        else:
            parts.append(f"{f.key}={v}")
    return " ".join(parts)


def parse_text(form: Form, text: str) -> dict:
    """One-line input -> wizard values (so «✏️ عدّل القيم» works after typed input too)."""
    keys = {f.key.lower(): f for f in form.fields}
    vals: dict = {}
    for k, v in re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*=\s*([^\s]+)", clean(text)):
        f = keys.get(k.lower())
        if not f:
            continue
        vals[f.key] = (vals[f.key] + " " + v) if (f.multi and f.key in vals) else v
    return vals


def missing_any(form: Form, values: dict) -> list:
    """[] if the any_of rule is satisfied, else the keys the user must choose from."""
    if not form.any_of:
        return []
    return [] if any(values.get(k) not in (None, "", "0") for k in form.any_of) else list(form.any_of)


def schema(tool: str) -> dict | None:
    f = FORMS.get(tool)
    if not f:
        return None
    return {"desc": f.desc, "example": f.example, "note": f.note, "any_of": list(f.any_of), "fields": [x.to_dict() for x in f.fields]}
