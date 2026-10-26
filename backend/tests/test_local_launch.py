"""Check actual launch-script arguments without starting paid or persistent services."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executable(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def run(script, **kwargs):
    return subprocess.check_output(['bash', str(script)], text=True, timeout=5, **kwargs)


def test_backend_binds_loopback_and_reload_is_explicit(tmp_path):
    script = tmp_path / 'backend/run.sh'
    script.parent.mkdir()
    shutil.copy(ROOT / 'backend/run.sh', script)
    executable(tmp_path / '.venv/bin/uvicorn', '#!/bin/sh\nprintf "%s\\n" "$@"\n')
    args = run(script).splitlines()
    assert args[args.index('--host') + 1] == '127.0.0.1'
    assert '--reload' not in args
    assert '--reload' in subprocess.check_output(['bash', str(script), '--reload'], text=True, timeout=5)


def test_frontend_binds_loopback(tmp_path):
    script = tmp_path / 'scripts/run-frontend.sh'
    script.parent.mkdir()
    shutil.copy(ROOT / 'scripts/run-frontend.sh', script)
    css = tmp_path / 'frontend/css/tailwind.css'
    css.parent.mkdir(parents=True)
    css.touch()
    executable(tmp_path / 'bin/python3', '#!/bin/sh\nprintf "%s\\n" "$@"\n')
    output = run(script, env={**os.environ, 'PATH': f"{tmp_path / 'bin'}:{os.environ['PATH']}"}).splitlines()
    assert output[-2:] == ['--bind', '127.0.0.1']


def test_lightrag_overrides_existing_public_binding(tmp_path):
    script = tmp_path / 'scripts/run-lightrag.sh'
    script.parent.mkdir()
    shutil.copy(ROOT / 'scripts/run-lightrag.sh', script)
    work = tmp_path / 'backend/data/lightrag'
    work.mkdir(parents=True)
    (work / '.env').write_text('HOST=0.0.0.0\nLLM_MODEL=test-model\nEMBEDDING_BINDING=openai\n')
    executable(tmp_path / 'backend/LightRAG/.venv/bin/lightrag-server', '#!/bin/sh\nexit 0\n')
    run(script)
    text = (work / '.env').read_text()
    assert 'HOST=127.0.0.1' in text and 'HOST=0.0.0.0' not in text
    assert 'LLM_MODEL=test-model' in text
