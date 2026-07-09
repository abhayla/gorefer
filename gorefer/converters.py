"""URL path converters.

`ChannelConverter` matches the B1 share-channel path prefix in
`/r/{channel}/{client_id}` (e.g. `/r/wa/RJ4521`). It is deliberately narrow —
1–8 lowercase letters — so it can only ever match a short channel code, never a
Zerodha client_id (4–16 chars, uppercased) and never the literal `continue`
segment (mixed case would not match; and the two-segment /r/X/Y structure is what
selects the channel route, not the code's length). Unknown-but-well-formed codes
still match here and are normalized to "other" downstream (config-driven), so a
typo'd channel never 404s the referral link.
"""
from __future__ import annotations


class ChannelConverter:
    # 1–8 lowercase ASCII letters — covers every configured code (wa, fb, x, li,
    # tg, ig, email, copy) with head-room for future ones, and excludes digits so
    # it can't shadow a numeric-ish client_id.
    regex = r"[a-z]{1,8}"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value
