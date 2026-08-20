# DEPLOY-TARGET.md — MOVED

**Purpose:** the AUTHORITATIVE deploy target for GoRefer production — host, nginx, certbot,
systemd units, and the backup host. Read it before any deploy/DNS/TLS decision; if any other
doc disagrees, that file wins.

**It now lives in the PRIVATE repo `gorefer-ops`, at `docs/deploy/DEPLOY-TARGET.md`.**
It names production IP addresses, so it cannot live in this public repository.

- Repo: https://github.com/abhayla/gorefer-ops
- Local clone: `D:\Abhay\Ventures\gorefer-ops` (Windows VPS: `C:\Abhay\Ventures\gorefer-ops`)

Deploy scripts in this repo read the target host from `DEPLOY_SSH_HOSTNAME` (see
`scripts/deploy.sh`), which is set from the untracked `scripts/.deploy-target.env`.
