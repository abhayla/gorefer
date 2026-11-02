"""Preview card v2 — the server-rendered 1200x630 link-preview image (owner 2026-11-03).

WHY A RENDERER AND NOT A STATIC FILE
------------------------------------
The v1 card (`static/img/referral-preview-card.png`, built by `scripts/make_preview_card.py`)
is a committed raster: changing one word means a code change and a deploy. v2 draws the card
on request from cascade keys, so the owner can reword it on the Preferences screen (CLAUDE.md
§6d/§6e) and can put the referrer's first name on it ("RAHUL INVITED YOU").

This module is PURE: no DB, no request, no settings lookup. The caller resolves the text
(`apps.referrals.og.v2_card_text`) and passes it in, so the layout is testable in isolation
and the same input always gives the same bytes (which is what makes the cache key and the
`?v=` hash honest).

Layout = the owner-approved reference (`gorefer-ops/review/preview-card-2026-11-03/approved/
FINAL_card.png` + `NAME_card.png`), exact coordinates. The legal band ALWAYS carries the
locked compliance strings the caller passes in; the renderer never invents legal text.

Fonts are committed files (`static/fonts/card/Inter-*.ttf`, SIL OFL) — never system fonts,
so the card looks the same on the laptop, in CI and on the server.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: Bump when the drawing code changes, so every cached PNG and every `?v=` hash rolls over.
DESIGN_VERSION = "card-v2.1"

W, H = 1200, 630
COBALT_TOP = (37, 88, 235)
COBALT_BOT = (67, 112, 245)
BAR = (23, 52, 140)
WHITE = (255, 255, 255)
SOFT = (206, 220, 255)
FAINT = (176, 196, 246)
YELLOW = (255, 214, 10)
NAVY = (16, 32, 88)

X = 78
INNER = W - 2 * X  # 1044
EYEBROW_Y = 44
HEADLINE_Y = 84
HEADLINE_SIZE = 66
HEADLINE_MIN_SIZE = 54
HEADLINE_STEP = 76  # line step at the full 66 px size; scales with the size below it
HEADLINE_MAX_LINES = 2
BADGE_GAP_ABOVE = 38
BADGE_H, BADGE_PAD, BADGE_GAP, BADGE_RADIUS = 112, 30, 18, 22
DOCS_GAP = 20
CTA_H, CTA_RADIUS, CTA_PAD = 66, 33, 28
LEGAL_SIZE, LEGAL_STEP, LEGAL_TOP_PAD = 20, 27, 18
CONTENT_BAND_MARGIN = 8  # minimum clear pixels between content and the legal band

FONT_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts" / "card"
REGULAR = FONT_DIR / "Inter-Regular.ttf"
BOLD = FONT_DIR / "Inter-Bold.ttf"


@dataclass(frozen=True)
class CardText:
    """Every string the card draws. `named` switches the eyebrow to the yellow 34 px style."""

    eyebrow: str
    headline: str
    price_big: str
    price_rest: str
    docs: str
    cta: str
    legal_disclosure: str
    legal_risk: str
    named: bool = False

    def fingerprint(self) -> str:
        """sha256 over every drawn string + the design version — the cache key and `?v=`."""
        parts = [DESIGN_VERSION, "named" if self.named else "generic", self.eyebrow, self.headline,
                 self.price_big, self.price_rest, self.docs, self.cta, self.legal_disclosure,
                 self.legal_risk]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RenderResult:
    png: bytes
    drawn: list[str]


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _bold(size: int) -> ImageFont.FreeTypeFont:
    return _font(str(BOLD), size)


def _regular(size: int) -> ImageFont.FreeTypeFont:
    return _font(str(REGULAR), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Greedy word wrap (same rule as the v1 generator). A single over-long word stays whole."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_one_line(draw, text: str, make_font, size: int, min_size: int, max_w: int):
    """Shrink a one-line string in 2 px steps down to `min_size`; then cut with an ellipsis."""
    font = make_font(size)
    while draw.textlength(text, font=font) > max_w and size > min_size:
        size -= 2
        font = make_font(size)
    if draw.textlength(text, font=font) <= max_w:
        return text, font
    cut = text
    while cut and draw.textlength(cut + "…", font=font) > max_w:
        cut = cut[:-1]
    return cut.rstrip() + "…", font


def _headline_layout(draw, text: str):
    """66 px; if it wraps past two lines, shrink in 4 px steps down to 54 px.

    Still more than two lines at 54 px -> keep two and end the second with an ellipsis
    (operator copy must never push the card into the legal band)."""
    size = HEADLINE_SIZE
    while True:
        font = _bold(size)
        lines = wrap(draw, text, font, INNER)
        if len(lines) <= HEADLINE_MAX_LINES or size <= HEADLINE_MIN_SIZE:
            break
        size -= 4
    if len(lines) > HEADLINE_MAX_LINES:
        rest = " ".join(lines[HEADLINE_MAX_LINES - 1:])
        last, _ = _fit_one_line(draw, rest, lambda _s: font, size, size, INNER)
        lines = lines[: HEADLINE_MAX_LINES - 1] + [last]
    # Any single word wider than the card is cut too.
    lines = [_fit_one_line(draw, ln, lambda _s: font, size, size, INNER)[0] for ln in lines]
    step = round(HEADLINE_STEP * size / HEADLINE_SIZE)
    return lines, font, step


def legal_blocks(draw, disclosure: str, risk: str) -> tuple[list[str], list[str]]:
    font = _regular(LEGAL_SIZE)
    return wrap(draw, disclosure, font, INNER), wrap(draw, risk, font, INNER)


def _one_line(text: str) -> str:
    """Collapse every whitespace run (incl. newlines) to one space: Pillow cannot measure
    multi-line text, and operator copy can carry a newline (review finding, 2026-11-03)."""
    return " ".join((text or "").split())


def render_card(lines: CardText) -> RenderResult:
    """Draw the card. Pure + deterministic: the same `CardText` always gives the same bytes.

    Raises ValueError only if the content would overlap the legal band; callers that serve
    the image must catch it and fall back (see `apps.referrals.og.card_png`)."""
    lines = CardText(
        eyebrow=_one_line(lines.eyebrow), headline=_one_line(lines.headline),
        price_big=_one_line(lines.price_big), price_rest=_one_line(lines.price_rest),
        docs=_one_line(lines.docs), cta=_one_line(lines.cta),
        legal_disclosure=lines.legal_disclosure, legal_risk=lines.legal_risk, named=lines.named,
    )
    img = Image.new("RGB", (W, H), COBALT_TOP)
    d = ImageDraw.Draw(img)

    legal_ap, legal_risk = legal_blocks(d, lines.legal_disclosure, lines.legal_risk)
    legal = legal_ap + legal_risk
    bar_h = 44 + len(legal) * LEGAL_STEP
    top = H - bar_h
    for y in range(top):
        t = y / max(1, top - 1)
        d.line([(0, y), (W, y)], fill=tuple(
            int(COBALT_TOP[i] + (COBALT_BOT[i] - COBALT_TOP[i]) * t) for i in range(3)))
    d.rectangle([0, top, W, H], fill=BAR)

    # Eyebrow — generic: Bold 28 SOFT; named: Bold 34 YELLOW.
    eb_size, eb_fill = (34, YELLOW) if lines.named else (28, SOFT)
    eyebrow, f_eb = _fit_one_line(d, lines.eyebrow, _bold, eb_size, 20, INNER)
    d.text((X, EYEBROW_Y), eyebrow, font=f_eb, fill=eb_fill)

    h1, f_h1, step = _headline_layout(d, lines.headline)
    for i, line in enumerate(h1):
        d.text((X, HEADLINE_Y + i * step), line, font=f_h1, fill=WHITE)

    # CTA pill first, so the badge knows how much room it has to its left.
    by = HEADLINE_Y + len(h1) * step + BADGE_GAP_ABOVE
    cta, f_cta = _fit_one_line(d, lines.cta, _bold, 34, 26, INNER // 3)
    cx2 = W - X
    cx1 = cx2 - d.textlength(cta, font=f_cta) - 2 * CTA_PAD
    cy1 = by + (BADGE_H - CTA_H) // 2

    # Price badge: big price Bold 92 + rest Bold 46, both NAVY on YELLOW.
    price_big, f_big = _fit_one_line(d, lines.price_big, _bold, 92, 60, INNER // 3)
    wb = d.textlength(price_big, font=f_big)
    room = (cx1 - 24) - (X + BADGE_PAD + wb + BADGE_GAP + BADGE_PAD)
    rest, f_rest = _fit_one_line(d, lines.price_rest, _bold, 46, 30, max(0, int(room)))
    wr = d.textlength(rest, font=f_rest)
    d.rounded_rectangle([X, by, X + BADGE_PAD + wb + BADGE_GAP + wr + BADGE_PAD, by + BADGE_H],
                        radius=BADGE_RADIUS, fill=YELLOW)
    d.text((X + BADGE_PAD, by + 2), price_big, font=f_big, fill=NAVY)
    d.text((X + BADGE_PAD + wb + BADGE_GAP, by + 34), rest, font=f_rest, fill=NAVY)

    d.rounded_rectangle([cx1, cy1, cx2, cy1 + CTA_H], radius=CTA_RADIUS, fill=WHITE)
    d.text((cx1 + CTA_PAD, cy1 + 12), cta, font=f_cta, fill=COBALT_TOP)

    docs, f_docs = _fit_one_line(d, lines.docs, _regular, 33, 24, INNER)
    docs_y = by + BADGE_H + DOCS_GAP
    d.text((X, docs_y), docs, font=f_docs, fill=SOFT)
    content_bottom = docs_y + f_docs.getbbox(docs or " ")[3]

    for i, line in enumerate(legal):
        d.text((X, top + LEGAL_TOP_PAD + i * LEGAL_STEP), line, font=_regular(LEGAL_SIZE), fill=FAINT)

    if content_bottom + CONTENT_BAND_MARGIN > top:
        raise ValueError(f"card content ({content_bottom}px) overlaps the legal band ({top}px)")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    # One entry per element, wrapped lines re-joined, so a test can assert a whole string
    # (e.g. the byte-exact AP disclosure) was drawn, not just its fragments.
    drawn = [eyebrow, " ".join(h1), price_big, rest, docs, cta,
             " ".join(legal_ap), " ".join(legal_risk)]
    return RenderResult(png=buf.getvalue(), drawn=drawn)
