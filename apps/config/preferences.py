"""Preference config keys — the tenant-tier settings the Preferences screen owns.

One home for the key NAMES + their central defaults (config-over-code: no scattered
string literals in views/templates). Each key is a plain (unlocked) cascade key, so a
tenant override at the GLOBAL tier wins over the central default (ADR-022, ADR-034).
Compliance-locked keys (the incentive claim, AP disclosure block, NSE AP no.) are NOT
here — they resolve from central only and the screen never writes them.

`LANDING_MODE` is set THROUGH the Preferences screen, never a backend override
(ADR-034). The ADR-032 disclosure coupling (`direct` only when a live /d/{slug}
exists) is enforced at the screen (see apps/referrals/landing_mode.has_live_disclosure_page).
"""
from __future__ import annotations

from django.conf import settings

from .cascade import resolve

# --- Key names (single source; referenced everywhere by constant, never literal) ---
LANDING_MODE = "landing_mode"
SHARE_SHOW_REWARD = "share_show_reward"
REFERRER_REWARD_CLAIM = "referrer_reward_claim"
SUPPORT_HELPLINE_PHONE = "support_helpline_phone"
WATI_BUSINESS_NUMBER = "wati_business_number"
SHARE_CHANNELS_ALLOWLIST = "share_channels_allowlist"
ENABLE_ASSISTED_REFERRAL = "enable_assisted_referral"

# --- Share/redirect recovery page (T-122) -------------------------------------------
# GET /share/{channel}/ (missing client_id), GET /r/, GET /r — the soft-landing page
# for a link that fell out of its client_id (Zoho field-mapping bug sent WhatsApp
# template URL buttons with a blank {{client_id}}). Copy + the wa.me pre-fill are
# cascade keys (rail E-6 / §6d) so the owner can reword the recovery message without a
# deploy; the WATI business NUMBER is not duplicated here — it reuses WATI_BUSINESS_NUMBER
# above. Defaults are the shipped literals, so an unseeded database renders identically.
SHARE_RECOVERY_HEADLINE = "share_recovery_headline"
SHARE_RECOVERY_HEADLINE_DEFAULT = "We couldn't load your personal referral link"

SHARE_RECOVERY_BODY = "share_recovery_body"
SHARE_RECOVERY_BODY_DEFAULT = (
    "The link you followed is missing a piece. Message us on WhatsApp and we'll send "
    "you your referral link right away."
)

SHARE_RECOVERY_BUTTON_LABEL = "share_recovery_button_label"
SHARE_RECOVERY_BUTTON_LABEL_DEFAULT = "Message us on WhatsApp"

SHARE_RECOVERY_PREFILL = "share_recovery_prefill_text"
SHARE_RECOVERY_PREFILL_DEFAULT = "Hi, I need my referral link"

# --- Records magic link (T-051; behind ENABLE_RECORDS_LINK) ------------------------
# How long a WhatsApp [Referral Records] link stays usable. A cascade key, not a
# literal (rail E-6 / §6d): shortening the window has to take effect on links ALREADY
# in people's chat history, which a code constant could never do without a re-send.
# Not on the Preferences screen yet — the surface it governs ships flag-OFF.
RECORDS_LINK_TTL_DAYS = "records_link_ttl_days"
RECORDS_LINK_TTL_DAYS_DEFAULT = 90

# --- Token mint (T-054) -----------------------------------------------------------
# `record_date` in a mint response is pasted straight into a message body ("as per our
# records dated …"), so the strftime pattern that renders it is a cascade key, not a
# literal (rail E-6 / §6d): the owner can switch "07 Aug 2026" to "07/08/2026" without
# a deploy. A pattern strftime rejects falls back to this default (api/records_tokens).
RECORDS_MINT_DATE_FORMAT = "records_mint_date_format"
RECORDS_MINT_DATE_FORMAT_DEFAULT = "%d %b %Y"

# --- Records-link operator send (T-057; `send_records_links` management command) --
# The approved UTILITY template the command sends — a cascade key (rail E-6 / §6d) so
# a re-cut template name swaps in with no deploy, exactly like `notify_template_name`.
RECORDS_LINK_TEMPLATE_EN = "records_link_template_en"
RECORDS_LINK_TEMPLATE_EN_DEFAULT = "gr_platform_gorefer_refrecord_en_2026_08_07"

# Per-run send cap. A literal here would mean a bad `--client-ids` list could only be
# bounded by a deploy; a cascade key lets the owner tighten/loosen it without one.
RECORDS_LINK_SEND_MAX_PER_RUN = "records_link_send_max_per_run"
RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT = 50

# Minimum days between two records-link sends to the same client_id — the anti-spam
# floor mirroring `followup_min_gap_minutes`'s reasoning at a slower cadence.
RECORDS_LINK_SEND_MIN_GAP_DAYS = "records_link_send_min_gap_days"
RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT = 7

# --- Referral invite per-recipient send (T-073; `send_invite_links` command) -------
# The invite template carries a SERVER-COMPUTED {{token}} behind its share-hub URL
# button, so it can only be sent by a sender that mints one PER RECIPIENT — a
# dashboard broadcast would fill that variable from a contact attribute nobody sets
# and ship a dead `…/hub/` link to every recipient. Three cascade keys (rail E-6 /
# §6d), matching the records-link family's shape: template name, per-run cap, and
# the anti-spam min-gap. The template named here is a DRAFT at Meta today, and the
# sender refuses to send an unapproved template — this ships as CAPABILITY only, it
# fires no blast.
INVITE_TEMPLATE_EN = "invite_template_en"
INVITE_TEMPLATE_EN_DEFAULT = "gr_brokers_zerodha_referandearn_invite_en_2026_08_10"

INVITE_SEND_MAX_PER_RUN = "invite_send_max_per_run"
INVITE_SEND_MAX_PER_RUN_DEFAULT = 50

INVITE_SEND_MIN_GAP_DAYS = "invite_send_min_gap_days"
INVITE_SEND_MIN_GAP_DAYS_DEFAULT = 30

# --- Referrer conversion congrats (T-058; P-01/Gap 5) ------------------------------
# The one-time "your referral just opened their account" notification to the CREDITED
# referrer, fired once per conversion from the Zoho ingest path
# (apps.integrations.congrats). Two cascade keys (rail E-6 / §6d): the in-session copy
# (used when the referrer's own 24h WhatsApp window is open) and the WhatsApp template
# name (used otherwise). The template default is EMPTY — this feature ships DORMANT
# on the template leg until the owner configures an approved name; template
# creation/submission is NOT this task (owner ruling 2026-08-08, CLAUDE.md). The body
# never names the prospect (generic descriptor only, §6.1 precedent) and states no
# reward amount (Gap 4: GoRefer never computes rewards).
REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN = "referrer_conversion_congrats_template_en"
REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN_DEFAULT = ""

REFERRER_CONVERSION_CONGRATS_BODY_EN = "referrer_conversion_congrats_body_en"
REFERRER_CONVERSION_CONGRATS_BODY_EN_DEFAULT = (
    "Great news {name}! A referral of yours just completed their account opening. "
    "Thank you for referring — view your records anytime from your GoRefer link."
)

# --- Referral share hub (T-053; behind ENABLE_SHARE_HUB) ---------------------------
# Every word this page says, and the brand image its link preview uses, is a cascade
# key rather than a template literal (rail E-6 / §6d). Two reasons, both concrete:
#   * the shipped copy below is a PLACEHOLDER pending the owner's compliance review —
#     it has to be replaceable without a deploy, and it will be replaced;
#   * the incentive claim is NOT here. It resolves from REFERRER_REWARD_CLAIM (whose
#     central default is flags.REFERRAL_INCENTIVE_CLAIM), so the "10%" wording stays
#     in the ONE editable field CLAUDE.md §4 requires and is never restated.
SHARE_HUB_HEADLINE = "share_hub_headline"
SHARE_HUB_INTRO = "share_hub_intro"
SHARE_HUB_BENEFITS_HEADING = "share_hub_benefits_heading"
SHARE_HUB_BENEFITS = "share_hub_benefits"              # JSON list of bullet strings
SHARE_HUB_GUIDANCE_HEADING = "share_hub_guidance_heading"
SHARE_HUB_GUIDANCE = "share_hub_guidance"              # JSON list of bullet strings
SHARE_HUB_OG_IMAGE_URL = "share_hub_og_image_url"

# The PIFS attribution line under the partner header (T-055, owner review 2026-08-08).
# The PARTNER NAME itself is never here — it comes from the Partner DB record via the
# identity (renaming the row must change the header with no deploy, ADR-014/§4). This
# key only carries the fixed PIFS-attribution wording, which is config per rail E-6.
SHARE_HUB_PARTNER_ATTRIBUTION = "share_hub_partner_attribution"
SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT = "via PIFS - Authorised Person"

#: Static brand card for the hub's link preview. A committed placeholder asset — an
#: operator swaps in the owner-approved image by pointing this key at a new static
#: path or an absolute CDN URL, with no deploy (§6d).
SHARE_HUB_OG_IMAGE_DEFAULT = "img/referral-preview-card.png"

SHARE_HUB_HEADLINE_DEFAULT = "Your referral link is ready"
SHARE_HUB_INTRO_DEFAULT = (
    "Send it to one person today. When someone opens an account through this link, "
    "the referral is recorded against your Client ID."
)
SHARE_HUB_BENEFITS_HEADING_DEFAULT = "What you get"
SHARE_HUB_BENEFITS_DEFAULT = [
    "Any reward comes from the broker's own referral programme, on their terms. We "
    "record the referral against your Client ID and pass it on — we never calculate, "
    "hold or add to the amount.",
    "Every referral is tracked against your Client ID automatically. No forms, no "
    "follow-up calls, nothing to remember.",
    "Your friend is guided through account opening end to end by PIFS. PIFS charges "
    "your friend nothing for this help; PIFS is paid by the broker as its Authorised "
    "Person. Account and brokerage charges are the broker's own.",
    "Open your record any time to see exactly where each person has reached.",
]
SHARE_HUB_GUIDANCE_HEADING_DEFAULT = "How to share so it actually works"
SHARE_HUB_GUIDANCE_DEFAULT = [
    "One direct message beats ten group posts. Send it to a person, not to a crowd.",
    "Say why YOU use it in your own words — your own experience of opening and using "
    "the account. Do not promise returns or advise anyone on what to invest in; leave "
    "that to them and their own research.",
    "Start with family and friends who have already asked you about investing.",
    "If someone shows interest but goes quiet, one short reminder the next day helps "
    "far more than sending the link again.",
]

# --- Share hub HI twins (T-061) -----------------------------------------------------
# `apps.config.i18n.bi_text`/`bi_lines` resolve `{key}_hi` beside the EN key above and
# fall back to EN whenever the HI value is unset/blank — a missing HI row can never
# blank the page. Drafts below are a faithful translation of the PR #124
# compliance-reviewed EN copy (owner review pending, CLAUDE.md pre-made decision #3;
# copy is config, so a wording edit needs no deploy).
SHARE_HUB_HEADLINE_HI_DEFAULT = "आपका रेफ़रल लिंक तैयार है"
SHARE_HUB_INTRO_HI_DEFAULT = (
    "आज ही किसी एक व्यक्ति को यह भेजें। जब कोई इस लिंक से खाता खोलता है, तो रेफ़रल आपकी "
    "क्लाइंट आईडी पर दर्ज होता है।"
)
SHARE_HUB_BENEFITS_HEADING_HI_DEFAULT = "आपको क्या मिलता है"
SHARE_HUB_BENEFITS_HI_DEFAULT = [
    "कोई भी रिवॉर्ड ब्रोकर के अपने रेफ़रल प्रोग्राम से, उन्हीं की शर्तों पर आता है। हम रेफ़रल "
    "को आपकी क्लाइंट आईडी पर दर्ज कर आगे पहुंचाते हैं — हम कभी राशि की गणना, होल्ड या उसमें "
    "जोड़ नहीं करते।",
    "हर रेफ़रल आपकी क्लाइंट आईडी पर अपने-आप ट्रैक होता है। कोई फ़ॉर्म नहीं, कोई फॉलो-अप कॉल "
    "नहीं, याद रखने को कुछ नहीं।",
    "आपके मित्र को खाता खोलने की पूरी प्रक्रिया में PIFS द्वारा शुरू से अंत तक मदद दी जाती है। "
    "PIFS आपके मित्र से इसके लिए कोई शुल्क नहीं लेता; PIFS को ब्रोकर द्वारा उसके ऑथराइज़्ड "
    "पर्सन के रूप में भुगतान किया जाता है। खाता और ब्रोकरेज शुल्क ब्रोकर के अपने हैं।",
    "किसी भी समय अपना रिकॉर्ड खोलकर देखें कि हर व्यक्ति कहां तक पहुंचा है।",
]
SHARE_HUB_GUIDANCE_HEADING_HI_DEFAULT = "असरदार तरीके से कैसे शेयर करें"
SHARE_HUB_GUIDANCE_HI_DEFAULT = [
    "दस ग्रुप पोस्ट से बेहतर है एक सीधा मैसेज। इसे किसी व्यक्ति को भेजें, भीड़ को नहीं।",
    "अपने शब्दों में बताएं कि आप इसे क्यों इस्तेमाल करते हैं — खाता खोलने और इस्तेमाल करने का "
    "अपना अनुभव साझा करें। किसी को रिटर्न का वादा न करें या निवेश की सलाह न दें; यह उन पर और "
    "उनकी अपनी रिसर्च पर छोड़ दें।",
    "उन परिवार और दोस्तों से शुरुआत करें जिन्होंने पहले ही आपसे निवेश के बारे में पूछा है।",
    "अगर कोई दिलचस्पी दिखाकर चुप हो जाए, तो अगले दिन एक छोटा-सा रिमाइंडर लिंक दोबारा भेजने "
    "से कहीं ज़्यादा असरदार होता है।",
]
SHARE_HUB_PARTNER_ATTRIBUTION_HI_DEFAULT = "PIFS - ऑथराइज़्ड पर्सन के माध्यम से"

# HI cascade key names (`{key}_hi`, resolved by apps.config.i18n against the EN key
# above). Named explicitly rather than string-built at every call site.
SHARE_HUB_HEADLINE_HI = "share_hub_headline_hi"
SHARE_HUB_INTRO_HI = "share_hub_intro_hi"
SHARE_HUB_BENEFITS_HEADING_HI = "share_hub_benefits_heading_hi"
SHARE_HUB_BENEFITS_HI = "share_hub_benefits_hi"
SHARE_HUB_GUIDANCE_HEADING_HI = "share_hub_guidance_heading_hi"
SHARE_HUB_GUIDANCE_HI = "share_hub_guidance_hi"
SHARE_HUB_PARTNER_ATTRIBUTION_HI = "share_hub_partner_attribution_hi"

# --- Records page (T-051) + share-hub chrome bilingual copy (T-061) ----------------
# The `/rr/{token}` page copy (RECORDS_CONFIG in apps.accounts.records) and the
# `/hub/{token}` chrome labels (HUB_CHROME in apps.accounts.hub) were plain module
# dicts — page furniture, not owner-editable via the Preferences screen, but still
# text a Hindi-first referrer reads. Rail E-6 / §6d already treats SHARE_HUB_* the
# same way; these keys extend the identical cascade-key pattern to the remaining
# strings on both pages so every one of them gets an EN default + an `_hi` twin.
RECORDS_TITLE = "records_title"
RECORDS_NOT_ON_FILE = "records_not_on_file"
RECORDS_MASKED_NOTE = "records_masked_note"
RECORDS_LOGIN_CTA = "records_login_cta"
RECORDS_EXPIRED_TITLE = "records_expired_title"
RECORDS_EXPIRED_BODY = "records_expired_body"
RECORDS_EMPTY = "records_empty"
RECORDS_HUB_CTA = "records_hub_cta"
RECORDS_STAT_REFERRED = "records_stat_referred"
RECORDS_STAT_CONVERTED = "records_stat_converted"
RECORDS_STAT_PENDING = "records_stat_pending"
RECORDS_COL_NAME = "records_col_name"
RECORDS_COL_MOBILE = "records_col_mobile"
RECORDS_COL_STATUS = "records_col_status"
RECORDS_COL_REFERRED = "records_col_referred"
RECORDS_STATUS_OPENED = "records_status_opened"
RECORDS_STATUS_IN_PROGRESS = "records_status_in_progress"

RECORDS_TITLE_DEFAULT = "Your referral records"
RECORDS_NOT_ON_FILE_DEFAULT = "— not on file —"
RECORDS_MASKED_NOTE_DEFAULT = (
    "Names and numbers are partly hidden on this link because it can be forwarded. "
    "Log in to see full details."
)
RECORDS_LOGIN_CTA_DEFAULT = "Log in for full details"
RECORDS_EXPIRED_TITLE_DEFAULT = "This link has expired"
RECORDS_EXPIRED_BODY_DEFAULT = "Referral-record links stop working after a while. Log in to see your records."
RECORDS_EMPTY_DEFAULT = "No referrals recorded yet."
RECORDS_HUB_CTA_DEFAULT = "Share your referral link"
RECORDS_STAT_REFERRED_DEFAULT = "Referred"
RECORDS_STAT_CONVERTED_DEFAULT = "Accounts opened"
RECORDS_STAT_PENDING_DEFAULT = "In progress"
RECORDS_COL_NAME_DEFAULT = "Name"
RECORDS_COL_MOBILE_DEFAULT = "Mobile"
RECORDS_COL_STATUS_DEFAULT = "Status"
RECORDS_COL_REFERRED_DEFAULT = "Referred"
RECORDS_STATUS_OPENED_DEFAULT = "Account opened"
RECORDS_STATUS_IN_PROGRESS_DEFAULT = "In progress"

RECORDS_TITLE_HI = "records_title_hi"
RECORDS_NOT_ON_FILE_HI = "records_not_on_file_hi"
RECORDS_MASKED_NOTE_HI = "records_masked_note_hi"
RECORDS_LOGIN_CTA_HI = "records_login_cta_hi"
RECORDS_EXPIRED_TITLE_HI = "records_expired_title_hi"
RECORDS_EXPIRED_BODY_HI = "records_expired_body_hi"
RECORDS_EMPTY_HI = "records_empty_hi"
RECORDS_HUB_CTA_HI = "records_hub_cta_hi"
RECORDS_STAT_REFERRED_HI = "records_stat_referred_hi"
RECORDS_STAT_CONVERTED_HI = "records_stat_converted_hi"
RECORDS_STAT_PENDING_HI = "records_stat_pending_hi"
RECORDS_COL_NAME_HI = "records_col_name_hi"
RECORDS_COL_MOBILE_HI = "records_col_mobile_hi"
RECORDS_COL_STATUS_HI = "records_col_status_hi"
RECORDS_COL_REFERRED_HI = "records_col_referred_hi"
RECORDS_STATUS_OPENED_HI = "records_status_opened_hi"
RECORDS_STATUS_IN_PROGRESS_HI = "records_status_in_progress_hi"

RECORDS_TITLE_HI_DEFAULT = "आपके रेफ़रल रिकॉर्ड"
RECORDS_NOT_ON_FILE_HI_DEFAULT = "— उपलब्ध नहीं —"
RECORDS_MASKED_NOTE_HI_DEFAULT = (
    "इस लिंक को आगे भेजा जा सकता है, इसलिए नाम और नंबर आंशिक रूप से छिपाए गए हैं। पूरी "
    "जानकारी देखने के लिए लॉग इन करें।"
)
RECORDS_LOGIN_CTA_HI_DEFAULT = "पूरी जानकारी के लिए लॉग इन करें"
RECORDS_EXPIRED_TITLE_HI_DEFAULT = "यह लिंक समाप्त हो गया है"
RECORDS_EXPIRED_BODY_HI_DEFAULT = (
    "रेफ़रल-रिकॉर्ड लिंक कुछ समय बाद काम करना बंद कर देते हैं। अपने रिकॉर्ड देखने के लिए लॉग इन करें।"
)
RECORDS_EMPTY_HI_DEFAULT = "अभी तक कोई रेफ़रल दर्ज नहीं हुआ है।"
RECORDS_HUB_CTA_HI_DEFAULT = "अपना रेफ़रल लिंक शेयर करें"
RECORDS_STAT_REFERRED_HI_DEFAULT = "रेफ़र किए गए"
RECORDS_STAT_CONVERTED_HI_DEFAULT = "खाते खुले"
RECORDS_STAT_PENDING_HI_DEFAULT = "प्रगति में"
RECORDS_COL_NAME_HI_DEFAULT = "नाम"
RECORDS_COL_MOBILE_HI_DEFAULT = "मोबाइल"
RECORDS_COL_STATUS_HI_DEFAULT = "स्थिति"
RECORDS_COL_REFERRED_HI_DEFAULT = "रेफ़र किया गया"
RECORDS_STATUS_OPENED_HI_DEFAULT = "खाता खुल गया"
RECORDS_STATUS_IN_PROGRESS_HI_DEFAULT = "प्रगति में"

# --- Share hub chrome (button labels, section furniture — T-061 HI twins) ----------
HUB_YOUR_LINK_LABEL = "hub_your_link_label"
HUB_SHARE_HEADING = "hub_share_heading"
HUB_COPY_LABEL = "hub_copy_label"
HUB_COPY_DONE_LABEL = "hub_copy_done_label"
HUB_MORE_LABEL = "hub_more_label"
HUB_RECORDS_CTA = "hub_records_cta"
HUB_DOWNLOAD_LABEL = "hub_download_label"

HUB_YOUR_LINK_LABEL_DEFAULT = "Your referral link"
HUB_SHARE_HEADING_DEFAULT = "Share it"
HUB_COPY_LABEL_DEFAULT = "Copy link"
HUB_COPY_DONE_LABEL_DEFAULT = "Copied"
HUB_MORE_LABEL_DEFAULT = "More…"
HUB_RECORDS_CTA_DEFAULT = "See your referral records"
HUB_DOWNLOAD_LABEL_DEFAULT = "Download poster"

HUB_YOUR_LINK_LABEL_HI = "hub_your_link_label_hi"
HUB_SHARE_HEADING_HI = "hub_share_heading_hi"
HUB_COPY_LABEL_HI = "hub_copy_label_hi"
HUB_COPY_DONE_LABEL_HI = "hub_copy_done_label_hi"
HUB_MORE_LABEL_HI = "hub_more_label_hi"
HUB_RECORDS_CTA_HI = "hub_records_cta_hi"
HUB_DOWNLOAD_LABEL_HI = "hub_download_label_hi"

HUB_YOUR_LINK_LABEL_HI_DEFAULT = "आपका रेफ़रल लिंक"
HUB_SHARE_HEADING_HI_DEFAULT = "इसे शेयर करें"
HUB_COPY_LABEL_HI_DEFAULT = "लिंक कॉपी करें"
HUB_COPY_DONE_LABEL_HI_DEFAULT = "कॉपी हो गया"
HUB_MORE_LABEL_HI_DEFAULT = "और…"
HUB_RECORDS_CTA_HI_DEFAULT = "अपने रेफ़रल रिकॉर्ड देखें"
HUB_DOWNLOAD_LABEL_HI_DEFAULT = "पोस्टर डाउनलोड करें"

# --- Share hub images (T-063) — up to two configurable share-poster image slots ----
# EMPTY by default so no image UI renders anywhere until the owner points these at a
# compliance-reviewed asset (Constitution §4: no dead buttons). Consumed by
# `apps.accounts.hub.resolve_share_image_url`, which enforces same-origin (a
# cross-origin value is rejected, never rendered — see that function's docstring for
# the reasoning) both when the Preferences screen saves a value and when the hub
# renders one, so a value written directly to the DB can't slip past the render-time
# check either.
SHARE_HUB_IMAGE_1_URL = "share_hub_image_1_url"
SHARE_HUB_IMAGE_2_URL = "share_hub_image_2_url"
SHARE_HUB_IMAGE_1_URL_DEFAULT = ""
SHARE_HUB_IMAGE_2_URL_DEFAULT = ""

# --- Referrer-personalized share opener (T-064) -------------------------------------
# A referrer may replace the OPENING sentence of the message they forward — nothing
# more. The credit link and the compliance disclosure line are appended SERVER-SIDE
# after whatever the referrer wrote (apps.referrals.share_intent_service.kit_message),
# so no text a referrer can type is able to remove or reorder them.
#
# Both knobs are cascade keys (rail E-6 / §6d) rather than literals:
#   * `..._enabled` — the surface's own gate. Default TRUE because the feature ships
#     COMPLETE (edit + reset + composition + admin reset), so a False default would
#     mean shipping a finished surface nobody can see; an owner who wants it off flips
#     one tenant row, with no deploy.
#   * `..._max_chars` — the server-side length cap. 300 is the owner's figure
#     (2026-08-10): long enough for a real personal note, short enough that the link
#     and disclosure line stay visible in a WhatsApp preview without a "read more" tap.
REFERRER_SHARE_OPENER_ENABLED = "referrer_share_opener_enabled"
REFERRER_SHARE_OPENER_ENABLED_DEFAULT = True
REFERRER_SHARE_OPENER_MAX_CHARS = "referrer_share_opener_max_chars"
REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT = 300

# Hub copy for the opener editor — bilingual (T-061 contract: every base key has an
# `_hi` twin that falls back to EN when unset/blank).
HUB_OPENER_HEADING = "hub_opener_heading"
HUB_OPENER_HEADING_DEFAULT = "Your personal message"
HUB_OPENER_HEADING_HI = "hub_opener_heading_hi"
HUB_OPENER_HEADING_HI_DEFAULT = "आपका निजी संदेश"

HUB_OPENER_HELP = "hub_opener_help"
HUB_OPENER_HELP_DEFAULT = "Write your own opening line. Leave it empty to use the standard message."
HUB_OPENER_HELP_HI = "hub_opener_help_hi"
HUB_OPENER_HELP_HI_DEFAULT = "अपनी शुरुआती पंक्ति लिखें। खाली छोड़ने पर सामान्य संदेश भेजा जाएगा।"

HUB_OPENER_LOCKED_NOTE = "hub_opener_locked_note"
HUB_OPENER_LOCKED_NOTE_DEFAULT = (
    "Your referral link and the disclosure line are always added automatically."
)
HUB_OPENER_LOCKED_NOTE_HI = "hub_opener_locked_note_hi"
HUB_OPENER_LOCKED_NOTE_HI_DEFAULT = (
    "आपका रेफ़रल लिंक और डिस्क्लोज़र लाइन हमेशा अपने आप जोड़ दी जाती है।"
)

HUB_OPENER_SAVE_LABEL = "hub_opener_save_label"
HUB_OPENER_SAVE_LABEL_DEFAULT = "Save message"
HUB_OPENER_SAVE_LABEL_HI = "hub_opener_save_label_hi"
HUB_OPENER_SAVE_LABEL_HI_DEFAULT = "संदेश सेव करें"

HUB_OPENER_RESET_LABEL = "hub_opener_reset_label"
HUB_OPENER_RESET_LABEL_DEFAULT = "Use the standard message"
HUB_OPENER_RESET_LABEL_HI = "hub_opener_reset_label_hi"
HUB_OPENER_RESET_LABEL_HI_DEFAULT = "सामान्य संदेश इस्तेमाल करें"

# --- Login-gated hub: the "no linked referral record yet" state (T-075) ------------
# `GET /hub` resolves the referrer from the SESSION, so it can be reached by someone
# who has proved who they are but has no `ReferralIdentity` row yet (bound at login,
# never clicked, no Zoho-imported conversion). Identities are created at CLICK time
# (ADR-008) and rendering a page must not create one — so that visitor gets this
# explicit "link your account" state instead of a blank or broken hub.
#
# Copy is cascade keys, not literals (rail E-6 / §6d), with the T-061 `_hi` twins.
HUB_UNLINKED_TITLE = "hub_unlinked_title"
HUB_UNLINKED_TITLE_DEFAULT = "Your referral link isn't ready yet"
HUB_UNLINKED_TITLE_HI = "hub_unlinked_title_hi"
HUB_UNLINKED_TITLE_HI_DEFAULT = "आपका रेफ़रल लिंक अभी तैयार नहीं है"

HUB_UNLINKED_BODY = "hub_unlinked_body"
HUB_UNLINKED_BODY_DEFAULT = (
    "We could not find a referral record for your account yet. "
    "Verify your account details and we will set it up for you."
)
HUB_UNLINKED_BODY_HI = "hub_unlinked_body_hi"
HUB_UNLINKED_BODY_HI_DEFAULT = (
    "आपके खाते के लिए अभी कोई रेफ़रल रिकॉर्ड नहीं मिला। "
    "अपना विवरण सत्यापित करें, हम इसे सेट कर देंगे।"
)

HUB_UNLINKED_CTA = "hub_unlinked_cta"
HUB_UNLINKED_CTA_DEFAULT = "Verify your account"
HUB_UNLINKED_CTA_HI = "hub_unlinked_cta_hi"
HUB_UNLINKED_CTA_HI_DEFAULT = "अपना खाता सत्यापित करें"

# --- Language toggle label (T-061) --------------------------------------------------
LANG_TOGGLE_TO_HI_LABEL = "lang_toggle_to_hi_label"
LANG_TOGGLE_TO_EN_LABEL = "lang_toggle_to_en_label"
LANG_TOGGLE_TO_HI_LABEL_DEFAULT = "हिंदी में देखें"
LANG_TOGGLE_TO_EN_LABEL_DEFAULT = "View in English"

# --- Compliance — market-risk warning HI twin (T-061) -------------------------------
# The EN `market_risk_warning` key stays COMPLIANCE-LOCKED and untouched (D-1 rail,
# central-only, ADR-014) — this is a SEPARATE, unlocked cascade key carrying only the
# Hindi wording, so it can never weaken or replace the locked EN claim; the two render
# together (this string + the verbatim-EN AP_DISCLOSURE_BLOCK/NSE reg. no., which are
# regulator-registered identifiers and are never translated). Default is the exact
# wording already approved and live in the HI WhatsApp templates (owner precedent,
# Wati-Project docs) — not a fresh translation.
MARKET_RISK_WARNING_HI = "market_risk_warning_hi"
MARKET_RISK_WARNING_HI_DEFAULT = (
    "प्रतिभूति बाज़ार में निवेश बाज़ार जोखिमों के अधीन है।"
)

# --- Share-kit message, EN + HI (T-062 self-serve editing) -------------------------
# The one-tap /share/{channel}/{client_id} + referral share hub prefill (a referrer's
# forward-to-a-prospect message). Editable through Preferences (rail E-6 / §6d) — it is
# customer-facing copy, so the owner edits it directly, no deploy. Key name MUST match
# apps.referrals.share_intent_service.SHARE_KIT_MESSAGE_KEY exactly; kept as a literal
# here (not imported) to avoid a preferences<->share_intent_service import cycle —
# tests/test_t062_share_message_prefs.py pin the two strings equal.
#
# Placeholders the template supports (read from kit_message() — never guessed):
#   {link}          the referrer's own tracked referral link
#   {program_brand} the resolved partner/program brand name (T-059)
# The compliance disclosure line (`Disclosures: https://…/d/{slug}`) is appended by
# kit_message() automatically and is NOT part of this editable template — an operator
# cannot drop it by rewording.
SHARE_KIT_MESSAGE_TEMPLATE = "share_kit_message_template"

# HI twin — same {link}/{program_brand} placeholders, resolved by kit_message() when
# the caller's lang is "hi". Falls back to the EN template when unset (apps.config.i18n
# contract).
SHARE_KIT_MESSAGE_TEMPLATE_HI = "share_kit_message_template_hi"
SHARE_KIT_MESSAGE_TEMPLATE_HI_DEFAULT = (
    "एक मुफ़्त {program_brand} खाता खोलें — मेरा रेफ़रल लिंक:\n{link}"
)

# --- WhatsApp notification routing (Tier 2, admin) ---------------------------------
# Which of the three lead-time notifications actually go out (doc-08 A6 a/b/c).
# Routing only: turning one OFF suppresses that recipient; it never changes WHAT is
# sent, and it never overrides the harder gates that already exist upstream —
# ENABLE_WATI_SEND (log-only when off), opt-out state, and "referrer phone unknown ⇒
# skip, never guess". This is the admin saying "don't route this one", not a way to
# force a send past a suppression.
NOTIFY_OFFICE = "notify_office"      # (a) Ashok / the office alert
NOTIFY_PROSPECT = "notify_prospect"  # (b) the new person (warm UTILITY, opt-in-aware)
NOTIFY_REFERRER = "notify_referrer"  # (c) the referrer thank-you (only if phone known)

# Role code -> routing key. The roles match notify.queue_lead_notifications, so a new
# recipient is a row here + a notify call, not a new branch in the screen.
NOTIFY_ROLE_KEYS = {
    "office": NOTIFY_OFFICE,
    "prospect": NOTIFY_PROSPECT,
    "referrer": NOTIFY_REFERRER,
}


# --- My Referrals self-view (T-054 door to the share hub) --------------------------
# The CTA label on the referrer's own "go to your share hub" button/link — a rail E-6
# cascade key (T-060 checker finding, COORDINATION.md 2026-08-08) rather than a
# template/view literal, so the owner can re-word it with no deploy.
MY_REFERRALS_HUB_CTA = "my_referrals_hub_cta"
MY_REFERRALS_HUB_CTA_DEFAULT = "Share your link"

# --- Per-referrer (Tier 3) — STAGED, dormant until ENABLE_CUSTOMER_LOGIN ----------
# These resolve at the USER tier of the cascade (ADR-022), which the resolver only
# consults when ENABLE_CUSTOMER_LOGIN is on — so they are inert today by construction,
# not merely hidden. The screen renders them only when that flag is on (Constitution
# §4: no dead UI). Defaults below are what every referrer gets until they choose.
REFERRER_LANDING_MODE = "referrer_landing_mode"        # "" = inherit the tenant default
REFERRER_NOTIFICATIONS_ON = "referrer_notifications_on"
REFERRER_LANGUAGE = "referrer_language"
REFERRER_PROMO_OPT_OUT = "referrer_promo_opt_out"

LANG_EN = "en"
LANG_HI = "hi"
REFERRER_LANGUAGE_CHOICES = [(LANG_EN, "English"), (LANG_HI, "Hindi")]
_VALID_LANGUAGES = {code for code, _ in REFERRER_LANGUAGE_CHOICES}

# --- Lead-time WATI template names (config-over-code) -------------------------------
# The Meta-approved template each (role, language) send uses. Config-driven so a new
# approved template version (or a new partner) is swapped through config with NO deploy
# — never hardcoded in notify.py (the earlier bug: notify.py named templates that did
# not exist in Wati). Key = "notify_template_<role>_<lang>". Office is English-only
# (internal alert); prospect/referrer carry both. Central defaults are the names
# APPROVED 2026-07-17 (see Wati-Project/docs/wati-templates.json + docs/integrations/
# WATI-TEMPLATE-INVENTORY.md). A tenant override wins per the cascade.
def _notify_template_key(role: str, lang: str) -> str:
    return f"notify_template_{role}_{lang}"


# These defaults MUST name templates that actually exist at Meta.
#
# They are the fallback when no config override is set, so a default naming a deleted or
# never-created template is a live landmine: sends fail and cascade silently. That is exactly
# the P0 found 2026-07-26 — `otp_whatsapp_template` pointed at `gorefer_login_otp`, a name
# that had never existed, so every WhatsApp login OTP got HTTP 400 and silently degraded to
# the `manual` channel while the flag still read ON.
#
# Realigned 2026-07-26 to the values production actually resolves, so that deleting the
# genuinely-superseded older templates (owner decision D6) cannot resurrect that failure mode.
NOTIFY_TEMPLATE_DEFAULTS = {
    # office has no Hindi variant → both map to the English office alert.
    _notify_template_key("office", LANG_EN): "gr_brokers_zerodha_office_lead_alert_en_2026_07_19",
    _notify_template_key("office", LANG_HI): "gr_brokers_zerodha_office_lead_alert_en_2026_07_19",
    # prospect: use the v2 UTILITY re-cut (the v1 pair reclassified to MARKETING, which
    # is capped — wrong for a must-arrive welcome). v2 dropped the promo phrasing.
    _notify_template_key("prospect", LANG_EN): "gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2",
    _notify_template_key("prospect", LANG_HI): "gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2",
    # referrer: the live path sends the "your referral has started" UPDATE, not the older
    # thank-you. The thank-you templates still exist at Meta and are a genuinely DIFFERENT
    # message (not a superseded version), so they are kept — just not the default.
    _notify_template_key("referrer", LANG_EN): "gr_brokers_zerodha_referrer_update_en_2026_07_19",
    _notify_template_key("referrer", LANG_HI): "gr_brokers_zerodha_referrer_update_hin_2026_07_19",
}


def notify_template_name(role: str, *, lang: str = LANG_EN, tenant_id: int | None = None) -> str:
    """Resolve the Meta template name for a (role, language) lead-time notification.

    Config-driven (cascade), defaulting to the approved names. Unknown language falls
    back to English; an unknown role raises (a new role must register a default).
    """
    lang = lang if lang in _VALID_LANGUAGES else LANG_EN
    key = _notify_template_key(role, lang)
    default = NOTIFY_TEMPLATE_DEFAULTS.get(key) or NOTIFY_TEMPLATE_DEFAULTS.get(
        _notify_template_key(role, LANG_EN)
    )
    if default is None:
        raise KeyError(f"no notify template default for role={role!r}")
    return resolve(key, tenant_id=tenant_id, default=default)


# The (role, lang, label) rows the Settings screen renders + persists, in display
# order. One row per editable template-name field. Office is en-only (its hi key maps
# to the same en name, so the screen shows a single office field).
NOTIFY_TEMPLATE_FIELDS = [
    ("office", LANG_EN, "Office / Ashok alert (English)"),
    ("prospect", LANG_EN, "Prospect welcome (English)"),
    ("prospect", LANG_HI, "Prospect welcome (Hindi)"),
    ("referrer", LANG_EN, "Referrer thank-you (English)"),
    ("referrer", LANG_HI, "Referrer thank-you (Hindi)"),
]


def notify_template_fields_view(tenant_id: int | None = None) -> list[dict]:
    """Rows for the Settings 'WhatsApp Templates' section: each editable field with its
    form key, label, currently-resolved value, and whether it is an override or default."""
    rows = []
    for role, lang, label in NOTIFY_TEMPLATE_FIELDS:
        key = _notify_template_key(role, lang)
        default = NOTIFY_TEMPLATE_DEFAULTS[key]
        current = resolve(key, tenant_id=tenant_id, default=default)
        rows.append({
            "form_key": key,          # e.g. notify_template_prospect_en
            "label": label,
            "value": current,
            "default": default,
            "is_override": current != default,
        })
    return rows

# A referrer may only pick a landing mode the TENANT allows; "" means inherit. The
# ADR-032 coupling (direct needs a live /d/{slug}) is a tenant-level fact, so a
# per-referrer `direct` can never bypass it — it is re-checked on resolve.
REFERRER_LANDING_INHERIT = ""

# --- Messaging engine (T-124 W1) — digest/alert knobs on the Preferences screen ----
# Campaign CONFIG itself (MessagingCampaign/MessagingCampaignStep) lives on its own
# CRUD page at /admin-panel/campaigns (decision ⑬) — these five are the single-value
# knobs that decision put on the EXISTING Preferences screen instead: when/where the
# operator's own status digest goes, and the alert thresholds around it. No sending/
# scheduling engine reads these yet (W2) — this is configuration only (rail E-6/§6d).
MESSAGING_DIGEST_SEND_HOUR_IST = "messaging_digest_send_hour_ist"
MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT = 9

MESSAGING_DIGEST_RECIPIENTS = "messaging_digest_recipients"
MESSAGING_DIGEST_RECIPIENTS_DEFAULT = "917388882020"

MESSAGING_DIGEST_ALERTS_ENABLED = "messaging_digest_alerts_enabled"
MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT = False

MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT = "messaging_digest_alert_failure_ratio_pct"
MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT = 30

MESSAGING_DIGEST_ALERT_RECOVERY_HITS = "messaging_digest_alert_recovery_hits"
MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT = 10

# T-127 W4 — the approved template the daily digest sends. A cascade key (rail E-6 /
# §6d), same reasoning as RECORDS_LINK_TEMPLATE_EN: a re-cut name swaps in with no
# deploy. Default is the name verified live at T-127 intake (2026-08-14).
MESSAGING_DIGEST_TEMPLATE_EN = "messaging_digest_template_en"
MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT = "gr_platform_gorefer_funnel_report_en_2026_07_21"

# The rows the Preferences screen's "Messaging engine" section renders + persists, in
# display order — the same data-driven shape as NOTIFY_TEMPLATE_FIELDS, so a future
# knob is a row here, not a new template block. `kind` picks the input widget the
# template renders (int / text / bool); `bounds` is (lo, hi) for int fields.
MESSAGING_ENGINE_FIELDS = [
    (MESSAGING_DIGEST_SEND_HOUR_IST, "Digest send hour (IST)", "int", (0, 23)),
    (MESSAGING_DIGEST_RECIPIENTS, "Digest recipients (comma-separated numbers)", "text", None),
    (MESSAGING_DIGEST_ALERTS_ENABLED, "Alerts enabled", "bool", None),
    (MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT, "Alert failure ratio (%)", "int", (0, 100)),
    (MESSAGING_DIGEST_ALERT_RECOVERY_HITS, "Alert recovery hits", "int", (0, 1000)),
    (MESSAGING_DIGEST_TEMPLATE_EN, "Digest template name (EN)", "text", None),
]

_MESSAGING_ENGINE_DEFAULTS = {
    MESSAGING_DIGEST_SEND_HOUR_IST: MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT,
    MESSAGING_DIGEST_RECIPIENTS: MESSAGING_DIGEST_RECIPIENTS_DEFAULT,
    MESSAGING_DIGEST_ALERTS_ENABLED: MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT,
    MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT: MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT,
    MESSAGING_DIGEST_ALERT_RECOVERY_HITS: MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT,
    MESSAGING_DIGEST_TEMPLATE_EN: MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT,
}


def messaging_engine_fields_view(tenant_id: int | None = None) -> list[dict]:
    """Rows for the Preferences 'Messaging engine' section: form key, label, widget
    kind, bounds (for int fields), and the currently-resolved value."""
    rows = []
    for key, label, kind, bounds in MESSAGING_ENGINE_FIELDS:
        default = _MESSAGING_ENGINE_DEFAULTS[key]
        value = resolve(key, tenant_id=tenant_id, default=default)
        if kind == "bool":
            value = _as_bool(value)
        elif kind == "int":
            value = _as_int(value, default)
        rows.append({
            "form_key": key,
            "label": label,
            "kind": kind,
            "bounds": bounds,
            "value": value,
            "default": default,
        })
    return rows


# --- OTP login keys (Q-M-OTP) — per-tenant, cascade-resolved, edited on the screen.
# The "very easily configurable for admin" requirement: swap the OTP channel/order/
# template/limits through Preferences with NO deploy (config-over-code). The master
# ENABLE_OTP_LOGIN flag stays a flags.py env flag (gates the whole feature); these
# keys tune behaviour once it's on.
OTP_PRIMARY_CHANNEL = "otp_primary_channel"
OTP_FALLBACK_CHANNELS = "otp_fallback_channels"
OTP_WHATSAPP_TEMPLATE = "otp_whatsapp_template"
OTP_CODE_LENGTH = "otp_code_length"
OTP_CODE_TTL_SECONDS = "otp_code_ttl_seconds"
OTP_MAX_VERIFY_ATTEMPTS = "otp_max_verify_attempts"
OTP_RESEND_COOLDOWN_SECONDS = "otp_resend_cooldown_seconds"
OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR = "otp_rate_limit_per_identity_per_hour"
# T-078 email leg copy. Rail E-6: what a message SAYS is config, never a literal.
# Body placeholders: {code}, {minutes}, {sender_identity}.
OTP_EMAIL_SUBJECT = "otp_email_subject"
OTP_EMAIL_BODY_TEMPLATE = "otp_email_body_template"
# T-081 — the sender ADDRESS is self-serve too (owner rule 2026-08-10, §6d): where
# the OTP email appears to come FROM is customer-facing behavior, same category as
# subject/body above. The SMTP credential (host/port/user/password) stays env-only —
# only this non-secret address is exposed here. "" = no override; the adapter falls
# back to settings.DEFAULT_FROM_EMAIL exactly as T-078 shipped (byte-identical when
# unset).
OTP_EMAIL_FROM_ADDRESS = "otp_email_from_address"
OTP_EMAIL_FROM_ADDRESS_DEFAULT = ""

# OTP channel codes an admin may pick (must match apps.otp.channels registry keys).
OTP_CHANNEL_WHATSAPP_WATI = "whatsapp_wati"
OTP_CHANNEL_SMS = "sms"
OTP_CHANNEL_MANUAL = "manual"
OTP_CHANNEL_CHOICES = [
    (OTP_CHANNEL_WHATSAPP_WATI, "WhatsApp (Wati)"),
    (OTP_CHANNEL_SMS, "SMS"),
    (OTP_CHANNEL_MANUAL, "Manual / assisted"),
]
_VALID_OTP_CHANNELS = {code for code, _ in OTP_CHANNEL_CHOICES}

# The channel codes a tenant may enable (must match gorefer.flags.SHARE_CHANNEL_LABELS).
# WhatsApp + Copy are the always-on defaults; the rest are opt-in per tenant.
DEFAULT_SHARE_CHANNELS = ["wa", "copy"]


def central_defaults() -> dict:
    """Central baseline for the preference keys (seeded into config_central).

    Values are the current settings/flags so behaviour is identical to today until a
    tenant overrides one through the screen.
    """
    from gorefer.flags import flags

    return {
        LANDING_MODE: "page",
        SHARE_SHOW_REWARD: True,
        REFERRER_REWARD_CLAIM: flags.REFERRAL_INCENTIVE_CLAIM,
        SUPPORT_HELPLINE_PHONE: getattr(settings, "SUPPORT_HELPLINE_PHONE", ""),
        WATI_BUSINESS_NUMBER: settings.WATI_BUSINESS_NUMBER,
        SHARE_CHANNELS_ALLOWLIST: DEFAULT_SHARE_CHANNELS,
        ENABLE_ASSISTED_REFERRAL: False,
        # Share/redirect recovery page (T-122) — see the key block above.
        SHARE_RECOVERY_HEADLINE: SHARE_RECOVERY_HEADLINE_DEFAULT,
        SHARE_RECOVERY_BODY: SHARE_RECOVERY_BODY_DEFAULT,
        SHARE_RECOVERY_BUTTON_LABEL: SHARE_RECOVERY_BUTTON_LABEL_DEFAULT,
        SHARE_RECOVERY_PREFILL: SHARE_RECOVERY_PREFILL_DEFAULT,
        RECORDS_LINK_TTL_DAYS: RECORDS_LINK_TTL_DAYS_DEFAULT,
        RECORDS_MINT_DATE_FORMAT: RECORDS_MINT_DATE_FORMAT_DEFAULT,
        RECORDS_LINK_TEMPLATE_EN: RECORDS_LINK_TEMPLATE_EN_DEFAULT,
        RECORDS_LINK_SEND_MAX_PER_RUN: RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
        RECORDS_LINK_SEND_MIN_GAP_DAYS: RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
        INVITE_TEMPLATE_EN: INVITE_TEMPLATE_EN_DEFAULT,
        INVITE_SEND_MAX_PER_RUN: INVITE_SEND_MAX_PER_RUN_DEFAULT,
        INVITE_SEND_MIN_GAP_DAYS: INVITE_SEND_MIN_GAP_DAYS_DEFAULT,
        REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN: REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN_DEFAULT,
        REFERRER_CONVERSION_CONGRATS_BODY_EN: REFERRER_CONVERSION_CONGRATS_BODY_EN_DEFAULT,
        # Share hub (T-053) — placeholder copy pending owner compliance review.
        SHARE_HUB_HEADLINE: SHARE_HUB_HEADLINE_DEFAULT,
        SHARE_HUB_INTRO: SHARE_HUB_INTRO_DEFAULT,
        SHARE_HUB_BENEFITS_HEADING: SHARE_HUB_BENEFITS_HEADING_DEFAULT,
        SHARE_HUB_BENEFITS: SHARE_HUB_BENEFITS_DEFAULT,
        SHARE_HUB_GUIDANCE_HEADING: SHARE_HUB_GUIDANCE_HEADING_DEFAULT,
        SHARE_HUB_GUIDANCE: SHARE_HUB_GUIDANCE_DEFAULT,
        SHARE_HUB_OG_IMAGE_URL: SHARE_HUB_OG_IMAGE_DEFAULT,
        SHARE_HUB_PARTNER_ATTRIBUTION: SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT,
        MY_REFERRALS_HUB_CTA: MY_REFERRALS_HUB_CTA_DEFAULT,
        # Share hub — Hindi twins (T-061). Owner review pending (pre-made decision #3).
        SHARE_HUB_HEADLINE_HI: SHARE_HUB_HEADLINE_HI_DEFAULT,
        SHARE_HUB_INTRO_HI: SHARE_HUB_INTRO_HI_DEFAULT,
        SHARE_HUB_BENEFITS_HEADING_HI: SHARE_HUB_BENEFITS_HEADING_HI_DEFAULT,
        SHARE_HUB_BENEFITS_HI: SHARE_HUB_BENEFITS_HI_DEFAULT,
        SHARE_HUB_GUIDANCE_HEADING_HI: SHARE_HUB_GUIDANCE_HEADING_HI_DEFAULT,
        SHARE_HUB_GUIDANCE_HI: SHARE_HUB_GUIDANCE_HI_DEFAULT,
        SHARE_HUB_PARTNER_ATTRIBUTION_HI: SHARE_HUB_PARTNER_ATTRIBUTION_HI_DEFAULT,
        # Records page (EN + HI) — T-061.
        RECORDS_TITLE: RECORDS_TITLE_DEFAULT,
        RECORDS_NOT_ON_FILE: RECORDS_NOT_ON_FILE_DEFAULT,
        RECORDS_MASKED_NOTE: RECORDS_MASKED_NOTE_DEFAULT,
        RECORDS_LOGIN_CTA: RECORDS_LOGIN_CTA_DEFAULT,
        RECORDS_EXPIRED_TITLE: RECORDS_EXPIRED_TITLE_DEFAULT,
        RECORDS_EXPIRED_BODY: RECORDS_EXPIRED_BODY_DEFAULT,
        RECORDS_EMPTY: RECORDS_EMPTY_DEFAULT,
        RECORDS_HUB_CTA: RECORDS_HUB_CTA_DEFAULT,
        RECORDS_STAT_REFERRED: RECORDS_STAT_REFERRED_DEFAULT,
        RECORDS_STAT_CONVERTED: RECORDS_STAT_CONVERTED_DEFAULT,
        RECORDS_STAT_PENDING: RECORDS_STAT_PENDING_DEFAULT,
        RECORDS_COL_NAME: RECORDS_COL_NAME_DEFAULT,
        RECORDS_COL_MOBILE: RECORDS_COL_MOBILE_DEFAULT,
        RECORDS_COL_STATUS: RECORDS_COL_STATUS_DEFAULT,
        RECORDS_COL_REFERRED: RECORDS_COL_REFERRED_DEFAULT,
        RECORDS_STATUS_OPENED: RECORDS_STATUS_OPENED_DEFAULT,
        RECORDS_STATUS_IN_PROGRESS: RECORDS_STATUS_IN_PROGRESS_DEFAULT,
        RECORDS_TITLE_HI: RECORDS_TITLE_HI_DEFAULT,
        RECORDS_NOT_ON_FILE_HI: RECORDS_NOT_ON_FILE_HI_DEFAULT,
        RECORDS_MASKED_NOTE_HI: RECORDS_MASKED_NOTE_HI_DEFAULT,
        RECORDS_LOGIN_CTA_HI: RECORDS_LOGIN_CTA_HI_DEFAULT,
        RECORDS_EXPIRED_TITLE_HI: RECORDS_EXPIRED_TITLE_HI_DEFAULT,
        RECORDS_EXPIRED_BODY_HI: RECORDS_EXPIRED_BODY_HI_DEFAULT,
        RECORDS_EMPTY_HI: RECORDS_EMPTY_HI_DEFAULT,
        RECORDS_HUB_CTA_HI: RECORDS_HUB_CTA_HI_DEFAULT,
        RECORDS_STAT_REFERRED_HI: RECORDS_STAT_REFERRED_HI_DEFAULT,
        RECORDS_STAT_CONVERTED_HI: RECORDS_STAT_CONVERTED_HI_DEFAULT,
        RECORDS_STAT_PENDING_HI: RECORDS_STAT_PENDING_HI_DEFAULT,
        RECORDS_COL_NAME_HI: RECORDS_COL_NAME_HI_DEFAULT,
        RECORDS_COL_MOBILE_HI: RECORDS_COL_MOBILE_HI_DEFAULT,
        RECORDS_COL_STATUS_HI: RECORDS_COL_STATUS_HI_DEFAULT,
        RECORDS_COL_REFERRED_HI: RECORDS_COL_REFERRED_HI_DEFAULT,
        RECORDS_STATUS_OPENED_HI: RECORDS_STATUS_OPENED_HI_DEFAULT,
        RECORDS_STATUS_IN_PROGRESS_HI: RECORDS_STATUS_IN_PROGRESS_HI_DEFAULT,
        # Hub chrome (EN + HI) — T-061.
        HUB_YOUR_LINK_LABEL: HUB_YOUR_LINK_LABEL_DEFAULT,
        HUB_SHARE_HEADING: HUB_SHARE_HEADING_DEFAULT,
        HUB_COPY_LABEL: HUB_COPY_LABEL_DEFAULT,
        HUB_COPY_DONE_LABEL: HUB_COPY_DONE_LABEL_DEFAULT,
        HUB_MORE_LABEL: HUB_MORE_LABEL_DEFAULT,
        HUB_RECORDS_CTA: HUB_RECORDS_CTA_DEFAULT,
        HUB_DOWNLOAD_LABEL: HUB_DOWNLOAD_LABEL_DEFAULT,
        HUB_YOUR_LINK_LABEL_HI: HUB_YOUR_LINK_LABEL_HI_DEFAULT,
        HUB_SHARE_HEADING_HI: HUB_SHARE_HEADING_HI_DEFAULT,
        HUB_COPY_LABEL_HI: HUB_COPY_LABEL_HI_DEFAULT,
        HUB_COPY_DONE_LABEL_HI: HUB_COPY_DONE_LABEL_HI_DEFAULT,
        HUB_MORE_LABEL_HI: HUB_MORE_LABEL_HI_DEFAULT,
        HUB_RECORDS_CTA_HI: HUB_RECORDS_CTA_HI_DEFAULT,
        HUB_DOWNLOAD_LABEL_HI: HUB_DOWNLOAD_LABEL_HI_DEFAULT,
        # Share hub images (T-063) — EMPTY by default (no image UI until configured).
        SHARE_HUB_IMAGE_1_URL: SHARE_HUB_IMAGE_1_URL_DEFAULT,
        SHARE_HUB_IMAGE_2_URL: SHARE_HUB_IMAGE_2_URL_DEFAULT,
        # Referrer-personalized share opener (T-064) — the gate + the length cap, plus
        # the editor's bilingual copy. Enabled by default: the surface ships complete.
        REFERRER_SHARE_OPENER_ENABLED: REFERRER_SHARE_OPENER_ENABLED_DEFAULT,
        REFERRER_SHARE_OPENER_MAX_CHARS: REFERRER_SHARE_OPENER_MAX_CHARS_DEFAULT,
        HUB_OPENER_HEADING: HUB_OPENER_HEADING_DEFAULT,
        HUB_OPENER_HELP: HUB_OPENER_HELP_DEFAULT,
        HUB_OPENER_LOCKED_NOTE: HUB_OPENER_LOCKED_NOTE_DEFAULT,
        HUB_OPENER_SAVE_LABEL: HUB_OPENER_SAVE_LABEL_DEFAULT,
        HUB_OPENER_RESET_LABEL: HUB_OPENER_RESET_LABEL_DEFAULT,
        HUB_OPENER_HEADING_HI: HUB_OPENER_HEADING_HI_DEFAULT,
        HUB_OPENER_HELP_HI: HUB_OPENER_HELP_HI_DEFAULT,
        HUB_OPENER_LOCKED_NOTE_HI: HUB_OPENER_LOCKED_NOTE_HI_DEFAULT,
        HUB_OPENER_SAVE_LABEL_HI: HUB_OPENER_SAVE_LABEL_HI_DEFAULT,
        HUB_OPENER_RESET_LABEL_HI: HUB_OPENER_RESET_LABEL_HI_DEFAULT,
        # Login-gated hub "no linked record yet" state (T-075), EN + HI.
        HUB_UNLINKED_TITLE: HUB_UNLINKED_TITLE_DEFAULT,
        HUB_UNLINKED_BODY: HUB_UNLINKED_BODY_DEFAULT,
        HUB_UNLINKED_CTA: HUB_UNLINKED_CTA_DEFAULT,
        HUB_UNLINKED_TITLE_HI: HUB_UNLINKED_TITLE_HI_DEFAULT,
        HUB_UNLINKED_BODY_HI: HUB_UNLINKED_BODY_HI_DEFAULT,
        HUB_UNLINKED_CTA_HI: HUB_UNLINKED_CTA_HI_DEFAULT,
        # Language toggle label — T-061.
        LANG_TOGGLE_TO_HI_LABEL: LANG_TOGGLE_TO_HI_LABEL_DEFAULT,
        LANG_TOGGLE_TO_EN_LABEL: LANG_TOGGLE_TO_EN_LABEL_DEFAULT,
        # Market-risk warning HI twin — unlocked, separate from the locked EN key.
        MARKET_RISK_WARNING_HI: MARKET_RISK_WARNING_HI_DEFAULT,
        # Share-kit message, EN + HI (T-062). EN default mirrors the pre-existing
        # flags.SHARE_KIT_MESSAGE_TEMPLATE env flag exactly — zero behavior change
        # until an admin edits it through the screen.
        SHARE_KIT_MESSAGE_TEMPLATE: flags.SHARE_KIT_MESSAGE_TEMPLATE,
        SHARE_KIT_MESSAGE_TEMPLATE_HI: SHARE_KIT_MESSAGE_TEMPLATE_HI_DEFAULT,
        # Notification routing defaults to ON for all three — this mirrors today's
        # behaviour exactly (doc-08 A6 fires all three), so adding the toggles changes
        # nothing until an admin turns one off.
        NOTIFY_OFFICE: True,
        NOTIFY_PROSPECT: True,
        NOTIFY_REFERRER: True,
        # Tier-3 per-referrer defaults (dormant until ENABLE_CUSTOMER_LOGIN).
        REFERRER_LANDING_MODE: REFERRER_LANDING_INHERIT,  # inherit the tenant default
        REFERRER_NOTIFICATIONS_ON: True,
        REFERRER_LANGUAGE: LANG_EN,
        REFERRER_PROMO_OPT_OUT: False,
        # OTP defaults (Q-M-OTP) — WhatsApp/Wati primary, manual fallback until SMS
        # provider is chosen. Behaviour identical to the spec defaults until an admin
        # overrides through the screen.
        OTP_PRIMARY_CHANNEL: OTP_CHANNEL_WHATSAPP_WATI,
        OTP_FALLBACK_CHANNELS: [OTP_CHANNEL_MANUAL],
        OTP_WHATSAPP_TEMPLATE: getattr(
            settings, "OTP_WHATSAPP_TEMPLATE", "gr_platform_gorefer_login_otp_en_2026_07_21"
        ),
        OTP_CODE_LENGTH: 6,
        OTP_CODE_TTL_SECONDS: 300,
        OTP_MAX_VERIFY_ATTEMPTS: 5,
        OTP_RESEND_COOLDOWN_SECONDS: 60,
        OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR: 5,
        # T-078 — the second (email) leg's copy. Transactional and minimal: the code,
        # its expiry, the ignore-if-not-you line, and the sender identity. No account
        # details, no PII, no marketing.
        OTP_EMAIL_SUBJECT: "Your GoRefer login code",
        OTP_EMAIL_BODY_TEMPLATE: (
            "Your GoRefer login code is {code}.\n\n"
            "It is valid for {minutes} minute(s) and can be used once.\n"
            "If you didn't request this code, please ignore this email.\n\n"
            "— {sender_identity}"
        ),
        # T-081 — empty by default (no override); the adapter falls back to
        # settings.DEFAULT_FROM_EMAIL, exactly what T-078 already sends.
        OTP_EMAIL_FROM_ADDRESS: OTP_EMAIL_FROM_ADDRESS_DEFAULT,
        # Messaging engine (T-124 W1) — digest/alert knobs. No sending engine reads
        # these yet; configuration only.
        MESSAGING_DIGEST_SEND_HOUR_IST: MESSAGING_DIGEST_SEND_HOUR_IST_DEFAULT,
        MESSAGING_DIGEST_RECIPIENTS: MESSAGING_DIGEST_RECIPIENTS_DEFAULT,
        MESSAGING_DIGEST_ALERTS_ENABLED: MESSAGING_DIGEST_ALERTS_ENABLED_DEFAULT,
        MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT: MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT_DEFAULT,
        MESSAGING_DIGEST_ALERT_RECOVERY_HITS: MESSAGING_DIGEST_ALERT_RECOVERY_HITS_DEFAULT,
        MESSAGING_DIGEST_TEMPLATE_EN: MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT,
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _valid_channel(value, fallback: str) -> str:
    """A stored primary channel, guarded to a known adapter code."""
    code = str(value).strip() if value is not None else ""
    return code if code in _VALID_OTP_CHANNELS else fallback


def _as_channel_list(value) -> list[str]:
    """Coerce a stored fallback-channels value to a clean, validated ordered list.

    Accepts a JSON list (how it is stored) or a comma-separated string (defensive).
    Drops unknown channel codes so a bad/legacy value can never route OTP to a
    non-existent adapter.
    """
    if isinstance(value, str):
        items = [c.strip() for c in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(c).strip() for c in value]
    else:
        items = []
    return [c for c in items if c in _VALID_OTP_CHANNELS]


def notification_routing(tenant_id: int | None) -> dict:
    """Role code -> whether that lead-time notification is routed (Tier 2).

    Consumed by notify.queue_lead_notifications. A role that is OFF is recorded as
    skipped with a reason (never silently dropped) — the funnel must still show that
    the message did not go, and why.
    """
    prefs = get_preferences(tenant_id)
    return {role: bool(prefs[key]) for role, key in NOTIFY_ROLE_KEYS.items()}


def get_referrer_preferences(tenant_id: int | None, user_id: int | None) -> dict:
    """Resolve the Tier-3 per-referrer settings through the USER tier of the cascade.

    Inert by construction, not merely hidden: `cascade.resolve()` only consults the
    user tier when ENABLE_CUSTOMER_LOGIN is on, so with the flag off every key here
    falls through to the tenant/central default no matter what a user row says. That
    is the guarantee that staging this now cannot change Sprint-1 behaviour.
    """
    defaults = central_defaults()

    def r(key):
        return resolve(key, tenant_id=tenant_id, user_id=user_id, default=defaults[key])

    mode = str(r(REFERRER_LANDING_MODE) or "").strip().lower()
    if mode not in {"page", "direct", REFERRER_LANDING_INHERIT}:
        mode = REFERRER_LANDING_INHERIT  # unknown value => inherit, never guess
    lang = str(r(REFERRER_LANGUAGE) or "").strip().lower()
    return {
        REFERRER_LANDING_MODE: mode,
        REFERRER_NOTIFICATIONS_ON: _as_bool(r(REFERRER_NOTIFICATIONS_ON)),
        REFERRER_LANGUAGE: lang if lang in _VALID_LANGUAGES else LANG_EN,
        REFERRER_PROMO_OPT_OUT: _as_bool(r(REFERRER_PROMO_OPT_OUT)),
    }


def get_preferences(tenant_id: int | None) -> dict:
    """Resolve every preference key for a tenant through the cascade (typed).

    This is what the Preferences screen renders and what consumers (landing page,
    WhatsApp messages) read, so a saved override takes effect immediately.
    """
    defaults = central_defaults()
    channels = resolve(
        SHARE_CHANNELS_ALLOWLIST, tenant_id=tenant_id, default=defaults[SHARE_CHANNELS_ALLOWLIST]
    )
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]
    return {
        LANDING_MODE: resolve(LANDING_MODE, tenant_id=tenant_id, default=defaults[LANDING_MODE]),
        SHARE_SHOW_REWARD: _as_bool(
            resolve(SHARE_SHOW_REWARD, tenant_id=tenant_id, default=defaults[SHARE_SHOW_REWARD])
        ),
        REFERRER_REWARD_CLAIM: resolve(
            REFERRER_REWARD_CLAIM, tenant_id=tenant_id, default=defaults[REFERRER_REWARD_CLAIM]
        ),
        SUPPORT_HELPLINE_PHONE: resolve(
            SUPPORT_HELPLINE_PHONE, tenant_id=tenant_id, default=defaults[SUPPORT_HELPLINE_PHONE]
        ),
        WATI_BUSINESS_NUMBER: resolve(
            WATI_BUSINESS_NUMBER, tenant_id=tenant_id, default=defaults[WATI_BUSINESS_NUMBER]
        ),
        # Share-kit message, EN + HI (T-062) — what the Preferences screen edits.
        SHARE_KIT_MESSAGE_TEMPLATE: resolve(
            SHARE_KIT_MESSAGE_TEMPLATE, tenant_id=tenant_id, default=defaults[SHARE_KIT_MESSAGE_TEMPLATE]
        ),
        SHARE_KIT_MESSAGE_TEMPLATE_HI: resolve(
            SHARE_KIT_MESSAGE_TEMPLATE_HI,
            tenant_id=tenant_id,
            default=defaults[SHARE_KIT_MESSAGE_TEMPLATE_HI],
        ),
        SHARE_CHANNELS_ALLOWLIST: list(channels),
        # Share hub images (T-063) — resolved raw here; `apps.accounts.hub` is the one
        # place that turns a value into a same-origin render URL (or drops it).
        SHARE_HUB_IMAGE_1_URL: resolve(
            SHARE_HUB_IMAGE_1_URL, tenant_id=tenant_id, default=defaults[SHARE_HUB_IMAGE_1_URL]
        ),
        SHARE_HUB_IMAGE_2_URL: resolve(
            SHARE_HUB_IMAGE_2_URL, tenant_id=tenant_id, default=defaults[SHARE_HUB_IMAGE_2_URL]
        ),
        # Referrer-personalized share opener (T-064) — the gate and the length cap.
        # Only these two are surfaced on the screen; the editor's five copy strings
        # resolve through the cascade like every other bilingual hub label.
        REFERRER_SHARE_OPENER_ENABLED: _as_bool(
            resolve(
                REFERRER_SHARE_OPENER_ENABLED,
                tenant_id=tenant_id,
                default=defaults[REFERRER_SHARE_OPENER_ENABLED],
            )
        ),
        REFERRER_SHARE_OPENER_MAX_CHARS: resolve(
            REFERRER_SHARE_OPENER_MAX_CHARS,
            tenant_id=tenant_id,
            default=defaults[REFERRER_SHARE_OPENER_MAX_CHARS],
        ),
        ENABLE_ASSISTED_REFERRAL: _as_bool(
            resolve(ENABLE_ASSISTED_REFERRAL, tenant_id=tenant_id, default=defaults[ENABLE_ASSISTED_REFERRAL])
        ),
        # Notification routing (Tier 2) — which of the three recipients are routed.
        NOTIFY_OFFICE: _as_bool(
            resolve(NOTIFY_OFFICE, tenant_id=tenant_id, default=defaults[NOTIFY_OFFICE])
        ),
        NOTIFY_PROSPECT: _as_bool(
            resolve(NOTIFY_PROSPECT, tenant_id=tenant_id, default=defaults[NOTIFY_PROSPECT])
        ),
        NOTIFY_REFERRER: _as_bool(
            resolve(NOTIFY_REFERRER, tenant_id=tenant_id, default=defaults[NOTIFY_REFERRER])
        ),
        # OTP (Q-M-OTP) — the same cascade the screen writes, so a saved override
        # takes effect immediately with no deploy.
        OTP_PRIMARY_CHANNEL: _valid_channel(
            resolve(OTP_PRIMARY_CHANNEL, tenant_id=tenant_id, default=defaults[OTP_PRIMARY_CHANNEL]),
            defaults[OTP_PRIMARY_CHANNEL],
        ),
        OTP_FALLBACK_CHANNELS: _as_channel_list(
            resolve(OTP_FALLBACK_CHANNELS, tenant_id=tenant_id, default=defaults[OTP_FALLBACK_CHANNELS])
        ),
        OTP_WHATSAPP_TEMPLATE: resolve(
            OTP_WHATSAPP_TEMPLATE, tenant_id=tenant_id, default=defaults[OTP_WHATSAPP_TEMPLATE]
        ),
        OTP_CODE_LENGTH: _as_int(
            resolve(OTP_CODE_LENGTH, tenant_id=tenant_id, default=defaults[OTP_CODE_LENGTH]),
            defaults[OTP_CODE_LENGTH],
        ),
        OTP_CODE_TTL_SECONDS: _as_int(
            resolve(OTP_CODE_TTL_SECONDS, tenant_id=tenant_id, default=defaults[OTP_CODE_TTL_SECONDS]),
            defaults[OTP_CODE_TTL_SECONDS],
        ),
        OTP_MAX_VERIFY_ATTEMPTS: _as_int(
            resolve(OTP_MAX_VERIFY_ATTEMPTS, tenant_id=tenant_id, default=defaults[OTP_MAX_VERIFY_ATTEMPTS]),
            defaults[OTP_MAX_VERIFY_ATTEMPTS],
        ),
        OTP_RESEND_COOLDOWN_SECONDS: _as_int(
            resolve(
                OTP_RESEND_COOLDOWN_SECONDS,
                tenant_id=tenant_id,
                default=defaults[OTP_RESEND_COOLDOWN_SECONDS],
            ),
            defaults[OTP_RESEND_COOLDOWN_SECONDS],
        ),
        OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR: _as_int(
            resolve(
                OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR,
                tenant_id=tenant_id,
                default=defaults[OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR],
            ),
            defaults[OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR],
        ),
        # T-078 email copy — read at SEND time, so an edit changes the very next code.
        OTP_EMAIL_SUBJECT: resolve(
            OTP_EMAIL_SUBJECT, tenant_id=tenant_id, default=defaults[OTP_EMAIL_SUBJECT]
        ) or defaults[OTP_EMAIL_SUBJECT],
        OTP_EMAIL_BODY_TEMPLATE: resolve(
            OTP_EMAIL_BODY_TEMPLATE, tenant_id=tenant_id, default=defaults[OTP_EMAIL_BODY_TEMPLATE]
        ) or defaults[OTP_EMAIL_BODY_TEMPLATE],
        # T-081 — "" is a legitimate resolved value (means "no override"), so there is
        # no "or default" fallback here (unlike subject/body, whose defaults are never
        # blank).
        OTP_EMAIL_FROM_ADDRESS: resolve(
            OTP_EMAIL_FROM_ADDRESS, tenant_id=tenant_id, default=defaults[OTP_EMAIL_FROM_ADDRESS]
        ),
        # Messaging engine (T-124 W1) digest/alert knobs.
        MESSAGING_DIGEST_SEND_HOUR_IST: _as_int(
            resolve(
                MESSAGING_DIGEST_SEND_HOUR_IST,
                tenant_id=tenant_id,
                default=defaults[MESSAGING_DIGEST_SEND_HOUR_IST],
            ),
            defaults[MESSAGING_DIGEST_SEND_HOUR_IST],
        ),
        MESSAGING_DIGEST_RECIPIENTS: resolve(
            MESSAGING_DIGEST_RECIPIENTS, tenant_id=tenant_id, default=defaults[MESSAGING_DIGEST_RECIPIENTS]
        ),
        MESSAGING_DIGEST_ALERTS_ENABLED: _as_bool(
            resolve(
                MESSAGING_DIGEST_ALERTS_ENABLED,
                tenant_id=tenant_id,
                default=defaults[MESSAGING_DIGEST_ALERTS_ENABLED],
            )
        ),
        MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT: _as_int(
            resolve(
                MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT,
                tenant_id=tenant_id,
                default=defaults[MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT],
            ),
            defaults[MESSAGING_DIGEST_ALERT_FAILURE_RATIO_PCT],
        ),
        MESSAGING_DIGEST_ALERT_RECOVERY_HITS: _as_int(
            resolve(
                MESSAGING_DIGEST_ALERT_RECOVERY_HITS,
                tenant_id=tenant_id,
                default=defaults[MESSAGING_DIGEST_ALERT_RECOVERY_HITS],
            ),
            defaults[MESSAGING_DIGEST_ALERT_RECOVERY_HITS],
        ),
        MESSAGING_DIGEST_TEMPLATE_EN: resolve(
            MESSAGING_DIGEST_TEMPLATE_EN,
            tenant_id=tenant_id,
            default=defaults[MESSAGING_DIGEST_TEMPLATE_EN],
        ) or defaults[MESSAGING_DIGEST_TEMPLATE_EN],
    }
