# Findings registry

A finding is knowledge that must stay reachable; an issue is a work item that closes. Proven findings live here.

How to add one:

1. Create `docs/reviews/failure-classes/<slug>.json` (the file name must equal `slug`). Copy an existing file.
2. Write it as a CLASS: `class_symptom` and `mechanism` are generic; the one instance goes in `first_seen` with real counts. Keep this repo public: no mobile numbers, host addresses, client names or visitor IPs.
3. Prove it first: `measurements` holds the query and its counts, the log line, or the file:line. An unproven observation is not a finding.
4. `detection.status` is `unguarded` (with a `reason`) until a named check or gate covers the class, then `guarded` (with `check`).
5. Run `python scripts/build_findings_registry.py` and commit the regenerated `FINDINGS.md`. CI runs `--check` and fails on a stale aggregate. Never hand-edit `FINDINGS.md`.
