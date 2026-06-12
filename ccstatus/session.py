"""Parse Claude Code's session JSON (stdin) into one flat Session struct."""
import json
import os
from types import SimpleNamespace

from .textutil import inum, fnum


def _getter(data):
    def g(*path, default=None):
        cur = data
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
            if cur is None:
                return default
        return cur
    return g


def read(stream):
    """Read and normalize the session payload into a SimpleNamespace.

    Unknown/missing fields degrade to sensible empties so every downstream
    segment can be written as if its data is always present.
    """
    try:
        data = json.load(stream)
    except (ValueError, OSError):
        data = {}
    g = _getter(data)

    repo_host  = g('workspace', 'repo', 'host', default='') or ''
    repo_owner = g('workspace', 'repo', 'owner', default='') or ''
    repo_name  = g('workspace', 'repo', 'name', default='') or ''
    repo_url = (f'https://{repo_host}/{repo_owner}/{repo_name}'
                if (repo_host and repo_owner and repo_name) else '')
    pn = g('pr', 'number', default='')
    directory = g('workspace', 'current_dir') or g('cwd') or ''

    return SimpleNamespace(
        MODEL      = g('model', 'display_name', default='Claude'),
        DIR        = directory,
        DIRBASE    = os.path.basename(directory),
        SESSION    = g('session_id', default='default'),
        EFFORT     = g('effort', 'level', default='') or '',
        TRANSCRIPT = g('transcript_path', default='') or '',
        PCT        = inum(g('context_window', 'used_percentage', default=0)),
        CTXTOK     = inum(g('context_window', 'total_input_tokens', default=0)),
        CTXOUT     = inum(g('context_window', 'total_output_tokens', default=0)),
        CTXMAX     = inum(g('context_window', 'context_window_size', default=0)),
        COST       = fnum(g('cost', 'total_cost_usd', default=0)) or 0.0,
        ADDED      = inum(g('cost', 'total_lines_added', default=0)),
        REMOVED    = inum(g('cost', 'total_lines_removed', default=0)),
        ELAPSED    = inum(g('cost', 'total_duration_ms', default=0)) // 1000,
        FIVE       = fnum(g('rate_limits', 'five_hour', 'used_percentage')),
        FIVE_R     = inum(g('rate_limits', 'five_hour', 'resets_at', default=0)),
        WEEK       = fnum(g('rate_limits', 'seven_day', 'used_percentage')),
        WEEK_R     = inum(g('rate_limits', 'seven_day', 'resets_at', default=0)),
        REPO_URL   = repo_url,
        PR_NUM     = str(pn) if pn not in (None, '') else '',
        PR_URL     = g('pr', 'url', default='') or '',
        PR_STATE   = g('pr', 'review_state', default='') or '',
    )
