# AGENTS.md

For agents installing or tweaking **claude-statusline**. `statusline.py` is a thin entry point Claude Code runs as its status line; the logic lives in the `ccstatus/` package (one library per concern). Reads session JSON on stdin, prints 4 lines. No deps.

## Install
One command (copies the package to `~/.claude/claude-statusline/` and merges `settings.json`, backup first):
```sh
curl -fsSL https://raw.githubusercontent.com/bttnns/claude-statusline/main/install.sh | bash
```
From a local clone: `./install.sh`. Honor `CLAUDE_CONFIG_DIR` if set (defaults to `~/.claude`).

## Configure
Precedence: preset < config file < env var.
- **Preset:** `CCSTATUS_PRESET=full|words|lean` (full = dense, words = plain English, lean = core).
- **File:** `~/.claude/ccstatus.config`, one `KEY=VALUE` per line (keys are `CCSTATUS_*` names without the prefix), e.g. `PRESET=words`.
- **Env:** any `CCSTATUS_*`. Full list is in the README config table.

## Verify / test
```sh
python3 -m unittest discover -s tests
echo '{"model":{"display_name":"Opus"},"context_window":{"used_percentage":42},"cost":{"total_cost_usd":1.23}}' | python3 statusline.py
```

## Package map
`palette` colors/gauge · `textutil` width+formatting · `session` parse JSON · `config` settings · `gitinfo` git · `usage` tokens · `trend` runway/arrows · `treats` snacks · `render` builders+main.

## Rules
- Always emit exactly 4 rows and never let a line wrap; either breaks Claude Code's redraw.
- For demos, point `CCSTATUS_DAILY_FILE` at a throwaway file. Never write the real `~/.claude/ccstatus-daily.txt`.
- No em-dashes anywhere. Keep the tests green.
