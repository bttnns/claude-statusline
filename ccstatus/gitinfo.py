"""One `git status --porcelain --branch`, parsed and cached 5s per session."""
import os
import re
import subprocess
import time
from types import SimpleNamespace

US = '\x1f'   # cache field separator


def _fresh(path, ttl):
    try:
        return (time.time() - os.path.getmtime(path)) <= ttl
    except OSError:
        return False


def _empty():
    return SimpleNamespace(branch='', staged=0, modified=0,
                           untracked=0, ahead=0, behind=0)


def _pack(ns):
    return US.join(str(x) for x in
                   (ns.branch, ns.staged, ns.modified, ns.untracked, ns.ahead, ns.behind))


def _unpack(line):
    p = (line.rstrip('\n').split(US) + [''] * 6)[:6]
    return SimpleNamespace(
        branch=p[0],
        staged=int(p[1] or 0), modified=int(p[2] or 0), untracked=int(p[3] or 0),
        ahead=int(p[4] or 0), behind=int(p[5] or 0),
    )


def collect(directory, session):
    """Return a struct of branch + dirty/ahead/behind counts (cached 5s)."""
    cache = f'/tmp/ccstatus-git-{session}'
    if _fresh(cache, 5):
        try:
            return _unpack(open(cache).read())
        except OSError:
            pass

    info = _empty()
    try:
        r = subprocess.run(['git', '-C', directory, 'status', '--porcelain', '--branch'],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            lines = r.stdout.split('\n')
            if lines and lines[0].startswith('## '):
                h = lines[0][3:]
                if h.startswith('HEAD '):
                    info.branch = 'HEAD'
                elif h.startswith('No commits yet on '):
                    rest = h[len('No commits yet on '):].split()
                    info.branch = rest[0] if rest else ''
                else:
                    info.branch = re.split(r'\.\.\.| ', h, maxsplit=1)[0]
                m = re.search(r'ahead (\d+)', h);  info.ahead = int(m.group(1)) if m else 0
                m = re.search(r'behind (\d+)', h); info.behind = int(m.group(1)) if m else 0
            for ln in lines[1:]:
                if len(ln) >= 2:
                    if ln[0] in 'MADRCU':
                        info.staged += 1
                    if ln[1] in 'MD':
                        info.modified += 1
                    if ln[:2] == '??':
                        info.untracked += 1
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        open(cache, 'w').write(_pack(info) + '\n')
    except OSError:
        pass
    return info
