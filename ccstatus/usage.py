"""Token accounting: incremental transcript parsing + a daily cross-session counter.

The transcript is append-only, so each render consumes only the bytes added
since the last one (offset cached in /tmp) and folds the delta into both the
session totals and today's running total.
"""
import json
import os
import time

US = '\x1f'   # cache field separator


def daily_total(path, add=0):
    """Today's running new-token total across all sessions; add `add` first if > 0."""
    today = time.strftime('%Y%m%d')
    total = 0
    try:
        day, t = open(path).read().split()
        if day == today:
            total = int(t)
    except (OSError, ValueError):
        pass
    if add > 0:
        total += add
        try:
            open(path, 'w').write(f'{today} {total}')
        except OSError:
            pass
    return total


def session_usage(transcript, session, daily_path):
    """Return (input, output, cache_read) token totals for this session.

    Reads only newly-appended transcript bytes since the cached offset, and
    feeds the new-token delta into the daily counter at `daily_path`.
    """
    if not transcript or not os.path.isfile(transcript):
        return 0, 0, 0

    cache = f'/tmp/ccstatus-tok2-{session}'
    off = i = o = c = 0
    try:
        p = open(cache).read().rstrip('\n').split(US)
        off, i, o, c = int(p[0]), int(p[1]), int(p[2]), int(p[3])
    except (OSError, ValueError, IndexError):
        off = i = o = c = 0

    try:
        size = os.path.getsize(transcript)
    except OSError:
        return i, o, c
    if size < off:                                   # rotated/truncated
        off = i = o = c = 0
    if size <= off:
        return i, o, c

    try:
        with open(transcript, 'rb') as fh:
            fh.seek(off)
            chunk = fh.read()
    except OSError:
        return i, o, c

    nl = chunk.rfind(b'\n')                           # only consume whole lines
    if nl == -1:
        return i, o, c

    bi, bo, bc = i, o, c                              # base totals before this delta
    for raw in chunk[:nl].split(b'\n'):
        if not raw.strip():
            continue
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        u = (m.get('message') or {}).get('usage') or {}
        i += ((u.get('input_tokens') or 0)
              + (u.get('cache_creation_input_tokens') or 0)
              + (u.get('cache_read_input_tokens') or 0))
        o += u.get('output_tokens') or 0
        c += u.get('cache_read_input_tokens') or 0
    off += nl + 1
    try:
        open(cache, 'w').write(US.join(map(str, [off, i, o, c])) + '\n')
    except OSError:
        pass
    daily_total(daily_path, add=(i - bi - (c - bc)) + (o - bo))
    return i, o, c
