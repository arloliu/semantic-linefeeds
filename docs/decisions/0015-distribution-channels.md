# ADR-0015: Distribution channels

**Status:** accepted
**Date:** 2026-08-14

## Decision

### pipx and uv install from the repository, not a package index

`pipx install git+https://github.com/arloliu/semantic-linefeeds`,
and the equivalent `uv tool install`,
both build `semlf` straight from the repository —
either that URL or a local checkout.
Publishing to PyPI is a maintainer release act,
deliberately left out of repository automation:
nothing here builds or uploads a PyPI artifact,
so the install stays reproducible from a git ref alone,
the same guarantee `install.sh`'s `--repo`/`SEMLF_REPO` already gives the checkout path.

### One `pyproject.toml`, mapping files rather than forking them

`pyproject.toml` declares `cli/semlf` and `scripts/check_linefeeds.py`
as the wheel's contents by `package-dir` mapping,
never by copying either into a packaging-only tree.
[`tests/test_packaging.py`](../../tests/test_packaging.py) pins the mapping:
`packages = ["semlf"]` from `cli/semlf`,
`py-modules = ["check_linefeeds"]` from `scripts`,
the entry point `semlf = "semlf.cli:main"`,
and the version read dynamically off `check_linefeeds.__version__`,
so a release never needs a second place to bump it.
The zipapp builder (`build_pyz`) and the wheel now draw from the same two source locations by two different mechanisms,
never from a packaging fork of either.

### The top-level `check_linefeeds` module name is an accepted trade

The wheel installs `check_linefeeds` as a top-level module beside the `semlf` package,
not nested under it.
`cli/semlf/cli.py` already imports it that way (`import check_linefeeds as core`),
and the zipapp's `__main__.py` stub does the same,
so keeping one import name across every channel is what lets the CLI module serve pipx, uv, and the zipapp without a second code path.
Renaming it into the `semlf` namespace for the wheel would fork the import between channels.
pipx and uv both install into an isolated venv,
so a top-level module name never collides with an unrelated package the way it might on a shared system Python.

### The zipapp remains the air-gapped channel

`install.py --cli` still builds and installs the `semlf` zipapp at `~/.local/bin/semlf`,
through the same `build_pyz` the packaging proof under [`docs/proofs/zipapp-packaging/`](../../docs/proofs/zipapp-packaging/) replays,
unaffected by pipx and uv joining it.
It is the channel for a machine pipx and uv cannot reach:
mirrored, private-network, or air-gapped installs,
the same case `install.sh`'s `--repo`/`SEMLF_REPO` already serves for the checkout path.

### One channel per machine, and three refusals that say so

pipx, uv, and `install.py --cli` all want the same name at `~/.local/bin/semlf`
(or the venv-shim equivalent),
so a machine picks one channel, not several.
Nothing in this repository arbitrates the collision;
three independent, already-shipped refusals surface it instead:
pipx's own refusal to overwrite a foreign file at its install target,
`install_cli`'s refusal to touch a destination that is a symlink rather than its own rendering or a managed one,
and `semlf doctor`'s PATH check,
which warns when `semlf` on `PATH` resolves to a different file than the artifact running doctor.

### The Go option stays unaffected

[ADR-0011](0011-go-port-gated-on-field-evidence.md)'s deferred Go port is untouched by any of this.
Packaging metadata names an implementation —
`setuptools`, a Python `pyproject.toml` —
the contract it ships does not,
and a future Go binary would sit behind the same flags,
config schema, diagnostic schema, and exit codes with no adapter change,
exactly as ADR-0011 already requires.

### pre-commit builds the checkout, not an installed binary

[`.pre-commit-hooks.yaml`](../../.pre-commit-hooks.yaml)'s hook definition uses `language: python`,
so pre-commit builds this repository into its own managed environment,
and `semlf` never needs to be pre-installed or on `PATH` beforehand.
This is a fourth consumer of the same `pyproject.toml`,
not a fourth channel a user installs by hand.

## Evidence

- `pyproject.toml` is the implementation this record describes.
- `tests/test_packaging.py` pins the entry point, the dynamic version,
  both module roots' mapping, and the `>=3.9` floor.
- `cli/semlf/cli.py`'s `import check_linefeeds as core`,
  and the zipapp's `MAIN_STUB` in `scripts/install.py`,
  are why the top-level module name is load-bearing across every channel.
- `scripts/install.py`'s `build_pyz` is the one zipapp builder,
  shared by `install.py --cli` and the packaging proof's `verify.sh`.
- `cli/semlf/doctor.py`'s PATH check
  (`path: warn — semlf resolves to ..., not the artifact running doctor`)
  is the collision evidence doctor surfaces.
- `scripts/install.py`'s `install_cli` symlink refusal is the collision evidence the checkout-side installer surfaces.
- `.pre-commit-hooks.yaml`'s `language: python` is the fourth consumer named above.
- [ADR-0004](0004-portable-core-and-repository-cli.md) already keeps the core one file
  and the CLI a thin router; this record is the packaging shape that keeps both true across channels.

## Alternatives rejected

- **Publishing to PyPI from repository automation.**
  Rejected because a release is a maintainer act with its own review and versioning decision,
  not something a commit to this repository should trigger on its own;
  a `git+URL` install already gives pipx and uv a reproducible source without one.
- **Forking `cli/semlf` or `check_linefeeds.py` into a packaging-only source tree.**
  Rejected for the same reason [ADR-0004](0004-portable-core-and-repository-cli.md) keeps the core one file:
  two copies of either drift,
  and `package-dir` mapping the wheel to the real locations costs nothing a fork would save.
- **Nesting `check_linefeeds` under the `semlf` package for the wheel.**
  Rejected because it would fork the import between the wheel and the zipapp/checkout,
  and venv isolation already removes the top-level-name collision risk a shared system Python would carry.
- **Arbitrating the one-channel-per-machine collision in code** —
  an installer that detects and refuses a foreign channel,
  or a shared lock file naming which channel owns `~/.local/bin/semlf`.
  Rejected as machinery beyond what three independent, already-correct refusals need to add:
  pipx's own refusal, `install_cli`'s refusal, and doctor's PATH check already surface the collision without a fourth mechanism coordinating them.
