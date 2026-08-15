---
name: setup-semlf
description: Use when the user asks to install, set up, repair, reconfigure, or uninstall semlf (semantic-linefeeds) on this machine or in this project, or asks why its hook or checker is not running. Installs the CLI when it is missing, repairs a stale install, and writes the project's .semlf.ini.
---

# Set up semlf

`semlf` installs itself.
This skill exists so the agent driving it does not improvise:
no guessed package names, no hand-edited `hooks.json`, no `--force` to make a refusal go away.

Every command below is a real one.
Run them as written, and when one fails, report what it actually printed —
never translate a failure into a guessed cause.

## Gate

Two rules govern the whole procedure, and neither bends.

**Show, then ask, then run.**
Before the first install command, name the exact command and wait for the user to agree.
Before writing any file, show its exact content and wait.
An invocation the user did not intend must end having changed nothing.

**Never `--force`, never `sudo`.**
See [Refusals](#refusals) for what to do instead.

## Step 0 — is it already here?

```bash
semlf --version
```

Answers, go to [step 2](#step-2--verify-and-repair).
Does not, go to step 1.

## Step 1 — install the CLI

Only when step 0 found nothing.
Take the first rung whose tool is present, and ask before running it.

| Rung | Command |
|---|---|
| 1 | `uv tool install semlf` |
| 2 | `pipx install semlf` |
| 3 | `python3 -m pip install --user semlf` |
| 4 | `curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh \| sh -s -- --auto` |

Rung 4 fetches a checkout, so it needs `git`, `curl`, and network reach to GitHub.
It also installs every detected agent's integration by itself, which makes step 2's repair a no-op afterward.
Do not add `--cli` to it: `--auto` already installs the CLI, and the two flags together are a usage error.

Rungs 2 and 3 need an interpreter at 3.9 or newer.
When `python3` is older, list the `python3.*` names on `PATH`, take the newest that qualifies,
and run rung 3 through that interpreter.
For rung 2 the interpreter is the one `pipx` itself runs on,
so `pipx install --python <interpreter> semlf` is the only way to change it.

Two failures worth naming rather than guessing at:
`pip install --user` refuses inside an active virtual environment,
and `PYTHONUSERBASE` can send it outside the home.

When a rung fails, report its real error and try the next.
When all four fail, stop.
There is no fifth path, and inventing one is how machines end up with an install nobody can uninstall.

### Confirm the right binary answers

A previously installed zipapp at `~/.local/bin/semlf` can sit ahead of a new `uv` or `pipx` shim on `PATH`,
and the shadowed one is the one that answers.

```bash
command -v semlf
semlf --version
```

When the resolved path is not the one the installer just reported, say so, name both paths, and stop.
Proceeding would repair the wrong install.

## Step 2 — verify and repair

**If step 1 installed or upgraded anything, run `semlf install` now and skip the check below.**
`semlf doctor` cannot see every kind of staleness — a skill or plugin can sit at old bytes while `doctor` still exits 0 —
so an upgrade is repaired because it happened, not because a health check noticed.

Otherwise:

```bash
semlf doctor
```

Exit 0 means healthy: go to [step 3](#step-3--configure-the-project).

On failure, read what it says before acting.

**Repairable** — a payload reported missing, stale, edited, or pointing at an old checker path.
Show the plan, get agreement, apply:

```bash
semlf install --dry-run     # show this output to the user verbatim
semlf install --yes         # only after they agree
```

`--yes` carries the agreement you already have;
`semlf install` alone exits 1 in a non-interactive shell because its own prompt cannot reach the user through you.
It is never a way to skip asking.

**Not repairable by install.**
This covers a replay failure and an unreadable or malformed `hooks.json`.
It also covers Windows, where an installed Codex hook always fails.
Report these and stop.
Re-running install does not fix them and may refuse outright.

Then confirm:

```bash
semlf doctor
```

### Refusals

`semlf install` refuses rather than overwrite a file whose content it does not recognize.
That refusal is information, not an obstacle.

Show the user the difference between what is installed and what would replace it, and let them decide.
**Never pass `--force` on your own authority.**
It overwrites a user's file, which is a heavier act than adding a suppression directive —
something this project already forbids an agent from doing alone.

Never move, rename, or delete a file that blocks an install.
A backup already sitting in the way is the user's file and the user's call.

## Step 3 — configure the project

Machine-wide setup is done after step 2.
The only per-project file is `.semlf.ini`, at the repository root.

Most projects need none.
`long-limit` already defaults to 120, so offer this step, do not perform it by default.

```ini
[semlf]
long-limit = 120
exclude =
    path/to/generated/
experimental-wrap = false
```

- **`long-limit`** — the advisory length past which a `long` finding appears.
  Default 120.
- **`exclude`** — paths dropped from discovery.
  See the restriction below.
- **`experimental-wrap`** — opt in to `wrap` findings, which never block.
  Default off.

Show the exact file content and get agreement before writing.
When `.semlf.ini` already exists, show a diff and never silently replace it.

**Never author an `exclude` line yourself.**
Excludes suppress discovery, so they are the user's judgment to make and yours only to transcribe.
Write one when the user names it;
never propose one to make a finding go away.

## Uninstall

```bash
semlf uninstall codex        # or: opencode, agentsmd PATH
semlf uninstall codex --dry-run
```

Claude Code is not `semlf`'s to remove — it is managed by the plugin marketplace:

```
claude plugin uninstall semantic-linefeeds@semantic-linefeeds
```

## What this skill never does

- Edit `hooks.json`, a skills directory, a plugin directory, or any installed payload by hand.
  Those belong to `semlf install` and `semlf uninstall`, which record what they wrote so removal works later.
- Pass `--force`, or run anything under `sudo`.
- Set `SEMLF_HOME`, `PYTHONUSERBASE`, or a package manager's destination override to place files outside the home.
- Add an `exclude` or a suppression directive on its own authority.
- Report success it did not verify.
  The evidence is `semlf doctor` exiting 0, not the install command exiting 0.
