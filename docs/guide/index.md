# Personal Finance OS Guide

Self-hosted personal finance platform: Discord bot → SQLite → FastAPI → React dashboard.
This site is the **product manual** for understanding how money moves through the system —
especially the **double-entry ledger**.

:::{admonition} How to read this site
:class: tip

- **Operator path** — start at {doc}`getting-started`, then {doc}`workflows/index`.
- **Internals path** — start at {doc}`ledger/overview` and work through each ledger page.
- Open the committed HTML at ``docs/site/index.html`` after ``make docs``, or serve with ``make docs-serve``.
:::

## Contents

```{toctree}
:maxdepth: 2
:caption: Start here

getting-started
```

```{toctree}
:maxdepth: 2
:caption: Ledger

ledger/index
```

```{toctree}
:maxdepth: 2
:caption: Day-to-day workflows

workflows/index
```

```{toctree}
:maxdepth: 2
:caption: Dashboard

dashboard/index
```

```{toctree}
:maxdepth: 2
:caption: Reference (stubs + API)

reference/index
```

## Rebuild the site

Always-on (systemd, port **8080** locally; MagicDNS at ``/guide/``):

```bash
sudo systemctl restart finance-docs.service   # rebuild + serve
make configure-tailscale                      # once: map /guide on Tailscale Serve
# local:    http://127.0.0.1:8080/guide/
# MagicDNS: https://<host>.ts.net/guide/
```

One-shot:

```bash
make docs          # writes HTML into docs/site/
make docs-serve    # http://127.0.0.1:8080
```

Sources live in ``docs/guide/`` (MyST Markdown). Design specs and implementation plans stay under ``docs/superpowers/`` and are **not** part of this TOC.
