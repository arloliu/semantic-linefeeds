#!/bin/sh
# Curl-able bootstrapper for semantic-linefeeds.
# It fetches (or updates) a checkout into $SEMLF_HOME,
# then hands off every remaining argument to scripts/install.py.
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --codex
#
# Private mirror (curl the raw script from the mirror, point SEMLF_REPO back at it)
# or a pinned ref:
#   curl -fsSL https://git.internal/you/semantic-linefeeds/-/raw/main/install.sh |
#     SEMLF_REPO=git@git.internal:you/semantic-linefeeds.git sh -s -- --codex
#   SEMLF_REPO=git@example.com:you/semantic-linefeeds.git SEMLF_REF=v0.4.0 sh install.sh --codex
#
# --repo/--home/--ref (or the SEMLF_REPO/SEMLF_HOME/SEMLF_REF env vars)
# are consumed here;
# everything else — --codex, --opencode, --agentsmd, --cli, --dry-run, --force,
# or no arguments at all — passes straight through to install.py.
set -eu

repo="${SEMLF_REPO:-https://github.com/arloliu/semantic-linefeeds.git}"
# Left empty when neither --home nor SEMLF_HOME is given;
# filled in lazily below, after argument parsing,
# so an unset $HOME does not blow up a run that passes --home explicitly.
home_dir="${SEMLF_HOME:-}"
ref="${SEMLF_REF:-}"

# --repo (by flag or env) disables the self-checkout shortcut below,
# so track whether either form was used.
repo_given=false
[ -n "${SEMLF_REPO:-}" ] && repo_given=true

# Quote a single argument for safe reinsertion into a `set --` string:
# wrap it in single quotes,
# escaping any single quotes it already contains with the close-escape-reopen sequence '\''.
# The sed script needs a doubled backslash
# so sed itself sees one backslash in its replacement text, not zero.
quote_arg() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Split argv into what install.sh consumes (--repo/--home/--ref)
# and everything else,
# which is rebuilt below with `eval "set -- $pass"`
# so spaces in, say, an --agentsmd path survive untouched.
pass=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo)
            [ "$#" -ge 2 ] || { echo "install.sh: --repo needs a value" >&2; exit 64; }
            repo="$2"
            repo_given=true
            shift 2
            ;;
        --home)
            [ "$#" -ge 2 ] || { echo "install.sh: --home needs a value" >&2; exit 64; }
            home_dir="$2"
            shift 2
            ;;
        --ref)
            [ "$#" -ge 2 ] || { echo "install.sh: --ref needs a value" >&2; exit 64; }
            ref="$2"
            shift 2
            ;;
        *)
            pass="$pass $(quote_arg "$1")"
            shift
            ;;
    esac
done
eval "set -- $pass"

# Reject an option-lookalike ref (from either --ref or SEMLF_REF) up front,
# so it can never be parsed as a git option
# when it reaches `fetch origin "$ref"` or `clone --branch "$ref"` below.
case "$ref" in
    -*)
        echo "install.sh: --ref value must not start with '-': $ref" >&2
        exit 64
        ;;
esac

# Self-checkout: a piped run has $0 = sh, so it never matches this case
# and always falls through to the fetch path below.
self_checkout=false
case "$0" in
    *install.sh)
        self_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
        if [ "$repo_given" = false ] && [ -f "$self_dir/scripts/check_linefeeds.py" ]; then
            if [ -z "$ref" ]; then
                home_dir="$self_dir"
                self_checkout=true
            else
                # A pinned ref means the caller wants a specific version,
                # not just whatever this checkout currently has checked out.
                # Fetch it from this checkout's own directory,
                # instead of taking the install-in-place shortcut.
                repo="$self_dir"
            fi
        fi
        ;;
esac

# The default home lives under $HOME,
# but it is only computed now, once self-checkout has had its chance to skip fetching entirely,
# so an unset $HOME never blocks a run that passes --home explicitly.
if [ "$self_checkout" = false ] && [ -z "$home_dir" ]; then
    if [ -n "${XDG_DATA_HOME:-}" ]; then
        home_dir="$XDG_DATA_HOME/semantic-linefeeds"
    elif [ -n "${HOME:-}" ]; then
        home_dir="$HOME/.local/share/semantic-linefeeds"
    else
        echo "install.sh: cannot determine an install location;" \
             "pass --home or set SEMLF_HOME, XDG_DATA_HOME, or HOME" >&2
        exit 1
    fi
fi

if [ "$self_checkout" = false ]; then
    command -v git >/dev/null 2>&1 || {
        echo "install.sh: git is required but was not found on PATH" >&2
        exit 1
    }
    if [ -d "$home_dir/.git" ]; then
        if [ -n "$ref" ]; then
            # A pinned ref leaves a detached HEAD,
            # so re-fetch and re-detach rather than pull --ff-only,
            # which fails once HEAD is off any branch.
            git -C "$home_dir" fetch --quiet origin "$ref"
            git -C "$home_dir" checkout --quiet --detach FETCH_HEAD
            echo "semantic-linefeeds: already cloned in $home_dir; checked out $ref"
        else
            git -C "$home_dir" pull --ff-only --quiet
            echo "semantic-linefeeds: already cloned in $home_dir; pulled latest"
        fi
    else
        if [ -n "$ref" ]; then
            # --quiet does not suppress the detached-HEAD advice on a --branch clone,
            # so silence it explicitly to keep this a quiet install.
            git -c advice.detachedHead=false \
                clone --quiet --branch "$ref" -- "$repo" "$home_dir"
        else
            git clone --quiet -- "$repo" "$home_dir"
        fi
        echo "semantic-linefeeds: cloned $repo into $home_dir"
    fi
fi

command -v python3 >/dev/null 2>&1 || {
    echo "install.sh: python3 is required but was not found on PATH" >&2
    exit 1
}

exec python3 "$home_dir/scripts/install.py" "$@"
