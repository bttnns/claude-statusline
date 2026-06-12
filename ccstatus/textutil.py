"""Number coercion/formatting, ANSI-aware width and truncation, terminal width.

The width helpers understand SGR color codes and OSC 8 hyperlinks plus
east-asian and emoji double-width, so the renderer can measure and cut a
colored line by its true on-screen columns.
"""
import os
import re
import unicodedata

from .palette import RESET

env = os.environ.get


# ---- numeric coercion -------------------------------------------------------
def inum(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- human formatting -------------------------------------------------------
def ftok(n):
    """Compact token count: 950, 12.3k, 4.5M."""
    return (f'{(n := float(n)) / 1e6:.1f}M' if n >= 1e6 else
            f'{n / 1e3:.1f}k' if n >= 1e3 else str(int(n)))


def fdur(sec):
    """Reset/projection horizon: decimal hours under a day, decimal days beyond."""
    return ('' if sec is None else 'now' if sec <= 0 else
            f'{sec / 3600:.1f}h' if sec < 86400 else f'{sec / 86400:.1f}d')


def fup(sec):
    """Session uptime: whole minutes under an hour, else decimal hours."""
    return f'{sec // 60}m' if (sec := max(0, sec)) < 3600 else f'{sec / 3600:.1f}h'


# ---- ANSI-aware display width ----------------------------------------------
_OSC = r'\x1b\]8;;[^\x07\x1b]*(?:\x07|\x1b\\)'   # OSC 8 hyperlink wrapper
_SGR = r'\x1b\[[0-9;]*m'                          # color / style
_ESC = re.compile(f'{_OSC}|{_SGR}')


def _chw(ch):
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


def dw(s):
    """On-screen width of a string, ignoring escapes and combining marks."""
    w = 0
    for ch in _ESC.sub('', s):
        if not unicodedata.combining(ch):
            w += _chw(ch)
    return w


def padv(s, n):
    return s + ' ' * max(0, n - dw(s))


def trunc(s, w):
    """Cut a colored string to width `w`, preserving escapes; always reset at end."""
    out, width, i = '', 0, 0
    while i < len(s):
        m = _ESC.match(s, i)
        if m:
            out += m.group(0)
            i = m.end()
            continue
        ch = s[i]
        cw = _chw(ch)
        if width + cw > w:
            break
        out += ch
        width += cw
        i += 1
    return out + RESET


# ---- terminal width ---------------------------------------------------------
def detect_cols():
    """Best-effort terminal column count.

    Claude Code does not export COLUMNS to the status command, so we probe the
    real pty. Critically this NEVER returns 0: a 0 would disable the renderer's
    truncation safety net and let wide lines wrap, which corrupts the redraw.
    """
    v = env('CCSTATUS_COLS')                      # explicit override wins
    if v:
        try:
            n = int(v)
            if n > 0:
                return n
        except ValueError:
            pass
    try:
        n = int(env('COLUMNS') or 0)
        if n > 0:
            return n
    except ValueError:
        pass
    for src in (2, 1, 0):                         # stderr/stdout/stdin, if any is a tty
        try:
            n = os.get_terminal_size(src).columns
            if n > 0:
                return n
        except OSError:
            pass
    try:                                          # controlling terminal (ssh/tmux)
        fd = os.open('/dev/tty', os.O_RDONLY)
        try:
            n = os.get_terminal_size(fd).columns
        finally:
            os.close(fd)
        if n > 0:
            return n
    except OSError:
        pass
    try:                                          # last resort: conservative width
        n = int(env('CCSTATUS_COLS_FALLBACK') or 80)
        return n if n > 0 else 80
    except ValueError:
        return 80
