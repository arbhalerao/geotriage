BOOTSTRAP_PYTHON ?= python3
VENV             := .venv
PYTHON           := $(VENV)/bin/python
DEPS             := $(VENV)/.installed
PY_SOURCES       := backend tools

REGISTRY         ?= localhost

# The contract lives in its own repo but the platform imports it, so the built wheel is
# committed under backend/vendor/. A fresh clone builds with nothing else present.
# See backend/vendor/README.md. It changes only when the contract changes -- adding a
# model or a provider is a container image and never touches this.
VENDOR           := backend/vendor

# A sibling checkout, if you happen to have one. Two uses, both development-only:
# `make install` installs the contract editable so changes there are live, and
# `make vendor-sdk` rebuilds the wheel above. The images never look at it.
SDK_DIR          ?= ../geotriage-sdk

COMPOSE          ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help venv install test fmt fmt-check check typecheck \
        vendor-sdk vendor-check sdk-image builtins examples up down down-v restart build logs ps migrate psql clean

help:  ## print this help
	@grep -hE '^[a-z][a-zA-Z0-9_-]*:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip

$(DEPS): $(PYTHON) backend/requirements.app.txt backend/requirements.worker.txt \
         backend/requirements.dev.txt $(wildcard $(SDK_DIR)/pyproject.toml)
	$(PYTHON) -m pip install \
		-r backend/requirements.app.txt \
		-r backend/requirements.worker.txt \
		-r backend/requirements.dev.txt
	@if [ -f "$(SDK_DIR)/pyproject.toml" ]; then \
		echo "geotriage-sdk: editable from $(SDK_DIR)"; \
		$(PYTHON) -m pip install -e $(SDK_DIR); \
	else \
		echo "geotriage-sdk: vendored wheel"; \
		$(PYTHON) -m pip install --force-reinstall $(VENDOR)/*.whl; \
	fi
	@touch $(DEPS)

venv: $(PYTHON)  ## create .venv if missing

install: $(DEPS)  ## install the platform, plus the contract (editable if $(SDK_DIR) exists)

test: $(DEPS)  ## run the test suite
	$(PYTHON) -m pytest

fmt: $(DEPS)  ## format with black
	$(PYTHON) -m black $(PY_SOURCES)

fmt-check: $(DEPS)  ## check formatting without changing anything
	$(PYTHON) -m black --check $(PY_SOURCES)

typecheck:  ## typecheck the frontend
	cd frontend && npx --no-install tsc --noEmit

vendor-check:  ## fail if the vendored contract is behind $(SDK_DIR) (skipped without it)
	@python3 tools/vendor_check.py $(VENDOR) $(SDK_DIR)

check: fmt-check test typecheck vendor-check  ## everything CI would run

# Only needed when the contract itself changes. Regenerates the wheel and the note
# recording which commit it came from, so the two never drift apart.
vendor-sdk:  ## rebuild the vendored contract wheel from $(SDK_DIR)
	@test -f "$(SDK_DIR)/pyproject.toml" \
		|| { echo "no contract checkout at $(SDK_DIR) -- set SDK_DIR"; exit 1; }
	$(MAKE) -C $(SDK_DIR) build
	@rm -f $(VENDOR)/*.whl
	@cp $(SDK_DIR)/dist/*.whl $(VENDOR)/
	@python3 tools/vendor_note.py $(VENDOR) $(SDK_DIR)
	@echo "vendored: $$(ls $(VENDOR)/*.whl) -- rebuild the images with 'make build'"

sdk-image:  ## build the base image authors build FROM (in $(SDK_DIR))
	$(MAKE) -C $(SDK_DIR) image REGISTRY=$(REGISTRY)

builtins:  ## build the four images the platform registers as its defaults
	$(MAKE) -C $(SDK_DIR) builtins REGISTRY=$(REGISTRY)

examples:  ## build the defaults plus a third-party model and two that fail on purpose
	$(MAKE) -C $(SDK_DIR) examples REGISTRY=$(REGISTRY)

up:  ## start everything
	$(COMPOSE) up -d

down:  ## stop everything (volumes are kept; pass -v yourself to wipe the database)
	$(COMPOSE) down

down-v:  ## stop everything, including volumes
	$(COMPOSE) down -v

build:  ## rebuild the application images
	$(COMPOSE) build api worker frontend

restart: build  ## rebuild and restart the application services
	$(COMPOSE) up -d --force-recreate api worker frontend

logs:  ## follow the api and worker logs
	$(COMPOSE) logs -f api worker

ps:  ## what is running
	$(COMPOSE) ps

migrate:  ## apply database migrations
	$(COMPOSE) exec api alembic upgrade head

psql:  ## open a database shell
	$(COMPOSE) exec postgres psql -U geotriage -d geotriage

clean:  ## remove the venv, caches and build artifacts (leaves docker alone)
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.egg-info' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(VENV) .pytest_cache frontend/dist
