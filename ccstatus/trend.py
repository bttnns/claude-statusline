"""Rolling trend samples for 5h % / 7d % / context %, with runway projection.

Each render appends a timestamped sample to /tmp (rate-limited by spacing) and
prunes anything older than the window. From that short history we derive the
small trend arrows and the "context runway": a projection of how long until the
context window is full, assuming the current fill rate holds.
"""
import os

from .textutil import fnum


class TrendTracker:
    # sample columns: (timestamp, five%, seven%, context%)
    _FIVE, _WEEK, _CTX = 1, 2, 3

    def __init__(self, session, now, window, spacing, minhist, ratemin):
        self.now = now
        self.window = window
        self.spacing = spacing
        self.minhist = minhist
        self.ratemin = ratemin
        self.path = f'/tmp/ccstatus-rate-{session}'
        self.samples = []

    def update(self, five, week, pct):
        """Load recent samples, append the current one if due, and persist."""
        samples, pruned = [], False
        try:
            with open(self.path) as fh:
                for line in fh:
                    p = line.split()
                    if len(p) >= 3:
                        if self.now - int(p[0]) <= self.window:
                            ctx = p[3] if len(p) >= 4 else 'na'
                            samples.append((int(p[0]), p[1], p[2], ctx))
                        else:
                            pruned = True
        except OSError:
            pass

        fmt = lambda v: f'{v:.2f}' if v is not None else 'na'
        due = (not samples) or (self.now - samples[-1][0] >= self.spacing)
        if due:
            samples.append((self.now, fmt(five), fmt(week), fmt(float(pct))))
        if due or pruned:
            try:
                with open(self.path, 'w') as fh:
                    fh.writelines(f'{s[0]} {s[1]} {s[2]} {s[3]}\n' for s in samples)
            except OSError:
                pass
        self.samples = samples
        return self

    def _series(self, idx):
        return [(s[0], fnum(s[idx])) for s in self.samples if fnum(s[idx]) is not None]

    def arrow(self, cur, idx):
        """▲ climbing, → steady, '' when there is too little history yet."""
        if cur is None:
            return ''
        hist = self._series(idx)
        if not hist:
            return ''
        ts, base = hist[0]
        dt = self.now - ts
        if dt < self.minhist:
            return ''
        return '▲' if (cur - base) / dt * 3600.0 >= self.ratemin else '→'

    def runway(self, pct):
        """Seconds until context % is projected to reach 100, or None."""
        hist = self._series(self._CTX)
        if len(hist) < 2:
            return None
        ts, base = hist[0]
        dt = self.now - ts
        if dt < self.minhist:
            return None
        rate = (pct - base) / dt          # %/sec; only project while climbing
        if rate <= 0:
            return None
        return (100 - pct) / rate
