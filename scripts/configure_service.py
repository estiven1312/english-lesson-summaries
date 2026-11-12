#!/usr/bin/env python3
"""Render Linux user-service units; optionally install/enable them when requested."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_NAMES = ('darwinglish-inbox.service', 'darwinglish-inbox.path')


def unit_value(value):
    if any(character in value for character in ('\n', '\r', '\x00')):
        raise ValueError('Unit settings must be single-line strings')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def render_units(root, config, executable_path):
    root = root.resolve()
    config = config.resolve()
    settings = tomllib.loads(config.read_text(encoding='utf-8'))
    inbox = (root / settings['inbox']).resolve()
    content = (root / settings['content']).resolve()
    if not content.is_relative_to(root) or not inbox.is_relative_to(content) or inbox == content:
        raise ValueError('Inbox must be a subdirectory of project content')
    bash = shutil.which('bash')
    if not bash:
        raise ValueError('Bash was not found on PATH')
    # Path directives take a literal path rather than a shell command.
    if any(character in str(inbox) for character in ('\n', '\r', '\x00')):
        raise ValueError('Inbox must be a single-line path')
    values = {
        '@INBOX@': str(inbox).replace('%', '%%'),
        '@PROJECT@': str(root).replace('%', '%%'),
        '@PATH_ENV@': unit_value('PATH=' + executable_path),
        '@CONFIG_ENV@': unit_value('ENGLISH_CONFIG=' + str(config)),
        '@BASH@': unit_value(bash),
        '@LAUNCHER@': unit_value(str(root / 'config/start.sh')),
    }
    units = {}
    for name in UNIT_NAMES:
        text = (root / 'config/systemd' / (name + '.in')).read_text(encoding='utf-8')
        for key, value in values.items():
            text = text.replace(key, value)
        units[name] = text
    return units, inbox


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('generate', 'install'))
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('ENGLISH_CONFIG') or ROOT / 'config/job.toml'))
    args = parser.parse_args(argv)
    if not sys.platform.startswith('linux'):
        parser.error('These units require Linux with a systemd user session')
    units, inbox = render_units(ROOT, args.config, os.environ.get('PATH', ''))
    generated = ROOT / 'config/systemd/generated'
    generated.mkdir(parents=True, exist_ok=True)
    for name, text in units.items():
        (generated / name).write_text(text, encoding='utf-8')
    print(f'Generated units: {generated}')
    if args.action == 'generate':
        return 0
    target = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'systemd/user'
    target.mkdir(parents=True, exist_ok=True)
    for name in UNIT_NAMES:
        destination = target / name
        if destination.is_symlink():
            raise ValueError(f'Remove or inspect the existing unit symlink before installing: {destination}')
        if destination.exists() and 'DarwinGlish' not in destination.read_text(encoding='utf-8'):
            raise ValueError(f'Refusing to overwrite an unrelated unit: {destination}')
    inbox.mkdir(parents=True, exist_ok=True)
    for name in UNIT_NAMES:
        shutil.copyfile(generated / name, target / name)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'darwinglish-inbox.path'], check=True)
    print('Inbox event monitoring enabled. No always-running Python watcher was installed.')
    print('Existing Inbox files are not processed merely by enabling PathChanged.')
    print('To process existing files: systemctl --user start darwinglish-inbox.service')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
