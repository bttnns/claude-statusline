# AGENTS.md

For agents installing or tweaking **claude-statusline**. It is one Python 3 file, `statusline.py`, that reads Claude Code's session JSON on stdin and prints a 4-line dashboard. No deps.

## Install
```sh
cp statusline.py ~/.claude/statusline.py && chmod +x ~/.claude/statusline.py
```
Then merge into `~/.claude/settings.json`:
```json
{ "statusLine": { "type": "command", "command": "~/.claude/statusline.py", "padding": 1, "refreshInterval": 10 } }
```

## Configure
Precedence: preset < config file < env var.
- **Preset:** `CCSTATUS_PRESET=full|words|lean` (full = dense, words = plain English, lean = core).
- **File:** `~/.claude/ccstatus.config`, one `KEY=VALUE` per line (keys are `CCSTATUS_*` names without the prefix), e.g. `PRESET=words`.
- **Env:** any `CCSTATUS_*`. Full list is in the README config table.

## Preview / verify
```sh
echo '{"model":{"display_name":"Opus"},"context_window":{"used_percentage":42},"cost":{"total_cost_usd":1.23}}' | python3 statusline.py
```

## Rules
- Always emit exactly 4 rows and never let a line wrap; either breaks Claude Code's redraw.
- For demos, point `CCSTATUS_DAILY_FILE` at a throwaway file. Never write the real `~/.claude/ccstatus-daily.txt`.
- No em-dashes anywhere.
