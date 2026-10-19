"""Pure text helpers for the Telegram layer (no python-telegram-bot import, so they are unit-testable)."""
from __future__ import annotations
import re

# Buttons of the old project keyboard (TikTok/AI/YouTube/...). Only a WHOLE message made of the label plus
# emoji/punctuation matches. Arabic letters count as \w, so an Arabic sentence that merely contains "AI" never matches.
LEGACY_RE = re.compile(r"(?i)^[\W_]*(tiktok|ai|youtube|shorten|crypto|proxies|my\s*info|about)[\W_]*$")

_TAG = re.compile(r"<(/?)([a-zA-Z]+)[^>]*>")


def _safe_cut(piece: str) -> int:
    """Index where a hard cut does not land inside an HTML tag or an entity."""
    lt, gt = piece.rfind("<"), piece.rfind(">")
    if lt > gt:
        return lt
    amp = piece.rfind("&")
    if amp > piece.rfind(";") and len(piece) - amp < 10:
        return amp
    return len(piece)


def split_html(text: str, limit: int = 3900) -> list[str]:
    """Split Telegram HTML into chunks <= limit on line boundaries, closing open tags at the end of a chunk
    and re-opening them at the start of the next one (so every chunk is valid HTML)."""
    if len(text) <= limit:
        return [text]
    pieces = []
    for line in text.split("\n"):
        while len(line) > limit - 300:
            cut = _safe_cut(line[:limit - 300]) or limit - 300
            pieces.append(line[:cut]); line = line[cut:]
        pieces.append(line)
    chunks, stack, cur, fresh = [], [], "", True
    closers = lambda: "".join(f"</{n}>" for n, _ in reversed(stack))
    for piece in pieces:
        sep = "" if fresh else "\n"
        if not fresh and len(cur) + len(sep) + len(piece) + len(closers()) > limit:
            chunks.append(cur + closers())
            cur, sep = "".join(t for _, t in stack), ""
        cur += sep + piece
        fresh = False
        for m in _TAG.finditer(piece):
            if m.group(1):
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k][0] == m.group(2).lower():
                        del stack[k]; break
            else:
                stack.append((m.group(2).lower(), m.group(0)))
    if cur:
        chunks.append(cur + closers())
    return chunks


