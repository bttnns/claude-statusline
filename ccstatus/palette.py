"""Colors, the green-to-red heat gradient, and the 24-bit gradient gauge.

Pure and dependency-free: everything here is a string transform. The rest of
the package speaks color only through these helpers.
"""

RESET = '\x1b[0m'
DIM   = '\x1b[2m'
BOLD  = '\x1b[1m'


def rgb(r, g, b):
    return f'\x1b[38;2;{r};{g};{b}m'


GREEN   = rgb(63, 185, 80)
AMBER   = rgb(229, 192, 123)
RED     = rgb(248, 81, 73)
CYAN    = rgb(86, 182, 194)
BLUE    = rgb(97, 175, 239)
MAGENTA = rgb(198, 120, 221)
GREY    = rgb(120, 120, 130)
FRAME   = rgb(92, 96, 104)

SEP        = f' {DIM}·{RESET} '          # the one divider used everywhere
LINK_OPEN  = '\x1b]8;;{}\x1b\\'
LINK_CLOSE = '\x1b]8;;\x1b\\'            # OSC 8 terminator, also a mid-link cut guard


def paint(col, s):
    return col + s + RESET


def d(s):
    return DIM + s + RESET


def fr(s):
    return FRAME + s + RESET


def link(url, s, enabled=True):
    """Wrap text in an OSC 8 hyperlink, or pass it through if disabled."""
    return f'{LINK_OPEN.format(url)}{s}{LINK_CLOSE}' if (enabled and url) else s


# Three-stop gradient: calm green, warning amber, alarming red.
GRADIENT = [(0.0, (63, 185, 80)), (0.55, (210, 153, 34)), (1.0, (248, 81, 73))]


def grad(t):
    """Interpolate the gradient at 0..1, returning an (r, g, b) tuple."""
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(GRADIENT, GRADIENT[1:]):
        if t <= t1:
            f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return GRADIENT[-1][1]


def heat(v):
    """SGR color for a 0..100 percentage along the gradient."""
    return rgb(*grad((v or 0) / 100.0))


def bar(pct, width=10):
    """A 24-bit gradient gauge with eighth-block sub-cell precision."""
    full, rem = divmod(min(width * 8, round(pct / 100.0 * width * 8)), 8)
    cell = lambda i, ch: rgb(*grad((i + 0.5) / width)) + ch
    cells = [cell(i, '█') for i in range(full)]
    if rem and full < width:
        cells.append(cell(full, ' ▏▎▍▌▋▊▉'[rem]))
    return (fr('▏') + ''.join(cells) + RESET
            + GREY + '░' * (width - len(cells)) + RESET + fr('▕'))
