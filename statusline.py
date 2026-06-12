#!/usr/bin/env python3
"""claude-statusline entry point.

Claude Code runs this file as the status-line command. It just makes the
sibling `ccstatus` package importable and hands off to the renderer. All the
logic lives in the package; see ccstatus/ for the individual libraries.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ccstatus.render import main

if __name__ == '__main__':
    main()
