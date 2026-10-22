.PHONY: install install-web seed reset status api mcp web dev stop test test-web lint clean

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
UVICORN ?= $(VENV)/bin/uvicorn
NPM ?= npm

RUNTIME_DIR := data/runtime
PID_MCP := $(RUNTIME_DIR)/mcp.pid
PID_API := $(RUNTIME_DIR)/api.pid
PID_WEB := $(RUNTIME_DIR)/web.pid
LOG_DIR := /tmp/opencode

all: dev

install:
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -e ".[dev]"

install-web:
	@cd apps/web && $(NPM) install

seed:
	$(PYTHON) -m homeops_core.cli seed

reset:
	$(PYTHON) -m homeops_core.cli reset

status:
	$(PYTHON) -m homeops_core.cli status

api:
	$(UVICORN) homeops_api.main:app --host 127.0.0.1 --port 8000

mcp:
	$(PYTHON) -m homeops_mcp_server.server

web:
	@cd apps/web && $(NPM) run dev -- --host 127.0.0.1 --port 5173

dev:
	@mkdir -p $(RUNTIME_DIR) $(LOG_DIR)
	@echo "Starting HomeOps..."
	@bash -c 'setsid $(PYTHON) -m homeops_mcp_server.server > $(LOG_DIR)/mcp.log 2>&1 < /dev/null & echo $$! > $(PID_MCP)'
	@sleep 2
	@bash -c 'setsid $(UVICORN) homeops_api.main:app --host 127.0.0.1 --port 8000 > $(LOG_DIR)/api.log 2>&1 < /dev/null & echo $$! > $(PID_API)'
	@sleep 2
	@bash -c 'cd apps/web && setsid $(NPM) run dev -- --host 127.0.0.1 --port 5173 > $(LOG_DIR)/web.log 2>&1 < /dev/null & echo $$! > "$(CURDIR)/$(PID_WEB)"'
	@sleep 2
	@echo "MCP: http://127.0.0.1:8001/mcp"
	@echo "API: http://127.0.0.1:8000"
	@echo "Web: http://127.0.0.1:5173"
	@echo "PIDs written to $(RUNTIME_DIR)/"

stop:
	@for pid in $(PID_MCP) $(PID_API) $(PID_WEB); do \
		if [ -f $$pid ]; then \
			pidval=$$(cat $$pid); \
			if [ -n "$$pidval" ]; then \
				kill -TERM -$$pidval 2>/dev/null || kill -TERM $$pidval 2>/dev/null || true; \
				sleep 1; \
				kill -KILL -$$pidval 2>/dev/null || kill -KILL $$pidval 2>/dev/null || true; \
			fi; \
			rm -f $$pid; \
		fi; \
	done
	@echo "Stopped."

test:
	$(PYTHON) -m pytest -v

test-web:
	@cd apps/web && $(NPM) run typecheck && $(NPM) run build

lint:
	$(VENV)/bin/ruff check .

clean:
	rm -rf .pytest_cache $(LOG_DIR) $(RUNTIME_DIR) data/local/homeops.db
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
