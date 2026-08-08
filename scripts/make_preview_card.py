"""Render the PIFS referral link-preview card (1200x630 Open Graph).

WHY THIS IS A GENERATOR AND NOT A HAND-MADE IMAGE
-------------------------------------------------
The card is the highest-volume surface the compliance strings ever appear on: every
referrer forwards it to every friend. Text baked into a raster cannot be corrected by a
config change, so a hand-drawn card is the one place `MARKET_RISK_WARNING` and
`AP_DISCLOSURE_BLOCK` can silently drift out of date (2026-08-08 compliance review: the
first hand-made card truncated the statutory warning by 60 characters and omitted the
broker's SEBI registration entirely).

So the card is GENERATED from `gorefer.settings` — the same byte-exact constants every
page renders — and every string it draws is also written to a sidecar
`static/img/referral-preview-card.txt`. `tests/test_preview_card_compliance.py` asserts
that sidecar still matches settings, so editing a compliance string without regenerating
the card FAILS CI instead of shipping a stale legal line.

Run after any change to the compliance constants or the card design:

    python scripts/make_preview_card.py     # needs Pillow (dev-only, not a runtime dep)

Design constraints (CLAUDE.md §4, ADR-014): PIFS-branded, no partner logo or trademark,
must not resemble the partner's own assets. The broker is NAMED in the disclosure line
because an Authorised Person must disclose its principal — naming is disclosure, not
impersonation; a card that names no broker implies PIFS opens the accounts itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import django
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gorefer.settings")
django.setup()

from django.conf import settings  # noqa: E402

W, H = 1200, 630
COBALT_TOP = (37, 88, 235)
COBALT_BOT = (67, 112, 245)
BAR = (23, 52, 140)
WHITE = (255, 255, 255)
SOFT = (206, 220, 255)
FAINT = (176, 196, 246)

BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
REG = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

HEADLINE = "Open a demat & trading account"
EYEBROW = "YOU'VE BEEN PERSONALLY REFERRED"
SUBLINE = "Guided end to end by PIFS. PIFS charges you nothing for the help."


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
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


def build() -> tuple[Image.Image, list[str]]:
    img = Image.new("RGB", (W, H), COBALT_TOP)
    d = ImageDraw.Draw(img)

    f_eyebrow = _font(BOLD, 29)
    f_h1 = _font(BOLD, 72)
    f_sub = _font(REG, 33)
    f_legal = _font(REG, 20)
    f_legalb = _font(BOLD, 22)

    x, inner = 78, W - 156
    legal_lines = _wrap(d, settings.AP_DISCLOSURE_BLOCK, f_legal, inner)
    legal_lines += _wrap(d, settings.MARKET_RISK_WARNING, f_legal, inner)
    bar_h = 44 + len(legal_lines) * 27

    for y in range(H - bar_h):
        t = y / max(1, H - bar_h - 1)
        d.line([(0, y), (W, y)], fill=tuple(
            int(COBALT_TOP[i] + (COBALT_BOT[i] - COBALT_TOP[i]) * t) for i in range(3)))
    d.rectangle([0, H - bar_h, W, H], fill=BAR)

    d.text((x, 74), EYEBROW, font=f_eyebrow, fill=SOFT)
    for i, line in enumerate(_wrap(d, HEADLINE, f_h1, inner)):
        d.text((x, 132 + i * 84), line, font=f_h1, fill=WHITE)
    for i, line in enumerate(_wrap(d, SUBLINE, f_sub, inner)):
        d.text((x, 318 + i * 44), line, font=f_sub, fill=SOFT)

    d.text((x, H - bar_h + 16), "PIFS", font=f_legalb, fill=WHITE)
    for i, line in enumerate(legal_lines):
        d.text((x + 62, H - bar_h + 18 + i * 27), line, font=f_legal, fill=FAINT)

    return img, [EYEBROW, HEADLINE, SUBLINE, settings.AP_DISCLOSURE_BLOCK,
                 settings.MARKET_RISK_WARNING]


def main() -> int:
    img, strings = build()
    png = ROOT / "static" / "img" / "referral-preview-card.png"
    img.save(png, "PNG", optimize=True)
    (ROOT / "static" / "img" / "referral-preview-card.txt").write_text(
        "\n".join(strings) + "\n", encoding="utf-8")
    print(f"wrote {png} {img.size} + sidecar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
