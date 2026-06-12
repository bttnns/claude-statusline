#!/usr/bin/env python3
"""claude-statusline entry point.

Dual mode: with NO arguments Claude Code runs this as the status-line command
(reads session JSON on stdin, prints the bar). WITH arguments it is a tiny
management CLI: `statusline.py preset words`, `preview`, `doctor`. All logic
lives in the sibling `ccstatus` package.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    if len(sys.argv) > 1:
        from ccstatus.cli import run
        sys.exit(run(sys.argv[1:]))
    from ccstatus.render import main
    main()
