# Documentation

| Path | Purpose |
|------|---------|
| [`site/index.html`](site/index.html) | **Product guide** (committed Sphinx HTML) — start here |
| [`guide/`](guide/) | Sphinx + MyST sources for the product guide |
| [`superpowers/`](superpowers/) | Design specs and implementation plans (not in the guide TOC) |
| `CREDIT_CARDS.md`, `SETUP_AND_OPERATIONS.md`, … | Standalone topic notes (being folded into the guide over time) |

## Rebuild

```bash
make docs          # regenerates docs/site/
make docs-serve    # preview at http://127.0.0.1:8000
```

Requires the `docs` uv dependency group (`uv sync --group docs`).
