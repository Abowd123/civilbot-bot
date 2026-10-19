"""Regression tests for the v-audit fixes (2026-10-19)."""
import os, re, tempfile, threading, time, urllib.request, urllib.error
os.environ.setdefault("CIVILBOT_DB", os.path.join(tempfile.mkdtemp(), "fx.sqlite3"))
from civilbot.bot.textutil import LEGACY_RE, split_html
from civilbot.bot import storage


def test_legacy_buttons_do_not_eat_arabic_messages():
    for label in ("🤖 AI", "About", "📱 TikTok", "My Info", "ai"):
        assert LEGACY_RE.search(label), label
    for text in ("البوت ممتاز بس ميزة AI بطيئة", "محلل الشروخ ai ما يشتغل", "about the slab design", "L=6 w=10 ai"):
        assert not LEGACY_RE.search(text), text


def _balanced(chunk):
    stack = []
    for m in re.finditer(r"<(/?)([a-z]+)[^>]*>", chunk):
        if m.group(1):
            assert stack and stack[-1] == m.group(2), chunk[:200]
            stack.pop()
        else:
            stack.append(m.group(2))
    return not stack and not re.search(r"<[^>]*$", chunk)


def test_split_html_keeps_every_chunk_valid():
    line = "<b>{i}. عنوان</b>\n<code>M = w·L²/8 &amp; V = wL/2</code>\n➜ <b>نتيجة {i}</b>"
    big = "<b>العنوان</b>\n" + "\n".join(line.format(i=i) for i in range(400))
    big += "\n<code>" + "x" * 9000 + "</code>"            # one huge line inside a tag
    chunks = split_html(big, 3900)
    assert len(chunks) > 3
    for ch in chunks:
        assert len(ch) <= 3900 and _balanced(ch)
    assert split_html("short") == ["short"]


def test_input_errors_do_not_burn_quota():
    uid = 777001
    before = storage.used_today(uid)
    storage.log(uid, "beam", True, 10)
    storage.log(uid, "beam", False, 10, counts=False)   # typo / InputError
    storage.log(uid, "beam", False, 10)                  # real failure still counts
    assert storage.used_today(uid) == before + 2


def test_schema_created_once_and_migrates_old_db():
    import sqlite3
    old = os.path.join(tempfile.mkdtemp(), "old.sqlite3")
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE usage(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, tool TEXT, ok INTEGER, ms INTEGER, at TEXT)")
    con.execute("INSERT INTO usage(uid,tool,ok,ms,at) VALUES(1,'beam',1,5,'2099-01-01')")
    con.commit(); con.close()
    saved = storage.DB
    storage.DB = old
    try:
        storage.log(1, "beam", True, 5)
        assert storage.used_today(1) == 2                    # old rows default to counts=1
        assert old in storage._READY
    finally:
        storage.DB = saved


def test_api_serves_miniapp_pages_and_blocks_traversal():
    from http.server import ThreadingHTTPServer
    from civilbot import api
    srv = ThreadingHTTPServer(("127.0.0.1", 0), api.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        for path in ("/editor.html", "/webapp/editor.html", "/viewer3d.html", "/webapp/viewer3d.html"):
            body = urllib.request.urlopen(base + path).read().decode()
            assert "telegram-web-app.js" in body and "CivilBot" in body, path
        index = urllib.request.urlopen(base + "/").read()
        assert urllib.request.urlopen(base + "/../../etc/passwd").read() == index
    finally:
        srv.shutdown()


def test_busy_guard_and_pool_recycle():
    try:
        from civilbot.bot import launch as L
    except ImportError:          # python-telegram-bot not installed
        return
    import asyncio
    L.CURRENT_UID.set(424242)
    L.INFLIGHT.add(424242)
    try:
        try:
            asyncio.run(L.offload("tool", "beam", "L=6 type=ss w=10"))
            raise AssertionError("expected Busy")
        except L.Busy:
            pass
    finally:
        L.INFLIGHT.discard(424242)
    assert asyncio.run(L.offload("tool", "beam", "L=6 type=ss w=10")) is not None
    assert 424242 not in L.INFLIGHT
