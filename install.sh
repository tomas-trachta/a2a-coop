#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
bin_dir="$HOME/.local/bin"

python=$(command -v python3 || command -v python || true)
if [[ -z "$python" ]] || ! "$python" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "a2a-coop needs Python 3.10 or newer." >&2
    exit 1
fi

if command -v uv >/dev/null; then
    uv tool install --editable . --force
elif command -v pipx >/dev/null; then
    pipx install --editable . --force
else
    "$python" -m venv .venv
    .venv/bin/python -m pip install --quiet --editable .
    mkdir -p "$bin_dir"
    ln -sf "$PWD/.venv/bin/a2a-coop" "$bin_dir/a2a-coop"
fi

a2a_coop=$(command -v a2a-coop || echo "$bin_dir/a2a-coop")
"$a2a_coop" setup

case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) echo; echo "Add $bin_dir to your PATH to run \`a2a-coop\` from anywhere." ;;
esac
