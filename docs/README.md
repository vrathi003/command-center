# Documentation

| Path | Purpose |
|------|---------|
| [`site/index.html`](site/index.html) | **Product guide** (committed Sphinx HTML) — start here |
| [`guide/`](guide/) | Sphinx + MyST sources (ledger, workflows, **dashboard**, reference) |
| [`guide/dashboard/`](guide/dashboard/) | Credit cards, Assets, Goals UI (KPIs / sections) |
| [`superpowers/`](superpowers/) | Design specs and implementation plans (not in the guide TOC) |
| `CREDIT_CARDS.md`, `SETUP_AND_OPERATIONS.md`, `2026-08-11-money-engine-changes-brief.md`, … | Standalone topic notes (being folded into the guide over time) |

## Rebuild & serve

Always-on service (port **8080** locally; MagicDNS via Tailscale Serve):

```bash
sudo systemctl restart finance-docs.service   # rebuilds Sphinx HTML, then serves
make configure-tailscale                     # exposes /guide on MagicDNS HTTPS
# local:     http://127.0.0.1:8080/guide/
# MagicDNS:  https://<your-machine>.ts.net/guide/
```

Do **not** use `http://…ts.net:8080` — Serve only publishes **HTTPS on 443**, with docs at path `/guide/`.

`make configure-tailscale` **upserts** `/`, `/api`, and `/guide` only — it does **not** run `serve reset`, so other apps’ handlers on this host stay intact. If `/` is already used by another product, the script skips it; set `FINANCE_TS_DASHBOARD_PATH=/finance` (etc.) to pick a free path.

One-shot local preview:

```bash
make docs          # regenerates docs/site/
make docs-serve    # preview at http://127.0.0.1:8080
```

Requires the `docs` uv dependency group (`uv sync --group docs`). Install/enable the unit with `make install-services` (or `sudo bash scripts/install_systemd_services.sh`).
