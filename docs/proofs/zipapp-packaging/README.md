# Zipapp packaging proof

This proof claims one thing:
the portable core and the repository CLI can ship as one stdlib-only artifact,
and the core is not forked to do it.

## Build recipe

The proof builds through `install.build_pyz` in `scripts/install.py` —
the same function the installer uses for `semlf --cli`.
There is no second build recipe here to drift from the one that ships.
The packaged `semlf` sources are `cli/semlf/`, never a committed copy —
a committed copy is exactly the staleness this proof exists to catch.

## Running it

```sh
sh docs/proofs/zipapp-packaging/verify.sh
```

Every row must print `ok`.
The script rebuilds the archive from this repository's current sources,
so a stale artifact can never pass silently.

## Limits

`verify.sh` prints its own recorded limits at the end of a run —
see its trailing lines for what this proof does and does not cover.
