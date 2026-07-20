# Moved to Wati-Project (owner decision, Abhay 2026-07-19)

Reusable Wati platform know-how is filed with the platform, so every project on the shared
Wati account `105355` can use it. The following files LEFT this folder on 2026-07-19:

| Was here | Now lives at | Note |
|---|---|---|
| `WATI-TEMPLATE-CREATION-RULE.md` | `C:\Abhay\5Wealths\Wati-Project\docs\wati-shared-template-whole-flow-rule.md` | The "design the whole flow" standing rule — platform-wide; GoRefer examples kept as worked examples |
| `WATI-TEMPLATE-NAMING-CONVENTION.md` | `C:\Abhay\5Wealths\Wati-Project\docs\wati-shared-template-naming-convention.md` | Generalized: `<projectPrefix>_…` with a prefix registry (`gr` = GoRefer) |
| `WATI-TEMPLATE-INVENTORY.md` | `_source-archive\WATI-TEMPLATE-INVENTORY-2026-07-17-SUPERSEDED.md` | NOT moved to Wati-Project — it was a stale 2026-07-17 snapshot, superseded on BOTH halves: GoRefer side by `Wati-GoRefer\Wati-GoRefer-Templates.md`, account side by `Wati-Project\docs\wati-templates.json` |

**What deliberately STAYS in this repo** (a GoRefer code change can invalidate them — the §6b
CI gate needs them next to the code): `Wati-GoRefer\` (integration contract + role→template map),
`apps\integrations\wati\wati-templates.json` (the code manifest),
`docs\integrations\08-Zoho-WATI-Integration.md` (numbered spec set), and the
`WATI-lead-capture-templates-PROPOSAL.md` draft (GoRefer-specific history).

Zoho counterpart of this move: the webhook-signer Deluge code was extracted from
`Zoho-GoRefer\Zoho-Signer-Steps.md` to `C:\Abhay\5Wealths\Zoho-Project\deluge\gorefer_webhook_signer.dg`
(filed by owning system); the steps doc remains and points there.
