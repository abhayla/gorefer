"""Every styling class a template uses must actually EXIST in the built CSS.

The gap this closes (DA bug 2026-07-16, Settings toggles): a Tailwind utility can go
missing from the compiled CSS **silently**. No build error, no purge warning, the HTML
is byte-identical, so unit tests and curl-based deploy checks all pass — and the
element renders unstyled in the browser. The Settings toggle track used
`bg-ink-300/50`, which Tailwind emitted NOTHING for (it cannot apply an opacity
modifier to a `var()` colour), so an OFF switch had a transparent track.

These tests read the built `static/css/app.css` and assert that the classes the
templates actually reference resolve to a rule. That catches the whole bug class —
purge dropping a class, or a config that silently refuses to emit one — without
needing a headless browser in CI.

A rendered check still has value for true layout bugs (overlap, stacking); this is
the cheap, deterministic 90% that runs on every PR.
"""
import re
from pathlib import Path

import pytest
from django.conf import settings

CSS_PATH = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
TEMPLATE_DIR = Path(settings.BASE_DIR) / "templates"

# Utilities whose absence is invisible in HTML but breaks the UI. Each is a real
# usage in a template; the list is derived below, these are the load-bearing ones we
# name explicitly so a regression names itself in the failure output.
CRITICAL_TOGGLE_CLASSES = [
    "w-11",                        # track width  — collapses to 0 without it
    "h-6",                         # track height
    "w-5",                         # knob
    "h-5",
    "bg-ink-300/50",               # OFF track colour — the bug: silently absent
    "peer-checked:bg-cobalt-600",  # ON track colour
    "peer-checked:translate-x-5",  # knob slide
]


def _css() -> str:
    assert CSS_PATH.exists(), f"built CSS missing at {CSS_PATH} — run `npm run build:css`"
    return CSS_PATH.read_text(encoding="utf-8")


def _escape_for_css(cls: str) -> str:
    """Tailwind escapes special chars in selectors: `bg-ink-300/50` -> `bg-ink-300\\/50`."""
    return re.sub(r"([/:\.\[\]])", r"\\\1", cls)


def _rule_exists(css: str, cls: str) -> bool:
    """True if a rule whose selector is built from this class exists in the CSS.

    Tailwind escapes `/` and `:` in selectors, so `focus:ring-cobalt-500/30` appears as
    `.focus\\:ring-cobalt-500\\/30:focus{...}`. We look for the escaped class name
    preceded by `.` and not immediately followed by another class-name character — so
    `.w-5` does not match `.w-56`, while `.focus\\:ring-x\\/30:focus` still matches.
    """
    esc = _escape_for_css(cls)
    return re.search(r"\." + re.escape(esc) + r"(?![\w-])", css) is not None


@pytest.mark.parametrize("cls", CRITICAL_TOGGLE_CLASSES)
def test_toggle_utility_exists_in_built_css(cls):
    """The Settings toggle's own classes. Named individually so a failure says which
    one vanished rather than 'some class is missing'."""
    css = _css()
    assert _rule_exists(css, cls), (
        f"Tailwind utility {cls!r} is used by the toggle markup but emits NO rule in "
        f"static/css/app.css. The switch will render wrong (collapsed or invisible) "
        f"while the HTML still looks correct to curl and to unit tests. "
        f"If it is an opacity modifier (`/50`), check that the colour token in "
        f"static/css/input.css is an 'R G B' channel triplet and that "
        f"tailwind.config.js wraps it as `rgb(var(--token) / <alpha-value>)`."
    )


def test_no_opacity_modifier_on_themed_colour_is_silently_dropped():
    """The general form of the bug: ANY `<utility>-<themed-colour>/<opacity>` used in a
    template must emit a rule.

    This is the regression guard that would have caught the toggle bug on the PR that
    introduced it — and it covers the other 30-odd usages (bg-cobalt-50/40,
    ring-cobalt-500/30, bg-positive/10, ...) that were equally dead.
    """
    css = _css()
    # Capture any leading variant prefixes too (`focus:`, `focus-within:`, `md:`,
    # `peer-checked:`): Tailwind emits the utility under its PREFIXED selector, so
    # `ring-cobalt-500/30` used only as `focus:ring-cobalt-500/30` legitimately has no
    # bare rule. Checking the unprefixed stem would be a false alarm.
    pattern = re.compile(
        r"((?:[\w-]+:)*"                                          # optional variants
        r"(?:bg|text|border|ring|from|via|to)-"
        r"(?:ink|cobalt|line|bg|positive|pending|danger)(?:-\d+)?/\d+)"
    )
    used: set[str] = set()
    for path in TEMPLATE_DIR.rglob("*.html"):
        for m in pattern.findall(path.read_text(encoding="utf-8")):
            used.add(m)

    assert used, "no opacity-modified themed utilities found — has the palette changed?"

    missing = sorted(cls for cls in used if not _rule_exists(css, cls))
    assert not missing, (
        f"{len(missing)} themed opacity utilities are used in templates but emit NO CSS "
        f"rule: {missing}. They render transparent/unstyled in the browser while every "
        f"HTML-level test still passes. Cause is usually a colour token that is a whole "
        f"colour (`var(--c-x)`) instead of channels — Tailwind cannot inject alpha into "
        f"it and silently emits nothing."
    )


def test_colour_tokens_are_channel_triplets_not_hex():
    """Root-cause guard. If a token reverts to #hex, every `/opacity` utility silently
    dies again — so assert the token FORM, not just the symptom."""
    src = (Path(settings.BASE_DIR) / "static" / "css" / "input.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{(.*?)\}", src, re.S)
    assert root, "could not find :root token block in input.css"

    hex_tokens = re.findall(r"(--c-[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", root.group(1))
    assert not hex_tokens, (
        f"colour tokens must be 'R G B' channel triplets, not #hex — found {hex_tokens}. "
        f"Tailwind composes `bg-x/50` as `rgb(<channels> / .5)`; given a #hex or a "
        f"complete `var()` colour it emits NOTHING for every opacity variant, silently."
    )


def test_direct_token_uses_are_wrapped_in_rgb():
    """A channel triplet is not a colour: `color: var(--c-ink-500)` is invalid and the
    declaration is dropped. Every direct use must be `rgb(var(--c-ink-500))`."""
    src = (Path(settings.BASE_DIR) / "static" / "css" / "input.css").read_text(encoding="utf-8")
    # Strip comments so the explanatory prose doesn't trip the check.
    body = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    # Look only at declarations (prop: value;), not the :root definitions.
    bad = []
    for prop, val in re.findall(r"([\w-]+)\s*:\s*([^;{}]*var\(--c-[^;{}]*);", body):
        if prop.startswith("--"):
            continue  # the token definitions themselves
        if re.search(r"(?<!rgb\()\bvar\(--c-[\w-]+\)", val) and "rgb(" not in val:
            bad.append(f"{prop}: {val.strip()}")
    assert not bad, (
        f"direct token uses must be wrapped in rgb(): {bad}. A bare var(--c-x) is now "
        f"'148 163 184', not a colour — the browser drops the declaration."
    )
