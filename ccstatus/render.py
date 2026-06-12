"""Segment builders, layout/compose, the wrap-safe draw, and main().

Each `build_*` turns the gathered Session (`S`) and resolved Config (`C`) into a
colored string, honoring the per-layout feature flags `f`. The git-count and
limit segments are data-driven; main() gathers everything once, then sheds
optional detail (in DROP_ORDER) until the widest row fits the pane.
"""
import sys
import time

from . import config, gitinfo, session, usage
from .palette import (AMBER, BLUE, BOLD, CYAN, DIM, GREEN, GREY, MAGENTA, RED,
                      RESET, SEP, LINK_CLOSE, bar, d, heat, link, paint)
from .textutil import detect_cols, dw, fdur, ftok, fup, trunc
from .treats import treat_text
from .trend import TrendTracker

PR_COLORS = {'approved': GREEN, 'changes_requested': RED, 'pending': AMBER, 'draft': GREY}

# git counts as data: (attr, plural label, symbol prefix, color). Rendered in
# this order for both the symbolic and the plain-words layouts.
_GIT_COUNTS = (
    ('ahead', 'ahead', '⇡', CYAN),
    ('behind', 'behind', '⇣', RED),
    ('staged', 'staged', '+', GREEN),
    ('modified', 'modified', '!', AMBER),
    ('untracked', 'untracked', '?', GREY),
)


def build_title(S, C, f):
    words = C.WORDS
    tl = BOLD + paint(CYAN, S.MODEL)
    if S.CTXMAX > 0:
        tl += SEP + d(ftok(S.CTXMAX).replace('.0', '') + (' context' if words else ' ctx'))
    if S.EFFORT:
        tl += SEP + paint(MAGENTA, S.EFFORT + (' effort' if words else ''))
    if S.ELAPSED >= 60:
        tl += SEP + d(('up ' if words else '⏱ ') + fup(S.ELAPSED))

    tr = d('in' if words else '📁') + ' ' + S.DIRBASE
    g = S.git
    if g.branch:
        btxt = paint(BLUE, g.branch)
        if S.REPO_URL:
            btxt = link(f'{S.REPO_URL}/tree/{g.branch}', btxt, C.LINKS)
        tr += SEP + d('on' if words else '🌿') + ' ' + btxt
        if f['gitcounts']:
            fmt = (lambda lbl, sym, n: f'{n} {lbl}') if words else (lambda lbl, sym, n: f'{sym}{n}')
            parts = [paint(col, fmt(lbl, sym, n))
                     for attr, lbl, sym, col in _GIT_COUNTS if (n := getattr(g, attr))]
            if words:
                tr += (d(' (') + d(', ').join(parts) + d(')')) if parts else ' ' + paint(GREEN, 'clean')
            else:
                tr += ' ' + (' '.join(parts) if parts else paint(GREEN, '✓'))

    if f['pr'] and C.SHOW_PR and S.PR_NUM:
        label = f'PR #{S.PR_NUM}' + (f' ({S.PR_STATE})' if words and S.PR_STATE else '')
        tr += SEP + link(S.PR_URL, paint(PR_COLORS.get(S.PR_STATE, BLUE), label), C.LINKS)
    return tl, tr


def build_rows(S, C, f):
    words = C.WORDS
    # row 1: context gauge + runway (+ cache hit) | cost + burn
    alert = S.PCT >= C.CTX_ALERT
    ctxcol = BOLD + RED if alert else heat(S.PCT)
    lab = paint(BOLD + RED, '⚠ context') if alert else d('context')
    r1l = (lab + ' ' + paint(ctxcol, f'{S.PCT}% full') if words
           else lab + ' ' + bar(S.PCT, C.BAR_W) + ' ' + paint(ctxcol, f'{S.PCT:>3}%'))
    if f['runway']:
        rw = S.tr.runway(S.PCT)
        if rw is not None:
            rwcol = RED if rw <= 300 else (AMBER if rw <= 900 else GREY)
            r1l += ' ' + paint(rwcol, f'~{fup(int(rw))} to compact' if words else f'~{fup(int(rw))} left')
    if f['cache'] and S.SIN > 0:                      # cache hit lives with context (input side)
        cp = S.CACHE * 100 / S.SIN
        r1l += SEP + d('cache hit ' if words else 'cache ') + paint(heat(100 - cp), f'{cp:.0f}%')

    r1r = d('spent' if words else 'cost') + ' ' + paint(GREEN, f'${S.COST:.2f}')
    if f['burn'] and S.ELAPSED >= 120:
        rate = f'${S.COST / (S.ELAPSED / 3600):.0f}/hr'
        r1r += d(f' (~{rate})' if words else f' ~{rate}')

    # row 2: tokens / breakdown / today · line counts · treat
    toks = ftok(S.CTXTOK + S.CTXOUT)
    r2l = (BOLD + toks + RESET + d(' tokens')) if words else (d('tokens') + ' ' + BOLD + toks + RESET)
    if f['breakdown']:
        r2l += d(f' ({ftok(S.CTXTOK)} in / {ftok(S.CTXOUT)} out)' if words
                 else f' ({ftok(S.CTXTOK)}↑/{ftok(S.CTXOUT)}↓)')
    if f['today'] and S.DAILY > 0:
        r2l += SEP + (paint(CYAN, ftok(S.DAILY)) + d(' today') if words
                      else d('Σ ') + paint(CYAN, ftok(S.DAILY)))
    if S.ADDED or S.REMOVED:
        r2l += SEP + (paint(GREEN, f'+{S.ADDED}') + d('/') + paint(RED, f'-{S.REMOVED}') + d(' lines') if words
                      else paint(GREEN, f'+{S.ADDED}') + ' ' + paint(RED, f'-{S.REMOVED}'))
    if f['treat'] and C.SHOW_TREAT and S.COST > 0:
        r2l += SEP + d(treat_text(S.COST, S.SESSION, S.ELAPSED, C.TREAT_BUCKET))
    return r1l, r1r, r2l


def build_window(S, C, label, pct, reset_at, idx, f):
    words = C.WORDS
    arrow = S.tr.arrow(pct, idx)
    seg = (paint(BOLD + RED, '⚠ ' + label) if pct >= C.ALERT_PCT else d(label)) + ' '
    if f['gauges']:
        seg += bar(pct, C.LIMIT_BAR_W) + ' '
    seg += paint(heat(pct), f'{pct:.0f}%' if words else f'{pct:>3.0f}%') + (d(' used') if words else '')
    if arrow:
        seg += ' ' + paint(RED if arrow == '▲' else GREY, arrow)
    rl = fdur(reset_at - S.NOW) if reset_at else ''
    if rl:
        seg += d(f' resets in {rl}') if words else f' {DIM}({RESET}{rl}{DIM}){RESET}'
    return seg


def build_limits(S, C, f):
    windows = [('5h', S.FIVE, S.FIVE_R, 1), ('7d', S.WEEK, S.WEEK_R, 2)]
    segs = [build_window(S, C, lbl, pct, rst, idx, f)
            for lbl, pct, rst, idx in windows if pct is not None]
    return SEP.join(segs)


def compose(S, C, f):
    tl, tr = build_title(S, C, f)
    r1l, r1r, r2l = build_rows(S, C, f)
    # Always exactly 4 rows: Claude Code reserves screen rows from the first
    # render's line count; a later change drifts the reserved area and the
    # prompt redraws into the wrong row.
    rows = [tl + SEP + tr, r1l + SEP + r1r, r2l, build_limits(S, C, f) or '']
    return rows, max(dw(r) for r in rows) + 2


def draw(S, C, rows):
    # frameless: a colored left accent bar per line (heat by context %, red on alert)
    acc = paint(BOLD + RED if S.PCT >= C.CTX_ALERT else heat(S.PCT), '▌')
    lines = [acc + ' ' + r for r in rows]
    if S.COLS:                                        # hard safety net against wrap-corruption
        lines = [trunc(l, S.COLS) + LINK_CLOSE for l in lines]
    return '\n'.join(lines)


def _layouts(flags, drop_order):
    """Yield progressively-stripped flag sets: full, then each drop applied."""
    cur = dict(flags)
    yield dict(cur)
    for k in drop_order:
        cur = {**cur, k: 0}
        yield dict(cur)


def render_text(S, C):
    """Pick the richest layout that fits S.COLS, then draw it (wrap-safe)."""
    rows = None
    for flags in _layouts(C.FLAGS, C.DROP_ORDER):
        rows, width = compose(S, C, flags)
        if not S.COLS or width <= S.COLS:
            break                                     # first layout that fits wins
    # If even the most-stripped layout overflows, render it anyway and let
    # trunc() in draw() cut each row: never change the row count.
    return draw(S, C, rows)


def gather(S, C, now):
    """Populate the dynamic fields on a parsed Session (git, usage, trend, width)."""
    S.NOW = now
    S.COLS = detect_cols()
    S.git = gitinfo.collect(S.DIR, S.SESSION)
    S.SIN, S.SOUT, S.CACHE = usage.session_usage(S.TRANSCRIPT, S.SESSION, C.DAILY_FILE)
    S.DAILY = usage.daily_total(C.DAILY_FILE)
    S.tr = TrendTracker(S.SESSION, now, C.TR_WINDOW, C.TR_SPACING,
                        C.TR_MINHIST, C.TR_RATEMIN).update(S.FIVE, S.WEEK, S.PCT)
    return S


def main():
    C = config.load()
    S = gather(session.read(sys.stdin), C, int(time.time()))
    print(render_text(S, C))
