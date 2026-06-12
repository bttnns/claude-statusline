#!/usr/bin/env bash
# claude-statusline installer.
#
#   Local clone:  ./install.sh
#   One-liner:    curl -fsSL https://raw.githubusercontent.com/bttnns/claude-statusline/main/install.sh | bash
#
# Copies the package into ~/.claude/claude-statusline and points Claude Code's
# statusLine at it by safely merging ~/.claude/settings.json (a timestamped
# backup is written first). Re-running is safe and idempotent.
set -euo pipefail

REPO="https://github.com/bttnns/claude-statusline"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CLAUDE_DIR/claude-statusline"
ENTRY="$DEST/statusline.py"

say() { printf '\033[1;36m▌\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is required but not found."

# 1. Locate the source: this clone if present, otherwise fetch a fresh copy.
SRC=""
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SELF_DIR" ] && [ -d "$SELF_DIR/ccstatus" ]; then
  SRC="$SELF_DIR"
else
  command -v git >/dev/null 2>&1 || die "git is required to fetch the repo."
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "Fetching $REPO ..."
  git clone --depth 1 "$REPO" "$TMP/repo" >/dev/null 2>&1 || die "clone failed."
  SRC="$TMP/repo"
fi

# 2. Install the package files.
say "Installing into $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/ccstatus"
cp -R "$SRC/ccstatus" "$DEST/ccstatus"
cp "$SRC/statusline.py" "$ENTRY"
chmod +x "$ENTRY"

# 3. Merge the statusLine block into settings.json (backup first).
say "Updating $CLAUDE_DIR/settings.json"
SETTINGS="$CLAUDE_DIR/settings.json" ENTRY="$ENTRY" python3 - <<'PY'
import json, os, shutil, time
settings = os.environ["SETTINGS"]
entry = os.environ["ENTRY"]
os.makedirs(os.path.dirname(settings), exist_ok=True)
data = {}
if os.path.exists(settings):
    shutil.copy(settings, f"{settings}.bak.{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        with open(settings) as fh:
            data = json.load(fh) or {}
    except ValueError:
        raise SystemExit(f"{settings} is not valid JSON; refusing to overwrite. Edit it by hand.")
data["statusLine"] = {"type": "command", "command": entry, "padding": 1, "refreshInterval": 10}
with open(settings, "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY

say "Done. Open a new Claude Code session (or run /resume) to see it."
printf '  Try presets:  \033[2mexport CCSTATUS_PRESET=words\033[0m  (or words / lean)\n'
