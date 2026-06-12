"""Tiny management CLI, reached when statusline.py is run WITH arguments.

With no arguments the script is the Claude Code render command (reads JSON on
stdin). With arguments it self-manages, so switching presets or previewing a
look never means hand-editing a config file:

    statusline.py preset words      set the density (full | words | lean)
    statusline.py preview [name]    render a sample line right now
    statusline.py doctor            check the install is wired up
"""
import io
import os
import sys
import time
from types import SimpleNamespace

from . import config, render, session
from .palette import BOLD, CYAN, GREEN, RED, RESET, paint
from .trend import TrendTracker

SAMPLE = (
    '{"model":{"display_name":"Opus 4.8"},"session_id":"preview","effort":{"level":"high"},'
    '"workspace":{"current_dir":"/home/you/claude-statusline"},'
    '"context_window":{"used_percentage":58,"total_input_tokens":116000,'
    '"total_output_tokens":8200,"context_window_size":200000},'
    '"cost":{"total_cost_usd":4.73,"total_lines_added":214,"total_lines_removed":38,'
    '"total_duration_ms":5400000},'
    '"rate_limits":{"five_hour":{"used_percentage":47,"resets_at":%d},'
    '"seven_day":{"used_percentage":63,"resets_at":%d}},'
    '"pr":{"number":42,"review_state":"approved"}}'
)


def _say(msg):
    print(paint(CYAN, '▌') + ' ' + msg)


def _config_path():
    return os.environ.get('CCSTATUS_CONFIG') or os.path.expanduser('~/.claude/ccstatus.config')


def _sample_session(C, now):
    """A fully-populated Session for previews, with no real side effects."""
    S = session.read(io.StringIO(SAMPLE % (now + 9000, now + 360000)))
    S.NOW, S.COLS = now, 0                            # COLS 0 => show full detail
    S.git = SimpleNamespace(branch='main', staged=3, modified=1,
                            untracked=3, ahead=0, behind=0)
    S.SIN, S.SOUT, S.CACHE = 116000, 8200, 90000
    S.DAILY = 16_300_000
    tr = TrendTracker('preview', now, C.TR_WINDOW, C.TR_SPACING, C.TR_MINHIST, C.TR_RATEMIN)
    try:
        open(tr.path, 'w').write(f'{now - 600} 39.00 60.00 44.00\n')
    except OSError:
        pass
    S.tr = tr.update(S.FIVE, S.WEEK, S.PCT)
    return S


def _render_preview(preset):
    if preset:
        os.environ['CCSTATUS_PRESET'] = preset
    C = config.load()
    return render.render_text(_sample_session(C, int(time.time())), C)


def cmd_preview(args):
    preset = args[0] if args else None
    if preset and preset not in config.PRESETS:
        return _fail(f"unknown preset '{preset}'. Choose: {', '.join(config.PRESETS)}")
    print(_render_preview(preset))
    return 0


def cmd_preset(args):
    if not args or args[0] not in config.PRESETS:
        return _fail(f"usage: preset <{' | '.join(config.PRESETS)}>")
    name = args[0]
    path = _config_path()
    lines = []
    try:
        lines = open(path).read().splitlines()
    except OSError:
        pass
    out, done = [], False
    for ln in lines:
        head = ln.split('#', 1)[0]
        if '=' in head and head.split('=', 1)[0].strip().upper() == 'PRESET':
            out.append(f'PRESET = {name}')
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f'PRESET = {name}')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as fh:
        fh.write('\n'.join(out) + '\n')
    _say(f"preset set to {paint(BOLD + GREEN, name)} in {path}")
    print(_render_preview(name))
    _say("open a new session or /resume to see it live.")
    return 0


def cmd_doctor(_args):
    ok = True

    def check(label, good, detail=''):
        nonlocal ok
        ok = ok and good
        mark = paint(GREEN, '✓') if good else paint(RED, '✗')
        print(f'  {mark} {label}{("  " + detail) if detail else ""}')

    print(paint(BOLD, 'claude-statusline doctor'))
    check(f'python {sys.version_info.major}.{sys.version_info.minor}', sys.version_info >= (3, 8))
    check('ccstatus package importable', True)

    settings = os.path.join(os.environ.get('CLAUDE_CONFIG_DIR', os.path.expanduser('~/.claude')),
                            'settings.json')
    cmd, wired = '', False
    try:
        import json
        cmd = (json.load(open(settings)).get('statusLine') or {}).get('command', '')
        wired = bool(cmd)
    except (OSError, ValueError):
        pass
    check('settings.json statusLine set', wired, cmd)
    if cmd:
        target = os.path.expanduser(cmd)
        check('status command file exists', os.path.exists(target), target)

    cfg = _config_path()
    if os.path.exists(cfg):
        check('config file present', True, cfg)
    _say('all good.' if ok else 'some checks failed; see the README install steps.')
    return 0 if ok else 1


def _fail(msg):
    print(paint(RED, '✗') + ' ' + msg, file=sys.stderr)
    return 2


def _usage():
    print(__doc__.strip())
    return 0


COMMANDS = {'preset': cmd_preset, 'preview': cmd_preview, 'doctor': cmd_doctor,
            'help': lambda a: _usage(), '--help': lambda a: _usage(), '-h': lambda a: _usage()}


def run(argv):
    if not argv:
        return _usage()
    cmd = COMMANDS.get(argv[0])
    if not cmd:
        return _fail(f"unknown command '{argv[0]}'. Try: {', '.join(sorted(COMMANDS))}")
    return cmd(argv[1:])
