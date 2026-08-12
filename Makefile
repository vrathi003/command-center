.PHONY: install dev dev-dashboard seed-demo seed-construction seed-construction-replace test lint fmt migrate clean pdf-to-csv install-services install-docs-service configure-tailscale service-status health check-ledger-writes docs docs-serve

XLSX ?= $(HOME)/Documents/Personal/Personal\ Finance/Personal_Finance_OS.xlsx
DB   ?= ~/finance/finance.db

install:
	uv sync
	@if [ -d dashboard ]; then npm install --prefix dashboard; \
	else echo "Skipping npm: no dashboard/ directory (Phase 2)."; fi

dev:
	uv run python start.py

dev-dashboard:
	npm run dev --prefix dashboard

seed-demo:
	uv run python scripts/seed_demo_data.py --force

# Synthetic construction snapshots only — does not touch transactions, budgets, home inventory, etc.
seed-construction:
	uv run python scripts/seed_demo_data.py --construction-only

# Clear construction tables only, then same as seed-construction
seed-construction-replace:
	uv run python scripts/seed_demo_data.py --construction-only --replace-construction

test:
	uv run pytest tests/ -v --asyncio-mode=auto

check-ledger-writes:
	uv run python scripts/ci_check_ledger_writes.py

lint: check-ledger-writes
	uv run ruff check packages/ scripts/ tests/
	uv run mypy packages/

fmt:
	uv run ruff format packages/ scripts/ tests/

migrate:
	uv run python scripts/migrate_from_excel.py \
		--xlsx "$(XLSX)" \
		--db "$(DB)" \
		--report migration_report.json

migrate-dry:
	uv run python scripts/migrate_from_excel.py \
		--xlsx "$(XLSX)" \
		--db "$(DB)" \
		--dry-run

# Usage: make pdf-to-csv PDF=~/Downloads/statement.pdf OUT=~/Downloads/out.csv
# Encrypted PDF: add PASS=secret (passed as -p to the script)
pdf-to-csv:
	uv run python scripts/bank_statement_pdf_to_csv.py "$(PDF)" -o "$(OUT)" \
		$(if $(PASS),-p "$(PASS)",)

# Product guide (Sphinx + MyST) → committed HTML under docs/site/
docs:
	uv run --group docs sphinx-build -b html -d docs/guide/_doctrees docs/guide docs/site

# Port 8080 (API uses 8000). Prefer the systemd service for always-on access.
# Served under /guide/ so MagicDNS + local URLs match (fixes CSS under Tailscale path).
docs-serve: docs
	@echo "Serving docs/site at http://127.0.0.1:8080/guide/"
	uv run python scripts/serve_docs.py --host 127.0.0.1 --port 8080 --directory docs/site

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	rm -rf .mypy_cache .ruff_cache .pytest_cache dashboard/dist docs/guide/_doctrees; \
	true

install-services:
	sudo bash scripts/install_systemd_services.sh

install-docs-service:
	sudo bash scripts/install_docs_service.sh

configure-tailscale:
	bash scripts/configure_tailscale_serve.sh

service-status:
	systemctl status finance-api.service finance-dashboard.service finance-bot.service finance-docs.service

health:
	@echo "== Systemd services =="
	@systemctl --no-pager --full status finance-api.service finance-dashboard.service finance-bot.service finance-docs.service || true
	@echo ""
	@echo "== API health =="
	@curl -fsS http://127.0.0.1:8000/health && echo ""
	@echo ""
	@echo "== Frontend health =="
	@curl -fsS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:4173
	@echo ""
	@echo "== Docs health =="
	@curl -fsS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8080/guide/
	@echo ""
	@echo "== Tailscale serve status =="
	@bash -lc 'if tailscale serve status >/dev/null 2>&1; then tailscale serve status; elif command -v sudo >/dev/null 2>&1; then sudo tailscale serve status; else echo "tailscale serve status unavailable"; fi'
