"""Fable5 M1 — concurrent first clicks must NOT twin a referral journey.

Lazy create is check-then-insert; under a WhatsApp blast two requests can pass the
"does it exist?" check simultaneously. The partial UNIQUE constraints turn the loser's
insert into an IntegrityError, which get_or_create swallows and refetches — so exactly
ONE Referral exists and both callers see the same row.

The suite otherwise has no concurrency test (all idempotency is sequential); this fills
that gap for the exact shape the system exists to serve.
"""
from __future__ import annotations

import threading

import pytest
from django.core.management import call_command
from django.db import connections


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_clicks_create_one_referral():
    from apps.referrals.models import Referral
    from apps.referrals.redirect_service import _active_program, _lazy_get_or_create_referral
    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    tenant = get_bootstrap_tenant()
    program = _active_program(tenant)
    client_id = "RJ4521"

    results: list[int] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()  # maximise the race — all threads insert at once
            ref = _lazy_get_or_create_referral(tenant, program, client_id)
            results.append(ref.id)
        except Exception as exc:  # capture, assert none escaped
            errors.append(exc)
        finally:
            connections.close_all()  # each thread owns its connection

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"lazy create raised under concurrency: {errors}"
    # Exactly one referral_link journey for this identity — no twins.
    n = Referral.objects.filter(
        referral_identity__client_id=client_id, source="referral_link"
    ).count()
    assert n == 1, f"expected 1 referral, got {n} (journey twinned)"
    # Every thread resolved to the SAME row.
    assert len(set(results)) == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_partner_direct_create_one_referral():
    from apps.referrals.models import Referral
    from apps.referrals.redirect_service import (
        _active_program,
        _get_or_create_partner_direct_referral,
    )
    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    tenant = get_bootstrap_tenant()
    program = _active_program(tenant)

    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            _get_or_create_partner_direct_referral(tenant, program)
        except Exception as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"partner-direct lazy create raised under concurrency: {errors}"
    n = Referral.objects.filter(referral_identity__isnull=True, source="partner_direct").count()
    assert n == 1, f"expected 1 partner-direct referral, got {n}"
