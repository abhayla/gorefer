# Frozen shared links — the GitHub setting only the owner can switch on

The frozen-link gate (CLAUDE.md §6h) has two checks that run on every pull request:

| Check | What it guards |
|---|---|
| `test` (workflow "CI") | Every link in `docs/links/frozen-links.json` still lands where it did |
| `frozen-links` (workflow "Frozen links") | The frozen list itself is changed only with your approval label |

**Until you make them required, they only warn: a failing PR can still be merged.**

## Switch it on (once, about 3 minutes, on github.com)

1. Open `github.com/abhayla/gorefer` → **Settings** → **Rules** → **Rulesets** → **New ruleset** → **New branch ruleset**.
2. **Ruleset name:** `main is protected`. **Enforcement status:** `Active`.
3. **Bypass list:** leave it **empty**. An empty list means nobody, you included, can skip the rule by accident.
4. **Target branches** → **Add target** → **Include default branch**.
5. Tick:
   - **Restrict deletions**
   - **Block force pushes**
   - **Require a pull request before merging** (required approvals: `0`, since you can't approve your own PRs)
   - **Require status checks to pass** → **Add checks** → add `test` and `frozen-links`.
6. **Create**.

The `frozen-links` check only appears in the "Add checks" search after it has run once on a PR, which it does after this change is merged.

## Approving a link change

When a PR really should change where an old link goes:

1. Read the `frozen-links` check's output on the PR. It lists every frozen link that changes, before → after.
2. If you agree, add the label **`link-change-approved`** to the PR, **by hand on github.com** (PR page → Labels). A label added by Claude or any app is ignored by design.
3. If more commits are pushed afterwards, the approval no longer counts: remove the label and add it again once you've checked the new changes.
