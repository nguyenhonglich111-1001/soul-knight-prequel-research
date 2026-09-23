"""Rebuild the instant stages and require the committed outputs to come back unchanged.

This is the "without hurting the result" check: a refactor of any builder must leave
every generated file byte-identical. Marked slow (~7 s); run with `pytest -m slow`.
It rewrites the files in place, so a failure leaves the new output in the working tree
for `git diff` to show."""

import os
import subprocess
import sys

import pytest
from conftest import ROOT

STAGES = [
    ['build_icon_map.py', '--check'],
    ['build_equipment.py'],
    ['build_indexes.py'],
    ['build_item_details.py'],
    ['build_guide.py'],
]
OUTPUTS = ['extracted', 'guide', 'range-guide.html']


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', check=False
    )


@pytest.mark.slow
def test_instant_stages_reproduce_committed_outputs():
    before = run('git', 'status', '--porcelain', '--', *OUTPUTS).stdout
    # An already-modified file stays ` M` however the rebuild changes it again, so the
    # status comparison below only means something from a clean starting point.
    assert before == '', f'commit or stash these outputs first:\n{before}'
    for stage in STAGES:
        r = run(sys.executable, os.path.join('tools', stage[0]), *stage[1:])
        assert r.returncode == 0, f'{stage[0]} failed:\n{r.stdout}\n{r.stderr}'
    after = run('git', 'status', '--porcelain', '--', *OUTPUTS).stdout
    assert after == before, f'outputs changed:\n{after}'
