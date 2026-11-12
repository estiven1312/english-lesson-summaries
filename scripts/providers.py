"""Noninteractive CLI adapters. No agent runs during tests or --prepare-only."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def run_agent(provider, cfg, prompt, images, job, schema_path):
    work = job / 'work'
    raw = job / 'raw-response.json'
    if raw.exists():
        raw.unlink()
    if provider == 'codex':
        args = [cfg['codex_command'], '-c', 'approval_policy="never"', 'exec',
                '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral',
                '--output-schema', str(schema_path), '-o', str(raw)]
        if cfg['model']:
            args += ['--model', cfg['model']]
        for image in images:
            args += ['--image', str(image)]
        args += ['-']
    else:
        args = [cfg['claude_command'], '-p', '--output-format', 'json',
                '--json-schema', schema_path.read_text(encoding='utf-8'),
                '--tools', 'Read', '--allowedTools', 'Read',
                '--permission-mode', 'dontAsk', '--setting-sources', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
        if cfg['model']:
            args += ['--model', cfg['model']]
    # A command is one executable, never shell text. Native CLI executables are preferred on Windows.
    stdout_path = job / 'agent-stdout.log'
    with stdout_path.open('wb') as stdout, (job / 'agent-stderr.log').open('wb') as stderr:
        process = subprocess.Popen(args, cwd=work, stdin=subprocess.PIPE, stdout=stdout,
                                   stderr=stderr, start_new_session=(os.name != 'nt'))
        try:
            process.communicate(prompt.encode('utf-8'), timeout=cfg['agent_timeout_seconds'])
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            stop_process(process)
            raise
    if process.returncode:
        raise RuntimeError(f'{provider} exited with {process.returncode}; see {job}/agent-*.log')
    if provider == 'codex':
        if not raw.exists():
            raise ValueError('Codex returned no structured response file.')
        return json.loads(raw.read_text(encoding='utf-8'))
    envelope = json.loads(stdout_path.read_text(encoding='utf-8'))
    if envelope.get('is_error') or not isinstance(envelope.get('structured_output'), dict):
        raise ValueError('Claude returned no successful structured_output; see agent-stdout.log.')
    return envelope['structured_output']
