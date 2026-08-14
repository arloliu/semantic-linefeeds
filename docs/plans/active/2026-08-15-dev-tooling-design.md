# Dev Tooling: Makefile, Ruff, and pre-commit

**Date:** 2026-08-15
**Status:** approved

## Purpose

The repo has no lint/format configuration, no `Makefile`, and no dev-only `.pre-commit-config.yaml`.
This spec adds a standard Python dev workflow — lint, format, test, build, release — without touching the shipped runtime contract.

## Constraints carried over from AGENTS.md and its rules

- `scripts/check_linefeeds.py` stays stdlib-only and Python 3.9+ compatible ([100-project-map.md](../../../.agents/rules/100-project-map.md)).
  Formatting and lint fixes may touch this file; adding a runtime import may not.
- Release to PyPI is a maintainer act, deliberately kept out of repository automation ([ADR-0015](../../decisions/0015-distribution-channels.md)).
  The `Makefile` gives a human a local command to run, not a CI trigger.
- The project already has a self-hosting rule:
  every touched Markdown file must pass `scripts/check_linefeeds.py --file`.
  This spec's own file is written that way.
- `.agents/rules/300-testing.md` names the two commands that already define "tested":
  `python3 -m pytest tests/ -q` and `bun test adapters/opencode/`.
  New tooling wraps these, it does not replace them.

## 1. `pyproject.toml` additions

```toml
[tool.ruff]
target-version = "py39"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "C4", "UP"]
ignore = ["E501"]

[dependency-groups]
dev = ["ruff>=0.8", "pytest>=8", "pre-commit>=4"]
```

`target-version = "py39"` matches `requires-python = ">=3.9"`,
so Ruff's `UP` (pyupgrade) rules never suggest syntax the core can't run.

`E501` (line-too-long) is excluded on purpose.
`scripts/check_linefeeds.py` and `cli/semlf/*.py` already carry single-sentence comments and docstrings past 200 characters,
because this repo's own one-thought-per-line rule keeps a long sentence on one line rather than wrapping it mid-clause.
A character-count line-length lint would flag exactly the lines `semlf` itself protects,
which is the false-positive failure mode [100-project-map.md](../../../.agents/rules/100-project-map.md) calls a bug, not a miss.

`[dependency-groups]` is PEP 735, the form `uv sync` reads natively.
No `build` or `twine` dependency is added: `uv build` and `uv publish` cover both without extra packages.

## 2. `Makefile`

All targets shell out through `uv run` so every contributor and CI runs the same locked tool versions from `uv.lock`, not whatever `uvx` happens to have cached.

| Target | Command | Notes |
|---|---|---|
| `help` (default) | prints target list | |
| `install` | `uv sync` | installs the `dev` dependency group |
| `lint` | `uv run ruff check .` | |
| `format` | `uv run ruff format . && uv run ruff check --fix .` | |
| `test` | `uv run pytest tests/ -q` then `bun test adapters/opencode/` if `bun` is on `PATH` | mirrors [300-testing.md](../../../.agents/rules/300-testing.md) verbatim |
| `selfcheck` | `python3 scripts/check_linefeeds.py --file $(git diff --name-only)` | wraps the existing self-hosting command from `AGENTS.md`, changes nothing about it |
| `build` | `uv build` | sdist + wheel into `dist/` |
| `release` | `lint` + `test` + `build`, prints the version, then `uv publish` only after an explicit confirmation prompt | a local command a maintainer runs by hand, matching [ADR-0015](../../decisions/0015-distribution-channels.md) |
| `clean` | removes `dist/`, `build/`, `*.egg-info/`, `__pycache__/` | |
| `precommit` | `uv run pre-commit install` | |

## 3. `.pre-commit-config.yaml` (new file)

This is the repo's own dev-time config, distinct from `.pre-commit-hooks.yaml`,
which defines the hook this repo ships *to* downstream consumers.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <pinned tag>
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: semlf
        name: semlf semantic linefeeds (self-check)
        entry: uv run semlf --staged
        language: system
        pass_filenames: false
```

The local hook reuses the existing `semlf` CLI entry point instead of inventing a second invocation path.

## 4. Standardize existing code

Run `ruff format` and `ruff check --fix` once across `cli/semlf/`, `scripts/check_linefeeds.py`, `scripts/install.py`, and `tests/*.py`.
This is one mechanical diff (quote style, import order, whitespace).
`scripts/check_linefeeds.py` receives formatting and lint fixes only — no new import, preserving the stdlib-only contract.
The diff is reviewed before commit and kept isolated from any other change.

## Testing

- `make lint` and `make test` both pass after the standardization diff.
- `python3 -m pytest tests/test_packaging.py -q` stays green —
  this spec only adds `[tool.ruff]` and `[dependency-groups]` to `pyproject.toml`,
  it does not touch `[project]` or `[tool.setuptools]`.
- `python3 scripts/check_linefeeds.py --file <touched Markdown>` on this spec file and any other Markdown touched.
- `pre-commit run --all-files` passes once `.pre-commit-config.yaml` lands.

## Out of scope

- Type checking (mypy) — explicitly declined.
- GitHub Actions / CI automation of any kind — none exists today
  and this spec does not add any, consistent with [ADR-0015](../../decisions/0015-distribution-channels.md).
- Reformatting Markdown or non-Python files — Ruff only touches Python; `semlf` already owns Markdown.
