#!/usr/bin/env python3
# Claude Code status line: a frameless dashboard panel. Pure Python, no deps.
# Reads the session JSON on stdin, runs git once (cached 5s), sums transcript
# usage incrementally (cached), and renders. No jq/awk/tail subprocesses.
# Tunable via CCSTATUS_* env vars; see README for the full list.
import os, re, sys, json, time, random, subprocess, unicodedata

NOW = int(time.time())
env = os.environ.get

def inum(x, d=0):
    try: return int(float(x))
    except (TypeError, ValueError): return d
def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None

# ---------- read Claude Code's JSON from stdin ----------
try: DATA = json.load(sys.stdin)
except (ValueError, OSError): DATA = {}
def g(*path, default=None):
    cur = DATA
    for k in path:
        if not isinstance(cur, dict): return default
        cur = cur.get(k)
        if cur is None: return default
    return cur

MODEL      = g('model', 'display_name', default='Claude')
DIR        = g('workspace', 'current_dir') or g('cwd') or ''
DIRBASE    = os.path.basename(DIR)
SESSION    = g('session_id', default='default')
EFFORT     = g('effort', 'level', default='') or ''
TRANSCRIPT = g('transcript_path', default='') or ''
PCT        = inum(g('context_window', 'used_percentage', default=0))
CTXTOK     = inum(g('context_window', 'total_input_tokens', default=0))
CTXOUT     = inum(g('context_window', 'total_output_tokens', default=0))
CTXMAX     = inum(g('context_window', 'context_window_size', default=0))
COST       = fnum(g('cost', 'total_cost_usd', default=0)) or 0.0
ADDED      = inum(g('cost', 'total_lines_added', default=0))
REMOVED    = inum(g('cost', 'total_lines_removed', default=0))
ELAPSED    = inum(g('cost', 'total_duration_ms', default=0)) // 1000     # session wall-clock
FIVE       = fnum(g('rate_limits', 'five_hour', 'used_percentage'))
FIVE_R     = inum(g('rate_limits', 'five_hour', 'resets_at', default=0))
WEEK       = fnum(g('rate_limits', 'seven_day', 'used_percentage'))
WEEK_R     = inum(g('rate_limits', 'seven_day', 'resets_at', default=0))
REPO_HOST  = g('workspace', 'repo', 'host', default='') or ''
REPO_OWNER = g('workspace', 'repo', 'owner', default='') or ''
REPO_NAME  = g('workspace', 'repo', 'name', default='') or ''
_pn        = g('pr', 'number', default='')
PR_NUM     = str(_pn) if _pn not in (None, '') else ''
PR_URL     = g('pr', 'url', default='') or ''
PR_STATE   = g('pr', 'review_state', default='') or ''
def _cols():
    # Claude Code does NOT export COLUMNS to the status command, so fall back to the
    # real pty width. Without this the wrap guard below is dead and wide lines wrap,
    # which overflows the reserved status rows and corrupts Claude Code's redraw.
    v = env('CCSTATUS_COLS')                     # explicit override wins
    if v:
        try:
            n = int(v)
            if n > 0: return n
        except ValueError: pass
    try:
        n = int(env('COLUMNS') or 0)
        if n > 0: return n
    except ValueError: pass
    for src in (2, 1, 0):                         # stderr/stdout/stdin, in case one is a tty
        try:
            n = os.get_terminal_size(src).columns
            if n > 0: return n
        except OSError: pass
    try:                                          # controlling terminal (works over ssh/tmux)
        fd = os.open('/dev/tty', os.O_RDONLY)
        try: n = os.get_terminal_size(fd).columns
        finally: os.close(fd)
        if n > 0: return n
    except OSError: pass
    # Detection failed (Claude Code often spawns the status command with piped std
    # streams and no /dev/tty, e.g. during post-compaction redraw). NEVER return 0:
    # that disables the truncation safety net, so wide lines wrap and corrupt the
    # prompt. Fall back to a conservative width so truncation always runs.
    try:
        n = int(env('CCSTATUS_COLS_FALLBACK') or 80)
        return n if n > 0 else 80
    except ValueError: return 80
COLS = _cols()

US = '\x1f'                                   # cache field separator
def fresh(path, ttl):
    try: return (NOW - os.path.getmtime(path)) <= ttl
    except OSError: return False

# ---------- git: one `status --branch --porcelain`, cached 5s ----------
def git_info():
    cache = f'/tmp/ccstatus-git-{SESSION}'
    if fresh(cache, 5):
        try: return open(cache).read().rstrip('\n').split(US)
        except OSError: pass
    branch = ''; ahead = behind = staged = modified = untracked = 0
    try:
        r = subprocess.run(['git', '-C', DIR, 'status', '--porcelain', '--branch'],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            lines = r.stdout.split('\n')
            if lines and lines[0].startswith('## '):
                h = lines[0][3:]
                if h.startswith('HEAD '): branch = 'HEAD'
                elif h.startswith('No commits yet on '):
                    rest = h[len('No commits yet on '):].split(); branch = rest[0] if rest else ''
                else: branch = re.split(r'\.\.\.| ', h, maxsplit=1)[0]
                m = re.search(r'ahead (\d+)', h);  ahead  = int(m.group(1)) if m else 0
                m = re.search(r'behind (\d+)', h); behind = int(m.group(1)) if m else 0
            for ln in lines[1:]:
                if len(ln) >= 2:
                    if ln[0] in 'MADRCU': staged += 1
                    if ln[1] in 'MD':     modified += 1
                    if ln[:2] == '??':    untracked += 1
    except (OSError, subprocess.SubprocessError): pass
    vals = list(map(str, [branch, staged, modified, untracked, ahead, behind]))
    try: open(cache, 'w').write(US.join(vals) + '\n')
    except OSError: pass
    return vals

BRANCH, STAGED, MODIFIED, UNTRACKED, AHEAD, BEHIND = git_info()
STAGED, MODIFIED, UNTRACKED = inum(STAGED), inum(MODIFIED), inum(UNTRACKED)
AHEAD, BEHIND = inum(AHEAD), inum(BEHIND)

# ---------- cross-session "tokens today" counter ----------
DAILY_FILE = os.path.expanduser('~/.claude/ccstatus-daily.txt')
def daily_total(add=0):
    """Today's running new-token total across all sessions; add `add` first if >0."""
    today = time.strftime('%Y%m%d')
    total = 0
    try:
        day, t = open(DAILY_FILE).read().split()
        if day == today: total = int(t)
    except (OSError, ValueError): pass
    if add > 0:
        total += add
        try: open(DAILY_FILE, 'w').write(f'{today} {total}')
        except OSError: pass
    return total

# ---------- session usage: incremental, only newly-appended bytes ----------
# Cache holds "offset in out cache_read". The per-render delta also feeds the
# cross-session "today" counter.
def usage():
    if not TRANSCRIPT or not os.path.isfile(TRANSCRIPT): return 0, 0, 0
    cache = f'/tmp/ccstatus-tok2-{SESSION}'
    off = i = o = c = 0
    try:
        p = open(cache).read().rstrip('\n').split(US)
        off, i, o, c = int(p[0]), int(p[1]), int(p[2]), int(p[3])
    except (OSError, ValueError, IndexError): off = i = o = c = 0
    try: size = os.path.getsize(TRANSCRIPT)
    except OSError: return i, o, c
    if size < off: off = i = o = c = 0               # rotated/truncated
    if size > off:
        try:
            with open(TRANSCRIPT, 'rb') as fh:
                fh.seek(off); chunk = fh.read()
        except OSError: return i, o, c
        nl = chunk.rfind(b'\n')                       # only consume whole lines
        if nl != -1:
            bi, bo, bc = i, o, c                      # base totals before this delta
            for raw in chunk[:nl].split(b'\n'):
                if not raw.strip(): continue
                try: m = json.loads(raw)
                except ValueError: continue
                u = (m.get('message') or {}).get('usage') or {}
                i += (u.get('input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0)
                o += u.get('output_tokens') or 0
                c += u.get('cache_read_input_tokens') or 0
            off = off + nl + 1
            try: open(cache, 'w').write(US.join(map(str, [off, i, o, c])) + '\n')
            except OSError: pass
            daily_total(add=(i - bi - (c - bc)) + (o - bo))   # new tokens in this delta
    return i, o, c

SIN, SOUT, CACHE = usage()
DAILY = daily_total()                      # new tokens across all sessions today

# ---------- config: preset < config file < CCSTATUS_* env var ----------
# Optional config file at ~/.claude/ccstatus.config (override path with
# CCSTATUS_CONFIG). One KEY=VALUE per line, '#' comments. Keys are the names
# below without the CCSTATUS_ prefix, e.g.  PRESET=words  or  BAR_W=12.
CONFIG_PATH = env('CCSTATUS_CONFIG') or os.path.expanduser('~/.claude/ccstatus.config')
FILECFG = {}
try:
    with open(CONFIG_PATH) as _fh:
        for _ln in _fh:
            _ln = _ln.split('#', 1)[0].strip()
            if '=' in _ln:
                _k, _v = _ln.split('=', 1)
                FILECFG[_k.strip().upper()] = _v.strip()
except OSError:
    pass

def cfg(name, default, cast=int):
    v = env('CCSTATUS_' + name)                  # env wins
    if v is None or v == '':
        v = FILECFG.get(name)                    # then config file
    if v is None or v == '':
        return default
    try: return cast(v)
    except (TypeError, ValueError): return default

# PRESET picks the density: full (dense symbols), words (plain English), lean (just the core).
PRESET = cfg('PRESET', 'full', str).strip().lower()
if PRESET not in ('full', 'words', 'lean'): PRESET = 'full'
WORDS  = PRESET == 'words'
LEAN   = PRESET == 'lean'

BAR_W        = cfg('BAR_W', 10)
LIMIT_BAR_W  = cfg('LIMIT_BAR_W', 6)
ALERT_PCT    = cfg('ALERT_PCT', 90)
CTX_ALERT    = cfg('CTX_ALERT', 80)
TREAT_BUCKET = cfg('TREAT_BUCKET', 600)
SHOW_TREAT   = cfg('SHOW_TREAT', 1)
SHOW_PR      = cfg('SHOW_PR', 1)
LINKS        = cfg('LINKS', 1)
TR_WINDOW    = cfg('TR_WINDOW', 1800)
TR_SPACING   = cfg('TR_SPACING', 45)
TR_MINHIST   = cfg('TR_MINHIST', 150)
TR_RATEMIN   = cfg('TR_RATEMIN', 1.0, float)

# ---------- palette ----------
RESET = '\x1b[0m'; DIM = '\x1b[2m'; BOLD = '\x1b[1m'
def rgb(r, g, b): return f'\x1b[38;2;{r};{g};{b}m'
GREEN   = rgb(63, 185, 80)
AMBER   = rgb(229, 192, 123)
RED     = rgb(248, 81, 73)
CYAN    = rgb(86, 182, 194)
BLUE    = rgb(97, 175, 239)
MAGENTA = rgb(198, 120, 221)
GREY    = rgb(120, 120, 130)
FRAME   = rgb(92, 96, 104)
def paint(col, s): return col + s + RESET
def d(s):  return DIM + s + RESET
def fr(s): return FRAME + s + RESET
def link(url, s):
    return f'\x1b]8;;{url}\x1b\\{s}\x1b]8;;\x1b\\' if (LINKS and url) else s
SEP = f' {DIM}·{RESET} '                # the one divider used everywhere

GRADIENT = [(0.0, (63, 185, 80)), (0.55, (210, 153, 34)), (1.0, (248, 81, 73))]
def grad(t):
    t = max(0.0, min(1.0, t))
    for i in range(len(GRADIENT) - 1):
        t0, c0 = GRADIENT[i]; t1, c1 = GRADIENT[i + 1]
        if t <= t1:
            f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return GRADIENT[-1][1]
def heat(v): return rgb(*grad((v or 0) / 100.0))

# ---------- formatters ----------
def ftok(n):
    n = float(n)
    if n >= 1e6: return f'{n/1e6:.1f}M'
    if n >= 1e3: return f'{n/1e3:.1f}k'
    return str(int(n))
def fdur(sec):                      # decimal hours under a day, decimal days beyond (reset/projection)
    if sec is None: return ''
    if sec <= 0: return 'now'
    if sec < 86400: return f'{sec / 3600:.1f}h'
    return f'{sec / 86400:.1f}d'
def fup(sec):                       # session uptime: m under an hour, else decimal hours
    sec = max(0, sec)
    if sec < 3600: return f'{sec // 60}m'
    return f'{sec / 3600:.1f}h'

# ---------- ANSI-aware display width / truncation ----------
_OSC = r'\x1b\]8;;[^\x07\x1b]*(?:\x07|\x1b\\)'   # OSC 8 hyperlink wrapper
_SGR = r'\x1b\[[0-9;]*m'                          # color / style
_ESC = re.compile(f'{_OSC}|{_SGR}')
def dw(s):
    s = _ESC.sub('', s)
    w = 0
    for ch in s:
        if unicodedata.combining(ch): continue
        w += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return w
def padv(s, n): return s + ' ' * max(0, n - dw(s))
def trunc(s, w):
    out, width, i = '', 0, 0
    while i < len(s):
        m = _ESC.match(s, i)
        if m: out += m.group(0); i = m.end(); continue
        ch = s[i]; cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if width + cw > w: break
        out += ch; width += cw; i += 1
    return out + RESET

# ---------- 24-bit gradient gauge (eighth-block precision) ----------
def bar(pct, width=BAR_W):
    PART = ' ▏▎▍▌▋▊▉'
    eighths = min(width * 8, round(pct / 100.0 * width * 8))
    full, rem = divmod(eighths, 8)
    out, used = '', 0
    for i in range(full):
        out += rgb(*grad((i + 0.5) / width)) + '█'; used += 1
    if rem and full < width:
        out += rgb(*grad((full + 0.5) / width)) + PART[rem]; used += 1
    out += RESET + GREY + '░' * (width - used) + RESET
    return fr('▏') + out + fr('▕')

# ---------- trend sampling: 5h % · 7d % · context % over the session ----------
RF = f'/tmp/ccstatus-rate-{SESSION}'
samples, pruned = [], False
try:
    with open(RF) as f:
        for line in f:
            p = line.split()
            if len(p) >= 3:
                if NOW - int(p[0]) <= TR_WINDOW:
                    pc = p[3] if len(p) >= 4 else 'na'          # context % (older files lack it)
                    samples.append((int(p[0]), p[1], p[2], pc))
                else: pruned = True
except OSError:
    pass
def _s(v): return f'{v:.2f}' if v is not None else 'na'
appended = (not samples) or (NOW - samples[-1][0] >= TR_SPACING)
if appended:
    samples.append((NOW, _s(FIVE), _s(WEEK), _s(float(PCT))))
if appended or pruned:
    try:
        with open(RF, 'w') as f:
            f.writelines(f'{s[0]} {s[1]} {s[2]} {s[3]}\n' for s in samples)
    except OSError:
        pass

def series(idx):                      # [(ts, value)] history for one sample column
    return [(s[0], fnum(s[idx])) for s in samples if fnum(s[idx]) is not None]

def trend(cur, idx):                  # ▲ climbing · → steady · '' too little history
    if cur is None: return ''
    hist = series(idx)
    if not hist: return ''
    ts, bv = hist[0]; dt = NOW - ts
    if dt < TR_MINHIST: return ''
    return '▲' if (cur - bv) / dt * 3600.0 >= TR_RATEMIN else '→'

def runway():                         # seconds until context % is projected to hit 100
    hist = series(3)
    if len(hist) < 2: return None
    ts, bv = hist[0]; dt = NOW - ts
    if dt < TR_MINHIST: return None
    rate = (PCT - bv) / dt            # %/sec; only project while genuinely climbing
    if rate <= 0: return None
    return (100 - PCT) / rate

# ---------- cost treat (rerolls every TREAT_BUCKET of session time) ----------
TREATS = [
    ('☕', 'lattes', 5.45),       ('🍕', 'pizza slices', 3.50), ('🌮', 'tacos', 2.50),
    ('🍺', 'craft beers', 7.00),  ('🍩', 'donuts', 1.50),       ('🥑', 'avocados', 2.00),
    ('🍌', 'bananas', 0.30),      ('🍔', 'Big Macs', 5.99),     ('🍦', 'ice creams', 4.00),
    ('🧋', 'boba teas', 6.50),    ('🥐', 'croissants', 3.75),   ('🍪', 'cookies', 2.25),
    ('🍫', 'chocolate bars', 2.50),('🍣', 'sushi rolls', 8.00), ('🥓', 'bacon strips', 1.00),
    ('🍟', 'fries', 3.00),        ('🌯', 'burritos', 9.50),     ('🥤', 'sodas', 2.00),
    ('🧁', 'cupcakes', 3.50),     ('🍎', 'apples', 0.80),       ('🥨', 'pretzels', 4.00),
    ('🍿', 'popcorn tubs', 8.50), ('🍭', 'lollipops', 0.50),    ('🥯', 'bagels', 2.00),
    ('🍵', 'matcha lattes', 5.75),('🍷', 'wine glasses', 11.0), ('🦪', 'oysters', 3.50),
    ('🍤', 'shrimp', 1.25),       ('🧀', 'cheese wedges', 6.00),('⛽', 'gas gallons', 3.50),
    ('🍰', 'cake slices', 5.50),  ('🥧', 'pies', 12.0),         ('🍮', 'puddings', 3.00),
    ('🍬', 'candies', 0.40),      ('🥃', 'whiskey shots', 9.00),('🍸', 'cocktails', 13.0),
    ('🍹', 'margaritas', 12.0),   ('🧃', 'juice boxes', 1.00),  ('🥖', 'baguettes', 3.50),
    ('🧇', 'waffles', 4.50),      ('🥞', 'pancake stacks', 8.00),('🌭', 'hot dogs', 2.50),
    ('🥪', 'sandwiches', 7.50),   ('🥗', 'salads', 11.0),       ('🍜', 'ramen bowls', 13.0),
    ('🥟', 'dumplings', 1.50),    ('🦞', 'lobster rolls', 25.0),('🍳', 'eggs', 0.35),
    ('🎟️', 'movie tickets', 15.0),('🚌', 'bus fares', 2.75),    ('🔋', 'AA batteries', 1.00),
    ('🧦', 'pairs of socks', 8.00),('🪥', 'toothbrushes', 4.00),('✏️', 'pencils', 0.25),
]
def treat_text():
    e, l, p = random.Random(f'{SESSION}:{ELAPSED // TREAT_BUCKET}').choice(TREATS)
    return f'{e} {COST / p:.1f} {l}'

# ---------- segment builders (flags control optional detail) ----------
PR_COLORS = {'approved': GREEN, 'changes_requested': RED, 'pending': AMBER, 'draft': GREY}
REPO_URL = f'https://{REPO_HOST}/{REPO_OWNER}/{REPO_NAME}' if (REPO_HOST and REPO_OWNER and REPO_NAME) else ''

def build_title(f):
    tl = BOLD + paint(CYAN, MODEL)
    if CTXMAX > 0: tl += SEP + d(ftok(CTXMAX).replace('.0', '') + (' context' if WORDS else ' ctx'))
    if EFFORT: tl += SEP + paint(MAGENTA, EFFORT + (' effort' if WORDS else ''))
    if ELAPSED >= 60: tl += SEP + d(('up ' if WORDS else '⏱ ') + fup(ELAPSED))
    tr = d('in' if WORDS else '📁') + ' ' + DIRBASE
    if BRANCH:
        btxt = paint(BLUE, BRANCH)
        if REPO_URL: btxt = link(f'{REPO_URL}/tree/{BRANCH}', btxt)
        tr += SEP + d('on' if WORDS else '🌿') + ' ' + btxt
        if f['gitcounts']:
            gc = []
            if WORDS:
                if AHEAD:     gc.append(paint(CYAN,  f'{AHEAD} ahead'))
                if BEHIND:    gc.append(paint(RED,   f'{BEHIND} behind'))
                if STAGED:    gc.append(paint(GREEN, f'{STAGED} staged'))
                if MODIFIED:  gc.append(paint(AMBER, f'{MODIFIED} modified'))
                if UNTRACKED: gc.append(paint(GREY,  f'{UNTRACKED} untracked'))
                if gc: tr += d(' (') + d(', ').join(gc) + d(')')
                else:  tr += ' ' + paint(GREEN, 'clean')
            else:
                if AHEAD:     gc.append(paint(CYAN,  f'⇡{AHEAD}'))
                if BEHIND:    gc.append(paint(RED,   f'⇣{BEHIND}'))
                if STAGED:    gc.append(paint(GREEN, f'+{STAGED}'))
                if MODIFIED:  gc.append(paint(AMBER, f'!{MODIFIED}'))
                if UNTRACKED: gc.append(paint(GREY,  f'?{UNTRACKED}'))
                tr += ' ' + (' '.join(gc) if gc else paint(GREEN, '✓'))
    if f['pr'] and SHOW_PR and PR_NUM:
        label = f'PR #{PR_NUM}' + (f' ({PR_STATE})' if WORDS and PR_STATE else '')
        badge = paint(PR_COLORS.get(PR_STATE, BLUE), label)
        tr += SEP + link(PR_URL, badge)
    return tl, tr

def build_rows(f):
    # row 1: context gauge + runway/sparkline (+ cache hit) | cost
    alert = PCT >= CTX_ALERT
    ctxcol = BOLD + RED if alert else heat(PCT)
    if WORDS:
        lab = paint(BOLD + RED, '⚠ context') if alert else d('context')
        r1l = lab + ' ' + paint(ctxcol, f'{PCT}% full')
    else:
        lab = paint(BOLD + RED, '⚠ context') if alert else d('context')
        r1l = lab + ' ' + bar(PCT) + ' ' + paint(ctxcol, f'{PCT:>3}%')
    if f['runway']:
        rw = runway()
        if rw is not None:
            rwcol = RED if rw <= 300 else (AMBER if rw <= 900 else GREY)
            r1l += ' ' + paint(rwcol, f'~{fup(int(rw))} to compact' if WORDS else f'~{fup(int(rw))} left')
    if f['cache'] and SIN > 0:                       # cache hit lives with context (input-side)
        cp = CACHE * 100 / SIN
        r1l += SEP + d('cache hit ' if WORDS else 'cache ') + paint(heat(100 - cp), f'{cp:.0f}%')
    if WORDS:
        r1r = d('spent') + ' ' + paint(GREEN, f'${COST:.2f}')
        if f['burn'] and ELAPSED >= 120:
            r1r += d(f' (~${COST / (ELAPSED / 3600):.0f}/hr)')
    else:
        r1r = d('cost') + ' ' + paint(GREEN, f'${COST:.2f}')
        if f['burn'] and ELAPSED >= 120:
            r1r += d(f' ~${COST / (ELAPSED / 3600):.0f}/hr')
    # row 2: tokens / breakdown / today · line counts · treat (usage + whimsy)
    r2l = BOLD + ftok(CTXTOK + CTXOUT) + RESET + d(' tokens') if WORDS else d('tokens') + ' ' + BOLD + ftok(CTXTOK + CTXOUT) + RESET
    if f['breakdown']:
        r2l += d(f' ({ftok(CTXTOK)} in / {ftok(CTXOUT)} out)' if WORDS else f' ({ftok(CTXTOK)}↑/{ftok(CTXOUT)}↓)')
    if f['today'] and DAILY > 0:
        r2l += SEP + (paint(CYAN, ftok(DAILY)) + d(' today') if WORDS else d('Σ ') + paint(CYAN, ftok(DAILY)))
    if ADDED or REMOVED:
        if WORDS:
            r2l += SEP + paint(GREEN, f'+{ADDED}') + d('/') + paint(RED, f'-{REMOVED}') + d(' lines')
        else:
            r2l += SEP + paint(GREEN, f'+{ADDED}') + ' ' + paint(RED, f'-{REMOVED}')
    if f['treat'] and SHOW_TREAT and COST > 0:
        r2l += SEP + d(treat_text())
    return r1l, r1r, r2l

def build_window(label, pct, reset_at, idx, f):
    arrow = trend(pct, idx)
    lab = paint(BOLD + RED, '⚠ ' + label) if pct >= ALERT_PCT else d(label)
    seg = lab + ' '
    if f['gauges']: seg += bar(pct, LIMIT_BAR_W) + ' '
    pctstr = f'{pct:.0f}%' if WORDS else f'{pct:>3.0f}%'
    seg += paint(heat(pct), pctstr) + (d(' used') if WORDS else '')
    if arrow: seg += ' ' + paint(RED if arrow == '▲' else GREY, arrow)
    rl = fdur(reset_at - NOW) if reset_at else ''
    if rl:
        seg += d(f' resets in {rl}') if WORDS else f' {DIM}({RESET}{rl}{DIM}){RESET}'
    return seg

def build_limits(f):
    out = ''
    if FIVE is not None: out = build_window('5h', FIVE, FIVE_R, 1, f)
    if WEEK is not None: out += (SEP if out else '') + build_window('7d', WEEK, WEEK_R, 2, f)
    return out

# ---------- compose + draw ----------
def compose(f):
    tl, tr = build_title(f)
    r1l, r1r, r2l = build_rows(f)
    r2r = build_limits(f)
    header = tl + SEP + tr
    # Always 4 rows. Claude Code reserves screen rows from the first render's line
    # count; if that count later changes (rate-limit data appears, or compact() fires
    # mid-session) the reserved area drifts and the prompt redraws into the wrong row.
    rows = [header, r1l + SEP + r1r, r2l, r2r or '']
    W = max(dw(r) for r in rows) + 2
    return tl, tr, rows, W

LINK_CLOSE = '\x1b]8;;\x1b\\'                     # OSC 8 terminator, in case a cut lands mid-link
def draw(tl, tr, rows, W):
    # frameless: a colored left accent bar per line (heat by context %, red on alert)
    ACC = paint(BOLD + RED if PCT >= CTX_ALERT else heat(PCT), '▌')
    lines = [ACC + ' ' + c for c in rows]
    if COLS:                                     # hard safety net: a line wider than the pane
        lines = [trunc(l, COLS) + LINK_CLOSE for l in lines]   # wraps and corrupts the redraw
    return '\n'.join(lines)

def compact():
    s = BOLD + paint(CYAN, MODEL) + RESET + ' ' + paint(heat(PCT), f'{PCT}%')
    s += ' ' + paint(GREEN, f'${COST:.2f}') + ' ' + d('tok') + ' ' + ftok(CTXTOK)
    if DAILY > 0: s += ' ' + d('Σ') + ' ' + ftok(DAILY)
    if FIVE is not None: s += ' ' + d('5h') + ' ' + paint(heat(FIVE), f'{FIVE:.0f}%')
    if WEEK is not None: s += ' ' + d('7d') + ' ' + paint(heat(WEEK), f'{WEEK:.0f}%')
    return trunc(s, COLS) if COLS else s

# progressive shedding: drop the least essential detail until it fits.
# The preset sets the starting flag set; lean begins already stripped to the core.
if LEAN:
    FLAGS = dict(treat=0, burn=0, cache=0, breakdown=0, today=0, gauges=1, pr=0, gitcounts=0, runway=0)
else:   # full and words start with everything; words renders it in plain English
    FLAGS = dict(treat=1, burn=1, cache=1, breakdown=1, today=1, gauges=not WORDS, pr=1, gitcounts=1, runway=1)
DROP_ORDER = ['treat', 'burn', 'breakdown', 'gauges', 'pr', 'gitcounts', 'today', 'cache', 'runway']
seq = [dict(FLAGS)]
cur = dict(FLAGS)
for k in DROP_ORDER:
    cur = dict(cur); cur[k] = 0; seq.append(dict(cur))

chosen = None
for fl in seq:
    parts = compose(fl)
    if not COLS or parts[-1] <= COLS:
        chosen = parts; break
# Never fall through to a different row count: if even the most-stripped layout
# doesn't fit, render it anyway and let trunc() in draw() cut each row to COLS.
# The single-line compact() path would change Claude Code's reserved row count and
# corrupt the prompt redraw.
if chosen is None: chosen = compose(seq[-1])
print(draw(*chosen))
