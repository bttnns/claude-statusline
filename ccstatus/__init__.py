"""claude-statusline: a frameless, preset-driven status line for Claude Code.

The package is split into focused libraries:
  palette   - colors, heat gradient, the 24-bit gauge
  textutil  - number formatting, ANSI-aware width/truncation, terminal width
  session   - parse Claude Code's session JSON from stdin
  config    - resolve preset + config file + env into one settings object
  gitinfo   - one cached `git status` into a small struct
  usage     - incremental transcript token accounting + daily counter
  trend     - rate sampling, trend arrows, context runway projection
  treats    - the cost-in-snacks "treat" data and picker
  render    - segment builders, compose/draw, and main()
"""
__version__ = '1.0.0'
