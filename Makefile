.DEFAULT_GOAL := help
.PHONY: help install lint format test selfcheck build release publish-token clean precommit

# uv publish reads UV_PUBLISH_TOKEN, a keyring, or a trusted-publishing OIDC token.
# It does not read ~/.pypirc, which is twine's format, so a machine configured for
# twine alone reaches the upload with no credentials at all.
# This bridges the two, with the environment winning wherever it is set —
# the same precedence the checker's own configuration uses.
PYPI_TOKEN = python3 -c 'import configparser, os, sys; c = configparser.ConfigParser(); c.read(os.path.expanduser("~/.pypirc")); sys.stdout.write(c.get("pypi", "password", fallback=""))'

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## Sync the dev environment (uv sync)
	uv sync

lint: ## Check lint rules, no fixes applied
	uv run ruff check .

format: ## Format and auto-fix
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the pytest suite, plus the opencode bun tests when bun is present
	uv run python3 -m pytest tests/ -q
	@if command -v bun >/dev/null 2>&1; then \
		bun test adapters/opencode/; \
	else \
		echo "bun not found, skipping adapters/opencode/ tests"; \
	fi

selfcheck: ## Run semlf's own checker over files changed since HEAD
	@files="$$(git diff --name-only --diff-filter=ACMR HEAD; git ls-files --others --exclude-standard)"; \
	if [ -z "$$files" ]; then \
		echo "no changed files"; \
	else \
		python3 scripts/check_linefeeds.py --file $$files; \
	fi

build: ## Build sdist + wheel into dist/
	uv build --clear

publish-token: ## Report whether a PyPI token is reachable, changing nothing
	@test -n "$${UV_PUBLISH_TOKEN:-$$($(PYPI_TOKEN))}" || { \
		echo "release requires a PyPI token, and none is reachable."; \
		echo "  export UV_PUBLISH_TOKEN=pypi-...   (or put the token in ~/.pypirc under [pypi] as password)"; \
		echo "uv publish does not read ~/.pypirc by itself; this target is what bridges the two."; \
		exit 1; \
	}
	@echo "publish token: found"

# publish-token comes first on purpose, and is a prerequisite rather than a recipe line:
# make runs prerequisites before any recipe, so a machine with no token fails in a second
# instead of after a lint, a build, and two test suites.
release: publish-token lint build ## Build then publish to PyPI after manual confirmation
	uv run python3 -m pytest tests/ -q
	@command -v bun >/dev/null 2>&1 || { echo "release requires bun (see .agents/rules/300-testing.md); install bun and retry"; exit 1; }
	bun test adapters/opencode/
	@echo "About to publish $$(uv run python3 -c 'import sys; sys.path.insert(0, "scripts"); import check_linefeeds; print(check_linefeeds.__version__)') to PyPI."
	@read -p "Type the version above to confirm: " confirm && \
	version="$$(uv run python3 -c 'import sys; sys.path.insert(0, "scripts"); import check_linefeeds; print(check_linefeeds.__version__)')" && \
	if [ "$$confirm" = "$$version" ]; then \
		UV_PUBLISH_TOKEN="$${UV_PUBLISH_TOKEN:-$$($(PYPI_TOKEN))}" uv publish; \
	else \
		echo "Confirmation did not match, aborting."; exit 1; \
	fi

clean: ## Remove build artifacts
	rm -rf dist build *.egg-info cli/semlf.egg-info scripts/semlf.egg-info
	find . -name '__pycache__' -not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} +

precommit: ## Install the pre-commit git hook
	uv run pre-commit install
