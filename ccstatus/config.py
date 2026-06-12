"""Resolve settings from three layers: preset defaults < config file < env var.

A `CCSTATUS_<NAME>` environment variable always wins; otherwise an optional
`~/.claude/ccstatus.config` (KEY=VALUE, '#' comments) supplies durable
defaults; otherwise the preset's baseline applies.
"""
import os
from types import SimpleNamespace

env = os.environ.get

PRESETS = ('full', 'words', 'lean')

# Which optional segments each preset starts with. `gauges` for words is set
# below (words is text-forward, so it drops the gauges). Progressive shedding
# removes these in DROP_ORDER until the line fits.
DROP_ORDER = ['treat', 'burn', 'breakdown', 'gauges', 'pr',
              'gitcounts', 'today', 'cache', 'runway']


def _load_file(path):
    cfg = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.split('#', 1)[0].strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    cfg[k.strip().upper()] = v.strip()
    except OSError:
        pass
    return cfg


def load():
    """Return a SimpleNamespace of all resolved settings + the preset flags."""
    config_path = env('CCSTATUS_CONFIG') or os.path.expanduser('~/.claude/ccstatus.config')
    filecfg = _load_file(config_path)

    def cfg(name, default, cast=int):
        v = env('CCSTATUS_' + name)
        if v is None or v == '':
            v = filecfg.get(name)
        if v is None or v == '':
            return default
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

    preset = cfg('PRESET', 'full', str).strip().lower()
    if preset not in PRESETS:
        preset = 'full'
    words = preset == 'words'
    lean = preset == 'lean'

    if lean:
        # lean strips to the core but keeps the fun treat (kill it with SHOW_TREAT=0)
        flags = dict(treat=1, burn=0, cache=0, breakdown=0, today=0,
                     gauges=1, pr=0, gitcounts=0, runway=0)
    else:
        # full and words start with everything; words renders it in plain English
        flags = dict(treat=1, burn=1, cache=1, breakdown=1, today=1,
                     gauges=not words, pr=1, gitcounts=1, runway=1)

    return SimpleNamespace(
        PRESET=preset, WORDS=words, LEAN=lean,
        FLAGS=flags, DROP_ORDER=DROP_ORDER,
        CONFIG_PATH=config_path,
        DAILY_FILE=env('CCSTATUS_DAILY_FILE') or os.path.expanduser('~/.claude/ccstatus-daily.txt'),
        BAR_W=cfg('BAR_W', 10),
        LIMIT_BAR_W=cfg('LIMIT_BAR_W', 6),
        ALERT_PCT=cfg('ALERT_PCT', 90),
        CTX_ALERT=cfg('CTX_ALERT', 80),
        TREAT_BUCKET=cfg('TREAT_BUCKET', 600),
        SHOW_TREAT=cfg('SHOW_TREAT', 1),
        SHOW_PR=cfg('SHOW_PR', 1),
        LINKS=cfg('LINKS', 1),
        TR_WINDOW=cfg('TR_WINDOW', 1800),
        TR_SPACING=cfg('TR_SPACING', 45),
        TR_MINHIST=cfg('TR_MINHIST', 150),
        TR_RATEMIN=cfg('TR_RATEMIN', 1.0, float),
    )
