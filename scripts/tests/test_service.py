"""Validate generated Linux service units without installing or starting them."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from configure_service import render_units, unit_value

ROOT = Path(__file__).resolve().parents[2]


class ServiceTests(unittest.TestCase):
    def test_systemd_accepts_units_with_spaces_and_percent_in_project_path(self):
        if not sys.platform.startswith('linux') or not shutil.which('systemd-analyze'):
            self.skipTest('systemd-analyze is not available')
        with tempfile.TemporaryDirectory(prefix='english service % spaces ') as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'config/systemd', root / 'config/systemd', ignore=shutil.ignore_patterns('generated'))
            config = root / 'config/job.toml'
            config.write_text('inbox = "content/Inbox"\ncontent = "content"\n')
            launcher = root / 'config/start.sh'
            launcher.write_text('#!/usr/bin/env bash\nexit 0\n')
            units, inbox = render_units(root, config, os.environ.get('PATH', ''))
            inbox.mkdir(parents=True)
            output = root / 'generated'
            output.mkdir()
            paths = []
            for name, text in units.items():
                path = output / name
                path.write_text(text)
                paths.append(str(path))
            result = subprocess.run(['systemd-analyze', 'verify', *paths], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_inbox_outside_project_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'job.toml'
            config.write_text('inbox = "../outside"\ncontent = "content"\n')
            with self.assertRaises(ValueError):
                render_units(root, config, '')

    def test_rejects_multiline_environment_value(self):
        with self.assertRaises(ValueError):
            unit_value('PATH=/usr/bin\nExecStart=another-command')


if __name__ == '__main__':
    unittest.main()
