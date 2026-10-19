/* CivilBot PWA: same engines as the Telegram bot, via /api */
const API = (new URLSearchParams(location.search).get("api") || localStorage.getItem("api") || "").replace(/\/$/, "");
if (new URLSearchParams(location.search).get("api")) localStorage.setItem("api", API);
const $ = (id) => document.getElementById(id);
let CAT = null, current = null, lastRun = null, FORM = null, VALS = {}, SHOW_ADV = false;
const NUM = /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i;
const AR = {"٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9","٫":".","،":","};
const clean = (t) => String(t ?? "").replace(/[٠-٩٫،]/g, (c) => AR[c]).trim();

/* ---------- structured form (same schema as the bot's step-by-step input) ---------- */
function choiceDefault(f) {
  for (const [v, l] of f.options) if (f.default === v || f.default === l) return v;
  return f.options.length ? f.options[0][0] : "";
}
function visible(form, vals) {
  return form.fields.filter((f) => {
    if (!f.when) return true;
    const dep = form.fields.find((x) => x.key === f.when[0]);
    const cur = f.when[0] in vals ? vals[f.when[0]] : (dep ? choiceDefault(dep) : null);
    return f.when[1].includes(cur);
  });
}
function buildText(form, vals) {
  const out = [];
  for (const f of visible(form, vals)) {
    let v = vals[f.key];
    if (v == null && f.kind === "choice") v = choiceDefault(f);
    else if (v == null && f.kind === "num" && f.ask && f.default && NUM.test(f.default)) v = f.default;
    if (v == null || v === "") continue;
    if (f.multi) out.push(...String(v).split(/[\s,]+/).filter(Boolean).map((x) => `${f.key}=${x}`));
    else out.push(`${f.key}=${String(v).replace(/\s+/g, "")}`);
  }
  return out.join(" ");
}
function parseText(form, text) {
  const vals = {}, keys = {};
  for (const f of form.fields) keys[f.key.toLowerCase()] = f;
  for (const m of clean(text).matchAll(/([A-Za-z][A-Za-z0-9]*)\s*=\s*(\S+)/g)) {
    const f = keys[m[1].toLowerCase()];
    if (f) vals[f.key] = f.multi && vals[f.key] ? vals[f.key] + " " + m[2] : m[2];
  }
  return vals;
}
function syncRaw() { $("input").value = buildText(FORM, VALS); }

function renderForm() {
  const box = $("form");
  box.innerHTML = "";
  const fields = visible(FORM, VALS);
  const adv = fields.filter((f) => !f.ask && !f.req);
  for (const f of fields) {
    if (!f.ask && !f.req && !SHOW_ADV) continue;
    const d = document.createElement("div");
    d.className = "fld" + (f.kind === "choice" && f.options.length > 3 ? " wide" : "");
    d.dataset.key = f.key;
    const lab = document.createElement("label");
    lab.innerHTML = `<span></span><code></code>` + (f.req ? `<span class="req">⭐ مطلوب</span>` : `<span class="opt">اختياري</span>`);
    lab.children[0].textContent = f.label; lab.children[1].textContent = f.key;
    d.appendChild(lab);
    if (f.kind === "choice") {
      const seg = document.createElement("div"); seg.className = "seg";
      const cur = f.key in VALS ? VALS[f.key] : choiceDefault(f);
      for (const [v, l] of f.options) {
        const b = document.createElement("button"); b.type = "button"; b.textContent = l;
        if (v === cur) b.className = "on";
        b.onclick = () => { VALS[f.key] = v; syncRaw(); renderForm(); };
        seg.appendChild(b);
      }
      d.appendChild(seg);
    } else {
      const row = document.createElement("div"); row.className = "row";
      const inp = document.createElement("input");
      inp.inputMode = f.kind === "num" ? "decimal" : "text";
      inp.placeholder = f.ex || (f.default && f.default !== "-" ? f.default : "");
      inp.value = VALS[f.key] ?? "";
      inp.oninput = () => {
        const v = clean(inp.value);
        if (v === "") delete VALS[f.key]; else VALS[f.key] = v;
        d.classList.remove("bad"); syncRaw();
      };
      inp.onkeydown = (e) => { if (e.key === "Enter") run(); };
      row.appendChild(inp);
      if (f.unit) { const u = document.createElement("span"); u.className = "unit"; u.textContent = f.unit; row.appendChild(u); }
      d.appendChild(row);
    }
    const hint = document.createElement("div"); hint.className = "hint";
    const dflt = !f.req && f.kind !== "choice" && f.default && f.default !== "-" ? `الافتراضي: ${f.default}` : "";
    hint.textContent = [dflt, f.hint].filter(Boolean).join(" · ");
    d.appendChild(hint);
    box.appendChild(d);
  }
  if (adv.length) {
    const b = document.createElement("button"); b.type = "button"; b.className = "adv";
    b.textContent = SHOW_ADV ? "▴ إخفاء الخيارات المتقدمة" : `▾ خيارات متقدمة (${adv.length})`;
    b.onclick = () => { SHOW_ADV = !SHOW_ADV; renderForm(); };
    box.appendChild(b);
  }
}
function validateForm() {
  let first = null;
  for (const f of visible(FORM, VALS)) {
    const el = $("form").querySelector(`[data-key="${f.key}"]`);
    const v = VALS[f.key];
    let err = "";
    if (f.req && (v == null || v === "")) err = "هذي القيمة مطلوبة";
    else if (v != null && v !== "" && f.kind === "num") {
      const n = v.replace(/,/g, v.includes(".") ? "" : ".");
      if (!NUM.test(n)) err = "لازم رقم، مثل " + (f.ex || "10");
      else if (f.pos && parseFloat(n) <= 0) err = "لازم أكبر من صفر";
      else VALS[f.key] = n;
    }
    if (err && el) { el.classList.add("bad"); el.querySelector(".hint").textContent = "⚠️ " + err; }
    if (err && !first) first = el || true;
  }
  if (!first && FORM.any_of?.length && !FORM.any_of.some((k) => VALS[k] && VALS[k] !== "0")) {
    const names = FORM.any_of.map((k) => FORM.fields.find((f) => f.key === k)?.label || k).slice(0, 3).join(" أو ");
    throw new Error("لازم تدخل قيمة وحدة على الأقل: " + names);
  }
  if (first) { first.scrollIntoView?.({behavior: "smooth", block: "center"}); throw new Error("كمّل الحقول المعلّمة بالأحمر"); }
  syncRaw();
}

async function api(path, body) {
  const r = await fetch(API + path, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
  if (!r.ok) {
    let m = "خطأ " + r.status;
    try { m = (await r.json()).error || m; } catch (e) {}
    throw new Error(m);
  }
  return r;
}

function show(id) {
  for (const s of ["home", "tool", "history"]) $(s).classList.toggle("hidden", s !== id);
  $("back").classList.toggle("hidden", id === "home");
  if (id === "home") { $("title").textContent = "👷‍♂️ CivilBot"; history.replaceState({v: "home"}, ""); }
  window.scrollTo(0, 0);
}

function renderHome(filter = "") {
  const f = filter.trim();
  $("cats").innerHTML = "";
  for (const c of CAT.categories) {
    const tools = c.tools.filter((t) => !f || CAT.tools[t].name.includes(f) || t.includes(f.toLowerCase()) || c.name.includes(f));
    if (!tools.length) continue;
    const div = document.createElement("div");
    div.className = "cat";
    div.innerHTML = `<h2>${c.name}</h2><div class="grid"></div>`;
    for (const t of tools) {
      const b = document.createElement("button");
      b.className = "t";
      b.textContent = CAT.tools[t].name;
      b.onclick = () => openTool(t);
      div.querySelector(".grid").appendChild(b);
    }
    $("cats").appendChild(div);
  }
}

function openTool(t, text) {
  current = t;
  const m = CAT.tools[t];
  $("title").textContent = m.name;
  $("help").innerHTML = m.help;
  $("desc").textContent = m.desc || "";
  FORM = m.form || null; SHOW_ADV = false;
  $("form").classList.toggle("hidden", !FORM || m.photo);
  $("rawBox").open = !FORM;
  $("rawSum").textContent = FORM ? "✍️ أو اكتب المدخلات بسطر واحد (متقدم)" : "✍️ المدخلات";
  $("examples").innerHTML = "";
  for (const ex of m.examples) {
    const c = document.createElement("span");
    c.className = "chip"; c.textContent = ex; c.title = ex;
    c.onclick = () => { $("input").value = ex.replace(/^\/\w+\s*/, ""); };
    $("examples").appendChild(c);
  }
  const useText = (t) => { $("input").value = t; if (FORM) { VALS = parseText(FORM, t); renderForm(); } };
  $("examples").querySelectorAll(".chip").forEach((c) => c.onclick = () => useText(c.title.replace(/^\/\w+\s*/, "")));
  $("help").querySelectorAll("code").forEach((c) => c.onclick = () => useText(c.textContent.replace(/^\/\w+\s*/, "")));
  $("textWrap").classList.toggle("hidden", m.photo);
  $("photoWrap").classList.toggle("hidden", !m.photo);
  $("examples").classList.toggle("hidden", m.photo);
  $("input").value = text ?? (FORM ? "" : (m.examples[0] || "").replace(/^\/\w+\s*/, ""));
  if (FORM) { VALS = text ? parseText(FORM, text) : {}; renderForm(); syncRaw(); }
  $("result").innerHTML = ""; $("status").textContent = "";
  history.pushState({v: "tool", t}, "");
  show("tool");
}

function b64Blob(b64, type) {
  const bin = atob(b64), arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], {type});
}

function renderResult(d) {
  const R = $("result");
  R.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className = "res";
  for (const [name, b64] of Object.entries(d.images || {})) {
    const img = document.createElement("img");
    img.src = "data:image/png;base64," + b64; img.alt = name;
    img.onclick = () => window.open(URL.createObjectURL(b64Blob(b64, "image/png")));
    wrap.appendChild(img);
  }
  const acts = document.createElement("div"); acts.className = "actions";
  for (const [fn, b64] of Object.entries(d.files || {})) {
    const a = document.createElement("a");
    const type = fn.endsWith(".gif") ? "image/gif" : "application/octet-stream";
    a.href = URL.createObjectURL(b64Blob(b64, type)); a.download = fn;
    a.textContent = (fn.endsWith(".dxf") ? "📐 " : fn.endsWith(".xlsx") ? "📊 " : "📎 ") + fn;
    acts.appendChild(a);
  }
  if (current && !CAT.tools[current].photo && current !== "units") {
    const p = document.createElement("button");
    p.textContent = "📄 مذكرة PDF";
    p.onclick = async () => {
      p.disabled = true; p.textContent = "⏳ جاري التجهيز…";
      try {
        const r = await api("/api/pdf", {tool: current, text: lastRun});
        const a = document.createElement("a");
        a.href = URL.createObjectURL(await r.blob()); a.download = `CivilBot_${current}.pdf`; a.click();
        p.textContent = "📄 مذكرة PDF";
      } catch (e) { p.textContent = "⚠️ " + e.message; }
      p.disabled = false;
    };
    acts.appendChild(p);
  }
  if (navigator.share) {
    const s = document.createElement("button");
    s.textContent = "📤 مشاركة";
    s.onclick = async () => {
      const first = Object.values(d.images || {})[0];
      const files = first ? [new File([b64Blob(first, "image/png")], "civilbot.png", {type: "image/png"})] : [];
      try { await navigator.share({title: d.title, text: d.title, files: navigator.canShare?.({files}) ? files : undefined}); } catch (e) {}
    };
    acts.appendChild(s);
  }
  const steps = document.createElement("div"); steps.className = "steps";
  steps.innerHTML = d.summary_html + (d.equation ? `<br><br>🧮 <code>${d.equation}</code>` : "");
  R.append(wrap, acts, steps);
}

async function run() {
  const btn = $("run"); btn.disabled = true;
  $("status").className = ""; $("status").textContent = "⏳ جاري الحساب…";
  const t0 = performance.now();
  try {
    let d;
    if (CAT.tools[current].photo) {
      const f = $("photo").files[0];
      if (!f) throw new Error("اختر صورة أولاً");
      const b64 = await shrink(f);
      d = await (await api("/api/photo", {kind: current, image: b64, caption: $("caption").value})).json();
    } else {
      if (FORM && !$("rawBox").open) validateForm();
      lastRun = $("input").value.trim();
      if (!lastRun) throw new Error("اكتب المدخلات أو اختر مثال");
      d = await (await api("/api/run", {tool: current, text: lastRun})).json();
      saveHist(current, lastRun, d.title);
    }
    renderResult(d);
    $("status").textContent = `✅ ${((performance.now() - t0) / 1000).toFixed(1)} ث`;
    $("result").scrollIntoView({behavior: "smooth"});
  } catch (e) {
    $("status").className = "err";
    $("status").textContent = "⚠️ " + (navigator.onLine ? e.message : "لا يوجد اتصال بالإنترنت");
  }
  btn.disabled = false;
}

function shrink(file, max = 1600) {
  return new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = img.width * k; c.height = img.height * k;
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      ok(c.toDataURL("image/jpeg", 0.88).split(",")[1]);
    };
    img.onerror = bad;
    img.src = URL.createObjectURL(file);
  });
}

function saveHist(t, text, title) {
  const h = JSON.parse(localStorage.getItem("hist") || "[]");
  h.unshift({t, text, title, at: Date.now()});
  localStorage.setItem("hist", JSON.stringify(h.slice(0, 50)));
}

function showHist() {
  const h = JSON.parse(localStorage.getItem("hist") || "[]");
  $("title").textContent = "🕘 السجل";
  $("histList").innerHTML = h.length ? "" : `<p class="note">لا يوجد حسابات بعد</p>`;
  for (const x of h) {
    const d = document.createElement("div"); d.className = "h";
    d.innerHTML = `<b></b><small></small>`;
    d.querySelector("b").textContent = (CAT?.tools[x.t]?.name || x.t) + " · " + new Date(x.at).toLocaleDateString("ar");
    d.querySelector("small").textContent = x.text;
    d.onclick = () => openTool(x.t, x.text);
    $("histList").appendChild(d);
  }
  history.pushState({v: "history"}, "");
  show("history");
}

$("photo").onchange = () => {
  const f = $("photo").files[0];
  if (f) { $("preview").src = URL.createObjectURL(f); $("preview").classList.remove("hidden"); }
};
$("run").onclick = run;
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
$("input").addEventListener("input", () => { if (FORM) { VALS = parseText(FORM, $("input").value); renderForm(); } });
$("search").oninput = (e) => renderHome(e.target.value);
$("back").onclick = () => history.back();
$("histBtn").onclick = showHist;
window.onpopstate = (e) => { if (!e.state || e.state.v === "home") show("home"); };
const net = () => $("offline").classList.toggle("hidden", navigator.onLine);
addEventListener("online", net); addEventListener("offline", net); net();

(async () => {
  try {
    CAT = await (await api("/api/tools")).json();
    localStorage.setItem("catalog", JSON.stringify(CAT));
  } catch (e) {
    CAT = JSON.parse(localStorage.getItem("catalog") || "null");
    if (!CAT) { $("cats").innerHTML = `<p class="err">تعذر الاتصال بالسيرفر</p>`; return; }
  }
  renderHome();
  const t = new URLSearchParams(location.search).get("tool");
  if (t && CAT.tools[t]) openTool(t);
})();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
