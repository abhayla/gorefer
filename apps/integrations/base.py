"""Adapter boundary marker — the real port Protocols land in Phase 2 (doc 16 §3.3).

Phase 0 (doc 16 D-3): this module previously declared a stale `WatiAdapter`
Protocol (one method, out of date) and a duplicate `LogOnlyWatiAdapter` that
NOTHING imported — dead code masquerading as the boundary contract. A future
adapter author would have implemented the wrong interface. Both were removed.

Until the Phase-2 role-ports (`MessagingPort`, `CrmPort` — ADR-039, doc 16 §3.3)
are defined here, the de-facto vendor contracts are the concrete adapter surfaces:

- WhatsApp BSP: `apps/integrations/wati/adapter.py`
  (`LiveWatiAdapter` / `LogOnlyWatiAdapter`, selected by `get_wati_adapter()`)
- CRM write:   `apps/integrations/zoho/adapter.py` (`get_zoho_adapter()`)
- CRM read:    `apps/integrations/zoho/read.py` (`get_zoho_read_adapter()`)

Any replacement adapter must additionally honor the five role-level invariants of
ADR-039 (terminal delivery status, never fabricate status, never auto-submit,
lead-saved-first, contract docs move with adapter code).
"""
from __future__ import annotations
