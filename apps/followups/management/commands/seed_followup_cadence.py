"""Configure an AP's follow-up cadence (idempotent).

Default = the owner's spec: a SESSION nudge **every 3 hours through the 24h window**
(so +3h, +6h, … +21h — the +24h boundary is excluded because the window closes then).
Quiet hours (23:00–06:00 IST, no sends) and a min-gap between sends are enforced by the
send gate at fire time, so a step that lands at night is deferred to 06:00 IST and two
nudges never reach a contact as a burst.

**Each step gets DISTINCT copy** (rotating through STEP_BODIES) — never the same message
repeated, which reads as spam. Copy is UTILITY "in-progress" framing (an update on the
contact's OWN pending account opening), never a promotional re-solicitation — so the
nudges stay honestly transactional. Bodies are editable per-step afterwards via the CRUD
API / admin; re-running this command updates them in place.

This seeds `FollowupRule` rows only — it deliberately does NOT flip `followups_enabled`.

Bodies carry a `{program_brand}` placeholder (T-059), resolved at FIRE time from the
tenant's active program (apps.referrals.branding) — never a hard-coded partner name.
Copy is stored on each `FollowupRule` row at SEED time, not re-read from this module,
so re-running this command is what pushes an updated STEP_BODIES/STEP_BODIES_HI wording
onto rows already scheduled — it does not happen on deploy alone.

    python manage.py seed_followup_cadence
    python manage.py seed_followup_cadence --interval-hours 3 --horizon-hours 24 --tenant pifs
    python manage.py seed_followup_cadence --stop-on-reply false   # keep firing after a reply (test mode)
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.followups.models import FollowupRule
from apps.tenants.models import Tenant

# Distinct, in-progress-framed copy — one per step, cycled if there are more steps than
# lines. NO promotional claims (keeps the nudge UTILITY-appropriate); reply-to-engage CTA.
# {program_brand} is resolved at FIRE time (apps.followups.tasks._apply) via the T-056
# fallback chain (apps.referrals.branding) — never a hard-coded partner name, so a
# second program (Groww, ...) renders correctly with no code change (T-059). Changing
# this list only reaches PENDING sends after an operator re-runs this command — see
# the module docstring.
STEP_BODIES = [
    "Hi! Your {program_brand} account opening is still pending — reply here and we'll help you "
    "complete it in a couple of minutes.",
    "Quick nudge: your {program_brand} account is almost set up. Reply here and we'll finish the "
    "last steps with you.",
    "Still need a hand with your {program_brand} account? Reply here and we'll guide you through "
    "what's left.",
    "We can complete your {program_brand} account opening over a short call today — reply here and "
    "we'll ring you.",
    "Your {program_brand} account is one step away from ready. Reply here and we'll wrap it up "
    "together.",
    "Almost there on your {program_brand} account — reply here and we'll take it to the finish line.",
    "Last check-in for today on your {program_brand} account setup — reply anytime and we'll help "
    "you complete it.",
]


# Hindi cadence — ORIGINAL copy, NOT a translation of STEP_BODIES (owner instruction
# 2026-07-27). Written for how a Hindi-speaking prospect is actually spoken to on WhatsApp:
# polite आप-form, short sentences, and the natural Hindi/English code-mixing real users
# write ("reply", "call", "account") rather than stilted pure-Devanagari equivalents. The
# beats escalate like the English cadence, but the wording is its own — the 12h step offers
# a call, the 21h step closes the day gently rather than pressing.
#
# Same discipline as the English: in-progress framing about the contact's OWN pending
# account, reply-to-engage CTA, and NO promotional claims — so the nudge stays honestly
# transactional.
STEP_BODIES_HI = [
    "नमस्ते! आपका {program_brand} अकाउंट अभी पूरा नहीं हुआ है। कहीं कुछ अटक रहा हो तो यहीं बता "
    "दीजिए — दो मिनट में पूरा करा देंगे।",
    "थोड़ा ही बाकी है — आपका {program_brand} अकाउंट लगभग तैयार है। यहीं reply कीजिए, आखिरी steps "
    "हम साथ में पूरे कर देते हैं।",
    "{program_brand} अकाउंट खोलने में कोई मदद चाहिए? जो भी सवाल हो, यहीं पूछ लीजिए — आगे क्या "
    "करना है, हम बता देंगे।",
    "चाहें तो आज एक छोटी सी call पर आपका {program_brand} अकाउंट पूरा करा देते हैं। यहीं reply "
    "कीजिए, हम आपको कॉल कर लेंगे।",
    "आपका {program_brand} अकाउंट बस एक कदम दूर है। यहीं reply कीजिए — साथ मिलकर पूरा कर लेते हैं।",
    "बस पूरा ही होने वाला है आपका {program_brand} अकाउंट — यहीं reply कीजिए, बाकी हम संभाल लेते हैं।",
    "आज के लिए आखिरी बार पूछ रहे हैं — आपका {program_brand} अकाउंट अधूरा रह गया है। जब भी समय "
    "मिले, यहीं reply कर दीजिए।",
]


def _as_bool(raw) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# A ready prospect should be able to open right away, credited to their referrer — the
# send path (apps.followups.tasks._apply) substitutes {link} with the resolved referral
# link (gorefer.in/r/wa/{referrer_client_id}, or gorefer.in/open as a fallback), per doc 15.
LINK_CTA = "\n\nReady now? Open your account here: {link}"
LINK_CTA_HI = "\n\nअभी खोलना चाहें तो यहाँ से: {link}"


def _body_for_step(index: int) -> str:
    """Distinct copy for step `index` (0-based); cycles + numbers if steps exceed the list.

    Every body carries the {link} placeholder so a ready prospect gets a one-tap,
    credit-preserving open link (resolved + substituted at send time).
    """
    base = STEP_BODIES[index % len(STEP_BODIES)]
    if index >= len(STEP_BODIES):
        base = f"{base} (reminder {index + 1})"
    return f"{base}{LINK_CTA}"


def _body_for_step_hi(index: int) -> str:
    """Hindi copy for step `index` (0-based). Same cycling rule as the English.

    Seeded so `body_hi` is NEVER blank: an empty value makes `services.body_for()` fall
    back to English, which is exactly how every Hindi-preferring prospect silently
    received the English cadence until 2026-07-27.
    """
    base = STEP_BODIES_HI[index % len(STEP_BODIES_HI)]
    if index >= len(STEP_BODIES_HI):
        base = f"{base} (रिमाइंडर {index + 1})"
    return f"{base}{LINK_CTA_HI}"


class Command(BaseCommand):
    help = "Idempotently seed an AP's follow-up cadence (every Nh through Hh, session, distinct copy)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="pifs", help="Tenant slug (default: pifs).")
        parser.add_argument("--interval-hours", type=int, default=3)
        parser.add_argument("--horizon-hours", type=int, default=24)
        parser.add_argument("--stop-on-reply", default="true",
                            help="Cancel remaining steps once the contact replies (default true).")

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"No tenant with slug '{opts['tenant']}'. Run seed_program first.")

        interval = opts["interval_hours"]
        horizon = opts["horizon_hours"]
        if interval <= 0 or horizon <= 0:
            raise CommandError("--interval-hours and --horizon-hours must be positive.")

        stop_on_reply = _as_bool(opts["stop_on_reply"])
        hours = list(range(interval, horizon, interval))  # steps strictly INSIDE the window
        if not hours:
            raise CommandError("No steps fit — interval must be smaller than horizon.")

        created = updated = 0
        for order, h in enumerate(hours, start=1):
            _, was_created = FollowupRule.objects.update_or_create(
                tenant=tenant,
                step_key=f"nudge_{h}h",
                defaults=dict(
                    offset_minutes=h * 60,
                    channel=FollowupRule.CHANNEL_SESSION,
                    template_name="",
                    body_en=_body_for_step(order - 1),  # DISTINCT per step
                    body_hi=_body_for_step_hi(order - 1),  # never blank — see _body_for_step_hi
                    enabled=True,
                    only_if_window_open=True,   # session-only; no out-of-window template fallback
                    stop_on_reply=stop_on_reply,
                    order=order,
                ),
            )
            created += was_created
            updated += (not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Cadence for '{tenant.slug}': {len(hours)} steps every {interval}h through {horizon}h "
            f"({created} created, {updated} updated) — session, DISTINCT copy, stop_on_reply={stop_on_reply}."
        ))
        self.stdout.write(
            "Quiet hours 23:00–06:00 IST + a min-gap between sends are enforced at send time "
            "(no overnight sends, no bursts). This did NOT enable sending — set `followups_enabled` "
            "true for the tenant to go live."
        )
