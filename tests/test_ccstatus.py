#!/usr/bin/env python3
"""Test suite for claude-statusline. Pure stdlib unittest, no dependencies.

Run:  python3 -m unittest discover -s tests
  or: python3 tests/test_ccstatus.py
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ccstatus import config, palette, session, textutil, treats
from ccstatus.trend import TrendTracker

_ANSI = re.compile(r'\x1b\[[0-9;]*m|\x1b\]8;;[^\x07\x1b]*(?:\x07|\x1b\\)')
strip = lambda s: _ANSI.sub('', s)


class TextUtil(unittest.TestCase):
    def test_inum_fnum(self):
        self.assertEqual(textutil.inum('42'), 42)
        self.assertEqual(textutil.inum('x', 7), 7)
        self.assertEqual(textutil.fnum('3.5'), 3.5)
        self.assertIsNone(textutil.fnum('nope'))

    def test_ftok(self):
        self.assertEqual(textutil.ftok(950), '950')
        self.assertEqual(textutil.ftok(1500), '1.5k')
        self.assertEqual(textutil.ftok(2_500_000), '2.5M')

    def test_fdur(self):
        self.assertEqual(textutil.fdur(None), '')
        self.assertEqual(textutil.fdur(0), 'now')
        self.assertEqual(textutil.fdur(3600), '1.0h')
        self.assertEqual(textutil.fdur(90000), '1.0d')

    def test_fup(self):
        self.assertEqual(textutil.fup(30), '0m')
        self.assertEqual(textutil.fup(1800), '30m')
        self.assertEqual(textutil.fup(7200), '2.0h')

    def test_dw_ignores_escapes(self):
        plain = 'context 58%'
        colored = palette.paint(palette.RED, plain)
        self.assertEqual(textutil.dw(plain), textutil.dw(colored))

    def test_dw_wide_chars(self):
        self.assertEqual(textutil.dw('ab'), 2)
        self.assertEqual(textutil.dw('🥐'), 2)          # emoji is double-width

    def test_trunc(self):
        out = textutil.trunc('hello world', 5)
        self.assertEqual(strip(out), 'hello')
        self.assertTrue(out.endswith(palette.RESET))
        # escapes do not count toward the width budget
        colored = palette.paint(palette.GREEN, 'hello world')
        self.assertEqual(strip(textutil.trunc(colored, 5)), 'hello')


class Palette(unittest.TestCase):
    def test_gradient_endpoints(self):
        self.assertEqual(palette.grad(0.0), (63, 185, 80))
        self.assertEqual(palette.grad(1.0), (248, 81, 73))

    def test_grad_clamps(self):
        self.assertEqual(palette.grad(-5), palette.grad(0.0))
        self.assertEqual(palette.grad(9), palette.grad(1.0))

    def test_bar_width(self):
        for w in (6, 10, 14):
            for pct in (0, 33, 50, 100):
                # visible width is the gauge plus its two frame caps
                self.assertEqual(textutil.dw(palette.bar(pct, w)), w + 2)


class Config(unittest.TestCase):
    def setUp(self):
        # isolate from the developer's real env/config during these tests
        self._saved = {k: os.environ.pop(k) for k in list(os.environ)
                       if k.startswith('CCSTATUS_')}
        self._tmp = tempfile.mkdtemp()
        os.environ['CCSTATUS_CONFIG'] = os.path.join(self._tmp, 'missing.config')

    def tearDown(self):
        for k in list(os.environ):
            if k.startswith('CCSTATUS_'):
                del os.environ[k]
        os.environ.update(self._saved)

    def test_defaults(self):
        C = config.load()
        self.assertEqual(C.PRESET, 'full')
        self.assertEqual(C.BAR_W, 10)
        self.assertTrue(C.FLAGS['gitcounts'])

    def test_preset_selection(self):
        os.environ['CCSTATUS_PRESET'] = 'lean'
        C = config.load()
        self.assertTrue(C.LEAN)
        self.assertEqual(C.FLAGS['runway'], 0)
        self.assertEqual(C.FLAGS['treat'], 1)          # lean keeps the treat

    def test_invalid_preset_falls_back(self):
        os.environ['CCSTATUS_PRESET'] = 'bogus'
        self.assertEqual(config.load().PRESET, 'full')

    def test_precedence_env_over_file_over_default(self):
        path = os.path.join(self._tmp, 'ccstatus.config')
        with open(path, 'w') as fh:
            fh.write('# comment\nPRESET = words\nBAR_W = 7\n')
        os.environ['CCSTATUS_CONFIG'] = path
        C = config.load()
        self.assertEqual(C.PRESET, 'words')            # file beats default
        self.assertEqual(C.BAR_W, 7)
        os.environ['CCSTATUS_BAR_W'] = '99'
        self.assertEqual(config.load().BAR_W, 99)      # env beats file


class Session(unittest.TestCase):
    def test_parses_fields(self):
        payload = ('{"model":{"display_name":"Opus 4.8"},'
                   '"session_id":"abc","context_window":{"used_percentage":58},'
                   '"cost":{"total_cost_usd":4.73}}')
        S = session.read(io.StringIO(payload))
        self.assertEqual(S.MODEL, 'Opus 4.8')
        self.assertEqual(S.PCT, 58)
        self.assertAlmostEqual(S.COST, 4.73)

    def test_empty_defaults(self):
        S = session.read(io.StringIO('not json'))
        self.assertEqual(S.MODEL, 'Claude')
        self.assertEqual(S.PCT, 0)
        self.assertEqual(S.COST, 0.0)


class Treats(unittest.TestCase):
    def test_deterministic_within_bucket(self):
        a = treats.treat_text(10.0, 'sess', 100, 600)
        b = treats.treat_text(10.0, 'sess', 200, 600)   # same bucket (100//600 == 200//600)
        self.assertEqual(a, b)
        self.assertRegex(a, r'^\S+ \d+\.\d ')

    def test_scales_with_cost(self):
        cheap = treats.treat_text(5.0, 'sess', 0, 600)
        dear = treats.treat_text(50.0, 'sess', 0, 600)  # 10x cost, same snack
        self.assertNotEqual(cheap, dear)


class Trend(unittest.TestCase):
    def _tracker(self, now, prior_line):
        sid = f'pytest-{os.getpid()}'
        path = f'/tmp/ccstatus-rate-{sid}'
        with open(path, 'w') as fh:
            fh.write(prior_line + '\n')
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return TrendTracker(sid, now, window=1800, spacing=45, minhist=150, ratemin=1.0)

    def test_runway_projection(self):
        now = 1_000_000
        t = self._tracker(now, f'{now-300} 40.00 60.00 40.00')   # ctx 40% 300s ago
        t.update(47.0, 60.0, 58)                                  # now at 58%
        # rate = (58-40)/300 = 0.06 %/s ; runway = (100-58)/0.06 = 700s
        self.assertAlmostEqual(t.runway(58), 700.0, delta=1.0)

    def test_arrow_climbing_vs_steady(self):
        now = 1_000_000
        t = self._tracker(now, f'{now-300} 40.00 60.00 40.00')
        t.update(58.0, 60.05, 58)
        self.assertEqual(t.arrow(58.0, 1), '▲')                   # 5h climbed 216%/hr
        self.assertEqual(t.arrow(60.05, 2), '→')                  # 7d only 0.6%/hr (< 1.0)


class EndToEnd(unittest.TestCase):
    JSON = ('{"model":{"display_name":"Opus 4.8"},"session_id":"e2e",'
            '"context_window":{"used_percentage":58,"total_input_tokens":116000,'
            '"total_output_tokens":8200,"context_window_size":200000},'
            '"cost":{"total_cost_usd":4.73,"total_duration_ms":5400000},'
            '"rate_limits":{"five_hour":{"used_percentage":47},'
            '"seven_day":{"used_percentage":63}}}')

    def _run(self, preset, cols):
        env = dict(os.environ, CCSTATUS_PRESET=preset, CCSTATUS_COLS=str(cols),
                   CCSTATUS_LINKS='0', CCSTATUS_DAILY_FILE='/tmp/ccstatus-e2e-daily.txt')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'statusline.py')],
                           input=self.JSON, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip('\n').split('\n')

    def test_always_four_rows(self):
        for preset in ('full', 'words', 'lean'):
            self.assertEqual(len(self._run(preset, 200)), 4, f'{preset} row count')

    def test_never_exceeds_pane_width(self):
        cols = 44
        for line in self._run('full', cols):
            self.assertLessEqual(textutil.dw(line), cols)         # wrap-safety

    def test_expected_content(self):
        full = '\n'.join(strip(l) for l in self._run('full', 220))
        self.assertIn('Opus 4.8', full)
        self.assertIn('58%', full)
        self.assertIn('$4.73', full)
        words = '\n'.join(strip(l) for l in self._run('words', 240))
        self.assertIn('context', words)
        self.assertIn('spent', words)


class CLI(unittest.TestCase):
    def _run(self, *args, **env):
        e = dict(os.environ, CCSTATUS_DAILY_FILE='/tmp/ccstatus-cli-daily.txt', **env)
        return subprocess.run([sys.executable, os.path.join(ROOT, 'statusline.py'), *args],
                              capture_output=True, text=True, env=e)

    def test_preview_renders_four_rows(self):
        r = self._run('preview', 'words')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(r.stdout.rstrip('\n').split('\n')), 4)
        self.assertIn('context', strip(r.stdout))

    def test_preset_writes_config(self):
        cfg = os.path.join(tempfile.mkdtemp(), 'ccstatus.config')
        r = self._run('preset', 'lean', CCSTATUS_CONFIG=cfg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('PRESET = lean', open(cfg).read())

    def test_preset_rejects_garbage(self):
        self.assertEqual(self._run('preset', 'bogus').returncode, 2)

    def test_unknown_command(self):
        self.assertEqual(self._run('frobnicate').returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
